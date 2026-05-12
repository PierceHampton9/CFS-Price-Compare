"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from pc_pricer.aggregator import aggregate_listings
from pc_pricer.config import load_config
from pc_pricer.detector import detect_specs
from pc_pricer.env_loader import load_env_file
from pc_pricer.listing_filter import filter_listings
from pc_pricer.normalizer import normalize_listings
from pc_pricer.price_adjustment import apply_pricing_basis
from pc_pricer.pricing_pipeline import price_specs
from pc_pricer.quality import add_listing_quality_flags
from pc_pricer.reporter import format_condition, format_listing_price, format_price_report
from pc_pricer.setup_credentials import run_setup
from pc_pricer.spec_builder import (
    VALID_CONDITIONS,
    VALID_DEVICE_TYPES,
    build_manual_specs,
    manual_device_type,
)
from pc_pricer.sources.factory import build_listing_sources
from pc_pricer.sources.ebay import EbaySource


def main() -> None:
    load_env_file()

    parser = argparse.ArgumentParser(prog="pc_pricer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup_parser = subparsers.add_parser(
        "setup",
        help="Prompt for eBay credentials and save them to a local .env file.",
    )
    setup_parser.add_argument("--env-file", help="Override where the .env file is written.")

    detect_parser = subparsers.add_parser("detect", help="Detect specs on this Windows PC.")
    detect_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    detect_parser.add_argument("--raw", action="store_true", help="Include raw Windows CIM output.")

    ebay_parser = subparsers.add_parser(
        "ebay-search",
        help="Search active eBay listings for manual smoke testing.",
    )
    ebay_parser.add_argument("query", nargs="+", help="Search terms to send to eBay.")
    ebay_parser.add_argument("--limit", type=int, default=None, help="Maximum listings to return.")
    ebay_parser.add_argument("--marketplace", default=None, help="eBay marketplace ID.")
    ebay_parser.add_argument("--config", default=None, help="Path to config file.")
    ebay_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    ebay_check_parser = subparsers.add_parser(
        "ebay-check",
        help="Validate eBay credentials without searching listings.",
    )
    ebay_check_parser.add_argument("--marketplace", default=None, help="eBay marketplace ID.")
    ebay_check_parser.add_argument("--config", default=None, help="Path to config file.")

    price_query_parser = subparsers.add_parser(
        "price-query",
        help="Search active eBay listings and print a draft price report.",
    )
    price_query_parser.add_argument("query", nargs="+", help="Search terms to price.")
    price_query_parser.add_argument("--limit", type=int, default=None, help="Maximum listings to fetch.")
    price_query_parser.add_argument("--marketplace", default=None, help="eBay marketplace ID.")
    price_query_parser.add_argument(
        "--condition",
        choices=["good", "excellent", "mint", "any"],
        default=None,
        help="Target listing condition for pricing.",
    )
    price_query_parser.add_argument(
        "--device-type",
        choices=sorted(VALID_DEVICE_TYPES),
        default="computer",
        help="Device type for parts/accessory filtering. Defaults to computer.",
    )
    price_query_parser.add_argument("--config", default=None, help="Path to config file.")
    price_query_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    price_manual_parser = subparsers.add_parser(
        "price-manual",
        help="Enter specs manually, search tiered eBay queries, and print a draft price report.",
    )
    price_manual_parser.add_argument(
        "--device-type",
        choices=sorted(VALID_DEVICE_TYPES),
        default="computer",
        help="Type of device to price. Defaults to computer.",
    )
    price_manual_parser.add_argument("--brand", help="Device brand, such as Lenovo, Apple, Dell, or Brother.")
    price_manual_parser.add_argument("--model", help="Device model or model family.")
    price_manual_parser.add_argument("--variant", help="Device variant, such as mini, Pro, Pro Max, Plus, FE, or Air.")
    price_manual_parser.add_argument("--screen-size", help='Screen size for phones, tablets, or laptops, such as 6.1, 11, 12.9, or 14".')
    price_manual_parser.add_argument("--oem-sku", help="Exact computer OEM model identifier when available.")
    price_manual_parser.add_argument(
        "--form-factor",
        choices=["laptop", "desktop", "all-in-one"],
        help="Computer form factor. Required for device-type computer.",
    )
    price_manual_parser.add_argument("--cpu", help="CPU model, preferably the short form such as i5-1135G7.")
    price_manual_parser.add_argument("--ram", type=int, help="RAM in GB.")
    price_manual_parser.add_argument("--storage", type=int, help="Computer/phone/tablet storage size in GB.")
    price_manual_parser.add_argument("--storage-type", default="SSD", help="Computer primary storage type, such as SSD or HDD.")
    price_manual_parser.add_argument("--gpu", help="Dedicated GPU model when present.")
    price_manual_parser.add_argument("--carrier", help="Phone carrier or unlocked status.")
    price_manual_parser.add_argument("--connectivity", help="Tablet connectivity, such as Wi-Fi or cellular.")
    price_manual_parser.add_argument("--size", help='Monitor size, such as 24 or 27".')
    price_manual_parser.add_argument("--resolution", help="Monitor resolution, such as 1080p, 1440p, or 4K.")
    price_manual_parser.add_argument("--refresh-rate", help="Monitor refresh rate, such as 60 or 144Hz.")
    price_manual_parser.add_argument("--printer-type", help="Printer type, such as laser, inkjet, or label.")
    price_manual_parser.add_argument("--color", help="Printer color support, such as color or mono.")
    price_manual_parser.add_argument("--capacity", help="Storage-device capacity, such as 512GB, 1TB, or 4TB.")
    price_manual_parser.add_argument("--drive-type", choices=["hdd", "ssd"], help="Storage-device drive type.")
    price_manual_parser.add_argument(
        "--drive-form-factor",
        help="Storage-device form factor. Accepts 1.8, 2.5, 3.5, m.2, msata, and common aliases.",
    )
    price_manual_parser.add_argument("--interface", help="Storage-device interface, such as SATA, NVMe, USB, or SAS.")
    price_manual_parser.add_argument(
        "--limit-per-query",
        type=int,
        default=None,
        help="Maximum listings to fetch for each generated query.",
    )
    price_manual_parser.add_argument("--marketplace", default=None, help="eBay marketplace ID.")
    price_manual_parser.add_argument(
        "--condition",
        choices=["good", "excellent", "mint", "any"],
        default=None,
        help="Target listing condition for pricing.",
    )
    price_manual_parser.add_argument("--config", default=None, help="Path to config file.")
    price_manual_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    price_detect_parser = subparsers.add_parser(
        "price-detect",
        help="Detect this Windows PC, search tiered eBay queries, and print a draft price report.",
    )
    price_detect_parser.add_argument(
        "--limit-per-query",
        type=int,
        default=None,
        help="Maximum listings to fetch for each generated query.",
    )
    price_detect_parser.add_argument("--marketplace", default=None, help="eBay marketplace ID.")
    price_detect_parser.add_argument(
        "--condition",
        choices=["good", "excellent", "mint", "any"],
        default=None,
        help="Target listing condition for pricing.",
    )
    price_detect_parser.add_argument("--config", default=None, help="Path to config file.")
    price_detect_parser.add_argument("--raw", action="store_true", help="Include raw detected specs in JSON output.")
    price_detect_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    args = parser.parse_args()

    if args.command == "setup":
        try:
            env_path = run_setup(args.env_file)
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

        print(f"Saved eBay credentials to: {env_path}")
        print("Next run: pc_pricer ebay-check")
    elif args.command == "detect":
        try:
            specs = detect_specs(include_raw=args.raw)
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

        if args.json:
            print(json.dumps(specs, indent=2))
        else:
            print_detected_specs(specs)
    elif args.command == "ebay-search":
        query = " ".join(args.query)
        try:
            config = load_config(args.config)
            source = _ebay_source(config, args.marketplace)
            listings = source.search(query, _limit(args.limit, config))
            listings = normalize_listings(listings)
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

        if args.json:
            print(json.dumps(listings, indent=2, default=str))
        else:
            print_ebay_listings(query, listings)
    elif args.command == "ebay-check":
        try:
            config = load_config(args.config)
            source = _ebay_source(config, args.marketplace)
            check_result = source.check_credentials()
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

        print("eBay credential configuration found.")
        print(check_result["message"])
        print(f"Marketplace: {source.marketplace}")
    elif args.command == "price-query":
        query = " ".join(args.query)
        try:
            config = load_config(args.config)
            source = _ebay_source(config, args.marketplace)
            listings = source.search(query, _limit(args.limit, config))
            listings = normalize_listings(listings)
            filtered = filter_listings(
                listings,
                target_condition=_condition(args.condition, config),
                device_type=_manual_device_type(args.device_type),
            )
            result = aggregate_listings(filtered["listings"], **_aggregation_options(config))
            result = apply_pricing_basis(result, **_asking_adjustment_options(config))
            result.update(
                {
                    "queries": [{"text": query, "tier": None, "reason": "manual query"}],
                    "raw_listing_count": len(listings),
                    "deduped_listing_count": len(listings),
                    "target_condition": filtered["target_condition"],
                    "excluded_count": filtered["excluded_count"],
                    "excluded_reasons": filtered["excluded_reasons"],
                }
            )
            result = add_listing_quality_flags(result, filtered["listings"], **_quality_options(config))
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(format_price_report(result))
    elif args.command == "price-manual":
        try:
            config = load_config(args.config)
            specs = _manual_specs(args)
            source = _pricing_sources(config, args.marketplace)
            result = price_specs(
                specs,
                source,
                limit_per_query=_limit_per_query(args.limit_per_query, config),
                target_condition=_condition(args.condition, config),
                **_pricing_options(config),
            )
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(format_price_report(result))
    elif args.command == "price-detect":
        try:
            config = load_config(args.config)
            specs = detect_specs(include_raw=args.raw)
            source = _pricing_sources(config, args.marketplace)
            result = price_specs(
                specs,
                source,
                limit_per_query=_limit_per_query(args.limit_per_query, config),
                target_condition=_condition(args.condition, config),
                **_pricing_options(config),
            )
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

        if args.json:
            if args.raw:
                result["specs"] = specs
            print(json.dumps(result, indent=2, default=str))
        else:
            print(format_price_report(result))


def print_detected_specs(specs: dict[str, Any]) -> None:
    print("Detected PC specs")
    print("-----------------")
    print(f"Brand:       {specs.get('brand') or 'Unknown'}")
    print(f"Model:       {specs.get('model') or 'Unknown'}")
    print(f"OEM SKU:     {specs.get('oem_sku') or 'Unknown'}")
    print(f"Form factor: {specs.get('form_factor') or 'Unknown'}")
    print(f"CPU:         {specs.get('cpu') or 'Unknown'}")
    print(f"RAM:         {_format_ram(specs)}")
    print(f"Storage:     {_format_storage(specs.get('storage'))}")
    print(f"GPU:         {specs.get('gpu') or 'Unknown'}")

    warnings = specs.get("warnings") or []
    if warnings:
        print()
        print("Warnings")
        print("--------")
        for warning in warnings:
            print(f"- {warning}")


def print_ebay_listings(query: str, listings: list[dict]) -> None:
    print(f"eBay active listings for: {query}")
    print("-------------------------")

    if not listings:
        print("No listings found.")
        return

    for index, listing in enumerate(listings, start=1):
        print(f"{index}. {listing.get('title') or 'Untitled listing'}")
        print(f"   Price:     {format_listing_price(listing)}")
        print(f"   Condition: {format_condition(listing)}")
        print(f"   Location:  {listing.get('location') or 'Unknown'}")
        print(f"   URL:       {listing.get('url') or 'Unknown'}")


def _format_ram(specs: dict[str, Any]) -> str:
    ram_gb = specs.get("ram_gb")
    if not ram_gb:
        return "Unknown"
    return f"{ram_gb} GB"


def _format_storage(storage: Any) -> str:
    if not storage:
        return "Unknown"

    parts = []
    for disk in storage:
        size = disk.get("size_gb")
        drive_type = disk.get("type") or "unknown type"
        model = disk.get("model")
        label = f"{size} GB {drive_type}" if size else drive_type
        if model:
            label = f"{label} ({model})"
        parts.append(label)
    return "; ".join(parts)


def _manual_specs(args: argparse.Namespace) -> dict[str, Any]:
    return build_manual_specs(args.device_type, vars(args))


def _manual_device_type(value: Any) -> str:
    return manual_device_type(value)


def _ebay_source(config: dict[str, Any], marketplace_override: str | None = None) -> EbaySource:
    ebay_config = _source_config(config, "ebay")
    enabled = _bool_value(ebay_config.get("enabled"), True)
    marketplace = marketplace_override or str(ebay_config.get("marketplace") or "EBAY_CA")
    source = EbaySource(marketplace=marketplace)
    source.enabled = enabled
    return source


def _pricing_sources(config: dict[str, Any], marketplace_override: str | None = None) -> list[Any]:
    return build_listing_sources(
        config,
        marketplace_override=marketplace_override,
    )


def _source_config(config: dict[str, Any], source_name: str) -> dict[str, Any]:
    sources = config.get("sources")
    if not isinstance(sources, dict):
        return {}
    source = sources.get(source_name)
    if not isinstance(source, dict):
        return {}
    return source


def _limit(cli_value: int | None, config: dict[str, Any]) -> int:
    return _positive_int(cli_value, _positive_int(config.get("default_limit"), 10))


def _limit_per_query(cli_value: int | None, config: dict[str, Any]) -> int:
    return _positive_int(cli_value, _positive_int(config.get("default_limit_per_query"), 10))


def _condition(cli_value: str | None, config: dict[str, Any]) -> str:
    value = cli_value or config.get("default_condition") or "good"
    condition = str(value).strip().lower() or "good"
    if condition not in VALID_CONDITIONS:
        raise RuntimeError(
            f"Invalid default_condition {condition!r}. Use good, excellent, mint, or any."
        )
    return condition


def _aggregation_options(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "warn_below_comparables": _positive_int(config.get("warn_below_comparables"), 10),
        "wide_iqr_ratio": _positive_float(config.get("wide_iqr_ratio"), 0.40),
        "support_limit": _positive_int(config.get("support_limit"), 5),
    }


def _quality_options(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "high_shipping_cad": _positive_float(config.get("high_shipping_cad"), 75.0),
        "high_shipping_ratio": _positive_float(config.get("high_shipping_ratio"), 0.25),
    }


def _pricing_options(config: dict[str, Any]) -> dict[str, Any]:
    return {
        **_aggregation_options(config),
        **_quality_options(config),
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


def _positive_int_or_none(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


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


if __name__ == "__main__":
    main()
