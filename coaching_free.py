"""Combine single-session advice and multi-day observations."""

from collections.abc import Iterable, Mapping

from coaching_patterns import analyze_sleep_patterns
from coaching_rules import evaluate_rule_advice


def _period_presentation(period: dict | None) -> dict | None:
    if period is None:
        return None
    average = period["average_asleep_minutes"]
    return {
        "valid_days": period["valid_days"],
        "average_asleep_minutes": average,
        "average_display": f"{average:g}분" if average is not None else None,
    }


def generate_free_coaching(
    selected_record: Mapping[str, object] | None,
    records: Iterable[Mapping[str, object]] | None,
    lifestyle: Mapping[str, object] | None,
    *,
    include_presentation: bool = False,
) -> dict:
    """Return coaching and optionally its versioned presentation data."""
    selected = selected_record or {}
    advice, decisions = evaluate_rule_advice(selected, lifestyle)
    patterns = analyze_sleep_patterns(
        selected, records if records is not None else (), include_limitation_ids=include_presentation,
    )

    limitations = list(dict.fromkeys([advice["limitation"], *patterns["limitations"]]))
    limitations[0] = f"선택 기록 · {limitations[0]}"
    result = {
        "observation": advice["observation"],
        "patterns": {
            "reference_day": patterns["reference_day"],
            **patterns["observation"],
            "comparison": patterns["comparison"],
        },
        "suggestion": advice["suggestion"],
        "limitations": limitations,
    }
    if include_presentation:
        observation = patterns["observation"]
        comparison = patterns["comparison"]
        regularity = observation["regularity"]
        difference = comparison["average_difference_minutes"]
        spread = regularity["start_spread_minutes"]
        result["presentation"] = {
            "version": 1,
            "observation": decisions["observation"],
            "patterns": {
                "recent": _period_presentation(observation["recent"]),
                "previous": _period_presentation(observation["previous"]),
                "comparison": comparison | {
                    "difference_display": f"{difference:+g}분" if difference is not None else None,
                },
                "regularity": {
                    "status": regularity["status"],
                    "start_spread_minutes": spread,
                    "spread_display": f"{spread:g}분" if spread is not None else None,
                },
            },
            "suggestion_id": decisions["suggestion_id"],
            "limitation_ids": decisions["limitation_ids"] + patterns["limitation_ids"],
        }
    return result


def _clock_spread(stamps):
    clocks = sorted(stamp.hour * 60 + stamp.minute for stamp in stamps)
    gaps = [right - left for left, right in zip(clocks, clocks[1:])]
    return 1440 - max([1440 + clocks[0] - clocks[-1], *gaps])


def session_advice(selected, recent, lifestyle, expression):
    """Describe the selected night and recommend at most two grounded actions."""
    from zoneinfo import ZoneInfo
    from coaching_patterns import _timestamp, _sleep_minutes, _window_minutes
    from health_records import is_manual_sleep

    zone = ZoneInfo(selected["timezone"])
    start = _timestamp(selected["start"]).astimezone(zone)
    end = _timestamp(selected["end"]).astimezone(zone)
    manual = is_manual_sleep(selected)
    casual = expression["speech"] == "casual"

    def duration(value):
        hours, minutes = divmod(int(value + 0.5), 60)
        return " ".join(part for part in (f"{hours}시간" if hours else "", f"{minutes}분" if minutes or not hours else "") if part)

    def sleep_minutes(row):
        if is_manual_sleep(row):
            return row["estimated_sleep_minutes"]
        window = _window_minutes(_timestamp(row["start"]), _timestamp(row["end"]))
        return _sleep_minutes(row, window) if window is not None else None

    measured = sleep_minutes(selected)
    end_day = f"{end.month}월 {end.day}일 " if end.date() != start.date() else ""
    until = f"{start.year}년 {start.month}월 {start.day}일 {start:%H:%M}부터 {end_day}{end:%H:%M}까지"
    if manual:
        selected_text = f"{until} 직접 입력했{'어' if casual else '어요'}. 두 시각 사이는 약 {duration(measured)}{'이야' if casual else '이에요'}."
    elif measured is not None:
        selected_text = f"{until} 기기가 기록했고, 그중 약 {duration(measured)}을 수면으로 분류했{'어' if casual else '어요'}."
    else:
        selected_text = f"{until} 기기 기록이 있지만 분류된 수면 시간은 확인하기 어려워{'요' if not casual else ''}."

    comparable = [row for row in recent
                  if row["timezone"] == selected["timezone"] and is_manual_sleep(row) == manual]
    starts = [start] + [_timestamp(row["start"]).astimezone(zone) for row in comparable]
    ends = [end] + [_timestamp(row["end"]).astimezone(zone) for row in comparable]
    distinct_days = len({stamp.date() for stamp in starts})
    consistent = distinct_days == len(starts) and len({stamp.utcoffset() for stamp in starts + ends}) == 1
    drift = max((_clock_spread(starts), "시작"), (_clock_spread(ends), "종료")) if distinct_days >= 3 and consistent else None
    previous = [value for row in comparable if (value := sleep_minutes(row)) is not None]
    difference = measured - sum(previous) / len(previous) if measured is not None and len(previous) >= 2 and consistent else None

    if expression["intensity"] == "gentle":
        ending = "해 볼래?" if casual else "해 보면 좋아요."
    else:
        ending = "해 봐." if casual else "해 보세요."
    usual_bedtime = lifestyle.get("usual_bedtime")
    usual_wake_time = lifestyle.get("usual_wake_time")
    if drift and drift[0] >= 45:
        start_drift = drift[1] == "시작"
        target = (usual_bedtime if start_drift else usual_wake_time) or (start if start_drift else end).strftime("%H:%M")
        action = (f"비교할 수 있는 {distinct_days}일의 기록에서 {drift[1]} 시각이 약 {duration(drift[0])} 차이 났{'어' if casual else '어요'}. "
                  f"다음 이틀은 {target}을 기준으로 {'잠자리 준비 시각' if start_drift else '기상 시각'}을 한 가지 정" + ending)
    elif difference is not None and difference <= -35:
        action = (f"이번 기록의 {'입력 시간 간격' if manual else '추정 수면 시간'}은 앞선 같은 방식의 기록 {len(previous)}개 평균보다 "
                  f"약 {duration(-difference)} 짧았{'어' if casual else '어요'}. 다음 기록에는 평소보다 일찍 시작할 수 있는 준비 한 가지를 정" + ending)
    elif measured is None:
        action = "다음 날에는 기기 앱에서 밤 전체 기록이 들어왔는지 확인" + ending
    else:
        action = f"다음 두 번의 수면에서 {usual_wake_time or end.strftime('%H:%M')} 전후의 실제 기상 시각을 적고 이번 기록과 비교" + ending
        if usual_bedtime and lifestyle.get("caffeine") != "있음" and lifestyle.get("satisfaction") != "나쁨":
            action += f" 잠자리 준비는 설정해 둔 {usual_bedtime}에 맞춰 시작" + ending

    if lifestyle.get("caffeine") == "있음":
        action += " 이번에는 취침 전 카페인 섭취를 기록했으니, 다음번에는 마지막 섭취 시각을 조금 앞당기고 시각을 적어 비교" + ending
    elif lifestyle.get("satisfaction") == "나쁨":
        action += " 이 날의 만족도가 낮았으니 다음 기록에도 기상 직후의 느낌을 한 줄로 기록" + ending

    limitations = []
    if manual:
        limitations.append("직접 입력한 두 시각의 간격으로, 실제로 잠든 시간이나 수면 단계는 확인할 수 없어" + ("" if casual else "요") + ".")
    elif measured is None or selected.get("unrecorded_minutes", 0) > 0:
        limitations.append("기기에 비어 있거나 분류되지 않은 시간이 있어 수면 시간 전체를 확인하기 어려워" + ("" if casual else "요") + ".")
    if distinct_days < 3 or not consistent:
        limitations.append("비교할 수 있는 같은 방식의 기록이 적거나 시각 조건이 달라 평소 경향은 아직 판단하기 어려워" + ("" if casual else "요") + ".")

    body = ["선택 기록\n" + selected_text, "실천 제안\n" + action]
    if limitations:
        body.append("데이터 한계\n" + " ".join(limitations))
    return "\n\n".join(body)
