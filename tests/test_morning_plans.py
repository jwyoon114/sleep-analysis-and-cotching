"""Sleep plans with synthetic records, an isolated SQLite database and authenticated HTTP."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import api
import health_records
import morning_plans as plans
import sleep_accounts
import sleep_alarms


class MorningPlanTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {
            "SLEEP_DB_BACKEND": "sqlite", "SLEEP_DESKTOP_ALARMS": "0", "DALJAM_ENV": "test",
        }))
        os.environ.pop("DATABASE_URL", None)
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.db = Path(directory) / "plans.sqlite"
        self.enterContext(patch.object(health_records, "DB_PATH", self.db))
        self.account = sleep_accounts.register("plan-a-test", "synthetic-password")["id"]
        self.other = sleep_accounts.register("plan-b-test", "synthetic-password")["id"]
        self.now = datetime.fromisoformat("2026-11-15T12:00:00+09:00")
        self.today = self.now.date()
        self.tomorrow = self.today + timedelta(days=1)

    def schedule(self, zone="Asia/Seoul", wake="07:00"):
        return sleep_alarms.save_settings(self.account, "22:00", wake, zone, False, db_path=self.db)

    def request(self, *titles):
        return plans.PlanRequest(activities=[{"id": f"a-{i}", "title": title} for i, title in enumerate(titles)])

    def insert(self, start, end, asleep, identifier=None):
        row = {"start": start, "end": end, "asleep_minutes": asleep, "timezone": "Asia/Seoul"}
        with closing(health_records.connect(self.db)) as db, db:
            db.execute("INSERT INTO sessions VALUES(?,?,?,?,?)",
                       (identifier or start, self.account, start, end, json.dumps(row)))

    def test_recommendation_uses_median_across_midnight_and_keeps_goals_untouched(self):
        self.assertFalse(sleep_alarms.get_settings(self.account, self.db)["saved"])
        self.assertEqual(plans.recommend_bedtime(self.account, self.now, self.db)["status"], "no_goal")
        self.schedule("Asia/Seoul")
        self.insert("2026-11-10T23:20:00+09:00", "2026-11-11T07:20:00+09:00", 451)
        self.insert("2026-11-12T00:15:00+09:00", "2026-11-12T08:15:00+09:00", 440)
        self.assertEqual(plans.recommend_bedtime(self.account, self.now, self.db)["status"], "insufficient")
        self.insert("2026-11-12T14:55:00+00:00", "2026-11-12T22:55:00+00:00", 455)
        self.insert("2026-11-12T14:55:00+00:00", "2026-11-12T22:55:00+00:00", 455, "duplicate")
        self.insert("2026-10-21T23:20:00+09:00", "2026-10-22T07:20:00+09:00", 400)
        self.insert("2026-11-15T23:20:00+09:00", "2026-11-16T07:20:00+09:00", 400)
        recommendation = plans.recommend_bedtime(self.account, self.now, self.db)
        self.assertEqual(recommendation, {
            "status": "available", "valid_nights": 3, "minimum_nights": 3, "lookback_days": 14,
            "bedtime": "23:00", "bed_date": "2026-11-15", "wake_date": "2026-11-16", "wake_time": "07:00",
            "timezone": "Asia/Seoul", "window_minutes": 480, "sleep_minutes": 451,
            "start_typical": "23:55", "end_typical": "07:55",
        })
        self.assertEqual(sleep_alarms.get_settings(self.account, self.db)["bedtime"], "22:00")
        sleep_alarms.save_settings(self.account, recommendation["bedtime"], "07:00", "Asia/Seoul", False, db_path=self.db)
        self.assertEqual(sleep_alarms.get_settings(self.account, self.db)["bedtime"], "23:00")
        self.insert("2026-11-12T23:05:00+09:00", "2026-11-13T06:55:00+09:00", 430)
        self.assertEqual(plans.recommend_bedtime(self.account, self.now, self.db)["valid_nights"], 2)
        self.assertEqual(plans.recommend_bedtime(self.other, self.now, self.db)["valid_nights"], 0)

    def test_order_completion_activity_history_and_account_boundary(self):
        self.schedule()
        early = self.now - timedelta(days=2)
        plans.save(self.account, early.date(), self.request("개인 활동", "물 한 잔 마시기"), early, self.db)
        saved = plans.save(self.account, self.tomorrow, self.request("개인 활동", "가벼운 스트레칭"), self.now, self.db)
        done = plans.mark(self.account, self.tomorrow, plans.CompletionRequest(id="a-0", completed=True), self.db)
        self.assertTrue(done["activities"][0]["completed"])
        order = plans.PlanRequest(activities=[{"id": v["id"], "title": v["title"]} for v in reversed(saved["activities"])])
        changed = plans.save(self.account, self.tomorrow, order, self.now, self.db)
        self.assertEqual([(item["title"], item["completed"]) for item in changed["activities"]],
                         [("가벼운 스트레칭", False), ("개인 활동", True)])
        view = plans.overview(self.account, self.now, self.db)
        self.assertEqual(view["next_plan"], changed)
        self.assertEqual(view["suggestions"][0], {"title": "개인 활동", "days": 1})
        self.assertEqual(plans.overview(self.other, self.now, self.db)["suggestions"][0]["days"], 0)
        with self.assertRaises(LookupError):
            plans.mark(self.other, self.tomorrow, plans.CompletionRequest(id="a-0", completed=False), self.db)
        self.assertFalse(plans.remove(self.other, self.tomorrow, self.db))
        self.assertTrue(plans.remove(self.account, self.tomorrow, self.db))
        self.assertIsNone(plans.overview(self.account, self.now, self.db)["next_plan"])

    def test_morning_claim_is_once_per_date_even_when_recreated(self):
        self.schedule()
        before = self.now.replace(hour=6, minute=59)
        self.assertEqual(plans.overview(self.account, before, self.db)["next_date"], self.today.isoformat())
        plans.save(self.account, self.today, self.request("오늘 계획"), before, self.db)
        plans.save(self.account, self.tomorrow, self.request("내일 계획"), self.now, self.db)
        self.assertIsNone(plans.claim_morning_view(self.account, before, self.db))
        self.assertIsNone(plans.claim_morning_view(self.other, self.now, self.db))
        with ThreadPoolExecutor(max_workers=4) as pool:
            result = list(pool.map(lambda _: plans.claim_morning_view(self.account, self.now, self.db), range(4)))
        shown, = [plan for plan in result if plan]
        self.assertEqual(shown["date"], self.today.isoformat())
        self.assertEqual(shown["activities"][0]["title"], "오늘 계획")
        self.assertTrue(plans.remove(self.account, self.today, self.db))
        plans.save(self.account, self.today, self.request("다시 작성한 계획"), self.now, self.db)
        self.assertIsNone(plans.claim_morning_view(self.account, self.now, self.db))
        next_day = plans.claim_morning_view(self.account, self.now + timedelta(days=1), self.db)
        self.assertEqual(next_day["activities"][0]["title"], "내일 계획")

    def test_repeated_hour_uses_earliest_occurrence_in_user_timezone(self):
        self.schedule("America/New_York", "01:30")
        before = datetime(2026, 11, 1, 5, 29, tzinfo=timezone.utc)
        late_repeat = datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc)
        first = date(2026, 11, 1)
        plans.save(self.account, first, self.request("시차 검증"), before, self.db)
        self.assertIsNone(plans.claim_morning_view(self.account, before, self.db))
        self.assertEqual(plans.claim_morning_view(self.account, late_repeat, self.db)["date"], first.isoformat())
        self.assertIsNone(plans.claim_morning_view(self.account, late_repeat, self.db))

    def test_http_and_account_data_persist_on_sign_in(self):
        with TestClient(api.app) as client:
            login = lambda: {"Authorization": "Bearer " + client.post("/auth/login", json={
                "username": "plan-a-test", "password": "synthetic-password"}).json()["token"]}
            first = login()
            self.assertEqual(client.get("/plans").status_code, 401)
            self.assertFalse(client.get("/alarms", headers=first).json()["saved"])
            self.assertTrue(client.post("/alarms", headers=first, json={
                "bedtime": "23:15", "wake_time": "00:00", "timezone": "Asia/Seoul", "enabled": False,
            }).json()["saved"])
            next_date = client.get("/plans", headers=first).json()["next_date"]
            path = "/plans/" + next_date
            request = {"activities": [{"id": "stretch", "title": "스트레칭"}]}
            self.assertEqual(client.post(path, headers=first, json=request).status_code, 200)
            self.assertEqual(client.post(path, headers=first, json={"activities": request["activities"] * 2}).status_code, 422)
            client.post("/auth/logout", headers=first).raise_for_status()
            second = login()
            self.assertEqual(client.get("/plans", headers=second).json()["next_plan"]["activities"][0]["title"], "스트레칭")
            self.assertTrue(client.patch(path, headers=second, json={"id": "stretch", "completed": True}).json()["plan"]["activities"][0]["completed"])
            self.assertEqual(client.delete(path, headers=second).status_code, 200)
            self.assertIsNone(client.get("/plans", headers=second).json()["next_plan"])
