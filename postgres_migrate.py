"""Apply Daljam's PostgreSQL schema with python -m postgres_migrate.

The target is selected explicitly through DATABASE_URL. The API does not
import this module. SQL in the manifest must support transactional execution.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
from dataclasses import dataclass, field

import postgres_db

MIGRATIONS = Path(__file__).resolve().parent / "migrations" / "postgresql"
# A transaction-scoped advisory lock shared by Daljam migrators in this DB.
_LOCK_ID = 0x44616C6A616D
_HISTORY = "public.daljam_schema_migrations"


class MigrationError(RuntimeError):
    """A migration could not be verified or applied."""


class MigrationManifestError(MigrationError):
    """Migration files do not match the manifest."""


class MigrationHistoryError(MigrationError):
    """Stored migration history cannot be reconciled with the manifest."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sha256: str
    body: str = field(repr=False)


def _initial_body(text: str) -> str:
    # 0001 is also a standalone script with its own outer transaction.
    begin = re.match(r"\A(?:\s|--[^\n]*\n)*BEGIN\s*;", text, re.IGNORECASE)
    commit = re.search(r"(?im)^COMMIT[ \t]*;\s*\Z", text)
    if not begin or not commit or begin.end() >= commit.start():
        raise MigrationManifestError("0001의 BEGIN/COMMIT 경계를 확인하세요.")
    return text[begin.end():commit.start()]


def load_migrations(directory: Path = MIGRATIONS) -> tuple[Migration, ...]:
    """Read once, validate, and hash LF-normalized SQL before connecting."""
    try:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, RecursionError):
        raise MigrationManifestError("PostgreSQL 마이그레이션 manifest를 읽을 수 없습니다.") from None
    if (
        not isinstance(manifest, dict)
        or type(manifest.get("format_version")) is not int
        or manifest["format_version"] != 1
        or manifest.get("dialect") != "postgresql"
        or manifest.get("schema") != "public"
        or not isinstance(manifest.get("migrations"), list)
        or not manifest["migrations"]
    ):
        raise MigrationManifestError("PostgreSQL public 마이그레이션 manifest 형식이 올바르지 않습니다.")

    migrations = []
    for version, entry in enumerate(manifest["migrations"], 1):
        if not isinstance(entry, dict) or type(entry.get("version")) is not int or entry["version"] != version:
            raise MigrationManifestError(f"마이그레이션 버전은 1부터 순서대로 등록해야 합니다. 확인할 버전: {version}.")
        filename = entry.get("file")
        if (
            not isinstance(filename, str)
            or not re.fullmatch(rf"{version:04d}_[a-z][a-z0-9_]*\.sql", filename)
            or (version == 1 and filename != "0001_initial_schema.sql")
        ):
            raise MigrationManifestError(f"버전 {version}의 마이그레이션 파일 이름을 확인하세요.")
        expected = entry.get("sha256")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise MigrationManifestError(f"버전 {version}의 SHA-256 형식이 올바르지 않습니다.")
        try:
            text = (directory / filename).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            raise MigrationManifestError(f"버전 {version}의 SQL 파일을 읽을 수 없습니다.") from None
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != expected:
            raise MigrationManifestError(f"버전 {version}의 SQL 체크섬이 manifest와 다릅니다.")
        body = _initial_body(text) if version == 1 else text
        if not body.strip():
            raise MigrationManifestError(f"버전 {version}의 SQL이 비어 있습니다.")
        migrations.append(Migration(version, Path(filename).stem, expected, body))
    return tuple(migrations)


def _applied_versions(connection, migrations: tuple[Migration, ...]) -> tuple[int, ...]:
    from psycopg.errors import UndefinedColumn

    table = connection.execute(
        "SELECT c.relkind FROM pg_catalog.pg_class AS c "
        "JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relname = 'daljam_schema_migrations'"
    ).fetchone()
    if table is None:
        return ()
    if table["relkind"] != "r":
        raise MigrationHistoryError("마이그레이션 이력 객체가 테이블이 아닙니다.")
    try:
        rows = connection.execute(f"SELECT version, name, sha256 FROM {_HISTORY} ORDER BY version").fetchall()
    except UndefinedColumn:
        raise MigrationHistoryError(
            "마이그레이션 이력에 필수 열이 없습니다. 체크섬을 확인할 수 있는 이력이 필요합니다."
        ) from None
    if not rows:
        raise MigrationHistoryError("기존 마이그레이션 이력 테이블이 비어 있습니다.")
    if len(rows) > len(migrations):
        raise MigrationHistoryError("DB에 이 manifest보다 앞선 마이그레이션이 있습니다.")
    for row, migration in zip(rows, migrations):
        if (row["version"], row["name"]) != (migration.version, migration.name):
            raise MigrationHistoryError(f"버전 {migration.version}의 DB 이력 순서 또는 이름이 일치하지 않습니다.")
        if row["sha256"] != migration.sha256:
            raise MigrationHistoryError(f"버전 {migration.version}의 DB 이력 체크섬이 manifest와 다릅니다.")
    return tuple(migration.version for migration in migrations[:len(rows)])


def _apply_one(connection, migration: Migration) -> None:
    from psycopg import sql

    # SPI executes the SQL inside the surrounding transaction. A COMMIT in a
    # migration body cannot commit early, even inside a procedure or DO block.
    body = sql.SQL("BEGIN EXECUTE {}; END").format(sql.Literal(migration.body)).as_string(connection)
    connection.execute(sql.SQL("DO {}").format(sql.Literal(body)))
    if migration.version == 1:
        # Preserve the released 0001 bytes and extend its history in the same
        # transaction. An existing history without a hash is never backfilled.
        connection.execute(
            f"ALTER TABLE {_HISTORY} ADD COLUMN sha256 TEXT COLLATE \"C\" "
            "CHECK (sha256 ~ '^[0-9a-f]{64}$')"
        )
        row = connection.execute(
            f"UPDATE {_HISTORY} SET sha256 = %s WHERE version = %s AND name = %s",
            (migration.sha256, migration.version, migration.name),
        )
        if row.rowcount != 1:
            raise MigrationHistoryError("0001이 만든 마이그레이션 이력을 찾을 수 없습니다.")
        connection.execute(f"ALTER TABLE {_HISTORY} ALTER COLUMN sha256 SET NOT NULL")
    else:
        connection.execute(
            f"INSERT INTO {_HISTORY} (version, name, sha256) VALUES (%s, %s, %s)",
            (migration.version, migration.name, migration.sha256),
        )


def apply_migrations(directory: Path = MIGRATIONS, *, connect_timeout: int = 10) -> tuple[int, ...]:
    """Apply pending versions atomically and return the versions committed."""
    migrations = load_migrations(directory)
    connection = postgres_db.connect_postgres(connect_timeout=connect_timeout)
    from psycopg import Error, InterfaceError, OperationalError
    from psycopg.errors import LockNotAvailable

    version = None
    try:
        with connection:
            # A waiter must see the other runner's committed history after
            # acquiring the lock, even if the server defaults to RR.
            connection.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            connection.execute("SET LOCAL lock_timeout = '5s'")
            connection.execute("SET LOCAL statement_timeout = '60s'")
            connection.execute("SET LOCAL search_path = pg_catalog, public")
            connection.execute("SELECT pg_catalog.pg_advisory_xact_lock(%s)", (_LOCK_ID,))
            applied = _applied_versions(connection, migrations)
            pending = migrations[len(applied):]
            for migration in pending:
                version = migration.version
                _apply_one(connection, migration)
            if pending and len(_applied_versions(connection, migrations)) != len(migrations):
                raise MigrationHistoryError("적용한 마이그레이션의 DB 이력을 확인할 수 없습니다.")
        return tuple(migration.version for migration in pending)
    except LockNotAvailable:
        raise MigrationError("PostgreSQL 잠금 대기 시간이 초과됐습니다. 실행 중인 작업을 확인하세요.") from None
    except (Error, OSError) as error:
        # Raw driver errors can expose credentials, server names or SQL.
        state = getattr(error, "sqlstate", None)
        if (
            isinstance(error, (InterfaceError, OSError))
            or (isinstance(error, OperationalError) and state is None)
            or (state and (state.startswith("08") or state in {"57P01", "57P02", "57P03"}))
        ):
            raise postgres_db.PostgresConnectionError(
                "마이그레이션 중 PostgreSQL 연결이 끊겼습니다. 연결 복구 후 다시 실행해 적용 이력을 확인하세요."
            ) from None
        if version is None:
            raise MigrationError("PostgreSQL 마이그레이션 잠금 또는 이력을 확인하지 못했습니다.") from None
        raise MigrationError(f"PostgreSQL 마이그레이션 버전 {version} 적용에 실패했습니다.") from None


def main() -> int:
    try:
        applied = apply_migrations()
    except (
        MigrationError,
        postgres_db.PostgresConfigurationError,
        postgres_db.PostgresConnectionError,
        postgres_db.PostgresDriverUnavailable,
    ) as error:
        print(error, file=sys.stderr)
        return 1
    if applied:
        print("적용한 PostgreSQL 마이그레이션: " + ", ".join(map(str, applied)))
    else:
        print("적용할 PostgreSQL 마이그레이션이 없습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
