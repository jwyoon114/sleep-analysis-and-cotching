"""Opt-in, session-bound Web Push rehearsal. No scheduled sender runs in this version."""

import base64
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from app_database import uses_postgres
from health_records import connect
from production_policy import is_production
from sleep_accounts import digest


class PushError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class Keys(BaseModel):
    model_config = {"extra": "forbid"}
    p256dh: str = Field(min_length=87, max_length=88)
    auth: str = Field(min_length=22, max_length=24)


class Subscription(BaseModel):
    model_config = {"extra": "forbid"}
    endpoint: str = Field(min_length=1, max_length=2048)
    keys: Keys
    expirationTime: int | None = Field(default=None, ge=0, le=253402300799000, strict=True)


class TestRequest(BaseModel):
    model_config = {"extra": "forbid"}
    id: str = Field(pattern=r"^[a-f0-9]{64}$")


@dataclass(frozen=True, repr=False)
class Configuration:
    private_key: str
    public_key: str
    subject: str


def decode_key(value, length):
    if not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", value):
        raise ValueError
    raw = base64.urlsafe_b64decode(value.rstrip("=") + "=" * (-len(value.rstrip("=")) % 4))
    if len(raw) != length or base64.urlsafe_b64encode(raw).decode().rstrip("=") != value.rstrip("="):
        raise ValueError
    return raw


def configuration():
    if is_production() or os.getenv("DALJAM_WEB_PUSH_TEST") != "1" or not uses_postgres():
        return None
    key = os.getenv("DALJAM_VAPID_PRIVATE_KEY", "")
    subject = os.getenv("DALJAM_VAPID_SUBJECT", "")
    if not re.fullmatch(r"mailto:[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", subject):
        return None
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        private = ec.derive_private_key(int.from_bytes(decode_key(key, 32), "big"), ec.SECP256R1())
        public = private.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    except (ImportError, ValueError):
        return None
    return Configuration(key.rstrip("="), base64.urlsafe_b64encode(public).decode().rstrip("="), subject)


def require_configuration():
    config = configuration()
    if config is None:
        raise PushError(503, "이 환경에서는 Web Push 검증을 사용할 수 없어요.")
    return config


def validate_endpoint(endpoint):
    """Only recognized push service origins and paths may receive outbound requests."""
    if not re.fullmatch(r"https://[a-z0-9.-]+/[A-Za-z0-9_./~=+:%-]+", endpoint):
        raise ValueError
    url = urlsplit(endpoint)
    if url.netloc == "fcm.googleapis.com" and re.fullmatch(r"/fcm/send/[A-Za-z0-9_:-]+", url.path):
        return
    if url.netloc == "updates.push.services.mozilla.com" and re.fullmatch(r"/(?:w?push)/v[12]/[A-Za-z0-9_-]+", url.path):
        return
    if re.fullmatch(r"(?:[a-z0-9-]+\.)+push\.apple\.com", url.netloc) and re.fullmatch(r"/[A-Za-z0-9_~=-]+", url.path):
        return
    raise ValueError


def _now():
    return datetime.now(timezone.utc)


def status(account_id, token):
    config = configuration()
    if config is None:
        return {"enabled": False, "public_key": None, "devices": []}
    now = _now()
    with closing(connect()) as db:
        rows = db.execute(
            "SELECT s.endpoint_id, s.token_hash, s.registered_at FROM web_push_subscriptions s "
            "JOIN auth_tokens t ON t.token_hash=s.token_hash WHERE t.account_id=? AND t.expires_at>? "
            "AND (s.expires_at IS NULL OR s.expires_at>?) ORDER BY s.registered_at DESC",
            (account_id, now.isoformat(), now),
        ).fetchall()
    return {"enabled": True, "public_key": config.public_key, "devices": [
        {"id": row["endpoint_id"], "this_session": row["token_hash"] == digest(token),
         "registered_at": row["registered_at"]} for row in rows
    ]}


def subscribe(account_id, token, value):
    require_configuration()
    now = _now()
    expires = datetime.fromtimestamp(value.expirationTime / 1000, timezone.utc) if value.expirationTime is not None else None
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        validate_endpoint(value.endpoint)
        decode_key(value.keys.auth, 16)
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), decode_key(value.keys.p256dh, 65))
        if expires is not None and expires <= now:
            raise ValueError
    except (ValueError, OverflowError):
        raise PushError(400, "브라우저 구독이 올바르지 않거나 만료됐어요.") from None
    endpoint_id = hashlib.sha256(value.endpoint.encode()).hexdigest()
    token_hash = digest(token)
    with closing(connect()) as db, db:
        active = db.execute("SELECT 1 FROM auth_tokens WHERE token_hash=? AND account_id=? AND expires_at>?",
                            (token_hash, account_id, now.isoformat())).fetchone()
        if active is None:
            raise PushError(401, "다시 로그인해 주세요.")
        db.execute(
            "DELETE FROM web_push_subscriptions WHERE token_hash IN (SELECT token_hash FROM auth_tokens WHERE expires_at<=?) "
            "OR expires_at<=?", (now.isoformat(), now),
        )
        owner = db.execute(
            "SELECT t.account_id FROM web_push_subscriptions s JOIN auth_tokens t ON t.token_hash=s.token_hash "
            "WHERE s.endpoint_id=?", (endpoint_id,),
        ).fetchone()
        if owner is not None and owner["account_id"] != account_id:
            raise PushError(409, "이 브라우저는 다른 계정에 연결되어 있어요. 그 계정에서 먼저 해제해 주세요.")
        if owner is None:
            count = db.execute(
                "SELECT count(*) FROM web_push_subscriptions s JOIN auth_tokens t ON t.token_hash=s.token_hash WHERE t.account_id=?",
                (account_id,),
            ).fetchone()[0]
            if count >= 8:
                raise PushError(409, "등록된 기기가 8개예요. 다른 기기를 해제한 후 다시 시도해 주세요.")
        db.execute(
            "INSERT INTO web_push_subscriptions (endpoint_id,token_hash,endpoint,p256dh,auth_secret,expires_at,registered_at) "
            "VALUES (?,?,?,?,?,?,?) ON CONFLICT(endpoint_id) DO UPDATE SET token_hash=excluded.token_hash, "
            "p256dh=excluded.p256dh, auth_secret=excluded.auth_secret, expires_at=excluded.expires_at",
            (endpoint_id, token_hash, value.endpoint, value.keys.p256dh, value.keys.auth, expires, now),
        )
    return {"id": endpoint_id}


def unsubscribe(account_id, endpoint_id):
    if uses_postgres():
        with closing(connect()) as db, db:
            db.execute(
                "DELETE FROM web_push_subscriptions WHERE endpoint_id=? "
                "AND token_hash IN (SELECT token_hash FROM auth_tokens WHERE account_id=?)",
                (endpoint_id, account_id),
            )
    return {"status": "removed"}


def _send(subscription, config):
    from pywebpush import WebPushException, webpush
    from requests import RequestException, Session

    class PushSession(Session):
        def post(self, url, *args, **kwargs):
            validate_endpoint(url)
            kwargs["allow_redirects"] = False
            return super().post(url, *args, **kwargs)

    with PushSession() as session:
        session.trust_env = False
        try:
            response = webpush(
                {"endpoint": subscription["endpoint"], "keys": {
                    "p256dh": subscription["p256dh"], "auth": subscription["auth_secret"]}},
                data=json.dumps({"kind": "bedtime-test"}), vapid_private_key=config.private_key,
                vapid_claims={"sub": config.subject}, ttl=60, timeout=5, requests_session=session,
            )
            return response.status_code
        except WebPushException as error:
            return error.response.status_code if error.response is not None else None
        except (RequestException, ValueError):
            return None


def send_test(account_id, token, endpoint_id):
    config = require_configuration()
    now = _now()
    token_hash = digest(token)
    cutoff = now - timedelta(minutes=1)
    with closing(connect()) as db, db:
        subscription = db.execute(
            "SELECT s.endpoint, s.p256dh, s.auth_secret, s.expires_at FROM web_push_subscriptions s "
            "JOIN auth_tokens t ON t.token_hash=s.token_hash "
            "WHERE s.endpoint_id=? AND s.token_hash=? AND t.account_id=? AND t.expires_at>?",
            (endpoint_id, token_hash, account_id, now.isoformat()),
        ).fetchone()
        if subscription is None:
            raise PushError(404, "이 기기를 먼저 등록해 주세요.")
        expired = subscription["expires_at"] is not None and subscription["expires_at"] <= now
        if expired:
            db.execute("DELETE FROM web_push_subscriptions WHERE endpoint_id=? AND token_hash=?", (endpoint_id, token_hash))
        else:
            previous = db.execute("SELECT attempted_at FROM web_push_test_limits WHERE account_id=?", (account_id,)).fetchone()
            total = db.execute("SELECT count(*) FROM web_push_test_limits WHERE attempted_at>?", (cutoff,)).fetchone()[0]
            if (previous and previous["attempted_at"] > cutoff) or total >= 20:
                raise PushError(429, "잠시 후 테스트 알림을 다시 요청해 주세요.")
            db.execute(
                "INSERT INTO web_push_test_limits VALUES (?,?) ON CONFLICT(account_id) "
                "DO UPDATE SET attempted_at=excluded.attempted_at", (account_id, now),
            )
    if expired:
        raise PushError(410, "구독이 만료됐어요. 이 기기를 다시 등록해 주세요.")
    # The global DB transaction lock is released before external I/O.
    result = _send(subscription, config)
    if result in (404, 410):
        with closing(connect()) as db, db:
            db.execute(
                "DELETE FROM web_push_subscriptions WHERE endpoint_id=? AND token_hash=? "
                "AND p256dh=? AND auth_secret=?",
                (endpoint_id, token_hash, subscription["p256dh"], subscription["auth_secret"]),
            )
        raise PushError(410, "구독이 만료됐어요. 이 기기를 다시 등록해 주세요.")
    if result is None or not 200 <= result < 300:
        raise PushError(502, "푸시 서비스가 알림을 접수하지 못했어요.")
    return {"status": "accepted"}
