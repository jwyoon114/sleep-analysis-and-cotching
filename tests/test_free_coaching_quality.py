from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from itertools import product
import json
import os
import sqlite3
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import account_personalization as personalization
from coaching_expression import expression_snapshot
from coaching_session import VERSION, MBTI_STRATEGIES, analyze_session, render_session
import coaching_service
import health_records
from free_coaching_scenarios import night, variable_nights
from test_manual_sleep import ManualSleepFixture


class EvidenceAndDeliveryTests(unittest.TestCase):
    def test_all_types_tones_consent_sources_and_habits_keep_facts(self):
        outputs = {}
        cases = 0
        for manual, many, habits in product((False, True), (False, True), ({}, {"caffeine": "있음", "satisfaction": "나쁨"})):
            selected, recent = variable_nights(manual=manual)
            recent = recent if many else []
            analysis = analyze_session(selected, recent, habits)
            saved = deepcopy(analysis)
            for speech, intensity, allowed in product(("polite", "casual"), ("gentle", "firm", "direct"), (False, True)):
                observations = set()
                strategies = set()
                for mbti in MBTI_STRATEGIES:
                    expression = expression_snapshot(dict(mbti=mbti, speech=speech, intensity=intensity, allow_profanity=allowed))
                    body = render_session(analysis, habits, expression)
                    observations.add(body.split("\n\n")[0])
                    strategies.add(body.split("실행 방법 · ")[1].split("\n")[0])
                    self.assertEqual(expression["allow_profanity"], allowed)
                    self.assertNotIn(mbti, body)  # No substituting type names for actual strategies.
                    self.assertNotIn("수면 패턴", body)
                    self.assertNotIn("input_summary", body)
                    self.assertNotRegex(body, r"불면증|수면의 질이|게으르|한심|의지가|네 탓|너 때문|심박|REM")
                    if not allowed:
                        self.assertNotIn("젠장", body)
                    if manual:
                        self.assertIn("추정 수면 시간", body)
                        self.assertNotIn("기기가 기록", body)
                    self.assertEqual(analysis, saved)
                    cases += 1
                self.assertEqual(len(observations), 1)
                self.assertEqual(len(strategies), 16)
                outputs[manual, many, bool(habits), speech, intensity, allowed] = body
        self.assertEqual(cases, 1536)
        for speech in ("polite", "casual"):
            a, b, c = [outputs[True, True, False, speech, intensity, consent]
                       for intensity, consent in (("gentle", False), ("direct", False), ("direct", True))]
            self.assertEqual(len({a, b, c}), 3)
            self.assertNotIn("젠장", a + b)
            self.assertIn("젠장", c)
            # A stable single record does not force profanity even with consent.
            self.assertNotIn("젠장", outputs[True, False, False, speech, "direct", True])

    def test_priority_is_grounded_and_no_unentered_habit_is_claimed(self):
        selected, recent = variable_nights()
        analysis = analyze_session(selected, recent, {"caffeine": "있음", "satisfaction": "나쁨"})
        self.assertEqual(analysis["focus"], "start_variation")
        self.assertEqual(analysis["actions"], ["start_variation", "caffeine"])
        self.assertEqual(analysis["facts"]["start_spread_minutes"], 90)
        self.assertEqual(analysis["facts"]["end_spread_minutes"], 0)
        body = render_session(analyze_session(selected, [], {}), {}, expression_snapshot(None))
        self.assertNotIn("카페인", body)
        self.assertNotIn("만족도", body)
        self.assertNotIn("성인", body)
        self.assertIn("07:00", body)
        self.assertEqual(analyze_session(selected, recent, {})["focus"], "start_variation")

    def test_shorter_is_same_source_average_not_recorded_window(self):
        selected = night(15, "23:00", 440, manual=False)
        selected["asleep_minutes"] = 400
        recent = [night(14, minutes=440, manual=False), night(13, minutes=440, manual=False), night(12, minutes=900)]
        result = analyze_session(selected, recent, {})
        self.assertEqual(result["facts"]["previous_average_minutes"], 440)
        self.assertEqual(result["facts"]["difference_minutes"], -40)
        self.assertEqual(result["focus"], "shorter")
        self.assertEqual(result["facts"]["sample_days"], 3)

    def test_midnight_utc_encoding_and_dst(self):
        selected, recent = night(15, "00:10", 420), [night(13, "23:50", 440), night(12, "23:55", 435)]
        result = analyze_session(selected, recent, {})
        self.assertEqual(result["facts"]["start_spread_minutes"], 20)
        encoded = deepcopy(selected)
        encoded["start"] = datetime.fromisoformat(selected["start"]).astimezone(timezone.utc).isoformat()
        encoded["end"] = datetime.fromisoformat(selected["end"]).astimezone(timezone.utc).isoformat()
        self.assertEqual(analyze_session(encoded, recent, {}), result)
        dst = {**night(), "start": "2024-03-09T23:00:00-05:00", "end": "2024-03-10T07:00:00-04:00",
               "timezone": "America/New_York", "estimated_sleep_minutes": 420}
        prior = [{**night(12), "start": "2024-03-08T23:00:00-05:00", "end": "2024-03-09T07:00:00-05:00",
                  "timezone": "America/New_York", "estimated_sleep_minutes": 480}]
        facts = analyze_session(dst, prior, {})["facts"]
        self.assertEqual(facts["window_minutes"], 420)
        self.assertFalse(facts["timing_comparable"])
        self.assertIsNone(facts["start_spread_minutes"])

    def test_travel_split_ambiguous_future_and_old_records_do_not_define_routine(self):
        selected, recent = variable_nights()
        travel = analyze_session(selected, [{**recent[0], "timezone": "America/New_York"}, recent[1]], {})
        self.assertIsNone(travel["facts"]["start_spread_minutes"])
        self.assertIsNone(travel["facts"]["previous_average_minutes"])
        split = analyze_session(night(15, "23:00", 420), [night(14, "13:00", 60), {**night(14, "23:00", 420), "analysis_id": "synthetic-split"}], {})
        self.assertIsNone(split["facts"]["previous_average_minutes"])
        self.assertFalse(split["facts"]["timing_comparable"])
        duplicates = analyze_session(selected, [recent[0], deepcopy(recent[0]), night(16), night(1)], {})
        self.assertEqual(duplicates["facts"]["sample_days"], 1)
        self.assertEqual(duplicates["facts"]["excluded_history"], 4)
        overlap = analyze_session(night(16), [night(14, "23:00", 480), {**night(13), "start": "2024-11-15T01:00:00+09:00", "end": "2024-11-15T08:00:00+09:00"}], {})
        self.assertEqual(overlap["facts"]["sample_days"], 1)

    def test_missing_duration_does_not_invent_sleep_and_consent_is_not_mandatory_profanity(self):
        selected = night(manual=False)
        selected["asleep_minutes"] = None
        result = analyze_session(selected, [], {})
        self.assertIsNone(result["facts"]["sleep_minutes"])
        self.assertEqual(result["focus"], "check_record")
        body = render_session(result, {}, expression_snapshot(dict(speech="casual", intensity="direct", allow_profanity=True)))
        self.assertNotIn("약 7시간", body)
        self.assertNotIn("젠장", body)
        self.assertIn("밤 전체 기록", body)

    def test_repeated_later_requires_explicit_usual_time_and_three_days(self):
        selected = night(15, "00:50", 420)
        recent = [night(14, "00:50", 420), night(13, "00:50", 420)]
        self.assertEqual(analyze_session(selected, recent, {})["focus"], "track_wake")
        result = analyze_session(selected, recent, {"usual_bedtime": "23:30"})
        self.assertEqual((result["focus"], result["facts"]["late_count"]), ("repeated_later", 3))
        self.assertNotEqual(analyze_session(selected, recent[:1], {"usual_bedtime": "23:30"})["focus"], "repeated_later")


class FreeCoachingPersistenceTests(ManualSleepFixture, unittest.TestCase):
    choices = dict(mbti="ISTJ", speech="polite", intensity="gentle", character="cat", allow_profanity=False)

    def setup_profile(self):
        self.client.post("/auth/personalization", headers=self.owner, json=self.choices).raise_for_status()

    def free(self, record_id):
        return self.client.post("/coach/free", headers=self.owner, json={"analysis_id": record_id}).raise_for_status().json()

    def test_settings_each_invalidate_cache_and_history_stays_exact(self):
        self.setup_profile()
        sid = self.manual().raise_for_status().json()["record"]["analysis_id"]
        original = self.free(sid)
        settings = self.choices.copy()
        snapshots = [original]
        for key, value in (("mbti", "ENFP"), ("speech", "casual"), ("intensity", "direct"), ("allow_profanity", True)):
            settings[key] = value
            self.client.patch("/auth/personalization", headers=self.owner, json=settings).raise_for_status()
            item = self.free(sid)
            self.assertNotIn(item["id"], [s["id"] for s in snapshots])
            self.assertFalse(item["reused"])
            self.assertEqual(self.free(sid)["id"], item["id"])
            snapshots.append(item)
        settings["character"] = "rabbit"
        self.client.patch("/auth/personalization", headers=self.owner, json=settings).raise_for_status()
        self.assertEqual(self.free(sid)["id"], snapshots[-1]["id"])
        stored = self.client.get(f"/watch/sessions/{sid}/coaching", headers=self.owner).raise_for_status().json()["history"]
        self.assertEqual({s["id"]: s["coaching"] for s in stored}, {s["id"]: s["coaching"] for s in snapshots})
        self.assertNotIn("free_analysis", original["context"])
        self.assertNotIn("input_summary", original["context"])
        self.assertEqual(self.client.post("/coach/free", headers=self.other, json={"analysis_id": sid}).status_code, 404)

    def test_consent_is_independent_and_persists_across_login_and_client(self):
        self.setup_profile()
        settings = {**self.choices, "allow_profanity": True}
        for intensity in ("gentle", "firm", "direct"):
            settings["intensity"] = intensity
            self.client.patch("/auth/personalization", headers=self.owner, json=settings).raise_for_status()
            self.assertTrue(self.client.get("/auth/personalization", headers=self.owner).json()["personalization"]["allow_profanity"])
        with TestClient(self.client.app) as device:
            login = device.post("/auth/login", json={"username": "manual-owner", "password": "synthetic-tests-only"}).raise_for_status().json()
            headers = {"Authorization": "Bearer " + login["token"]}
            profile = device.get("/auth/personalization", headers=headers).raise_for_status().json()["personalization"]
            self.assertEqual({k: profile[k] for k in settings}, settings)
            device.post("/auth/logout", headers=headers).raise_for_status()
            self.assertEqual(device.get("/auth/personalization", headers=headers).status_code, 401)

    def test_concurrent_reuse_record_revision_history_and_engine_version(self):
        self.setup_profile()
        first = self.manual().raise_for_status().json()["record"]["analysis_id"]
        with patch("openai.OpenAI", side_effect=AssertionError("External provider forbidden")):
            with ThreadPoolExecutor(max_workers=4) as pool:
                items = list(pool.map(lambda _: self.free(first), range(4)))
        self.assertEqual(len({i["id"] for i in items}), 1)
        self.assertEqual(sum(not i["reused"] for i in items), 1)
        original = items[0]
        self.client.patch("/coach/preferences", headers=self.owner, json={"age_group": "성인"}).raise_for_status()
        # Input snapshot changed even when text didn't: never attach a new snapshot to an old row.
        changed = self.free(first)
        self.assertNotEqual(changed["id"], original["id"])
        with closing(health_records.connect()) as db, db:
            row = db.execute("SELECT payload FROM sessions WHERE id=?", (first,)).fetchone()
            payload = json.loads(row[0]); payload["fixture_revision"] = "synthetic-only"
            db.execute("UPDATE sessions SET payload=? WHERE id=?", (json.dumps(payload), first))
        revision = self.free(first)
        self.assertNotEqual(revision["id"], changed["id"])
        with patch.object(coaching_service, "FREE_VERSION", VERSION + "-test"):
            self.assertNotEqual(self.free(first)["id"], revision["id"])
        next_id = self.manual("2024-11-16T23:00", "2024-11-17T07:00").raise_for_status().json()["record"]["analysis_id"]
        other_id = self.manual("2024-11-14T23:00", "2024-11-15T07:00", headers=self.other).raise_for_status().json()["record"]["analysis_id"]
        self.free(next_id)
        owner_id = self.client.get("/auth/me", headers=self.owner).json()["user"]["id"]
        latest = coaching_service.latest_coaching(owner_id, next_id)
        self.assertIn(first, latest["context"]["record_ids"])
        self.assertNotIn(other_id, latest["context"]["record_ids"])
        self.assertEqual(latest["context"]["prompt_version"], VERSION)

    def test_legacy_sqlite_consent_upgrade_preserves_every_row_and_fk(self):
        if self.cluster:
            self.skipTest("SQLite-specific legacy schema test")
        self.setup_profile()
        account_id = self.client.get("/auth/me", headers=self.owner).json()["user"]["id"]
        original = personalization.get_personalization(account_id)
        with closing(health_records.connect()) as db, db:
            db.execute("DROP TABLE account_personalization")
            legacy = personalization._SQLITE_SCHEMA.replace("completed_at TEXT NOT NULL", "completed_at TEXT NOT NULL, CHECK (NOT allow_profanity OR intensity = 'direct')")
            db.execute(legacy)
            db.execute("INSERT INTO account_personalization VALUES(?,?,?,?,?,?,?)", (account_id, *[original[k] for k in ("mbti", "speech", "intensity", "allow_profanity", "character", "completed_at")]))
        self.assertEqual(personalization.get_personalization(account_id), original)
        personalization.save_personalization(account_id, personalization.Preferences(**{**self.choices, "allow_profanity": True}))
        self.assertTrue(personalization.get_personalization(account_id)["allow_profanity"])
        with closing(health_records.connect()) as db:
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_legacy_sqlite_upgrade_failure_rolls_back_without_losing_choices(self):
        if self.cluster:
            self.skipTest("SQLite-specific rollback test")
        self.setup_profile()
        account_id = self.client.get("/auth/me", headers=self.owner).json()["user"]["id"]
        original = personalization.get_personalization(account_id)
        with closing(health_records.connect()) as db, db:
            db.execute("DROP TABLE account_personalization")
            legacy = personalization._SQLITE_SCHEMA.replace("completed_at TEXT NOT NULL", "completed_at TEXT NOT NULL, CHECK (NOT allow_profanity OR intensity = 'direct')")
            db.execute(legacy)
            values = (account_id, *[original[k] for k in ("mbti", "speech", "intensity", "allow_profanity", "character", "completed_at")])
            db.execute("INSERT INTO account_personalization VALUES(?,?,?,?,?,?,?)", values)
            db.execute(personalization._SQLITE_SCHEMA.replace("account_personalization", "account_personalization_consent_upgrade"))
            db.execute("INSERT INTO account_personalization_consent_upgrade VALUES(?,?,?,?,?,?,?)", values)
        with self.assertRaises(sqlite3.IntegrityError):
            personalization.get_personalization(account_id)
        with closing(health_records.connect()) as db:
            self.assertEqual(tuple(db.execute("SELECT * FROM account_personalization").fetchone()), values)
            self.assertIn("NOT allow_profanity OR intensity", db.execute("SELECT sql FROM sqlite_master WHERE name='account_personalization'").fetchone()[0])
