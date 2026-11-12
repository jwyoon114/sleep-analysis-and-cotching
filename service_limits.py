"""Optional server-side request limits shared by web and API deployments."""
from app_database import begin_write
from contextlib import closing
from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

from health_records import connect


class CoachingLimitError(ValueError):
    pass


def setting(name, default):
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        raise ValueError(f"서버의 {name} 설정은 0 이상의 정수여야 합니다.") from None
    if value < 0:
        raise ValueError(f"서버의 {name} 설정은 0 이상의 정수여야 합니다.")
    return value


def reserve_coaching_request(account_id, db_path=None):
    user_limit = setting("COACHING_USER_LIMIT_24H", 0)
    global_limit = setting("COACHING_GLOBAL_LIMIT_24H", 0)
    if not user_limit and not global_limit:
        return
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=24)).isoformat()
    with closing(connect(db_path)) as db, db:
        begin_write(db)
        if not db.execute("SELECT 1 FROM accounts WHERE id=?", (account_id,)).fetchone():
            raise LookupError("계정을 찾을 수 없습니다. 다시 로그인하세요.")
        db.execute("DELETE FROM coaching_requests WHERE requested_at<=?", (cutoff,))
        if user_limit and db.execute("SELECT count(*) FROM coaching_requests WHERE account_id=?", (account_id,)).fetchone()[0] >= user_limit:
            raise CoachingLimitError("최근 24시간의 계정별 AI 코칭 요청 한도에 도달했습니다. 나중에 다시 시도하세요.")
        if global_limit and db.execute("SELECT count(*) FROM coaching_requests").fetchone()[0] >= global_limit:
            raise CoachingLimitError("최근 24시간의 서비스 전체 AI 코칭 요청 한도에 도달했습니다. 나중에 다시 시도하세요.")
        db.execute("INSERT INTO coaching_requests VALUES(?,?,?)", (uuid4().hex, account_id, now.isoformat()))
