"""Resolve shortened export clocks without guessing between multiple dates."""
from datetime import datetime, timedelta
import re

SHORT = re.compile(r"^\d{2}:\d{2}:\d{2}$")


def point(value, windows, tz):
    if not isinstance(value, str):
        raise ValueError("내보내기 시각이 문자열이 아닙니다.")
    value = value.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}T", value):
        dt = datetime.fromisoformat(value)
        if dt.utcoffset() is None:
            raise ValueError("전체 날짜 시각에는 시간대가 필요합니다.")
        return dt.astimezone(tz)
    candidates = set()
    for lower, upper in windows:
        if SHORT.fullmatch(value):
            day = lower.date()
            while day <= upper.date():
                dt = datetime.combine(day, datetime.strptime(value, "%H:%M:%S").time(), tzinfo=tz)
                if lower <= dt <= upper:
                    candidates.add(dt)
                day += timedelta(days=1)
        else:
            for year in range(lower.year, upper.year + 1):
                try:
                    dt = datetime.strptime(f"{year}-{value}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
                except ValueError:
                    continue
                if lower <= dt <= upper:
                    candidates.add(dt)
    if len(candidates) != 1:
        raise ValueError(f"시각의 날짜를 확정할 수 없습니다: {value}. 날짜가 포함된 내보내기를 사용하세요.")
    return candidates.pop()


def bounds(start, end, range_start, range_end, tz):
    if isinstance(start, str) and isinstance(end, str) and SHORT.fullmatch(start) and SHORT.fullmatch(end):
        candidates = []
        day = range_start.date() - timedelta(days=2)
        while day <= range_end.date():
            a = datetime.combine(day, datetime.strptime(start, "%H:%M:%S").time(), tzinfo=tz)
            b = datetime.combine(day, datetime.strptime(end, "%H:%M:%S").time(), tzinfo=tz)
            if b <= a:
                b += timedelta(days=1)
            if a < range_end and b > range_start:
                candidates.append((a, b))
            day += timedelta(days=1)
        if len(candidates) != 1:
            raise ValueError("수면 기록의 날짜가 모호합니다. 날짜가 포함된 형식으로 내보내세요.")
        return candidates[0]
    windows = [(range_start - timedelta(days=2), range_end + timedelta(days=2))]
    return point(start, windows, tz), point(end, windows, tz)
