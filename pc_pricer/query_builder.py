"""Build pricing search queries from detected or manually entered specs."""

from __future__ import annotations

import re
from typing import Any


def build_queries(specs: dict[str, Any]) -> list[dict[str, Any]]:
    """Return search queries ordered from most specific to broadest."""
    form_factor = _clean(specs.get("form_factor"))

    if form_factor in {"laptop", "all-in-one"}:
        queries = _laptop_queries(specs, form_factor)
    else:
        queries = _desktop_queries(specs)

    return _dedupe_queries(queries)


def _laptop_queries(specs: dict[str, Any], form_factor: str) -> list[dict[str, Any]]:
    brand = _clean(specs.get("brand"))
    model = _model_term(specs)
    oem_sku = _clean(specs.get("oem_sku"))
    cpu = _cpu_term(specs)
    ram = _ram_term(specs)
    storage = _storage_term(specs)

    queries = []
    if oem_sku:
        queries.append(_query(oem_sku, 1, f"exact {form_factor} OEM SKU"))

    if model:
        spec_query = _join_terms(brand, model, cpu, ram)
        queries.append(_query(spec_query, 2, f"{form_factor} brand/model/spec fallback"))

        family_query = _join_terms(brand, model)
        if family_query:
            queries.append(_query(family_query, 3, f"{form_factor} brand/model family fallback"))
    elif cpu and ram:
        queries.append(_query(_join_terms(brand, cpu, ram, storage, form_factor), 3, f"{form_factor} spec fallback"))

    return queries


def _desktop_queries(specs: dict[str, Any]) -> list[dict[str, Any]]:
    brand = _clean(specs.get("brand"))
    model = _model_term(specs)
    cpu = _cpu_term(specs)
    ram = _ram_term(specs)
    storage = _storage_term(specs)
    gpu = _dedicated_gpu_term(specs)
    form_factor = _clean(specs.get("form_factor")) or "desktop"

    queries = []

    if (brand or model) and cpu and ram:
        queries.append(
            _query(
                _join_terms(brand, model, cpu, ram, storage, gpu),
                1,
                "desktop brand/model/spec match",
            )
        )

    if cpu and ram:
        queries.append(
            _query(
                _join_terms(cpu, ram, storage, gpu, form_factor),
                2,
                "desktop spec match",
            )
        )
        queries.append(
            _query(
                _join_terms(cpu, ram, gpu, form_factor),
                3,
                "desktop broad spec fallback",
            )
        )

    return queries


def _query(text: str | None, tier: int, reason: str) -> dict[str, Any]:
    return {
        "text": text,
        "tier": tier,
        "reason": reason,
    }


def _dedupe_queries(queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean_queries = []
    seen = set()

    for query in queries:
        text = _clean_query_text(query.get("text"))
        if not text:
            continue

        key = text.lower()
        if key in seen:
            continue

        seen.add(key)
        clean_queries.append({**query, "text": text})

    return clean_queries


def _cpu_term(specs: dict[str, Any]) -> str | None:
    return _clean(specs.get("cpu_short")) or _clean(specs.get("cpu"))


def _model_term(specs: dict[str, Any]) -> str | None:
    if specs.get("model_is_machine_type") and not _clean(specs.get("search_model")):
        return None
    return _clean(specs.get("search_model")) or _clean(specs.get("model"))


def _ram_term(specs: dict[str, Any]) -> str | None:
    ram_gb = specs.get("ram_gb")
    if not ram_gb:
        return None
    return f"{ram_gb}GB"


def _storage_term(specs: dict[str, Any]) -> str | None:
    storage = specs.get("storage") or []
    if not isinstance(storage, list):
        return None

    drives = [
        drive for drive in storage if isinstance(drive, dict) and _safe_int(drive.get("size_gb")) > 0
    ]
    if not drives:
        return None

    drive = max(drives, key=lambda item: _safe_int(item.get("size_gb")))
    size = _marketed_storage_size(drive.get("size_gb"))
    drive_type = _clean(drive.get("type"))

    return _join_terms(size, drive_type)


def _marketed_storage_size(size_gb: Any) -> str | None:
    try:
        size = int(size_gb)
    except (TypeError, ValueError):
        return None

    if size <= 0:
        return None

    common_sizes = [128, 256, 512, 1024, 2048, 4096]
    for common_size in common_sizes:
        lower = common_size * 0.85
        upper = common_size * 1.08
        if lower <= size <= upper:
            if common_size >= 1024:
                return f"{common_size // 1024}TB"
            return f"{common_size}GB"

    if size >= 1000:
        return f"{round(size / 1024)}TB"
    return f"{size}GB"


def _dedicated_gpu_term(specs: dict[str, Any]) -> str | None:
    gpu = _clean(specs.get("gpu"))
    if not gpu:
        return None

    gpu_lower = gpu.lower()
    dedicated_markers = [
        "geforce",
        "gtx",
        "rtx",
        "quadro",
        "radeon rx",
        "firepro",
        "arc",
    ]
    integrated_markers = [
        "intel hd",
        "intel uhd",
        "intel iris",
        "iris xe",
        "radeon graphics",
    ]

    if any(marker in gpu_lower for marker in dedicated_markers):
        return gpu
    if any(marker in gpu_lower for marker in integrated_markers):
        return None
    return None


def _join_terms(*terms: str | None) -> str | None:
    clean_terms = [_clean(term) for term in terms]
    clean_terms = [term for term in clean_terms if term]
    if not clean_terms:
        return None
    return " ".join(clean_terms)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _clean_query_text(text: Any) -> str | None:
    return _clean(text)


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
