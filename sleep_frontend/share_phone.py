"""Share the authenticated Next.js app through a verified, explicitly started tunnel."""
import argparse
import ctypes
import hashlib
import html
import json
import msvcrt
from pathlib import Path
import re
import subprocess
import time
import urllib.request
import webbrowser
import launch_web as web

ROOT=Path(__file__).resolve().parent
DIRECTORY=ROOT/'.runtime'
STATE=DIRECTORY/'phone-share.json'
VERSION='2026.10.7'
SHA256='2493dbc168923bb3e59e5e7716f71deced92992eea9acd6e9d74f84ac7751343'
PATTERN=re.compile(r'https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com')

def load():
    try:
        state=json.loads(STATE.read_text(encoding='utf-8'))
        return state if state.get('root')==str(ROOT) else None
    except (OSError,ValueError): return None

def stop():
    state=load()
    if state and web.alive(state.get('tunnel')):
        item=state['tunnel']
        handle=web.kernel.OpenProcess(0x1000|0x0001,False,item['pid'])
        if handle:
            try:
                if web.signature(handle)==item['created']:
                    if not web.kernel.TerminateProcess(handle,0): raise OSError('휴대폰 공유 연결을 중지하지 못했습니다.')
            finally: web.kernel.CloseHandle(handle)
    STATE.unlink(missing_ok=True)

def connection_page(url):
    if not PATTERN.fullmatch(url): raise ValueError('공유 주소 형식을 확인하세요.')
    qr=''
    try:
        import qrcode
        qrcode.make(url).save(DIRECTORY/'phone-qr.png')
        qr='<img src="phone-qr.png" width="240" height="240" alt="휴대폰 접속 QR 코드">'
    except ImportError: pass
    page='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>달잠 휴대폰 연결</title><style>body{font-family:system-ui;background:#f8f8fb;color:#383044;margin:30px;line-height:1.9}main{max-width:620px;margin:auto}a{color:#695298;word-break:break-all}img{display:block;margin:20px 0}h2{margin-top:28px}</style><main><h1>달잠을 휴대폰에서 열어요</h1>'''+qr+f'<p><a href="{html.escape(url)}">{html.escape(url)}</a></p>'+'''<p>휴대폰 카메라로 QR 코드를 스캔하거나 위 주소를 휴대폰 브라우저에서 여세요. 로그인 후 기존 수면 기록과 코칭을 사용할 수 있습니다.</p><h2>아이폰</h2><p>Safari → 공유 → 홈 화면에 추가 → ‘웹 앱으로 열기’가 표시되면 켜기 → 추가</p><h2>안드로이드</h2><p>Chrome 또는 삼성 인터넷 → 메뉴 → 앱 설치 / 홈 화면에 추가</p><h2>연결 안내</h2><p>서버 PC·인터넷·달잠 웹앱·휴대폰 공유가 켜져 있어야 합니다. 공유를 새로 시작해 주소가 바뀌면 새 주소로 다시 설치하세요. 바탕화면 ‘달잠 휴대폰 공유 중지’는 휴대폰 접속만 중지합니다.</p><p>취침·기상 알람은 서버 PC에서 울립니다. 휴대폰 기본 알람에는 등록되지 않습니다. AI 코칭은 API 잔액과 사용 한도에 따라 별도 오류가 발생할 수 있습니다.</p></main></html>'''
    destination=DIRECTORY/'phone-connect.html'
    destination.write_text(page.replace('달잠 휴대폰 공유 중지','달잠 웹앱 휴대폰 공유 종료'),encoding='utf-8')
    (DIRECTORY/'phone-url.txt').write_text(url,encoding='utf-8')
    return destination

def start(project,binary=None,open_browser=True):
    DIRECTORY.mkdir(exist_ok=True)
    # Coordinate with desktop start/stop operations.
    with (DIRECTORY/'launcher.lock').open('a+b') as lock:
        lock.seek(0,2)
        if lock.tell()==0: lock.write(b'0');lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        try: web.start(project,False)
        finally:
            lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
    existing=load()
    if existing and web.alive(existing.get('tunnel')) and PATTERN.fullmatch(existing.get('url','')):
        page=connection_page(existing['url'])
        if open_browser: webbrowser.open(page.as_uri())
        return existing['url']
    stop()
    if binary is None:
        binary=project/'.sleep-share'/f'cloudflared-{VERSION}.exe'
        if not binary.exists():
            binary=ROOT/'tools/bin'/f'cloudflared-{VERSION}.exe'
        if not binary.exists():
            subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'tools/download-cloudflared.ps1')],check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    binary=binary.resolve(strict=True)
    if hashlib.sha256(binary.read_bytes()).hexdigest()!=SHA256:
        raise RuntimeError('공유 도구의 무결성 확인에 실패했습니다. 실행하지 않았습니다.')
    config=DIRECTORY/'phone-tunnel.yml'
    config.write_text('loglevel: info\n',encoding='utf-8')
    log_path=DIRECTORY/'phone-tunnel.log'
    with log_path.open('wb') as log:
        process=subprocess.Popen([str(binary),'tunnel','--config',str(config),'--no-autoupdate','--edge-ip-version','4','--protocol','http2','--url',web.URL],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    created=web.process_signature(process.pid)
    if created is None:
        process.terminate()
        raise RuntimeError('공유 도구가 시작되지 않았습니다.')
    state={'root':str(ROOT),'tunnel':{'pid':process.pid,'created':created}}
    STATE.write_text(json.dumps(state),encoding='utf-8')
    try:
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            if process.poll() is not None: raise RuntimeError('휴대폰 공유 연결이 종료되었습니다.')
            matches=PATTERN.findall(log_path.read_text(encoding='utf-8',errors='replace'))
            if matches:
                state['url']=matches[-1]
                STATE.write_text(json.dumps(state),encoding='utf-8')
                page=connection_page(state['url'])
                if open_browser: webbrowser.open(page.as_uri())
                return state['url']
            time.sleep(.3)
        raise RuntimeError('공유 주소를 받지 못했습니다. 인터넷 연결을 확인하세요.')
    except BaseException:
        stop()
        raise

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--backend-project',type=Path,required=True)
    parser.add_argument('--cloudflared',type=Path)
    parser.add_argument('--stop',action='store_true')
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    try:
        DIRECTORY.mkdir(exist_ok=True)
        with (DIRECTORY/'phone-share.lock').open('a+b') as lock:
            lock.seek(0,2)
            if lock.tell()==0:lock.write(b'0');lock.flush()
            lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            try:
                if args.stop: stop()
                else: print(start(args.backend_project.resolve(strict=True),args.cloudflared,not args.no_browser))
            finally:
                lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
    except Exception as error:
        ctypes.windll.user32.MessageBoxW(0,str(error),'달잠 휴대폰 연결',0x10)
        raise SystemExit(1)
