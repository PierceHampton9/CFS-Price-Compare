"""Run the pricing pipeline from specs through comparable aggregation."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Protocol

from pc_pricer.aggregator import aggregate_listings
from pc_pricer.listing_filter import exclusion_reason, filter_listings
from pc_pricer.normalizer import normalize_listings
from pc_pricer.price_adjustment import apply_pricing_basis
from pc_pricer.quality import add_listing_quality_flags
from pc_pricer.query_builder import build_queries


class ListingSource(Protocol):
    def search(self, query: str, max_results: int) -> list[dict[str, Any]]:
        """Return source listings for a search query."""
        ...


def price_specs(
    specs: dict[str, Any],
    source: ListingSource | Sequence[ListingSource],
    limit_per_query: int = 10,
    target_condition: str | None = "good",
    warn_below_comparables: int = 10,
    wide_iqr_ratio: float = 0.40,
    support_limit: int = 5,
    high_shipping_cad: float = 75.0,
    high_shipping_ratio: float = 0.25,
    asking_discount_low: float = 0.00,
    asking_discount_high: float = 0.05,
) -> dict[str, Any]:
    """Price detected specs using tiered queries from a listing source."""
    queries = build_queries(specs)
    sources = _source_list(source)
    raw_listings, source_errors, source_statuses = _search_queries(sources, queries, limit_per_query, specs)
    deduped_listings = _dedupe_listings(raw_listings)
    normalized_listings = normalize_listings(deduped_listings)
    normalized_listings = _add_source_match_flags(normalized_listings, specs)
    filtered = filter_listings(
        normalized_listings,
        target_condition=target_condition,
        device_type=specs.get("device_type"),
        target_specs=specs,
    )
    pricing_listings, pricing_excluded_reasons = _pricing_listings(filtered["listings"])
    if pricing_excluded_reasons:
        filtered["excluded_count"] += sum(pricing_excluded_reasons.values())
        filtered["excluded_reasons"] = _merge_reason_counts(filtered["excluded_reasons"], pricing_excluded_reasons)
    _mark_included_in_pricing(normalized_listings, pricing_listings)
    source_diagnostics = _source_diagnostics(
        normalized_listings,
        specs,
        target_condition=target_condition,
    )

    result = aggregate_listings(
        pricing_listings,
        warn_below_comparables=warn_below_comparables,
        wide_iqr_ratio=wide_iqr_ratio,
        support_limit=support_limit,
    )
    result = apply_pricing_basis(
        result,
        asking_discount_low=asking_discount_low,
        asking_discount_high=asking_discount_high,
    )
    result.update(
        {
            "specs": _public_specs(specs),
            "queries": queries,
            "raw_listing_count": len(raw_listings),
            "deduped_listing_count": len(deduped_listings),
            "target_condition": filtered["target_condition"],
            "excluded_count": filtered["excluded_count"],
            "excluded_reasons": filtered["excluded_reasons"],
            "source_diagnostics": source_diagnostics,
            "source_statuses": source_statuses,
        }
    )
    result = _apply_source_quote_basis(
        result,
        pricing_listings,
        warn_below_comparables=warn_below_comparables,
        wide_iqr_ratio=wide_iqr_ratio,
        support_limit=support_limit,
        asking_discount_low=asking_discount_low,
        asking_discount_high=asking_discount_high,
    )
    result["source_errors"] = source_errors
    if source_errors:
        result["confidence_flags"] = _append_flag(result.get("confidence_flags"), "source_unavailable")
    result = add_listing_quality_flags(
        result,
        pricing_listings,
        high_shipping_cad=high_shipping_cad,
        high_shipping_ratio=high_shipping_ratio,
    )

    if not queries:
        result["confidence_flags"] = _append_flag(result.get("confidence_flags"), "no_queries")

    return result


def _source_list(source: ListingSource | Sequence[ListingSource]) -> list[ListingSource]:
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        return [item for item in source if getattr(item, "enabled", True)]
    if getattr(source, "enabled", True):
        return [source]
    return []


def _search_queries(
    sources: list[ListingSource],
    queries: list[dict[str, Any]],
    limit_per_query: int,
    specs: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, Any]]]:
    listings = []
    errors = []
    statuses = {
        _source_name(source): {
            "source": _source_name(source),
            "enabled": True,
            "searched": False,
            "query_count": 0,
            "queries": [],
            "raw_listing_count": 0,
            "error_count": 0,
            "errors": [],
        }
        for source in sources
    }
    searched = set()
    for query in queries:
        generated_query_text = str(query.get("text") or "").strip()
        if not generated_query_text:
            continue

        for source in sources:
            source_name = _source_name(source)
            query_text = _source_query_text(source_name, query, specs)
            if not query_text:
                continue
            searched_key = (source_name, query_text.lower())
            if searched_key in searched:
                continue
            searched.add(searched_key)
            status = statuses.setdefault(
                source_name,
                {
                    "source": source_name,
                    "enabled": True,
                    "searched": False,
                    "query_count": 0,
                    "queries": [],
                    "raw_listing_count": 0,
                    "error_count": 0,
                    "errors": [],
                },
            )
            status["searched"] = True
            status["query_count"] += 1
            status["queries"].append(query_text)
            try:
                source_listings = source.search(query_text, limit_per_query)
            except RuntimeError as exc:
                status["error_count"] += 1
                status["errors"].append(str(exc))
                errors.append(
                    {
                        "source": source_name,
                        "query": query_text,
                        "message": str(exc),
                    }
                )
                continue

            _add_source_runtime_stats(status, getattr(source, "last_search_stats", None))
            status["raw_listing_count"] += len(source_listings)
            for listing in source_listings:
                tagged = dict(listing)
                tagged["query_tier"] = query.get("tier")
                tagged["query_reason"] = query.get("reason")
                tagged["query_text"] = query_text
                if query_text != generated_query_text:
                    tagged["generated_query_text"] = generated_query_text
                listings.append(tagged)

    return listings, errors, list(statuses.values())


def _add_source_runtime_stats(status: dict[str, Any], stats: Any) -> None:
    if not isinstance(stats, dict):
        return
    status["candidate_count"] = _safe_int(status.get("candidate_count")) + _safe_int(stats.get("candidate_count"))
    status["detail_page_count"] = _safe_int(status.get("detail_page_count")) + _safe_int(stats.get("detail_page_count"))
    status["detail_error_count"] = _safe_int(status.get("detail_error_count")) + _safe_int(stats.get("detail_error_count"))
    detail_urls = status.setdefault("detail_urls", [])
    if not isinstance(detail_urls, list):
        detail_urls = []
        status["detail_urls"] = detail_urls
    for url in stats.get("detail_urls") or []:
        if url and url not in detail_urls:
            detail_urls.append(url)


def _source_name(source: ListingSource) -> str:
    return str(getattr(source, "name", source.__class__.__name__) or "unknown")


def _source_query_text(source_name: str, query: dict[str, Any], specs: dict[str, Any]) -> str:
    query_text = str(query.get("text") or "").strip()
    if source_name not in {"refurb_io", "amazon_renewed"}:
        return query_text
    if (
        source_name == "refurb_io"
        and _safe_int(query.get("tier")) == 1
        and _clean_text(specs.get("oem_sku")) == query_text
    ):
        return query_text

    retailer_query = _retailer_query_from_specs(specs)
    if source_name == "amazon_renewed":
        if _safe_int(query.get("tier")) == 1 and _clean_text(specs.get("oem_sku")) == query_text:
            return _amazon_query_text(retailer_query or query_text)
        return _amazon_query_text(query_text)
    return retailer_query or query_text


def _retailer_query_from_specs(specs: dict[str, Any]) -> str | None:
    device_type = str(specs.get("device_type") or "computer").strip().lower()
    brand = _clean_text(specs.get("brand"))
    model = _clean_text(specs.get("search_model")) or _clean_text(specs.get("model"))
    if not brand or not model:
        return None

    if device_type in {"phone", "tablet"}:
        parts = [
            brand,
            model,
            _clean_text(specs.get("variant")),
            _clean_text(specs.get("storage_capacity")),
        ]
    elif device_type == "computer":
        parts = [brand, model]
    else:
        parts = [brand, model]
    return " ".join(part for part in parts if part) or None


def _clean_text(value: Any) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text or None


def _amazon_query_text(query_text: str) -> str:
    text = query_text.strip()
    if not text:
        return ""
    if re.search(r"\brenew(ed|al)?\b", text, flags=re.IGNORECASE):
        return text
    return f"{text} Renewed"


def _dedupe_listings(listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped = []
    seen = set()

    for listing in listings:
        keys = _listing_keys(listing)
        if any(key in seen for key in keys):
            continue

        seen.update(keys)
        deduped.append(listing)

    return deduped


def _listing_keys(listing: dict[str, Any]) -> list[tuple[str, str]]:
    keys = []
    source = str(listing.get("source") or "unknown").strip().lower()
    item_id = str(listing.get("item_id") or "").strip().lower()
    if item_id:
        keys.append(("source_item", f"{source}|{item_id}"))

    url = str(listing.get("url") or "").strip().lower()
    if url:
        keys.append(("url", url))

    title = str(listing.get("title") or "").strip().lower()
    price = str(listing.get("total_price_cad") or "").strip()
    keys.append(("title_price", f"{title}|{price}"))
    return keys


def _public_specs(specs: dict[str, Any]) -> dict[str, Any]:
    public = dict(specs)
    public.pop("raw", None)
    public.pop("serial_number", None)
    return public


def _source_diagnostics(
    listings: list[dict[str, Any]],
    specs: dict[str, Any],
    target_condition: str | None,
) -> list[dict[str, Any]]:
    diagnostics = []
    for listing in listings:
        source = _source_key(listing)
        if source not in {"refurb_io", "amazon_renewed"}:
            continue

        filter_reason = exclusion_reason(
            listing,
            target_condition,
            device_type=specs.get("device_type"),
            target_specs=specs,
        )
        diagnostics.append(
            {
                "source": source,
                "title": listing.get("title"),
                "url": listing.get("url"),
                "query_text": listing.get("query_text"),
                "generated_query_text": listing.get("generated_query_text"),
                "query_tier": listing.get("query_tier"),
                "price_cad": listing.get("total_price_cad"),
                "available": listing.get("available"),
                "condition_raw": listing.get("condition_raw"),
                "condition_norm": listing.get("condition_norm"),
                "source_match_verified": listing.get("source_match_verified") is True,
                "source_match_reasons": list(listing.get("source_match_reasons") or []),
                "filter_exclusion_reason": filter_reason,
                "included_in_pricing": listing.get("_included_in_pricing") is True,
                "source_specs": listing.get("source_specs") if isinstance(listing.get("source_specs"), dict) else {},
            }
        )
    return diagnostics


def _pricing_listings(listings: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    hard_filtered = []
    excluded_reasons: dict[str, int] = {}
    for listing in listings:
        hard_reason = _source_match_hard_exclusion_reason(listing)
        if hard_reason:
            excluded_reasons[hard_reason] = excluded_reasons.get(hard_reason, 0) + 1
            continue
        hard_filtered.append(listing)

    verified_or_nonretail = []
    for listing in hard_filtered:
        if _source_key(listing) in {"refurb_io", "amazon_renewed"} and listing.get("source_match_verified") is not True:
            excluded_reasons["unverified_retailer_listing"] = excluded_reasons.get("unverified_retailer_listing", 0) + 1
            continue
        verified_or_nonretail.append(listing)

    hard_filtered = verified_or_nonretail
    verified_retail = [listing for listing in hard_filtered if _is_verified_retail_listing(listing)]
    if not verified_retail:
        return hard_filtered, excluded_reasons

    unverified_count = len(hard_filtered) - len(verified_retail)
    if unverified_count:
        excluded_reasons["displaced_by_retailer"] = excluded_reasons.get("displaced_by_retailer", 0) + unverified_count
    return verified_retail, excluded_reasons


def _mark_included_in_pricing(all_listings: list[dict[str, Any]], pricing_listings: list[dict[str, Any]]) -> None:
    included_keys = {_listing_identity(listing) for listing in pricing_listings}
    included_keys.discard("")
    for listing in all_listings:
        listing["_included_in_pricing"] = _listing_identity(listing) in included_keys


def _listing_identity(listing: dict[str, Any]) -> str:
    keys = _listing_keys(listing)
    if not keys:
        return ""
    key_type, key_value = keys[0]
    return f"{key_type}:{key_value}"


def _source_match_hard_exclusion_reason(listing: dict[str, Any]) -> str | None:
    source = _source_key(listing)
    if source not in {"refurb_io", "amazon_renewed"}:
        return None
    reasons = set(str(reason) for reason in (listing.get("source_match_reasons") or []))
    if "ram_mismatch" in reasons:
        return "ram_mismatch"
    if "storage_mismatch" in reasons:
        return "storage_mismatch"
    return None


def _is_verified_retail_listing(listing: dict[str, Any]) -> bool:
    return _source_key(listing) in {"refurb_io", "amazon_renewed"} and listing.get("source_match_verified") is True


def _merge_reason_counts(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    merged = dict(left)
    for reason, count in right.items():
        merged[reason] = merged.get(reason, 0) + count
    return merged


def _apply_source_quote_basis(
    result: dict[str, Any],
    filtered_listings: list[dict[str, Any]],
    warn_below_comparables: int,
    wide_iqr_ratio: float,
    support_limit: int,
    asking_discount_low: float,
    asking_discount_high: float,
) -> dict[str, Any]:
    updated = dict(result)
    metadata = _result_metadata(result)
    source_quotes = _source_quotes(filtered_listings, asking_discount_low, asking_discount_high)
    updated["source_quotes"] = source_quotes

    weighted_quotes = [
        quote
        for quote in source_quotes
        if _safe_float(quote.get("price_cad")) is not None
        and (_safe_float(quote.get("weight")) or 0) > 0
    ]
    verified_retail_quotes = [
        quote
        for quote in weighted_quotes
        if quote.get("source") in {"refurb_io", "amazon_renewed"} and quote.get("verified") is True
    ]
    if not verified_retail_quotes:
        ebay_listings = [listing for listing in filtered_listings if _source_key(listing) == "ebay"]
        if ebay_listings and len(ebay_listings) != len(filtered_listings):
            updated = aggregate_listings(
                ebay_listings,
                warn_below_comparables=warn_below_comparables,
                wide_iqr_ratio=wide_iqr_ratio,
                support_limit=support_limit,
            )
            updated = apply_pricing_basis(
                updated,
                asking_discount_low=asking_discount_low,
                asking_discount_high=asking_discount_high,
            )
            updated.update(metadata)
            updated["source_quotes"] = source_quotes
        elif filtered_listings and not ebay_listings:
            updated = aggregate_listings(
                [],
                warn_below_comparables=warn_below_comparables,
                wide_iqr_ratio=wide_iqr_ratio,
                support_limit=support_limit,
            )
            updated.update(metadata)
            updated["source_quotes"] = source_quotes
        updated["source_basis"] = _fallback_source_basis(updated)
        return updated

    quote_prices = sorted(float(quote["price_cad"]) for quote in weighted_quotes)
    weighted_price = _weighted_average(weighted_quotes)
    if weighted_price is not None:
        updated["median_price_cad"] = _round_money(weighted_price)
        updated["iqr_low_cad"] = _round_money(min(quote_prices))
        updated["iqr_high_cad"] = _round_money(max(quote_prices))
        updated["pricing_basis"] = "weighted_sources"
        updated["source_basis"] = "weighted_source_quotes"
        updated.pop("asking_median_price_cad", None)
        updated.pop("asking_only_discount_low", None)
        updated.pop("asking_only_discount_high", None)
        updated.pop("conservative_low_cad", None)
        updated.pop("conservative_high_cad", None)

    ebay_quote = next((quote for quote in source_quotes if quote.get("source") == "ebay"), None)
    if ebay_quote and _source_prices_disagree(ebay_quote.get("price_cad"), updated["median_price_cad"]):
        updated["confidence_flags"] = _append_flag(updated.get("confidence_flags"), "source_disagreement")
    return updated


def _result_metadata(result: dict[str, Any]) -> dict[str, Any]:
    aggregate_keys = {
        "median_price_cad",
        "iqr_low_cad",
        "iqr_high_cad",
        "count",
        "sold_count",
        "asking_count",
        "source_counts",
        "query_tier",
        "confidence_flags",
        "supporting_listings",
        "pricing_basis",
        "asking_median_price_cad",
        "asking_only_discount_low",
        "asking_only_discount_high",
        "conservative_low_cad",
        "conservative_high_cad",
    }
    return {key: value for key, value in result.items() if key not in aggregate_keys}


def _source_quotes(
    filtered_listings: list[dict[str, Any]],
    asking_discount_low: float,
    asking_discount_high: float,
) -> list[dict[str, Any]]:
    quotes: list[dict[str, Any]] = []
    ebay_listings = [listing for listing in filtered_listings if _source_key(listing) == "ebay"]
    if ebay_listings:
        ebay_result = aggregate_listings(ebay_listings, warn_below_comparables=1)
        ebay_result = apply_pricing_basis(
            ebay_result,
            asking_discount_low=asking_discount_low,
            asking_discount_high=asking_discount_high,
        )
        if ebay_result.get("median_price_cad") is not None:
            quotes.append(
                {
                    "source": "ebay",
                    "price_cad": ebay_result.get("median_price_cad"),
                    "basis": ebay_result.get("pricing_basis"),
                    "listing_count": ebay_result.get("count"),
                    "weight": 1,
                    "verified": False,
                }
            )

    for source_name in ["refurb_io", "amazon_renewed"]:
        source_listings = [
            listing
            for listing in filtered_listings
            if _source_key(listing) == source_name and listing.get("source_match_verified") is True
        ]
        prices = sorted(
            price
            for price in (_safe_float(listing.get("total_price_cad")) for listing in source_listings)
            if price is not None
        )
        if not prices:
            continue
        price = _percentile(prices, 0.50)
        quotes.append(
            {
                "source": source_name,
                "price_cad": _round_money(price),
                "basis": "verified_listing_median",
                "listing_count": len(prices),
                "weight": 2,
                "verified": True,
            }
        )
    return quotes


def _fallback_source_basis(result: dict[str, Any]) -> str:
    basis = result.get("pricing_basis")
    if basis:
        return f"ebay_{basis}"
    return "ebay_fallback"


def _source_prices_disagree(left: Any, right: Any) -> bool:
    left_price = _safe_float(left)
    right_price = _safe_float(right)
    if left_price is None or right_price is None or right_price <= 0:
        return False
    return abs(left_price - right_price) / right_price > 0.30


def _weighted_average(quotes: list[dict[str, Any]]) -> float | None:
    total_weight = 0.0
    total = 0.0
    for quote in quotes:
        price = _safe_float(quote.get("price_cad"))
        weight = _safe_float(quote.get("weight"))
        if price is None or weight is None or weight <= 0:
            continue
        total += price * weight
        total_weight += weight
    if total_weight <= 0:
        return None
    return total / total_weight


def _add_source_match_flags(
    listings: list[dict[str, Any]],
    specs: dict[str, Any],
) -> list[dict[str, Any]]:
    return [_add_source_match_flag(listing, specs) for listing in listings]


def _add_source_match_flag(listing: dict[str, Any], specs: dict[str, Any]) -> dict[str, Any]:
    if _source_key(listing) not in {"refurb_io", "amazon_renewed"}:
        return listing

    updated = dict(listing)
    verified, reasons = _verified_refurb_match(updated, specs)
    updated["source_match_verified"] = verified
    updated["source_match_reasons"] = reasons
    return updated


def _verified_refurb_match(
    listing: dict[str, Any],
    specs: dict[str, Any],
) -> tuple[bool, list[str]]:
    reasons = []
    text = _listing_match_text(listing)

    if not _text_matches_value(text, specs.get("brand")):
        reasons.append("brand_mismatch")

    model = specs.get("search_model") or specs.get("model")
    if model and not _all_tokens_present(text, str(model)):
        reasons.append("model_mismatch")

    device_type = specs.get("device_type")
    if device_type and not _device_type_matches(text, device_type):
        reasons.append("device_type_mismatch")

    ram_gb = _safe_int(specs.get("ram_gb"))
    if ram_gb and not _capacity_matches(text, ram_gb):
        reasons.append("ram_mismatch")

    storage_gb = _target_storage_gb(specs)
    if storage_gb and not _capacity_matches(text, storage_gb):
        reasons.append("storage_mismatch")

    cpu_short = specs.get("cpu_short")
    if cpu_short and not _cpu_matches(text, str(cpu_short)):
        reasons.append("cpu_mismatch")

    return not reasons, reasons


def _listing_match_text(listing: dict[str, Any]) -> str:
    parts = [listing.get("title")]
    source_specs = listing.get("source_specs")
    if isinstance(source_specs, dict):
        parts.extend(source_specs.values())
    return _normalize_match_text(" ".join(str(part) for part in parts if part))


def _text_matches_value(text: str, value: Any) -> bool:
    if not value:
        return True
    return _all_tokens_present(text, str(value))


def _all_tokens_present(text: str, value: str) -> bool:
    tokens = re.findall(r"[a-z0-9]+", value.lower())
    tokens = [token for token in tokens if token not in {"intel", "core", "gb", "ssd"}]
    return all(token in text for token in tokens)


def _form_factor_matches(text: str, value: Any) -> bool:
    form_factor = str(value or "").lower()
    if form_factor == "laptop":
        return "laptop" in text or "notebook" in text
    if form_factor == "desktop":
        return "desktop" in text or "tower" in text or "optiplex" in text
    if form_factor == "all-in-one":
        return "all in one" in text or "aio" in text
    return True


def _device_type_matches(text: str, value: Any) -> bool:
    device_type = str(value or "").lower()
    if device_type == "computer":
        return True
    return device_type in text


def _capacity_matches(text: str, capacity_gb: int) -> bool:
    terms = {f"{capacity_gb}gb", f"{capacity_gb} gb"}
    if capacity_gb >= 1024 and capacity_gb % 1024 == 0:
        tb = capacity_gb // 1024
        terms.update({f"{tb}tb", f"{tb} tb"})
    return any(term in text for term in terms)


def _cpu_matches(text: str, cpu_short: str) -> bool:
    wanted = _cpu_match_keys(cpu_short)
    if not wanted:
        return True
    available = text.replace(" ", "")
    return any(key in available for key in wanted)


def _cpu_match_keys(cpu_short: str) -> set[str]:
    normalized = _normalize_match_text(cpu_short).replace(" ", "")
    keys = {normalized} if normalized else set()
    if normalized and normalized[-1:].isalpha() and any(character.isdigit() for character in normalized):
        keys.add(normalized[:-1])
    return keys


def _target_storage_gb(specs: dict[str, Any]) -> int:
    storage = specs.get("storage") or []
    if isinstance(storage, list):
        sizes = [
            _safe_int(drive.get("size_gb"))
            for drive in storage
            if isinstance(drive, dict) and _safe_int(drive.get("size_gb")) > 0
        ]
        if sizes:
            return max(sizes)
    for key in ["storage_capacity", "capacity"]:
        parsed = _capacity_text_gb(specs.get(key))
        if parsed:
            return parsed
    return 0


def _capacity_text_gb(value: Any) -> int:
    text = str(value or "").strip().lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*(tb|gb)", text)
    if not match:
        return 0
    amount = float(match.group(1))
    return int(amount * 1024) if match.group(2) == "tb" else int(amount)


def _normalize_match_text(value: str) -> str:
    lowered = value.lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return f" {re.sub(r'\s+', ' ', lowered).strip()} "


def _source_key(listing: dict[str, Any]) -> str:
    return str(listing.get("source") or "").strip().lower()


def _percentile(values: list[float], percentile: float) -> float:
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * percentile
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(values) - 1)
    fraction = position - lower_index
    return values[lower_index] + (values[upper_index] - values[lower_index]) * fraction


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


def _append_flag(flags: Any, flag: str) -> list[str]:
    clean_flags = list(flags or [])
    if flag not in clean_flags:
        clean_flags.append(flag)
    return clean_flags
