"""Fixed diagnostic categories, with no exception details or SQL in logs."""
import unittest
from unittest.mock import MagicMock, patch

import app_database as database


class DatabaseDiagnosticsTests(unittest.TestCase):
    def test_sqlstate_categories_do_not_log_sensitive_details(self):
        for state, category in (("55P03", "lock_timeout"), ("57014", "statement_timeout"),
                                ("08006", "connection"), ("28000", "authentication"),
                                ("40001", "transaction_conflict"), ("53300", "resource_limit"),
                                ("42601", "query_or_schema"), ("23505", "constraint"),
                                ("sensitive-fixture", "unclassified"), (None, "unclassified")):
            error = RuntimeError("private DSN SQL and health text fixture")
            error.sqlstate = state
            with self.subTest(state=state), self.assertLogs("app_database", level="ERROR") as captured:
                database._log_database_failure("execute", error)
            self.assertEqual(captured.output, [
                "ERROR:app_database:Database failure: stage=execute category=" + category])

    def test_connect_and_schema_failures_remain_safe_and_distinguishable(self):
        scenarios = (("catalog", "postgres_migrate.load_migrations"),
                     ("connect", "app_database.connect_postgres"),
                     ("schema_history", "postgres_migrate.inspect_history"))
        for stage, target in scenarios:
            raw = MagicMock()
            with self.subTest(stage=stage), patch("postgres_migrate.load_migrations", return_value=[]), \
                 patch("app_database.connect_postgres", return_value=raw), \
                 patch(target, side_effect=RuntimeError("sensitive-fixture")), \
                 self.assertLogs("app_database", level="ERROR") as captured:
                with self.assertRaises(database.DatabaseUnavailable) as failure:
                    database.connect_application_postgres()
            self.assertNotIn("sensitive-fixture", str(failure.exception))
            self.assertEqual(captured.output, [
                "ERROR:app_database:Database failure: stage=" + stage + " category=unclassified"])

    def test_query_and_finish_failures_do_not_retry_writes(self):
        for action, stage in (("execute", "execute"), ("executemany", "executemany"), ("finish", "finish")):
            raw = MagicMock()
            connection = database.PostgresConnection(raw)
            transaction = MagicMock()
            connection._transaction = transaction
            error = RuntimeError("sensitive-fixture")
            error.sqlstate = "57014"
            if action == "finish":
                transaction.__exit__.side_effect = error
                call = lambda: connection.__exit__(None, None, None)
            elif action == "execute":
                raw.execute.side_effect = error
                call = lambda: connection.execute("synthetic SQL", ("private-fixture",))
            else:
                raw.cursor.return_value.executemany.side_effect = error
                call = lambda: connection.executemany("synthetic SQL", [("private-fixture",)])
            with self.subTest(action=action), self.assertLogs("app_database", level="ERROR") as captured:
                with self.assertRaises(database.DatabaseUnavailable):
                    call()
            self.assertEqual(captured.output, [
                "ERROR:app_database:Database failure: stage=" + stage + " category=statement_timeout"])
            if action == "execute":
                raw.execute.assert_called_once()
            elif action == "executemany":
                raw.cursor.return_value.executemany.assert_called_once()
            else:
                transaction.__exit__.assert_called_once()
