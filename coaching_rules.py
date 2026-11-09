"""Generate coaching text from one normalized sleep record and lifestyle answers."""

from collections.abc import Mapping

# The import parsers limit a session to 48 hours. This is a data bound.
_MAX_SESSION_MINUTES = 48 * 60
_MINUTE_TOLERANCE = 1e-6


def _minutes(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    # This range check also rejects NaN and infinities.
    return value if 0 <= value <= _MAX_SESSION_MINUTES else None


def _duration_text(minutes: int | float) -> str:
    if 0 < minutes < 1:
        return "1분 미만"
    whole_minutes = round(minutes)
    hours, remainder = divmod(whole_minutes, 60)
    if hours and remainder:
        text = f"{hours}시간 {remainder}분"
    elif hours:
        text = f"{hours}시간"
    else:
        text = f"{remainder}분"
    return f"약 {text}" if whole_minutes != minutes else text


def generate_rule_advice(
    selected_record: Mapping[str, object] | None,
    lifestyle: Mapping[str, object] | None,
) -> dict[str, str]:
    """Return an observation, one suggestion, and a data limitation.

    Duration fields use the numeric minutes produced by the sleep parsers.
    A missing measurement is treated as unknown. The recording duration
    can bound measurements and is never used to fill in sleep time.
    """
    record = selected_record or {}
    habits = lifestyle or {}
    asleep = _minutes(record.get("asleep_minutes"))
    recorded = _minutes(record.get("recorded_minutes"))
    if asleep is None or (
        recorded is not None
        and (recorded == 0 or asleep > recorded + _MINUTE_TOLERANCE)
    ):
        return {
            "observation": "이 기록에서 수면 시간을 확인할 수 없습니다.",
            "suggestion": "기기 앱에서 수면 시간이 기록됐는지 확인한 뒤 다시 불러와 보세요.",
            "limitation": "수면 시간 값이 없거나 유효한 기록 범위를 벗어났습니다.",
        }

    observation = f"기기에서 수면으로 분류한 시간은 {_duration_text(asleep)}입니다."
    measured_minutes = asleep
    awake = _minutes(record.get("awake_minutes"))
    if awake is not None and (
        recorded is None or asleep + awake <= recorded + _MINUTE_TOLERANCE
    ):
        observation += f" 각성으로 분류한 시간은 {_duration_text(awake)}입니다."
        measured_minutes += awake

    limitation = "기기가 추정한 한 건의 기록입니다. 평소 수면 패턴이나 변화의 원인을 판단하기에는 정보가 부족합니다."
    unrecorded = _minutes(record.get("unrecorded_minutes"))
    if unrecorded and (
        recorded is None or measured_minutes + unrecorded <= recorded + _MINUTE_TOLERANCE
    ):
        limitation += " 기록 안에 미기록 구간이 있습니다."

    if habits.get("caffeine") == "있음":
        suggestion = "카페인을 섭취한 시각을 적고, 며칠 동안의 수면 기록과 함께 살펴보세요."
    elif habits.get("regularity") == "자주 달라짐":
        suggestion = "며칠 동안 취침·기상 시각을 적어 보고, 일정에 맞춰 반복하기 쉬운 시간대를 찾아보세요."
    elif habits.get("satisfaction") == "나쁨":
        suggestion = "다음 기록에는 아침에 느낀 휴식 정도를 함께 적어, 기기 기록과 비교해 보세요."
    else:
        suggestion = "며칠 동안 수면 기록을 모아 날짜별 수면 시간을 비교해 보세요."

    return {
        "observation": observation,
        "suggestion": suggestion,
        "limitation": limitation,
    }
