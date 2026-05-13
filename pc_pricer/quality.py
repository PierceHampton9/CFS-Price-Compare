"""Add practical confidence flags to pricing results."""

from __future__ import annotations

from typing import Any


def add_listing_quality_flags(
    result: dict[str, Any],
    listings: list[dict[str, Any]],
    high_shipping_cad: float = 75.0,
    high_shipping_ratio: float = 0.25,
) -> dict[str, Any]:
    """Return a copy of a pricing result with listing-quality flags appended."""
    updated = dict(result)
    limitations = list(updated.get("pricing_limitations") or [])
    warnings = list(updated.get("listing_warnings") or [])

    if updated.get("pricing_basis") == "asking_adjusted":
        _append_flag(limitations, "asking_prices_only")

    if any(_has_unknown_shipping(listing) for listing in listings):
        _append_flag(warnings, "unknown_shipping")

    if any(_has_high_shipping(listing, high_shipping_cad, high_shipping_ratio) for listing in listings):
        _append_flag(warnings, "high_shipping")

    if any(_is_non_canadian_listing(listing) for listing in listings):
        _append_flag(warnings, "non_canadian_location")

    updated["pricing_limitations"] = limitations
    updated["listing_warnings"] = warnings
    return updated


def _has_unknown_shipping(listing: dict[str, Any]) -> bool:
    return listing.get("shipping_is_estimated") is True or listing.get("shipping_cad") is None


def _has_high_shipping(
    listing: dict[str, Any],
    high_shipping_cad: float,
    high_shipping_ratio: float,
) -> bool:
    shipping = _safe_float(listing.get("shipping_cad"))
    if shipping is None or shipping <= 0:
        return False

    if shipping >= high_shipping_cad:
        return True

    item_price = _safe_float(listing.get("item_price_cad"))
    return bool(item_price and item_price > 0 and shipping / item_price >= high_shipping_ratio)


def _is_non_canadian_listing(listing: dict[str, Any]) -> bool:
    location = str(listing.get("location") or "").strip().lower()
    if not location:
        return False

    parts = [part.strip(" .") for part in location.split(",") if part.strip()]
    country = parts[-1] if parts else location
    if country in {"ca", "canada"}:
        return False
    if country in {"us", "usa", "united states", "united states of america"}:
        return True

    non_canadian_markers = [
        "united states",
        "united kingdom",
        "china",
        "hong kong",
        "japan",
        "australia",
    ]
    return any(marker in location for marker in non_canadian_markers)


def _append_flag(flags: list[str], flag: str) -> None:
    if flag not in flags:
        flags.append(flag)


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
