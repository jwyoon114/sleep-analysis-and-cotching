"""Non-billing presentation grants. Never confer a paid AI entitlement."""

from dataclasses import dataclass
from datetime import datetime, timezone
import os
import secrets
from threading import Lock
import time

from account_personalization import get_personalization
from coaching_expression import expression_snapshot


class DemoUnavailable(PermissionError):
    pass


class InvalidCheckout(ValueError):
    pass


@dataclass
class DemoGrant:
    token: str
    checkout_until: float
    active_until: float = 0


# Deliberately ephemeral and separate from account, payment and health-data tables.
# A server restart clears presentation grants. This is not a subscription ledger.
_grants: dict[str, DemoGrant] = {}
_lock = Lock()
CHECKOUT_SECONDS = 10 * 60
DEMO_SECONDS = 24 * 60 * 60


def demo_available():
    return (os.getenv("DALJAM_PREMIUM_DEMO") == "1"
            and os.getenv("DALJAM_ENV") in {"development", "test", "staging"})


def has_paid_ai_entitlement(account_id):
    """Future billing integration must verify a real paid grant here, server-side.

    A demo grant, request parameter or environment engine switch never qualifies.
    There is currently no real billing or paid entitlement issuer.
    """
    return False


def _require_demo():
    if not demo_available():
        raise DemoUnavailable("이 환경에서는 모의 결제 시연을 사용할 수 없어요.")


def _prune(now):
    for account_id, grant in list(_grants.items()):
        if max(grant.checkout_until, grant.active_until) <= now:
            del _grants[account_id]


def _status(account_id, now):
    grant = _grants.get(account_id)
    active = bool(demo_available() and grant and grant.active_until > now)
    return {
        "tier": "premium_demo" if active else "free", "demo_available": demo_available(),
        "paid_entitlement": False, "live_ai_available": False,
        "demo_expires_at": datetime.fromtimestamp(grant.active_until, timezone.utc).isoformat() if active else None,
    }


def status(account_id):
    with _lock:
        now = time.time()
        _prune(now)
        return _status(account_id, now)


def start_checkout(account_id):
    _require_demo()
    with _lock:
        now = time.time()
        _prune(now)
        if _status(account_id, now)["tier"] == "premium_demo":
            raise InvalidCheckout("이미 프리미엄 시연이 활성화되어 있어요. 상태를 다시 확인해 주세요.")
        grant = DemoGrant(secrets.token_urlsafe(32), now + CHECKOUT_SECONDS)
        _grants[account_id] = grant
        return {"checkout_token": grant.token, "mode": "simulation", "payment_required": False}


def activate_demo(account_id, checkout_token):
    _require_demo()
    with _lock:
        now = time.time()
        _prune(now)
        grant = _grants.get(account_id)
        if (grant is None or not secrets.compare_digest(grant.token, checkout_token)
                or grant.checkout_until <= now):
            raise InvalidCheckout("결제 시연 확인이 만료되었어요. 소개 화면에서 다시 시작해 주세요.")
        if grant.active_until <= now:
            grant.active_until = now + DEMO_SECONDS
        return _status(account_id, now)


def clear_demo(account_id):
    """Also used on successful logout or account deletion, independent of feature flags."""
    with _lock:
        _grants.pop(account_id, None)


def reset_demo(account_id):
    _require_demo()
    clear_demo(account_id)
    return status(account_id)


SAMPLE_ACTIONS = {
    ("polite", "gentle"): "가상 기록의 취침 시각을 보며 무리 없이 반복할 수 있는 시간을 골라 보세요. 작은 준비 습관부터 이어가도 좋아요.",
    ("polite", "firm"): "가상 기록에서 달라진 취침 시각을 확인하세요. 반복할 시간을 정하고 잠자리에 들 준비를 미리 해 보세요.",
    ("polite", "direct"): "반복할 취침 시각을 정하세요. 준비를 미루지 말고 다음 기록에서 계획과 입력 시각을 확인하세요.",
    ("casual", "gentle"): "가상 기록의 취침 시각을 보며 무리 없이 반복할 수 있는 시간을 골라 봐. 작은 준비 습관부터 이어가도 좋아.",
    ("casual", "firm"): "가상 기록에서 달라진 취침 시각을 확인해. 반복할 시간을 정하고 잠자리에 들 준비를 미리 해 봐.",
    ("casual", "direct"): "반복할 취침 시각을 정해. 준비를 미루지 말고 다음 기록에서 계획과 입력 시각을 확인해.",
}


def sample_preview(account_id, db_path=None):
    _require_demo()
    if status(account_id)["tier"] != "premium_demo":
        raise DemoUnavailable("먼저 모의 결제를 완료해 프리미엄 시연을 활성화해 주세요.")
    expression = expression_snapshot(get_personalization(account_id, db_path))
    casual = expression["speech"] == "casual"
    observation = ("가상 기록의 취침 시각이 날마다 달라. 추정 수면 시간은 입력한 시각의 차이야." if casual
                   else "가상 기록의 취침 시각이 날마다 달라요. 추정 수면 시간은 입력한 시각의 차이예요.")
    return {
        "title": "AI 코칭 시연 예시 — 샘플 데이터", "source": "prepared_sample", "synthetic": True,
        "model_called": False, "saved_to_history": False, "expression": expression,
        "sample_records": [
            {"label": "가상 기록 A", "bedtime": "23:40", "wake_time": "07:00", "estimated_sleep_minutes": 440},
            {"label": "가상 기록 B", "bedtime": "00:10", "wake_time": "07:10", "estimated_sleep_minutes": 420},
            {"label": "가상 기록 C", "bedtime": "23:30", "wake_time": "07:00", "estimated_sleep_minutes": 450},
        ],
        "coaching": observation + "\n\n" + SAMPLE_ACTIONS[expression["speech"], expression["intensity"]],
        "notice": "준비된 가상 기록과 샘플 조언이에요. 현재 계정의 말투·강도만 적용하며 실제 수면 기록이나 코칭 이력에 저장하지 않아요.",
    }
