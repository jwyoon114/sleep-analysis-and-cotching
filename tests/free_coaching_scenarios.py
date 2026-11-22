"""Synthetic fixtures only; never use a user's exported health file."""
from datetime import datetime, timedelta


def night(day=15, clock="23:00", minutes=420, *, manual=True, zone="Asia/Seoul"):
    start = datetime.fromisoformat(f"2024-11-{day:02d}T{clock}:00+09:00")
    if start.hour < 12:
        start += timedelta(days=1)
    end = start + timedelta(minutes=minutes)
    result = {"analysis_id": f"synthetic-{'manual' if manual else 'wearable'}-{day}",
              "start": start.isoformat(), "end": end.isoformat(), "timezone": zone}
    if manual:
        result.update(data_type="manual", estimated_sleep_minutes=minutes)
    else:
        result.update(asleep_minutes=minutes, recorded_minutes=minutes, unrecorded_minutes=0,
                      segments=[{"stage": "core", "start": start.isoformat(), "end": end.isoformat()}])
    return result


def variable_nights(*, manual=True):
    # Same morning time, bedtime range 90 minutes, no inferred sleep stages.
    selected = night(15, "00:30", 390, manual=manual)
    recent = [night(14, "23:00", 480, manual=manual), night(13, "23:30", 450, manual=manual)]
    return selected, recent
