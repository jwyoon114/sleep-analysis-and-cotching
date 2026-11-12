"""Account-owned daily PC alarms; persisted claims prevent duplicate ringing."""
from app_database import begin_write
from contextlib import closing
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import health_records

_lock = threading.Lock()
_worker = None

def connect(db_path=None):
    db = health_records.connect(db_path)
    if getattr(db, 'is_postgres', False):
        return db
    db.executescript('''
    CREATE TABLE IF NOT EXISTS sleep_alarm_settings(
      account_id TEXT PRIMARY KEY REFERENCES accounts(id), bedtime TEXT NOT NULL,
      wake_time TEXT NOT NULL, timezone TEXT NOT NULL, enabled INTEGER NOT NULL,
      coaching_id TEXT, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS sleep_alarm_fires(
      account_id TEXT NOT NULL REFERENCES accounts(id), kind TEXT NOT NULL,
      local_date TEXT NOT NULL, fired_at TEXT NOT NULL,
      PRIMARY KEY(account_id,kind,local_date));
    ''')
    return db

def get_settings(account_id, db_path=None):
    with closing(connect(db_path)) as db:
        row = db.execute('SELECT * FROM sleep_alarm_settings WHERE account_id=?',(account_id,)).fetchone()
        settings = dict(row) if row else dict(bedtime='23:00',wake_time='07:00',timezone='Asia/Seoul',enabled=False,coaching_id=None)
        settings.pop('account_id',None)
        settings['enabled'] = bool(settings['enabled'])
        return settings | {'desktop_available': desktop_available()}

def desktop_available():
    return os.name == 'nt' and os.getenv('SLEEP_DESKTOP_ALARMS','1') == '1'

def save_settings(account_id, bedtime, wake_time, timezone_name, enabled, coaching_id=None, db_path=None):
    for value in (bedtime,wake_time):
        if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',value):
            raise ValueError('시간은 HH:MM 형식으로 입력하세요.')
    if bedtime == wake_time:
        raise ValueError('취침과 기상 시간을 서로 다르게 설정하세요.')
    try: ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError): raise ValueError('지원하지 않는 시간대입니다.') from None
    if enabled and not desktop_available():
        raise ValueError('이 서버에서는 PC 알람을 사용할 수 없습니다. Windows PC 실행기를 사용하세요.')
    with closing(connect(db_path)) as db, db:
        if not db.execute('SELECT 1 FROM accounts WHERE id=?',(account_id,)).fetchone():
            raise ValueError('계정을 확인하세요.')
        if coaching_id and not db.execute('''SELECT 1 FROM coaching c JOIN sessions s ON s.id=c.session_id
          WHERE c.id=? AND c.account_id=? AND s.subject=?
          AND NOT EXISTS(SELECT 1 FROM trash_coaching WHERE coaching_id=c.id)
          AND NOT EXISTS(SELECT 1 FROM trash_sessions WHERE session_id=s.id)''',(coaching_id,account_id,account_id)).fetchone():
            raise ValueError('선택한 AI 코칭을 찾을 수 없습니다.')
        db.execute('''INSERT INTO sleep_alarm_settings VALUES(?,?,?,?,?,?,?)
          ON CONFLICT(account_id) DO UPDATE SET bedtime=excluded.bedtime,wake_time=excluded.wake_time,
          timezone=excluded.timezone,enabled=excluded.enabled,coaching_id=excluded.coaching_id,updated_at=excluded.updated_at''',
          (account_id,bedtime,wake_time,timezone_name,int(enabled),coaching_id,datetime.now(timezone.utc).isoformat()))
    return get_settings(account_id,db_path)

def notify(kind):
    if not desktop_available(): return
    # Only a fixed kind is passed. No usernames, health records or credentials.
    subprocess.Popen([str(Path(getattr(sys,'_base_executable',sys.executable)).resolve()),
                      str(Path(__file__).with_name('sleep_alarm_popup.py')),kind],
                     stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                     creationflags=subprocess.CREATE_NO_WINDOW)

def tick(now=None, db_path=None, notifier=notify):
    now = now or datetime.now(timezone.utc)
    due = []
    with closing(connect(db_path)) as db, db:
        begin_write(db)
        for row in db.execute('SELECT * FROM sleep_alarm_settings WHERE enabled=1'):
            local = now.astimezone(ZoneInfo(row['timezone']))
            # Only the current minute rings; startup/resume never replays old alarms.
            instant = local.replace(second=0,microsecond=0)
            if instant.astimezone(timezone.utc) < datetime.fromisoformat(row['updated_at']): continue
            for kind in ('bedtime','wake_time'):
                if row[kind] != local.strftime('%H:%M'): continue
                inserted = db.execute('INSERT INTO sleep_alarm_fires VALUES(?,?,?,?) ON CONFLICT DO NOTHING',
                    (row['account_id'],kind,local.date().isoformat(),now.isoformat())).rowcount
                if inserted: due.append(kind)
        db.execute('DELETE FROM sleep_alarm_fires WHERE fired_at<?',((now-timedelta(days=90)).isoformat(),))
    for kind in due: notifier(kind)
    return due

def start_worker():
    global _worker
    if not desktop_available(): return
    with _lock:
        if _worker and _worker.is_alive(): return
        def run():
            while True:
                try:
                    if health_records.DB_PATH.exists(): tick()
                except Exception:
                    # A DB temporarily locked/replaced must not kill future alarms.
                    pass
                threading.Event().wait(5)
        _worker = threading.Thread(target=run,name='sleep-alarms',daemon=True)
        _worker.start()
