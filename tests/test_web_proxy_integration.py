"""Opt-in real HTTP checks against the built standalone web and synthetic API."""
import http.cookiejar
import json
import os
from pathlib import Path
import shutil
import re
import socket
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


@unittest.skipUnless(os.getenv('DALJAM_RUN_PROXY_SMOKE') == '1', 'Requires built standalone web and explicit local smoke opt-in')
class WebProxyTests(unittest.TestCase):
    def test_cookie_origin_mobile_limits_and_backend_outage(self):
        node = os.getenv('DALJAM_TEST_NODE') or shutil.which('node')
        dist = os.getenv('DALJAM_TEST_DIST_DIR', '.next')
        self.assertIn(dist, ('.next', '.next-production'))
        server = ROOT / 'sleep_frontend' / dist / 'standalone/server.js'
        self.assertTrue(node and server.is_file(), 'Build standalone web first')
        shutil.copytree(ROOT / 'sleep_frontend/public', server.parent / 'public', dirs_exist_ok=True)
        shutil.copytree(ROOT / 'sleep_frontend' / dist / 'static', server.parent / dist / 'static', dirs_exist_ok=True)
        api_port, web_port = free_port(), free_port()
        base = f'http://127.0.0.1:{web_port}'
        env = {k: v for k, v in os.environ.items() if not k.startswith('PG') and k not in ('DATABASE_URL', 'OPENAI_API_KEY')}
        env.update(SLEEP_DB_BACKEND='sqlite', SLEEP_DESKTOP_ALARMS='0', COACHING_ENGINE='rules',
                   PORT=str(web_port), HOSTNAME='127.0.0.1', SLEEP_API_URL=f'http://127.0.0.1:{api_port}')
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            log = open(Path(directory) / 'servers.log', 'wb')
            db_path = str(Path(directory) / 'synthetic.sqlite3')
            api_command = f'import health_records;from pathlib import Path;health_records.DB_PATH=Path({db_path!r});import uvicorn;uvicorn.run("api:app",host="127.0.0.1",port={api_port},access_log=False)'
            processes = []
            jar = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

            def request(path, method='GET', payload=None, headers=None):
                body = None if payload is None else json.dumps(payload).encode()
                req = urllib.request.Request(base + path, data=body, method=method, headers={'Content-Type': 'application/json', **(headers or {})})
                try:
                    response = opener.open(req, timeout=10)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    # An early 413 can close a still-uploading socket on Windows.
                    # Error assertions need only the received HTTP status.
                    return SimpleNamespace(status=response.status, body=response.read() if response.status < 400 else b'', headers=response.headers)

            try:
                processes.append(subprocess.Popen([sys.executable, '-c', api_command], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT))
                processes.append(subprocess.Popen([node, str(server)], cwd=server.parent, env=env, stdout=log, stderr=subprocess.STDOUT))
                deadline = time.monotonic() + 90
                while True:
                    try:
                        if request('/api/sleep/health').status == 200:
                            break
                    except (OSError, urllib.error.URLError):
                        pass
                    if any(p.poll() is not None for p in processes) or time.monotonic() >= deadline:
                        log.flush()
                        self.fail('Local servers did not become live: ' + (Path(directory) / 'servers.log').read_text(errors='replace')[-2000:])
                    time.sleep(.2)
                page = request('/')
                self.assertEqual(page.status, 200)
                asset = re.search(r'src="(/_next/static/[^"]+)"', page.body.decode()).group(1)
                self.assertEqual(request(asset).status, 200)
                self.assertEqual(request('/offline.html').status, 200)
                self.assertEqual(request('/api/ready').status, 503)  # SQLite is not cloud-ready.
                self.assertEqual(request('/api/sleep/auth/me').status, 401)
                credentials = {'username': 'synthetic-proxy-user', 'password': 'synthetic-proxy-password'}
                self.assertEqual(request('/api/sleep/auth/register', 'POST', credentials).status, 403)
                self.assertEqual(request('/api/sleep/auth/register', 'POST', credentials, {'Origin': base}).status, 201)
                response = request('/api/sleep/auth/login', 'POST', credentials, {'Origin': base})
                self.assertEqual(response.status, 200)
                self.assertNotIn('token', json.loads(response.body))
                self.assertTrue(any(c.name == 'sleep_session' and c.has_nonstandard_attr('HttpOnly') for c in jar))
                self.assertEqual(request('/api/sleep/auth/me').status, 200)
                self.assertEqual(request('/api/sleep/internal-not-allowed').status, 404)
                self.assertEqual(request('/api/mobile/health-sync', 'POST', {}).status, 401)
                # Use an actual oversized body; a false Content-Length can
                # stall Node's HTTP parser before the application is reached.
                self.assertEqual(request('/api/mobile/health-sync', 'POST', {'padding':'a'*(3*1024*1024)}, {'Authorization': 'Bearer ' + 'a' * 64}).status, 413)
                self.assertEqual(request('/api/mobile/health-sync', 'POST', {}, {'Authorization': 'Bearer ' + 'a' * 64}).status, 401)
                self.assertEqual(request('/api/sleep/auth/logout', 'POST', {}, {'Origin': base}).status, 200)
                self.assertFalse(any(c.name == 'sleep_session' for c in jar))
                processes[0].terminate()
                processes[0].wait(timeout=10)
                self.assertEqual(request('/api/ready').status, 503)
                self.assertEqual(request('/api/sleep/health').status, 502)
            finally:
                for process in reversed(processes):
                    if process.poll() is None:
                        process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                log.close()
