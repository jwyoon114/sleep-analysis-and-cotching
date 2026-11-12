"""Summarize normalized sleep sessions for the rule-based coaching engine."""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from itertools import chain
from math import fsum

_MIN_TREND_DAYS = 3
_MIN_START_DAYS = 2
_DAY_MINUTES = 24 * 60
_MINUTE_TOLERANCE = 1e-6


@dataclass(frozen=True)
class _Session:
    day: date
    start: datetime
    end: datetime
    asleep_minutes: int | float | None
    timezone_name: str | None


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError:
        return None
    return stamp if stamp.utcoffset() is not None else None


def _night_day(start: datetime | None) -> date | None:
    if start is None:
        return None
    if start.hour >= 12:
        return start.date()
    return start.date() - timedelta(days=1) if start.date() > date.min else None


def _record_day(record: Mapping[str, object], start: datetime | None) -> date | None:
    sync = record.get("health_sync")
    if isinstance(sync, Mapping) and "day" in sync:
        value = sync["day"]
        if not isinstance(value, str):
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return _night_day(start)


def _window_minutes(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    minutes = (end - start).total_seconds() / 60
    return minutes if 0 < minutes <= 2 * _DAY_MINUTES else None


def _sleep_minutes(record: Mapping[str, object], window: float) -> int | float | None:
    asleep = record.get("asleep_minutes")
    if isinstance(asleep, bool) or not isinstance(asleep, (int, float)):
        return None
    recorded = record.get("recorded_minutes")
    if isinstance(recorded, (int, float)) and not isinstance(recorded, bool):
        if recorded == 0:
            return None
        if recorded > 0:
            window = min(window, recorded)
    return asleep if 0 <= asleep <= window + _MINUTE_TOLERANCE else None


def _uncertain_start(record: Mapping[str, object], start: datetime, asleep: int | float | None) -> bool:
    # A synced session may start at noon because it was split there.
    if asleep == 0 or (isinstance(record.get("health_sync"), Mapping) and start.time() == time(12)):
        return True
    segments = record.get("segments")
    if isinstance(segments, list) and segments and isinstance(segments[0], Mapping):
        first = segments[0]
        return first.get("stage") == "wake" or _timestamp(first.get("start")) != start
    return False


def _overlap_days(sessions: Iterable[_Session]) -> set[date]:
    overlapping = set()
    furthest = None
    for session in sorted(sessions, key=lambda row: (row.start, row.end)):
        if furthest is not None and session.start < furthest.end:
            overlapping.update((furthest.day, session.day))
        if furthest is None or session.end > furthest.end:
            furthest = session
    return overlapping


def _period(start: date, end: date, days: dict[date, list[_Session]]) -> dict:
    totals = [
        fsum(row.asleep_minutes for row in sessions)
        for day, sessions in days.items()
        if start <= day <= end
    ]
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "valid_days": len(totals),
        "average_asleep_minutes": fsum(totals) / len(totals) if totals else None,
    }


def _regularity(days: dict[date, list[_Session]], uncertain_start: bool) -> dict:
    result = {"sample_days": len(days), "start_spread_minutes": None}
    if uncertain_start or any(len(sessions) != 1 for sessions in days.values()):
        return result | {"status": "unreliable_start"}

    sessions = [sessions[0] for sessions in days.values()]
    if any(row.timezone_name is None for row in sessions):
        return result | {"status": "unreliable_start"}
    zones = {(row.timezone_name, row.start.utcoffset()) for row in sessions}
    if len(zones) > 1:
        return result | {"status": "mixed_timezones"}
    if len(sessions) < _MIN_START_DAYS:
        return result | {"status": "insufficient_days"}

    # The smallest arc on the clock is the complement of its largest empty gap.
    starts = sorted(
        row.start.hour * 60 + row.start.minute
        + row.start.second / 60 + row.start.microsecond / 60_000_000
        for row in sessions
    )
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    gaps.append(_DAY_MINUTES + starts[0] - starts[-1])
    return result | {
        "status": "available",
        "start_spread_minutes": round(_DAY_MINUTES - max(gaps), 2),
    }


def analyze_sleep_patterns(
    selected_record: Mapping[str, object],
    records: Iterable[Mapping[str, object]],
    *,
    include_limitation_ids: bool = False,
) -> dict:
    """Compare two seven-day windows ending on the selected sleep day.

    The selected session is included once. Sleep days follow the sync
    convention of local noon to noon. The selected end time bounds the
    observations, including when another session shares its sleep day.
    Callers preparing a presentation can request the corresponding limitation IDs.
    """
    selected_start = _timestamp(selected_record.get("start"))
    cutoff = _timestamp(selected_record.get("end"))
    reference = _record_day(selected_record, selected_start)
    if (
        reference is None
        or reference.toordinal() < 14
        or reference != _night_day(selected_start)
        or _window_minutes(selected_start, cutoff) is None
    ):
        result = {
            "reference_day": None,
            "observation": {
                "recent": None,
                "previous": None,
                "regularity": {
                    "status": "invalid_reference",
                    "sample_days": 0,
                    "start_spread_minutes": None,
                },
            },
            "comparison": {"status": "invalid_reference", "average_difference_minutes": None},
            "limitations": ["선택한 기록의 날짜와 시간 구간을 확인해 주세요."],
        }
        if include_limitation_ids:
            result["limitation_ids"] = ["invalid_reference"]
        return result

    recent_start = reference - timedelta(days=6)
    previous_start = reference - timedelta(days=13)
    previous_end = recent_start - timedelta(days=1)
    sessions = {}
    identities = {}
    unusable_days = set()
    ambiguous_days = set()
    unreliable_starts = set()
    undated_record = False

    for record in chain((selected_record,), records):
        start = _timestamp(record.get("start"))
        end = _timestamp(record.get("end"))
        if (start is not None and start >= cutoff) or (end is not None and end > cutoff):
            continue
        day = _record_day(record, start)
        if day is None:
            undated_record = True
            continue
        if day > reference:
            continue
        window = _window_minutes(start, end)
        if window is None or day != _night_day(start):
            unusable_days.add(day)
            unreliable_starts.add(day)
            continue

        asleep = _sleep_minutes(record, window)
        if asleep is None:
            unusable_days.add(day)
        zone = record.get("timezone")
        zone = zone.strip() if isinstance(zone, str) and zone.strip() else None
        if _uncertain_start(record, start, asleep):
            unreliable_starts.add(day)

        key = (day, start.isoformat(), end.isoformat(), asleep, zone)
        record_id = record.get("analysis_id")
        if isinstance(record_id, str) and record_id:
            first = identities.setdefault(record_id, key)
            if first != key:
                ambiguous_days.update((first[0], day))
        sessions[key] = _Session(day, start, end, asleep, zone)

    ambiguous_days.update(_overlap_days(sessions.values()))
    excluded_days = unusable_days | ambiguous_days
    daily = defaultdict(list)
    for session in sessions.values():
        if previous_start <= session.day <= reference and session.day not in excluded_days:
            daily[session.day].append(session)

    recent = _period(recent_start, reference, daily)
    previous = _period(previous_start, previous_end, daily)
    enough_days = min(recent["valid_days"], previous["valid_days"]) >= _MIN_TREND_DAYS
    difference = (
        round(recent["average_asleep_minutes"] - previous["average_asleep_minutes"], 2)
        if enough_days else None
    )
    for period in (recent, previous):
        average = period["average_asleep_minutes"]
        if average is not None:
            period["average_asleep_minutes"] = round(average, 2)

    recent_days = {day: rows for day, rows in daily.items() if day >= recent_start}
    uncertain_start = undated_record or any(
        recent_start <= day <= reference for day in unreliable_starts
    )
    regularity = _regularity(recent_days, uncertain_start)

    limitations = [
        ("valid_days_device_estimates", "평균은 유효한 기록이 있는 날의 기기 추정 수면 시간만 사용합니다."),
    ]
    if undated_record or any(previous_start <= day <= reference for day in unusable_days):
        limitations.append(("unusable_records_excluded", "날짜, 시간 구간 또는 수면 시간을 확인할 수 없는 기록은 집계에서 제외했습니다."))
    if any(previous_start <= day <= reference for day in ambiguous_days):
        limitations.append(("ambiguous_records_excluded", "기록이 겹치거나 같은 기록 ID의 값이 다른 날은 집계에서 제외했습니다."))
    if not enough_days:
        limitations.append(("insufficient_comparison_days", "두 기간에 각각 유효 기록일이 3일 이상 있어야 평균 차이를 표시합니다."))
    if regularity["status"] == "mixed_timezones":
        limitations.append(("mixed_timezones", "최근 기록의 시간대 또는 UTC 오프셋이 달라 시작 시각 변동을 보류했습니다."))
    elif regularity["status"] == "unreliable_start":
        limitations.append(("unreliable_start", "날짜별 시작 시각을 하나씩 신뢰하기 어려워 시작 시각 변동을 보류했습니다."))
    elif regularity["status"] == "insufficient_days":
        limitations.append(("insufficient_start_days", "시작 시각 변동을 계산하려면 최근 유효 기록일이 2일 이상 필요합니다."))
    else:
        limitations.append(("device_start_range", "시작 시각 변동은 기기 기록의 시작 시각 범위입니다."))

    result = {
        "reference_day": reference.isoformat(),
        "observation": {"recent": recent, "previous": previous, "regularity": regularity},
        "comparison": {
            "status": "available" if enough_days else "insufficient_days",
            "average_difference_minutes": difference,
        },
        "limitations": [message for _, message in limitations],
    }
    if include_limitation_ids:
        result["limitation_ids"] = [identifier for identifier, _ in limitations]
    return result
