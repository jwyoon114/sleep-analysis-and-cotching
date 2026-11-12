"""Opt-in real HTTP checks: standalone demo, no real API/DB/AI involved."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
from threading import Thread
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


@unittest.skipUnless(os.getenv('DALJAM_RUN_DEMO_HTTP') == '1', 'Build standalone web and opt into local demo HTTP tests')
class DemoHTTPTests(unittest.TestCase):
    def test_demo_isolation_and_normal_mode_preserved(self):
        node = os.getenv('DALJAM_TEST_NODE') or shutil.which('node')
        server = ROOT / 'sleep_frontend/.next/standalone/server.js'
        self.assertTrue(node and server.is_file(), 'Build standalone first')
        shutil.copytree(ROOT / 'sleep_frontend/public', server.parent / 'public', dirs_exist_ok=True)
        shutil.copytree(ROOT / 'sleep_frontend/.next/static', server.parent / '.next/static', dirs_exist_ok=True)
        upstream_requests = []

        class Stub(BaseHTTPRequestHandler):
            def do_GET(self):
                upstream_requests.append((self.command, self.path))
                body = json.dumps({'status':'synthetic-upstream'}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        upstream = ThreadingHTTPServer(('127.0.0.1', 0), Stub)
        Thread(target=upstream.serve_forever, daemon=True).start()
        opener = urllib.request.build_opener(NoRedirect())
        env = {k:v for k,v in os.environ.items() if not k.startswith(('PG','OPENAI_')) and k not in {'DATABASE_URL','SLEEP_DB_PATH','SLEEP_DB_BACKEND'}}
        env.update(HOSTNAME='127.0.0.1', NEXT_TELEMETRY_DISABLED='1', NODE_ENV='production',
                   SLEEP_API_URL=f'http://127.0.0.1:{upstream.server_port}')
        process = None
        with tempfile.TemporaryDirectory(prefix='daljam-demo-http-') as folder:
            log = open(Path(folder) / 'server.log', 'wb')

            def request(base, path, method='GET', headers=None, body=None):
                req = urllib.request.Request(base + path, data=body, method=method, headers=headers or {})
                try:
                    response = opener.open(req, timeout=10)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    return response.status, response.headers, response.read() if method != 'HEAD' else b''

            def start(demo, launcher=True):
                port = free_port()
                current = {**env, 'PORT':str(port), 'DALJAM_DEMO_ONLY':'1' if demo else '0'}
                command = [node, str(ROOT / 'deploy/start-demo.mjs'), str(server)] if demo and launcher else [node, str(server)]
                child = subprocess.Popen(command, cwd=ROOT, env=current, stdout=log, stderr=subprocess.STDOUT)
                base = f'http://127.0.0.1:{port}'
                deadline = time.monotonic() + 60
                while True:
                    try:
                        if request(base, '/api/demo-health')[0] in (200, 404):
                            return child, base
                    except (OSError, urllib.error.URLError):
                        pass
                    if child.poll() is not None or time.monotonic() > deadline:
                        if child.poll() is None:
                            child.terminate()
                            child.wait(timeout=10)
                        self.fail('Standalone server failed to start')
                    time.sleep(.2)

            def stop(child):
                child.terminate()
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()

            try:
                process, base = start(True)
                for path in ['/', '/?demo=0', '/?demo=2', '/?demo=0&demo=1']:
                    status, headers, _ = request(base, path)
                    self.assertEqual(status, 307, path)
                    self.assertEqual(urllib.parse.urlsplit(headers['Location']).query, 'demo=1')
                    self.assertIn('no-store', headers['Cache-Control'])
                status, _, page = request(base, '/?demo=1')
                self.assertEqual(status, 200)
                self.assertIn('달잠 체험 버전'.encode(), page)
                asset = re.search(r'src="(/_next/static/[^"]+)"', page.decode()).group(1)
                for path in [asset, '/icons/app-192.png', '/offline.html', '/sw.js', '/manifest.webmanifest']:
                    self.assertEqual(request(base, path)[0], 200, path)
                status, headers, body = request(base, '/api/demo-health')
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body), {'status':'ok','mode':'demo','data_collection':False})
                auth = {'Cookie':'sleep_session=synthetic-cookie', 'Authorization':'Bearer ' + 'a'*64,
                        'Origin':base, 'Content-Type':'application/json'}
                routes = ['/api/sleep/auth/register', '/api/sleep/auth/login', '/api/sleep/auth/me',
                          '/api/sleep/analyze', '/api/sleep/watch/import', '/api/sleep/watch/sessions',
                          '/api/sleep/coach', '/api/sleep/watch/health/connection', '/api/sleep/watch/trash',
                          '/api/mobile/health-sync', '/api/sleep/health', '/api/future-data-route']
                for route in routes:
                    for method in ['GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS']:
                        status, headers, body = request(base, route+'?demo=0', method, auth,
                            b'{}' if method in {'POST','PUT','PATCH','DELETE'} else None)
                        self.assertEqual(status, 403, (route, method))
                        self.assertIn('no-store', headers['Cache-Control'])
                        self.assertIsNone(headers.get('Set-Cookie'))
                        if method != 'HEAD':
                            self.assertEqual(json.loads(body)['detail']['code'], 'demo_only')
                self.assertEqual(upstream_requests, [], 'Demo must never forward to API')
                stop(process)
                process = None
                # Prove the route guards themselves block a configured upstream,
                # even when the demo-only launcher is bypassed in this test.
                process, base = start(True, launcher=False)
                status, _, body = request(base, '/api/sleep/auth/me', headers=auth)
                self.assertEqual(status, 403)
                self.assertEqual(json.loads(body)['detail']['code'], 'demo_only')
                status, _, _ = request(base, '/api/mobile/health-sync', 'POST', auth, b'{}')
                self.assertEqual(status, 403)
                self.assertEqual(upstream_requests, [])
                stop(process)
                process = None
                # Same built output, different runtime flag: no demo banner/redirect,
                # and original proxy still forwards to an isolated synthetic server.
                process, base = start(False)
                status, _, page = request(base, '/')
                self.assertEqual(status, 200)
                self.assertNotIn('달잠 체험 버전'.encode(), page)
                self.assertEqual(request(base, '/api/demo-health')[0], 404)
                status, _, body = request(base, '/api/sleep/health')
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body)['status'], 'synthetic-upstream')
                self.assertEqual(upstream_requests, [('GET','/health')])
            finally:
                if process is not None:
                    stop(process)
                log.close()
                upstream.shutdown()
                upstream.server_close()
