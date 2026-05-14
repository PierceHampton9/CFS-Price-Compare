"""Format pricing results for humans."""

from __future__ import annotations

from typing import Any

from pc_pricer.source_labels import format_cpu_value, format_source_basis, format_source_name


FLAG_LABELS = {
    "no_comparables": "No usable comparable listings",
    "low_comparable_count": "Low comparable count",
    "no_queries": "No usable search queries",
    "source_disagreement": "Source disagreement",
    "source_unavailable": "Source unavailable",
    "wide_price_range": "Wide price range",
}

LIMITATION_LABELS = {
    "asking_prices_only": "eBay active listing estimate; conservative range discounts the eBay median",
}

WARNING_LABELS = {
    "unknown_shipping": "Unknown shipping on one or more comparables",
    "high_shipping": "High shipping on one or more comparables",
    "non_canadian_location": "Non-Canadian location on one or more comparables",
}

FILTER_LABELS = {
    "condition_mismatch": "condition mismatch",
    "displaced_by_retailer": "displaced by verified retailer listing",
    "parts_or_accessory": "parts/accessory listing",
    "ram_mismatch": "RAM mismatch",
    "storage_mismatch": "storage mismatch",
    "unavailable_listing": "unavailable listing",
    "user_removed_comparable": "manually removed comparable",
    "unverified_retailer_listing": "unverified retailer listing",
    "variant_mismatch": "variant/screen-size mismatch",
    "unknown_condition": "unknown condition",
}


def format_price_report(
    result: dict[str, Any],
    advanced: bool = True,
    include_all_comparables: bool = False,
) -> str:
    """Format an aggregation result for human review."""
    lines = [
        "Price estimate",
        "--------------",
    ]

    if not result.get("count"):
        lines.extend(_spec_lines(result.get("specs")))
        if advanced:
            lines.extend(_query_lines(result.get("queries")))
            lines.extend(_search_count_lines(result))
        lines.extend(_filter_lines(result))
        if advanced:
            lines.extend(_source_status_lines(result))
            lines.extend(_source_quote_lines(result))
        lines.append("No usable comparable listings found.")
        lines.extend(_confidence_lines(result))
        lines.extend(_limitation_lines(result))
        lines.extend(_warning_lines(result))
        return "\n".join(lines)

    lines.extend(_price_lines(result))
    if advanced:
        lines.extend(_search_count_lines(result))
        lines.extend(_pricing_basis_lines(result))
        lines.extend(_source_status_lines(result))
        lines.extend(_source_quote_lines(result))
        lines.extend(_source_diagnostic_lines(result))
    lines.extend(_spec_lines(result.get("specs")))
    if advanced:
        lines.extend(_query_lines(result.get("queries")))
    lines.extend(_filter_lines(result))
    lines.extend(_confidence_lines(result))
    lines.extend(_limitation_lines(result))
    lines.extend(_warning_lines(result))
    lines.extend(_supporting_listing_lines(_report_listings(result, include_all_comparables)))
    return "\n".join(lines)


def _price_lines(result: dict[str, Any]) -> list[str]:
    lines = []
    if result.get("pricing_basis") == "asking_adjusted":
        lines.append(
            f"Conservative est.: {_format_money(result.get('conservative_low_cad'))} - {_format_money(result.get('conservative_high_cad'))}"
        )
        lines.append(f"eBay median:       {_format_money(result.get('asking_median_price_cad'))}")
    else:
        lines.append(f"Median price:      {_format_money(result.get('median_price_cad'))}")

    range_label = "Source quote range" if result.get("pricing_basis") == "weighted_sources" else "Comparable range"
    lines.append(f"{range_label}:  {_format_money(_range_low(result))} - {_format_money(_range_high(result))}")
    lines.append(f"Comparables:       {result.get('count')}")
    lines.append(f"Query tier:        {_format_query_tier(result.get('query_tier'))}")
    lines.append(f"Sources:           {_format_source_counts(result.get('source_counts'))}")
    return lines


def _spec_lines(specs: Any) -> list[str]:
    if not isinstance(specs, dict) or not specs:
        return []

    parts = _spec_parts(specs)
    text = " ".join(str(part) for part in parts if part)
    if not text:
        return []
    return [f"{_spec_label(specs)}:    {text}"]


def _spec_parts(specs: dict[str, Any]) -> list[Any]:
    device_type = str(specs.get("device_type") or "computer").lower()
    if device_type == "phone":
        return [
            specs.get("brand"),
            _display_model(specs),
            specs.get("variant"),
            specs.get("screen_size"),
            specs.get("storage_capacity"),
            specs.get("carrier"),
        ]
    if device_type == "tablet":
        return [
            specs.get("brand"),
            _display_model(specs),
            specs.get("variant"),
            specs.get("screen_size"),
            specs.get("storage_capacity"),
            specs.get("connectivity"),
        ]
    if device_type == "monitor":
        return [
            specs.get("brand"),
            _display_model(specs),
            specs.get("size"),
            specs.get("resolution"),
            specs.get("refresh_rate"),
        ]
    if device_type == "printer":
        return [specs.get("brand"), _display_model(specs), specs.get("printer_type"), specs.get("color")]
    if device_type == "storage":
        return [
            specs.get("brand"),
            _display_model(specs),
            specs.get("capacity"),
            specs.get("drive_type"),
            specs.get("drive_form_factor"),
            specs.get("interface"),
        ]
    if device_type == "computer":
        return [
            specs.get("brand"),
            _display_model(specs),
            specs.get("variant"),
            specs.get("screen_size"),
            _cpu_label(specs.get("cpu_short") or specs.get("cpu")),
            _ram_label(specs.get("ram_gb")),
        ]
    return []


def _spec_label(specs: dict[str, Any]) -> str:
    device_type = str(specs.get("device_type") or "computer").lower()
    if specs.get("input_method") == "manual" and device_type != "computer":
        return f"Manual {device_type}"
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


def _pricing_basis_lines(result: dict[str, Any]) -> list[str]:
    basis = result.get("pricing_basis")
    source_basis = result.get("source_basis")
    lines = []

    if basis:
        lines.append(f"Pricing basis:    {_format_pricing_basis(result)}")
    if source_basis:
        lines.append(f"Source basis:     {format_source_basis(source_basis)}")
    return lines


def _format_pricing_basis(result: dict[str, Any]) -> str:
    value = result.get("pricing_basis")
    if value == "sold":
        return "comparable listings"
    if value == "asking_adjusted":
        return f"eBay active listings, discounted {_discount_percent_range(result)}"
    if value == "active":
        return "active listings"
    if value == "mixed":
        return "comparable listings"
    if value == "unknown":
        return "unknown"
    if value == "weighted_sources":
        return "weighted source quote average"
    return str(value)


def _source_quote_lines(result: dict[str, Any]) -> list[str]:
    quotes = result.get("source_quotes") or []
    errors = result.get("source_errors") or []
    lines = []
    if quotes:
        parts = []
        for quote in quotes:
            source = format_source_name(quote.get("source"))
            price = _format_money(quote.get("price_cad"))
            weight = quote.get("weight")
            marker = " verified" if quote.get("verified") else ""
            weight_text = f", weight {weight:g}" if isinstance(weight, (int, float)) else ""
            listing_count = quote.get("listing_count")
            count_text = f", {listing_count} listing{'s' if listing_count != 1 else ''}" if listing_count else ""
            parts.append(f"{source}: {price}{marker}{weight_text}{count_text}")
        lines.append(f"Source quotes:    {', '.join(parts)}")
    if errors:
        sources = sorted({format_source_name(error.get("source")) for error in errors if isinstance(error, dict)})
        lines.append(f"Source errors:    {', '.join(sources)}")
    return lines


def _source_status_lines(result: dict[str, Any]) -> list[str]:
    statuses = result.get("source_statuses") or []
    if not isinstance(statuses, list) or not statuses:
        return []

    lines = ["Source status:"]
    for status in statuses:
        if not isinstance(status, dict):
            continue
        source = format_source_name(status.get("source"))
        state = _source_status_label(status.get("status"))
        query_count = _safe_int(status.get("query_count"))
        listing_count = _safe_int(status.get("raw_listing_count"))
        message = str(status.get("message") or "").strip()
        detail_parts = []
        if query_count:
            detail_parts.append(f"{query_count} quer{'y' if query_count == 1 else 'ies'}")
        if status.get("searched"):
            detail_parts.append(f"{listing_count} raw listing{'s' if listing_count != 1 else ''}")
        if message:
            detail_parts.append(message)
        detail_text = f" ({'; '.join(detail_parts)})" if detail_parts else ""
        lines.append(f"  {source}: {state}{detail_text}")
    return lines


def _source_status_label(value: Any) -> str:
    labels = {
        "disabled": "disabled",
        "error": "error",
        "no_results": "no results",
        "not_searched": "not searched",
        "returned": "returned listings",
    }
    return labels.get(str(value or "").strip().lower(), str(value or "unknown"))


def _source_diagnostic_lines(result: dict[str, Any]) -> list[str]:
    diagnostics = result.get("source_diagnostics") or []
    if not diagnostics:
        return []

    lines = ["Source diagnostics:"]
    for diagnostic in diagnostics[:5]:
        if not isinstance(diagnostic, dict):
            continue
        source = format_source_name(diagnostic.get("source"))
        title = diagnostic.get("title") or "Untitled listing"
        status = "verified" if diagnostic.get("source_match_verified") else "not verified"
        reasons = diagnostic.get("source_match_reasons") or []
        filter_reason = diagnostic.get("filter_exclusion_reason")
        details = []
        if reasons:
            details.append(f"match: {', '.join(str(reason) for reason in reasons)}")
        if filter_reason:
            details.append(f"filter: {filter_reason}")
        if diagnostic.get("generated_query_text"):
            details.append(f"generated query: {diagnostic.get('generated_query_text')}")
        detail_text = f" ({'; '.join(details)})" if details else ""
        lines.append(f"  {source}: {status} - {title}{detail_text}")
    if len(diagnostics) > 5:
        lines.append(f"  ... {len(diagnostics) - 5} more source diagnostics omitted")
    return lines


def _discount_percent_range(result: dict[str, Any]) -> str:
    low = _safe_percent(result.get("asking_only_discount_low"))
    high = _safe_percent(result.get("asking_only_discount_high"))
    if low is None or high is None:
        return "unknown range"
    return f"{low}-{high}%"


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


def _limitation_lines(result: dict[str, Any]) -> list[str]:
    limitations = result.get("pricing_limitations") or []
    if not limitations:
        return []

    labels = [LIMITATION_LABELS.get(limitation, str(limitation)) for limitation in limitations]
    return [f"Pricing limits:   {', '.join(labels)}"]


def _warning_lines(result: dict[str, Any]) -> list[str]:
    warnings = result.get("listing_warnings") or []
    if not warnings:
        return []

    labels = [WARNING_LABELS.get(warning, str(warning)) for warning in warnings]
    return [f"Listing warnings: {', '.join(labels)}"]


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
        lines.append(f"   Source:    {format_source_name(listing.get('source'))}")
        lines.append(f"   Condition: {format_condition(listing)}")
        lines.append(f"   Tier:      {_format_query_tier(listing.get('query_tier'))}")
        if listing.get("query_text"):
            lines.append(f"   Query:     {listing.get('query_text')}")
        lines.append(f"   Location:  {format_location(listing.get('location'))}")
        lines.append(f"   URL:       {listing.get('url') or 'Unknown'}")
    return lines


def _report_listings(result: dict[str, Any], include_all_comparables: bool) -> list[dict[str, Any]]:
    if include_all_comparables and isinstance(result.get("all_comparable_listings"), list):
        listings = result.get("all_comparable_listings") or []
    else:
        listings = result.get("supporting_listings") or []
    return [
        listing
        for listing in listings
        if isinstance(listing, dict) and listing.get("excluded_by_user") is not True
    ]


def format_listing_price(listing: dict[str, Any]) -> str:
    item_price = _format_money(listing.get("item_price_cad"))
    shipping = _format_money(listing.get("shipping_cad"))
    total = _format_money(listing.get("total_price_cad"))

    if listing.get("shipping_is_estimated"):
        return f"{item_price} item price + unknown shipping"
    if listing.get("shipping_cad") is None:
        return total
    return f"{total} total ({item_price} item + {shipping} shipping)"


def format_condition(listing: dict[str, Any]) -> str:
    raw = listing.get("condition_raw") or "Unknown"
    normalized = listing.get("condition_norm")
    if not normalized:
        return raw
    return f"{normalized} ({raw})"


def format_location(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "Unknown"
    parts = [part.strip() for part in text.split(",")]
    if parts and parts[-1].upper() == "CA":
        parts[-1] = "Canada"
    return ", ".join(part for part in parts if part)


def _format_source_counts(source_counts: Any) -> str:
    if not isinstance(source_counts, dict) or not source_counts:
        return "none"

    parts = [f"{format_source_name(source)}: {count}" for source, count in sorted(source_counts.items())]
    return ", ".join(parts)


def _format_query_tier(query_tier: Any) -> str:
    if query_tier is None:
        return "unknown"
    return str(query_tier)


def _range_low(result: dict[str, Any]) -> Any:
    return result.get("price_low_cad", result.get("iqr_low_cad"))


def _range_high(result: dict[str, Any]) -> Any:
    return result.get("price_high_cad", result.get("iqr_high_cad"))


def _ram_label(ram_gb: Any) -> str | None:
    if not ram_gb:
        return None
    return f"{ram_gb}GB"


def _cpu_label(value: Any) -> str | None:
    return format_cpu_value(value) or None


def _format_money(value: Any) -> str:
    try:
        return f"${float(value):,.2f} CAD"
    except (TypeError, ValueError):
        return "Unknown"


def _safe_percent(value: Any) -> int | None:
    try:
        return round(float(value) * 100)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
