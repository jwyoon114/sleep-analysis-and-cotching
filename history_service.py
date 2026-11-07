"""Account-scoped trash, restoration, retention and calendar comparisons."""
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import json

from health_records import connect, erase_session_rows, overview

RETENTION_DAYS = 30


def trash_history(subject, db_path=None):
    with closing(connect(db_path)) as db:
        sessions = [dict(row) | {"record": json.loads(row["payload"])} for row in db.execute(
            "SELECT s.id, s.payload, t.deleted_at FROM trash_sessions t JOIN sessions s ON s.id=t.session_id WHERE s.subject=? AND t.subject=? ORDER BY t.deleted_at DESC", (subject, subject))]
        coaching = [dict(row) for row in db.execute(
            "SELECT c.id, c.session_id, c.text AS coaching, c.created_at, t.deleted_at, s.start AS session_start, EXISTS(SELECT 1 FROM trash_sessions ts WHERE ts.session_id=s.id) AS parent_in_trash FROM trash_coaching t JOIN coaching c ON c.id=t.coaching_id JOIN sessions s ON s.id=c.session_id WHERE c.account_id=? AND s.subject=? ORDER BY t.deleted_at DESC", (subject, subject))]
    for item in sessions + coaching:
        item["expires_at"] = (datetime.fromisoformat(item["deleted_at"]) + timedelta(days=RETENTION_DAYS)).isoformat()
    return {"sessions": sessions, "coaching": coaching}


def restore_record(kind, record_id, subject, db_path=None):
    if kind not in {"session", "coaching"}:
        raise ValueError("잘못된 기록 종류입니다.")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
    with closing(connect(db_path)) as db, db:
        if kind == "session":
            result = db.execute("DELETE FROM trash_sessions WHERE session_id=? AND subject=? AND deleted_at>? AND EXISTS(SELECT 1 FROM sessions WHERE id=? AND subject=?)", (record_id, subject, cutoff, record_id, subject))
        else:
            result = db.execute("DELETE FROM trash_coaching WHERE coaching_id=? AND account_id=? AND deleted_at>? AND EXISTS(SELECT 1 FROM coaching c JOIN sessions s ON s.id=c.session_id WHERE c.id=? AND c.account_id=? AND s.subject=? AND NOT EXISTS(SELECT 1 FROM trash_sessions ts WHERE ts.session_id=s.id))", (record_id, subject, cutoff, record_id, subject, subject))
        return result.rowcount > 0


def erase_coaching_rows(db, coaching_id, subject):
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "coaching" not in tables:
        return False
    row = db.execute("SELECT 1 FROM coaching WHERE id=? AND account_id=?", (coaching_id, subject)).fetchone()
    if not row:
        return False
    for table in ("trash_coaching", "coaching_context"):
        if table in tables:
            db.execute(f"DELETE FROM {table} WHERE coaching_id=?", (coaching_id,))
    db.execute("DELETE FROM coaching WHERE id=? AND account_id=?", (coaching_id, subject))
    return True


def purge_record(kind, record_id, subject, db_path=None):
    """Only trashed records can be permanently deleted by a user."""
    if kind not in {"session", "coaching"}:
        raise ValueError("잘못된 기록 종류입니다.")
    with closing(connect(db_path)) as db:
        db.execute("PRAGMA secure_delete=ON")
        with db:
            db.execute("BEGIN IMMEDIATE")
            table, column, owner = ("trash_sessions", "session_id", "subject") if kind == "session" else ("trash_coaching", "coaching_id", "account_id")
            if not db.execute(f"SELECT 1 FROM {table} WHERE {column}=? AND {owner}=?", (record_id, subject)).fetchone():
                return False
            erase = erase_session_rows if kind == "session" else erase_coaching_rows
            if not erase(db, record_id, subject):
                return False
            db.execute("INSERT OR REPLACE INTO permanent_deletions VALUES(?,?,?,?)", (kind, record_id, subject, datetime.now(timezone.utc).isoformat()))
    # A durable deletion ledger also sanitizes future backups and enables retries
    # if one existing snapshot is temporarily locked. No health payload is stored.
    from backup_policy import maintain_backups
    maintain_backups(db_path)
    return True


def expire_trash(subject, db_path=None, now=None):
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=RETENTION_DAYS)
    # Expiry needs identifiers and timestamps, never full health payloads.
    with closing(connect(db_path)) as db:
        history = {
            "sessions": list(db.execute("SELECT t.session_id AS id, t.deleted_at FROM trash_sessions t JOIN sessions s ON s.id=t.session_id WHERE t.subject=? AND s.subject=?", (subject, subject))),
            "coaching": list(db.execute("SELECT t.coaching_id AS id, t.deleted_at FROM trash_coaching t JOIN coaching c ON c.id=t.coaching_id JOIN sessions s ON s.id=c.session_id WHERE c.account_id=? AND s.subject=?", (subject, subject))),
        }
    count = 0
    for kind, items in (("session", history["sessions"]), ("coaching", history["coaching"])):
        for item in items:
            if datetime.fromisoformat(item["deleted_at"]) <= cutoff:
                count += bool(purge_record(kind, item["id"], subject, db_path))
    return count


def compare_periods(sessions, end_date, days):
    if days not in (7, 30):
        raise ValueError("비교 기간은 7일 또는 30일입니다.")
    end = date.fromisoformat(end_date) if isinstance(end_date, str) else end_date
    start = end - timedelta(days=days - 1)
    previous_start = start - timedelta(days=days)
    previous_end = start - timedelta(days=1)

    def summarize(a, b):
        records = [s for s in sessions if a.isoformat() <= s["start"][:10] <= b.isoformat()]
        result = overview(records)
        result.update(start=a.isoformat(), end=b.isoformat(), sessions=records)
        result["average_awake_minutes_per_recorded_day"] = sum(s["awake_minutes"] for s in records) / result["recorded_days"] if result["recorded_days"] else None
        by_day = {row["date"]: row for row in result["daily"]}
        result["daily"] = [by_day.get((a + timedelta(days=i)).isoformat(), {"date": (a + timedelta(days=i)).isoformat(), "asleep_minutes": None, "awake_minutes": None, "session_count": 0}) for i in range(days)]
        return result

    return {"current": summarize(start, end), "previous": summarize(previous_start, previous_end), "days": days}
