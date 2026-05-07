"""Run the pricing pipeline from specs through comparable aggregation."""

from __future__ import annotations

from typing import Any, Protocol

from pc_pricer.aggregator import aggregate_listings
from pc_pricer.listing_filter import filter_listings
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
    source: ListingSource,
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
    raw_listings = _search_queries(source, queries, limit_per_query)
    deduped_listings = _dedupe_listings(raw_listings)
    normalized_listings = normalize_listings(deduped_listings)
    filtered = filter_listings(normalized_listings, target_condition=target_condition)

    result = aggregate_listings(
        filtered["listings"],
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
        }
    )
    result = add_listing_quality_flags(
        result,
        filtered["listings"],
        high_shipping_cad=high_shipping_cad,
        high_shipping_ratio=high_shipping_ratio,
    )

    if not queries:
        result["confidence_flags"] = _append_flag(result.get("confidence_flags"), "no_queries")

    return result


def _search_queries(
    source: ListingSource,
    queries: list[dict[str, Any]],
    limit_per_query: int,
) -> list[dict[str, Any]]:
    listings = []
    for query in queries:
        query_text = str(query.get("text") or "").strip()
        if not query_text:
            continue

        for listing in source.search(query_text, limit_per_query):
            tagged = dict(listing)
            tagged["query_tier"] = query.get("tier")
            tagged["query_reason"] = query.get("reason")
            tagged["query_text"] = query_text
            listings.append(tagged)

    return listings


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


def _append_flag(flags: Any, flag: str) -> list[str]:
    clean_flags = list(flags or [])
    if flag not in clean_flags:
        clean_flags.append(flag)
    return clean_flags
