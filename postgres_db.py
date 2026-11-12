"""Opt-in PostgreSQL connections; existing SQLite services do not import this module.

No connection, SQL, schema creation, retries, or DB selection happens on import.
Install requirements-postgres.txt before explicitly calling connect_postgres().
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib import import_module
import os
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from psycopg import Connection


class PostgresConfigurationError(ValueError):
    """Invalid or incomplete explicit PostgreSQL configuration."""


class PostgresDriverUnavailable(RuntimeError):
    """The optional PostgreSQL driver is not installed or cannot load."""


class PostgresConnectionError(ConnectionError):
    """A connection failed; the underlying message is intentionally hidden."""


@dataclass(frozen=True)
class PostgresSettings:
    # Never expose usernames, passwords, hosts, or database names in repr().
    _parameters: Mapping[str, str] = field(repr=False)
    connect_timeout: int
    sslmode: str


def _driver_modules():
    try:
        driver = import_module("psycopg")
        parser = import_module("psycopg.conninfo").conninfo_to_dict
        row_factory = import_module("psycopg.rows").dict_row
    except ImportError:
        raise PostgresDriverUnavailable(
            "PostgreSQL 드라이버를 불러올 수 없습니다. requirements-postgres.txt를 설치하세요."
        ) from None
    return driver, parser, row_factory


def load_postgres_settings(*, connect_timeout: int = 10) -> PostgresSettings:
    """Validate DATABASE_URL without opening any network connection.

    Explicit host, user, database and a single TCP endpoint are required.
    TLS is required. PGHOST/PGDATABASE defaults and libpq services must not
    silently select a different database. The application controls the timeout.
    """
    if type(connect_timeout) is not int or not 1 <= connect_timeout <= 60:
        raise PostgresConfigurationError(
            "connect_timeout은 1~60초 사이의 정수여야 합니다."
        )
    value = os.getenv("DATABASE_URL")
    if not value or not value.strip():
        raise PostgresConfigurationError(
            "DATABASE_URL이 설정되지 않았습니다. 다른 DB로 자동 전환하지 않습니다."
        )
    dsn = value.strip()
    if not dsn.startswith(("postgresql://", "postgres://")) or "\x00" in dsn:
        raise PostgresConfigurationError(
            "DATABASE_URL에는 명시적인 PostgreSQL URL이 필요합니다."
        )

    if os.getenv("PGSERVICE") or os.getenv("PGHOSTADDR"):
        raise PostgresConfigurationError(
            "PGSERVICE 또는 PGHOSTADDR의 암묵적 대상 설정을 제거하고 DATABASE_URL을 사용하세요."
        )

    driver, parser, _ = _driver_modules()
    try:
        parameters = parser(dsn)
    except (driver.Error, ValueError, UnicodeError):
        raise PostgresConfigurationError(
            "DATABASE_URL의 PostgreSQL 연결 형식이 올바르지 않습니다."
        ) from None

    if (
        any(not parameters.get(key, "").strip() for key in ("host", "user", "dbname"))
        or any(key in parameters for key in ("service", "hostaddr"))
        or "," in parameters.get("host", "")
        or parameters.get("host", "").startswith(("/", "@"))
    ):
        raise PostgresConfigurationError(
            "DATABASE_URL에 단일 TCP 호스트, 계정과 DB 이름을 명시해야 합니다."
        )
    try:
        port = int(parameters.get("port", "5432"))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise PostgresConfigurationError(
            "PostgreSQL 포트 설정이 올바르지 않습니다."
        ) from None

    sslmode = parameters.get("sslmode", "require")
    if sslmode not in {"require", "verify-ca", "verify-full"}:
        raise PostgresConfigurationError("PostgreSQL 연결에는 TLS가 필요합니다.")

    # Explicit target fields prevent ambient PG* defaults from redirecting us.
    parameters["port"] = str(port)
    parameters["sslmode"] = sslmode
    parameters.pop("connect_timeout", None)
    return PostgresSettings(
        _parameters=MappingProxyType(parameters),
        connect_timeout=connect_timeout,
        sslmode=sslmode,
    )


def connect_postgres(*, connect_timeout: int = 10) -> Connection[dict[str, Any]]:
    """Open exactly one configured connection; execute no SQL.

    The caller owns the connection. Use 'with connect_postgres() as connection'
    for Psycopg's commit/rollback/close context management. Dictionary rows are
    intentional and are NOT a drop-in replacement for sqlite3.Row indexing.
    """
    settings = load_postgres_settings(connect_timeout=connect_timeout)
    driver, _, row_factory = _driver_modules()
    try:
        return driver.connect(
            **dict(settings._parameters),
            connect_timeout=settings.connect_timeout,
            row_factory=row_factory,
            autocommit=False,
        )
    except (driver.Error, OSError, ValueError, UnicodeError):
        # Driver errors can contain credentials or connection details.
        # Suppress the original exception in ordinary tracebacks and never log it.
        raise PostgresConnectionError(
            "PostgreSQL에 연결하지 못했습니다. 접속 설정과 서버 상태를 확인하세요. "
            "다른 DB로 자동 전환하거나 데이터를 삭제하지 않았습니다."
        ) from None
