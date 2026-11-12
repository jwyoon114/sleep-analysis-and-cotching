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
