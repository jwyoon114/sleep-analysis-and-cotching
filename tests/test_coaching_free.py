"""Exercise free coaching with normalized, synthetic sleep records."""

from copy import deepcopy
from datetime import datetime, timedelta
import unittest

from coaching_free import generate_free_coaching
from coaching_patterns import analyze_sleep_patterns
from coaching_rules import generate_rule_advice


def session(day, asleep, clock="23:50", provider="healthkit"):
    start = datetime.fromisoformat(f"{day}T{clock}:00+09:00")
    if start.hour < 12:
        start += timedelta(days=1)
    duration = asleep + 30
    return {
        "start": start.isoformat(),
        "end": (start + timedelta(minutes=duration)).isoformat(),
        "timezone": "Asia/Seoul",
        "recorded_minutes": duration,
        "asleep_minutes": asleep,
        "awake_minutes": 30,
        "health_sync": {"day": day, "provider": provider, "source_id": "synthetic"},
    }


class FreeCoachingTests(unittest.TestCase):
    def setUp(self):
        self.selected = session("2026-11-14", 420, "23:55")
        self.history = [
            session("2026-11-01", 350),
            session("2026-11-04", 360),
            session("2026-11-07", 370),
            session("2026-11-08", 380),
            session("2026-11-13", 400, "00:10", provider="health_connect"),
        ]

    def test_combines_selected_observation_suggestion_and_scoped_limitations(self):
        habits = {"caffeine": "있음"}
        advice = generate_rule_advice(self.selected, habits)
        patterns = analyze_sleep_patterns(self.selected, self.history)

        result = generate_free_coaching(self.selected, self.history, habits)

        self.assertEqual(set(result), {"observation", "patterns", "suggestion", "limitations"})
        self.assertEqual(result["observation"], advice["observation"])
        self.assertIn("7시간", result["observation"])
        self.assertEqual(result["suggestion"], advice["suggestion"])
        self.assertIn("카페인", result["suggestion"])
        self.assertEqual(
            result["limitations"],
            [f"선택 기록 · {advice['limitation']}", *patterns["limitations"]],
        )
        self.assertNotIn("limitations", result["patterns"])

    def test_preserves_available_weekly_comparison_and_start_spread(self):
        patterns = analyze_sleep_patterns(self.selected, self.history)
        result = generate_free_coaching(self.selected, self.history, {})["patterns"]

        self.assertEqual(result["reference_day"], "2026-11-14")
        self.assertEqual(result["recent"], patterns["observation"]["recent"])
        self.assertEqual(result["previous"], patterns["observation"]["previous"])
        self.assertEqual(result["regularity"], patterns["observation"]["regularity"])
        self.assertEqual(result["recent"]["valid_days"], 3)
        self.assertEqual(result["recent"]["average_asleep_minutes"], 400)
        self.assertEqual(result["previous"]["valid_days"], 3)
        self.assertEqual(result["previous"]["average_asleep_minutes"], 360)
        self.assertEqual(result["regularity"]["start_spread_minutes"], 20)
        self.assertEqual(result["comparison"], {
            "status": "available", "average_difference_minutes": 40,
        })

    def test_presentation_uses_the_same_observation_and_pattern_values(self):
        habits = {"caffeine": "있음"}
        legacy = generate_free_coaching(self.selected, self.history, habits)
        result = generate_free_coaching(
            self.selected, self.history, habits, include_presentation=True,
        )
        presentation = result.pop("presentation")
        self.assertEqual(result, legacy)
        self.assertEqual(presentation, {
            "version": 1,
            "observation": {
                "id": "device_sleep_estimate",
                "asleep": {"valid": True, "minutes": 420, "display": "7시간"},
                "awake": {"valid": True, "minutes": 30, "display": "30분"},
            },
            "patterns": {
                "recent": {"valid_days": 3, "average_asleep_minutes": 400, "average_display": "400분"},
                "previous": {"valid_days": 3, "average_asleep_minutes": 360, "average_display": "360분"},
                "comparison": {
                    "status": "available", "average_difference_minutes": 40, "difference_display": "+40분",
                },
                "regularity": {"status": "available", "start_spread_minutes": 20, "spread_display": "20분"},
            },
            "suggestion_id": "track_caffeine_timing",
            "limitation_ids": [
                "single_device_estimate", "valid_days_device_estimates", "device_start_range",
            ],
        })

    def test_withholds_difference_with_insufficient_history(self):
        result = generate_free_coaching(
            self.selected, self.history[-1:], None, include_presentation=True,
        )

        self.assertEqual(result["patterns"]["recent"]["valid_days"], 2)
        self.assertEqual(result["patterns"]["previous"]["valid_days"], 0)
        self.assertIsNone(result["patterns"]["previous"]["average_asleep_minutes"])
        self.assertEqual(result["patterns"]["comparison"], {
            "status": "insufficient_days", "average_difference_minutes": None,
        })
        self.assertTrue(any("3일 이상" in note for note in result["limitations"]))
        presentation = result["presentation"]
        self.assertEqual(presentation["patterns"]["previous"], {
            "valid_days": 0, "average_asleep_minutes": None, "average_display": None,
        })
        self.assertEqual(presentation["patterns"]["comparison"], {
            "status": "insufficient_days", "average_difference_minutes": None, "difference_display": None,
        })
        self.assertIn("insufficient_comparison_days", presentation["limitation_ids"])

    def test_zero_and_negative_differences_have_signed_display_values(self):
        for previous_average, difference, display in [(400, 0, "+0분"), (420, -20, "-20분")]:
            with self.subTest(difference=difference):
                history = [
                    session(day, previous_average)
                    for day in ("2026-11-01", "2026-11-04", "2026-11-07")
                ] + self.history[-2:]
                result = generate_free_coaching(
                    self.selected, history, {}, include_presentation=True,
                )
                self.assertEqual(result["presentation"]["patterns"]["comparison"], {
                    "status": "available",
                    "average_difference_minutes": difference,
                    "difference_display": display,
                })

    def test_missing_lifestyle_answers_use_only_reported_habits(self):
        result = generate_free_coaching(self.selected, [], {"regularity": "자주 달라짐"})
        empty = generate_free_coaching(self.selected, [], {})

        self.assertIn("취침·기상 시각", result["suggestion"])
        self.assertNotIn("카페인", result["suggestion"])
        self.assertNotEqual(result["suggestion"], empty["suggestion"])
        self.assertEqual(empty, generate_free_coaching(self.selected, [], None))

    def test_presentation_suggestion_follows_existing_lifestyle_priority(self):
        cases = [
            ({"caffeine": "있음", "regularity": "자주 달라짐", "satisfaction": "나쁨"}, "track_caffeine_timing"),
            ({"caffeine": "미입력", "regularity": "자주 달라짐", "satisfaction": "나쁨"}, "track_bed_and_wake_times"),
            ({"caffeine": "없음", "satisfaction": "나쁨"}, "track_morning_rest"),
            ({"caffeine": "미입력"}, "compare_daily_sleep"),
        ]
        for lifestyle, suggestion_id in cases:
            with self.subTest(suggestion_id=suggestion_id):
                result = generate_free_coaching(self.selected, [], lifestyle, include_presentation=True)
                self.assertEqual(result["presentation"]["suggestion_id"], suggestion_id)

    def test_presentation_marks_omitted_measurements_unavailable(self):
        unavailable = {"valid": False, "minutes": None, "display": None}
        for awake in (None, 100):
            with self.subTest(awake=awake):
                selected = dict(self.selected, asleep_minutes=419.5, awake_minutes=awake, unrecorded_minutes=5)
                result = generate_free_coaching(selected, [], {}, include_presentation=True)
                presentation = result["presentation"]
                self.assertEqual(presentation["observation"]["asleep"], {
                    "valid": True, "minutes": 419.5, "display": "약 7시간",
                })
                self.assertEqual(presentation["observation"]["awake"], unavailable)
                self.assertNotIn("각성으로 분류한 시간", result["observation"])
                self.assertIn("unrecorded_segments", presentation["limitation_ids"])

        selected = dict(self.selected, asleep_minutes=None)
        result = generate_free_coaching(selected, [], {"caffeine": "있음"}, include_presentation=True)
        presentation = result["presentation"]
        self.assertEqual(presentation["observation"], {
            "id": "sleep_duration_unavailable", "asleep": unavailable, "awake": unavailable,
        })
        self.assertEqual(presentation["suggestion_id"], "check_device_record")
        self.assertIn("sleep_duration_unavailable", presentation["limitation_ids"])
        self.assertIn("unusable_records_excluded", presentation["limitation_ids"])

    def test_presentation_withholds_start_range_across_timezones(self):
        history = self.history[:-1] + [dict(self.history[-1], timezone="Asia/Tokyo")]
        result = generate_free_coaching(self.selected, history, {}, include_presentation=True)
        presentation = result["presentation"]
        self.assertEqual(presentation["patterns"]["regularity"], {
            "status": "mixed_timezones", "start_spread_minutes": None, "spread_display": None,
        })
        self.assertIn("mixed_timezones", presentation["limitation_ids"])

    def test_missing_reference_times_keep_the_single_record_observation(self):
        result = generate_free_coaching(
            {"asleep_minutes": 380}, self.history, {}, include_presentation=True,
        )

        self.assertIn("6시간 20분", result["observation"])
        self.assertIsNone(result["patterns"]["reference_day"])
        self.assertIsNone(result["patterns"]["recent"])
        self.assertEqual(result["patterns"]["comparison"], {
            "status": "invalid_reference", "average_difference_minutes": None,
        })
        presentation = result["presentation"]
        self.assertIsNone(presentation["patterns"]["recent"])
        self.assertIsNone(presentation["patterns"]["previous"])
        self.assertEqual(presentation["patterns"]["regularity"], {
            "status": "invalid_reference", "start_spread_minutes": None, "spread_display": None,
        })
        self.assertIn("invalid_reference", presentation["limitation_ids"])

    def test_absent_inputs_return_record_check_without_comparison_values(self):
        result = generate_free_coaching(None, None, None)

        self.assertIn("수면 시간을 확인할 수 없습니다", result["observation"])
        self.assertIn("다시 불러와", result["suggestion"])
        self.assertIsNone(result["patterns"]["comparison"]["average_difference_minutes"])
        self.assertTrue(result["limitations"])

    def test_same_input_is_deterministic_without_mutating_records(self):
        habits = {"satisfaction": "나쁨"}
        original = deepcopy((self.selected, self.history, habits))
        first = generate_free_coaching(self.selected, self.history, habits)

        self.assertEqual(first, generate_free_coaching(self.selected, self.history, habits))
        self.assertEqual(first, generate_free_coaching(self.selected, iter(self.history), habits))
        self.assertEqual((self.selected, self.history, habits), original)
