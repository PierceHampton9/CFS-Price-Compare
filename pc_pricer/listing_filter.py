"""Filter listings before price aggregation."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any


PARTS_TITLE_PATTERNS = [
    r"\bfor parts\b",
    r"\bparts only\b",
    r"\bnot working\b",
    r"\bmotherboard\b",
    r"\bmainboard\b",
    r"\blogic board\b",
    r"\bscreen replacement\b",
    r"\breplacement\s+(lcd|screen|keyboard|battery|cable)\b",
    r"\b(lcd|screen|keyboard|battery|cable)\s+replacement\b",
    r"\b(keyboard|battery|screen|cable)\s+only\b",
    r"\bpalm\s*rest\b",
    r"\bpalmrest\b",
    r"\bhinge\b",
    r"\bbezel\b",
    r"\bbottom case\b",
]


def filter_listings(
    listings: list[dict[str, Any]],
    target_condition: str | None = "good",
) -> dict[str, Any]:
    """Return listings suitable for aggregation plus simple exclusion counts."""
    condition = _clean_condition(target_condition)
    included = []
    excluded_reasons: Counter[str] = Counter()

    for listing in listings:
        reason = exclusion_reason(listing, condition)
        if reason:
            excluded_reasons[reason] += 1
            continue
        included.append(listing)

    return {
        "listings": included,
        "excluded_count": sum(excluded_reasons.values()),
        "excluded_reasons": dict(excluded_reasons),
        "target_condition": condition or "any",
    }


def exclusion_reason(listing: dict[str, Any], target_condition: str | None = "good") -> str | None:
    """Return a short reason if a listing should not be used as a comparable."""
    if _looks_like_parts_listing(listing):
        return "parts_or_accessory"

    condition = _clean_condition(target_condition)
    listing_condition = _clean_condition(listing.get("condition_norm"))
    if condition and not listing_condition:
        return "unknown_condition"
    if condition and listing_condition != condition:
        return "condition_mismatch"

    return None


def _looks_like_parts_listing(listing: dict[str, Any]) -> bool:
    if _clean_condition(listing.get("condition_norm")) == "parts":
        return True

    title = str(listing.get("title") or "").lower()
    return any(re.search(pattern, title) for pattern in PARTS_TITLE_PATTERNS)


def _clean_condition(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text or text == "any":
        return None
    return text
