from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import app
import postgres_migrate
from postgres_migration_fixture import PostgresTestCluster
from production_policy import BACKUP_POLICY
import scheduled_push
from sleep_accounts import digest
from test_web_push import encoded, enrollment, key_pair
import web_push


UTC = timezone.utc
SEOUL_DUE = datetime(2026, 10, 1, 13, 30, tzinfo=UTC)


class ReminderTimeTests(unittest.TestCase):
    def test_local_midnight_and_dst(self):
        times = (
            (date(2026, 10, 1), "23:00", "Asia/Seoul", SEOUL_DUE),
            (date(2026, 10, 2), "00:15", "Asia/Seoul", datetime(2026, 10, 1, 14, 45, tzinfo=UTC)),
            (date(2026, 10, 1), "23:00", "Pacific/Honolulu", datetime(2026, 10, 2, 8, 30, tzinfo=UTC)),
            (date(2026, 3, 8), "02:30", "America/New_York", datetime(2026, 3, 8, 6, 30, tzinfo=UTC)),
            (date(2026, 11, 1), "01:30", "America/New_York", datetime(2026, 11, 1, 5, 0, tzinfo=UTC)),
        )
        for day, bedtime, zone, expected in times:
            with self.subTest(day=day, bedtime=bedtime, zone=zone):
                self.assertEqual(scheduled_push.reminder_time(day, bedtime, zone), expected)
                self.assertEqual(scheduled_push.due_now({"bedtime": bedtime, "timezone": zone}, expected),
                                 (day, expected))
                self.assertIsNone(scheduled_push.due_now({"bedtime": bedtime, "timezone": zone},
                                                         expected + scheduled_push.GRACE))


@unittest.skipUnless(os.getenv("DALJAM_TEST_POSTGRES_BIN"), "Requires disposable PostgreSQL.")
class ScheduledPushPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cluster = PostgresTestCluster(cls, Path(os.environ["DALJAM_TEST_POSTGRES_BIN"]))

    def setUp(self):
        self.database = self.cluster.new_database()
        private, _ = key_pair()
        self.secret = secrets.token_urlsafe(32)
        self.enterContext(patch.dict(os.environ, {
            "DATABASE_URL": self.cluster.url(self.database), "SLEEP_DB_BACKEND": "postgresql",
            "DALJAM_ENV": "staging", "SLEEP_DESKTOP_ALARMS": "0",
            "DALJAM_WEB_PUSH_TEST": "1", "DALJAM_BACKUP_POLICY": BACKUP_POLICY,
            "DALJAM_VAPID_PRIVATE_KEY": encoded(private.private_numbers().private_value.to_bytes(32, "big")),
            "DALJAM_VAPID_SUBJECT": "mailto:fixture@example.org",
            "DALJAM_SCHEDULED_PUSH": "1", "DALJAM_PUSH_JOB_SECRET": self.secret,
        }))
        self.client = self.enterContext(TestClient(app))
        self.password = "scheduled-test-password"

    def credentials(self, name):
        return {"username": name, "password": self.password}

    def login(self, name, installation=None, register=False):
        credentials = self.credentials(name)
        if register:
            self.client.post("/auth/register", json=credentials).raise_for_status()
        headers = {"X-Daljam-Push-Device": installation or secrets.token_hex(32)}
        token = self.client.post("/auth/login", headers=headers, json=credentials).raise_for_status().json()["token"]
        return {**headers, "Authorization": "Bearer " + token}

    def goal(self, headers, bedtime="23:00"):
        self.client.post("/alarms", headers=headers, json={
            "bedtime": bedtime, "wake_time": "07:00", "timezone": "Asia/Seoul", "enabled": False,
        }).raise_for_status()

    def subscribe(self, headers, suffix):
        payload = enrollment("https://web.push.apple.com/" + suffix)
        return self.client.post("/web-push/subscriptions", headers=headers, json=payload).raise_for_status().json()["id"]

    def toggle(self, headers, device, enabled=True):
        return self.client.patch("/web-push/subscriptions/" + device, headers=headers, json={"enabled": enabled})

    def job(self, when=SEOUL_DUE):
        return scheduled_push.run(web_push.require_configuration(), clock=lambda: when)

    def state(self, device):
        with self.cluster.connect(self.database) as db:
            return db.execute("SELECT state, attempts FROM web_push_deliveries WHERE endpoint_id=%s ORDER BY bedtime_date",
                              (device,)).fetchall()

    def devices(self, headers):
        return self.client.get("/web-push", headers=headers).raise_for_status().json()["devices"]

    def test_upgrade_reconnects_legacy_device_without_enabling_reminders(self):
        with TemporaryDirectory() as directory:
            catalog = Path(directory)
            shutil.copytree(postgres_migrate.MIGRATIONS, catalog, dirs_exist_ok=True)
            path = catalog / "manifest.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["migrations"] = manifest["migrations"][:5]
            path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(postgres_migrate.apply_migrations(catalog), (1, 2, 3, 4, 5))

        payload = enrollment("https://web.push.apple.com/legacy")
        token = secrets.token_hex(32)
        now = web_push._now()
        endpoint_id = digest(payload["endpoint"])
        with self.cluster.connect(self.database) as db:
            db.execute("INSERT INTO accounts VALUES ('legacy-account', 'legacy', 'unused', 'unused', %s)", (now.isoformat(),))
            db.execute("INSERT INTO auth_tokens VALUES (%s,'legacy-account',%s)",
                       (digest(token), (now + timedelta(hours=24)).isoformat()))
            db.execute("INSERT INTO web_push_subscriptions "
                       "(endpoint_id,token_hash,endpoint,p256dh,auth_secret,registered_at) VALUES (%s,%s,%s,%s,%s,%s)",
                       (endpoint_id, digest(token), payload["endpoint"], payload["keys"]["p256dh"], payload["keys"]["auth"], now))
        self.assertEqual(postgres_migrate.apply_migrations(), (6, 7))
        self.assertEqual(postgres_migrate.apply_migrations(), ())
        headers = {"Authorization": "Bearer " + token, "X-Daljam-Push-Device": secrets.token_hex(32)}
        before, = self.devices(headers)
        self.assertEqual((before["id"], before["durable"], before["reminders_enabled"]), (endpoint_id, False, False))
        self.client.post("/web-push/subscriptions", headers=headers, json=payload).raise_for_status()
        after, = self.devices(headers)
        self.assertEqual((after["id"], after["durable"], after["reminders_enabled"]), (endpoint_id, True, False))

    def test_session_expiry_relogin_logout_and_account_deletion(self):
        postgres_migrate.apply_migrations()
        home = self.login("scheduled-account", register=True)
        other = self.login("scheduled-account")
        self.goal(home)
        first, second = self.subscribe(home, "first"), self.subscribe(other, "second")
        self.toggle(home, first).raise_for_status()
        self.toggle(other, second).raise_for_status()
        with self.cluster.connect(self.database) as db:
            db.execute("UPDATE auth_tokens SET expires_at=%s WHERE token_hash=%s",
                       ((web_push._now() - timedelta(seconds=1)).isoformat(), digest(home["Authorization"][7:])))
        self.assertEqual(self.client.get("/web-push", headers=home).status_code, 401)
        with patch.object(web_push, "_send", return_value=201):
            self.assertEqual(self.job()["sent"], 2)
        home = self.login("scheduled-account", home["X-Daljam-Push-Device"])
        self.assertEqual({d["id"]: d["this_session"] for d in self.devices(home)}, {first: True, second: False})
        self.client.post("/auth/logout", headers=home).raise_for_status()
        self.assertEqual([d["id"] for d in self.devices(other)], [second])
        with patch.object(web_push, "_send", return_value=201):
            self.assertEqual(self.job(SEOUL_DUE + timedelta(days=1))["sent"], 1)
        self.client.request("DELETE", "/auth/me", headers=other, json={
            "current_password": self.password, "confirmation": "계정 삭제",
        }).raise_for_status()
        self.assertEqual(self.state(first), [])
        self.assertEqual(self.state(second), [])
        with patch.object(web_push, "_send") as send:
            self.assertEqual(self.job(SEOUL_DUE + timedelta(days=2))["due"], 0)
            send.assert_not_called()

    def test_job_auth_device_ownership_opt_in_and_account_switch(self):
        postgres_migrate.apply_migrations()
        alice, bob = self.login("scheduled-alice", register=True), self.login("scheduled-bob", register=True)
        endpoint_id = self.subscribe(alice, "personal")
        self.assertEqual(self.toggle(alice, endpoint_id).status_code, 409)
        self.goal(alice)
        self.goal(bob)
        self.assertEqual(self.toggle(bob, endpoint_id).status_code, 404)
        self.assertEqual(self.toggle(bob, endpoint_id, False).status_code, 404)
        self.assertEqual(self.job()["due"], 0)
        self.toggle(alice, endpoint_id).raise_for_status()
        self.assertEqual(self.client.post("/internal/web-push/run", headers=alice).status_code, 403)
        self.assertEqual(self.client.post("/internal/web-push/run").status_code, 403)
        job_header = {"Authorization": "Bearer " + self.secret}
        self.assertEqual(self.client.get("/web-push", headers=job_header).status_code, 401)
        with patch.dict(os.environ, {"DALJAM_SCHEDULED_PUSH": "0", "DALJAM_WEB_PUSH_TEST": "0"}):
            self.assertEqual(self.client.post("/internal/web-push/run", headers=job_header).status_code, 404)
            state = self.client.get("/web-push", headers=alice).json()
            self.assertFalse(state["enabled"])
            self.assertTrue(state["devices"][0]["reminders_enabled"])
            self.toggle(alice, endpoint_id, False).raise_for_status()
            self.assertEqual(self.toggle(alice, endpoint_id).status_code, 503)
        with patch.object(scheduled_push, "run", return_value={"sent": 0}) as run:
            result = self.client.post("/internal/web-push/run", headers=job_header)
            self.assertEqual(result.status_code, 200)
            self.assertIn("no-store", result.headers["cache-control"])
            run.assert_called_once()
        self.login("scheduled-bob", alice["X-Daljam-Push-Device"])
        self.assertEqual(self.devices(alice), [])
        self.assertEqual(self.devices(bob), [])
        self.assertEqual(self.job()["due"], 0)

    def test_concurrent_dispatch_goal_change_and_same_day_reenrollment(self):
        postgres_migrate.apply_migrations()
        home = self.login("scheduled-concurrent", register=True)
        self.goal(home)
        endpoint_id = self.subscribe(home, "concurrent")
        self.toggle(home, endpoint_id).raise_for_status()
        self.goal(home, "23:10")
        later = SEOUL_DUE + timedelta(minutes=10)
        with patch.object(web_push, "_send", return_value=201) as send:
            self.assertEqual(self.job()["due"], 0)
            with ThreadPoolExecutor(max_workers=3) as pool:
                results = list(pool.map(self.job, [later] * 3))
            self.assertEqual(sum(r["sent"] for r in results), 1)
            send.assert_called_once()
            self.assertEqual(send.call_args.kwargs, {"kind": "bedtime-reminder", "ttl": 60})
            self.toggle(home, endpoint_id, False).raise_for_status()
            self.client.delete("/web-push/subscriptions/" + endpoint_id, headers=home).raise_for_status()
            new_id = self.subscribe(home, "replacement")
            self.toggle(home, new_id).raise_for_status()
            self.assertEqual(self.job(later)["sent"], 0)
            self.assertEqual(self.job(later + timedelta(days=1))["sent"], 1)
            self.assertEqual(send.call_count, 2)

    def test_retries_timeout_stale_claim_and_provider_expiry(self):
        postgres_migrate.apply_migrations()
        headers = self.login("scheduled-retry", register=True)
        self.goal(headers)
        endpoint_id = self.subscribe(headers, "retry")
        self.toggle(headers, endpoint_id).raise_for_status()
        with patch.object(web_push, "_send", side_effect=[429, 429]) as send:
            self.assertEqual(self.job()["retry"], 1)
            self.assertEqual(self.job(SEOUL_DUE + timedelta(minutes=1))["claimed"], 0)
            self.assertEqual(self.job(SEOUL_DUE + timedelta(minutes=2))["failed"], 1)
            self.assertEqual(self.job(SEOUL_DUE + timedelta(minutes=4))["claimed"], 0)
            self.assertEqual(send.call_count, 2)
        self.assertEqual(self.state(endpoint_id), [{"state": "failed", "attempts": 2}])
        tomorrow = SEOUL_DUE + timedelta(days=1)
        with patch.object(web_push, "_send", return_value=None) as send:
            self.assertEqual(self.job(tomorrow)["uncertain"], 1)
            self.assertEqual(self.job(tomorrow + timedelta(minutes=2))["claimed"], 0)
            send.assert_called_once()
        missed = tomorrow + timedelta(days=1)
        self.assertIsNotNone(scheduled_push._claim(endpoint_id, missed))
        with patch.object(web_push, "_send") as send:
            self.assertEqual(self.job(missed + timedelta(minutes=2))["claimed"], 0)
            self.assertEqual(self.job(missed + timedelta(days=1, minutes=10))["due"], 0)
            send.assert_not_called()
        self.assertEqual([row["state"] for row in self.state(endpoint_id)], ["failed", "uncertain", "uncertain"])
        with patch.object(web_push, "_send", return_value=410):
            self.assertEqual(self.job(missed + timedelta(days=2))["failed"], 1)
        self.assertEqual(self.devices(headers), [])

    def test_expired_provider_response_keeps_reassigned_subscription(self):
        postgres_migrate.apply_migrations()
        alice = self.login("scheduled-transfer-alice", register=True)
        self.login("scheduled-transfer-bob", register=True)
        self.goal(alice)
        payload = enrollment("https://web.push.apple.com/transfer")
        endpoint_id = self.client.post("/web-push/subscriptions", headers=alice, json=payload).raise_for_status().json()["id"]
        self.toggle(alice, endpoint_id).raise_for_status()

        def later_response(*args, **kwargs):
            bob = self.login("scheduled-transfer-bob", alice["X-Daljam-Push-Device"])
            self.client.post("/web-push/subscriptions", headers=bob, json=payload).raise_for_status()
            return 410

        with patch.object(web_push, "_send", side_effect=later_response):
            self.assertEqual(self.job()["failed"], 1)
        bob = self.login("scheduled-transfer-bob", alice["X-Daljam-Push-Device"])
        self.assertEqual([d["id"] for d in self.devices(bob)], [endpoint_id])

    def test_opt_out_before_send_and_stored_expiration(self):
        postgres_migrate.apply_migrations()
        headers = self.login("scheduled-opt-out", register=True)
        self.goal(headers)
        endpoint_id = self.subscribe(headers, "optout")
        self.toggle(headers, endpoint_id).raise_for_status()
        claim = scheduled_push._claim(endpoint_id, SEOUL_DUE)
        self.assertIsNotNone(claim)
        self.toggle(headers, endpoint_id, False).raise_for_status()
        with patch.object(web_push, "_send") as send:
            self.assertEqual(scheduled_push._dispatch(claim, web_push.require_configuration(), lambda: SEOUL_DUE),
                             "cancelled")
            send.assert_not_called()
        self.toggle(headers, endpoint_id).raise_for_status()
        with self.cluster.connect(self.database) as db:
            db.execute("UPDATE web_push_subscriptions SET expires_at=%s WHERE endpoint_id=%s", (SEOUL_DUE, endpoint_id))
        with patch.object(web_push, "_send") as send:
            self.assertEqual(self.job()["due"], 0)
            send.assert_not_called()
        self.assertEqual(self.devices(headers), [])
