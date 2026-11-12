"""Opt-in full service tests on a FRESH local disposable PostgreSQL database.

Never uses DATABASE_URL, never resets a database, never calls external AI.
Use a different fresh fixture from the migration integration suite.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import copy
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
TEST_URL = os.getenv('DALJAM_TEST_PG_URL')


@unittest.skipUnless(TEST_URL or os.getenv('DALJAM_TEST_POSTGRES_BIN'), 'A fresh, local disposable PostgreSQL DB is required')
class PostgresAPIIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.rows import dict_row
        import postgres_migrate
        if os.getenv('DALJAM_TEST_POSTGRES_BIN'):
            from postgres_migration_fixture import PostgresTestCluster
            cls.cluster = PostgresTestCluster(cls, Path(os.environ['DALJAM_TEST_POSTGRES_BIN']))
            name = cls.cluster.new_database()
            cls.connect = staticmethod(lambda **kwargs: cls.cluster.connect(name, autocommit=False))
        else:
            parsed = urlsplit(TEST_URL)
            if parsed.hostname not in {'127.0.0.1', 'localhost', '::1'} or parsed.path != '/daljam_disposable_tests':
                raise RuntimeError('Only the named local disposable test database is allowed')
            cls.connect = staticmethod(lambda **kwargs: psycopg.connect(TEST_URL, row_factory=dict_row, connect_timeout=5))
        with cls.connect() as db:
            if db.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'").fetchall():
                raise RuntimeError('An EMPTY database is required; nothing was removed')
        with patch('postgres_db.connect_postgres', cls.connect):
            postgres_migrate.apply_migrations()

    def test_service_and_http_contracts(self):
        import api, app_database, backup_policy, coaching_service, health_records
        import health_sync, history_service, service_limits, sleep_accounts, sleep_alarms
        from fastapi.testclient import TestClient
        from json_sleep import EXAMPLE_JSON
        from openai import OpenAI
        exported = json.loads(EXAMPLE_JSON)
        exported['samples'] = [{'metric': 'heartRate', 'unit': 'bpm', 'source': 'synthetic-watch',
                                'start': '2026-11-01T23:10:00+09:00', 'value': 62}]
        EXAMPLE_JSON = json.dumps(exported, ensure_ascii=False)

        with patch.dict(os.environ, {'SLEEP_DB_BACKEND': 'postgresql', 'SLEEP_DESKTOP_ALARMS': '0'}), patch('app_database.connect_postgres', self.connect), patch.object(OpenAI, '__init__', side_effect=AssertionError('External AI is forbidden')):
            client = TestClient(api.app)
            self.addCleanup(client.close)
            self.assertEqual(client.get('/ready').status_code, 200)
            password = 'synthetic-password-only'
            with self.subTest('registration login authentication and owner isolation'):
                users = {}
                headers = {}
                for name in ('alice-test', 'bob-test'):
                    response = client.post('/auth/register', json={'username': name, 'password': password})
                    self.assertEqual(response.status_code, 201, response.text)
                    users[name] = response.json()['user']
                    response = client.post('/auth/login', json={'username': name, 'password': password})
                    self.assertEqual(response.status_code, 200, response.text)
                    headers[name] = {'Authorization': 'Bearer ' + response.json()['token']}
                alice, bob = users['alice-test']['id'], users['bob-test']['id']
                a, b = headers['alice-test'], headers['bob-test']
                self.assertEqual(client.get('/auth/me', headers=a).json()['user']['id'], alice)
                self.assertEqual(client.post('/auth/login', json={'username': 'alice-test', 'password': 'wrong'}).status_code, 401)
                self.assertEqual(client.get('/watch/sessions').status_code, 401)

            with self.subTest('concurrent imports are idempotent and stages survive reconnection'):
                def upload(_):
                    return health_records.import_export(EXAMPLE_JSON, 'synthetic.json', alice)
                with ThreadPoolExecutor(max_workers=3) as pool:
                    results = list(pool.map(upload, range(3)))
                self.assertEqual(sum(r['added_sessions'] for r in results), 1)
                sid = results[0]['analysis_ids'][0]
                self.assertEqual(len(health_records.list_sessions(alice)), 1)
                self.assertEqual(client.get('/watch/sessions/' + sid, headers=b).status_code, 404)
                with closing(health_records.connect()) as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM stages WHERE session_id=?', (sid,)).fetchone()[0], 4)
                    self.assertEqual(db.execute('SELECT count(*) FROM samples WHERE subject=?', (alice,)).fetchone()[0], 1)
                    self.assertEqual(db.execute("SELECT '? 50%' AS literal, ? AS bound", ('safe-value',)).fetchone()['literal'], '? 50%')
                response = client.post('/watch/import', headers=a, files={'file': ('synthetic.json', EXAMPLE_JSON, 'application/json')})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue(response.json()['duplicate_file'])
                changed = json.loads(EXAMPLE_JSON)
                changed['sessions'][0]['segments'][0]['stage'] = 'rem'
                with self.assertRaises(ValueError):
                    health_records.import_export(json.dumps(changed), 'changed.json', alice)
                self.assertEqual(health_records.get_owned_session(sid, alice)['stage_minutes']['core'], 20)

            with self.subTest('real free rules coaching and versioned presentation JSON contract'):
                result = coaching_service.generate(alice, sid, {'age_group': '미입력'})
                answer = result['coaching']
                self.assertTrue(answer)
                self.assertEqual(result['context']['engine'], 'rules')
                self.assertEqual(result['context']['presentation']['version'], 1)
                cid = result['id']
                context = result['context']
                saved = client.get('/watch/sessions/' + sid + '/coaching', headers=a)
                self.assertEqual(saved.status_code, 200, saved.text)
                stored = coaching_service.list_coaching(alice, sid)[0]
                self.assertEqual(stored['coaching'], answer)
                self.assertEqual(stored['context'], context)
                self.assertEqual(coaching_service.list_coaching(bob, sid), [])

            with self.subTest('trash restore and approved permanent-deletion guard'):
                self.assertEqual(client.delete('/watch/sessions/' + sid, headers=b).status_code, 404)
                self.assertEqual(client.delete('/watch/sessions/' + sid, headers=a).status_code, 200)
                self.assertEqual(health_records.list_sessions(alice), [])
                self.assertEqual(len(history_service.trash_history(alice)['sessions']), 1)
                response = client.delete('/watch/trash/session/' + sid, headers=a)
                self.assertEqual(response.status_code, 503, response.text)
                self.assertEqual(response.json()['detail']['code'], 'backup_policy_pending')
                self.assertTrue(history_service.restore_record('session', sid, alice))
                self.assertEqual(coaching_service.list_coaching(alice, sid)[0]['coaching'], answer)
                self.assertTrue(coaching_service.delete_coaching(alice, sid, cid))
                self.assertTrue(history_service.restore_record('coaching', cid, alice))
                response = client.request('DELETE', '/auth/me', headers=a, json={'current_password': password, 'confirmation': '계정 삭제'})
                self.assertEqual(response.status_code, 503, response.text)
                self.assertEqual(client.get('/auth/me', headers=a).status_code, 200)
                self.assertIsNone(backup_policy.maintain_backups()['retention_days'])

            with self.subTest('native health create update retry rollback token rotation'):
                paired = health_sync.pair(alice, 'healthkit', 'synthetic-watch', 'Synthetic Watch')
                token = paired['sync_token']
                snapshot = {'provider': 'healthkit', 'source_id': 'synthetic-watch', 'timezone': 'Asia/Seoul',
                            'window_start': '2026-11-03T00:00:00Z', 'window_end': '2026-11-07T00:00:00Z',
                            'records': [{'id': 'synthetic-night', 'start': '2026-11-04T23:00:00+09:00', 'end': '2026-11-05T07:00:00+09:00',
                                         'segments': [{'start': '2026-11-04T23:00:00+09:00', 'end': '2026-11-05T07:00:00+09:00', 'stage': 'core'}]}]}
                response = client.post('/mobile/health-sync', headers={'Authorization': 'Bearer ' + token}, json=snapshot)
                self.assertEqual(response.status_code, 200, response.text)
                health_sid = response.json()['analysis_ids'][0]
                with ThreadPoolExecutor(max_workers=2) as pool:
                    repeats = list(pool.map(lambda _: health_sync.synchronize(token, snapshot), range(2)))
                self.assertEqual(sum(r['added_sessions'] + r['updated_sessions'] for r in repeats), 0)
                changed = copy.deepcopy(snapshot)
                changed['records'][0]['segments'][0]['stage'] = 'rem'
                self.assertEqual(health_sync.synchronize(token, changed)['updated_sessions'], 1)
                invalid = copy.deepcopy(changed)
                invalid['records'][0]['segments'][0]['stage'] = 'invalid'
                with self.assertRaises(ValueError): health_sync.synchronize(token, invalid)
                self.assertEqual(health_records.get_owned_session(health_sid, alice)['stage_minutes']['rem'], 480)
                token2 = health_sync.pair(alice, 'healthkit', 'synthetic-watch', 'Synthetic Watch')['sync_token']
                with closing(health_records.connect()) as db:
                    self.assertIsNone(db.execute('SELECT last_window_end FROM health_connections WHERE account_id=?', (alice,)).fetchone()[0])
                    self.assertEqual(db.execute('SELECT count(*) FROM health_sync_sessions WHERE account_id=?', (alice,)).fetchone()[0], 1)
                with self.assertRaises(sleep_accounts.AuthenticationError): health_sync.synchronize(token, snapshot)
                health_sync.synchronize(token2, changed)

            with self.subTest('internal deletion SQL and JSON references, always rolled back'):
                class RollbackProbe(Exception): pass
                with self.assertRaises(RollbackProbe):
                    with closing(health_records.connect()) as db, db:
                        # Test the SQL without enabling the guarded public API.
                        db.execute('INSERT INTO coaching VALUES(?,?,?,?,?,?)', ('synthetic-cross-reference', alice, health_sid, '보존할 원문', '{}', '2026-11-11'))
                        db.execute('INSERT INTO coaching_context VALUES(?,?)', ('synthetic-cross-reference', json.dumps({'record_ids': [sid, health_sid]})))
                        self.assertFalse(health_records.erase_session_rows(db, sid, bob))
                        self.assertTrue(health_records.erase_session_rows(db, sid, alice))
                        self.assertEqual(db.execute('SELECT count(*) FROM samples WHERE subject=?', (alice,)).fetchone()[0], 0)
                        self.assertIsNone(db.execute('SELECT payload FROM coaching_context WHERE coaching_id=?', ('synthetic-cross-reference',)).fetchone())
                        self.assertEqual(db.execute('SELECT text FROM coaching WHERE id=?', ('synthetic-cross-reference',)).fetchone()[0], '보존할 원문')
                        raise RollbackProbe()
                with self.assertRaises(RollbackProbe):
                    with closing(health_records.connect()) as db, db:
                        sleep_accounts.erase_account_rows(db, alice)
                        self.assertIsNone(db.execute('SELECT id FROM accounts WHERE id=?', (alice,)).fetchone())
                        self.assertIsNotNone(db.execute('SELECT id FROM accounts WHERE id=?', (bob,)).fetchone())
                        raise RollbackProbe()
                self.assertEqual(len(health_records.list_sessions(alice)), 2)

            with self.subTest('atomic request caps and alarm persistence'):
                def reserve(_):
                    try:
                        service_limits.reserve_coaching_request(alice)
                        return True
                    except service_limits.CoachingLimitError:
                        return False
                with patch.dict(os.environ, {'COACHING_USER_LIMIT_24H': '1', 'COACHING_GLOBAL_LIMIT_24H': '1'}), ThreadPoolExecutor(max_workers=3) as pool:
                    self.assertEqual(sum(pool.map(reserve, range(3))), 1)
                settings = sleep_alarms.save_settings(alice, '23:00', '07:00', 'Asia/Seoul', False, cid)
                self.assertFalse(settings['enabled'])
                self.assertEqual(sleep_alarms.get_settings(alice)['coaching_id'], cid)

            with self.subTest('SQL failure rolls back and HTTP database failure stays sanitized'):
                with self.assertRaises(app_database.DatabaseUnavailable):
                    with closing(health_records.connect()) as db, db:
                        db.execute('INSERT INTO login_attempts VALUES(?,?)', ('rollback-probe', 'synthetic'))
                        db.execute('SELECT 1/0')
                with closing(health_records.connect()) as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM login_attempts WHERE username=?', ('rollback-probe',)).fetchone()[0], 0)
                with patch('app_database.connect_postgres', side_effect=RuntimeError('secret-password')):
                    response = client.get('/auth/me', headers=a)
                    self.assertEqual(response.status_code, 503)
                    self.assertNotIn('secret-password', response.text)

            with self.subTest('account edit revokes web and native tokens without changing saved records'):
                response = client.patch('/auth/me', headers=a, json={'current_password': password, 'new_username': 'alice-updated'})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(client.get('/auth/me', headers=a).status_code, 401)
                with self.assertRaises(sleep_accounts.AuthenticationError): health_sync.synchronize(token2, snapshot)
                self.assertEqual(len(health_records.list_sessions(alice)), 2)

            with self.subTest('production consent is atomic and deletion works with managed backup policy'):
                with patch.dict(os.environ, {'DALJAM_ENV': 'production', 'DALJAM_BACKUP_POLICY': 'render-pitr-7d-v1'}):
                    credentials = {'username': 'production-synthetic', 'password': password}
                    self.assertEqual(client.post('/auth/register', json=credentials).status_code, 400)
                    credentials.update(privacy_consent=True, health_consent=True, policy_version='2026-11-12-v1', overseas_consent=True, adult_confirmed=True)
                    response = client.post('/auth/register', json=credentials)
                    self.assertEqual(response.status_code, 201, response.text)
                    uid = response.json()['user']['id']
                    with closing(health_records.connect()) as db:
                        self.assertEqual(db.execute('SELECT policy_version FROM account_consents WHERE account_id=?', (uid,)).fetchone()[0], '2026-11-12-v1')
                    result = client.post('/auth/login', json={'username': credentials['username'], 'password': password})
                    auth = {'Authorization': 'Bearer ' + result.json()['token']}
                    sid = health_records.import_export(EXAMPLE_JSON, 'synthetic.json', uid)['analysis_ids'][0]
                    self.assertTrue(health_records.delete_session(sid, uid))
                    self.assertTrue(history_service.purge_record('session', sid, uid))
                    response = client.request('DELETE', '/auth/me', headers=auth, json={'current_password': password, 'confirmation': '계정 삭제'})
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(client.get('/auth/me', headers=auth).status_code, 401)
                    with closing(health_records.connect()) as db:
                        self.assertEqual(db.execute('SELECT count(*) FROM account_consents WHERE account_id=?', (uid,)).fetchone()[0], 0)


if __name__ == '__main__': unittest.main()
