"""Persistent, non-production demo budgets in an explicitly configured SQLite ledger."""

from contextlib import contextmanager
import hashlib
from pathlib import Path
import sqlite3
import time
from uuid import uuid4


APPLICATION_ID = 0x444A4149
WINDOW_SECONDS = 24 * 60 * 60
DAILY_LIMIT = 3


class UsageUnavailable(RuntimeError):
    pass


class DemoCallLimit(ValueError):
    pass


class DuplicateRequest(ValueError):
    pass


def account_key(account_id):
    return hashlib.sha256(account_id.encode("utf-8")).hexdigest()


@contextmanager
def ledger(path, *, write=False):
    db = None
    try:
        path = Path(path)
        if write:
            db = sqlite3.connect(path, timeout=10, isolation_level=None)
            db.execute("BEGIN IMMEDIATE")
        else:
            db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10)
        db.row_factory = sqlite3.Row
        app_id = db.execute("PRAGMA application_id").fetchone()[0]
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if write and not tables and app_id == 0:
            db.execute("""CREATE TABLE requests (
                account_key TEXT NOT NULL, request_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                session_id TEXT NOT NULL, coaching_id TEXT NOT NULL, created_at REAL NOT NULL,
                sent_at REAL, status TEXT NOT NULL, model TEXT NOT NULL, input_bound INTEGER NOT NULL,
                input_tokens INTEGER, output_tokens INTEGER, total_tokens INTEGER,
                source TEXT, error_code TEXT, PRIMARY KEY(account_key, request_id)
            )""")
            db.execute("CREATE INDEX request_budget ON requests(account_key, created_at)")
            db.execute(f"PRAGMA application_id={APPLICATION_ID}")
            db.execute("PRAGMA user_version=1")
        elif app_id != APPLICATION_ID or tables != {"requests"} or db.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise UsageUnavailable("시연 사용량 저장소 설정을 확인해 주세요.")
        yield db
        if write:
            db.commit()
    except sqlite3.Error:
        raise UsageUnavailable("시연 사용량 저장소를 사용할 수 없어요.") from None
    finally:
        if db is not None:
            db.close()


def _budget(db, subject, now):
    rows = list(db.execute("""SELECT * FROM requests WHERE account_key=? AND COALESCE(sent_at,created_at)>?
        AND (sent_at IS NOT NULL OR status IN ('reserved','received','interrupted'))""",
        (subject, now - WINDOW_SECONDS)))
    return {
        "limit": DAILY_LIMIT, "window_hours": 24, "used": len(rows),
        "calls_started": sum(row["sent_at"] is not None for row in rows),
        "remaining": max(0, DAILY_LIMIT - len(rows)),
        "input_tokens": sum(row["input_tokens"] or 0 for row in rows),
        "output_tokens": sum(row["output_tokens"] or 0 for row in rows),
        "unknown_usage_calls": sum(row["sent_at"] is not None and row["total_tokens"] is None for row in rows),
    }


def summary(path, account_id):
    if not Path(path).exists():
        return {"limit": DAILY_LIMIT, "window_hours": 24, "used": 0, "calls_started": 0,
                "remaining": DAILY_LIMIT, "input_tokens": 0, "output_tokens": 0, "unknown_usage_calls": 0}
    with ledger(path) as db:
        return _budget(db, account_key(account_id), time.time())


def reserve(path, account_id, request_id, fingerprint, session_id, model, input_bound):
    subject, now = account_key(account_id), time.time()
    with ledger(path, write=True) as db:
        row = db.execute("SELECT * FROM requests WHERE account_key=? AND request_id=?", (subject, request_id)).fetchone()
        if row is not None and row["fingerprint"] != fingerprint:
            raise DuplicateRequest("같은 요청 번호의 입력이 달라졌어요. 현재 기록으로 새 요청을 시작해 주세요.")
        if row is None:
            row = db.execute("""SELECT * FROM requests WHERE account_key=? AND fingerprint=? AND COALESCE(sent_at,created_at)>?
                ORDER BY created_at DESC LIMIT 1""", (subject, fingerprint, now - WINDOW_SECONDS)).fetchone()
        if row is not None:
            return dict(row), False
        if _budget(db, subject, now)["remaining"] == 0:
            raise DemoCallLimit("최근 24시간의 실제 AI 호출 예산 3회를 모두 사용했어요. 무료 기본 조언과 샘플은 계속 이용할 수 있어요.")
        coaching_id = str(uuid4())
        db.execute("""INSERT INTO requests(account_key,request_id,fingerprint,session_id,coaching_id,
            created_at,status,model,input_bound) VALUES(?,?,?,?,?,?,'reserved',?,?)""",
            (subject, request_id, fingerprint, session_id, coaching_id, now, model, input_bound))
        row = db.execute("SELECT * FROM requests WHERE account_key=? AND request_id=?", (subject, request_id)).fetchone()
        return dict(row), True


def mark_sent(path, row):
    with ledger(path, write=True) as db:
        now = time.time()
        others = db.execute("""SELECT count(*) FROM requests WHERE account_key=? AND request_id!=?
            AND COALESCE(sent_at,created_at)>? AND (sent_at IS NOT NULL OR status IN ('reserved','received','interrupted'))""",
            (row["account_key"], row["request_id"], now - WINDOW_SECONDS)).fetchone()[0]
        if others >= DAILY_LIMIT:
            raise DemoCallLimit("최근 24시간의 실제 AI 호출 예산 3회를 모두 사용했어요.")
        duplicate = db.execute("""SELECT 1 FROM requests WHERE account_key=? AND request_id!=?
            AND fingerprint=? AND COALESCE(sent_at,created_at)>? LIMIT 1""",
            (row["account_key"], row["request_id"], row["fingerprint"], now - WINDOW_SECONDS)).fetchone()
        if duplicate:
            raise DuplicateRequest("동일한 입력의 새 요청이 이미 있어요. 저장된 결과를 확인해 주세요.")
        changed = db.execute("""UPDATE requests SET status='sent', sent_at=?
            WHERE account_key=? AND request_id=? AND status='reserved'""",
            (now, row["account_key"], row["request_id"])).rowcount
        if changed != 1:
            raise DuplicateRequest("이미 처리 중이거나 처리된 AI 요청이에요.")


def record_usage(path, row, usage):
    def count(name):
        value = getattr(usage, name, None)
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
    with ledger(path, write=True) as db:
        db.execute("""UPDATE requests SET status='received',input_tokens=?,output_tokens=?,total_tokens=?
            WHERE account_key=? AND request_id=?""",
            (count("input_tokens"), count("output_tokens"), count("total_tokens"), row["account_key"], row["request_id"]))


def finish(path, row, source, error_code=None):
    with ledger(path, write=True) as db:
        db.execute("UPDATE requests SET status='completed',source=?,error_code=? WHERE account_key=? AND request_id=?",
                   (source, error_code, row["account_key"], row["request_id"]))


def interrupt(path, row):
    # A crash or ambiguous provider failure never triggers an automatic re-send.
    with ledger(path, write=True) as db:
        db.execute("""UPDATE requests SET status=CASE WHEN sent_at IS NULL THEN 'cancelled' ELSE 'interrupted' END
            WHERE account_key=? AND request_id=?
            AND status!='completed'""", (row["account_key"], row["request_id"]))
