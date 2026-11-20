from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from api import app
import coaching_service
import morning_plans
import postgres_migrate
from postgres_migration_fixture import PostgresTestCluster


class ManualSleepFixture:
    @classmethod
    def setUpClass(cls):
        pg_bin = os.getenv("DALJAM_TEST_POSTGRES_BIN")
        cls.cluster = PostgresTestCluster(cls, Path(pg_bin)) if pg_bin else None

    def setUp(self):
        flags = {"COACHING_ENGINE": "rules", "DALJAM_ENV": "staging", "SLEEP_DESKTOP_ALARMS": "0",
                 "COACHING_USER_LIMIT_24H": "0", "COACHING_GLOBAL_LIMIT_24H": "0"}
        if self.cluster:
            flags |= {"SLEEP_DB_BACKEND": "postgresql", "DATABASE_URL": self.cluster.url(self.cluster.new_database())}
        else:
            folder = self.enterContext(TemporaryDirectory())
            db_path = Path(folder) / "fixture.sqlite3"
            self.enterContext(patch("health_records.DB_PATH", db_path))
            flags |= {"SLEEP_DB_BACKEND": "sqlite"}
        self.enterContext(patch.dict(os.environ, flags))
        if self.cluster:
            self.assertEqual(postgres_migrate.apply_migrations(), (1, 2, 3, 4, 5, 6))
            self.assertEqual(postgres_migrate.apply_migrations(), ())
        self.client = self.enterContext(TestClient(app))
        self.owner = self.register("manual-owner")
        self.other = self.register("manual-other")

    def register(self, name):
        credentials = {"username": name, "password": "synthetic-tests-only"}
        self.client.post("/auth/register", json=credentials).raise_for_status()
        token = self.client.post("/auth/login", json=credentials).raise_for_status().json()["token"]
        return {"Authorization": "Bearer " + token}

    def manual(self, start="2024-11-15T23:00", end="2024-11-16T07:00",
               timezone="Asia/Seoul", *, headers=None, record_id=None):
        path = "/watch/manual-sessions" + (f"/{record_id}" if record_id else "")
        return self.client.request("PATCH" if record_id else "POST", path, headers=headers or self.owner,
                                   json={"start_local": start, "end_local": end, "timezone": timezone})

    def upload(self, start, end):
        data = {"schema_version": 1, "timezone": "Asia/Seoul", "source": "synthetic-watch",
                "sessions": [{"start": start, "end": end, "segments": [{"stage": "core", "start": start, "end": end}]}]}
        return self.client.post("/analyze", headers=self.owner,
                                files={"file": ("synthetic.json", json.dumps(data), "application/json")})

class ManualSleepTests(ManualSleepFixture, unittest.TestCase):
    def test_record_crud_access_and_concurrent_duplicates(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(lambda _: self.manual().raise_for_status().json(), range(2)))
        self.assertEqual(sorted(reply["created"] for reply in replies), [False, True])
        one, two = (reply["record"] for reply in replies)
        self.assertEqual(one, two)
        self.assertEqual(one["data_type"], "manual")
        self.assertEqual(one["estimated_sleep_minutes"], 480)
        self.assertEqual(one["segments"], [])
        self.assertIsNone(one["asleep_minutes"])
        self.assertIsNone(one["awake_minutes"])
        self.assertEqual(one["stage_minutes"], {})
        record_id = one["analysis_id"]
        path = f"/watch/sessions/{record_id}"
        self.assertEqual(self.client.get(path, headers=self.other).status_code, 404)
        self.assertEqual(self.manual(record_id=record_id, headers=self.other).status_code, 404)
        self.assertEqual(self.client.delete(path, headers=self.other).status_code, 404)
        self.assertEqual(self.client.post("/coach", headers=self.other, json={"analysis_id": record_id}).status_code, 404)
        self.assertEqual(self.manual(start="2024-11-16T02:00", end="2024-11-16T08:00").status_code, 409)
        changed = self.manual(end="2024-11-16T06:30", record_id=record_id).raise_for_status().json()["record"]
        self.assertEqual(changed["analysis_id"], record_id)
        self.assertEqual(changed["estimated_sleep_minutes"], 450)
        self.assertEqual(self.client.get(path, headers=self.owner).json(), changed)
        self.client.delete(path, headers=self.owner).raise_for_status()
        self.assertEqual(self.client.get(path, headers=self.owner).status_code, 404)
        self.assertEqual(self.manual(end="2024-11-16T06:30").status_code, 409)

    def test_timezones_and_invalid_inputs(self):
        for start, end, zone in [
            ("2024-11-15T23:00", "2024-11-15T22:00", "Asia/Seoul"),
            ("2024-11-15T23:00", "2024-11-18T07:00", "Asia/Seoul"),
            ("2024-11-15T23:00", "2024-11-16T07:00", "Invalid/Zone"),
            ("2024-11-15T23:00", "2099-11-16T07:00", "Asia/Seoul"),
            ("2024-03-10T02:30", "2024-03-10T08:00", "America/New_York"),
            ("2024-11-03T01:30", "2024-11-03T08:00", "America/New_York"),
            ("2024-02-30T21:00", "2024-03-01T06:00", "Asia/Seoul"),
        ]:
            with self.subTest(start=start, end=end, zone=zone):
                self.assertEqual(self.manual(start, end, zone).status_code, 400)
        record = self.manual("2024-03-09T23:00", "2024-03-10T07:00", "America/New_York").raise_for_status().json()["record"]
        self.assertEqual(record["estimated_sleep_minutes"], 420)
        self.assertTrue(record["start"].endswith("-05:00"))
        self.assertTrue(record["end"].endswith("-04:00"))

    def test_overlap_and_coaching_do_not_contaminate_measured_history(self):
        prior = self.upload("2024-11-14T23:00:00+09:00", "2024-11-15T07:00:00+09:00")
        wearable_id, = prior.raise_for_status().json()["analysis_ids"]
        self.assertEqual(self.manual("2024-11-15T00:00", "2024-11-15T08:00").status_code, 409)
        self.assertEqual(self.manual(record_id=wearable_id).status_code, 404)
        manual_id = self.manual().raise_for_status().json()["record"]["analysis_id"]
        with patch.object(
            coaching_service, "_generate_openai", side_effect=AssertionError("Wearable adapter cannot process manual records")
        ):
            coaching = self.client.post("/coach", headers=self.owner, json={
                "analysis_id": manual_id, "caffeine": "있음",
            }).raise_for_status().json()
        self.assertIn("추정 수면 시간은 8시간", coaching["coaching"])
        self.assertNotRegex(coaching["coaching"], r"각성|깊은 수면|REM")
        self.assertIn("카페인 섭취 시각", coaching["coaching"])
        self.assertEqual(coaching["context"]["engine"], "manual-rules")
        self.assertEqual(coaching["context"]["record_ids"], [manual_id, wearable_id])
        self.assertEqual(set(coaching["context"]["input_summary"]["selected_record"]),
                         {"start", "end", "timezone", "source", "estimated_sleep_minutes"})
        self.manual(end="2024-11-16T06:45", record_id=manual_id).raise_for_status()
        history = self.client.get(f"/watch/sessions/{manual_id}/coaching", headers=self.owner).json()["history"]
        self.assertEqual(history[0]["coaching"], coaching["coaching"])
        later = self.upload("2024-11-15T23:15:00+09:00", "2024-11-16T06:50:00+09:00")
        later_id, = later.raise_for_status().json()["analysis_ids"]
        sessions = self.client.get("/watch/sessions", headers=self.owner).raise_for_status().json()
        self.assertEqual(len(sessions["sessions"]), 3)
        self.assertEqual(sessions["overview"]["session_count"], 2)
        automated = self.client.post("/coach", headers=self.owner, json={
            "analysis_id": later_id,
        }).raise_for_status().json()
        self.assertEqual(automated["context"]["engine"], "rules")
        self.assertNotIn(manual_id, automated["context"]["record_ids"])
        self.client.post("/alarms", headers=self.owner, json={
            "bedtime": "23:00", "wake_time": "07:00", "timezone": "Asia/Seoul", "enabled": False,
        }).raise_for_status()
        owner_id = self.client.get("/auth/me", headers=self.owner).json()["user"]["id"]
        recommendation = morning_plans.recommend_bedtime(owner_id, now=datetime(2024,11,16,5,tzinfo=timezone.utc))
        self.assertEqual(recommendation["valid_nights"], 2)
