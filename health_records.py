"""Apple Watch Markdown import and persistent local sleep history (no EEG inference)."""
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from zoneinfo import ZoneInfo
from export_times import SHORT, bounds, point

DB_PATH = Path(os.getenv("SLEEP_DB_PATH", str(Path(__file__).parent / "data" / "sleep_records.sqlite3")))
STAGES = {"core", "deep", "rem", "wake", "unspecified"}


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_export(text):
    text = text.replace("\r\n", "\n")
    if len(text.encode("utf-8")) > 10 * 1024 * 1024:
        raise ValueError("파일은 10MiB 이하여야 합니다.")
    match = re.search(r"^- range: (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) → (\d{4}-\d{2}-\d{2} \d{2}:\d{2})$", text, re.M)
    tz_match = re.search(r"^- timezone: (.+)$", text, re.M)
    if not match or not tz_match:
        raise ValueError("Health Data Export의 range와 timezone이 필요합니다.")
    tz_name = tz_match[1].strip()
    tz = timezone(timedelta(hours=9), "Asia/Seoul") if tz_name == "Asia/Seoul" else ZoneInfo(tz_name)
    range_start, range_end = [datetime.strptime(v, "%Y-%m-%d %H:%M").replace(tzinfo=tz) for v in match.groups()]
    if range_end <= range_start or range_end - range_start > timedelta(days=366):
        raise ValueError("내보내기 날짜 범위가 올바르지 않습니다.")

    sessions = []
    active_window = None

    def clock(value):
        if SHORT.fullmatch(value.strip()):
            windows = [active_window] if active_window else [
                (datetime.fromisoformat(s["start"]) - timedelta(minutes=10),
                 datetime.fromisoformat(s["end"]) + timedelta(minutes=10)) for s in sessions]
        else:
            windows = [(range_start - timedelta(days=2), range_end + timedelta(days=2))]
        return point(value, windows, tz)

    blocks = re.finditer(r"^## Session \d+ — (.*?) → (.*?) \([^\n]*\)\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    for block in blocks:
        start, end = bounds(block[1], block[2], range_start, range_end, tz)
        active_window = (start, end)
        if end <= start or end - start > timedelta(days=2):
            raise ValueError("수면 기록 시작·종료 시각을 확인하세요.")
        body = block[3]
        source = re.search(r"^- source: (.+)$", body, re.M)
        stage_csv = re.search(r"### Stages[^\n]*\n```csv\s*\n(.*?)```", body, re.S)
        if not source or not stage_csv:
            raise ValueError("수면 기록에 source 또는 Stages CSV가 없습니다.")
        rows = list(csv.DictReader(io.StringIO(stage_csv[1].strip())))
        if not rows:
            raise ValueError("수면 단계가 비어 있습니다.")
        segments, warnings = [], []
        for i, row in enumerate(rows):
            t = clock(row["time"])
            stage = row["stage"]
            minutes = float(row["durationMin"])
            if stage not in STAGES or not math.isfinite(minutes) or minutes <= 0:
                raise ValueError("알 수 없는 수면 단계 또는 잘못된 길이입니다.")
            estimated_end = t + timedelta(minutes=minutes)
            boundary = clock(rows[i + 1]["time"]) if i + 1 < len(rows) else end
            # durationMin is rounded to 0.1 min. Prefer exact adjacent timestamps
            # only within that rounding tolerance; retain larger gaps as unrecorded.
            delta = (boundary - estimated_end).total_seconds()
            if delta < -3.1 or t < start or t >= end or boundary <= t:
                raise ValueError("수면 단계 시각이 겹치거나 기록 범위를 벗어납니다.")
            stop = boundary if abs(delta) <= 3.1 else estimated_end
            if delta > 3.1:
                warnings.append(f"{t.isoformat()} 이후 미기록 구간이 있습니다.")
            segments.append({"start": t.isoformat(), "end": stop.isoformat(), "stage": stage,
                             "minutes": (stop - t).total_seconds() / 60,
                             "exported_duration_minutes": minutes})
        if clock(rows[0]["time"]) != start:
            warnings.append("기록 시작과 첫 수면 단계 사이에 미기록 구간이 있습니다.")
        totals = {stage: sum(s["minutes"] for s in segments if s["stage"] == stage) for stage in sorted(STAGES)}
        asleep = sum(v for k, v in totals.items() if k != "wake")
        duration = (end - start).total_seconds() / 60
        declared = re.search(r"^- asleep (\d+)h (\d+)m · awake (\d+)h (\d+)m \((\d+) awakenings\) · efficiency (\d+)%", body, re.M)
        vitals = []
        table = re.search(r"### Vitals Summary\s*\n(.*?)(?=\n### |\Z)", body, re.S)
        if table:
            lines = [line.strip() for line in table[1].strip().splitlines() if line.startswith("|")]
            if len(lines) >= 2:
                headers = [v.strip() for v in lines[0].strip("|").split("|")]
                for line in lines[2:]:
                    values = [v.strip() for v in line.strip("|").split("|")]
                    if len(values) != len(headers):
                        raise ValueError("생체지표 요약 표 형식이 올바르지 않습니다.")
                    vitals.append(dict(zip(headers, values)))
        sessions.append({"data_type": "apple_watch", "source": source[1].strip(),
                         "timezone": tz_name, "start": start.isoformat(), "end": end.isoformat(),
                         "recorded_minutes": duration, "asleep_minutes": asleep,
                         "awake_minutes": totals["wake"], "stage_minutes": totals,
                         "unrecorded_minutes": max(0, duration - sum(totals.values())),
                         "session_asleep_ratio_percent": asleep / duration * 100,
                         "wake_segment_count": sum(s["stage"] == "wake" for s in segments),
                         "exported_summary": {"asleep_minutes": int(declared[1])*60+int(declared[2]),
                                              "awake_minutes": int(declared[3])*60+int(declared[4]),
                                              "awakenings": int(declared[5]), "efficiency_percent": int(declared[6])} if declared else None,
                         "vitals_summary": vitals, "segments": segments, "warnings": warnings,
                         "interpretation": "애플워치 추정 기록입니다. EEG 모델 예측이나 확정 진단이 아닙니다. 세션 내 수면 비율은 실제 침대 체류시간 기준 수면 효율과 다를 수 있습니다."})
    if not sessions:
        raise ValueError("가져올 수면 세션이 없습니다.")
    active_window = None
    streams = []
    stream_block = text.split("## Streams", 1)
    if len(stream_block) == 2:
        for stream in re.finditer(r"^### (.*?) — (\d+) samples\s*\n(.*?)(?=^### |\Z)", stream_block[1], re.M | re.S):
            source = re.search(r"^- source: (.+)$", stream[3], re.M)
            unit = re.search(r"^- unit: (.+)$", stream[3], re.M)
            data = re.search(r"```csv\s*\n(.*?)```", stream[3], re.S)
            if not source or not unit or not data:
                raise ValueError("생체지표 스트림 형식이 올바르지 않습니다.")
            records = list(csv.DictReader(io.StringIO(data[1].strip())))
            if len(records) != int(stream[2]):
                raise ValueError("생체지표 표본 수가 헤더와 다릅니다.")
            for row in records:
                value = float(row["value"])
                if not math.isfinite(value):
                    raise ValueError("생체지표에 유효하지 않은 수치가 있습니다.")
                t = clock(row["time"])
                stop = clock(row["endTime"]) if row.get("endTime") else t
                if stop < t:
                    raise ValueError("생체지표 종료 시각이 시작보다 이릅니다.")
                streams.append({"metric": stream[1], "unit": unit[1].strip(), "source": source[1].strip(),
                                "start": t.isoformat(), "end": stop.isoformat(), "value": value})
    return {"timezone": tz_name, "range_start": range_start.isoformat(), "range_end": range_end.isoformat(),
            "sessions": sessions, "samples": streams}


def connect(db_path=None):
    path = Path(db_path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    # SQLite stores the completed schema migration in the DB itself. Every
    # connection still checks it, so replacing/restoring the DB is safe.
    if db.execute("PRAGMA user_version").fetchone()[0] < 1:
        db.executescript("""
    CREATE TABLE IF NOT EXISTS imports(id TEXT PRIMARY KEY, subject TEXT NOT NULL, filename TEXT NOT NULL, imported_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, subject TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS import_sessions(import_id TEXT REFERENCES imports(id), session_id TEXT REFERENCES sessions(id), PRIMARY KEY(import_id, session_id));
    CREATE TABLE IF NOT EXISTS stages(session_id TEXT REFERENCES sessions(id), position INTEGER, start TEXT, end TEXT, stage TEXT, minutes REAL, PRIMARY KEY(session_id, position));
    CREATE TABLE IF NOT EXISTS samples(id TEXT PRIMARY KEY, subject TEXT NOT NULL, metric TEXT, source TEXT, unit TEXT, start TEXT, end TEXT, value REAL);
    CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, salt TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS auth_tokens(token_hash TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id), expires_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS login_attempts(username TEXT NOT NULL, attempted_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS coaching(id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id), session_id TEXT NOT NULL REFERENCES sessions(id), text TEXT NOT NULL, lifestyle TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS sessions_subject_start ON sessions(subject, start);
    CREATE INDEX IF NOT EXISTS samples_observation ON samples(subject, metric, source, unit, start, end);
    CREATE TABLE IF NOT EXISTS trash_sessions(session_id TEXT PRIMARY KEY REFERENCES sessions(id), subject TEXT NOT NULL, deleted_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS trash_coaching(coaching_id TEXT PRIMARY KEY REFERENCES coaching(id), account_id TEXT NOT NULL, deleted_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS coaching_context(coaching_id TEXT PRIMARY KEY REFERENCES coaching(id), payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS permanent_deletions(kind TEXT NOT NULL, record_id TEXT NOT NULL, subject TEXT NOT NULL, deleted_at TEXT NOT NULL, PRIMARY KEY(kind, record_id, subject));
    CREATE TABLE IF NOT EXISTS session_created(session_id TEXT PRIMARY KEY REFERENCES sessions(id), created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS coaching_requests(id TEXT PRIMARY KEY, account_id TEXT, requested_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS coaching_requests_time ON coaching_requests(requested_at);
    CREATE INDEX IF NOT EXISTS coaching_account_session ON coaching(account_id, session_id, created_at);
    CREATE INDEX IF NOT EXISTS trash_sessions_owner_time ON trash_sessions(subject, deleted_at);
    CREATE INDEX IF NOT EXISTS trash_coaching_owner_time ON trash_coaching(account_id, deleted_at);
    PRAGMA user_version = 1;
    """)
    return db


def session_signature(session):
    # The same observation can be exported in MD and JSON. Ignore display-only
    # summaries and rounded duration fields, while preserving clinical content.
    return {"source": session["source"], "start": session["start"], "end": session["end"],
            "segments": [{k: s[k] for k in ["start", "end", "stage"]} for s in session["segments"]],
            "vitals": sorted([{k: (float(v) if k not in {"metric", "unit"} and v not in {"—", ""} else v)
                        for k, v in vital.items() if v not in {"—", ""}} for vital in session["vitals_summary"]], key=lambda v: (v["metric"], v["unit"]))}


def same_observation(a, b):
    a, b = session_signature(a), session_signature(b)
    if any(a[k] != b[k] for k in ["source", "start", "end", "segments"]):
        return False
    if len(a["vitals"]) != len(b["vitals"]):
        return False
    for x, y in zip(a["vitals"], b["vitals"]):
        if x.keys() != y.keys():
            return False
        for key in x:
            if key in {"metric", "unit", "n"}:
                if x[key] != y[key]:
                    return False
            elif not math.isclose(x[key], y[key], rel_tol=0, abs_tol=0.100000001):
                return False
    return True


def import_export(text, filename, subject="apple_watch_owner", db_path=None):
    if not subject.strip() or len(subject) > 100:
        raise ValueError("기록 소유자 별칭은 1~100자로 입력하세요.")
    if len(text.encode("utf-8")) > 10 * 1024 * 1024:
        raise ValueError("파일은 10MiB 이하여야 합니다.")
    suffix = Path(filename).suffix.lower()
    if suffix == ".json":
        from json_sleep import parse_json_export
        parsed = parse_json_export(text)
    elif suffix == ".md":
        parsed = parse_export(text)
    else:
        raise ValueError("수면 기록 .md 또는 .json 파일을 선택하세요.")
    import_id = digest(subject + "\0" + text)
    ids, added = [], 0
    db = connect(db_path)
    try:
        with db:
            duplicate = db.execute("SELECT 1 FROM imports WHERE id=?", (import_id,)).fetchone() is not None
            db.execute("INSERT OR IGNORE INTO imports VALUES(?,?,?,?)", (import_id, subject, Path(filename).name, datetime.now(timezone.utc).isoformat()))
            for session in parsed["sessions"]:
                sid = digest(json.dumps([subject, session["source"], session["start"], session["end"]]))
                session["analysis_id"] = sid
                session["subject"] = subject
                payload = json.dumps(session, ensure_ascii=False)
                existing = db.execute("SELECT payload FROM sessions WHERE id=?", (sid,)).fetchone()
                if db.execute("SELECT 1 FROM trash_sessions WHERE session_id=?", (sid,)).fetchone():
                    raise ValueError("이 기록은 휴지통에 있습니다. 휴지통에서 복원하거나 영구 삭제한 뒤 다시 업로드하세요.")
                if existing and not same_observation(json.loads(existing["payload"]), session):
                    raise ValueError("동일 시각에 다른 내용의 기록이 이미 있습니다. 별칭과 원본을 확인하세요.")
                if not existing:
                    added += 1
                    db.execute("INSERT INTO sessions VALUES(?,?,?,?,?)", (sid, subject, session["start"], session["end"], payload))
                    db.execute("INSERT INTO session_created VALUES(?,?)", (sid, datetime.now(timezone.utc).isoformat()))
                    db.executemany("INSERT INTO stages VALUES(?,?,?,?,?,?)", [(sid, i, s["start"], s["end"], s["stage"], s["minutes"]) for i, s in enumerate(session["segments"])])
                db.execute("INSERT OR IGNORE INTO import_sessions VALUES(?,?)", (import_id, sid))
                ids.append(sid)
            for sample in parsed["samples"]:
                # Health Export Kit's MD and JSON HRV rounding differs by 0.1 ms.
                # Match the observation identity first, preserving the first value.
                prior = db.execute("SELECT value FROM samples WHERE subject=? AND metric=? AND source=? AND unit=? AND start=? AND end=?", (subject, sample["metric"], sample["source"], sample["unit"], sample["start"], sample["end"])).fetchall()
                if prior:
                    tolerance = 0.100000001 if sample["metric"] == "HRV SDNN" else 0
                    if any(not math.isclose(row["value"], sample["value"], rel_tol=0, abs_tol=tolerance) for row in prior):
                        raise ValueError("동일 시각의 생체지표 값이 기존 기록과 다릅니다. 원본 파일을 확인하세요.")
                    continue
                sample_id = digest(json.dumps([subject, sample], sort_keys=True))
                db.execute("INSERT OR IGNORE INTO samples VALUES(?,?,?,?,?,?,?,?)", (sample_id, subject, sample["metric"], sample["source"], sample["unit"], sample["start"], sample["end"], sample["value"]))
        return {"import_id": import_id, "duplicate_file": duplicate, "added_sessions": added,
                "session_count": len(ids), "sample_count": len(parsed["samples"]), "analysis_ids": ids}
    finally:
        db.close()


def list_sessions(subject="apple_watch_owner", db_path=None):
    db = connect(db_path)
    try:
        return [json.loads(row["payload"]) | {"coaching_count": row["coaching_count"]} for row in db.execute("SELECT s.payload, (SELECT count(*) FROM coaching c WHERE c.session_id=s.id AND c.account_id=s.subject AND NOT EXISTS (SELECT 1 FROM trash_coaching tc WHERE tc.coaching_id=c.id)) AS coaching_count FROM sessions s WHERE s.subject=? AND NOT EXISTS (SELECT 1 FROM trash_sessions t WHERE t.session_id=s.id) ORDER BY s.start DESC", (subject,))]
    finally:
        db.close()


def get_session(analysis_id, db_path=None):
    db = connect(db_path)
    try:
        row = db.execute("SELECT payload FROM sessions WHERE id=? AND NOT EXISTS (SELECT 1 FROM trash_sessions WHERE session_id=sessions.id)", (analysis_id,)).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        db.close()


def get_owned_session(analysis_id, subject, db_path=None):
    db = connect(db_path)
    try:
        row = db.execute("SELECT payload FROM sessions WHERE id=? AND subject=? AND NOT EXISTS (SELECT 1 FROM trash_sessions WHERE session_id=sessions.id)", (analysis_id, subject)).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        db.close()


def delete_session(analysis_id, subject, db_path=None):
    """Move an owned analysis to trash; linked coaching becomes hidden too."""
    db = connect(db_path)
    try:
        with db:
            result = db.execute("INSERT OR IGNORE INTO trash_sessions SELECT id, subject, ? FROM sessions WHERE id=? AND subject=?", (datetime.now(timezone.utc).isoformat(), analysis_id, subject))
            return result.rowcount > 0
    finally:
        db.close()


def erase_session_rows(db, analysis_id, subject):
    """Internal hard deletion, also used to sanitize managed SQLite backups."""
    row = db.execute("SELECT start, end FROM sessions WHERE id=? AND subject=?", (analysis_id, subject)).fetchone()
    if row is None:
        return False
    start, end = (datetime.fromisoformat(row[key]) for key in ("start", "end"))
    remaining = [(datetime.fromisoformat(r["start"]), datetime.fromisoformat(r["end"])) for r in db.execute("SELECT start, end FROM sessions WHERE subject=? AND id<>?", (subject, analysis_id))]
    sample_ids = []
    for sample in db.execute("SELECT id, start, end FROM samples WHERE subject=?", (subject,)):
        a, b = datetime.fromisoformat(sample["start"]), datetime.fromisoformat(sample["end"])
        if start <= a <= b <= end and not any(a <= y and b >= x for x, y in remaining):
            sample_ids.append((sample["id"],))
    db.executemany("DELETE FROM samples WHERE id=?", sample_ids)
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table, column in (("trash_coaching", "coaching_id"), ("coaching_context", "coaching_id")):
        if table in tables:
            db.execute(f"DELETE FROM {table} WHERE {column} IN (SELECT id FROM coaching WHERE session_id=?)", (analysis_id,))
    # A context snapshot for another coaching may also contain this record.
    # Remove that snapshot rather than retain a second copy of deleted data.
    if "coaching_context" in tables:
        db.execute("DELETE FROM coaching_context WHERE EXISTS (SELECT 1 FROM json_each(coaching_context.payload, '$.record_ids') WHERE value=?)", (analysis_id,))
    if "trash_sessions" in tables:
        db.execute("DELETE FROM trash_sessions WHERE session_id=?", (analysis_id,))
    if "session_created" in tables:
        db.execute("DELETE FROM session_created WHERE session_id=?", (analysis_id,))
    for table in ("coaching", "stages", "import_sessions"):
        if table in tables:
            db.execute(f"DELETE FROM {table} WHERE session_id=?", (analysis_id,))
    db.execute("DELETE FROM sessions WHERE id=? AND subject=?", (analysis_id, subject))
    db.execute("DELETE FROM imports WHERE subject=? AND NOT EXISTS (SELECT 1 FROM import_sessions WHERE import_id=imports.id)", (subject,))
    return True


def overview(sessions):
    days = {}
    for session in sessions:
        day = session["start"][:10]
        daily = days.setdefault(day, {"date": day, "asleep_minutes": 0, "awake_minutes": 0, "session_count": 0})
        daily["asleep_minutes"] += session["asleep_minutes"]
        daily["awake_minutes"] += session["awake_minutes"]
        daily["session_count"] += 1
    total = sum(s["asleep_minutes"] for s in sessions)
    return {"session_count": len(sessions), "recorded_days": len(days),
            "total_asleep_minutes": total,
            "average_asleep_minutes_per_recorded_day": total / len(days) if days else None,
            "daily": [days[key] for key in sorted(days)],
            "note": "수면 시작일 기준 합계입니다. 기록이 없는 날은 평균에서 제외하며, 하루 전체를 측정했다고 가정하지 않습니다."}


if __name__ == "__main__":
    import argparse
    cli = argparse.ArgumentParser()
    cli.add_argument("file", type=Path)
    cli.add_argument("--subject", default="apple_watch_owner")
    cli.add_argument("--db", type=Path, default=DB_PATH)
    args = cli.parse_args()
    print(json.dumps(import_export(args.file.read_text(encoding="utf-8-sig"), args.file.name, args.subject, args.db), ensure_ascii=False, indent=2))
