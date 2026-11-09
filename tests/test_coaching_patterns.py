"""Check multi-day sleep statistics with synthetic health sync records."""

from copy import deepcopy
from datetime import date, datetime, timedelta
import unittest

from coaching_patterns import analyze_sleep_patterns


def session(day, asleep, clock="23:50", zone="Asia/Seoul", offset="+09:00", provider="healthkit"):
    night = date.fromisoformat(day)
    local_date = night + timedelta(days=clock < "12:00")
    start = datetime.fromisoformat(f"{local_date}T{clock}:00{offset}")
    duration = asleep + 30
    return {
        "analysis_id": f"{day}-{clock}-{provider}",
        "start": start.isoformat(),
        "end": (start + timedelta(minutes=duration)).isoformat(),
        "timezone": zone,
        "recorded_minutes": duration,
        "asleep_minutes": asleep,
        "health_sync": {"day": day, "provider": provider, "source_id": "synthetic"},
    }


class SleepPatternTests(unittest.TestCase):
    def test_compares_windows_without_missing_days_or_future_records(self):
        selected = session("2026-11-14", 420, "23:55")
        records = [
            session("2026-11-01", 350),
            session("2026-11-04", 360),
            session("2026-11-07", 370),
            session("2026-11-08", 380),
            session("2026-11-13", 400, "00:10", provider="health_connect"),
            session("2026-10-31", 120),
            session("2026-11-15", 600),
            session("2026-11-14", 600, "23:58"),
            selected.copy(),
        ]

        result = analyze_sleep_patterns(selected, records)

        self.assertEqual(result["reference_day"], "2026-11-14")
        self.assertEqual(result["observation"]["recent"], {
            "start_date": "2026-11-08", "end_date": "2026-11-14",
            "valid_days": 3, "average_asleep_minutes": 400,
        })
        self.assertEqual(result["observation"]["previous"], {
            "start_date": "2026-11-01", "end_date": "2026-11-07",
            "valid_days": 3, "average_asleep_minutes": 360,
        })
        self.assertEqual(result["comparison"]["average_difference_minutes"], 40)
        self.assertEqual(result["observation"]["regularity"]["start_spread_minutes"], 20)

    def test_after_midnight_keeps_the_sync_day_and_wraps_clock_distance(self):
        selected = session("2026-11-14", 380, "00:10")
        result = analyze_sleep_patterns(selected, [session("2026-11-13", 380, "23:50")])

        self.assertTrue(selected["start"].startswith("2026-11-15"))
        self.assertEqual(result["reference_day"], "2026-11-14")
        self.assertEqual(result["observation"]["regularity"], {
            "status": "available", "sample_days": 2, "start_spread_minutes": 20,
        })

    def test_duplicate_counted_once_and_overlapping_day_excluded(self):
        selected = session("2026-11-14", 420)
        duplicate = session("2026-11-12", 380)
        result = analyze_sleep_patterns(selected, [
            duplicate, dict(duplicate, analysis_id="duplicate-export"),
            session("2026-11-13", 400), session("2026-11-13", 200, "23:55"),
        ])

        self.assertEqual(result["observation"]["recent"]["valid_days"], 2)
        self.assertEqual(result["observation"]["recent"]["average_asleep_minutes"], 400)
        self.assertTrue(any("겹치거나" in note for note in result["limitations"]))

    def test_conflicting_versions_of_one_record_id_exclude_both_days(self):
        first = session("2026-11-12", 380)
        moved = dict(session("2026-11-13", 400), analysis_id=first["analysis_id"])
        result = analyze_sleep_patterns(session("2026-11-14", 420), [first, moved])

        self.assertEqual(result["observation"]["recent"]["valid_days"], 1)
        self.assertEqual(result["observation"]["recent"]["average_asleep_minutes"], 420)

    def test_touching_sessions_can_sum_without_choosing_one_as_bedtime(self):
        selected = session("2026-11-14", 420)
        earlier = session("2026-11-13", 30, "19:00")
        later = session("2026-11-13", 350, "20:00")
        result = analyze_sleep_patterns(selected, [earlier, later])

        self.assertEqual(earlier["end"], later["start"])
        self.assertEqual(result["observation"]["recent"]["valid_days"], 2)
        self.assertEqual(result["observation"]["recent"]["average_asleep_minutes"], 400)
        self.assertEqual(result["observation"]["regularity"]["status"], "unreliable_start")

    def test_trend_requires_three_days_on_each_side(self):
        previous = [session(f"2026-11-0{day}", 360) for day in (1, 2, 3)]
        recent = [session(f"2026-11-{day}", 400) for day in (12, 13)]
        selected = session("2026-11-14", 400)
        for old, new in ((previous[:2], recent), (previous, recent[:1])):
            with self.subTest(previous=len(old), recent=len(new) + 1):
                result = analyze_sleep_patterns(selected, old + new)
                self.assertEqual(result["comparison"], {
                    "status": "insufficient_days", "average_difference_minutes": None,
                })
                self.assertEqual(result["observation"]["recent"]["average_asleep_minutes"], 400)
                self.assertEqual(result["observation"]["previous"]["average_asleep_minutes"], 360)

    def test_mixed_zone_or_offset_holds_regularity_but_keeps_durations(self):
        selected = session("2026-11-14", 420)
        for zone, offset in (("Asia/Tokyo", "+09:00"), ("Asia/Seoul", "+08:00")):
            with self.subTest(zone=zone, offset=offset):
                other = session("2026-11-13", 380, zone=zone, offset=offset)
                result = analyze_sleep_patterns(selected, [other])
                self.assertEqual(result["observation"]["regularity"]["status"], "mixed_timezones")
                self.assertIsNone(result["observation"]["regularity"]["start_spread_minutes"])
                self.assertEqual(result["observation"]["recent"]["average_asleep_minutes"], 400)

    def test_unreliable_start_holds_regularity(self):
        selected = session("2026-11-14", 420)
        other = session("2026-11-13", 380)
        incomplete = session("2026-11-12", 370)
        for record in (
            dict(incomplete, start=None),
            dict(incomplete, timezone=None),
            session("2026-11-12", 370, "12:00"),
            session("2026-11-12", 0),
            dict(incomplete, segments=[{"start": incomplete["start"], "stage": "wake"}]),
            dict(incomplete, segments=[{"start": "2026-11-12T23:55:00+09:00", "stage": "core"}]),
        ):
            with self.subTest(record=record):
                result = analyze_sleep_patterns(selected, [other, record])
                self.assertEqual(result["observation"]["regularity"]["status"], "unreliable_start")
                self.assertIsNone(result["observation"]["regularity"]["start_spread_minutes"])

    def test_missing_sleep_is_not_zero_and_empty_period_has_no_average(self):
        selected = session("2026-11-14", 420)
        unknown = session("2026-11-13", 380)
        del unknown["asleep_minutes"]
        invalid = dict(session("2026-11-12", 380), asleep_minutes=float("nan"))
        result = analyze_sleep_patterns(selected, [unknown, invalid])

        self.assertEqual(result["observation"]["recent"]["valid_days"], 1)
        self.assertEqual(result["observation"]["recent"]["average_asleep_minutes"], 420)
        self.assertEqual(result["observation"]["previous"]["valid_days"], 0)
        self.assertIsNone(result["observation"]["previous"]["average_asleep_minutes"])

    def test_legacy_record_uses_local_noon_boundary_and_invalid_anchor_is_reported(self):
        selected = session("2026-11-14", 420, "00:10")
        del selected["health_sync"]
        self.assertEqual(analyze_sleep_patterns(selected, [])["reference_day"], "2026-11-14")
        result = analyze_sleep_patterns(dict(selected, end=None), [])
        self.assertEqual(result["comparison"]["status"], "invalid_reference")
        self.assertIsNone(result["observation"]["recent"])

    def test_repeated_and_reordered_inputs_are_deterministic_and_preserved(self):
        selected = session("2026-11-14", 420)
        records = [session("2026-11-12", 380), session("2026-11-13", 400), selected.copy()]
        original = deepcopy((selected, records))

        first = analyze_sleep_patterns(selected, records)
        self.assertEqual(first, analyze_sleep_patterns(selected, records))
        self.assertEqual(first, analyze_sleep_patterns(selected, reversed(records)))
        self.assertEqual((selected, records), original)
