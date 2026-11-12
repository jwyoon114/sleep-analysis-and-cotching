"""Synthetic configuration and mocked connections only; never contact a DB server."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import traceback
import unittest
from contextlib import closing
from unittest.mock import MagicMock, patch
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import postgres_db as pg

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None

SYNTHETIC_PASSWORD = "synthetic-test-only-password"
TEST_URL = (
    "postgresql://synthetic_user:" + SYNTHETIC_PASSWORD
    + "@database.example.invalid/synthetic_database"
)


class ConfigurationBoundaryTests(unittest.TestCase):
    def test_module_import_is_inactive_even_with_invalid_database_url(self):
        with patch.dict(os.environ, {"DATABASE_URL": "invalid synthetic configuration"}):
            importlib.reload(pg)

    def test_missing_or_blank_url_fails_before_loading_driver(self):
        for value in (None, "", " \n "):
            with self.subTest(value_is_missing=value is None):
                with patch.dict(os.environ, {}, clear=True):
                    if value is not None:
                        os.environ["DATABASE_URL"] = value
                    with patch.object(pg, "_driver_modules") as loader:
                        with self.assertRaises(pg.PostgresConfigurationError):
                            pg.connect_postgres()
                        loader.assert_not_called()

    def test_non_postgres_url_or_keyword_dsn_is_rejected(self):
        values = (
            "sqlite:///synthetic.sqlite3",
            "https://database.example.invalid",
            "host=database.example.invalid dbname=synthetic",
            "postgresql://synthetic_user@host/db\x00",
        )
        for value in values:
            with self.subTest():
                # OS environments reject NUL themselves; mock getenv to test our guard.
                with patch("postgres_db.os.getenv", return_value=value):
                    with patch.object(pg, "_driver_modules") as loader:
                        with self.assertRaises(pg.PostgresConfigurationError):
                            pg.connect_postgres()
                        loader.assert_not_called()

    def test_timeout_must_be_finite_integer(self):
        for timeout in (0, -1, 61, True, 1.5, "10", None):
            with self.subTest(timeout_type=type(timeout).__name__):
                with patch.dict(os.environ, {"DATABASE_URL": TEST_URL}):
                    with self.assertRaises(pg.PostgresConfigurationError):
                        pg.connect_postgres(connect_timeout=timeout)

    def test_ambient_service_or_hostaddr_cannot_redirect_target(self):
        for key in ("PGSERVICE", "PGHOSTADDR"):
            with self.subTest(variable=key):
                with patch.dict(os.environ, {
                    "DATABASE_URL": TEST_URL, key: "synthetic-ambient-target"
                }, clear=True):
                    with patch.object(pg, "_driver_modules") as loader:
                        with self.assertRaises(pg.PostgresConfigurationError):
                            pg.connect_postgres()
                        loader.assert_not_called()

    def test_missing_driver_error_hides_original_details(self):
        with patch.dict(os.environ, {"DATABASE_URL": TEST_URL}, clear=True):
            with patch.object(pg, "import_module", side_effect=ImportError(TEST_URL)):
                try:
                    pg.connect_postgres()
                except pg.PostgresDriverUnavailable as error:
                    self.assertNotIn(SYNTHETIC_PASSWORD, traceback.format_exc())
                    self.assertNotIn(TEST_URL, str(error))
                else:
                    self.fail("Expected optional-driver error")


@unittest.skipIf(psycopg is None, "Install requirements-postgres.txt for driver tests")
class PostgresDriverTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "DATABASE_URL": TEST_URL, "PGSERVICE": "", "PGHOSTADDR": ""
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.connector = patch(
            "psycopg.connect",
            side_effect=AssertionError("Real database connections are forbidden"),
        )
        self.connect = self.connector.start()
        self.addCleanup(self.connector.stop)

    def test_config_uses_real_libpq_parser_without_connecting(self):
        settings = pg.load_postgres_settings()
        self.assertEqual(settings.sslmode, "require")
        self.assertEqual(settings.connect_timeout, 10)
        self.assertEqual(settings._parameters["host"], "database.example.invalid")
        self.assertEqual(settings._parameters["port"], "5432")
        self.connect.assert_not_called()

    def test_postgres_scheme_and_encoded_credentials_are_supported(self):
        secret = "synthetic:password@with/slash"
        value = (
            "postgres://synthetic_user:" + quote(secret, safe="")
            + "@database.example.invalid:5433/synthetic_database?sslmode=verify-full"
        )
        with patch.dict(os.environ, {"DATABASE_URL": value}):
            settings = pg.load_postgres_settings()
        self.assertEqual(settings._parameters["password"], secret)
        self.assertEqual(settings._parameters["port"], "5433")
        self.assertEqual(settings.sslmode, "verify-full")
        self.connect.assert_not_called()

    def test_incomplete_target_does_not_use_ambient_pg_defaults(self):
        values = (
            "postgresql:///synthetic_database",
            "postgresql://database.example.invalid/synthetic_database",
            "postgresql://synthetic_user@database.example.invalid/",
        )
        for value in values:
            with self.subTest():
                with patch.dict(os.environ, {
                    "DATABASE_URL": value,
                    "PGHOST": "ambient.example.invalid",
                    "PGDATABASE": "ambient_database",
                    "PGUSER": "ambient_user",
                }):
                    with self.assertRaises(pg.PostgresConfigurationError):
                        pg.connect_postgres()
        self.connect.assert_not_called()

    def test_services_hostaddr_unix_socket_and_multi_host_are_rejected(self):
        values = (
            TEST_URL + "?service=synthetic_service",
            TEST_URL + "?hostaddr=127.0.0.1",
            TEST_URL + "?host=%2Ftmp",
            TEST_URL + "?host=first.example.invalid,second.example.invalid",
        )
        for value in values:
            with self.subTest():
                with patch.dict(os.environ, {"DATABASE_URL": value}):
                    with self.assertRaises(pg.PostgresConfigurationError):
                        pg.connect_postgres()
        self.connect.assert_not_called()

    def test_insecure_tls_modes_are_rejected(self):
        for mode in ("disable", "allow", "prefer", "invalid"):
            with self.subTest(mode=mode):
                with patch.dict(os.environ, {"DATABASE_URL": TEST_URL + "?sslmode=" + mode}):
                    with self.assertRaises(pg.PostgresConfigurationError):
                        pg.connect_postgres()
        self.connect.assert_not_called()

    def test_tls_options_are_preserved(self):
        with patch.dict(os.environ, {
            "DATABASE_URL": TEST_URL + "?sslmode=require&channel_binding=require"
        }):
            settings = pg.load_postgres_settings()
        self.assertEqual(settings._parameters["channel_binding"], "require")
        self.connect.assert_not_called()

    def test_invalid_port_is_rejected_without_connecting(self):
        for port in ("0", "65536", "invalid", "5432,5433"):
            with self.subTest():
                with patch.dict(os.environ, {"DATABASE_URL": TEST_URL + "?port=" + port}):
                    with self.assertRaises(pg.PostgresConfigurationError):
                        pg.connect_postgres()
        self.connect.assert_not_called()

    def test_parser_error_hides_url_and_password(self):
        with patch.dict(os.environ, {"DATABASE_URL": TEST_URL + "?unknown_option=" + SYNTHETIC_PASSWORD}):
            try:
                pg.connect_postgres()
            except pg.PostgresConfigurationError:
                formatted = traceback.format_exc()
                self.assertNotIn(SYNTHETIC_PASSWORD, formatted)
                self.assertNotIn(TEST_URL, formatted)
            else:
                self.fail("Expected invalid connection configuration")
        self.connect.assert_not_called()

    def test_settings_are_immutable_and_repr_does_not_expose_target(self):
        settings = pg.load_postgres_settings()
        for sensitive in (SYNTHETIC_PASSWORD, "synthetic_user", "synthetic_database", "database.example.invalid"):
            self.assertNotIn(sensitive, repr(settings))
            self.assertNotIn(sensitive, str(settings))
        with self.assertRaises(TypeError):
            settings._parameters["dbname"] = "replacement"

    def test_success_opens_once_with_explicit_target_and_no_sql(self):
        connection = MagicMock()
        self.connect.side_effect = None
        self.connect.return_value = connection
        with patch.dict(os.environ, {
            "DATABASE_URL": TEST_URL + "?connect_timeout=999",
            "PGPORT": "6543",
        }):
            actual = pg.connect_postgres(connect_timeout=12)
        self.assertIs(actual, connection)
        self.connect.assert_called_once()
        arguments = self.connect.call_args.kwargs
        self.assertEqual(arguments["dbname"], "synthetic_database")
        self.assertEqual(arguments["user"], "synthetic_user")
        self.assertEqual(arguments["host"], "database.example.invalid")
        self.assertEqual(arguments["port"], "5432")
        self.assertEqual(arguments["connect_timeout"], 12)
        self.assertEqual(arguments["sslmode"], "require")
        self.assertIs(arguments["row_factory"], dict_row)
        self.assertIs(arguments["autocommit"], False)
        connection.execute.assert_not_called()
        connection.cursor.assert_not_called()
        connection.close.assert_not_called()

    def test_connection_failure_is_sanitized_without_retry_or_sqlite_fallback(self):
        self.connect.side_effect = psycopg.OperationalError(TEST_URL)
        with patch("sqlite3.connect", side_effect=AssertionError("SQLite fallback forbidden")) as sqlite:
            try:
                pg.connect_postgres()
            except pg.PostgresConnectionError:
                formatted = traceback.format_exc()
                self.assertNotIn(SYNTHETIC_PASSWORD, formatted)
                self.assertNotIn(TEST_URL, formatted)
            else:
                self.fail("Expected connection failure")
        self.connect.assert_called_once()
        sqlite.assert_not_called()

    def test_os_connection_failure_is_sanitized(self):
        self.connect.side_effect = OSError(TEST_URL)
        with self.assertRaises(pg.PostgresConnectionError) as caught:
            pg.connect_postgres()
        self.assertNotIn(SYNTHETIC_PASSWORD, str(caught.exception))
        self.connect.assert_called_once()


class SQLiteIsolationTests(unittest.TestCase):
    def test_existing_sqlite_accounts_and_twenty_tables_remain_independent(self):
        import health_records
        import health_sync
        import sleep_accounts
        import sleep_alarms

        expected_tables = {
            "imports", "sessions", "import_sessions", "stages", "samples",
            "accounts", "auth_tokens", "login_attempts", "coaching",
            "trash_sessions", "trash_coaching", "coaching_context",
            "permanent_deletions", "session_created", "coaching_requests",
            "health_connections", "health_sync_sessions", "health_advice_jobs",
            "sleep_alarm_settings", "sleep_alarm_fires",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.sqlite3"
            with patch.dict(os.environ, {}, clear=True):
                with patch.object(pg, "_driver_modules", side_effect=AssertionError("Postgres must remain opt-in")) as driver:
                    account = sleep_accounts.register(
                        "synthetic-local-user", "synthetic-local-password", path
                    )
                    login = sleep_accounts.login(
                        "synthetic-local-user", "synthetic-local-password", path
                    )
                    self.assertEqual(sleep_accounts.current_user(login["token"], path)["id"], account["id"])
                    with closing(health_sync.database(path)):
                        pass
                    with closing(sleep_alarms.connect(path)):
                        pass
                    with closing(health_records.connect(path)) as database:
                        actual = {r[0] for r in database.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        )}
                    self.assertEqual(actual, expected_tables)
                    driver.assert_not_called()


if __name__ == "__main__":
    unittest.main()
