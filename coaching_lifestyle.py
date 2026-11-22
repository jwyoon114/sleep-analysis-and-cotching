"""Account settings and optional habits for the selected night's local date."""

from contextlib import closing
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, StringConstraints

from coaching_patterns import _record_day, _timestamp
from health_records import connect

Clock = Annotated[str, StringConstraints(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")]


class Preferences(BaseModel):
    model_config = {"extra": "forbid"}

    age_group: Literal["성인", "미성년자"] | None = None
    usual_bedtime: Clock | None = None
    usual_wake_time: Clock | None = None


class DailyHabits(BaseModel):
    model_config = {"extra": "forbid"}

    caffeine: Literal["없음", "있음"] | None = None
    satisfaction: Literal["좋음", "보통", "나쁨"] | None = None


def _prepare(db):
    if not getattr(db, "is_postgres", False):
        db.execute("""CREATE TABLE IF NOT EXISTS coaching_preferences (
            account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
            age_group TEXT, usual_bedtime TEXT, usual_wake_time TEXT)""")
        db.execute("""CREATE TABLE IF NOT EXISTS coaching_daily_habits (
            account_id TEXT REFERENCES accounts(id) ON DELETE CASCADE,
            sleep_day TEXT NOT NULL, caffeine TEXT, satisfaction TEXT,
            PRIMARY KEY (account_id, sleep_day))""")


def _save(db, table, identity, settings):
    changes = settings.model_dump(exclude_unset=True)
    if not changes:
        return
    values = identity | changes
    placeholders = ",".join("?" for _ in values)
    updates = ", ".join(f"{key}=excluded.{key}" for key in changes)
    db.execute(f"INSERT INTO {table} ({','.join(values)}) VALUES ({placeholders}) "
               f"ON CONFLICT ({','.join(identity)}) DO UPDATE SET {updates}", tuple(values.values()))


def preferences(account_id, settings=None, db_path=None):
    with closing(connect(db_path)) as db, db:
        _prepare(db)
        if settings is not None:
            _save(db, "coaching_preferences", {"account_id": account_id}, settings)
        row = db.execute("""SELECT age_group, usual_bedtime, usual_wake_time
            FROM coaching_preferences WHERE account_id=?""", (account_id,)).fetchone()
        return dict(row) if row else Preferences().model_dump()


def daily_habits(account_id, record, settings=None, db_path=None):
    start = _timestamp(record["start"])
    day = _record_day(record, start.astimezone(ZoneInfo(record["timezone"])) if start else None)
    if day is None:
        raise ValueError("수면 기록 날짜를 확인해 주세요.")
    day = day.isoformat()
    with closing(connect(db_path)) as db, db:
        _prepare(db)
        if settings is not None:
            _save(db, "coaching_daily_habits", {"account_id": account_id, "sleep_day": day}, settings)
        row = db.execute("""SELECT caffeine, satisfaction FROM coaching_daily_habits
            WHERE account_id=? AND sleep_day=?""", (account_id, day)).fetchone()
        return {"day": day, "habits": dict(row) if row else DailyHabits().model_dump()}
