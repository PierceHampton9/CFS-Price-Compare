"""Summarize configured pricing source runtime status."""

from __future__ import annotations

from typing import Any

from pc_pricer.config import DEFAULT_CONFIG


SOURCE_STATUS_ORDER = ["ebay", "refurb_io", "amazon_renewed"]


def merge_config_source_statuses(
    runtime_statuses: Any,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Merge runtime source attempts with disabled/enabled config state."""
    by_source: dict[str, dict[str, Any]] = {}
    if isinstance(runtime_statuses, list):
        for status in runtime_statuses:
            if not isinstance(status, dict):
                continue
            source = _source_key(status.get("source"))
            if not source:
                continue
            by_source[source] = dict(status)

    for source in SOURCE_STATUS_ORDER:
        enabled = _configured_enabled(config, source)
        status = by_source.setdefault(
            source,
            {
                "source": source,
                "searched": False,
                "query_count": 0,
                "queries": [],
                "raw_listing_count": 0,
                "error_count": 0,
                "errors": [],
            },
        )
        status["enabled"] = enabled
        status["configured"] = True

    return [_summarize_status(by_source[source]) for source in SOURCE_STATUS_ORDER if source in by_source]


def _configured_enabled(config: dict[str, Any], source: str) -> bool:
    sources = config.get("sources")
    source_config = sources.get(source) if isinstance(sources, dict) else None
    default_source_config = ((DEFAULT_CONFIG.get("sources") or {}).get(source) or {})
    default = _bool_value(default_source_config.get("enabled"), True)
    if not isinstance(source_config, dict):
        return default
    return _bool_value(source_config.get("enabled"), default)


def _summarize_status(status: dict[str, Any]) -> dict[str, Any]:
    updated = dict(status)
    errors = [str(error) for error in updated.get("errors") or [] if error]
    updated["errors"] = errors
    updated["error_count"] = _safe_int(updated.get("error_count")) or len(errors)
    updated["query_count"] = _safe_int(updated.get("query_count"))
    updated["raw_listing_count"] = _safe_int(updated.get("raw_listing_count"))
    updated["candidate_count"] = _safe_int(updated.get("candidate_count"))
    updated["dropped_candidate_count"] = _safe_int(updated.get("dropped_candidate_count"))
    updated["dropped_candidate_reasons"] = _reason_counts(updated.get("dropped_candidate_reasons"))
    updated["detail_page_count"] = _safe_int(updated.get("detail_page_count"))
    updated["detail_error_count"] = _safe_int(updated.get("detail_error_count"))
    updated["queries"] = list(updated.get("queries") or [])
    updated["detail_urls"] = list(updated.get("detail_urls") or [])

    if updated.get("enabled") is False:
        updated["status"] = "disabled"
        updated["message"] = "Disabled in config."
    elif updated["error_count"] > 0:
        updated["status"] = "error"
        updated["message"] = errors[0] if errors else "Source search failed."
    elif updated.get("searched") and updated["raw_listing_count"] > 0:
        updated["status"] = "returned"
        updated["message"] = _searched_message(updated, f"Returned {updated['raw_listing_count']} raw listing(s).")
    elif updated.get("searched"):
        updated["status"] = "no_results"
        updated["message"] = _searched_message(updated, "Searched but returned 0 raw listings.")
    else:
        updated["status"] = "not_searched"
        updated["message"] = "Enabled but no usable query was sent."
    return updated


def _searched_message(status: dict[str, Any], base_message: str) -> str:
    details = []
    candidate_count = _safe_int(status.get("candidate_count"))
    detail_page_count = _safe_int(status.get("detail_page_count"))
    detail_error_count = _safe_int(status.get("detail_error_count"))
    dropped_candidate_count = _safe_int(status.get("dropped_candidate_count"))
    if candidate_count:
        details.append(f"{candidate_count} search candidate(s)")
    if dropped_candidate_count:
        reasons = _format_reasons(status.get("dropped_candidate_reasons"))
        detail = f"{dropped_candidate_count} candidate(s) dropped"
        if reasons:
            detail = f"{detail}: {reasons}"
        details.append(detail)
    if detail_page_count:
        details.append(f"{detail_page_count} product page(s) opened")
    if detail_error_count:
        details.append(f"{detail_error_count} product page error(s)")
    if not details:
        return base_message
    return f"{base_message} {'; '.join(details)}."


def _source_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text or ""


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


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _reason_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    counts = {}
    for key, count in value.items():
        text = str(key or "").strip()
        parsed_count = _safe_int(count)
        if text and parsed_count:
            counts[text] = parsed_count
    return counts


def _format_reasons(value: Any) -> str:
    reasons = _reason_counts(value)
    if not reasons:
        return ""
    return ", ".join(f"{reason}={count}" for reason, count in sorted(reasons.items()))
