"""Retention and deletion propagation for this app's managed DB snapshots."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

import health_records
from health_records import connect, erase_session_rows

BACKUP_DAYS = 30


def managed_backups(db_path=None):
    from app_database import require_backup_policy
    require_backup_policy(db_path)
    path = Path(db_path or health_records.DB_PATH).resolve()
    # Restrict operations to recognized app backups in the DB's own directory.
    candidates = set(path.parent.glob(path.name + ".before-accounts-*.bak"))
    candidates.update(path.parent.glob(path.name + ".managed-*.bak"))
    return [p for p in sorted(candidates) if not p.is_symlink() and p.is_file() and p.resolve().parent == path.parent]


def maintain_backups(db_path=None, now=None):
    from app_database import uses_postgres
    if uses_postgres(db_path):
        from production_policy import backup_policy_ready
        if backup_policy_ready():
            return {"status": "managed_pitr", "backup_count": None, "retention_days": 7,
                    "pending": False, "permanent_deletion_available": True,
                    "message": "운영 DB에서 삭제된 자료는 복구용 백업에서 최대 7일 후 만료됩니다. 수동 백업은 생성하지 않습니다."}
        return {"status": "cloud_policy_pending", "backup_count": None,
                "retention_days": None, "pending": True,
                "permanent_deletion_available": False,
                "message": "클라우드 백업의 보관·삭제 정책 확인이 필요합니다. 영구 삭제와 자동 만료는 보류됩니다."}
    from history_service import erase_coaching_rows
    from sleep_accounts import erase_account_rows
    now = now or datetime.now(timezone.utc)
    errors, cleaned, expired = 0, 0, 0
    with closing(connect(db_path)) as db:
        deletions = list(db.execute("SELECT kind, record_id, subject, deleted_at FROM permanent_deletions"))
    for path in managed_backups(db_path):
        try:
            with path.open("rb") as file:
                if file.read(16) != b"SQLite format 3\x00":
                    raise ValueError("Unrecognized backup")
            if datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) <= now - timedelta(days=BACKUP_DAYS):
                path.unlink()
                expired += 1
                continue
            if not deletions:
                continue
            # mode=rw prevents creating a new DB if a concurrent cleanup removed it.
            with closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=5)) as snapshot:
                snapshot.row_factory = sqlite3.Row
                snapshot.execute("PRAGMA foreign_keys=ON")
                snapshot.execute("PRAGMA secure_delete=ON")
                old_time = path.stat().st_mtime
                before = snapshot.total_changes
                tables = {r[0] for r in snapshot.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                with snapshot:
                    for item in deletions:
                        if item["kind"] == "account":
                            erase_account_rows(snapshot, item["subject"])
                            continue
                        if item["kind"] == "session" and "session_created" in tables:
                            generation = snapshot.execute("SELECT created_at FROM session_created WHERE session_id=?", (item["record_id"],)).fetchone()
                            if generation and datetime.fromisoformat(generation[0]) > datetime.fromisoformat(item["deleted_at"]):
                                continue
                        erase = erase_session_rows if item["kind"] == "session" else erase_coaching_rows
                        erase(snapshot, item["record_id"], item["subject"])
                # Compact free pages without extending the retention deadline.
                changed = snapshot.total_changes > before
                if changed:
                    snapshot.execute("VACUUM")
            import os
            if changed:
                os.utime(path, (old_time, old_time))
                cleaned += 1
        except (OSError, sqlite3.Error, ValueError):
            errors += 1
    return {"backup_count": len(managed_backups(db_path)), "retention_days": BACKUP_DAYS, "cleaned": cleaned, "expired": expired, "pending": errors}


def create_backup(db_path=None):
    from app_database import uses_postgres, BackupPolicyPending
    if uses_postgres(db_path):
        raise BackupPolicyPending("클라우드 수동 백업은 지원하지 않습니다. 관리형 복구 기능을 사용하세요.")
    from app_database import require_backup_policy
    require_backup_policy(db_path)
    from uuid import uuid4
    path = Path(db_path or health_records.DB_PATH).resolve()
    target = path.with_name(path.name + ".managed-" + uuid4().hex + ".bak")
    with closing(connect(path)) as source, closing(sqlite3.connect(target)) as destination:
        source.backup(destination)
    status = maintain_backups(path)
    return status
