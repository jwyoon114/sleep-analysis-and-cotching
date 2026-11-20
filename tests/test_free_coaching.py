from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import unittest

import coaching_service
from test_manual_sleep import ManualSleepFixture


class FreeCoachingTests(ManualSleepFixture, unittest.TestCase):
    def free(self, record_id, headers=None):
        return self.client.post("/coach/free", headers=headers or self.owner,
                                json={"analysis_id": record_id})

    def test_manual_free_reuses_inputs_and_regenerates_after_edit(self):
        record_id = self.manual().raise_for_status().json()["record"]["analysis_id"]
        with patch.object(coaching_service, "request_response", side_effect=AssertionError("provider called")):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: self.free(record_id).raise_for_status().json(), range(2)))
        self.assertEqual({result["id"] for result in results}, {results[0]["id"]})
        self.assertEqual(sorted(result["reused"] for result in results), [False, True])
        result = results[0]
        self.assertIn("약 8시간", result["coaching"])
        self.assertIn("평소 경향은 아직 판단하기 어려워요", result["coaching"])
        self.assertNotIn("수면 패턴", result["coaching"])
        self.assertNotIn("input_summary", result["context"])
        path = f"/watch/sessions/{record_id}/coaching"
        self.assertEqual(len(self.client.get(path, headers=self.owner).json()["history"]), 1)
        self.assertIn("input_summary", self.client.get(path, headers=self.owner).json()["result"]["context"])
        self.assertNotIn("input_summary", self.client.get(path + "?view=summary", headers=self.owner).json()["result"]["context"])
        self.manual(end="2024-11-16T06:15", record_id=record_id).raise_for_status()
        changed = self.free(record_id).raise_for_status().json()
        self.assertNotEqual(result["id"], changed["id"])
        self.assertIn("약 7시간 15분", changed["coaching"])
        self.assertEqual(self.free(record_id, self.other).status_code, 404)

    def test_settings_follow_account_and_daily_input_stays_on_selected_night(self):
        prefs = "/coach/preferences"
        self.client.patch(prefs, headers=self.owner, json={"usual_wake_time": "06:45"}).raise_for_status()
        self.assertIsNone(self.client.get(prefs, headers=self.other).json()["usual_wake_time"])
        first = self.manual().raise_for_status().json()["record"]["analysis_id"]
        habits = f"/coach/habits/{first}"
        self.client.patch(habits, headers=self.owner, json={"caffeine": "있음"}).raise_for_status()
        self.assertEqual(self.client.get(habits, headers=self.other).status_code, 404)
        self.assertEqual(self.client.get(habits, headers=self.owner).json()["habits"],
                         {"caffeine": "있음", "satisfaction": None})
        first_advice = self.free(first).raise_for_status().json()["coaching"]
        self.assertIn("카페인", first_advice)
        self.assertNotIn("만족도", first_advice)
        second = self.manual("2024-11-16T23:00", "2024-11-17T07:00").raise_for_status().json()["record"]["analysis_id"]
        next_advice = self.free(second).raise_for_status().json()["coaching"]
        self.assertIn("06:45", next_advice)
        self.assertNotIn("카페인", next_advice)

    def test_uploaded_and_manual_histories_distinguish_consistency_and_shorter_duration(self):
        intervals = [
            ("2024-11-11T23:00:00+09:00", "2024-11-12T07:00:00+09:00"),
            ("2024-11-12T23:00:00+09:00", "2024-11-13T07:00:00+09:00"),
            ("2024-11-13T23:00:00+09:00", "2024-11-14T06:20:00+09:00"),
            ("2024-11-14T21:30:00+09:00", "2024-11-15T07:00:00+09:00"),
        ]
        ids = [self.upload(*interval).raise_for_status().json()["analysis_ids"][0] for interval in intervals]
        shorter = self.free(ids[2]).raise_for_status().json()["coaching"]
        variable = self.free(ids[3]).raise_for_status().json()["coaching"]
        self.assertIn("약 7시간 20분", shorter)
        self.assertIn("평균보다 약 40분 짧았어요", shorter)
        self.assertIn("시각이 약 1시간 30분 차이", variable)
        self.assertNotIn("데이터 한계", variable)
        manual_id = self.manual().raise_for_status().json()["record"]["analysis_id"]
        mixed = self.free(manual_id).raise_for_status().json()["coaching"]
        self.assertIn("직접 입력", mixed)
        self.assertNotIn("평균보다", mixed)
