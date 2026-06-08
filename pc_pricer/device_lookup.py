"""Identify devices from exact model identifiers before pricing."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol
import re


LOOKUP_SOURCE_NAMES = {"refurb_io", "amazon_renewed"}


class DeviceLookupSource(Protocol):
    name: str
    enabled: bool

    def search(self, query: str, max_results: int) -> list[dict[str, Any]]:
        """Return search results that may contain title and source_specs metadata."""
        ...


def enrich_specs_from_model_lookup(
    specs: dict[str, Any],
    sources: Sequence[DeviceLookupSource],
    max_results: int = 3,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return specs enriched by a trusted exact-identifier lookup when possible."""
    identifier = model_identifier(specs)
    if not identifier:
        return dict(specs), None

    device_type = str(specs.get("device_type") or "computer").strip().lower()
    if device_type != "computer":
        return dict(specs), None

    brand = _clean(specs.get("brand"))
    queries = _dedupe([_join_terms(brand, identifier), identifier])
    lookup_sources = [
        source
        for source in sources
        if getattr(source, "enabled", True) and str(getattr(source, "name", "")).lower() in LOOKUP_SOURCE_NAMES
    ]
    if not lookup_sources:
        return dict(specs), _lookup_status(identifier, queries, "not_available", errors=["No enabled device lookup source."])

    candidates = []
    errors = []
    for source in lookup_sources:
        source_name = str(getattr(source, "name", source.__class__.__name__) or "unknown")
        for query in queries:
            try:
                listings = source.search(query, max(1, max_results))
            except Exception as exc:  # pragma: no cover - defensive boundary around optional lookup.
                errors.append({"source": source_name, "query": query, "message": str(exc)})
                continue
            for listing in listings[:max_results]:
                candidate = _candidate_from_listing(listing, specs, identifier, source_name, query)
                if candidate:
                    candidates.append(candidate)

    if not candidates:
        return dict(specs), _lookup_status(identifier, queries, "not_found", errors=errors)

    best = max(candidates, key=lambda candidate: candidate["score"])
    if best["score"] < 6:
        return dict(specs), _lookup_status(
            identifier,
            queries,
            "low_confidence",
            candidates=_public_candidates(candidates),
            errors=errors,
        )

    enriched, added_fields = _merge_enriched_specs(specs, identifier, best["enriched_specs"])
    status = _lookup_status(
        identifier,
        queries,
        "identified",
        source=best["source"],
        title=best["title"],
        url=best.get("url"),
        confidence=_confidence_label(best["score"]),
        score=best["score"],
        added_fields=added_fields,
        candidates=_public_candidates(candidates),
        errors=errors,
    )
    return enriched, status


def model_identifier(specs: dict[str, Any]) -> str | None:
    """Return the exact model identifier worth looking up, if one is present."""
    oem_sku = _clean(specs.get("oem_sku"))
    if oem_sku:
        return oem_sku
    model = _clean(specs.get("model"))
    search_model = _clean(specs.get("search_model"))
    if model and (specs.get("model_is_machine_type") or _looks_like_model_number(model)):
        return model
    if search_model and _looks_like_model_number(search_model):
        return search_model
    return None


def looks_like_model_number(value: Any) -> bool:
    text = _clean(value)
    return bool(text and _looks_like_model_number(text))


def _candidate_from_listing(
    listing: dict[str, Any],
    target_specs: dict[str, Any],
    identifier: str,
    source_name: str,
    query: str,
) -> dict[str, Any] | None:
    source_specs = listing.get("source_specs") if isinstance(listing.get("source_specs"), dict) else {}
    title = _clean(listing.get("title")) or ""
    text = _normalized_text(
        " ".join(
            str(part)
            for part in [
                title,
                listing.get("item_id"),
                listing.get("url"),
                *source_specs.values(),
            ]
            if part
        )
    )
    brand = _clean(target_specs.get("brand"))
    title_text = _normalized_text(title)
    if brand and title and not _all_tokens_present(title_text, brand):
        return None
    if brand and not title and not _all_tokens_present(text, brand):
        return None

    enriched = _canonical_specs_from_listing(title, source_specs, target_specs)
    score = 0
    if brand:
        score += 3
    if _identifier_in_text(identifier, text):
        score += 5
    elif query and _identifier_in_text(identifier, _normalized_text(query)):
        score += 2
    if enriched.get("search_model"):
        score += 2
    for key in ["form_factor", "cpu_short", "ram_gb"]:
        if enriched.get(key):
            score += 1
    if enriched.get("storage"):
        score += 1

    return {
        "source": source_name,
        "query": query,
        "title": title,
        "url": listing.get("url"),
        "score": score,
        "enriched_specs": enriched,
    }


def _canonical_specs_from_listing(
    title: str,
    source_specs: dict[str, Any],
    target_specs: dict[str, Any],
) -> dict[str, Any]:
    source_model = _clean(source_specs.get("model"))
    specs = {
        "device_type": "computer",
        "brand": _clean(source_specs.get("brand")) or _clean(target_specs.get("brand")),
        "search_model": source_model,
        "form_factor": _clean(source_specs.get("form_factor")) or _form_factor_from_text(title),
        "screen_size": _clean(source_specs.get("screen_size")),
        "cpu_short": _clean(source_specs.get("cpu_short")) or _clean(source_specs.get("cpu")),
        "cpu": _clean(source_specs.get("cpu")) or _clean(source_specs.get("processor")),
        "ram_gb": _safe_int(source_specs.get("ram_gb")),
        "storage": _storage_from_source_specs(source_specs, title),
    }
    return {key: value for key, value in specs.items() if value not in (None, "", [], 0)}


def _merge_enriched_specs(
    original: dict[str, Any],
    identifier: str,
    found: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    enriched = dict(original)
    added_fields = []

    if not _clean(enriched.get("oem_sku")):
        enriched["oem_sku"] = identifier
        added_fields.append("oem_sku")
    if _clean(enriched.get("model")) == identifier or _clean(enriched.get("search_model")) == identifier:
        enriched["model"] = identifier
        enriched["model_is_machine_type"] = True
        if "model_is_machine_type" not in added_fields:
            added_fields.append("model_is_machine_type")

    for key, value in found.items():
        if value in (None, "", [], 0):
            continue
        if key == "search_model":
            current = _clean(enriched.get("search_model"))
            original_model = _clean(enriched.get("model"))
            user_supplied_family = original_model and original_model != identifier and not _looks_like_model_number(original_model)
            if not user_supplied_family and (not current or current == identifier or _looks_like_model_number(current)):
                enriched[key] = value
                added_fields.append(key)
            continue
        if key == "storage":
            if not enriched.get("storage"):
                enriched[key] = value
                added_fields.append(key)
            continue
        if not enriched.get(key):
            enriched[key] = value
            added_fields.append(key)

    return enriched, _dedupe(added_fields)


def _lookup_status(
    identifier: str,
    queries: list[str],
    status: str,
    source: str | None = None,
    title: str | None = None,
    url: Any = None,
    confidence: str | None = None,
    score: int | None = None,
    added_fields: list[str] | None = None,
    candidates: list[dict[str, Any]] | None = None,
    errors: list[Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "attempted": True,
        "status": status,
        "identifier": identifier,
        "queries": queries,
    }
    if source:
        payload["source"] = source
    if title:
        payload["title"] = title
    if url:
        payload["url"] = url
    if confidence:
        payload["confidence"] = confidence
    if score is not None:
        payload["score"] = score
    if added_fields:
        payload["added_fields"] = added_fields
    if candidates:
        payload["candidates"] = candidates
    if errors:
        payload["errors"] = errors
    return payload


def _public_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(candidates, key=lambda candidate: candidate["score"], reverse=True)
    return [
        {
            "source": candidate["source"],
            "query": candidate["query"],
            "title": candidate["title"],
            "url": candidate.get("url"),
            "score": candidate["score"],
        }
        for candidate in ordered[:5]
    ]


def _form_factor_from_text(value: Any) -> str | None:
    text = _normalized_text(value)
    if any(marker in text for marker in [" all in one ", " aio "]):
        return "all-in-one"
    if any(marker in text for marker in [" laptop ", " notebook ", " ultrabook ", " thinkpad ", " elitebook ", " latitude "]):
        return "laptop"
    if any(marker in text for marker in [" desktop ", " tower ", " optiplex ", " thinkcentre "]):
        return "desktop"
    return None


def _storage_from_source_specs(source_specs: dict[str, Any], title: str) -> list[dict[str, Any]]:
    storage_gb = _safe_int(source_specs.get("storage_gb")) or _storage_gb(source_specs.get("storage")) or _storage_gb(title)
    if not storage_gb:
        return []
    drive_type = _drive_type(source_specs.get("storage") or title)
    return [{"size_gb": storage_gb, "type": drive_type}]


def _storage_gb(value: Any) -> int:
    text = str(value or "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*(tb|gb)", text, flags=re.IGNORECASE)
    if not match:
        return 0
    amount = float(match.group(1))
    return int(amount * 1024) if match.group(2).lower() == "tb" else int(amount)


def _drive_type(value: Any) -> str:
    text = str(value or "").lower()
    if "nvme" in text:
        return "NVMe"
    if "emmc" in text:
        return "eMMC"
    if "hdd" in text or "hard drive" in text:
        return "HDD"
    return "SSD"


def _confidence_label(score: int) -> str:
    if score >= 10:
        return "high"
    if score >= 7:
        return "medium"
    return "low"


def _identifier_in_text(identifier: str, text: str) -> bool:
    compact_identifier = re.sub(r"[^a-z0-9]+", "", identifier.lower())
    compact_text = re.sub(r"[^a-z0-9]+", "", text.lower())
    return bool(compact_identifier and compact_identifier in compact_text)


def _all_tokens_present(text: str, value: str) -> bool:
    tokens = re.findall(r"[a-z0-9]+", value.lower())
    return all(token in text for token in tokens)


def _looks_like_model_number(value: str) -> bool:
    text = value.strip()
    if len(text) < 6 or len(text) > 24:
        return False
    if " " in text:
        return False
    if not re.search(r"[A-Za-z]", text) or not re.search(r"\d", text):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9._-]+", text))


def _normalized_text(value: Any) -> str:
    return f" {re.sub(r'[^a-z0-9]+', ' ', str(value or '').lower()).strip()} "


def _join_terms(*terms: str | None) -> str | None:
    clean_terms = [_clean(term) for term in terms]
    clean_terms = [term for term in clean_terms if term]
    if not clean_terms:
        return None
    return " ".join(clean_terms)


def _dedupe(values: list[Any]) -> list[Any]:
    deduped = []
    seen = set()
    for value in values:
        if value in (None, ""):
            continue
        key = str(value).lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def _safe_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0
