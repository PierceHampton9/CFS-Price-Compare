"""Add pricing-basis details to aggregated results."""

from __future__ import annotations

from typing import Any


def apply_pricing_basis(
    result: dict[str, Any],
    asking_discount_low: float = 0.05,
    asking_discount_high: float = 0.10,
) -> dict[str, Any]:
    """Return a copy of an aggregate result with asking-only adjustment fields."""
    updated = dict(result)
    sold_count = _safe_int(updated.get("sold_count"))
    asking_count = _safe_int(updated.get("asking_count"))

    if not updated.get("count"):
        return updated

    if sold_count == 0 and asking_count > 0:
        median = _safe_float(updated.get("median_price_cad"))
        updated["pricing_basis"] = "asking_adjusted"
        updated["asking_median_price_cad"] = updated.get("median_price_cad")
        updated["asking_only_discount_low"] = asking_discount_low
        updated["asking_only_discount_high"] = asking_discount_high
        if median is not None:
            updated["conservative_low_cad"] = round(median * (1 - asking_discount_high), 2)
            updated["conservative_high_cad"] = round(median * (1 - asking_discount_low), 2)
        return updated

    if sold_count > 0 and asking_count > 0:
        updated["pricing_basis"] = "mixed"
    elif sold_count > 0:
        updated["pricing_basis"] = "sold"
    else:
        updated["pricing_basis"] = "unknown"
    return updated


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
