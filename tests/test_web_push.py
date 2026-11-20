from base64 import urlsafe_b64encode
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import postgres_migrate
import web_push
from api import app
from postgres_migration_fixture import PostgresTestCluster
from production_policy import BACKUP_POLICY


def encoded(raw):
    return urlsafe_b64encode(raw).decode().rstrip("=")


def key_pair():
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    private = ec.generate_private_key(ec.SECP256R1())
    return private, private.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)


def enrollment(endpoint):
    _, public = key_pair()
    return {"endpoint": endpoint, "keys": {"p256dh": encoded(public), "auth": encoded(os.urandom(16))}}


class PushTransportTests(unittest.TestCase):
    def test_endpoint_allowlist(self):
        for endpoint in ("https://fcm.googleapis.com/fcm/send/fixture:part",
                         "https://updates.push.services.mozilla.com/wpush/v2/fixture",
                         "https://web.push.apple.com/fixture"):
            web_push.validate_endpoint(endpoint)
        for endpoint in ("http://web.push.apple.com/fixture", "https://localhost/fixture",
                         "https://web.push.apple.com.example.net/fixture", "https://fcm.googleapis.com/internal",
                         "https://user@web.push.apple.com/fixture", "https://web.push.apple.com:8443/fixture",
                         "https://web.push.apple.com/fixture?extra=1"):
            with self.assertRaises(ValueError):
                web_push.validate_endpoint(endpoint)

    def test_provider_request_uses_vapid_and_encrypts_fixed_payload(self):
        import http_ece
        from requests import Response

        receiver, public = key_pair()
        vapid, _ = key_pair()
        auth = os.urandom(16)
        config = web_push.Configuration(
            encoded(vapid.private_numbers().private_value.to_bytes(32, "big")), "", "mailto:fixture@example.org",
        )
        row = {"endpoint": "https://web.push.apple.com/example", "p256dh": encoded(public), "auth_secret": encoded(auth)}
        response = Response()
        response.status_code = 201
        with patch("requests.Session.post", return_value=response) as post:
            self.assertEqual(web_push._send(row, config), 201)
        args, params = post.call_args
        self.assertEqual(args[0], row["endpoint"])
        self.assertIs(params["allow_redirects"], False)
        headers = {key.lower(): value for key, value in params["headers"].items()}
        self.assertTrue(headers["authorization"].startswith("vapid "))
        self.assertEqual(headers["ttl"], "60")
        content = http_ece.decrypt(params["data"], private_key=receiver, auth_secret=auth, version="aes128gcm")
        self.assertEqual(json.loads(content), {"kind": "bedtime-test"})


@unittest.skipUnless(os.getenv("DALJAM_TEST_POSTGRES_BIN"), "Requires disposable PostgreSQL.")
class PushPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cluster = PostgresTestCluster(cls, Path(os.environ["DALJAM_TEST_POSTGRES_BIN"]))

    def setUp(self):
        self.database = self.cluster.new_database()
        key, _ = key_pair()
        self.enterContext(patch.dict(os.environ, {
            "DATABASE_URL": self.cluster.url(self.database), "SLEEP_DB_BACKEND": "postgresql",
            "DALJAM_ENV": "staging", "SLEEP_DESKTOP_ALARMS": "0",
            "DALJAM_WEB_PUSH_TEST": "1", "DALJAM_BACKUP_POLICY": BACKUP_POLICY,
            "DALJAM_VAPID_PRIVATE_KEY": encoded(key.private_numbers().private_value.to_bytes(32, "big")),
            "DALJAM_VAPID_SUBJECT": "mailto:fixture@example.org",
        }))
        self.client = self.enterContext(TestClient(app))
        self.password = "synthetic-password"

    def register(self, name):
        self.client.post("/auth/register", json={"username": name, "password": self.password}).raise_for_status()
        return self.login(name)

    def login(self, name):
        token = self.client.post("/auth/login", json={"username": name, "password": self.password}).raise_for_status().json()["token"]
        return {"Authorization": "Bearer " + token}

    def subscribe(self, headers, suffix):
        payload = enrollment("https://web.push.apple.com/" + suffix)
        return self.client.post("/web-push/subscriptions", headers=headers, json=payload).raise_for_status().json()["id"]

    def test_upgrade_and_inert_production(self):
        with TemporaryDirectory() as directory:
            old = Path(directory)
            shutil.copytree(postgres_migrate.MIGRATIONS, old, dirs_exist_ok=True)
            manifest_file = old / "manifest.json"
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            manifest["migrations"] = manifest["migrations"][:4]
            manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(postgres_migrate.apply_migrations(old), (1, 2, 3, 4))
        from sleep_accounts import password_hash
        salt = os.urandom(16).hex()
        with self.cluster.connect(self.database) as db:
            db.execute("INSERT INTO accounts (id,username,salt,password_hash,created_at) VALUES (%s,%s,%s,%s,%s)",
                       ("existing", "previous-schema", salt, password_hash(self.password, salt), "2026-11-12"))
        self.assertEqual(postgres_migrate.apply_migrations(), (5, 6, 7))
        self.assertEqual(postgres_migrate.apply_migrations(), ())
        headers = self.login("previous-schema")
        self.assertEqual(self.client.get("/auth/me", headers=headers).status_code, 200)
        with patch.dict(os.environ, {"DALJAM_ENV": "production"}), patch.object(web_push, "_send") as send:
            self.assertEqual(self.client.get("/web-push", headers=headers).json(), {
                "enabled": False, "public_key": None, "devices": [],
            })
            self.assertEqual(self.client.post("/web-push/test", headers=headers, json={"id": "a" * 64}).status_code, 503)
            send.assert_not_called()

    def test_production_pilot_only_allows_selected_accounts_without_scheduling(self):
        postgres_migrate.apply_migrations()
        pilot = self.register("push-pilot")
        other = self.register("push-other")
        account_id = self.client.get("/auth/me", headers=pilot).raise_for_status().json()["user"]["id"]
        with patch.dict(os.environ, {
            "DALJAM_ENV": "production",
            "DALJAM_WEB_PUSH_TEST_ACCOUNT_IDS": account_id,
            "DALJAM_SCHEDULED_PUSH": "0",
        }), patch.object(web_push, "_send", return_value=201) as send:
            state = self.client.get("/web-push", headers=pilot).json()
            self.assertTrue(state["enabled"] and state["test_enabled"])
            self.assertFalse(state["scheduled_enabled"])
            self.assertFalse(self.client.get("/web-push", headers=other).json()["enabled"])
            payload = enrollment("https://web.push.apple.com/limited-pilot")
            self.assertEqual(self.client.post("/web-push/subscriptions", headers=other, json=payload).status_code, 503)
            endpoint_id = self.subscribe(pilot, "limited-pilot")
            self.assertEqual(self.client.post("/web-push/test", headers=other, json={"id": endpoint_id}).status_code, 503)
            self.assertEqual(self.client.patch(f"/web-push/subscriptions/{endpoint_id}", headers=pilot,
                                              json={"enabled": True}).status_code, 503)
            self.client.post("/web-push/test", headers=pilot, json={"id": endpoint_id}).raise_for_status()
            self.assertEqual(send.call_count, 1)
            with patch.dict(os.environ, {"DALJAM_WEB_PUSH_TEST": "0"}):
                self.assertFalse(self.client.get("/web-push", headers=pilot).json()["enabled"])
                self.assertEqual(self.client.post("/web-push/test", headers=pilot, json={"id": endpoint_id}).status_code, 503)
            self.assertEqual(send.call_count, 1)

    def test_ownership_cooldown_expiry_logout_and_account_deletion(self):
        postgres_migrate.apply_migrations()
        alice = self.register("push-alice")
        bob = self.register("push-bob")
        second_device = self.login("push-alice")
        first_id = self.subscribe(alice, "first")
        second_id = self.subscribe(second_device, "second")
        bob_id = self.subscribe(bob, "third")
        self.assertEqual(self.client.get("/web-push").status_code, 401)
        state = self.client.get("/web-push", headers=alice)
        self.assertIn("no-store", state.headers["cache-control"])
        self.assertEqual(len(web_push.decode_key(state.json()["public_key"], 65)), 65)
        self.assertEqual({d["id"]: d["this_session"] for d in state.json()["devices"]}, {first_id: True, second_id: False})
        self.assertNotIn("https://web.push.apple.com", state.text)
        self.assertEqual(self.client.get("/web-push", headers=bob).json()["devices"][0]["id"], bob_id)
        conflict = self.client.post("/web-push/subscriptions", headers=bob, json=enrollment("https://web.push.apple.com/first"))
        self.assertEqual(conflict.status_code, 409)
        self.client.delete("/web-push/subscriptions/" + first_id, headers=bob).raise_for_status()
        bad = self.client.post("/web-push/subscriptions", headers=alice, json={"endpoint": "private-fixture", "keys": {}})
        self.assertEqual(bad.status_code, 422)
        self.assertNotIn("private-fixture", bad.text)
        with patch.object(web_push, "_send", return_value=201) as send:
            self.assertEqual(self.client.post("/web-push/test", headers=bob, json={"id": first_id}).status_code, 404)
            def send_current(_):
                return self.client.post("/web-push/test", headers=alice, json={"id": first_id}).status_code
            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertEqual(sorted(pool.map(send_current, range(2))), [200, 429])
            self.assertEqual(self.client.post("/web-push/test", headers=second_device, json={"id": second_id}).status_code, 429)
            self.assertEqual(send.call_count, 1)
        later = web_push._now() + timedelta(minutes=2)
        with patch.object(web_push, "_now", return_value=later), patch.object(web_push, "_send", return_value=410):
            self.assertEqual(self.client.post("/web-push/test", headers=alice, json={"id": first_id}).status_code, 410)
        self.assertEqual([d["id"] for d in self.client.get("/web-push", headers=alice).json()["devices"]], [second_id])
        self.client.post("/auth/logout", headers=second_device).raise_for_status()
        self.assertEqual(self.client.get("/web-push", headers=alice).json()["devices"], [])
        self.client.request("DELETE", "/auth/me", headers=bob, json={
            "current_password": self.password, "confirmation": "계정 삭제",
        }).raise_for_status()
        with self.cluster.connect(self.database) as db:
            self.assertEqual(db.execute("SELECT count(*) AS count FROM web_push_subscriptions").fetchone()["count"], 0)
