"""Account-based wearable sleep API. No EEG model is required."""
from typing import Literal
from datetime import date, datetime
from zoneinfo import ZoneInfo
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from openai import APIConnectionError, APIStatusError, RateLimitError
from pydantic import BaseModel, Field
import coaching_service
import history_service
import backup_policy
import sleep_alarms
from health_records import delete_session, get_owned_session, import_export, list_sessions, overview
from sleep_accounts import AuthenticationError, current_user, delete_account, login, logout, register, update_account
from service_limits import CoachingLimitError

app = FastAPI(title="나의 수면 리포트 API", version="2.0.0")
@app.on_event("startup")
def start_alarm_scheduler():
    sleep_alarms.start_worker()

class AlarmRequest(BaseModel):
    model_config = {"extra": "forbid"}
    bedtime: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    wake_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    timezone: str = Field(default="Asia/Seoul", max_length=80)
    enabled: bool
    coaching_id: str | None = Field(default=None,max_length=80)
bearer = HTTPBearer(auto_error=False)


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=1, max_length=128)


class CoachingRequest(BaseModel):
    analysis_id: str
    caffeine: Literal["미입력", "없음", "있음"] = "미입력"
    regularity: Literal["미입력", "대체로 일정함", "자주 달라짐"] = "미입력"
    satisfaction: Literal["미입력", "좋음", "보통", "나쁨"] = "미입력"
    age_group: Literal["미입력", "성인", "미성년자"] = "미입력"


class AccountUpdateRequest(BaseModel):
    model_config = {"extra": "forbid"}
    current_password: str = Field(min_length=1, max_length=128)
    new_username: str | None = Field(default=None, min_length=3, max_length=40)
    new_password: str | None = Field(default=None, min_length=10, max_length=128)


class AccountDeleteRequest(BaseModel):
    model_config = {"extra": "forbid"}
    current_password: str = Field(min_length=1, max_length=128)
    confirmation: Literal["계정 삭제"]


def require_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    try:
        user = current_user(credentials.credentials if credentials else None)
        history_service.expire_trash(user["id"])
        return user
    except AuthenticationError as error:
        raise HTTPException(401, str(error), headers={"WWW-Authenticate": "Bearer"})


@app.get("/health")
def health():
    return {"status": "ok", "service": "wearable_sleep", "supported_formats": ["Health Data Export Markdown (.md)", "Sleep JSON v1 (.json)", "Health Export Kit JSON v2 (.json)"]}

@app.get("/alarms")
def alarms(user=Depends(require_user)):
    return sleep_alarms.get_settings(user['id'])

@app.post("/alarms")
def save_alarms(request: AlarmRequest,user=Depends(require_user)):
    try:
        return sleep_alarms.save_settings(user['id'],request.bedtime,request.wake_time,request.timezone,request.enabled,request.coaching_id)
    except ValueError as error:
        raise HTTPException(400,str(error))

@app.post("/alarms/test")
def test_alarm(user=Depends(require_user)):
    if not sleep_alarms.desktop_available(): raise HTTPException(400,'이 PC에서는 알람을 사용할 수 없습니다.')
    sleep_alarms.notify('bedtime')
    return {'status':'started'}


@app.post("/auth/register", status_code=201)
def sign_up(request: Credentials):
    try:
        return {"user": register(request.username, request.password)}
    except ValueError as error:
        raise HTTPException(400, str(error))


@app.post("/auth/login")
def sign_in(request: Credentials):
    try:
        return login(request.username, request.password)
    except AuthenticationError as error:
        raise HTTPException(401, str(error))


@app.get("/auth/me")
def me(user=Depends(require_user)):
    return {"user": user}


@app.patch("/auth/me")
def edit_me(request: AccountUpdateRequest, user=Depends(require_user)):
    try:
        return {"user": update_account(user["id"], **request.model_dump())}
    except AuthenticationError as error:
        raise HTTPException(403, str(error))
    except ValueError as error:
        raise HTTPException(400, str(error))


@app.delete("/auth/me")
def delete_me(request: AccountDeleteRequest, user=Depends(require_user)):
    try:
        return delete_account(user["id"], **request.model_dump())
    except AuthenticationError as error:
        raise HTTPException(403, str(error))
    except ValueError as error:
        raise HTTPException(400, str(error))


@app.post("/auth/logout")
def sign_out(user=Depends(require_user), credentials=Depends(bearer)):
    logout(credentials.credentials)
    return {"status": "logged_out"}


@app.post("/analyze")
@app.post("/watch/import")
def import_watch(file: UploadFile = File(...), user=Depends(require_user)):
    try:
        if not (file.filename or "").lower().endswith((".md", ".json")):
            raise HTTPException(400, "수면 기록 .md 또는 .json 파일을 선택하세요.")
        content = file.file.read(10 * 1024 * 1024 + 1)
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(413, "최대 10MiB입니다.")
        return import_export(content.decode("utf-8-sig"), file.filename, user["id"])
    except (ValueError, KeyError, UnicodeError, OverflowError) as error:
        raise HTTPException(400, f"파일 형식을 확인하세요: {error}")
    finally:
        file.file.close()


@app.get("/watch/sessions")
def watch_sessions(user=Depends(require_user)):
    records = list_sessions(user["id"])
    return {"sessions": records, "overview": overview(records)}


@app.get("/watch/sessions/{analysis_id}")
def watch_session(analysis_id: str, user=Depends(require_user)):
    result = get_owned_session(analysis_id, user["id"])
    if result is None:
        raise HTTPException(404, "기록을 찾을 수 없습니다.")
    return result


@app.get("/watch/sessions/{analysis_id}/coaching")
def saved_coaching(analysis_id: str, user=Depends(require_user)):
    watch_session(analysis_id, user)
    records = coaching_service.list_coaching(user["id"], analysis_id)
    return {"result": records[0] if records else None, "history": records}


@app.delete("/watch/sessions/{analysis_id}")
def remove_session(analysis_id: str, user=Depends(require_user)):
    if not delete_session(analysis_id, user["id"]):
        raise HTTPException(404, "기록을 찾을 수 없습니다.")
    return {"status": "trashed", "retention_days": history_service.RETENTION_DAYS}


@app.delete("/watch/sessions/{analysis_id}/coaching/{coaching_id}")
def remove_coaching(analysis_id: str, coaching_id: str, user=Depends(require_user)):
    if not coaching_service.delete_coaching(user["id"], analysis_id, coaching_id):
        raise HTTPException(404, "조언을 찾을 수 없습니다.")
    return {"status": "trashed", "retention_days": history_service.RETENTION_DAYS}


@app.get("/watch/trash")
def view_trash(user=Depends(require_user)):
    return history_service.trash_history(user["id"])


@app.post("/watch/trash/{kind}/{record_id}/restore")
def restore_trash(kind: Literal["session", "coaching"], record_id: str, user=Depends(require_user)):
    if not history_service.restore_record(kind, record_id, user["id"]):
        raise HTTPException(404, "복원할 기록이 없거나 복원 기간이 지났습니다. 코칭의 분석 기록이 휴지통에 있다면 먼저 복원하세요.")
    return {"status": "restored"}


@app.delete("/watch/trash/{kind}/{record_id}")
def purge_trash(kind: Literal["session", "coaching"], record_id: str, user=Depends(require_user)):
    if not history_service.purge_record(kind, record_id, user["id"]):
        raise HTTPException(404, "휴지통의 기록을 찾을 수 없습니다.")
    return {"status": "permanently_deleted", "backups": backup_policy.maintain_backups()}


@app.get("/watch/comparison")
def comparison(days: int = 7, end_date: date | None = None, user=Depends(require_user)):
    try:
        return history_service.compare_periods(list_sessions(user["id"]), end_date or datetime.now(ZoneInfo("Asia/Seoul")).date(), days)
    except ValueError as error:
        raise HTTPException(400, str(error))


@app.get("/watch/backup-policy")
def backup_status(user=Depends(require_user)):
    return backup_policy.maintain_backups()


@app.post("/coach")
def coach(request: CoachingRequest, user=Depends(require_user)):
    watch_session(request.analysis_id, user)
    try:
        return coaching_service.generate(user["id"], request.analysis_id, request.model_dump(exclude={"analysis_id"}))
    except RateLimitError as error:
        raise HTTPException(429, coaching_service.api_limit_detail(error))
    except APIConnectionError:
        raise HTTPException(502, "AI 서버 연결을 확인하세요. 수면 기록은 저장되어 있습니다.")
    except APIStatusError:
        raise HTTPException(502, "서버의 OpenAI API 키와 모델 접근 권한을 확인하세요.")
    except CoachingLimitError as error:
        raise HTTPException(429, str(error))
    except ValueError as error:
        raise HTTPException(503, str(error))
    except RuntimeError as error:
        raise HTTPException(502, str(error))
