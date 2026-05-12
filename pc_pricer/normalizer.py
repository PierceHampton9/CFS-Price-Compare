"""Normalize listing data from different sources."""

from __future__ import annotations

from typing import Any


EBAY_CONDITION_MAP = {
    "new": "mint",
    "open box": "excellent",
    "certified - refurbished": "excellent",
    "excellent - refurbished": "excellent",
    "very good - refurbished": "good",
    "good - refurbished": "good",
    "seller refurbished": "good",
    "used": "good",
    "for parts or not working": "parts",
}

REFURB_IO_CONDITION_MAP = {
    "grade a": "good",
    "a-grade": "good",
    "grade b": "good",
    "b-grade": "good",
    "refurbished": "good",
    "good": "good",
    "excellent": "excellent",
    "grade c": "parts",
    "c-grade": "parts",
}


CONDITION_MAPS = {
    "ebay": EBAY_CONDITION_MAP,
    "refurb_io": REFURB_IO_CONDITION_MAP,
}


def normalize_listing(listing: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a listing with normalized fields filled in."""
    normalized = dict(listing)
    normalized["condition_norm"] = normalize_condition(
        normalized.get("source"),
        normalized.get("condition_raw"),
    )
    return normalized


def normalize_listings(listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize every listing in a list."""
    return [normalize_listing(listing) for listing in listings]


def normalize_condition(source: Any, condition_raw: Any) -> str | None:
    """Map a source-specific condition label to the canonical condition scale."""
    source_key = _clean_key(source)
    condition_key = _clean_key(condition_raw)
    if not source_key or not condition_key:
        return None

    condition_map = CONDITION_MAPS.get(source_key)
    if not condition_map:
        return None
    return condition_map.get(condition_key)


def _clean_key(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    text = " ".join(text.split()).strip().lower()
    return text or None
