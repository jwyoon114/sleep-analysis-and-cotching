"""One-shot bedtime dispatch. The caller supplies the cadence, and the DB owns claims."""

from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import hmac
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from health_records import connect
import web_push


LEAD = timedelta(minutes=30)
GRACE = timedelta(minutes=10)
RETRY_DELAY = timedelta(minutes=2)
BATCH_LIMIT = 8
UTC = timezone.utc

DEVICES = """
    SELECT s.account_id, s.endpoint_id, s.device_hash, s.endpoint, s.p256dh,
           s.auth_secret, a.bedtime, a.timezone
    FROM web_push_subscriptions s JOIN sleep_alarm_settings a ON a.account_id=s.account_id
    WHERE s.reminders_enabled AND s.device_hash IS NOT NULL
      AND (s.expires_at IS NULL OR s.expires_at>?)
"""


def reminder_time(bedtime_date, bedtime, timezone_name):
    """Resolve the wall clock first and subtract 30 elapsed minutes in UTC."""
    zone = ZoneInfo(timezone_name)
    wall = datetime.combine(bedtime_date, time.fromisoformat(bedtime))
    # fold=0 selects the first occurrence. Gaps advance to the next valid minute.
    for _ in range(1441):
        instant = wall.replace(tzinfo=zone, fold=0).astimezone(UTC)
        if instant.astimezone(zone).replace(tzinfo=None) == wall:
            return instant - LEAD
        wall += timedelta(minutes=1)
    raise ValueError("A valid local bedtime could not be resolved.")


def due_now(row, now):
    try:
        local_date = now.astimezone(ZoneInfo(row["timezone"])).date()
        for offset in (0, 1, -1):
            bedtime_date = local_date + timedelta(days=offset)
            due = reminder_time(bedtime_date, row["bedtime"], row["timezone"])
            if due <= now < due + GRACE:
                return bedtime_date, due
    except (ValueError, ZoneInfoNotFoundError):
        return None
    return None


@dataclass(frozen=True, repr=False)
class Claim:
    account_id: str
    device_hash: str
    bedtime_date: date
    due: datetime
    endpoint_id: str
    attempt: int

    @property
    def key(self):
        return self.account_id, self.device_hash, self.bedtime_date


def _claim(endpoint_id, now):
    # The existing application adapter serializes these short DB transactions.
    with closing(connect()) as db, db:
        device = db.execute(DEVICES + " AND s.endpoint_id=?", (now, endpoint_id)).fetchone()
        window = due_now(device, now) if device else None
        if window is None:
            return None
        date, due = window
        account, installation = device["account_id"], device["device_hash"]
        matching = db.execute(
            "SELECT device_hash, attempts, state, next_attempt, due_at FROM web_push_deliveries "
            "WHERE account_id=? AND bedtime_date=? AND (device_hash=? OR endpoint_id=?)",
            (account, date, installation, endpoint_id),
        ).fetchall()
        if not matching:
            db.execute(
                "INSERT INTO web_push_deliveries (account_id,device_hash,endpoint_id,bedtime_date,due_at,updated_at,attempts,state) "
                "VALUES (?,?,?,?,?,?,1,'sending')", (account, installation, endpoint_id, date, due, now),
            )
            return Claim(account, installation, date, due, endpoint_id, 1)
        if len(matching) != 1:
            return None
        previous = matching[0]
        attempt = previous["attempts"]
        if previous["state"] == "retry" and attempt < 2:
            if previous["due_at"] == due and previous["next_attempt"] > now:
                return None
            attempt += 1
        elif previous["state"] != "cancelled":
            return None
        db.execute(
            "UPDATE web_push_deliveries SET endpoint_id=?, due_at=?, updated_at=?, attempts=?, state='sending', next_attempt=NULL "
            "WHERE account_id=? AND device_hash=? AND bedtime_date=?",
            (endpoint_id, due, now, attempt, account, previous["device_hash"], date),
        )
        return Claim(account, previous["device_hash"], date, due, endpoint_id, attempt)


def _finish(claim, now, state, retry_at=None, expired_subscription=None):
    with closing(connect()) as db, db:
        db.execute(
            "UPDATE web_push_deliveries SET updated_at=?, state=?, next_attempt=? "
            "WHERE account_id=? AND device_hash=? AND bedtime_date=? AND attempts=? AND state='sending'",
            (now, state, retry_at, *claim.key, claim.attempt),
        )
        if expired_subscription is not None:
            web_push.remove_provider_subscription(db, claim.account_id, claim.endpoint_id, expired_subscription)


def _dispatch(claim, config, clock):
    now = clock()
    with closing(connect()) as db:
        subscription = db.execute(DEVICES + " AND s.endpoint_id=? AND s.account_id=?",
                                  (now, claim.endpoint_id, claim.account_id)).fetchone()
    # A goal change or opt-out before this check cancels the selected delivery.
    if subscription is None or due_now(subscription, now) != (claim.bedtime_date, claim.due):
        _finish(claim, now, "cancelled")
        return "cancelled"
    ttl = min(60, int((claim.due + GRACE - now).total_seconds()))
    if ttl <= 0:
        _finish(claim, now, "cancelled")
        return "cancelled"
    result = web_push._send(subscription, config, kind="bedtime-reminder", ttl=ttl)
    finished = clock()
    retry_at = finished + RETRY_DELAY
    if result is not None and 200 <= result < 300:
        state = "sent"
    elif result == 429 and claim.attempt < 2 and retry_at < claim.due + GRACE:
        _finish(claim, finished, "retry", retry_at)
        return "retry"
    elif result is None:
        state = "uncertain"
    else:
        state = "failed"
    _finish(claim, finished, state, expired_subscription=subscription if result in (404, 410) else None)
    return state


def run(config, *, clock=web_push._now):
    now = clock()
    with closing(connect()) as db, db:
        db.execute("DELETE FROM web_push_subscriptions WHERE expires_at<=?", (now,))
        db.execute("DELETE FROM web_push_deliveries WHERE updated_at<?", (now - timedelta(days=14),))
        db.execute(
            "UPDATE web_push_deliveries SET state='uncertain', updated_at=? WHERE state='sending' AND updated_at<?",
            (now, now - timedelta(minutes=1)),
        )
        devices = db.execute(DEVICES + " ORDER BY s.endpoint_id", (now,)).fetchall()
    selected = [row["endpoint_id"] for row in devices if due_now(row, now)]
    totals = {"due": len(selected), "claimed": 0, "sent": 0, "retry": 0, "failed": 0, "uncertain": 0, "cancelled": 0}
    for endpoint_id in selected:
        claim = _claim(endpoint_id, clock())
        if claim:
            totals[_dispatch(claim, config, clock)] += 1
            totals["claimed"] += 1
            if totals["claimed"] == BATCH_LIMIT:
                break
    return totals


def run_authorized(credentials):
    secret = web_push.job_secret()
    if not web_push.scheduled_enabled():
        raise web_push.PushError(404, "예약 발송이 비활성화되어 있어요.")
    if credentials is None or not hmac.compare_digest(credentials.encode(), secret.encode()):
        raise web_push.PushError(403, "작업 인증을 확인해 주세요.")
    return run(web_push.require_configuration())
