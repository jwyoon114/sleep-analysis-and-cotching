"""Versioned coaching wording preserves results from the rules."""

from itertools import product
import unittest

from coaching_expression import DEFAULT_EXPRESSION, expression_snapshot, render_personalized_answer
from coaching_free import generate_free_coaching
from coaching_service import _rule_pattern_lines


class CoachingExpressionTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "start": "2026-11-10T23:00:00+09:00", "end": "2026-11-11T06:00:00+09:00",
            "timezone": "Asia/Seoul", "asleep_minutes": 380, "recorded_minutes": 420,
            "awake_minutes": 20, "unrecorded_minutes": 20,
        }

    def render(self, result, speech, intensity, mbti=None, allow=False):
        expression = expression_snapshot({"mbti": mbti, "speech": speech, "intensity": intensity,
                                          "allow_profanity": allow})
        return render_personalized_answer(result, _rule_pattern_lines(result), expression)

    def test_six_wordings_keep_the_same_facts_and_caffeine_action(self):
        result = generate_free_coaching(self.record, [], {"caffeine": "있음"}, include_presentation=True)
        endings = {
            ("polite", "gentle"): "나란히 놓고 살펴봐요.",
            ("polite", "firm"): "그다음 며칠 동안의 수면 기록과 함께 비교하세요.",
            ("polite", "direct"): "며칠 동안의 수면 기록과 비교하세요.",
            ("casual", "gentle"): "같이 살펴보자.",
            ("casual", "firm"): "그다음 며칠 동안의 수면 기록과 함께 비교해 봐.",
            ("casual", "direct"): "며칠 동안의 수면 기록과 비교해.",
        }
        outputs = []
        for (speech, intensity), wording in endings.items():
            with self.subTest(speech=speech, intensity=intensity):
                text = self.render(result, speech, intensity)
                outputs.append(text)
                for fact in ("6시간 20분", "20분", "카페인을 섭취한 시각", "며칠 동안의 수면 기록",
                             "미기록 구간", "각각 유효 기록일이 3일 이상"):
                    self.assertIn(fact, text)
                self.assertNotIn("평균 차이(최근 − 직전)", text)
                self.assertIn(wording, text)
        self.assertEqual(len(set(outputs)), 6)

    def test_all_mbti_choices_vary_expression_and_keep_the_same_numbers(self):
        earlier = [{**self.record,
                    "start": f"2026-11-{day:02d}T23:00:00+09:00",
                    "end": f"2026-11-{day+1:02d}T06:00:00+09:00",
                    "asleep_minutes": 390 if day < 4 else 380}
                   for day in (1, 2, 3, 8, 9)]
        result = generate_free_coaching(self.record, earlier, {}, include_presentation=True)
        self.assertIn("평균 차이(최근 − 직전) -10분", _rule_pattern_lines(result))
        variants = []
        for letters in product("EI", "SN", "TF", "JP"):
            mbti = "".join(letters)
            text = self.render(result, "casual", "direct", mbti)
            for fact in ("6시간 20분", "380분", "390분", "-10분", "0분",
                         "며칠 동안 수면 기록을 모아", "날짜별 수면 시간을 비교해"):
                self.assertIn(fact, text)
            self.assertNotIn("오늘 기록", text)
            self.assertEqual(text.startswith("수면 패턴"), mbti[1] == "N")
            variants.append(text)
        self.assertEqual(len(set(variants)), 16)

    def test_missing_measurement_and_defaults_assume_nothing(self):
        self.assertEqual(expression_snapshot(None), DEFAULT_EXPRESSION)
        self.assertEqual(expression_snapshot({"mbti": "FISH", "speech": "", "allow_profanity": True}), DEFAULT_EXPRESSION)
        result = generate_free_coaching({}, [], {"caffeine": "있음"}, include_presentation=True)
        text = self.render(result, "casual", "direct", allow=True)
        self.assertIn("수면 시간을 확인할 수 없어", text)
        self.assertIn("기기 앱에서 수면 시간이 기록됐는지 확인해", text)
        self.assertIn("날짜와 시간 구간", text)
        self.assertNotIn("평균 차이(최근 − 직전)", text)
        self.assertNotIn("카페인", text)
        self.assertEqual(text, self.render(result, "casual", "direct", allow=False))
