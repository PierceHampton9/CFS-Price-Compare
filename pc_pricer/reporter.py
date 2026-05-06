"""Format pricing results for humans."""

from __future__ import annotations

from typing import Any


FLAG_LABELS = {
    "no_comparables": "No usable comparable listings",
    "low_comparable_count": "Low comparable count",
    "no_queries": "No usable search queries",
    "wide_price_range": "Wide price range",
    "asking_prices_only": "Asking prices only",
    "unknown_shipping": "Unknown shipping on one or more comparables",
    "high_shipping": "High shipping on one or more comparables",
    "non_canadian_location": "Non-Canadian location on one or more comparables",
}

FILTER_LABELS = {
    "condition_mismatch": "condition mismatch",
    "parts_or_accessory": "parts/accessory listing",
    "unknown_condition": "unknown condition",
}


def format_price_report(result: dict[str, Any]) -> str:
    """Format an aggregation result for human review."""
    lines = [
        "Price estimate",
        "--------------",
    ]

    if not result.get("count"):
        lines.extend(_spec_lines(result.get("specs")))
        lines.extend(_query_lines(result.get("queries")))
        lines.extend(_search_count_lines(result))
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
    lines.extend(_search_count_lines(result))
    lines.extend(_spec_lines(result.get("specs")))
    lines.extend(_query_lines(result.get("queries")))
    lines.extend(_filter_lines(result))
    lines.extend(_confidence_lines(result))
    lines.extend(_supporting_listing_lines(result.get("supporting_listings") or []))
    return "\n".join(lines)


def _spec_lines(specs: Any) -> list[str]:
    if not isinstance(specs, dict) or not specs:
        return []

    parts = [
        specs.get("brand"),
        _display_model(specs),
        specs.get("cpu_short") or specs.get("cpu"),
        _ram_label(specs.get("ram_gb")),
    ]
    text = " ".join(str(part) for part in parts if part)
    if not text:
        return []
    return [f"{_spec_label(specs)}:    {text}"]


def _spec_label(specs: dict[str, Any]) -> str:
    if specs.get("input_method") == "manual":
        return "Manual specs"
    return "Detected specs"


def _display_model(specs: dict[str, Any]) -> Any:
    if specs.get("search_model"):
        return specs.get("search_model")
    if specs.get("model_is_machine_type"):
        return None
    return specs.get("model")


def _query_lines(queries: Any) -> list[str]:
    if not isinstance(queries, list) or not queries:
        return []

    lines = ["Queries used:"]
    for query in queries:
        if not isinstance(query, dict):
            continue
        text = query.get("text")
        if not text:
            continue
        if query.get("tier") is None:
            lines.append(f"  {text}")
        else:
            lines.append(f"  T{_format_query_tier(query.get('tier'))}: {text}")
    return lines


def _search_count_lines(result: dict[str, Any]) -> list[str]:
    raw_count = result.get("raw_listing_count")
    deduped_count = result.get("deduped_listing_count")
    if raw_count is None or deduped_count is None:
        return []
    return [f"Search results:    {raw_count} raw, {deduped_count} after dedupe"]


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
        if listing.get("query_text"):
            lines.append(f"   Query:     {listing.get('query_text')}")
        lines.append(f"   Location:  {listing.get('location') or 'Unknown'}")
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


def _ram_label(ram_gb: Any) -> str | None:
    if not ram_gb:
        return None
    return f"{ram_gb}GB"


def _format_money(value: Any) -> str:
    try:
        return f"${float(value):,.2f} CAD"
    except (TypeError, ValueError):
        return "Unknown"
