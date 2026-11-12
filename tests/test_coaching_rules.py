"""Exercise the pure coaching engine with synthetic records."""

from copy import deepcopy
import unittest

from coaching_rules import generate_rule_advice


class RuleAdviceTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "start": "2026-11-01T23:30:00+09:00",
            "end": "2026-11-02T06:30:00+09:00",
            "timezone": "Asia/Seoul",
            "recorded_minutes": 420,
            "asleep_minutes": 380,
            "awake_minutes": 30,
            "unrecorded_minutes": 10,
            "vitals_summary": [],
        }

    def test_uses_sleep_minutes_separately_from_the_recording_window(self):
        result = generate_rule_advice(self.record, {})

        self.assertEqual(set(result), {"observation", "suggestion", "limitation"})
        self.assertIn("수면으로 분류한 시간은 6시간 20분", result["observation"])
        self.assertIn("각성으로 분류한 시간은 30분", result["observation"])
        self.assertNotIn("7시간", result["observation"])
        self.assertIn("미기록 구간", result["limitation"])

    def test_caffeine_answer_changes_only_the_suggestion(self):
        reported = generate_rule_advice(self.record, {"caffeine": "있음"})
        unknown = generate_rule_advice(self.record, {"caffeine": "미입력"})
        none_reported = generate_rule_advice(self.record, {"caffeine": "없음"})

        self.assertIn("카페인", reported["suggestion"])
        self.assertIn("수면 기록과 함께", reported["suggestion"])
        self.assertNotIn("카페인", unknown["suggestion"])
        self.assertEqual(unknown, none_reported)
        self.assertEqual(unknown, generate_rule_advice(self.record, {}))
        for field in ("observation", "limitation"):
            self.assertEqual(reported[field], unknown[field])

    def test_missing_or_invalid_sleep_asks_to_check_the_record(self):
        without_sleep = dict(self.record)
        del without_sleep["asleep_minutes"]
        records = [None, without_sleep]
        records.extend(
            dict(self.record, asleep_minutes=value)
            for value in (None, "380", True, -1, float("nan"), float("inf"), 421)
        )

        for record in records:
            with self.subTest(record=record):
                result = generate_rule_advice(record, {"caffeine": "있음"})
                self.assertIn("확인할 수 없습니다", result["observation"])
                self.assertIn("다시 불러와", result["suggestion"])
                self.assertNotRegex(result["observation"], r"\d")
                self.assertNotIn("카페인", result["suggestion"])

    def test_same_input_is_deterministic_and_preserved(self):
        habits = {
            "caffeine": "있음",
            "regularity": "미입력",
            "satisfaction": "보통",
            "age_group": "미입력",
        }
        original_record = deepcopy(self.record)
        original_habits = habits.copy()

        first = generate_rule_advice(self.record, habits)
        second = generate_rule_advice(original_record, original_habits)

        self.assertEqual(first, second)
        self.assertEqual(self.record, original_record)
        self.assertEqual(habits, original_habits)

    def test_uses_other_reported_habits_when_caffeine_is_unknown(self):
        for habits, keyword in (
            ({"regularity": "자주 달라짐"}, "취침·기상 시각"),
            ({"satisfaction": "나쁨"}, "아침에 느낀 휴식 정도"),
        ):
            with self.subTest(habits=habits):
                result = generate_rule_advice(self.record, habits)
                self.assertIn(keyword, result["suggestion"])

    def test_omits_optional_values_that_do_not_fit_the_record(self):
        record = dict(self.record, awake_minutes=90, unrecorded_minutes=60)
        result = generate_rule_advice(record, {})

        self.assertIn("6시간 20분", result["observation"])
        self.assertNotIn("각성", result["observation"])
        self.assertNotIn("미기록 구간", result["limitation"])

    def test_reports_zero_and_qualifies_rounded_minutes(self):
        for value, expected in ((0, "0분"), (0.5, "1분 미만"), (380.2, "약 6시간 20분")):
            with self.subTest(value=value):
                result = generate_rule_advice({"asleep_minutes": value}, {})
                self.assertEqual(
                    result["observation"],
                    f"기기에서 수면으로 분류한 시간은 {expected}입니다.",
                )
