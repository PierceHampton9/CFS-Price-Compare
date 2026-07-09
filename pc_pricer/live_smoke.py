"""Live source smoke checks for scheduled scraper/API validation."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib import error, request

from pc_pricer.config import load_config
from pc_pricer.env_loader import load_env_file
from pc_pricer.pricing_pipeline import price_specs
from pc_pricer.source_status import merge_config_source_statuses
from pc_pricer.sources.factory import build_listing_sources
from pc_pricer.sources.refurb_io import parse_product_html


SourceFactory = Callable[[dict[str, Any]], list[Any]]
HtmlFetcher = Callable[[str], str]


DEFAULT_PRICE_CASES = [
    {
        "name": "detected_lenovo_20w9_x13_yoga_gen2",
        "min_comparables": 1,
        "price_floor_cad": 150,
        "price_ceiling_cad": 1000,
        "require_identification": True,
        "required_query_terms": ["ThinkPad X13 Yoga Gen 2"],
        "specs": {
            "device_type": "computer",
            "brand": "LENOVO",
            "model": "20W9S23S00",
            "model_is_machine_type": True,
            "form_factor": "laptop",
            "cpu_short": "i7-1185G7",
            "ram_gb": 16,
            "storage": [{"size_gb": 238, "type": "SSD"}],
        },
    },
    {
        "name": "lenovo_x13_yoga_gen2",
        "min_comparables": 1,
        "price_floor_cad": 150,
        "price_ceiling_cad": 900,
        "specs": {
            "device_type": "computer",
            "brand": "Lenovo",
            "model": "ThinkPad X13 Yoga Gen 2",
            "form_factor": "laptop",
            "cpu_short": "i5-1135G7",
            "ram_gb": 16,
            "storage": [{"size_gb": 512, "type": "SSD"}],
        },
    },
    {
        "name": "iphone_13_128gb",
        "min_comparables": 1,
        "price_floor_cad": 150,
        "price_ceiling_cad": 900,
        "specs": {
            "device_type": "phone",
            "brand": "Apple",
            "model": "iPhone 13",
            "storage_capacity": "128GB",
            "carrier": "unlocked",
        },
    },
    {
        "name": "dell_u2419h",
        "min_comparables": 1,
        "price_floor_cad": 40,
        "price_ceiling_cad": 600,
        "specs": {
            "device_type": "monitor",
            "brand": "Dell",
            "model": "U2419H",
            "size": '24"',
            "resolution": "1080p",
        },
    },
]


DEFAULT_REFURB_URLS = [
    "https://ca.refurb.io/products/dell-7050-sff-i5-6500-16gb-ram-512gb-ssd-windows-10-pro-refurbished",
]


def run_live_smoke(
    *,
    config_path: str | None = None,
    output_dir: str | Path | None = None,
    limit_per_query: int | None = None,
    price_cases: list[dict[str, Any]] | None = None,
    refurb_urls: list[str] | None = None,
    source_factory: SourceFactory = build_listing_sources,
    html_fetcher: HtmlFetcher | None = None,
) -> dict[str, Any]:
    """Run live source checks and optionally write summary files."""
    config = load_config(config_path)
    sources = source_factory(config)
    html_fetcher = html_fetcher or _fetch_html
    limit = _positive_int(limit_per_query, _positive_int(config.get("smoke_limit_per_query"), 5))
    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_path": config_path,
        "limit_per_query": limit,
        "overall_status": "ok",
        "checks": [],
        "summary": {"ok": 0, "warning": 0, "error": 0},
    }

    payload["checks"].extend(_credential_checks(sources))
    selected_price_cases = DEFAULT_PRICE_CASES if price_cases is None else price_cases
    selected_refurb_urls = DEFAULT_REFURB_URLS if refurb_urls is None else refurb_urls

    for case in selected_price_cases:
        payload["checks"].append(_price_case_check(case, sources, config, limit))
    payload["checks"].extend(_refurb_io_live_checks(config, selected_refurb_urls, html_fetcher))

    payload["summary"] = _summary_counts(payload["checks"])
    payload["overall_status"] = "error" if payload["summary"]["error"] else "warning" if payload["summary"]["warning"] else "ok"

    if output_dir:
        _write_outputs(Path(output_dir), payload)
    return payload


def main() -> None:
    load_env_file()
    parser = argparse.ArgumentParser(prog="python -m pc_pricer.live_smoke")
    parser.add_argument("--config", default=None, help="Path to config.yaml.")
    parser.add_argument("--output", default="smoke-reports", help="Folder for live smoke summaries.")
    parser.add_argument("--limit-per-query", type=int, default=None, help="Listings to fetch per generated query.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary.")
    args = parser.parse_args()

    try:
        payload = run_live_smoke(
            config_path=args.config,
            output_dir=args.output,
            limit_per_query=args.limit_per_query,
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(_format_text_summary(payload))
        print(f"Output folder: {args.output}")

    if payload["overall_status"] == "error":
        raise SystemExit(1)


def _credential_checks(sources: list[Any]) -> list[dict[str, Any]]:
    checks = []
    for source in sources:
        if getattr(source, "enabled", True) is False:
            continue
        source_name = _source_name(source)
        if source_name != "ebay" or not hasattr(source, "check_credentials"):
            continue
        try:
            result = source.check_credentials()
        except RuntimeError as exc:
            checks.append(
                _check(
                    name="ebay_credentials",
                    severity="error",
                    message=str(exc),
                    source=source_name,
                )
            )
            continue
        checks.append(
            _check(
                name="ebay_credentials",
                severity="ok",
                message=str(result.get("message") or "eBay credential check succeeded."),
                source=source_name,
            )
        )
    return checks


def _price_case_check(
    case: dict[str, Any],
    sources: list[Any],
    config: dict[str, Any],
    limit_per_query: int,
) -> dict[str, Any]:
    name = str(case.get("name") or "unnamed_price_case")
    try:
        result = price_specs(
            dict(case.get("specs") or {}),
            sources,
            limit_per_query=limit_per_query,
            target_condition=str(case.get("condition") or config.get("default_condition") or "good"),
            warn_below_comparables=_positive_int(config.get("warn_below_comparables"), 5),
            wide_iqr_ratio=_positive_float(config.get("wide_iqr_ratio"), 0.40),
            support_limit=_positive_int(config.get("support_limit"), 5),
            high_shipping_cad=_positive_float(config.get("high_shipping_cad"), 75.0),
            high_shipping_ratio=_positive_float(config.get("high_shipping_ratio"), 0.25),
            asking_discount_low=_non_negative_float(config.get("asking_discount_low"), 0.0),
            asking_discount_high=_non_negative_float(config.get("asking_discount_high"), 0.05),
        )
    except RuntimeError as exc:
        return _check(name=name, severity="error", message=str(exc), check_type="price_case")

    statuses = merge_config_source_statuses(result.get("source_statuses"), config)
    source_errors = [status for status in statuses if status.get("enabled") and status.get("status") == "error"]
    comparable_count = _safe_int(result.get("count"))
    median = _safe_float(result.get("median_price_cad") or result.get("asking_median_price_cad"))
    min_comparables = _positive_int(case.get("min_comparables"), 1)
    floor = _safe_float(case.get("price_floor_cad"))
    ceiling = _safe_float(case.get("price_ceiling_cad"))
    warnings = []

    if source_errors:
        return _check(
            name=name,
            severity="error",
            message=f"{len(source_errors)} enabled source(s) errored.",
            check_type="price_case",
            result=_price_result_summary(result, statuses),
        )
    if comparable_count <= 0:
        return _check(
            name=name,
            severity="error",
            message="No usable comparable listings found.",
            check_type="price_case",
            result=_price_result_summary(result, statuses),
        )
    if comparable_count < min_comparables:
        warnings.append(f"Only {comparable_count} comparable(s); expected at least {min_comparables}.")
    if median is not None and floor is not None and median < floor:
        warnings.append(f"Median {median:.2f} CAD is below smoke floor {floor:.2f} CAD.")
    if median is not None and ceiling is not None and median > ceiling:
        warnings.append(f"Median {median:.2f} CAD is above smoke ceiling {ceiling:.2f} CAD.")
    if case.get("require_identification") and not _identified_device(result):
        warnings.append("Device identification did not complete.")
    missing_terms = _missing_required_query_terms(result, list(case.get("required_query_terms") or []))
    if missing_terms:
        warnings.append(f"Generated queries missing required term(s): {', '.join(missing_terms)}.")

    return _check(
        name=name,
        severity="warning" if warnings else "ok",
        message=" ".join(warnings) if warnings else "Price case returned usable comparables.",
        check_type="price_case",
        result=_price_result_summary(result, statuses),
    )


def _refurb_io_live_checks(
    config: dict[str, Any],
    urls: list[str],
    html_fetcher: HtmlFetcher,
) -> list[dict[str, Any]]:
    if not _source_enabled(config, "refurb_io", default=True):
        return [
            _check(
                name="refurb_io_live_parser",
                severity="ok",
                message="Refurb.io disabled in config; live parser sanity skipped.",
                source="refurb_io",
            )
        ]

    checks = []
    for index, url in enumerate(urls, start=1):
        name = f"refurb_io_live_parser_{index}"
        try:
            html = html_fetcher(url)
            product = parse_product_html(html)
        except RuntimeError as exc:
            checks.append(_check(name=name, severity="error", message=str(exc), source="refurb_io", url=url))
            continue

        details = {
            "title": product.title,
            "price_cad": product.item_price_cad,
            "available": product.available,
            "condition_raw": product.condition_raw,
            "shipping_cad": product.shipping_cad,
            "shipping_is_estimated": product.shipping_is_estimated,
            "sku": product.sku,
        }
        missing = []
        if not product.title:
            missing.append("title")
        if product.item_price_cad is None:
            missing.append("price")
        if product.available is None:
            missing.append("availability")
        if product.shipping_cad is None and product.shipping_is_estimated is not True:
            missing.append("shipping")

        severity = "error" if "title" in missing or "price" in missing else "warning" if missing else "ok"
        message = f"Missing parser field(s): {', '.join(missing)}." if missing else "Refurb.io product parser returned usable fields."
        checks.append(_check(name=name, severity=severity, message=message, source="refurb_io", url=url, result=details))
    return checks


def _fetch_html(url: str) -> str:
    req = request.Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "CFS-Price-Compare/live-smoke",
        },
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} while fetching {url}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Request failed while fetching {url}: {exc.reason}") from exc


def _price_result_summary(result: dict[str, Any], statuses: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "comparables": result.get("count"),
        "median_price_cad": result.get("median_price_cad"),
        "asking_median_price_cad": result.get("asking_median_price_cad"),
        "confidence_flags": list(result.get("confidence_flags") or []),
        "listing_warnings": list(result.get("listing_warnings") or []),
        "raw_listing_count": result.get("raw_listing_count"),
        "deduped_listing_count": result.get("deduped_listing_count"),
        "source_statuses": statuses,
        "queries": result.get("queries") or [],
        "device_identification": result.get("device_identification"),
    }


def _identified_device(result: dict[str, Any]) -> bool:
    identification = result.get("device_identification")
    return isinstance(identification, dict) and identification.get("status") == "identified"


def _missing_required_query_terms(result: dict[str, Any], terms: list[str]) -> list[str]:
    query_text = " ".join(str(query.get("text") or "") for query in result.get("queries") or [] if isinstance(query, dict))
    lowered = query_text.lower()
    return [term for term in terms if str(term).lower() not in lowered]


def _write_outputs(output_dir: Path, payload: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "live_smoke_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    (output_dir / "live_smoke_summary.txt").write_text(_format_text_summary(payload), encoding="utf-8")


def _format_text_summary(payload: dict[str, Any]) -> str:
    lines = [
        "Live smoke summary",
        "------------------",
        f"Generated: {payload.get('generated_at')}",
        f"Overall:   {payload.get('overall_status')}",
        f"Checks:    ok={payload.get('summary', {}).get('ok', 0)} warning={payload.get('summary', {}).get('warning', 0)} error={payload.get('summary', {}).get('error', 0)}",
        "",
    ]
    for check in payload.get("checks") or []:
        if not isinstance(check, dict):
            continue
        lines.append(f"[{str(check.get('severity') or 'unknown').upper()}] {check.get('name')}: {check.get('message')}")
    return "\n".join(lines)


def _check(
    *,
    name: str,
    severity: str,
    message: str,
    check_type: str = "source",
    source: str | None = None,
    url: str | None = None,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "type": check_type,
        "severity": severity,
        "message": message,
    }
    if source:
        payload["source"] = source
    if url:
        payload["url"] = url
    if result is not None:
        payload["result"] = result
    return payload


def _summary_counts(checks: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"ok": 0, "warning": 0, "error": 0}
    for check in checks:
        severity = str(check.get("severity") or "").lower()
        if severity in summary:
            summary[severity] += 1
    return summary


def _source_name(source: Any) -> str:
    return str(getattr(source, "name", source.__class__.__name__) or "unknown").strip().lower()


def _source_enabled(config: dict[str, Any], source_name: str, default: bool) -> bool:
    sources = config.get("sources")
    source_config = sources.get(source_name) if isinstance(sources, dict) else None
    if not isinstance(source_config, dict):
        return default
    value = source_config.get("enabled")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return default


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


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    main()
