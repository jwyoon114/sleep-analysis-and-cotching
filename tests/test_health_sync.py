"""Synthetic data only. No API calls, real accounts, or production database."""
import copy
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from health_records import connect, list_sessions, delete_session, get_owned_session
import health_sync
from sleep_accounts import AuthenticationError, erase_account_rows

class HealthSyncTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.db=Path(self.temp.name)/'test.sqlite3'
  with closing(connect(self.db)) as db, db:
   for account in ('alice','bob'):
    db.execute('INSERT INTO accounts VALUES(?,?,?,?,?)',(account,account,'test','test','2026-01-01'))
  self.token=health_sync.pair('alice','healthkit','watch','Watch',path=self.db)['sync_token']
  self.snapshot={'provider':'healthkit','source_id':'watch','timezone':'Asia/Seoul','window_start':'2026-11-01T00:00:00Z','window_end':'2026-11-07T00:00:00Z','records':[
   {'id':'broad','start':'2026-11-03T23:00:00+09:00','end':'2026-11-04T07:00:00+09:00','segments':[{'start':'2026-11-03T23:00:00+09:00','end':'2026-11-04T07:00:00+09:00','stage':'unspecified'}]},
   {'id':'deep','start':'2026-11-04T00:00:00+09:00','end':'2026-11-04T01:00:00+09:00','segments':[{'start':'2026-11-04T00:00:00+09:00','end':'2026-11-04T01:00:00+09:00','stage':'deep'}]}]}
 def tearDown(self):self.temp.cleanup()
 def sync(self,snapshot=None):return health_sync.synchronize(self.token,snapshot or self.snapshot,self.db)
 def test_overlap_and_repeat_do_not_double_count(self):
  first=self.sync();second=self.sync()
  self.assertEqual(first['added_sessions'],1);self.assertEqual(second['added_sessions'],0);self.assertEqual(second['updated_sessions'],0)
  record=list_sessions('alice',self.db)[0]
  self.assertEqual(record['asleep_minutes'],480);self.assertEqual(record['stage_minutes']['deep'],60)
  self.assertEqual(list_sessions('bob',self.db),[])
 def test_correction_keeps_session_id(self):
  sid=self.sync()['analysis_ids'][0];changed=copy.deepcopy(self.snapshot)
  changed['records'][1]['segments'][0]['stage']='rem'
  result=self.sync(changed)
  self.assertEqual(result['analysis_ids'],[sid]);self.assertEqual(result['updated_sessions'],1)
 def test_user_deleted_record_does_not_return(self):
  sid=self.sync()['analysis_ids'][0];delete_session(sid,'alice',self.db)
  self.assertEqual(self.sync()['skipped_deleted'],1);self.assertEqual(list_sessions('alice',self.db),[])
 def test_permanently_deleted_record_does_not_return(self):
  sid=self.sync()['analysis_ids'][0]
  from health_records import erase_session_rows
  with closing(connect(self.db)) as db, db:
   erase_session_rows(db,sid,'alice')
   db.execute('INSERT INTO permanent_deletions VALUES(?,?,?,?)',('session',sid,'alice',datetime.now(timezone.utc).isoformat()))
  self.assertEqual(self.sync()['skipped_deleted'],1);self.assertEqual(list_sessions('alice',self.db),[])
 def test_bad_snapshot_is_atomic(self):
  self.sync();bad=copy.deepcopy(self.snapshot);bad['records'][1]['segments'][0]['stage']='invalid'
  with self.assertRaises(ValueError):self.sync(bad)
  self.assertEqual(list_sessions('alice',self.db)[0]['stage_minutes']['deep'],60)
 def test_source_mismatch_rejected(self):
  bad=copy.deepcopy(self.snapshot);bad['source_id']='other'
  with self.assertRaises(ValueError):self.sync(bad)
 def test_revoke_and_rotate(self):
  old=self.token;self.token=health_sync.pair('alice','healthkit','watch','Watch',path=self.db)['sync_token']
  with self.assertRaises(AuthenticationError):health_sync.synchronize(old,self.snapshot,self.db)
  self.sync();health_sync.disconnect('alice',self.db)
  with self.assertRaises(AuthenticationError):self.sync()
 def test_account_deletion_cascades(self):
  self.sync()
  with closing(connect(self.db)) as db, db:erase_account_rows(db,'alice')
  self.assertFalse(health_sync.status('alice',self.db)['connected'])
  with self.assertRaises(AuthenticationError):self.sync()
 def test_empty_snapshot_cannot_erase_history(self):
  self.sync();empty=copy.deepcopy(self.snapshot);empty['records']=[]
  self.sync(empty)
  self.assertEqual(len(list_sessions('alice',self.db)),1)
 def test_detailed_stage_conflict_rejected(self):
  bad=copy.deepcopy(self.snapshot);extra=copy.deepcopy(bad['records'][1]);extra['id']='conflict';extra['segments'][0]['stage']='rem';bad['records'].append(extra)
  with self.assertRaises(ValueError):self.sync(bad)
 def test_only_complete_day_can_be_reconciled(self):
  self.sync();trimmed=copy.deepcopy(self.snapshot);trimmed['window_start']='2026-11-04T00:00:00+09:00';trimmed['records']=[]
  self.sync(trimmed);self.assertEqual(len(list_sessions('alice',self.db)),1)

 def test_stale_snapshot_rejected(self):
  self.sync();old=copy.deepcopy(self.snapshot);old['window_end']='2026-11-06T23:00:00Z'
  with self.assertRaises(ValueError):self.sync(old)
 def test_expired_token_rejected(self):
  with closing(health_sync.database(self.db)) as db, db:db.execute("UPDATE health_connections SET expires_at='2020-01-01T00:00:00+00:00'")
  with self.assertRaises(AuthenticationError):self.sync()
 def test_token_is_stored_as_hash(self):
  with closing(health_sync.database(self.db)) as db, db:
   row=db.execute('SELECT token_hash FROM health_connections').fetchone()
   self.assertNotEqual(row['token_hash'],self.token)
 def test_real_source_deletion_hides_only_synced_day(self):
  self.token=health_sync.pair('alice','health_connect','watch','Watch',path=self.db)['sync_token'];self.snapshot['provider']='health_connect'
  self.sync();changed=copy.deepcopy(self.snapshot)
  second=copy.deepcopy(changed['records'][0]);second['id']='another-night';second['start']='2026-11-05T23:00:00+09:00';second['end']='2026-11-06T07:00:00+09:00';second['segments']=[{'start':second['start'],'end':second['end'],'stage':'core'}]
  changed['records']=[second]
  partial=self.sync(changed)
  self.assertEqual(partial['removed_sessions'],0)
  self.assertEqual(len(list_sessions('alice',self.db)),2)
  changed['complete_snapshot']=True;result=self.sync(changed)
  self.assertEqual(result['removed_sessions'],1);self.assertEqual(len(list_sessions('alice',self.db)),1)

class HealthAPITests(unittest.TestCase):
 # Reuse the same isolated fixture, but test the actual HTTP contract.
 def setUp(self):
  HealthSyncTests.setUp(self)
  import health_records
  import api
  from fastapi.testclient import TestClient
  self.module=health_records;self.original=health_records.DB_PATH;health_records.DB_PATH=self.db
  self.addCleanup(setattr,health_records,'DB_PATH',self.original)
  self.client=TestClient(api.app)
 def tearDown(self):
  self.client.close();self.module.DB_PATH=self.original;HealthSyncTests.tearDown(self)
 def test_http_sync_contract(self):
  response=self.client.post('/mobile/health-sync',headers={'Authorization':'Bearer '+self.token},json=self.snapshot)
  self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['added_sessions'],1)
 def test_sync_token_cannot_log_in_to_account(self):
  response=self.client.get('/auth/me',headers={'Authorization':'Bearer '+self.token})
  self.assertEqual(response.status_code,401)
 def test_invalid_native_token_is_rejected(self):
  response=self.client.post('/mobile/health-sync',headers={'Authorization':'Bearer not-a-valid-token'},json=self.snapshot)
  self.assertEqual(response.status_code,401)

 def test_auto_advice_is_queued_once_for_new_night(self):
  from unittest.mock import patch
  self.token=health_sync.pair('alice','healthkit','watch','Watch',True,path=self.db)['sync_token']
  with patch('health_sync.auto_advice') as generated:
   first=self.client.post('/mobile/health-sync',headers={'Authorization':'Bearer '+self.token},json=self.snapshot)
   second=self.client.post('/mobile/health-sync',headers={'Authorization':'Bearer '+self.token},json=self.snapshot)
  self.assertTrue(first.json()['advice_queued']);self.assertFalse(second.json()['advice_queued']);self.assertEqual(generated.call_count,1)
 def test_malformed_record_returns_400(self):
  data=copy.deepcopy(self.snapshot);data['records']=['not-an-object']
  response=self.client.post('/mobile/health-sync',headers={'Authorization':'Bearer '+self.token},json=data)
  self.assertEqual(response.status_code,400)
 def test_account_change_revokes_native_token(self):
  from unittest.mock import patch
  import sleep_accounts
  with patch('sleep_accounts._verify_account_action',return_value=({'username':'alice','salt':'test','password_hash':'test'},None)):
   sleep_accounts.update_account('alice','not-used',new_username='alice-new',db_path=self.db)
  response=self.client.post('/mobile/health-sync',headers={'Authorization':'Bearer '+self.token},json=self.snapshot)
  self.assertEqual(response.status_code,401)

 def web_headers(self,account='alice'):
  from datetime import timedelta
  from health_records import digest
  token='synthetic-web-login-token-for-'+account
  with closing(connect(self.db)) as db, db:
   db.execute('INSERT OR REPLACE INTO auth_tokens VALUES(?,?,?)',(digest(token),account,(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()))
  return {'Authorization':'Bearer '+token}
 def test_connection_lifecycle_is_account_scoped(self):
  alice=self.web_headers();bob=self.web_headers('bob')
  self.assertFalse(self.client.get('/watch/health/connection',headers=bob).json()['connected'])
  response=self.client.post('/watch/health/connection',headers=alice,json={'provider':'health_connect','source_id':'galaxy','source_name':'Samsung Health'})
  self.assertEqual(response.status_code,200,response.text)
  self.assertEqual(response.json()['account_id'],'alice')
  replacement=response.json()['sync_token']
  status=self.client.get('/watch/health/connection',headers=alice)
  self.assertEqual(status.status_code,200)
  self.assertEqual(status.json()['connection']['provider'],'health_connect')
  self.assertNotIn('sync_token',status.json()['connection'])
  self.assertFalse(self.client.get('/watch/health/connection',headers=bob).json()['connected'])
  self.assertEqual(self.client.delete('/watch/health/connection',headers=bob).status_code,200)
  self.assertTrue(self.client.get('/watch/health/connection',headers=alice).json()['connected'])
  with self.assertRaises(AuthenticationError):health_sync.synchronize(self.token,self.snapshot,self.db)
  self.assertEqual(self.client.delete('/watch/health/connection',headers=alice).status_code,200)
  self.assertFalse(self.client.get('/watch/health/connection',headers=alice).json()['connected'])
  with closing(health_sync.database(self.db)) as db:
   with self.assertRaises(AuthenticationError):health_sync.authenticated(db,replacement)
 def test_connection_endpoints_require_web_authentication(self):
  payload={'provider':'healthkit','source_id':'watch','source_name':'Watch'}
  for headers in ({},{'Authorization':'Bearer '+self.token}):
   for method in ('get','post','delete'):
    with self.subTest(method=method,headers_present=bool(headers)):
     kwargs={'headers':headers}
     if method=='post':kwargs['json']=payload
     self.assertEqual(getattr(self.client,method)('/watch/health/connection',**kwargs).status_code,401)
 def test_web_login_token_cannot_upload_health_records(self):
  response=self.client.post('/mobile/health-sync',headers=self.web_headers(),json=self.snapshot)
  self.assertEqual(response.status_code,401)
 def test_invalid_connection_request_keeps_current_connection(self):
  response=self.client.post('/watch/health/connection',headers=self.web_headers(),json={'provider':'unsupported','source_id':'watch','source_name':'Watch'})
  self.assertEqual(response.status_code,422)
  result=self.client.post('/mobile/health-sync',headers={'Authorization':'Bearer '+self.token},json=self.snapshot)
  self.assertEqual(result.status_code,200,result.text)
 def test_legacy_api_remains_available_with_health_connection(self):
  alice=self.web_headers()
  self.assertEqual(self.client.get('/health').status_code,200)
  self.assertEqual(self.client.get('/auth/me',headers=alice).json()['user']['id'],'alice')
  synced=self.client.post('/mobile/health-sync',headers={'Authorization':'Bearer '+self.token},json=self.snapshot)
  self.assertEqual(synced.status_code,200,synced.text)
  sid=synced.json()['analysis_ids'][0]
  self.assertEqual(self.client.get('/watch/sessions',headers=alice).status_code,200)
  self.assertEqual(self.client.get('/watch/sessions/'+sid,headers=alice).status_code,200)
  self.assertEqual(self.client.get('/watch/sessions/'+sid,headers=self.web_headers('bob')).status_code,404)
  self.assertEqual(self.client.delete('/watch/sessions/'+sid,headers=alice).status_code,200)
  self.assertEqual(list_sessions('alice',self.db),[])
  self.assertEqual(self.client.post('/auth/logout',headers=alice).status_code,200)
  self.assertEqual(self.client.get('/auth/me',headers=alice).status_code,401)


class LegacyAccountTests(unittest.TestCase):
 def test_account_change_without_health_schema_still_works(self):
  from sleep_accounts import register,login,current_user,update_account
  with tempfile.TemporaryDirectory() as directory:
   db_path=Path(directory)/'legacy.sqlite3'
   account=register('legacy-user','synthetic-password-123',db_path)
   old=login('legacy-user','synthetic-password-123',db_path)['token']
   with closing(connect(db_path)) as db:
    self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='health_connections'").fetchone())
   updated=update_account(account['id'],'synthetic-password-123',new_username='legacy-renamed',db_path=db_path)
   self.assertTrue(updated['reauthentication_required'])
   with self.assertRaises(AuthenticationError):current_user(old,db_path)
   new=login('legacy-renamed','synthetic-password-123',db_path)['token']
   self.assertEqual(current_user(new,db_path)['id'],account['id'])

if __name__=='__main__':unittest.main()
