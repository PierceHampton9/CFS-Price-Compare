"""Combine comparable listings into price estimates."""

from __future__ import annotations

from collections import Counter
from typing import Any


def aggregate_listings(
    listings: list[dict[str, Any]],
    warn_below_comparables: int = 10,
    wide_iqr_ratio: float = 0.40,
    support_limit: int = 5,
) -> dict[str, Any]:
    """Aggregate comparable listings into a pricing summary."""
    priced_listings = [_with_price(listing) for listing in listings]
    priced_listings = [listing for listing in priced_listings if listing["_price"] is not None]
    prices = sorted(listing["_price"] for listing in priced_listings)

    if not prices:
        return {
            "median_price_cad": None,
            "iqr_low_cad": None,
            "iqr_high_cad": None,
            "count": 0,
            "sold_count": 0,
            "asking_count": 0,
            "source_counts": {},
            "query_tier": None,
            "confidence_flags": ["no_comparables"],
            "supporting_listings": [],
        }

    median = _percentile(prices, 0.50)
    iqr_low = _percentile(prices, 0.25)
    iqr_high = _percentile(prices, 0.75)
    flags = _confidence_flags(
        count=len(prices),
        median=median,
        iqr_low=iqr_low,
        iqr_high=iqr_high,
        warn_below_comparables=warn_below_comparables,
        wide_iqr_ratio=wide_iqr_ratio,
    )

    sold_count = sum(1 for listing in priced_listings if listing.get("is_sold") is True)

    return {
        "median_price_cad": _round_money(median),
        "iqr_low_cad": _round_money(iqr_low),
        "iqr_high_cad": _round_money(iqr_high),
        "count": len(prices),
        "sold_count": sold_count,
        "asking_count": len(prices) - sold_count,
        "source_counts": dict(Counter(_source(listing) for listing in priced_listings)),
        "query_tier": _query_tier(priced_listings),
        "confidence_flags": flags,
        "supporting_listings": _supporting_listings(priced_listings, median, support_limit),
    }


def _with_price(listing: dict[str, Any]) -> dict[str, Any]:
    copy = dict(listing)
    copy["_price"] = _safe_float(copy.get("total_price_cad"))
    return copy


def _percentile(values: list[float], percentile: float) -> float:
    if len(values) == 1:
        return values[0]

    position = (len(values) - 1) * percentile
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(values) - 1)
    fraction = position - lower_index
    return values[lower_index] + (values[upper_index] - values[lower_index]) * fraction


def _confidence_flags(
    count: int,
    median: float,
    iqr_low: float,
    iqr_high: float,
    warn_below_comparables: int,
    wide_iqr_ratio: float,
) -> list[str]:
    flags = []

    if count < warn_below_comparables:
        flags.append("low_comparable_count")

    if median > 0 and (iqr_high - iqr_low) / median > wide_iqr_ratio:
        flags.append("wide_price_range")

    return flags


def _supporting_listings(
    listings: list[dict[str, Any]],
    median: float,
    support_limit: int,
) -> list[dict[str, Any]]:
    sorted_listings = sorted(
        listings,
        key=lambda listing: (
            _supporting_source_rank(listing),
            _supporting_tier_rank(listing.get("query_tier")),
            abs((listing["_price"] or 0) - median),
        ),
    )
    return [_public_listing(listing) for listing in sorted_listings[:support_limit]]


def _public_listing(listing: dict[str, Any]) -> dict[str, Any]:
    copy = dict(listing)
    copy.pop("_price", None)
    return copy


def _source(listing: dict[str, Any]) -> str:
    source = listing.get("source")
    if source is None:
        return "unknown"
    return str(source)


def _query_tier(listings: list[dict[str, Any]]) -> int | None:
    tiers = [_safe_int(listing.get("query_tier")) for listing in listings]
    tiers = [tier for tier in tiers if tier > 0]
    if not tiers:
        return None
    return min(tiers)


def _supporting_tier_rank(value: Any) -> int:
    tier = _safe_int(value)
    return tier if tier > 0 else 999


def _supporting_source_rank(listing: dict[str, Any]) -> int:
    if listing.get("source_match_verified") is True and _source(listing) in {
        "refurb_io",
        "amazon_renewed",
    }:
        return 0
    return 1


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _round_money(value: float) -> float:
    return round(value, 2)
