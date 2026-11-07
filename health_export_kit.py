"""Adapter for Health Export Kit JSON schemaVersion 2."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from export_times import bounds, point

STAGE_MAP = {"asleepCore": "core", "asleepDeep": "deep", "asleepREM": "rem",
             "awake": "wake", "asleepUnspecified": "unspecified", "asleep": "unspecified"}
STREAM_NAMES = {"heartRate": "Heart Rate", "hrvSDNN": "HRV SDNN",
                "respiratoryRate": "Respiratory Rate", "oxygenSaturation": "Oxygen Saturation"}


def adapt(data):
    meta = data["meta"]
    name = meta.get("timeZone")
    try:
        tz = timezone(timedelta(hours=9), "Asia/Seoul") if name == "Asia/Seoul" else ZoneInfo(name)
        a = datetime.fromisoformat(meta["rangeStart"])
        b = datetime.fromisoformat(meta["rangeEnd"])
        if a.utcoffset() is None or b.utcoffset() is None:
            raise ValueError()
        a, b = a.astimezone(tz), b.astimezone(tz)
        if not a < b or b - a > timedelta(days=366):
            raise ValueError()
    except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError) as error:
        raise ValueError("Health Export Kit의 날짜 범위와 시간대를 확인하세요.") from error
    sleep = data.get("sleep")
    if not isinstance(sleep, dict) or not isinstance(sleep.get("sessions"), list) or not sleep["sessions"]:
        raise ValueError("JSON의 sleep.sessions에 수면 기록이 없습니다.")
    sessions, windows = [], []
    for item in sleep["sessions"]:
        if not isinstance(item, dict):
            raise ValueError("수면 세션 형식이 올바르지 않습니다.")
        start, end = bounds(item.get("start"), item.get("end"), a, b, tz)
        window = [(start, end)]
        windows.append((start - timedelta(minutes=10), end + timedelta(minutes=10)))
        stages = item.get("stages")
        if not isinstance(stages, list) or not stages:
            raise ValueError("JSON의 각 세션에 stages 배열이 필요합니다.")
        segments = []
        for stage in stages:
            if not isinstance(stage, dict) or not isinstance(stage.get("stage"), str) or stage["stage"] not in STAGE_MAP:
                raise ValueError("지원하지 않는 Health Export Kit 수면 단계입니다.")
            segments.append({"start": point(stage.get("start"), window, tz).isoformat(),
                             "end": point(stage.get("end"), window, tz).isoformat(), "stage": STAGE_MAP[stage["stage"]]})
        summaries = []
        vitals = item.get("vitals", {})
        if not isinstance(vitals, dict):
            raise ValueError("vitals는 객체여야 합니다.")
        for metric, value in vitals.items():
            if not isinstance(value, dict):
                raise ValueError("생체지표 요약 형식이 올바르지 않습니다.")
            summary = {"metric": metric, "unit": value.get("unit"), "n": value.get("count")}
            for key in ["min", "avg", "max", "p50", "p90"]:
                if key in value:
                    summary[key] = value[key]
            by_stage = value.get("byStage", {})
            if not isinstance(by_stage, dict):
                raise ValueError("byStage는 객체여야 합니다.")
            for key, val in by_stage.items():
                if key not in STAGE_MAP:
                    raise ValueError("지원하지 않는 생체지표 단계입니다.")
                summary[STAGE_MAP[key]] = val
            summaries.append(summary)
        sessions.append({"source": item.get("source"), "start": start.isoformat(), "end": end.isoformat(),
                         "segments": segments, "vitals_summary": summaries})
    samples = []
    streams = sleep.get("streams", {})
    if not isinstance(streams, dict):
        raise ValueError("sleep.streams는 객체여야 합니다.")
    for metric, stream in streams.items():
        if metric in {"anchor", "timeFormat"}:
            continue
        if not isinstance(stream, dict):
            raise ValueError("스트림 형식이 올바르지 않습니다.")
        if stream.get("downsampledTo") is not None:
            raise ValueError("집계 스트림은 아직 지원하지 않습니다. verbose(전체 표본)로 내보내세요.")
        schema, sources, rows = stream.get("tupleSchema"), stream.get("sources"), stream.get("samples")
        if not isinstance(schema, list) or any(not isinstance(k, str) for k in schema) or len(schema) != len(set(schema)):
            raise ValueError("스트림 tupleSchema가 올바르지 않습니다.")
        if not {"time", "value", "sourceIdx"}.issubset(schema):
            raise ValueError("스트림에 time, value, sourceIdx가 필요합니다. verbose로 내보내세요.")
        if not isinstance(sources, list) or not isinstance(rows, list):
            raise ValueError("스트림 sources와 samples 배열이 필요합니다.")
        for row in rows:
            if not isinstance(row, list) or len(row) != len(schema):
                raise ValueError("스트림 표본의 열 수가 tupleSchema와 다릅니다.")
            row = dict(zip(schema, row))
            idx = row["sourceIdx"]
            if type(idx) is not int or not 0 <= idx < len(sources):
                raise ValueError("스트림 sourceIdx가 sources 범위를 벗어납니다.")
            start = point(row["time"], windows, tz)
            end = point(row["endTime"], windows, tz) if "endTime" in row else start
            samples.append({"metric": STREAM_NAMES.get(metric, metric), "unit": stream.get("unit"),
                            "source": sources[idx], "start": start.isoformat(), "end": end.isoformat(), "value": row["value"]})
    return {"schema_version": 1, "timezone": name, "sessions": sessions, "samples": samples}
