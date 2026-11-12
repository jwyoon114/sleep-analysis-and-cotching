"""Explicit backend selection and a small DB-API bridge for shared services.

PostgreSQL never creates schema or falls back to SQLite. Transactions are
serialized initially to preserve the single-writer service assumptions. This
is deliberately conservative; finer locks require real multi-backend tests.
"""
from collections.abc import Mapping
import os

from postgres_db import connect_postgres


class DatabaseUnavailable(RuntimeError):
    pass


class BackupPolicyPending(DatabaseUnavailable):
    pass


def uses_postgres(db_path=None):
    # Explicit local files are used by the desktop and isolated SQLite tests.
    # A configured cloud backend must NEVER allow an explicit path to bypass it.
    backend = os.getenv("SLEEP_DB_BACKEND", "").strip().lower()
    if backend not in {"", "sqlite", "postgresql"}:
        raise DatabaseUnavailable("SLEEP_DB_BACKEND 설정을 확인하세요.")
    configured = "DATABASE_URL" in os.environ
    if backend == "sqlite" and configured:
        raise DatabaseUnavailable("SQLite와 DATABASE_URL을 동시에 설정할 수 없습니다.")
    selected = backend == "postgresql" or configured
    if selected and db_path is not None:
        raise DatabaseUnavailable("PostgreSQL 모드에서 로컬 DB 경로를 사용할 수 없습니다.")
    return selected


class Row(Mapping):
    """Retain both sqlite3.Row's positional access and dict(row) contract."""
    def __init__(self, values):
        self._values = values
        self._sequence = tuple(values.values())

    def __getitem__(self, key):
        return self._sequence[key] if isinstance(key, (int, slice)) else self._values[key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)


def bind_sql(sql):
    """Translate qmark parameters, preserving SQL strings/identifiers/comments.

    Only application statements use this bridge; migration SQL uses Psycopg
    directly. Percent literals must be escaped even inside SQL literals when
    Psycopg parameters are supplied.
    """
    import re
    result, quote, depth, index = [], None, 0, 0
    while index < len(sql):
        tail = sql[index:]
        char = sql[index]
        if quote:
            if sql.startswith(quote, index):
                result.append(quote.replace("%", "%%")); index += len(quote)
                if quote in {"'", '"'} and sql.startswith(quote, index):
                    result.append(quote); index += 1
                else:
                    quote = None
            else:
                result.append("%%" if char == "%" else char); index += 1
        elif depth:
            if tail.startswith("/*"):
                result.append("/*"); depth += 1; index += 2
            elif tail.startswith("*/"):
                result.append("*/"); depth -= 1; index += 2
            else:
                result.append("%%" if char == "%" else char); index += 1
        elif tail.startswith("--"):
            stop = sql.find("\n", index)
            stop = len(sql) if stop < 0 else stop
            result.append(sql[index:stop].replace("%", "%%")); index = stop
        elif tail.startswith("/*"):
            result.append("/*"); depth = 1; index += 2
        elif char in {"'", '"'}:
            quote = char; result.append(char); index += 1
        elif (tag := re.match(r"\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$", tail)):
            quote = tag[0]; result.append(quote); index += len(quote)
        else:
            result.append("%s" if char == "?" else "%%" if char == "%" else char)
            index += 1
    if quote or depth:
        raise DatabaseUnavailable("DB 쿼리 형식을 확인하세요.")
    return "".join(result)


class Cursor:
    def __init__(self, raw):
        self.raw = raw

    @property
    def rowcount(self):
        return self.raw.rowcount

    def fetchone(self):
        row = self.raw.fetchone()
        return Row(row) if row is not None else None

    def fetchall(self):
        return [Row(row) for row in self.raw.fetchall()]

    def __iter__(self):
        for row in self.raw:
            yield Row(row)


class PostgresConnection:
    is_postgres = True

    def __init__(self, raw):
        self.raw = raw
        self._transaction = None

    def _begin(self):
        if self._transaction is not None:
            return
        try:
            self._transaction = self.raw.transaction()
            self._transaction.__enter__()
            self.raw.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            self.raw.execute("SET LOCAL search_path = pg_catalog, public")
            self.raw.execute("SET LOCAL lock_timeout = '10s'")
            self.raw.execute("SET LOCAL statement_timeout = '60s'")
            # All service connections participate, including reads before writes.
            # READ COMMITTED takes a fresh snapshot after obtaining this lock.
            self.raw.execute("SELECT pg_advisory_xact_lock(731412811)")
        except Exception:
            self.close()
            raise DatabaseUnavailable("DB 트랜잭션을 시작하지 못했습니다. 잠시 후 다시 시도하세요.") from None

    def execute(self, sql, parameters=None):
        self._begin()
        try:
            return Cursor(self.raw.execute(bind_sql(sql), () if parameters is None else parameters))
        except Exception:
            raise DatabaseUnavailable("DB 요청을 완료하지 못했습니다. 저장 상태를 확인한 뒤 다시 시도하세요.") from None

    def executemany(self, sql, parameters):
        self._begin()
        try:
            cursor = self.raw.cursor()
            cursor.executemany(bind_sql(sql), parameters)
            return Cursor(cursor)
        except Exception:
            raise DatabaseUnavailable("DB 요청을 완료하지 못했습니다. 저장 상태를 확인한 뒤 다시 시도하세요.") from None

    def __enter__(self):
        if self._transaction is not None:
            raise DatabaseUnavailable("중첩 DB 트랜잭션은 지원하지 않습니다.")
        self._begin()
        return self

    def __exit__(self, kind, value, traceback):
        transaction, self._transaction = self._transaction, None
        try:
            return transaction.__exit__(kind, value, traceback)
        except Exception:
            # A lost commit response does not prove that the server rolled back.
            raise DatabaseUnavailable("DB 처리를 확인하지 못했습니다. 저장 상태를 먼저 확인하세요.") from None

    def close(self):
        # Psycopg closes outstanding read transactions by rolling them back.
        self._transaction = None
        self.raw.close()


def connect_application_postgres():
    from postgres_migrate import inspect_history, load_migrations
    raw = None
    try:
        migrations = load_migrations()
        raw = connect_postgres()
        # Session-bound prepared plans must not leak across pooled sessions.
        # executemany also respects this setting; retain its batching support.
        raw.prepare_threshold = None
        with raw.transaction():
            raw.execute("SET LOCAL statement_timeout = '10s'")
            rows = inspect_history(raw, migrations)
            if len(rows) != len(migrations):
                raise DatabaseUnavailable("DB 마이그레이션 적용이 필요합니다.")
        return PostgresConnection(raw)
    except Exception:
        if raw is not None:
            raw.close()
        raise DatabaseUnavailable("PostgreSQL 연결·마이그레이션 상태를 확인하세요. 로컬 DB로 전환하지 않습니다.") from None


def begin_write(db):
    if getattr(db, "is_postgres", False):
        db._begin()
    else:
        db.execute("BEGIN IMMEDIATE")


def table_names(db):
    sql = "SELECT tablename FROM pg_tables WHERE schemaname='public'" if getattr(db, "is_postgres", False) else "SELECT name FROM sqlite_master WHERE type='table'"
    return {row[0] for row in db.execute(sql)}


def secure_delete(db):
    if not getattr(db, "is_postgres", False):
        db.execute("PRAGMA secure_delete=ON")


def require_backup_policy(db_path=None):
    if uses_postgres(db_path):
        from production_policy import backup_policy_ready
        if backup_policy_ready():
            return
        raise BackupPolicyPending("클라우드 백업의 보관·삭제 정책이 확정되지 않아 영구 삭제와 백업 생성을 보류했습니다.")
