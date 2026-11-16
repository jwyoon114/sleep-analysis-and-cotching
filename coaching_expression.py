"""Versioned Korean wording for facts and actions selected by the sleep rules."""

import re

VERSION = 1
DEFAULT_EXPRESSION = {
    "version": VERSION, "mbti": None, "speech": "polite",
    "intensity": "gentle", "allow_profanity": False,
}


def expression_snapshot(preferences):
    settings = preferences or {}
    mbti = settings.get("mbti")
    speech = settings.get("speech")
    intensity = settings.get("intensity")
    return {
        "version": VERSION,
        "mbti": mbti if isinstance(mbti, str) and re.fullmatch(r"[EI][SN][TF][JP]", mbti) else None,
        "speech": speech if speech in ("polite", "casual") else "polite",
        "intensity": intensity if intensity in ("gentle", "firm", "direct") else "gentle",
        "allow_profanity": intensity == "direct" and settings.get("allow_profanity") is True,
    }


_OBSERVATION = {
    ("polite", "gentle"): "기기가 수면으로 추정한 시간부터 살펴봐요. 이번 기록에서는 {duration}이에요.",
    ("polite", "firm"): "이 기록의 기기 추정 수면 시간은 {duration}입니다.",
    ("polite", "direct"): "기기가 수면으로 분류한 건 {duration}이에요.",
    ("casual", "gentle"): "이번 기록을 같이 보자. 기기가 수면으로 추정한 시간은 {duration}이야.",
    ("casual", "firm"): "확인된 기록부터 볼게. 기기가 수면으로 추정한 시간은 {duration}이야.",
    ("casual", "direct"): "기기는 {duration}을 수면으로 분류했어.",
}

# Each variant retains the action, time period and comparison chosen by the rules.
_ACTIONS = {
    "check_device_record": (
        "기기 앱에서 수면 시간이 기록됐는지 살펴본 다음, 기록을 다시 불러와 보세요.",
        "먼저 기기 앱에서 수면 시간이 기록됐는지 확인하세요. 그다음 기록을 다시 불러오세요.",
        "기기 앱에서 수면 시간이 기록됐는지 확인하고 기록을 다시 불러오세요.",
        "기기 앱에 수면 시간이 기록됐는지 확인해 보고, 기록을 다시 불러와 봐.",
        "기기 앱에서 수면 시간이 기록됐는지 먼저 확인해. 그다음 기록을 다시 불러와.",
        "기기 앱에서 수면 시간이 기록됐는지 확인해. 확인했으면 기록을 다시 불러와.",
    ),
    "track_caffeine_timing": (
        "카페인을 섭취한 시각을 가볍게 메모해 보세요. 며칠 동안의 수면 기록과 나란히 놓고 살펴봐요.",
        "먼저 카페인을 섭취한 시각을 적으세요. 그다음 며칠 동안의 수면 기록과 함께 비교하세요.",
        "카페인을 섭취한 시각을 적으세요. 며칠 동안의 수면 기록과 비교하세요.",
        "카페인을 섭취한 시각을 가볍게 메모해 봐. 며칠 동안의 수면 기록과 같이 살펴보자.",
        "먼저 카페인을 섭취한 시각을 적어. 그다음 며칠 동안의 수면 기록과 함께 비교해 봐.",
        "카페인을 섭취한 시각을 적어. 며칠 동안의 수면 기록과 비교해.",
    ),
    "track_bed_and_wake_times": (
        "며칠 동안 취침·기상 시각을 적어 보세요. 생활 일정에 맞춰 꾸준히 지킬 수 있는 시간대를 찾아봐요.",
        "며칠 동안 취침·기상 시각을 적으세요. 기록을 바탕으로 일정에 맞춰 반복하기 쉬운 시간대를 고르세요.",
        "며칠 동안 취침·기상 시각을 적으세요. 일정에 맞춰 반복할 수 있는 시간대를 정하세요.",
        "며칠 동안 취침·기상 시각을 적어 봐. 생활 일정에 맞춰 꾸준히 지킬 수 있는 시간대를 같이 찾아보자.",
        "며칠 동안 취침·기상 시각부터 적어. 기록을 바탕으로 일정에 맞춰 반복하기 쉬운 시간대를 골라 봐.",
        "며칠 동안 취침·기상 시각을 적어. 일정에 맞춰 반복할 수 있는 시간대를 정해.",
    ),
    "track_morning_rest": (
        "다음 기록에는 아침에 얼마나 개운했는지 함께 적어 보세요. 기기 기록과 비교해 봐요.",
        "다음 기록에 아침에 느낀 휴식 정도를 적으세요. 적은 내용과 기기 기록을 비교하세요.",
        "다음에 기록할 때 아침에 느낀 휴식 정도를 적으세요. 기기 기록과 비교하세요.",
        "다음 기록에는 아침에 얼마나 개운했는지도 적어 봐. 기기 기록과 비교해 보자.",
        "다음 기록에 아침에 느낀 휴식 정도를 적어. 적은 내용과 기기 기록을 비교해 봐.",
        "다음에 기록할 때 아침에 느낀 휴식 정도를 적어. 기기 기록과 비교해.",
    ),
    "compare_daily_sleep": (
        "며칠 동안 기록을 모아 보세요. 날짜마다 얼마나 잤는지 나란히 살펴봐요.",
        "며칠 동안 수면 기록을 모으세요. 그다음 날짜별 수면 시간을 비교하세요.",
        "며칠 동안 수면 기록을 모으세요. 날짜별 수면 시간을 비교하세요.",
        "며칠 동안 기록을 모아 봐. 날짜마다 얼마나 잤는지 같이 살펴보자.",
        "며칠 동안 수면 기록을 모아. 그다음 날짜별 수면 시간을 비교해 봐.",
        "며칠 동안 수면 기록을 모아. 날짜별 수면 시간을 비교해.",
    ),
}
_ACTION_TONES = ("gentle", "firm", "direct")

# These are presentation choices only. The type is never an analysis input.
_OPENINGS = {
    "polite": {
        "ET": "기록의 수치를 하나씩 짚어봐요.", "IT": "확인된 수치를 정리했어요.",
        "EF": "이 기록부터 함께 볼까요?", "IF": "이 기록을 천천히 살펴봐요.",
    },
    "casual": {
        "ET": "기록에 나온 수치를 하나씩 짚어 보자.", "IT": "확인된 수치를 정리했어.",
        "EF": "이 기록부터 같이 볼까?", "IF": "이 기록을 천천히 살펴보자.",
    },
}
_ACTION_LEADS = {
    "polite": {"J": "해 볼 일을 순서대로 정리했어요.", "P": "일정에 맞는 때에 시도해 보세요."},
    "casual": {"J": "해 볼 일을 순서대로 정리했어.", "P": "일정에 맞는 때에 시도해 봐."},
}

_CASUAL_LIMITS = {
    "sleep_duration_unavailable": "수면 시간 값이 없거나 유효한 기록 범위를 벗어났어.",
    "single_device_estimate": "기기가 추정한 한 건의 기록이야. 평소 수면 패턴이나 변화의 원인을 판단하기엔 정보가 부족해.",
    "unrecorded_segments": "기록 안에 미기록 구간이 있어.",
    "invalid_reference": "선택한 기록의 날짜와 시간 구간을 확인해 봐.",
    "valid_days_device_estimates": "평균은 유효한 기록이 있는 날의 기기 추정 수면 시간만 사용했어.",
    "unusable_records_excluded": "날짜, 시간 구간 또는 수면 시간을 확인할 수 없는 기록은 집계에서 뺐어.",
    "ambiguous_records_excluded": "기록이 겹치거나 같은 기록 ID의 값이 다른 날은 집계에서 뺐어.",
    "insufficient_comparison_days": "두 기간에 각각 유효 기록일이 3일 이상 있어야 평균 차이를 표시할 수 있어.",
    "mixed_timezones": "최근 기록의 시간대나 UTC 오프셋이 달라 시작 시각의 변동은 표시하지 않았어.",
    "unreliable_start": "날짜별 시작 시각을 하나씩 신뢰하기 어려워 시작 시각의 변동은 표시하지 않았어.",
    "insufficient_start_days": "시작 시각의 변동을 계산하려면 최근 유효 기록일이 2일 이상 필요해.",
    "device_start_range": "시작 시각 변동은 기기가 기록한 시작 시각의 범위야.",
}


def _observation(data, speech, intensity):
    asleep, awake = data["asleep"], data["awake"]
    casual = speech == "casual"
    if not asleep["valid"]:
        return "이 기록에선 수면 시간을 확인할 수 없어." if casual else "이 기록에서는 수면 시간을 확인할 수 없어요."
    line = _OBSERVATION[speech, intensity].format(duration=asleep["display"])
    if awake["valid"]:
        line += f" 기기가 각성으로 분류한 시간은 {awake['display']}" + ("이야." if casual else "이에요.")
    return line


def _limitations(result, speech):
    ids = result["presentation"]["limitation_ids"]
    if speech != "casual" or any(key not in _CASUAL_LIMITS for key in ids):
        return result["limitations"]
    return ["선택 기록 · " + _CASUAL_LIMITS[ids[0]], *(_CASUAL_LIMITS[key] for key in ids[1:])]


def render_personalized_answer(result, pattern_lines, expression):
    """Render validated rule decisions. Profanity consent is recorded independently."""
    data = result["presentation"]
    speech, intensity, mbti = (expression[key] for key in ("speech", "intensity", "mbti"))
    observation = _observation(data["observation"], speech, intensity)
    variants = _ACTIONS.get(data["suggestion_id"])
    action_index = _ACTION_TONES.index(intensity) + (3 if speech == "casual" else 0)
    action = variants[action_index] if variants else result["suggestion"]
    if mbti:
        if data["observation"]["asleep"]["valid"]:
            observation = _OPENINGS[speech][mbti[0] + mbti[2]] + " " + observation
        action = _ACTION_LEADS[speech][mbti[3]] + " " + action

    sections = ["선택 기록\n" + observation]
    if pattern_lines:
        # N presents the broader pattern first, S starts with the individual record.
        sections.insert(0 if mbti and mbti[1] == "N" else 1, "수면 패턴\n" + "\n".join(pattern_lines))
    sections.extend(("실천 제안\n" + action, "데이터 한계\n" + "\n".join(_limitations(result, speech))))
    return "\n\n".join(sections)
