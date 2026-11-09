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

    def test_withholds_difference_with_insufficient_history(self):
        result = generate_free_coaching(self.selected, self.history[-1:], None)

        self.assertEqual(result["patterns"]["recent"]["valid_days"], 2)
        self.assertEqual(result["patterns"]["previous"]["valid_days"], 0)
        self.assertIsNone(result["patterns"]["previous"]["average_asleep_minutes"])
        self.assertEqual(result["patterns"]["comparison"], {
            "status": "insufficient_days", "average_difference_minutes": None,
        })
        self.assertTrue(any("3일 이상" in note for note in result["limitations"]))

    def test_missing_lifestyle_answers_use_only_reported_habits(self):
        result = generate_free_coaching(self.selected, [], {"regularity": "자주 달라짐"})
        empty = generate_free_coaching(self.selected, [], {})

        self.assertIn("취침·기상 시각", result["suggestion"])
        self.assertNotIn("카페인", result["suggestion"])
        self.assertNotEqual(result["suggestion"], empty["suggestion"])
        self.assertEqual(empty, generate_free_coaching(self.selected, [], None))

    def test_missing_reference_times_keep_the_single_record_observation(self):
        result = generate_free_coaching({"asleep_minutes": 380}, self.history, {})

        self.assertIn("6시간 20분", result["observation"])
        self.assertIsNone(result["patterns"]["reference_day"])
        self.assertIsNone(result["patterns"]["recent"])
        self.assertEqual(result["patterns"]["comparison"], {
            "status": "invalid_reference", "average_difference_minutes": None,
        })

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
