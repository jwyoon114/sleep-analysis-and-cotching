"""Backend routing, binding, failure and deletion guards. No network calls."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app_database as database


class AppDatabaseTests(unittest.TestCase):
    def test_desktop_default_and_explicit_selection(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(database.uses_postgres())
            self.assertFalse(database.uses_postgres('synthetic.sqlite3'))
        with patch.dict(os.environ, {'SLEEP_DB_BACKEND': 'postgresql'}, clear=True):
            self.assertTrue(database.uses_postgres())
            with self.assertRaises(database.DatabaseUnavailable):
                database.uses_postgres('synthetic.sqlite3')

    def test_invalid_or_conflicting_configuration_never_falls_back(self):
        for values in ({'DATABASE_URL': ''}, {'DATABASE_URL': 'invalid'}):
            with patch.dict(os.environ, values, clear=True):
                self.assertTrue(database.uses_postgres())
                with self.assertRaises(database.DatabaseUnavailable):
                    database.uses_postgres('synthetic.sqlite3')
        for values in ({'SLEEP_DB_BACKEND': 'typo'}, {'SLEEP_DB_BACKEND': 'sqlite', 'DATABASE_URL': ''}):
            with patch.dict(os.environ, values, clear=True):
                with self.assertRaises(database.DatabaseUnavailable):
                    database.uses_postgres()

    def test_qmark_literals_comments_and_percent(self):
        sql = '''SELECT ?, '? 50%', "?", $$?%$$ /* ? /* ? */ ? */ -- ?%
        , 'it''s ?' WHERE id=?'''
        expected = '''SELECT %s, '? 50%%', "?", $$?%%$$ /* ? /* ? */ ? */ -- ?%%
        , 'it''s ?' WHERE id=%s'''
        self.assertEqual(database.bind_sql(sql), expected)
        for invalid in ("SELECT 'x", 'SELECT /* x', 'SELECT $body$x'):
            with self.assertRaises(database.DatabaseUnavailable):
                database.bind_sql(invalid)

    def test_row_contract_retains_null_and_json_text(self):
        row = database.Row({'id': 'a', 'context': '{"record_ids":[]}', 'missing': None})
        self.assertEqual(row[0], row['id'])
        self.assertEqual(row[-1], None)
        self.assertEqual(dict(row)['context'], '{"record_ids":[]}')

    def test_connection_failure_is_sanitized_and_no_local_file_is_created(self):
        import health_records
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            target = Path(directory) / 'must-not-exist.sqlite3'
            with patch.dict(os.environ, {'DATABASE_URL': 'invalid'}, clear=True), patch.object(health_records, 'DB_PATH', target), patch('app_database.connect_postgres', side_effect=RuntimeError('secret-password')):
                with self.assertRaises(database.DatabaseUnavailable) as error:
                    health_records.connect()
                self.assertNotIn('secret-password', str(error.exception))
                self.assertFalse(target.exists())

    def test_cloud_delete_and_backup_are_blocked_before_connecting(self):
        import backup_policy, history_service, sleep_accounts
        with patch.dict(os.environ, {'SLEEP_DB_BACKEND': 'postgresql'}, clear=True), patch('app_database.connect_postgres', side_effect=AssertionError('Must not connect')):
            for action in (lambda: history_service.purge_record('session', 'x', 'owner'),
                           lambda: sleep_accounts.delete_account('owner', 'synthetic-pass', '계정 삭제'),
                           backup_policy.create_backup):
                with self.assertRaises(database.BackupPolicyPending): action()
            self.assertEqual(history_service.expire_trash('owner'), 0)
            self.assertEqual(backup_policy.maintain_backups()['status'], 'cloud_policy_pending')

    def test_application_connection_requires_complete_migrations_and_disables_prepared_plans(self):
        for history in ([], [{'version': 1}]):
            raw = MagicMock()
            with patch('app_database.connect_postgres', return_value=raw), patch('postgres_migrate.load_migrations', return_value=['synthetic']), patch('postgres_migrate.inspect_history', return_value=history):
                if not history:
                    with self.assertRaises(database.DatabaseUnavailable): database.connect_application_postgres()
                    raw.close.assert_called_once()
                else:
                    connection = database.connect_application_postgres()
                    self.assertIsNone(raw.prepare_threshold)
                    self.assertIs(connection.raw, raw)

    def test_database_http_error_is_safe_503(self):
        import api
        from fastapi.testclient import TestClient
        with patch('sleep_alarms.start_worker'), TestClient(api.app) as client, patch('sleep_accounts.connect', side_effect=database.DatabaseUnavailable('secret-password')):
            response = client.get('/auth/me', headers={'Authorization': 'Bearer synthetic'})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()['detail']['code'], 'database_unavailable')
            self.assertNotIn('secret-password', response.text)


if __name__ == '__main__':
    unittest.main()
