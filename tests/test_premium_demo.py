"""Presentation-only grants using synthetic accounts and isolated databases."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import os
import unittest
from unittest.mock import patch

import coaching_service
import health_records
import premium_service
from production_policy import BACKUP_POLICY
from test_manual_sleep import ManualSleepFixture


class PremiumDemoTests(ManualSleepFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.enterContext(patch.dict(os.environ, {"DALJAM_PREMIUM_DEMO": "1", "COACHING_ENGINE": "openai"}))
        self.enterContext(patch.dict(premium_service._grants, {}, clear=True))
        self.provider = self.enterContext(patch("openai.OpenAI", side_effect=AssertionError("External AI forbidden in presentation")))
        self.settings = self.enterContext(patch.object(coaching_service, "settings", side_effect=AssertionError("Key lookup forbidden")))
        self.addCleanup(self.provider.assert_not_called)
        self.addCleanup(self.settings.assert_not_called)

    def activate(self, headers=None):
        headers = headers or self.owner
        checkout = self.client.post("/premium/demo/checkout", headers=headers).raise_for_status().json()
        return self.client.post("/premium/demo/activate", headers=headers, json={
            "checkout_token": checkout["checkout_token"], "acknowledged": True,
        }).raise_for_status().json()

    def counts(self):
        with closing(health_records.connect()) as db:
            return {name: db.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
                    for name in ("accounts", "sessions", "coaching", "coaching_context")}

    def test_default_disabled_and_authentication_are_enforced(self):
        for path, method in [("/premium", "GET"), ("/premium/demo/preview", "GET"),
                             ("/premium/demo/checkout", "POST"), ("/premium/demo", "DELETE")]:
            self.assertEqual(self.client.request(method, path).status_code, 401)
        for flags in ({"DALJAM_PREMIUM_DEMO": "0"}, {"DALJAM_ENV": "production"},
                      {"DALJAM_ENV": ""}, {"DALJAM_ENV": "unknown"}):
            with self.subTest(flags=flags), patch.dict(os.environ, flags):
                state = self.client.get("/premium", headers=self.owner).json()
                self.assertEqual(state["tier"], "free")
                self.assertFalse(state["demo_available"])
                self.assertFalse(state["paid_entitlement"])
                for path, method in [("/premium/demo/checkout", "POST"), ("/premium/demo/preview", "GET"), ("/premium/demo", "DELETE")]:
                    self.assertEqual(self.client.request(method, path, headers=self.owner).status_code, 403)

    def test_mock_checkout_is_idempotent_and_never_grants_live_ai(self):
        checkout = self.client.post("/premium/demo/checkout", headers=self.owner).json()
        self.assertEqual(checkout["mode"], "simulation")
        self.assertFalse(checkout["payment_required"])
        self.assertEqual(self.client.get("/premium", headers=self.owner).json()["tier"], "free")
        def finish(_):
            return self.client.post("/premium/demo/activate", headers=self.owner, json={
                "checkout_token": checkout["checkout_token"], "acknowledged": True,
            }).raise_for_status().json()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.map(finish, range(2))
        self.assertEqual(first, second)
        self.assertEqual(first["tier"], "premium_demo")
        self.assertFalse(first["paid_entitlement"])
        self.assertFalse(first["live_ai_available"])
        account_id = self.client.get("/auth/me", headers=self.owner).json()["user"]["id"]
        self.assertFalse(premium_service.has_paid_ai_entitlement(account_id))
        self.assertNotIn("receipt", first)
        self.assertNotIn("price", first)

    def test_frontend_forgery_and_payment_fields_cannot_grant_access(self):
        self.assertEqual(self.client.get("/premium/demo/preview", headers=self.owner).status_code, 403)
        checkout = self.client.post("/premium/demo/checkout", headers=self.owner).json()
        data = {"checkout_token": checkout["checkout_token"], "acknowledged": True}
        for extra in ({"tier": "premium"}, {"paid_entitlement": True}, {"card_number": "synthetic-field-forbidden"}):
            self.assertEqual(self.client.post("/premium/demo/activate", headers=self.owner, json=data | extra).status_code, 422)
        self.assertEqual(self.client.post("/premium/demo/activate", headers=self.owner, json=data | {"acknowledged": False}).status_code, 422)
        self.assertEqual(self.client.post("/premium/demo/activate", headers=self.owner, json=data | {"checkout_token": "forged-token-" * 3}).status_code, 409)
        self.assertEqual(self.client.post("/premium/demo/activate", headers=self.other, json=data).status_code, 409)
        self.assertEqual(self.client.get("/premium", headers=self.owner).json()["tier"], "free")

    def test_free_and_demo_users_get_rules_even_when_global_engine_is_openai(self):
        manual_id = self.manual().json()["record"]["analysis_id"]
        automatic_id, = self.upload("2024-11-17T23:00:00+09:00", "2024-11-18T07:00:00+09:00").json()["analysis_ids"]
        for phase in ("free", "premium_demo"):
            if phase == "premium_demo":
                self.activate()
            for record_id, expected in [(manual_id, "manual-rules"), (automatic_id, "rules")]:
                result = self.client.post("/coach", headers=self.owner, json={
                    "analysis_id": record_id, "tier": "premium", "paid_entitlement": True,
                }).raise_for_status().json()
                self.assertEqual(result["context"]["engine"], expected)
        self.assertEqual(self.client.get("/watch/sessions", headers=self.owner).json()["overview"]["session_count"], 1)

    def test_sample_is_separate_from_health_records_and_coaching_history(self):
        manual_id = self.manual().json()["record"]["analysis_id"]
        self.activate()
        before = self.counts()
        result = self.client.get("/premium/demo/preview", headers=self.owner)
        self.assertIn("no-store", result.headers["cache-control"])
        sample = result.json()
        self.assertEqual(sample["source"], "prepared_sample")
        self.assertEqual(sample["title"], "AI 코칭 시연 예시 — 샘플 데이터")
        self.assertTrue(sample["synthetic"])
        self.assertFalse(sample["model_called"])
        self.assertFalse(sample["saved_to_history"])
        self.assertIn("가상 기록", sample["coaching"])
        self.assertNotRegex(sample["coaching"], r"REM|깊은 수면|심박|수면의 질")
        self.assertNotIn(manual_id, str(sample))
        self.assertNotIn("2024-11-15", str(sample))
        self.assertEqual(self.counts(), before)
        self.assertEqual(self.client.get(f"/watch/sessions/{manual_id}/coaching", headers=self.owner).json()["history"], [])

    def test_sample_respects_server_speech_and_intensity_and_ignores_character(self):
        self.activate()
        texts = []
        for speech in ("polite", "casual"):
            for intensity in ("gentle", "firm", "direct"):
                profile = {"mbti": None, "speech": speech, "intensity": intensity, "allow_profanity": False, "character": "cat"}
                self.client.request("PATCH" if texts else "POST", "/auth/personalization", headers=self.owner, json=profile).raise_for_status()
                sample = self.client.get("/premium/demo/preview", headers=self.owner).json()
                self.assertEqual(sample["expression"]["speech"], speech)
                self.assertEqual(sample["expression"]["intensity"], intensity)
                texts.append(sample["coaching"])
        self.assertEqual(len(set(texts)), 6)
        self.client.patch("/auth/personalization", headers=self.owner, json=profile | {"character": "rabbit"}).raise_for_status()
        self.assertEqual(self.client.get("/premium/demo/preview", headers=self.owner).json()["coaching"], texts[-1])

    def test_reset_only_clears_current_account_demo(self):
        self.activate()
        self.activate(self.other)
        before = self.counts()
        self.assertEqual(self.client.delete("/premium/demo", headers=self.owner).json()["tier"], "free")
        self.assertEqual(self.client.delete("/premium/demo", headers=self.owner).json()["tier"], "free")
        self.assertEqual(self.client.get("/premium/demo/preview", headers=self.owner).status_code, 403)
        self.assertEqual(self.client.get("/premium", headers=self.other).json()["tier"], "premium_demo")
        self.assertEqual(self.counts(), before)

    def test_checkout_and_demo_expiry_restart_and_production_transition(self):
        with patch("premium_service.time.time", return_value=1000):
            checkout = self.client.post("/premium/demo/checkout", headers=self.owner).json()
        with patch("premium_service.time.time", return_value=1601):
            self.assertEqual(self.client.post("/premium/demo/activate", headers=self.owner, json={
                "checkout_token": checkout["checkout_token"], "acknowledged": True,
            }).status_code, 409)
            active = self.activate()
        with patch("premium_service.time.time", return_value=1601 + premium_service.DEMO_SECONDS + 1):
            self.assertEqual(self.client.get("/premium", headers=self.owner).json()["tier"], "free")
        self.activate()
        with patch.dict(os.environ, {"DALJAM_ENV": "production"}):
            self.assertEqual(self.client.get("/premium", headers=self.owner).json()["tier"], "free")
            self.assertEqual(self.client.get("/premium/demo/preview", headers=self.owner).status_code, 403)
        with patch.dict(premium_service._grants, {}, clear=True):
            self.assertEqual(self.client.get("/premium", headers=self.owner).json()["tier"], "free")
        self.assertIsNotNone(active["demo_expires_at"])

    def test_logout_and_account_deletion_remove_presentation_grants(self):
        self.activate()
        self.client.post("/auth/logout", headers=self.owner).raise_for_status()
        token = self.client.post("/auth/login", json={"username": "manual-owner", "password": "synthetic-tests-only"}).json()["token"]
        self.owner = {"Authorization": "Bearer " + token}
        self.assertEqual(self.client.get("/premium", headers=self.owner).json()["tier"], "free")
        self.activate()
        account_id = self.client.get("/auth/me", headers=self.owner).json()["user"]["id"]
        # Simulate an approved backup policy for this disposable database only.
        with patch.dict(os.environ, {"DALJAM_BACKUP_POLICY": BACKUP_POLICY}):
            self.client.request("DELETE", "/auth/me", headers=self.owner, json={
                "current_password": "synthetic-tests-only", "confirmation": "계정 삭제",
            }).raise_for_status()
        self.assertNotIn(account_id, premium_service._grants)
        self.assertEqual(self.client.get("/premium", headers=self.owner).status_code, 401)
