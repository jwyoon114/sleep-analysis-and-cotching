import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from health_records import import_export, list_sessions
from json_sleep import parse_json_export


def synthetic_export(*, raw=False):
    export = {
        "meta": {
            "schemaVersion": 2, "timeZone": "Asia/Seoul",
            "rangeStart": "2026-01-01T00:00:00+09:00",
            "rangeEnd": "2026-01-08T00:00:00+09:00",
        },
        "sleep": {"sessions": [{
            "source": "Synthetic watch",
            "start": "2026-01-03T23:00:00+09:00",
            "end": "2026-01-04T00:00:00+09:00",
            "stages": [
                {"start": "23:00:00", "end": "23:55:00", "stage": "asleepCore"},
                {"start": "23:55:00", "end": "00:00:00", "stage": "awake"},
            ],
        }]},
    }
    if raw:
        export["sleep"]["streams"] = {"heartRate": {
            "unit": "bpm", "tupleSchema": ["time", "value", "sourceIdx"],
            "sources": ["Synthetic watch"], "samples": [["23:30:00", 60, 0]],
        }}
    return export


class IphoneHealthExportGuideTests(unittest.TestCase):
    def test_sleep_only_and_raw_v2_keep_the_same_sleep_observation(self):
        sleep_only = parse_json_export(json.dumps(synthetic_export()))
        raw = parse_json_export(json.dumps(synthetic_export(raw=True)))
        self.assertEqual(raw["sessions"], sleep_only["sessions"])
        self.assertEqual(raw["sessions"][0]["asleep_minutes"], 55)
        self.assertEqual(raw["sessions"][0]["awake_minutes"], 5)
        self.assertEqual(sleep_only["samples"], [])
        self.assertEqual(len(raw["samples"]), 1)

    def test_both_variants_and_repeated_upload_keep_one_session(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.sqlite"
            first = import_export(json.dumps(synthetic_export()), "sleep.json", "fixture", path)
            raw = json.dumps(synthetic_export(raw=True))
            second = import_export(raw, "raw.json", "fixture", path)
            third = import_export(raw, "raw.json", "fixture", path)
            self.assertEqual((first["added_sessions"], second["added_sessions"], third["added_sessions"]), (1, 0, 0))
            self.assertEqual(first["analysis_ids"], third["analysis_ids"])
            self.assertTrue(third["duplicate_file"])
            self.assertEqual(len(list_sessions("fixture", path)), 1)

    def test_downsampled_streams_are_rejected(self):
        export = synthetic_export(raw=True)
        export["sleep"]["streams"]["heartRate"]["downsampledTo"] = "1m"
        with self.assertRaisesRegex(ValueError, "집계 스트림"):
            parse_json_export(json.dumps(export))

    def test_ambiguous_clock_only_session_is_rejected_for_multi_day_range(self):
        export = synthetic_export()
        export["sleep"]["sessions"][0].update(start="23:00:00", end="00:00:00")
        with self.assertRaisesRegex(ValueError, "날짜가 모호합니다"):
            parse_json_export(json.dumps(export))

    def test_version_2_requires_sleep_sessions_with_stages(self):
        export = synthetic_export()
        del export["sleep"]["sessions"][0]["stages"]
        with self.assertRaisesRegex(ValueError, "stages 배열"):
            parse_json_export(json.dumps(export))
        export["sleep"]["sessions"].clear()
        with self.assertRaisesRegex(ValueError, "sleep.sessions"):
            parse_json_export(json.dumps(export))
