"""Account-scoped preferences. A row exists only after onboarding completes."""

from contextlib import closing
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, StrictBool

from app_database import uses_postgres
from health_records import connect


class Preferences(BaseModel):
    model_config = {"extra": "forbid"}

    mbti: Literal[
        "ISTJ", "ISFJ", "INFJ", "INTJ", "ISTP", "ISFP", "INFP", "INTP",
        "ESTP", "ESFP", "ENFP", "ENTP", "ESTJ", "ESFJ", "ENFJ", "ENTJ",
    ] | None
    speech: Literal["polite", "casual"]
    intensity: Literal["gentle", "firm", "direct"]
    allow_profanity: StrictBool = False
    character: Literal["cat", "raccoon", "dog", "rabbit"]

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS account_personalization (
    account_id TEXT PRIMARY KEY NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    mbti TEXT CHECK (mbti IN ('ISTJ','ISFJ','INFJ','INTJ','ISTP','ISFP','INFP','INTP','ESTP','ESFP','ENFP','ENTP','ESTJ','ESFJ','ENFJ','ENTJ')),
    speech TEXT NOT NULL CHECK (speech IN ('polite','casual')),
    intensity TEXT NOT NULL CHECK (intensity IN ('gentle','firm','direct')),
    allow_profanity BOOLEAN NOT NULL CHECK (allow_profanity IN (FALSE, TRUE)),
    character TEXT NOT NULL CHECK (character IN ('cat','raccoon','dog','rabbit')),
    completed_at TEXT NOT NULL
);
"""
_COLUMNS = "mbti, speech, intensity, allow_profanity, character, completed_at"


def _prepare_local(db, db_path):
    # The desktop SQLite backend upgrades on demand. PostgreSQL only uses its migration.
    if not uses_postgres(db_path):
        db.execute(_SQLITE_SCHEMA)
        # Upgrade only the old coupling constraint, inside one write transaction.
        # All columns/values and the account FK survive; never modify old advice.
        def coupled():
            row = db.execute("SELECT sql FROM sqlite_master WHERE name='account_personalization'").fetchone()
            return row and "NOT allow_profanity OR intensity" in row[0]
        if coupled():
            if not db.in_transaction:
                db.execute("BEGIN IMMEDIATE")
            if coupled():
                temporary = "account_personalization_consent_upgrade"
                db.execute(_SQLITE_SCHEMA.replace("account_personalization", temporary))
                columns = "account_id, " + _COLUMNS
                db.execute(f"INSERT INTO {temporary} ({columns}) SELECT {columns} FROM account_personalization")
                db.execute("DROP TABLE account_personalization")
                db.execute(f"ALTER TABLE {temporary} RENAME TO account_personalization")


def _get(db, account_id):
    row = db.execute(
        f"SELECT {_COLUMNS} FROM account_personalization WHERE account_id=?", (account_id,)
    ).fetchone()
    if not row:
        return None
    return {**dict(row), "allow_profanity": bool(row["allow_profanity"])}


def get_personalization(account_id, db_path=None):
    with closing(connect(db_path)) as db, db:
        _prepare_local(db, db_path)
        return _get(db, account_id)


def save_personalization(account_id, preferences, *, complete=False, db_path=None):
    values = (preferences.mbti, preferences.speech, preferences.intensity,
              preferences.allow_profanity, preferences.character)
    with closing(connect(db_path)) as db, db:
        _prepare_local(db, db_path)
        if complete:
            # Retrying onboarding, including from another tab, keeps the first stored choices.
            db.execute(
                f"INSERT INTO account_personalization(account_id, {_COLUMNS}) VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(account_id) DO NOTHING",
                (account_id, *values, datetime.now(timezone.utc).isoformat()),
            )
        else:
            db.execute(
                "UPDATE account_personalization SET mbti=?, speech=?, intensity=?, allow_profanity=?, character=? "
                "WHERE account_id=?",
                (*values, account_id),
            )
        return _get(db, account_id)
