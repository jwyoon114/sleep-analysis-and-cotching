"""Consent-based, read-only native health synchronization. Never store raw exports."""
from contextlib import closing
from datetime import datetime, timedelta, timezone, time
import json
import secrets
from zoneinfo import ZoneInfo
from health_records import connect, digest, STAGES
from sleep_accounts import AuthenticationError

PROVIDERS = {'healthkit': 'Apple 건강', 'health_connect': 'Health Connect'}

def database(path=None):
    db = connect(path)
    db.executescript("""
    CREATE TABLE IF NOT EXISTS health_connections(
      account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
      token_hash TEXT UNIQUE NOT NULL, provider TEXT NOT NULL, source_id TEXT NOT NULL,
      source_name TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
      last_synced_at TEXT, auto_coach INTEGER NOT NULL DEFAULT 0, advice_status TEXT);
    CREATE TABLE IF NOT EXISTS health_sync_sessions(
      account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
      day TEXT NOT NULL, session_id TEXT UNIQUE NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
      PRIMARY KEY(account_id, day));
    """)
    if 'last_window_end' not in {row['name'] for row in db.execute('PRAGMA table_info(health_connections)')}:
        db.execute('ALTER TABLE health_connections ADD COLUMN last_window_end TEXT')
        db.commit()
    db.execute('CREATE TABLE IF NOT EXISTS health_advice_jobs(account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE, PRIMARY KEY(account_id,session_id))')
    db.commit()
    return db

def status(account, path=None):
    with closing(database(path)) as db:
        row = db.execute('SELECT provider,source_name,last_synced_at,expires_at,auto_coach,advice_status FROM health_connections WHERE account_id=?', (account,)).fetchone()
        return {'connected': row is not None, 'connection': dict(row) if row else None}

def pair(account, provider, source_id, source_name, auto_coach=False, path=None):
    if provider not in PROVIDERS or not isinstance(source_id,str) or not 1 <= len(source_id) <= 300 or not isinstance(source_name,str) or not 1 <= len(source_name) <= 120:
        raise ValueError('건강 데이터 제공 앱을 선택하세요.')
    token = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    with closing(database(path)) as db, db:
        db.execute('INSERT OR REPLACE INTO health_connections(account_id,token_hash,provider,source_id,source_name,created_at,expires_at,last_synced_at,auto_coach,advice_status) VALUES(?,?,?,?,?,?,?,?,?,?)',
                   (account,digest(token),provider,source_id,source_name,now.isoformat(),(now+timedelta(days=180)).isoformat(),None,int(auto_coach),None))
    return {'sync_token':token, 'account_id':account}

def disconnect(account, path=None):
    with closing(database(path)) as db, db:
        db.execute('DELETE FROM health_connections WHERE account_id=?',(account,))

def authenticated(db, token):
    if not token or len(token)>200:
        raise AuthenticationError('건강앱 연결을 다시 설정해 주세요.')
    row=db.execute('SELECT * FROM health_connections WHERE token_hash=? AND expires_at>?', (digest(token),datetime.now(timezone.utc).isoformat())).fetchone()
    if not row:
        raise AuthenticationError('건강앱 연결이 해제되었거나 만료되었습니다. 다시 연결해 주세요.')
    return dict(row)

def stamp(value):
    try:
        t=datetime.fromisoformat(value.replace('Z','+00:00'))
        if t.utcoffset() is None: raise ValueError()
        return t.astimezone(timezone.utc)
    except (ValueError,TypeError,AttributeError,OverflowError) as error:
        raise ValueError('시각은 시간대가 있는 ISO 8601 형식이어야 합니다.') from error

def normalize(snapshot, connection):
    if snapshot.get('provider')!=connection['provider'] or snapshot.get('source_id')!=connection['source_id']:
        raise ValueError('연결한 건강앱의 데이터 출처와 일치하지 않습니다.')
    tz=ZoneInfo(snapshot['timezone'])
    first,last=stamp(snapshot['window_start']),stamp(snapshot['window_end'])
    if not timedelta(0)<last-first<=timedelta(days=31) or last>datetime.now(timezone.utc)+timedelta(minutes=10):
        raise ValueError('동기화 범위는 과거 최대 31일이어야 합니다.')
    records=snapshot.get('records')
    if not isinstance(records,list) or len(records)>20000: raise ValueError('동기화 기록 수가 너무 많습니다.')
    days={}; seen=set(); ignored=0; count=0
    for record in records:
        if not isinstance(record,dict): raise ValueError('각 건강 기록은 객체여야 합니다.')
        rid=record.get('id')
        if not isinstance(rid,str) or not 1<=len(rid)<=300 or rid in seen: raise ValueError('건강 기록 ID가 없거나 중복되었습니다.')
        seen.add(rid)
        start,end=stamp(record['start']),stamp(record['end'])
        if not timedelta(0)<end-start<=timedelta(days=2) or start<first-timedelta(days=2) or end>last or end<=first:
            raise ValueError('건강 기록 시각이 동기화 범위를 벗어납니다.')
        segments=record.get('segments')
        if not isinstance(segments,list): raise ValueError('수면 구간 목록이 필요합니다.')
        if not segments: ignored+=1
        for segment in segments:
            count+=1
            if count>30000: raise ValueError('수면 구간이 너무 많습니다.')
            a,b=stamp(segment['start']),stamp(segment['end']); stage=segment.get('stage')
            if stage not in STAGES or not start<=a<b<=end: raise ValueError('수면 단계 또는 시각이 올바르지 않습니다.')
            while a<b:
                local=a.astimezone(tz)
                day=local.date() if local.hour>=12 else local.date()-timedelta(days=1)
                boundary=datetime.combine(day+timedelta(days=1),time(12),tz).astimezone(timezone.utc)
                stop=min(b,boundary)
                days.setdefault(day.isoformat(),[]).append((a,stop,stage))
                a=stop
    normalized={}
    for day,segments in days.items():
        # Sweep interval endpoints: broad 'asleep' samples must not double-count
        # the detailed stages emitted by the same source.
        events={}
        for a,b,s in segments:
            events.setdefault(a,[]).append((s,1));events.setdefault(b,[]).append((s,-1))
        active={s:0 for s in STAGES}; result=[]; previous=None
        for instant,changes in sorted(events.items()):
            if previous is not None and previous<instant:
                detailed=[s for s in ('core','deep','rem','wake') if active[s]>0]
                if len(detailed)>1: raise ValueError('서로 다른 수면 단계가 겹칩니다. 건강앱의 원본 기록을 확인하세요.')
                stage=detailed[0] if detailed else 'unspecified' if active['unspecified'] else None
                if stage:
                    a=previous.astimezone(tz).isoformat(); b=instant.astimezone(tz).isoformat()
                    if result and result[-1]['stage']==stage and result[-1]['end']==a: result[-1]['end']=b
                    else: result.append({'start':a,'end':b,'stage':stage})
            for stage,delta in changes: active[stage]+=delta
            previous=instant
        if not result: continue
        for s in result: s['minutes']=(stamp(s['end'])-stamp(s['start'])).total_seconds()/60
        totals={s:sum(r['minutes'] for r in result if r['stage']==s) for s in sorted(STAGES)}
        asleep=sum(v for k,v in totals.items() if k!='wake')
        duration=(stamp(result[-1]['end'])-stamp(result[0]['start'])).total_seconds()/60
        normalized[day]={'data_type':'wearable','source':connection['source_name'],'timezone':snapshot['timezone'],
          'start':result[0]['start'],'end':result[-1]['end'],'segments':result,'stage_minutes':totals,
          'recorded_minutes':duration,'asleep_minutes':asleep,'awake_minutes':totals['wake'],
          'unrecorded_minutes':max(0,duration-sum(totals.values())), 'session_asleep_ratio_percent':asleep/duration*100,
          'wake_segment_count':sum(s['stage']=='wake' for s in result),'vitals_summary':[],'exported_summary':None,
          'warnings':['자동 연결 기록은 현지 정오부터 다음 정오까지 한 묶음으로 표시합니다.','건강앱에서 기록이 수정되면 분석도 갱신됩니다. 이전 AI 조언은 생성 당시 기록을 기준으로 합니다.'],
          'interpretation':'건강앱에 저장된 기기 추정 수면 기록입니다.',
          'health_sync':{'provider':connection['provider'],'source_id':connection['source_id'],'day':day}}
    return normalized,first,last,ignored

def synchronize(token, snapshot, path=None):
    with closing(database(path)) as db:
        # Hold the write transaction through token validation: revocation and
        # concurrent snapshots cannot race and restore an old connection.
        with db:
            db.execute('BEGIN IMMEDIATE')
            connection=authenticated(db,token); account=connection['account_id']
            records,first,last,ignored=normalize(snapshot,connection)
            if connection.get('last_window_end') and last<stamp(connection['last_window_end']):
                raise ValueError('이전 동기화보다 오래된 스냅샷입니다. 최신 기록을 다시 가져오세요.')
            now=datetime.now(timezone.utc).isoformat(); added=updated=skipped=removed=0; ids=[]
            for day,session in sorted(records.items()):
                sid=digest(account+'\0health-sync\0'+day)
                if db.execute("SELECT 1 FROM permanent_deletions WHERE kind='session' AND record_id=? AND subject=?",(sid,account)).fetchone() or db.execute('SELECT 1 FROM trash_sessions WHERE session_id=?',(sid,)).fetchone():
                    skipped+=1;continue
                session.update(analysis_id=sid,subject=account)
                payload=json.dumps(session,ensure_ascii=False,sort_keys=True)
                old=db.execute('SELECT payload FROM sessions WHERE id=? AND subject=?',(sid,account)).fetchone()
                if old and json.loads(old['payload'])==session: ids.append(sid);continue
                if old:
                    db.execute('UPDATE sessions SET start=?,end=?,payload=? WHERE id=?',(session['start'],session['end'],payload,sid));updated+=1
                    db.execute('DELETE FROM stages WHERE session_id=?',(sid,))
                else:
                    db.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(sid,account,session['start'],session['end'],payload))
                    db.execute('INSERT INTO session_created VALUES(?,?)',(sid,now));added+=1
                db.executemany('INSERT INTO stages VALUES(?,?,?,?,?,?)',[(sid,i,s['start'],s['end'],s['stage'],s['minutes']) for i,s in enumerate(session['segments'])])
                db.execute('INSERT OR REPLACE INTO health_sync_sessions VALUES(?,?,?)',(account,day,sid));ids.append(sid)
            # Only a complete snapshot for the chosen source may hide missing
            # native records. Manual uploads are never touched.
            for row in list(db.execute('SELECT h.day,s.id,s.start,s.end,s.payload FROM health_sync_sessions h JOIN sessions s ON s.id=h.session_id WHERE h.account_id=?',(account,))) if records and not ignored and connection['provider']=='health_connect' else []:
                meta=json.loads(row['payload']).get('health_sync',{})
                if row['day'] not in records and meta.get('provider')==connection['provider'] and meta.get('source_id')==connection['source_id'] and first<=stamp(row['start']) and stamp(row['end'])<=last:
                    removed+=db.execute('INSERT OR IGNORE INTO trash_sessions VALUES(?,?,?)',(row['id'],account,now)).rowcount
            db.execute('UPDATE health_connections SET last_synced_at=?,last_window_end=? WHERE account_id=?',(now,last.isoformat(),account))
        return {'added_sessions':added,'updated_sessions':updated,'skipped_deleted':skipped,'removed_sessions':removed,'ignored_incomplete':ignored,'analysis_ids':ids,'last_synced_at':now,'account_id':account,'auto_coach':bool(connection['auto_coach'])}

def auto_advice(account, ids):
    """At most the newest unseen night per sync; never block/undo saved records."""
    if not ids: return
    import coaching_service
    from health_records import get_owned_session
    try:
        rows=[get_owned_session(i,account) for i in ids]
        rows=[r for r in rows if r]
        if not rows: return
        newest=max(rows,key=lambda r:r['end'])
        if coaching_service.list_coaching(account,newest['analysis_id']): return
        with closing(database()) as db,db:
            connection=db.execute('SELECT auto_coach FROM health_connections WHERE account_id=?',(account,)).fetchone()
            if not connection or not connection['auto_coach']: return
            if not db.execute('INSERT OR IGNORE INTO health_advice_jobs VALUES(?,?)',(account,newest['analysis_id'])).rowcount: return
        # generate() applies the existing account/global limits and ownership checks.
        coaching_service.generate(account,newest['analysis_id'],{'caffeine':'미입력','regularity':'미입력','satisfaction':'미입력','age_group':'미입력'})
        message='최신 기록의 AI 조언을 저장했어요.'
    except Exception:
        message='기록은 저장했지만 AI 조언을 만들지 못했어요. AI 코칭 화면에서 다시 요청할 수 있어요.'
    with closing(database()) as db,db:
        db.execute('UPDATE health_connections SET advice_status=? WHERE account_id=?',(message,account))
