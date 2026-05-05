"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from pc_pricer.detector import detect_specs
from pc_pricer.sources.ebay import EbaySource


def main() -> None:
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
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

        if args.json:
            print(json.dumps(listings, indent=2, default=str))
        else:
            print_ebay_listings(query, listings)


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
        print(f"   Price:     {_format_listing_price(listing)}")
        print(f"   Condition: {listing.get('condition_raw') or 'Unknown'}")
        print(f"   Location:  {listing.get('location') or 'Unknown'}")
        print(f"   URL:       {listing.get('url') or 'Unknown'}")


def _format_ram(specs: dict[str, Any]) -> str:
    ram_gb = specs.get("ram_gb")
    if not ram_gb:
        return "Unknown"
    return f"{ram_gb} GB"


def _format_listing_price(listing: dict) -> str:
    item_price = _format_money(listing.get("item_price_cad"))
    shipping = _format_money(listing.get("shipping_cad"))
    total = _format_money(listing.get("total_price_cad"))

    if listing.get("shipping_is_estimated"):
        return f"{total} total ({item_price} item + unknown shipping)"
    return f"{total} total ({item_price} item + {shipping} shipping)"


def _format_money(value: Any) -> str:
    try:
        return f"${float(value):,.2f} CAD"
    except (TypeError, ValueError):
        return "Unknown"


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
