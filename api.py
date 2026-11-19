"""Account-based wearable sleep API. No EEG model is required."""
from typing import Literal
from uuid import UUID
from datetime import date, datetime
from zoneinfo import ZoneInfo
from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Response, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import JSONResponse
from openai import APIConnectionError, APIStatusError, RateLimitError
from pydantic import BaseModel, Field
from account_personalization import Preferences, get_personalization, save_personalization
import coaching_service
import morning_plans
import premium_service
import premium_live_coaching
import premium_ai_usage
import history_service
import backup_policy
import sleep_alarms
import health_sync
from health_records import ManualSleepConflict, delete_session, get_owned_session, import_export, list_sessions, overview, save_manual_sleep
from sleep_accounts import AuthenticationError, current_user, delete_account, login, logout, register, update_account
from service_limits import CoachingLimitError
from app_database import DatabaseUnavailable, BackupPolicyPending, connect_application_postgres, uses_postgres
from contextlib import closing

app = FastAPI(title="나의 수면 리포트 API", version="2.0.0")

@app.exception_handler(DatabaseUnavailable)
async def database_unavailable(request, error):
    code = 'backup_policy_pending' if isinstance(error, BackupPolicyPending) else 'database_unavailable'
    message = '클라우드 백업 정책 확인 전에는 영구 삭제를 사용할 수 없습니다.' if isinstance(error, BackupPolicyPending) else '데이터베이스를 사용할 수 없습니다. 잠시 후 다시 시도하세요.'
    return JSONResponse(status_code=503, content={'detail': {'code': code, 'message': message}})


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


class Registration(Credentials):
    privacy_consent: bool = False
    health_consent: bool = False
    overseas_consent: bool = False
    adult_confirmed: bool = False
    policy_version: str = ""


class CoachingRequest(BaseModel):
    analysis_id: str
    caffeine: Literal["미입력", "없음", "있음"] = "미입력"
    regularity: Literal["미입력", "대체로 일정함", "자주 달라짐"] = "미입력"
    satisfaction: Literal["미입력", "좋음", "보통", "나쁨"] = "미입력"
    age_group: Literal["미입력", "성인", "미성년자"] = "미입력"


class DemoActivationRequest(BaseModel):
    model_config = {"extra": "forbid"}
    checkout_token: str = Field(min_length=20, max_length=128)
    acknowledged: Literal[True]


class DemoCoachingRequest(CoachingRequest):
    model_config = {"extra": "forbid"}
    request_id: UUID


@app.exception_handler(premium_ai_usage.DemoCallLimit)
async def premium_call_limit(request, error):
    return JSONResponse(status_code=429, content={"detail": str(error)}, headers={"Cache-Control": "no-store"})


@app.exception_handler(premium_ai_usage.DuplicateRequest)
async def premium_duplicate_request(request, error):
    return JSONResponse(status_code=409, content={"detail": str(error)}, headers={"Cache-Control": "no-store"})


@app.exception_handler(premium_ai_usage.UsageUnavailable)
async def premium_usage_unavailable(request, error):
    return JSONResponse(status_code=503, content={"detail": str(error)}, headers={"Cache-Control": "no-store"})


@app.exception_handler(premium_service.DemoUnavailable)
async def premium_demo_unavailable(request, error):
    return JSONResponse(status_code=403, content={"detail": str(error)}, headers={"Cache-Control": "no-store"})


@app.exception_handler(premium_service.InvalidCheckout)
async def premium_checkout_invalid(request, error):
    return JSONResponse(status_code=409, content={"detail": str(error)}, headers={"Cache-Control": "no-store"})


class AccountUpdateRequest(BaseModel):
    model_config = {"extra": "forbid"}
    current_password: str = Field(min_length=1, max_length=128)
    new_username: str | None = Field(default=None, min_length=3, max_length=40)
    new_password: str | None = Field(default=None, min_length=10, max_length=128)


class AccountDeleteRequest(BaseModel):
    model_config = {"extra": "forbid"}
    current_password: str = Field(min_length=1, max_length=128)
    confirmation: Literal["계정 삭제"]


class HealthConnectionRequest(BaseModel):
    model_config = {"extra": "forbid"}
    provider: Literal["healthkit", "health_connect"]
    source_id: str = Field(min_length=1, max_length=300)
    source_name: str = Field(min_length=1, max_length=120)
    auto_coach: bool = False


class ManualSleepRequest(BaseModel):
    model_config = {"extra": "forbid"}
    start_local: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")
    end_local: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")
    timezone: str = Field(min_length=1, max_length=80)


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


@app.get("/ready")
def ready():
    # No migrations, data writes, or SQLite initialization during probes.
    if not uses_postgres():
        return JSONResponse(status_code=503, content={"status": "not_ready"}, headers={"Cache-Control": "no-store"})
    with closing(connect_application_postgres()) as db:
        db.execute("SELECT 1").fetchone()
    return JSONResponse(content={"status": "ready"}, headers={"Cache-Control": "no-store"})

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


@app.get("/plans")
def plan_overview(user=Depends(require_user)):
    return morning_plans.overview(user["id"])


@app.get("/plans/bedtime")
def bedtime_recommendation(user=Depends(require_user)):
    return morning_plans.recommend_bedtime(user["id"])


@app.post("/plans/morning-view")
def open_morning_plan(user=Depends(require_user)):
    return {"plan": morning_plans.claim_morning_view(user["id"])}


@app.post("/plans/{day}")
def save_morning_plan(day: date, request: morning_plans.PlanRequest, user=Depends(require_user)):
    try:
        return {"plan": morning_plans.save(user["id"], day, request)}
    except ValueError as error:
        raise HTTPException(409, str(error))


@app.patch("/plans/{day}")
def complete_morning_activity(day: date, request: morning_plans.CompletionRequest, user=Depends(require_user)):
    try:
        return {"plan": morning_plans.mark(user["id"], day, request)}
    except LookupError as error:
        raise HTTPException(404, str(error))


@app.delete("/plans/{day}")
def delete_morning_plan(day: date, user=Depends(require_user)):
    if not morning_plans.remove(user["id"], day):
        raise HTTPException(404, "저장된 계획이 없어요.")
    return {"plan": None}



@app.post("/auth/register", status_code=201)
def sign_up(request: Registration):
    try:
        from production_policy import require_registration_consent, is_production
        require_registration_consent(request.privacy_consent, request.health_consent, request.policy_version,
                                     request.overseas_consent, request.adult_confirmed)
        return {"user": register(request.username, request.password,
                                 consent=request.policy_version if is_production() else None)}
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


@app.get("/auth/personalization")
def personalization(response: Response, user=Depends(require_user)):
    response.headers["Cache-Control"] = "private, no-store"
    return {"personalization": get_personalization(user["id"])}


@app.post("/auth/personalization")
def complete_personalization(request: Preferences, response: Response, user=Depends(require_user)):
    response.headers["Cache-Control"] = "private, no-store"
    return {"personalization": save_personalization(user["id"], request, complete=True)}


@app.patch("/auth/personalization")
def edit_personalization(request: Preferences, response: Response, user=Depends(require_user)):
    profile = save_personalization(user["id"], request)
    if profile is None:
        raise HTTPException(409, "먼저 첫 설정을 완료해 주세요.")
    response.headers["Cache-Control"] = "private, no-store"
    return {"personalization": profile}



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
        result = delete_account(user["id"], **request.model_dump())
        premium_service.clear_demo(user["id"])
        return result
    except AuthenticationError as error:
        raise HTTPException(403, str(error))
    except ValueError as error:
        raise HTTPException(400, str(error))


@app.post("/auth/logout")
def sign_out(user=Depends(require_user), credentials=Depends(bearer)):
    logout(credentials.credentials)
    premium_service.clear_demo(user["id"])
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


def _write_manual_sleep(request, account_id, analysis_id=None):
    try:
        return save_manual_sleep(account_id, request.start_local, request.end_local, request.timezone, analysis_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from None
    except ManualSleepConflict as error:
        raise HTTPException(409, str(error)) from None
    except ValueError as error:
        raise HTTPException(400, str(error)) from None


@app.post("/watch/manual-sessions")
def create_manual_sleep(request: ManualSleepRequest, user=Depends(require_user)):
    return _write_manual_sleep(request, user["id"])


@app.patch("/watch/manual-sessions/{analysis_id}")
def edit_manual_sleep(analysis_id: str, request: ManualSleepRequest, user=Depends(require_user)):
    return _write_manual_sleep(request, user["id"], analysis_id)


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


@app.get("/premium")
def premium_status(response: Response, user=Depends(require_user)):
    response.headers["Cache-Control"] = "private, no-store"
    return premium_live_coaching.annotate_status(premium_service.status(user["id"]), user["id"])


@app.post("/premium/demo/checkout")
def premium_checkout(user=Depends(require_user)):
    return premium_service.start_checkout(user["id"])


@app.post("/premium/demo/activate")
def premium_activate(request: DemoActivationRequest, user=Depends(require_user)):
    return premium_live_coaching.annotate_status(premium_service.activate_demo(user["id"], request.checkout_token), user["id"])


@app.post("/premium/demo/coach")
def premium_generate(request: DemoCoachingRequest, response: Response, user=Depends(require_user)):
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return premium_live_coaching.generate(user["id"], request.analysis_id, str(request.request_id),
                                             request.model_dump(exclude={"analysis_id", "request_id"}))
    except LookupError:
        raise HTTPException(404, "기록을 찾을 수 없습니다.")
    except CoachingLimitError as error:
        raise HTTPException(429, str(error))


@app.delete("/premium/demo")
def premium_reset(user=Depends(require_user)):
    return premium_service.reset_demo(user["id"])


@app.get("/premium/demo/preview")
def premium_sample(response: Response, user=Depends(require_user)):
    response.headers["Cache-Control"] = "private, no-store"
    return premium_service.sample_preview(user["id"])


# Native apps use a revocable sync-only token, separate from web login.
@app.get("/watch/health/connection")
def health_connection(user=Depends(require_user)):
    return health_sync.status(user["id"])


@app.post("/watch/health/connection")
def connect_health(request: HealthConnectionRequest, user=Depends(require_user)):
    return health_sync.pair(user["id"], **request.model_dump())


@app.delete("/watch/health/connection")
def disconnect_health(user=Depends(require_user)):
    health_sync.disconnect(user["id"])
    return {"status": "disconnected"}


@app.post("/mobile/health-sync")
def sync_health(
    snapshot: dict,
    tasks: BackgroundTasks,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    try:
        result = health_sync.synchronize(
            credentials.credentials if credentials else None, snapshot
        )
        result["advice_queued"] = bool(
            result.pop("auto_coach") and result["added_sessions"] > 0
        )
        if result["advice_queued"]:
            tasks.add_task(
                health_sync.auto_advice, result["account_id"], result["analysis_ids"]
            )
        result.pop("account_id")
        return result
    except AuthenticationError as error:
        raise HTTPException(401, str(error))
    except (ValueError, KeyError, TypeError, OverflowError) as error:
        raise HTTPException(400, "건강 기록을 확인하세요: " + str(error))
