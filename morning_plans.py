"""Account-owned morning plans and bedtime estimates from recent records."""

from collections import Counter, defaultdict
from contextlib import closing
from datetime import date, datetime, time, timedelta, timezone
import json
from statistics import median
from typing import Annotated
from unicodedata import normalize
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, StrictBool, StringConstraints, model_validator

from app_database import begin_write
from coaching_patterns import _night_day, _sleep_minutes, _timestamp, _window_minutes
from health_records import connect, is_manual_sleep, list_sessions
from sleep_alarms import get_settings

_LOOKBACK = 14
_MIN_NIGHTS = 3
_MAX_ACTIVITIES = 12
_COMMON = ("가벼운 스트레칭", "물 한 잔 마시기", "가벼운 산책", "공부 또는 복습", "할 일 정리", "기상 후 샤워")
_ID = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]{1,64}$")]
_TITLE = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS morning_plans (
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    wake_date TEXT NOT NULL,
    timezone TEXT NOT NULL,
    activities TEXT NOT NULL,
    first_shown_at TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (account_id, wake_date)
);
"""


class Activity(BaseModel):
    model_config = {"extra": "forbid"}
    id: _ID
    title: _TITLE


def _key(title):
    return normalize("NFKC", " ".join(title.split())).casefold()


class PlanRequest(BaseModel):
    model_config = {"extra": "forbid"}
    activities: list[Activity] = Field(min_length=1, max_length=_MAX_ACTIVITIES)

    @model_validator(mode="after")
    def unique_activities(self):
        if (len({activity.id for activity in self.activities}) != len(self.activities)
                or len({_key(activity.title) for activity in self.activities}) != len(self.activities)):
            raise ValueError("같은 활동은 한 번만 넣을 수 있어요.")
        return self


class CompletionRequest(BaseModel):
    model_config = {"extra": "forbid"}
    id: _ID
    completed: StrictBool


def _db(db_path):
    db = connect(db_path)
    if not getattr(db, "is_postgres", False):
        try:
            db.execute(_SQLITE_SCHEMA)
        except Exception:
            db.close()
            raise
    return db


def _calendar(settings, now):
    zone = ZoneInfo(settings["timezone"])
    local_day = now.astimezone(zone).date()
    wake = _wake(local_day, settings, zone) if settings["saved"] else None
    next_day = local_day if wake is not None and now < wake else local_day + timedelta(days=1)
    return zone, local_day, next_day, wake


def _wake(day, settings, zone):
    # Use the first occurrence in a repeated hour. A skipped time advances by
    # the offset change when converted from the pre-transition wall time.
    return datetime.combine(day, time.fromisoformat(settings["wake_time"]), zone).astimezone(timezone.utc)


def _format_clock(minutes):
    hour, minute = divmod(round(minutes) % 1440, 60)
    return f"{hour:02d}:{minute:02d}"


def _local_clock(stamp, *, overnight=False):
    minutes = stamp.hour * 60 + stamp.minute + stamp.second / 60
    return minutes + 1440 if overnight and stamp.hour < 12 else minutes


def recommend_bedtime(account_id, now=None, db_path=None):
    now = now or datetime.now(timezone.utc)
    settings = get_settings(account_id, db_path)
    zone, today, next_day, _ = _calendar(settings, now)
    first = today - timedelta(days=_LOOKBACK - 1)
    days = defaultdict(set)
    for record in list_sessions(account_id, db_path):
        if is_manual_sleep(record):
            continue
        start, end = _timestamp(record.get("start")), _timestamp(record.get("end"))
        span = _window_minutes(start, end)
        if span is None or end > now:
            continue
        asleep = _sleep_minutes(record, span)
        if not asleep:
            continue
        local_start, local_end = start.astimezone(zone), end.astimezone(zone)
        night = _night_day(local_start)
        wake_date = night + timedelta(days=1) if night is not None else None
        if wake_date is not None and wake_date == local_end.date() and first <= wake_date <= today:
            days[wake_date].add((start.astimezone(timezone.utc), end.astimezone(timezone.utc), asleep, span))
    # Exact duplicates collapse. Several different records in one night cannot
    # determine one reliable window, so that night is excluded.
    candidates = sorted((day, *next(iter(rows))) for day, rows in days.items() if len(rows) == 1)
    overlapping = set()
    for index, (day, start, end, _, _) in enumerate(candidates):
        for other_day, other_start, other_end, _, _ in candidates[index + 1:]:
            if start < other_end and other_start < end:
                overlapping.update((day, other_day))
    valid = [row for row in candidates if row[0] not in overlapping]
    response = {"valid_nights": len(valid), "minimum_nights": _MIN_NIGHTS,
                "lookback_days": _LOOKBACK, "timezone": settings["timezone"]}
    if not settings["saved"]:
        return response | {"status": "no_goal"}
    if len(valid) < _MIN_NIGHTS:
        return response | {"status": "insufficient"}
    window = round(median(row[4] for row in valid))
    wake = _wake(next_day, settings, zone)
    estimate = (wake - timedelta(minutes=window)).astimezone(zone)
    return response | {
        "status": "available", "bedtime": estimate.strftime("%H:%M"),
        "bed_date": estimate.date().isoformat(), "wake_date": next_day.isoformat(),
        "wake_time": wake.astimezone(zone).strftime("%H:%M"),
        "window_minutes": window, "sleep_minutes": round(median(row[3] for row in valid)),
        "start_typical": _format_clock(median(_local_clock(row[1].astimezone(zone), overnight=True) for row in valid)),
        "end_typical": _format_clock(median(_local_clock(row[2].astimezone(zone)) for row in valid)),
    }


def _read(db, account, day):
    row = db.execute(
        "SELECT wake_date, timezone, activities FROM morning_plans WHERE account_id=? AND wake_date=?",
        (account, day.isoformat()),
    ).fetchone()
    if not row:
        return None
    activities = json.loads(row["activities"])
    return {"date": row["wake_date"], "timezone": row["timezone"], "activities": activities} if activities else None


def _suggestions(db, account, today):
    counts = Counter()
    titles = {}
    for row in db.execute("SELECT activities FROM morning_plans WHERE account_id=? AND wake_date BETWEEN ? AND ? ORDER BY wake_date DESC",
                          (account, (today - timedelta(days=_LOOKBACK - 1)).isoformat(), today.isoformat())):
        daily = {}
        for activity in json.loads(row["activities"]):
            title = activity["title"]
            daily[_key(title)] = title
        counts.update(daily.keys())
        for key, title in daily.items():
            titles.setdefault(key, title)
    frequent = sorted(counts, key=lambda key: (-counts[key], key))
    selected = [{"title": titles[key], "days": counts[key]} for key in frequent[:6]]
    selected.extend({"title": title, "days": 0} for title in _COMMON if _key(title) not in counts)
    return selected[:6]


def overview(account, now=None, db_path=None):
    now = now or datetime.now(timezone.utc)
    settings = get_settings(account, db_path)
    _, today, next_day, _ = _calendar(settings, now)
    with closing(_db(db_path)) as db:
        today_plan = _read(db, account, today)
        return {"today": today.isoformat(), "next_date": next_day.isoformat(), "timezone": settings["timezone"],
                "today_plan": today_plan, "next_plan": today_plan if next_day == today else _read(db, account, next_day),
                "suggestions": _suggestions(db, account, today)}


def save(account, day, request, now=None, db_path=None):
    now = now or datetime.now(timezone.utc)
    settings = get_settings(account, db_path)
    _, today, next_day, _ = _calendar(settings, now)
    if day not in (today, next_day):
        raise ValueError("날짜가 바뀌었어요. 계획을 다시 불러와 주세요.")
    with closing(_db(db_path)) as db, db:
        begin_write(db)
        old = _read(db, account, day)
        completed = {item["id"]: item["completed"] for item in old["activities"]} if old else {}
        activities = [item.model_dump() | {"completed": completed.get(item.id, False)} for item in request.activities]
        db.execute("""INSERT INTO morning_plans(account_id,wake_date,timezone,activities,updated_at) VALUES(?,?,?,?,?)
                      ON CONFLICT(account_id,wake_date) DO UPDATE SET
                      timezone=excluded.timezone,activities=excluded.activities,updated_at=excluded.updated_at""",
                   (account, day.isoformat(), settings["timezone"], json.dumps(activities, ensure_ascii=False), now.isoformat()))
        return _read(db, account, day)


def mark(account, day, request, db_path=None):
    with closing(_db(db_path)) as db, db:
        begin_write(db)
        plan = _read(db, account, day)
        if plan:
            for activity in plan["activities"]:
                if activity["id"] == request.id:
                    activity["completed"] = request.completed
                    db.execute("UPDATE morning_plans SET activities=?,updated_at=? WHERE account_id=? AND wake_date=?",
                               (json.dumps(plan["activities"], ensure_ascii=False), datetime.now(timezone.utc).isoformat(),
                                account, day.isoformat()))
                    return plan
        raise LookupError("저장된 활동을 찾지 못했어요. 계획을 다시 불러와 주세요.")


def remove(account, day, db_path=None):
    with closing(_db(db_path)) as db, db:
        begin_write(db)
        # Keep only the daily marker if the automatic sheet already opened.
        cleared = db.execute("""UPDATE morning_plans SET activities='[]',updated_at=?
                               WHERE account_id=? AND wake_date=? AND first_shown_at IS NOT NULL AND activities<>'[]'""",
                            (datetime.now(timezone.utc).isoformat(), account, day.isoformat())).rowcount
        deleted = db.execute("DELETE FROM morning_plans WHERE account_id=? AND wake_date=? AND first_shown_at IS NULL",
                             (account, day.isoformat())).rowcount
        return bool(cleared or deleted)


def claim_morning_view(account, now=None, db_path=None):
    now = now or datetime.now(timezone.utc)
    settings = get_settings(account, db_path)
    _, today, _, wake = _calendar(settings, now)
    if wake is None or now < wake:
        return None
    with closing(_db(db_path)) as db, db:
        begin_write(db)
        claimed = db.execute("""UPDATE morning_plans SET first_shown_at=?
                            WHERE account_id=? AND wake_date=? AND first_shown_at IS NULL AND activities<>'[]'""",
                             (now.isoformat(), account, today.isoformat())).rowcount
        return _read(db, account, today) if claimed else None
