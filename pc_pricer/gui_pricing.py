"""Pricing helpers used by the GUI."""

from __future__ import annotations

from typing import Any

from pc_pricer.config import load_config
from pc_pricer.env_loader import load_env_file
from pc_pricer.pricing_pipeline import ListingSource, price_specs
from pc_pricer.reporter import format_price_report
from pc_pricer.sources.ebay import EbaySource
from pc_pricer.spec_builder import VALID_CONDITIONS, build_manual_specs


def price_gui_values(
    device_type: str,
    values: dict[str, Any],
    source: ListingSource | None = None,
    config_path: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Price GUI form values and return both raw result and formatted report."""
    load_env_file(override=True)
    config = load_config(config_path)
    specs = build_manual_specs(device_type, values)
    result = price_specs(
        specs,
        source or _ebay_source(config),
        limit_per_query=_limit_per_query(config),
        target_condition=_condition(values.get("condition"), config),
        **_pricing_options(config),
    )
    return result, format_price_report(result)


def _ebay_source(config: dict[str, Any]) -> EbaySource:
    ebay_config = _source_config(config, "ebay")
    enabled = _bool_value(ebay_config.get("enabled"), True)
    marketplace = str(ebay_config.get("marketplace") or "EBAY_CA")
    source = EbaySource(marketplace=marketplace)
    source.enabled = enabled
    return source


def _source_config(config: dict[str, Any], source_name: str) -> dict[str, Any]:
    sources = config.get("sources")
    if not isinstance(sources, dict):
        return {}
    source = sources.get(source_name)
    if not isinstance(source, dict):
        return {}
    return source


def _limit_per_query(config: dict[str, Any]) -> int:
    return _positive_int(config.get("default_limit_per_query"), 10)


def _condition(gui_value: Any, config: dict[str, Any]) -> str:
    value = gui_value or config.get("default_condition") or "good"
    condition = str(value).strip().lower() or "good"
    if condition not in VALID_CONDITIONS:
        raise RuntimeError(f"Invalid condition {condition!r}. Use good, excellent, mint, or any.")
    return condition


def _pricing_options(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "warn_below_comparables": _positive_int(config.get("warn_below_comparables"), 10),
        "wide_iqr_ratio": _positive_float(config.get("wide_iqr_ratio"), 0.40),
        "support_limit": _positive_int(config.get("support_limit"), 5),
        "high_shipping_cad": _positive_float(config.get("high_shipping_cad"), 75.0),
        "high_shipping_ratio": _positive_float(config.get("high_shipping_ratio"), 0.25),
        **_asking_adjustment_options(config),
    }


def _asking_adjustment_options(config: dict[str, Any]) -> dict[str, Any]:
    discount_low = _non_negative_float(config.get("asking_discount_low"), 0.00)
    discount_high = _non_negative_float(config.get("asking_discount_high"), 0.05)
    if discount_low > discount_high:
        discount_low, discount_high = discount_high, discount_low

    return {
        "asking_discount_low": discount_low,
        "asking_discount_high": discount_high,
    }


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _positive_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _non_negative_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _bool_value(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return default
