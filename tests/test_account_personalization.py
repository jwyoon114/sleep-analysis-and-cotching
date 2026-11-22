"""Personalization uses the existing authentication and a disposable database."""

from contextlib import closing
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import api
import health_records
from json_sleep import EXAMPLE_JSON


PASSWORD = "synthetic-only-password"
CHOICES = {"mbti": None, "speech": "polite", "intensity": "gentle", "character": "cat"}
ENDPOINT = "/auth/personalization"


class PersonalizationTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {"SLEEP_DB_BACKEND": "sqlite", "DALJAM_ENV": "test", "COACHING_ENGINE": "rules"}))
        os.environ.pop("DATABASE_URL", None)
        directory = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.object(health_records, "DB_PATH", Path(directory) / "synthetic.sqlite"))
        self.client = TestClient(api.app)
        self.addCleanup(self.client.close)

    def sign_in(self, name, *, register=False):
        credentials = {"username": name, "password": PASSWORD}
        if register:
            response = self.client.post("/auth/register", json=credentials)
            self.assertEqual(response.status_code, 201)
        response = self.client.post("/auth/login", json=credentials)
        self.assertEqual(response.status_code, 200)
        return response.json()["user"]["id"], {"Authorization": "Bearer " + response.json()["token"]}

    def get(self, headers):
        response = self.client.get(ENDPOINT, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        return response.json()["personalization"]

    def test_first_login_retry_logout_and_account_isolation(self):
        alice, a = self.sign_in("test-alice", register=True)
        bob, b = self.sign_in("test-bob", register=True)
        for method in ("GET", "POST", "PATCH"):
            kwargs = {} if method == "GET" else {"json": CHOICES}
            self.assertEqual(self.client.request(method, ENDPOINT, **kwargs).status_code, 401)
        self.assertIsNone(self.get(a))
        self.assertEqual(self.client.patch(ENDPOINT, headers=a, json=CHOICES).status_code, 409)
        response = self.client.post(ENDPOINT, headers=a, json=CHOICES)
        self.assertEqual(response.status_code, 200)
        first = self.get(a)
        self.assertIsNone(first["mbti"])
        self.assertFalse(first["allow_profanity"])
        self.assertTrue(first["completed_at"])
        self.assertEqual(self.client.post(ENDPOINT, headers=a, json={**CHOICES, "mbti": "INFP"}).json()["personalization"], first)
        self.assertIsNone(self.get(b))
        self.assertEqual(self.client.post(ENDPOINT, headers=b, json={**CHOICES, "account_id": alice}).status_code, 422)
        self.assertEqual(self.client.get(ENDPOINT+"?account_id="+alice, headers=b).json()["personalization"], None)
        self.assertEqual(self.client.post("/auth/logout", headers=a).status_code, 200)
        self.assertEqual(self.client.get(ENDPOINT, headers=a).status_code, 401)
        self.assertEqual(self.get(self.sign_in("test-alice")[1]), first)
        self.assertNotEqual(alice, bob)

    def test_all_allowed_values_and_strict_consent(self):
        _, auth = self.sign_in("test-options", register=True)
        self.client.post(ENDPOINT, headers=auth, json=CHOICES).raise_for_status()
        original = self.get(auth)
        for mbti in ("ISTJ", "ISFJ", "INFJ", "INTJ", "ISTP", "ISFP", "INFP", "INTP",
                     "ESTP", "ESFP", "ENFP", "ENTP", "ESTJ", "ESFJ", "ENFJ", "ENTJ", None):
            self.client.patch(ENDPOINT, headers=auth, json={**CHOICES, "mbti": mbti}).raise_for_status()
            self.assertEqual(self.get(auth)["mbti"], mbti)
        for speech in ("polite", "casual"):
            for intensity in ("gentle", "firm", "direct"):
                for character in ("cat", "raccoon", "dog", "rabbit"):
                    values = {**CHOICES, "speech": speech, "intensity": intensity, "character": character,
                              "allow_profanity": intensity == "direct"}
                    self.assertEqual(self.client.patch(ENDPOINT, headers=auth, json=values).json()["personalization"],
                                     {**values, "completed_at": original["completed_at"]})
        for invalid in ({"mbti": "Abcd"}, {"speech": "unknown"}, {"character": "owl"}, {"intensity": "other"},
                        {"allow_profanity": 1}, {"intensity": "direct", "allow_profanity": "true"},
                        {"completed_at": "2026-11-01"}):
            self.assertEqual(self.client.patch(ENDPOINT, headers=auth, json={**CHOICES, **invalid}).status_code, 422)
        self.client.patch(ENDPOINT, headers=auth, json=CHOICES).raise_for_status()
        self.assertFalse(self.get(auth)["allow_profanity"])

    def test_existing_data_and_account_deletion_cascade(self):
        account, auth = self.sign_in("test-existing", register=True)
        response = self.client.post("/analyze", headers=auth, files={"file": ("fixture.json", EXAMPLE_JSON, "application/json")})
        response.raise_for_status()
        record_id = response.json()["analysis_ids"][0]
        self.client.post("/coach", headers=auth, json={"analysis_id": record_id}).raise_for_status()
        original = self.client.get(f"/watch/sessions/{record_id}/coaching", headers=auth).json()
        self.assertIsNone(self.get(auth))
        self.client.post(ENDPOINT, headers=auth, json=CHOICES).raise_for_status()
        self.client.patch(ENDPOINT, headers=auth, json={**CHOICES, "mbti": "ENFP", "character": "dog"}).raise_for_status()
        self.assertEqual(self.client.get(f"/watch/sessions/{record_id}/coaching", headers=auth).json(), original)
        self.assertEqual(self.client.get("/watch/sessions", headers=auth).json()["sessions"][0]["analysis_id"], record_id)
        response = self.client.request("DELETE", "/auth/me", headers=auth, json={
            "current_password": PASSWORD, "confirmation": "계정 삭제"})
        response.raise_for_status()
        with closing(health_records.connect()) as db:
            self.assertIsNone(db.execute("SELECT 1 FROM account_personalization WHERE account_id=?", (account,)).fetchone())
