"""Explicitly enabled, budgeted demo requests through the existing Responses adapter."""

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path

from account_personalization import get_personalization
from coaching_expression import expression_snapshot
import coaching_service
import health_records
import manual_coaching
import premium_ai_usage as usage
import premium_service
from service_limits import CoachingLimitError, reserve_coaching_request


LABELS = {
    "openai": "AI가 실제 수면 기록을 바탕으로 생성한 조언",
    "sample": "AI 코칭 시연 예시 — 샘플 데이터",
    "rules_fallback": "기본 수면 조언 — AI 연결을 사용할 수 없어 대체 제공",
}


@dataclass(frozen=True)
class LiveConfig:
    key: str = field(repr=False)
    project: str = field(repr=False)
    model: str
    ledger: Path = field(repr=False)
    input_limit: int
    output_limit: int


def configuration():
    if not premium_service.demo_available() or os.getenv("DALJAM_PREMIUM_AI_ENABLED") != "1":
        return None
    key, project, model, filename = (os.getenv(name, "").strip() for name in (
        "OPENAI_API_KEY", "OPENAI_PROJECT_ID", "OPENAI_MODEL", "DALJAM_PREMIUM_AI_USAGE_DB",
    ))
    if not all((key, project, model, filename)):
        return None
    path = Path(filename)
    if (not path.is_absolute() or path.is_symlink() or not path.parent.is_dir()
            or path.resolve() == Path(health_records.DB_PATH).resolve()):
        return None
    try:
        input_limit = int(os.getenv("DALJAM_PREMIUM_AI_MAX_INPUT_TOKENS", "8192"))
        output_limit = int(os.getenv("DALJAM_PREMIUM_AI_MAX_OUTPUT_TOKENS", "1000"))
    except ValueError:
        return None
    if not 2048 <= input_limit <= 16000 or not 128 <= output_limit <= 1400:
        return None
    return LiveConfig(key, project, model, path.resolve(), input_limit, output_limit)


def annotate_status(state, account_id):
    config = configuration() if state["tier"] == "premium_demo" else None
    if config is None:
        return state | {"live_ai_available": False, "ai_usage": None}
    try:
        budget = usage.summary(config.ledger, account_id)
    except usage.UsageUnavailable:
        return state | {"live_ai_available": False, "ai_usage": None}
    return state | {"live_ai_available": True, "ai_usage": budget}


def _require_active(account_id):
    premium_service._require_demo()
    if premium_service.status(account_id)["tier"] != "premium_demo":
        raise premium_service.DemoUnavailable("먼저 Premium 모의 결제를 완료해 주세요.")


def _sample(account_id):
    return {"kind": "sample", "label": LABELS["sample"], "sample": premium_service.sample_preview(account_id),
            "replayed": False, "usage": None}


def input_upper_bound(data):
    # Conservative byte-based budget, including instructions, schema and protocol headroom.
    # Provider-reported token usage is recorded separately, never inferred as actual usage.
    text = manual_coaching.INSTRUCTIONS + json.dumps(data, ensure_ascii=False) + json.dumps(manual_coaching.OUTPUT_FORMAT, ensure_ascii=False)
    return len(text.encode("utf-8")) + 1024


def _result(config, account_id, row, coaching, *, replayed):
    kind = coaching["context"]["premium_demo_live"]["kind"]
    return {"kind": kind, "label": LABELS[kind], "coaching": coaching, "request_id": row["request_id"],
            "replayed": replayed, "usage": usage.summary(config.ledger, account_id)}


def generate(account_id, session_id, request_id, lifestyle, db_path=None):
    _require_active(account_id)
    record = health_records.get_owned_session(session_id, account_id, db_path)
    if record is None:
        raise LookupError("기록을 찾을 수 없습니다.")
    config = configuration()
    if config is None:
        return _sample(account_id)
    recent = manual_coaching.recent_history(record, health_records.list_sessions(account_id, db_path))
    expression = expression_snapshot(get_personalization(account_id, db_path))
    lifestyle = manual_coaching.clean_lifestyle(lifestyle)
    build = manual_coaching.payload if health_records.is_manual_sleep(record) else manual_coaching.wearable_payload
    data = build(record, recent, lifestyle, expression)
    bound = input_upper_bound(data)
    fingerprint = hashlib.sha256(json.dumps({
        "session": session_id, "data": data, "model": config.model,
        "output_limit": config.output_limit, "prompt_version": manual_coaching.PROMPT_VERSION,
    }, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    try:
        row, created = usage.reserve(config.ledger, account_id, request_id, fingerprint, session_id, config.model, bound)
    except usage.UsageUnavailable:
        return _sample(account_id)
    if not created:
        saved = next((item for item in coaching_service.list_coaching(account_id, row["session_id"], db_path)
                      if item["id"] == row["coaching_id"]), None)
        if saved is None:
            raise usage.DuplicateRequest("이 요청은 처리 중이거나 결과 확인이 필요해요. 같은 요청으로 다시 확인하면 추가 AI 호출 없이 저장 결과를 확인해요.")
        kind = saved["context"]["premium_demo_live"]["kind"]
        usage.finish(config.ledger, row, kind, saved["context"].get("fallback_reason"))
        return _result(config, account_id, row, saved | {"analysis_id": row["session_id"]}, replayed=True)

    def request(input_text):
        _require_active(account_id)
        usage.mark_sent(config.ledger, row)
        response = coaching_service.request_response(
            config.key, config.model, input_text, project=config.project,
            max_output_tokens=config.output_limit, timeout=30,
        )
        usage.record_usage(config.ledger, row, getattr(response, "usage", None))
        return response

    try:
        if bound > config.input_limit:
            answer, provider = None, {"fallback_reason": "input_limit"}
        else:
            reserve_coaching_request(account_id, db_path)
            answer, provider = coaching_service._manual_openai(data, requester=request)
        kind = "openai" if answer is not None else "rules_fallback"
        if answer is None:
            answer = manual_coaching.render_answer(data, manual_coaching.rule_suggestions(data))
        source = "manual" if health_records.is_manual_sleep(record) else "wearable"
        context = {"engine": source + ("-openai" if kind == "openai" else "-rules"),
                   "model": provider.get("model") or (config.model if kind == "openai" else "규칙 기반"),
                   "requested_model": config.model, "prompt_version": manual_coaching.PROMPT_VERSION,
                   "expression": expression, "input_summary": data,
                   "premium_demo_live": {"request_id": row["request_id"], "kind": kind, "input_token_upper_bound": bound,
                                         "max_input_tokens": config.input_limit, "max_output_tokens": config.output_limit}}
        if "fallback_reason" in provider:
            context["fallback_reason"] = provider["fallback_reason"]
        coaching = coaching_service.save_generated(account_id, record, recent, lifestyle, answer, context, db_path,
                                                   coaching_id=row["coaching_id"])
        usage.finish(config.ledger, row, kind, context.get("fallback_reason"))
        return _result(config, account_id, row, coaching, replayed=False)
    except (premium_service.DemoUnavailable, usage.UsageUnavailable, usage.DemoCallLimit, CoachingLimitError):
        usage.interrupt(config.ledger, row)
        raise
    except ValueError:
        usage.interrupt(config.ledger, row)
        raise usage.DuplicateRequest("참고한 기록이나 설정이 달라졌어요. 현재 기록을 확인한 뒤 새 요청을 시작해 주세요.") from None
    except Exception:
        usage.interrupt(config.ledger, row)
        raise usage.UsageUnavailable("AI 요청 결과 확인이 필요해요. 같은 요청을 다시 확인해 주세요.") from None
