"""Combine single-session advice and multi-day observations."""

from collections.abc import Iterable, Mapping

from coaching_patterns import analyze_sleep_patterns
from coaching_rules import generate_rule_advice


def generate_free_coaching(
    selected_record: Mapping[str, object] | None,
    records: Iterable[Mapping[str, object]] | None,
    lifestyle: Mapping[str, object] | None,
) -> dict:
    """Return coaching for a selected normalized record and its history."""
    selected = selected_record or {}
    advice = generate_rule_advice(selected, lifestyle)
    patterns = analyze_sleep_patterns(selected, records if records is not None else ())

    limitations = list(dict.fromkeys([advice["limitation"], *patterns["limitations"]]))
    limitations[0] = f"선택 기록 · {limitations[0]}"
    return {
        "observation": advice["observation"],
        "patterns": {
            "reference_day": patterns["reference_day"],
            **patterns["observation"],
            "comparison": patterns["comparison"],
        },
        "suggestion": advice["suggestion"],
        "limitations": limitations,
    }
