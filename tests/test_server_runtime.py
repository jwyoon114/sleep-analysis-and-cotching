"""Synthetic health probes and real child-process lifecycle checks."""
import os
import ast
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import re
import unittest
from unittest.mock import MagicMock, patch

import api
from fastapi.testclient import TestClient
from app_database import DatabaseUnavailable
from deploy.supervisor import run


class ImageSourceTests(unittest.TestCase):
    def test_runtime_copy_contains_transitive_local_python_imports(self):
        root = Path(__file__).resolve().parents[1]
        dockerfile = (root / 'Dockerfile.production').read_text(encoding='utf-8').replace('\\\n', ' ')
        copied = set(re.search(r'COPY (api\.py.*?) \./', dockerfile, re.S).group(1).split())
        for filename in copied:
            tree = ast.parse((root / filename).read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                modules = [node.module] if isinstance(node, ast.ImportFrom) else [n.name for n in node.names] if isinstance(node, ast.Import) else []
                for module in filter(None, modules):
                    dependency = module.split('.')[0] + '.py'
                    if (root / dependency).is_file():
                        self.assertIn(dependency, copied, f'{filename} requires {dependency}')


class ReadinessTests(unittest.TestCase):
    def test_liveness_without_database_and_readiness_no_sqlite_creation(self):
        with patch.dict(os.environ, {}, clear=True), patch('api.connect_application_postgres') as connect, TestClient(api.app) as client:
            self.assertEqual(client.get('/health').status_code, 200)
            self.assertEqual(client.get('/ready').status_code, 503)
            connect.assert_not_called()

    def test_ready_and_sanitized_database_failure(self):
        with patch('api.uses_postgres', return_value=True), patch('api.connect_application_postgres', return_value=MagicMock()) as connect, TestClient(api.app) as client:
            self.assertEqual(client.get('/ready').json(), {'status': 'ready'})
            connect.return_value.close.assert_called_once()
            connect.side_effect = DatabaseUnavailable('synthetic-secret')
            response = client.get('/ready')
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('synthetic-secret', response.text)


class SupervisorTests(unittest.TestCase):
    def test_child_exit_and_startup_failure_stop_sibling(self):
        for failing in ([sys.executable, '-c', 'pass'], ['daljam-nonexistent-test-executable']):
            with self.subTest(command=failing), tempfile.TemporaryDirectory() as folder:
                pidfile = Path(folder) / 'child.pid'
                code = f'import os,time;from pathlib import Path;Path({str(pidfile)!r}).write_text(str(os.getpid()));time.sleep(60)'
                self.assertEqual(run([[sys.executable, '-c', code], failing], os.environ.copy(), grace=2), 1)

    @unittest.skipIf(os.name == 'nt', 'POSIX SIGTERM delivery requires Linux; Docker verification pending')
    def test_sigterm_stops_both_children(self):
        script = 'from deploy.supervisor import run;import sys,os;sys.exit(run([[sys.executable,"-c","import time;time.sleep(60)"]]*2,os.environ.copy(),grace=2))'
        process = subprocess.Popen([sys.executable, '-c', script])
        try:
            time.sleep(1)
            process.send_signal(signal.SIGTERM)
            self.assertEqual(process.wait(timeout=5), 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
