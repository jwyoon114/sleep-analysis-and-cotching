"""No network, operating DB, browser subscriptions or real notifications."""
import io
import os
from pathlib import Path
import selectors
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from threading import Event
import unittest
from unittest.mock import patch

import scheduled_push
from deploy.supervisor import production_commands


class PushWorkerTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "POSIX SIGTERM behavior is verified in Linux CI")
    def test_real_worker_process_exits_cleanly_on_sigterm(self):
        code = """
import os, scheduled_push
os.environ['DALJAM_SCHEDULED_PUSH']='1'
scheduled_push.web_push.scheduled_enabled=lambda: True
scheduled_push.web_push.require_configuration=lambda: object()
def cycle(*args, **kwargs):
    print('WORKER-CYCLE', flush=True)
    return {}
scheduled_push.run=cycle
raise SystemExit(scheduled_push.worker_main())
"""
        process=subprocess.Popen([sys.executable,"-B","-c",code],cwd=Path(__file__).resolve().parents[1],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout,selectors.EVENT_READ)
                self.assertTrue(selector.select(timeout=10),"Worker did not enter its first cycle")
                self.assertEqual(process.stdout.readline().strip(),"WORKER-CYCLE")
            process.terminate()
            process.communicate(timeout=5)
            self.assertEqual(process.returncode,0)
        finally:
            if process.poll() is None:
                process.kill();process.communicate(timeout=5)

    def test_disabled_worker_does_not_read_keys_or_database(self):
        for value in ("0", "", "true"):
            with self.subTest(value=value), patch.dict(os.environ, {"DALJAM_SCHEDULED_PUSH":value}), patch("web_push.require_configuration", side_effect=AssertionError("Must not connect")):
                self.assertEqual(scheduled_push.worker_main(), 0)
        self.assertEqual(len(production_commands({})), 2)
        self.assertEqual(len(production_commands({"DALJAM_SCHEDULED_PUSH":"0"})), 2)
        self.assertEqual(production_commands({"DALJAM_SCHEDULED_PUSH":"1"})[-1][1:], ["-m", "scheduled_push"])

    def test_shutdown_before_cycle_does_not_dispatch(self):
        stop=Event();stop.set()
        with patch("scheduled_push.run") as dispatch:
            scheduled_push.worker_loop(object(), stop)
            dispatch.assert_not_called()

    def test_failed_cycle_retries_without_exposing_error_details(self):
        class Stop:
            def __init__(self):self.waits=[]
            def is_set(self):return len(self.waits)>=2
            def wait(self, interval):self.waits.append(interval)
        stop=Stop();output=io.StringIO()
        with patch("scheduled_push.run", side_effect=[RuntimeError("private-endpoint-fixture"), {}]) as dispatch, redirect_stderr(output):
            scheduled_push.worker_loop(object(), stop, interval=30)
        self.assertEqual(dispatch.call_count, 2)
        self.assertEqual(stop.waits,[30,30])
        self.assertNotIn("private-endpoint-fixture", output.getvalue())
        self.assertIn("cycle failed", output.getvalue())

    def test_enabled_worker_fails_closed_without_valid_configuration(self):
        with patch.dict(os.environ, {"DALJAM_SCHEDULED_PUSH":"1"}), patch("web_push.scheduled_enabled",return_value=False), patch("scheduled_push.worker_loop") as loop, redirect_stderr(io.StringIO()):
            self.assertEqual(scheduled_push.worker_main(),1)
            loop.assert_not_called()

    def test_cycle_logs_only_allowlisted_integer_counts(self):
        stop=Event();output=io.StringIO()
        def dispatch(*args, **kwargs):
            stop.set()
            return {"due":1,"sent":1,"failed":"private-fixture", "endpoint":"private-endpoint-fixture"}
        with patch("scheduled_push.run",side_effect=dispatch),redirect_stdout(output):
            scheduled_push.worker_loop(object(),stop)
        self.assertIn('"due": 1',output.getvalue())
        self.assertNotIn("private",output.getvalue())
        self.assertNotIn("endpoint",output.getvalue())
