"""Deterministic, evidence-first free coaching. No provider, randomness or I/O.

Facts and action selection never depend on MBTI or wording preferences. MBTI
only chooses an optional way of carrying out the same action, not physiology.
"""
from collections import Counter
from datetime import timedelta
from zoneinfo import ZoneInfo

from coaching_patterns import _night_day, _timestamp, _window_minutes, _sleep_minutes, _uncertain_start
from coaching_rules import _minutes, _duration_text
from health_records import is_manual_sleep

VERSION = "session-rules-v2"
# 45/35-minute cutoffs below only choose a useful topic among observed changes.
# They are product heuristics, not clinical thresholds or sleep-quality scores.


def duration(value):
    # The formatter already marks fractional minutes as approximate.
    return _duration_text(value)


def _spread(stamps):
    clocks = sorted(s.hour * 60 + s.minute + s.second / 60 for s in stamps)
    gaps = [b - a for a, b in zip(clocks, clocks[1:])]
    return round(1440 - max([1440 + clocks[0] - clocks[-1], *gaps]), 2)


def _shift(current, previous):
    return round((current - previous + 720) % 1440 - 720, 2)


def _clock(stamp):
    return stamp.hour * 60 + stamp.minute + stamp.second / 60


def _sample(row):
    start, end = _timestamp(row.get("start")), _timestamp(row.get("end"))
    window = _window_minutes(start, end)
    if window is None:
        return None
    try:
        zone = ZoneInfo(row["timezone"])
    except (KeyError, ValueError, TypeError):
        return None
    manual = is_manual_sleep(row)
    minutes = _minutes(row.get("estimated_sleep_minutes")) if manual else _sleep_minutes(row, window)
    if minutes is not None and minutes > window + 1e-6:
        minutes = None
    local_start, local_end = start.astimezone(zone), end.astimezone(zone)
    return {"row": row, "start": start, "end": end, "local_start": local_start,
            "local_end": local_end, "day": _night_day(local_start), "manual": manual,
            "minutes": minutes, "window_minutes": window}


def analyze_session(selected, recent, lifestyle):
    """Analyze at most fourteen preceding local nights, separating data sources.

    Duplicate/conflicting IDs, overlapping sessions and split nights cannot
    establish a daily routine. Instants determine elapsed time across DST;
    local clocks are compared only with one zone and a stable UTC offset.
    """
    current = _sample(selected)
    if current is None or current["day"] is None or current["day"].toordinal() < 14:
        raise ValueError("선택한 수면 기록의 날짜와 시간대를 확인해 주세요.")
    candidates, excluded = [], 0
    first = current["day"] - timedelta(days=13)
    for row in recent:
        if selected.get("analysis_id") is not None and row.get("analysis_id") == selected["analysis_id"]:
            continue
        sample = _sample(row)
        if (sample is None or sample["end"] > current["start"]
                or sample["day"] is None or not first <= sample["day"] <= current["day"]):
            excluded += 1
            continue
        if sample["manual"] != current["manual"]:
            continue
        candidates.append(sample)
    ids = Counter(s["row"].get("analysis_id", (s["start"], s["end"])) for s in candidates)
    usable = []
    for sample in candidates:
        key = sample["row"].get("analysis_id", (sample["start"], sample["end"]))
        if ids[key] > 1 or any(sample is not other and sample["start"] < other["end"]
                              and other["start"] < sample["end"] for other in candidates):
            excluded += 1
        else:
            usable.append(sample)
    usable.sort(key=lambda s: (s["end"], s["row"].get("analysis_id", "")), reverse=True)
    samples = [current, *usable[:13]]
    days = Counter(s["day"] for s in samples)
    same_zone = all(s["row"]["timezone"] == selected["timezone"] for s in samples)
    stable_offset = len({stamp.utcoffset() for s in samples for stamp in (s["local_start"], s["local_end"])}) == 1
    single = len(days) == len(samples)
    reliable_start = current["manual"] or not any(
        _uncertain_start(s["row"], s["local_start"], s["minutes"]) for s in samples)
    timing_ok = same_zone and stable_offset and single and reliable_start
    duration_ok = same_zone and single
    previous = [s["minutes"] for s in samples[1:] if s["minutes"] is not None]
    average = sum(previous) / len(previous) if len(previous) >= 2 and duration_ok else None
    minutes = current["minutes"]
    facts = {
        "source": "manual" if current["manual"] else "wearable",
        "start": current["local_start"].isoformat(), "end": current["local_end"].isoformat(),
        "timezone": selected["timezone"], "sleep_minutes": minutes,
        "window_minutes": current["window_minutes"], "sample_days": len(days),
        "previous_duration_count": len(previous), "previous_average_minutes": average,
        "difference_minutes": round(minutes - average, 2) if minutes is not None and average is not None else None,
        "start_spread_minutes": _spread([s["local_start"] for s in samples]) if timing_ok and len(days) >= 3 else None,
        "end_spread_minutes": _spread([s["local_end"] for s in samples]) if timing_ok and len(days) >= 3 else None,
        "previous_start_shift_minutes": _shift(_clock(current["local_start"]), _clock(samples[1]["local_start"]))
            if timing_ok and len(samples) >= 2 else None,
        "late_count": 0, "timing_comparable": timing_ok, "excluded_history": excluded,
    }
    bedtime = lifestyle.get("usual_bedtime")
    if bedtime and timing_ok and len(days) >= 3:
        hour, minute = map(int, bedtime.split(":"))
        facts["late_count"] = sum(45 <= _shift(_clock(s["local_start"]), hour * 60 + minute) < 720 for s in samples)
    limits = []
    if current["manual"]:
        limits.append("manual_estimate")
    if minutes is None:
        limits.append("missing_duration")
    elif not current["manual"] and (_minutes(selected.get("unrecorded_minutes")) or 0) > 0:
        limits.append("incomplete_record")
    if len(days) < 3:
        limits.append("few_records")
    if not timing_ok:
        limits.append("incomparable_clocks")
    if excluded:
        limits.append("excluded_history")

    start_spread, end_spread = facts["start_spread_minutes"], facts["end_spread_minutes"]
    if minutes is None:
        focus = "check_record"
    elif start_spread is not None and max(start_spread, end_spread) >= 45:
        focus = "start_variation" if start_spread >= end_spread else "end_variation"
    elif facts["late_count"] >= 3:
        focus = "repeated_later"
    elif facts["difference_minutes"] is not None and facts["difference_minutes"] <= -35:
        focus = "shorter"
    elif facts["previous_start_shift_minutes"] is not None and facts["previous_start_shift_minutes"] >= 45:
        focus = "later_previous"
    elif lifestyle.get("caffeine") == "있음":
        focus = "caffeine"
    elif lifestyle.get("satisfaction") == "나쁨":
        focus = "satisfaction"
    else:
        focus = "track_wake"
    actions = [focus]
    for key in ("caffeine", "satisfaction"):
        if len(actions) < 2 and lifestyle.get(key) == {"caffeine": "있음", "satisfaction": "나쁨"}[key] and key not in actions:
            actions.append(key)
    return {"facts": facts, "focus": focus, "actions": actions, "limitations": limits}


# Strategies change tools, choice of workflow and review criteria. These are
# optional delivery preferences, never claims about the person's personality.
# Stems end in a verbal noun so all six honorific/intensity variants conjugate
# naturally without rewriting facts or interpolating arbitrary user text.
MBTI_STRATEGIES = {
    "ISTJ": ("private_checklist", "혼자 보는 메모에 이 행동의 체크칸을 만들고, 다음 이틀은 같은 순서로 실행한 뒤 실제 시각과 체크 여부를 비교"),
    "ISFJ": ("private_small_check", "개인 메모에 부담이 가장 적은 준비 하나를 정하고, 다음 이틀은 실행 여부와 기상 직후의 느낌만 확인"),
    "INFJ": ("private_direction_plan", "지키고 싶은 하루의 리듬을 개인 메모에 한 줄로 정하고, 다음 이틀은 이 행동이 생활에 맞는지 돌아보며 계획을 조정"),
    "INTJ": ("private_goal_review", "개인 메모에 바꿀 행동과 확인할 기록 시각을 나란히 정리하고, 다음 두 기록을 모은 뒤 계획을 계속할지 검토"),
    "ISTP": ("private_tool_choice", "메모와 휴대폰 캘린더 중 편한 도구 하나를 골라 이 행동을 표시하고, 다음 기록의 실제 시각과 실행 여부를 비교"),
    "ISFP": ("private_low_burden_choice", "혼자 편하게 할 수 있는 메모나 달력 표시 중 하나를 골라 이 행동을 남기고, 부담이 컸다면 다음에는 방식을 조정"),
    "INFP": ("private_meaning_choice", "이 행동으로 지키고 싶은 일상의 방향을 나만의 한 줄로 적고, 일정이 바뀌는 날에는 실행 방식부터 유연하게 조정"),
    "INTP": ("private_question_test", "개인 메모에 이번 행동으로 확인하고 싶은 질문 하나를 정하고, 메모나 캘린더 중 편한 방식으로 다음 두 기록을 비교"),
    "ESTJ": ("calendar_checklist", "원한다면 함께 쓰는 캘린더에 준비할 일만 등록하고, 다음 이틀은 같은 순서로 실행한 뒤 실제 시각과 체크 여부를 비교"),
    "ESFJ": ("optional_small_promise", "원한다면 가까운 사람과 이 준비만 가볍게 약속하고, 다음 이틀은 부담 없이 지킬 수 있었는지 함께 확인"),
    "ENFJ": ("optional_direction_promise", "원한다면 함께 지키고 싶은 생활 리듬을 한 줄로 정하고, 다음 이틀은 이 행동을 실천하기 편한 환경을 함께 점검"),
    "ENTJ": ("calendar_goal_review", "원한다면 공유 캘린더에 행동과 확인 시점을 정하고, 다음 두 기록의 실제 시각을 비교한 뒤 계획을 유지할지 결정"),
    "ESTP": ("visible_tool_choice", "눈에 잘 보이는 달력 표시와 캘린더 메모 중 하나를 골라 이 행동을 남기고, 다음 기록에서 실제 시각과 실행 여부를 비교"),
    "ESFP": ("optional_easy_choice", "원한다면 가까운 사람에게 준비만 가볍게 알리거나 눈에 보이는 달력에 표시하고, 오늘 편한 방법 하나만 선택"),
    "ENFP": ("optional_direction_choice", "원한다면 함께 바꾸고 싶은 생활 리듬을 이야기하거나 개인 음성 메모로 남기고, 일정에 맞는 실행 방식 하나를 선택"),
    "ENTP": ("optional_question_choice", "원한다면 함께 확인할 질문 하나를 정하거나 개인 메모로 남기고, 캘린더와 체크 메모 중 편한 방식으로 다음 두 기록을 비교"),
}


def _say(polite, casual, expression):
    return casual if expression["speech"] == "casual" else polite


def _do(stem, expression):
    endings = {("polite", "gentle"): "해 보면 좋아요.", ("polite", "firm"): "하세요.",
               ("polite", "direct"): "하세요.", ("casual", "gentle"): "해 볼래?",
               ("casual", "firm"): "해 봐.", ("casual", "direct"): "해."}
    return stem + endings[expression["speech"], expression["intensity"]]


def render_session(analysis, lifestyle, expression):
    f = analysis["facts"]
    start, end = _timestamp(f["start"]), _timestamp(f["end"])
    day_end = f"{end.month}월 {end.day}일 " if start.date() != end.date() else ""
    period = f"{start.year}년 {start.month}월 {start.day}일 {start:%H:%M}부터 {day_end}{end:%H:%M}까지"
    manual = f["source"] == "manual"
    if manual:
        observation = period + _say(" 직접 입력했어요.", " 직접 입력했어.", expression)
        if f["sleep_minutes"] is not None:
            observation += f" 추정 수면 시간은 약 {duration(f['sleep_minutes']).removeprefix('약 ')}" + _say("이에요.", "이야.", expression)
    elif f["sleep_minutes"] is not None:
        observation = period + f" 기기가 기록했고, 그중 약 {duration(f['sleep_minutes']).removeprefix('약 ')}을 수면으로 분류했" + _say("어요.", "어.", expression)
    else:
        observation = period + _say(" 기기 기록은 있지만 분류된 수면 시간은 확인하기 어려워요.", " 기기 기록은 있지만 분류된 수면 시간은 확인하기 어려워.", expression)

    focus = analysis["focus"]
    why = ""
    if focus in ("start_variation", "end_variation"):
        field = "시작" if focus == "start_variation" else "종료"
        spread = f["start_spread_minutes" if field == "시작" else "end_spread_minutes"]
        why = f"비교할 수 있는 {f['sample_days']}일의 기록에서 {field} 시각이 약 {duration(spread).removeprefix('약 ')} 차이 났" + _say("어요.", "어.", expression)
    elif focus == "shorter":
        why = f"이번 {'추정 수면 시간' if manual else '기기 분류 수면 시간'}은 앞선 같은 방식의 기록 {f['previous_duration_count']}개 평균보다 약 {duration(-f['difference_minutes']).removeprefix('약 ')} 짧았" + _say("어요.", "어.", expression)
    elif focus == "repeated_later":
        why = f"비교 가능한 {f['sample_days']}일 중 {f['late_count']}일의 시작 시각이 직접 적은 평소 취침 시각 {lifestyle['usual_bedtime']}보다 45분 이상 늦었" + _say("어요.", "어.", expression)
    elif focus == "later_previous":
        why = f"이번 시작 시각은 바로 앞 기록보다 약 {duration(f['previous_start_shift_minutes']).removeprefix('약 ')} 늦었" + _say("어요. 한 번의 차이로 평소 습관을 단정하지는 않아요.", "어. 한 번의 차이로 평소 습관을 단정하지는 않아.", expression)
    if why:
        observation += " " + why

    wake = lifestyle.get("usual_wake_time") or end.strftime("%H:%M")
    bed = lifestyle.get("usual_bedtime") or start.strftime("%H:%M")
    stems = {
        "start_variation": f"다음 이틀은 {bed}을 참고해 생활 일정에 맞는 준비 기준 시각 하나를 정하고, 실제 시작 시각을 메모",
        "end_variation": f"다음 이틀은 {wake}을 참고해 생활 일정에 맞는 기상 기준 시각 하나를 정하고, 실제 기상 시각을 메모",
        "shorter": "다음 잠자리 준비 전에 끝낼 일 하나를 미리 마치고, 다음 두 기록의 시간을 이번 기록과 비교",
        "repeated_later": f"직접 적은 {bed} 전에 마칠 준비 한 가지를 정하고, 다음 두 기록의 시작 시각을 비교",
        "later_previous": "이번에 준비가 끝난 시각을 적고, 다음 기록에는 준비할 일 하나를 미리 마칠 수 있는지 확인",
        "check_record": "다음 날 기기 앱에서 밤 전체 기록이 들어왔는지 확인",
        "caffeine": "취침 전 6시간 이내 카페인 섭취를 기록했으니, 마지막 섭취 시각을 적고 다음 기록에도 같은 항목을 메모",
        "satisfaction": "이 날의 만족도를 낮게 기록했으니, 다음 기상 직후에도 느낌을 한 줄로 메모",
        "track_wake": f"다음 두 번의 실제 기상 시각을 적고, {wake} 전후였는지 비교",
    }
    intensity = expression["intensity"]
    leads = {
        "gentle": _say("한 번에 다 바꾸지 않아도 괜찮아요. 이번에는 작은 행동부터 골라봐요.", "한 번에 다 바꾸지 않아도 괜찮아. 이번에는 작은 행동부터 골라보자.", expression),
        "firm": _say("다음 기록에서 확인할 행동을 정리했어요.", "다음 기록에서 확인할 행동을 정리했어.", expression),
        "direct": _say("우선순위를 정하세요. 아래 첫 행동부터 실행하세요.", "우선순위를 정해. 아래 첫 행동부터 실행해.", expression),
    }
    # Consent permits a mild expletive; it does not require it. Only an observed
    # timing deviation calls for it here. Never address/label the person roughly.
    rough = expression.get("allow_profanity") is True and intensity == "direct" and focus in (
        "start_variation", "end_variation", "shorter", "repeated_later", "later_previous")
    lead = ("젠장, " if rough else "") + leads[intensity]
    direct_actions = {
        "start_variation": (f"참고 시각은 {bed}입니다. 생활 일정에 맞는 준비 기준을 하나 정하세요. 다음 이틀의 실제 시작 시각을 적으세요.", f"참고 시각은 {bed}이야. 생활 일정에 맞는 준비 기준을 하나 정해. 다음 이틀의 실제 시작 시각을 적어."),
        "end_variation": (f"참고 시각은 {wake}입니다. 생활 일정에 맞는 기상 기준을 하나 정하세요. 다음 이틀의 실제 기상 시각을 적으세요.", f"참고 시각은 {wake}이야. 생활 일정에 맞는 기상 기준을 하나 정해. 다음 이틀의 실제 기상 시각을 적어."),
        "shorter": ("잠자리 준비 전에 끝낼 일 하나를 정하세요. 그 일을 미리 마치세요. 다음 두 기록의 시간을 이번 기록과 비교하세요.", "잠자리 준비 전에 끝낼 일 하나를 정해. 그 일을 미리 마쳐. 다음 두 기록의 시간을 이번 기록과 비교해."),
        "repeated_later": (f"직접 적은 {bed} 전에 마칠 준비 하나를 정하세요. 다음 두 기록의 시작 시각으로 실행 결과를 확인하세요.", f"직접 적은 {bed} 전에 마칠 준비 하나를 정해. 다음 두 기록의 시작 시각으로 실행 결과를 확인해."),
        "later_previous": ("이번 준비가 끝난 시각부터 적으세요. 다음에는 준비할 일 하나를 미리 마칠 수 있는지 확인하세요.", "이번 준비가 끝난 시각부터 적어. 다음에는 준비할 일 하나를 미리 마칠 수 있는지 확인해."),
        "check_record": ("기기 앱에서 밤 전체 기록이 들어왔는지 먼저 확인하세요. 확인되지 않은 시간을 수면 시간으로 해석하지 마세요.", "기기 앱에서 밤 전체 기록이 들어왔는지 먼저 확인해. 확인되지 않은 시간을 수면 시간으로 해석하지 마."),
        "caffeine": ("취침 전 6시간 이내 카페인 섭취를 기록했어요. 마지막 섭취 시각을 적으세요. 다음 기록에도 같은 항목을 남기세요.", "취침 전 6시간 이내 카페인 섭취를 기록했어. 마지막 섭취 시각을 적어. 다음 기록에도 같은 항목을 남겨."),
        "satisfaction": ("이 날의 만족도를 낮게 기록했어요. 다음 기상 직후의 느낌도 한 줄로 적으세요.", "이 날의 만족도를 낮게 기록했어. 다음 기상 직후의 느낌도 한 줄로 적어."),
        "track_wake": (f"다음 두 번의 실제 기상 시각부터 적으세요. {wake} 전후였는지 기록으로 비교하세요.", f"다음 두 번의 실제 기상 시각부터 적어. {wake} 전후였는지 기록으로 비교해."),
    }
    lines = [lead]
    for index, action in enumerate(analysis["actions"], 1):
        text = _say(*direct_actions[action], expression) if intensity == "direct" else _do(stems[action], expression)
        lines.append(f"{index}. " + text)
    mbti = expression.get("mbti")
    if mbti in MBTI_STRATEGIES:
        lines.append("실행 방법 · " + _do(MBTI_STRATEGIES[mbti][1], expression))
        if mbti.startswith("E"):
            lines.append(_say("건강 기록이나 수치는 다른 사람에게 공유하지 않아도 돼요.", "건강 기록이나 수치는 다른 사람에게 공유하지 않아도 돼.", expression))
    elif intensity == "direct":
        lines.append(_say("다음 기록에서 실행 여부를 확인하세요.", "다음 기록에서 실행 여부를 확인해.", expression))

    limit_stems = {
        "manual_estimate": ("직접 입력한 두 시각으로 계산한 추정치예요. 실제로 잠든 시간이나 수면 단계는 확인할 수 없어요.", "직접 입력한 두 시각으로 계산한 추정치야. 실제로 잠든 시간이나 수면 단계는 확인할 수 없어."),
        "missing_duration": ("확인되지 않은 수면 시간을 측정 구간 길이로 채우지 않았어요.", "확인되지 않은 수면 시간을 측정 구간 길이로 채우지 않았어."),
        "incomplete_record": ("기기에 미기록 구간이 있어 밤 전체의 수면 시간을 확정할 수 없어요.", "기기에 미기록 구간이 있어 밤 전체의 수면 시간을 확정할 수 없어."),
        "few_records": (f"같은 방식의 비교 가능한 기록은 {f['sample_days']}일뿐이에요. 평소 경향은 아직 판단하기 어려워요.", f"같은 방식의 비교 가능한 기록은 {f['sample_days']}일뿐이야. 평소 경향은 아직 판단하기 어려워."),
        "incomparable_clocks": ("시간대·UTC 오프셋이 다르거나 한 밤의 시작 시각을 하나로 정하기 어려워 시각 변동 비교는 보류했어요.", "시간대·UTC 오프셋이 다르거나 한 밤의 시작 시각을 하나로 정하기 어려워 시각 변동 비교는 보류했어."),
        "excluded_history": ("선택한 기록보다 뒤의 기록, 최근 14일 범위 밖의 기록, 시간이 불명확하거나 겹치는 기록은 비교에서 제외했어요.", "선택한 기록보다 뒤의 기록, 최근 14일 범위 밖의 기록, 시간이 불명확하거나 겹치는 기록은 비교에서 제외했어."),
    }
    sections = ["선택 기록\n" + observation, "실천 제안\n" + "\n".join(lines)]
    if analysis["limitations"]:
        sections.append("데이터 한계\n" + " ".join(_say(*limit_stems[key], expression) for key in analysis["limitations"]))
    return "\n\n".join(sections)
