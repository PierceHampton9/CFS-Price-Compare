"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from pc_pricer.aggregator import aggregate_listings
from pc_pricer.detector import detect_specs
from pc_pricer.env_loader import load_env_file
from pc_pricer.listing_filter import filter_listings
from pc_pricer.normalizer import normalize_listings
from pc_pricer.pricing_pipeline import price_specs
from pc_pricer.reporter import format_condition, format_listing_price, format_price_report
from pc_pricer.sources.ebay import EbaySource


def main() -> None:
    load_env_file()

    parser = argparse.ArgumentParser(prog="pc_pricer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    detect_parser = subparsers.add_parser("detect", help="Detect specs on this Windows PC.")
    detect_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    detect_parser.add_argument("--raw", action="store_true", help="Include raw Windows CIM output.")

    ebay_parser = subparsers.add_parser(
        "ebay-search",
        help="Search active eBay listings for manual smoke testing.",
    )
    ebay_parser.add_argument("query", nargs="+", help="Search terms to send to eBay.")
    ebay_parser.add_argument("--limit", type=int, default=5, help="Maximum listings to return.")
    ebay_parser.add_argument("--marketplace", default="EBAY_CA", help="eBay marketplace ID.")
    ebay_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    ebay_check_parser = subparsers.add_parser(
        "ebay-check",
        help="Validate eBay credentials without searching listings.",
    )
    ebay_check_parser.add_argument("--marketplace", default="EBAY_CA", help="eBay marketplace ID.")

    price_query_parser = subparsers.add_parser(
        "price-query",
        help="Search active eBay listings and print a draft price report.",
    )
    price_query_parser.add_argument("query", nargs="+", help="Search terms to price.")
    price_query_parser.add_argument("--limit", type=int, default=10, help="Maximum listings to fetch.")
    price_query_parser.add_argument("--marketplace", default="EBAY_CA", help="eBay marketplace ID.")
    price_query_parser.add_argument(
        "--condition",
        choices=["good", "excellent", "mint", "any"],
        default="good",
        help="Target listing condition for pricing.",
    )
    price_query_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    price_detect_parser = subparsers.add_parser(
        "price-detect",
        help="Detect this Windows PC, search tiered eBay queries, and print a draft price report.",
    )
    price_detect_parser.add_argument(
        "--limit-per-query",
        type=int,
        default=10,
        help="Maximum listings to fetch for each generated query.",
    )
    price_detect_parser.add_argument("--marketplace", default="EBAY_CA", help="eBay marketplace ID.")
    price_detect_parser.add_argument(
        "--condition",
        choices=["good", "excellent", "mint", "any"],
        default="good",
        help="Target listing condition for pricing.",
    )
    price_detect_parser.add_argument("--raw", action="store_true", help="Include raw detected specs in JSON output.")
    price_detect_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    args = parser.parse_args()

    if args.command == "detect":
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
            listings = EbaySource(marketplace=args.marketplace).search(query, args.limit)
            listings = normalize_listings(listings)
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

        if args.json:
            print(json.dumps(listings, indent=2, default=str))
        else:
            print_ebay_listings(query, listings)
    elif args.command == "ebay-check":
        source = EbaySource(marketplace=args.marketplace)
        try:
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
            listings = EbaySource(marketplace=args.marketplace).search(query, args.limit)
            listings = normalize_listings(listings)
            filtered = filter_listings(listings, target_condition=args.condition)
            result = aggregate_listings(filtered["listings"])
            result.update(
                {
                    "target_condition": filtered["target_condition"],
                    "excluded_count": filtered["excluded_count"],
                    "excluded_reasons": filtered["excluded_reasons"],
                }
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
            specs = detect_specs(include_raw=args.raw)
            source = EbaySource(marketplace=args.marketplace)
            result = price_specs(
                specs,
                source,
                limit_per_query=args.limit_per_query,
                target_condition=args.condition,
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


if __name__ == "__main__":
    main()
