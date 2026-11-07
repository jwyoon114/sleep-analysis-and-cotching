"""Strict JSON adapter for the same normalized sleep records as Markdown."""
from datetime import datetime, timedelta, timezone
import json
import math
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

STAGES = {"core", "deep", "rem", "wake", "unspecified"}

EXAMPLE_JSON = json.dumps({"schema_version": 1, "timezone": "Asia/Seoul", "source": "가상 예제 · 실제 측정 기록 아님",
    "sessions": [{"start": "2026-11-01T23:00:00+09:00", "end": "2026-11-02T00:00:00+09:00", "segments": [
        {"start": "2026-11-01T23:00:00+09:00", "end": "2026-11-01T23:20:00+09:00", "stage": "core"},
        {"start": "2026-11-01T23:20:00+09:00", "end": "2026-11-01T23:35:00+09:00", "stage": "deep"},
        {"start": "2026-11-01T23:35:00+09:00", "end": "2026-11-01T23:40:00+09:00", "stage": "wake"},
        {"start": "2026-11-01T23:40:00+09:00", "end": "2026-11-02T00:00:00+09:00", "stage": "rem"}],
        "vitals_summary": [{"metric": "heartRate", "unit": "bpm", "n": 2, "min": 60, "avg": 62, "max": 64}]}]}, ensure_ascii=False, indent=2)


def to_json_export(parsed):
    """Export normalized observations without trusting/repeating derived totals."""
    sessions = []
    for session in parsed["sessions"]:
        vitals = []
        for v in session["vitals_summary"]:
            vital = {k: v[k] for k in ["metric", "unit"]}
            for k, value in v.items():
                if k not in vital and value not in {"—", ""}:
                    vital[k] = int(value) if k == "n" else float(value)
            vitals.append(vital)
        sessions.append({"source": session["source"], "start": session["start"], "end": session["end"],
                         "segments": [{k: s[k] for k in ["start", "end", "stage"]} for s in session["segments"]],
                         "vitals_summary": vitals})
    return json.dumps({"schema_version": 1, "timezone": parsed["timezone"], "sessions": sessions,
                       "samples": parsed.get("samples", [])}, ensure_ascii=False, indent=2)


def parse_json_export(text):
    try:
        data = json.loads(text)
    except (ValueError, RecursionError) as error:
        raise ValueError("JSON 문법이 올바르지 않습니다.") from error
    if isinstance(data, dict) and isinstance(data.get("meta"), dict) and data["meta"].get("schemaVersion") == 2:
        from health_export_kit import adapt
        data = adapt(data)
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("JSON은 schema_version: 1과 sessions 배열을 포함해야 합니다.")
    name = data.get("timezone")
    try:
        tz = timezone(timedelta(hours=9), "Asia/Seoul") if name == "Asia/Seoul" else ZoneInfo(name)
    except (TypeError, ValueError, ZoneInfoNotFoundError) as error:
        raise ValueError("올바른 timezone을 지정하세요. 예: Asia/Seoul") from error

    def timestamp(value):
        try:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None or dt.utcoffset() is None:
                raise ValueError()
            return dt.astimezone(tz)
        except (ValueError, TypeError, OverflowError) as error:
            raise ValueError("시각은 시간대가 있는 ISO 8601 형식이어야 합니다. 예: 2026-11-01T23:00:00+09:00") from error

    def string(value, field):
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise ValueError(f"{field}는 비어 있지 않은 문자열이어야 합니다.")
        return value.strip()

    def number(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("생체지표에는 유한한 숫자를 입력하세요.")
        return value

    sessions = data.get("sessions")
    if not isinstance(sessions, list) or not sessions:
        raise ValueError("sessions는 하나 이상의 수면 기록을 포함해야 합니다.")
    result = []
    for item in sessions:
        if not isinstance(item, dict):
            raise ValueError("각 세션은 JSON 객체여야 합니다.")
        source = string(item.get("source", data.get("source")), "source")
        start, end = timestamp(item.get("start")), timestamp(item.get("end"))
        if not 0 < end.timestamp() - start.timestamp() <= 172800:
            raise ValueError("세션은 시작보다 뒤에 종료되어야 하며 48시간 이하여야 합니다.")
        rows = item.get("segments")
        if not isinstance(rows, list) or not rows:
            raise ValueError("각 세션에 segments 배열이 필요합니다.")
        segments, warnings, previous = [], [], start
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("stage"), str) or row["stage"] not in STAGES:
                raise ValueError("stage는 core, deep, rem, wake, unspecified 중 하나여야 합니다.")
            a, b = timestamp(row.get("start")), timestamp(row.get("end"))
            if a.timestamp() < previous.timestamp() or not a.timestamp() < b.timestamp() <= end.timestamp():
                raise ValueError("수면 구간은 세션 범위 안에서 시간순으로 정렬되고 서로 겹치지 않아야 합니다.")
            if a.timestamp() > previous.timestamp():
                warnings.append(f"{previous.isoformat()} 이후 미기록 구간이 있습니다.")
            minutes = (b.timestamp() - a.timestamp()) / 60
            segments.append({"start": a.isoformat(), "end": b.isoformat(), "stage": row["stage"],
                             "minutes": minutes, "exported_duration_minutes": round(minutes, 1)})
            previous = b
        if previous.timestamp() < end.timestamp():
            warnings.append(f"{previous.isoformat()} 이후 미기록 구간이 있습니다.")
        vitals = item.get("vitals_summary", [])
        if not isinstance(vitals, list):
            raise ValueError("vitals_summary는 배열이어야 합니다.")
        summaries = []
        for vital in vitals:
            if not isinstance(vital, dict):
                raise ValueError("각 생체지표 요약은 객체여야 합니다.")
            summary = {"metric": string(vital.get("metric"), "metric"), "unit": string(vital.get("unit"), "unit")}
            count = number(vital.get("n"))
            if count < 0 or int(count) != count:
                raise ValueError("표본 수 n은 0 이상의 정수여야 합니다.")
            summary["n"] = str(int(count))
            for key in ["min", "avg", "max", "p50", "p90", *sorted(STAGES)]:
                if vital.get(key) is not None:
                    summary[key] = str(number(vital[key]))
            summaries.append(summary)
        totals = {stage: sum(s["minutes"] for s in segments if s["stage"] == stage) for stage in sorted(STAGES)}
        asleep = sum(v for k, v in totals.items() if k != "wake")
        duration = (end.timestamp() - start.timestamp()) / 60
        result.append({"data_type": "wearable", "source": source, "timezone": name,
                       "start": start.isoformat(), "end": end.isoformat(), "recorded_minutes": duration,
                       "asleep_minutes": asleep, "awake_minutes": totals["wake"], "stage_minutes": totals,
                       "unrecorded_minutes": max(0, duration - sum(totals.values())),
                       "session_asleep_ratio_percent": asleep / duration * 100,
                       "wake_segment_count": sum(s["stage"] == "wake" for s in segments),
                       "exported_summary": None, "vitals_summary": summaries,
                       "segments": segments, "warnings": warnings,
                       "interpretation": "웨어러블 기기의 추정 기록입니다. 확정 진단이 아니며 세션 내 수면 비율은 침대 체류시간 기준 수면 효율과 다를 수 있습니다."})
    samples = data.get("samples", [])
    if not isinstance(samples, list):
        raise ValueError("samples는 배열이어야 합니다.")
    normalized_samples = []
    for sample in samples:
        if not isinstance(sample, dict):
            raise ValueError("각 표본은 객체여야 합니다.")
        a = timestamp(sample.get("start"))
        b = timestamp(sample.get("end", sample.get("start")))
        if b.timestamp() < a.timestamp():
            raise ValueError("표본의 종료는 시작보다 빠를 수 없습니다.")
        normalized_samples.append({"metric": string(sample.get("metric"), "metric"),
                                   "unit": string(sample.get("unit"), "unit"),
                                   "source": string(sample.get("source", data.get("source")), "source"),
                                   "start": a.isoformat(), "end": b.isoformat(), "value": float(number(sample.get("value")))})
    return {"timezone": name, "range_start": min(s["start"] for s in result),
            "range_end": max(s["end"] for s in result), "sessions": result, "samples": normalized_samples}
