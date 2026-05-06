"""Format pricing results for humans."""

from __future__ import annotations

from typing import Any


FLAG_LABELS = {
    "no_comparables": "No usable comparable listings",
    "low_comparable_count": "Low comparable count",
    "wide_price_range": "Wide price range",
}

FILTER_LABELS = {
    "condition_mismatch": "condition mismatch",
    "parts_or_accessory": "parts/accessory listing",
}


def format_price_report(result: dict[str, Any]) -> str:
    """Format an aggregation result for human review."""
    lines = [
        "Price estimate",
        "--------------",
    ]

    if not result.get("count"):
        lines.extend(_filter_lines(result))
        lines.append("No usable comparable listings found.")
        lines.extend(_confidence_lines(result))
        return "\n".join(lines)

    lines.extend(
        [
            f"Median price:      {_format_money(result.get('median_price_cad'))}",
            f"Comparable range:  {_format_money(result.get('iqr_low_cad'))} - {_format_money(result.get('iqr_high_cad'))}",
            f"Comparables:       {result.get('count')}",
            f"Query tier:        {_format_query_tier(result.get('query_tier'))}",
            f"Sold / asking:     {result.get('sold_count', 0)} sold, {result.get('asking_count', 0)} asking",
            f"Sources:           {_format_source_counts(result.get('source_counts'))}",
        ]
    )
    lines.extend(_filter_lines(result))
    lines.extend(_confidence_lines(result))
    lines.extend(_supporting_listing_lines(result.get("supporting_listings") or []))
    return "\n".join(lines)


def _filter_lines(result: dict[str, Any]) -> list[str]:
    if "excluded_count" not in result and "target_condition" not in result:
        return []

    lines = [f"Target condition:  {result.get('target_condition') or 'any'}"]
    excluded_count = result.get("excluded_count", 0)
    if not excluded_count:
        lines.append("Filtered out:      0")
        return lines

    lines.append(f"Filtered out:      {excluded_count} ({_format_filter_reasons(result.get('excluded_reasons'))})")
    return lines


def _format_filter_reasons(reasons: Any) -> str:
    if not isinstance(reasons, dict) or not reasons:
        return "unknown reason"

    parts = []
    for reason, count in sorted(reasons.items()):
        label = FILTER_LABELS.get(reason, str(reason))
        parts.append(f"{label}: {count}")
    return ", ".join(parts)


def _confidence_lines(result: dict[str, Any]) -> list[str]:
    flags = result.get("confidence_flags") or []
    if not flags:
        return ["Confidence flags: none"]

    labels = [FLAG_LABELS.get(flag, str(flag)) for flag in flags]
    return [f"Confidence flags: {', '.join(labels)}"]


def _supporting_listing_lines(listings: list[dict[str, Any]]) -> list[str]:
    if not listings:
        return []

    lines = [
        "",
        "Supporting listings",
        "-------------------",
    ]
    for index, listing in enumerate(listings, start=1):
        lines.append(f"{index}. {listing.get('title') or 'Untitled listing'}")
        lines.append(f"   Price:     {format_listing_price(listing)}")
        lines.append(f"   Source:    {listing.get('source') or 'unknown'}")
        lines.append(f"   Status:    {_format_listing_status(listing)}")
        lines.append(f"   Condition: {format_condition(listing)}")
        lines.append(f"   Tier:      {_format_query_tier(listing.get('query_tier'))}")
        lines.append(f"   URL:       {listing.get('url') or 'Unknown'}")
    return lines


def format_listing_price(listing: dict[str, Any]) -> str:
    item_price = _format_money(listing.get("item_price_cad"))
    shipping = _format_money(listing.get("shipping_cad"))
    total = _format_money(listing.get("total_price_cad"))

    if listing.get("shipping_is_estimated"):
        return f"{item_price} item price + unknown shipping"
    if listing.get("shipping_cad") is None:
        return total
    return f"{total} total ({item_price} item + {shipping} shipping)"


def _format_listing_status(listing: dict[str, Any]) -> str:
    return "sold" if listing.get("is_sold") is True else "asking"


def format_condition(listing: dict[str, Any]) -> str:
    raw = listing.get("condition_raw") or "Unknown"
    normalized = listing.get("condition_norm")
    if not normalized:
        return raw
    return f"{normalized} ({raw})"


def _format_source_counts(source_counts: Any) -> str:
    if not isinstance(source_counts, dict) or not source_counts:
        return "none"

    parts = [f"{source}: {count}" for source, count in sorted(source_counts.items())]
    return ", ".join(parts)


def _format_query_tier(query_tier: Any) -> str:
    if query_tier is None:
        return "unknown"
    return str(query_tier)


def _format_money(value: Any) -> str:
    try:
        return f"${float(value):,.2f} CAD"
    except (TypeError, ValueError):
        return "Unknown"
