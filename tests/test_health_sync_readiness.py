"""Contract regression tests with fabricated data and a disposable SQLite DB."""

from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import api
import health_records


SAMSUNG = "com.sec.android.app.shealth"
OWNER = "synthetic-owner"
OTHER = "synthetic-other"


def stage(start, end, kind):
    return {"start": start, "end": end, "stage": kind}


def session(record_id, start, end, segments):
    return {"id": record_id, "start": start, "end": end, "segments": segments}


def full_night():
    return session("full", "2025-11-01T22:00:00+09:00", "2025-11-02T06:00:00+09:00", [
        stage("2025-11-01T22:00:00+09:00", "2025-11-02T01:00:00+09:00", "core"),
        stage("2025-11-02T01:00:00+09:00", "2025-11-02T02:30:00+09:00", "deep"),
        stage("2025-11-02T02:30:00+09:00", "2025-11-02T02:50:00+09:00", "wake"),
        stage("2025-11-02T02:50:00+09:00", "2025-11-02T04:30:00+09:00", "rem"),
        stage("2025-11-02T04:30:00+09:00", "2025-11-02T06:00:00+09:00", "unspecified"),
    ])


class HealthSyncReadinessTests(unittest.TestCase):
    def setUp(self):
        root = Path(self.enterContext(TemporaryDirectory()))
        self.database = root / "health-readiness.sqlite3"
        self.enterContext(patch.object(health_records, "DB_PATH", self.database))
        self.enterContext(patch.dict(os.environ, {
            "SLEEP_DB_BACKEND": "sqlite", "SLEEP_DESKTOP_ALARMS": "0", "COACHING_ENGINE": "rules",
        }))
        self.web = {}
        with closing(health_records.connect(self.database)) as db, db:
            for account in (OWNER, OTHER):
                db.execute("INSERT INTO accounts VALUES(?,?,?,?,?)", (account, account, "fixture", "fixture", "2025-10-27"))
                token = f"synthetic-web-session-for-{account}"
                expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
                db.execute("INSERT INTO auth_tokens VALUES(?,?,?)", (health_records.digest(token), account, expires))
                self.web[account] = {"Authorization": f"Bearer {token}"}
        self.http = self.enterContext(TestClient(api.app))
        paired = self.http.post("/watch/health/connection", headers=self.web[OWNER], json={
            "provider": "health_connect", "source_id": SAMSUNG, "source_name": "Synthetic Samsung Health",
            "auto_coach": False,
        }).raise_for_status().json()
        self.native = {"Authorization": "Bearer " + paired["sync_token"]}

    def sync(self, *records, zone="Asia/Seoul", complete=False, headers=None):
        return self.http.post("/mobile/health-sync", headers=self.native if headers is None else headers, json={
            "provider": "health_connect", "source_id": SAMSUNG, "timezone": zone,
            "window_start": "2025-10-28T00:00:00Z", "window_end": "2025-11-06T00:00:00Z",
            "records": records, "complete_snapshot": complete,
        })

    def records(self, account=OWNER):
        return self.http.get("/watch/sessions", headers=self.web[account]).raise_for_status().json()["sessions"]

    def upload(self, value, filename="synthetic.json"):
        payload = value if isinstance(value, str) else json.dumps(value)
        return self.http.post("/analyze", headers=self.web[OWNER], files={"file": (filename, payload, "application/json")})

    def test_complete_night_crosses_midnight_and_counts_wake_separately(self):
        reply = self.sync(full_night()).raise_for_status().json()
        self.assertEqual((reply["added_sessions"], reply["ignored_incomplete"]), (1, 0))
        record, = self.records()
        self.assertEqual(record["health_sync"]["day"], "2025-11-01")
        self.assertEqual(record["recorded_minutes"], 480)
        self.assertEqual(record["asleep_minutes"], 460)
        self.assertEqual(record["awake_minutes"], 20)
        self.assertEqual(record["unrecorded_minutes"], 0)
        self.assertEqual(record["wake_segment_count"], 1)
        self.assertEqual(record["stage_minutes"], {"core": 180, "deep": 90, "wake": 20, "rem": 100, "unspecified": 90})
        self.assertEqual(self.records(OTHER), [])

    def test_stage_less_session_is_acknowledged_without_analysis(self):
        no_stages = full_night() | {"segments": []}
        reply = self.sync(no_stages).raise_for_status().json()
        self.assertEqual(reply["ignored_incomplete"], 1)
        self.assertEqual(reply["added_sessions"], 0)
        self.assertEqual(reply["analysis_ids"], [])
        self.assertFalse(reply["advice_queued"])
        self.assertTrue(reply["last_synced_at"])
        self.assertEqual(self.records(), [])

    def test_mixed_snapshot_stores_only_the_measured_session(self):
        empty = session("stage-less", "2025-11-03T22:30:00+09:00", "2025-11-04T06:30:00+09:00", [])
        reply = self.sync(full_night(), empty, complete=True).raise_for_status().json()
        self.assertEqual((reply["added_sessions"], reply["ignored_incomplete"]), (1, 1))
        record, = self.records()
        self.assertEqual(record["health_sync"]["day"], "2025-11-01")

    def test_partial_stages_exclude_gaps_and_outer_unmeasured_boundaries(self):
        partial = full_night() | {"segments": [
            stage("2025-11-01T22:30:00+09:00", "2025-11-02T01:00:00+09:00", "core"),
            stage("2025-11-02T02:00:00+09:00", "2025-11-02T02:10:00+09:00", "wake"),
            stage("2025-11-02T04:00:00+09:00", "2025-11-02T05:00:00+09:00", "rem"),
        ]}
        reply = self.sync(partial).raise_for_status().json()
        self.assertEqual(reply["ignored_incomplete"], 0)
        record, = self.records()
        self.assertEqual((record["start"], record["end"]), (partial["segments"][0]["start"], partial["segments"][-1]["end"]))
        self.assertEqual((record["recorded_minutes"], record["asleep_minutes"], record["awake_minutes"], record["unrecorded_minutes"]),
                         (390, 210, 10, 170))
        self.assertEqual(sum(record["stage_minutes"].values()), 220)
        self.assertEqual(record["stage_minutes"]["deep"], 0)
        self.assertEqual(record["stage_minutes"]["unspecified"], 0)
        self.assertEqual(len(record["segments"]), 3)

    def test_empty_snapshots_preserve_records_and_existing_coaching(self):
        empty = self.sync(complete=True).raise_for_status().json()
        self.assertEqual((empty["added_sessions"], empty["ignored_incomplete"], empty["removed_sessions"]), (0, 0, 0))
        self.assertEqual(empty["analysis_ids"], [])
        self.assertEqual(self.records(), [])

        result = self.sync(full_night()).raise_for_status().json()
        saved_id, = result["analysis_ids"]
        before = self.http.post("/coach", headers=self.web[OWNER], json={"analysis_id": saved_id}).raise_for_status().json()
        recorded, = self.records()
        latest_empty = self.sync(complete=True).raise_for_status().json()
        self.assertEqual(latest_empty["removed_sessions"], 0)
        self.assertEqual(self.records(), [recorded])
        saved, = self.http.get(f"/watch/sessions/{saved_id}/coaching", headers=self.web[OWNER]).raise_for_status().json()["history"]
        self.assertEqual(saved["coaching"], before["coaching"])

    def test_repeat_and_same_stage_overlap_are_idempotent(self):
        duplicate_stage = session("overlap", "2025-11-01T22:00:00+09:00", "2025-11-02T00:00:00+09:00", [
            stage("2025-11-01T22:00:00+09:00", "2025-11-02T00:00:00+09:00", "core"),
        ])
        first = self.sync(full_night(), duplicate_stage).raise_for_status().json()
        again = self.sync(duplicate_stage, full_night()).raise_for_status().json()
        self.assertEqual(again["analysis_ids"], first["analysis_ids"])
        self.assertEqual((again["added_sessions"], again["updated_sessions"]), (0, 0))
        record, = self.records()
        self.assertEqual(record["stage_minutes"]["core"], 180)
        self.assertEqual(record["asleep_minutes"], 460)
        conflicting = deepcopy(duplicate_stage)
        conflicting["segments"][0]["stage"] = "rem"
        self.assertEqual(self.sync(full_night(), conflicting).status_code, 400)
        self.assertEqual(self.records(), [record])

    def test_fragmented_sessions_are_grouped_without_filling_the_interval(self):
        a = "2025-11-01T23:00:00+09:00"
        b = "2025-11-02T01:00:00+09:00"
        c = "2025-11-02T03:00:00+09:00"
        d = "2025-11-02T05:00:00+09:00"
        head = session("head", a, b, [stage(a, b, "core")])
        tail = session("tail", c, d, [stage(c, d, "core")])
        self.sync(tail, head).raise_for_status()
        record, = self.records()
        self.assertEqual(len(record["segments"]), 2)
        self.assertEqual((record["recorded_minutes"], record["asleep_minutes"], record["unrecorded_minutes"]), (360, 240, 120))

    def test_local_noon_splits_a_crossing_segment(self):
        a, b = "2025-11-02T11:45:00+09:00", "2025-11-02T12:15:00+09:00"
        reply = self.sync(session("noon", a, b, [stage(a, b, "unspecified")])).raise_for_status().json()
        self.assertEqual(reply["added_sessions"], 2)
        self.assertEqual({r["health_sync"]["day"]: r["asleep_minutes"] for r in self.records()},
                         {"2025-11-01": 15, "2025-11-02": 15})

    def test_other_timezone_uses_elapsed_time_through_a_repeated_hour(self):
        a, b, c, d = ("2025-11-02T00:30:00-04:00", "2025-11-02T01:30:00-04:00",
                      "2025-11-02T01:30:00-05:00", "2025-11-02T02:30:00-05:00")
        sleep = session("dst", a, d, [stage(a, b, "core"), stage(b, c, "deep"), stage(c, d, "wake")])
        self.sync(sleep, zone="America/New_York").raise_for_status()
        record, = self.records()
        self.assertEqual(record["timezone"], "America/New_York")
        self.assertEqual(record["health_sync"]["day"], "2025-11-01")
        self.assertEqual((record["recorded_minutes"], record["asleep_minutes"], record["awake_minutes"]), (180, 120, 60))

    def test_missing_sync_token_rejects_request_without_storage(self):
        reply = self.sync(full_night(), headers={})
        self.assertEqual(reply.status_code, 401)
        self.assertEqual(self.records(), [])
        status = self.http.get("/watch/health/connection", headers=self.web[OWNER]).raise_for_status().json()
        self.assertIsNone(status["connection"]["last_synced_at"])

    def test_iphone_export_and_native_records_use_the_same_stage_meaning(self):
        native = full_night()
        self.sync(native).raise_for_status()
        synced, = self.records()
        names = {"core": "asleepCore", "deep": "asleepDeep", "wake": "awake",
                 "rem": "asleepREM", "unspecified": "asleepUnspecified"}
        apple = {
            "meta": {"schemaVersion": 2, "timeZone": "Asia/Seoul",
                     "rangeStart": "2025-11-01T12:00:00+09:00", "rangeEnd": "2025-11-02T12:00:00+09:00"},
            "sleep": {"sessions": [{
                "source": "Synthetic Apple Watch", "start": native["start"], "end": native["end"],
                "stages": [s | {"stage": names[s["stage"]]} for s in native["segments"]],
            }]},
        }
        first = self.upload(apple).raise_for_status().json()
        repeated = self.upload(apple).raise_for_status().json()
        imported = self.http.get(f"/watch/sessions/{first['analysis_ids'][0]}", headers=self.web[OWNER]).raise_for_status().json()
        for field in ("recorded_minutes", "asleep_minutes", "awake_minutes", "stage_minutes", "unrecorded_minutes"):
            self.assertEqual(imported[field], synced[field], field)
        self.assertEqual(first["added_sessions"], 1)
        self.assertTrue(repeated["duplicate_file"])
        self.assertEqual(repeated["added_sessions"], 0)
        self.assertEqual(repeated["analysis_ids"], first["analysis_ids"])
        self.assertEqual(len(self.records()), 2)

    def test_iphone_invalid_uploads_do_not_change_existing_records(self):
        data = {"schema_version": 1, "timezone": "Asia/Seoul", "source": "Synthetic Apple Watch",
                "sessions": [full_night()]}
        self.upload(data).raise_for_status()
        original = self.records()
        missing_stages = deepcopy(data)
        missing_stages["sessions"][0]["segments"] = []
        missing_offset = deepcopy(data)
        missing_offset["sessions"][0]["start"] = "2025-11-01T22:00:00"
        for value, detail in (
            ("{bad json", "JSON 문법"), (data | {"schema_version": 3}, "schema_version"),
            (missing_stages, "segments"), (missing_offset, "ISO 8601"), (data | {"timezone": "Invalid/Zone"}, "timezone"),
        ):
            with self.subTest(detail=detail):
                error = self.upload(value)
                self.assertEqual(error.status_code, 400)
                self.assertIn("파일 형식을 확인하세요", error.json()["detail"])
                self.assertIn(detail, error.json()["detail"])
        self.assertEqual(self.records(), original)

    def test_iphone_partial_stages_use_declared_span_and_real_timezone(self):
        a, b, c, d = ("2025-11-02T00:30:00-04:00", "2025-11-02T01:30:00-04:00",
                      "2025-11-02T01:30:00-05:00", "2025-11-02T02:30:00-05:00")
        data = {"schema_version": 1, "timezone": "America/New_York", "source": "Synthetic Apple Watch",
                "sessions": [session("dst", a, d, [stage(b, c, "core"), stage(c, d, "wake")])]}
        self.upload(data).raise_for_status()
        record, = self.records()
        self.assertEqual((record["start"], record["end"]), (a, d))
        self.assertEqual((record["recorded_minutes"], record["asleep_minutes"], record["awake_minutes"], record["unrecorded_minutes"]),
                         (180, 60, 60, 60))
        self.assertEqual(record["stage_minutes"]["unspecified"], 0)
        self.assertTrue(record["warnings"])
