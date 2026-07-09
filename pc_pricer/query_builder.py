"""Build pricing search queries from detected or manually entered specs."""

from __future__ import annotations

import re
from typing import Any

from pc_pricer.model_identifier import looks_like_model_number


def build_queries(specs: dict[str, Any]) -> list[dict[str, Any]]:
    """Return search queries ordered from most specific to broadest."""
    device_type = _device_type(specs)
    if device_type == "phone":
        return _dedupe_queries(_phone_queries(specs))
    if device_type == "tablet":
        return _dedupe_queries(_tablet_queries(specs))
    if device_type == "monitor":
        return _dedupe_queries(_monitor_queries(specs))
    if device_type == "printer":
        return _dedupe_queries(_printer_queries(specs))
    if device_type == "storage":
        return _dedupe_queries(_storage_device_queries(specs))

    form_factor = _clean(specs.get("form_factor"))

    if form_factor is not None and _uses_laptop_style_queries(form_factor):
        queries = _laptop_queries(specs, form_factor)
    else:
        queries = _desktop_queries(specs)

    return _dedupe_queries(queries)


def _device_type(specs: dict[str, Any]) -> str:
    return (_clean(specs.get("device_type")) or "computer").lower()


def _laptop_queries(specs: dict[str, Any], form_factor: str) -> list[dict[str, Any]]:
    brand = _clean(specs.get("brand"))
    model = _model_term(specs)
    model_identifier = _model_identifier_term(specs)
    variant = _clean(specs.get("variant"))
    screen_size = _screen_size_term(specs.get("screen_size"))
    cpu = _cpu_term(specs)
    ram = _ram_term(specs)
    storage = _storage_term(specs)

    queries = []
    if model_identifier:
        queries.append(_query(_join_terms(brand, model_identifier), 1, f"exact {form_factor} model number"))
        queries.append(_query(model_identifier, 1, f"exact {form_factor} model number"))

    if model:
        spec_query = _join_terms(brand, model, variant, screen_size, cpu, ram)
        queries.append(
            _query(spec_query, 2, f"{form_factor} brand/model/spec fallback")
        )

        family_query = _join_terms(brand, model, variant, screen_size)
        if family_query:
            queries.append(
                _query(family_query, 3, f"{form_factor} brand/model family fallback")
            )
    elif cpu and ram:
        queries.append(
            _query(
                _join_terms(brand, cpu, ram, storage, form_factor),
                3,
                f"{form_factor} spec fallback",
            )
        )

    return queries


def _uses_laptop_style_queries(form_factor: str | None) -> bool:
    normalized = (form_factor or "").lower()
    return normalized in {
        "laptop",
        "notebook",
        "ultrabook",
        "all-in-one",
        "2-in-1",
        "2 in 1",
        "convertible",
        "detachable",
        "tablet pc",
        "tablet",
    }


def _phone_queries(specs: dict[str, Any]) -> list[dict[str, Any]]:
    brand = _clean(specs.get("brand"))
    model = _model_term(specs)
    variant = _clean(specs.get("variant"))
    screen_size = _screen_size_term(specs.get("screen_size"))
    storage = _clean(specs.get("storage_capacity"))
    carrier = _clean(specs.get("carrier"))

    return [
        _query(
            _join_terms(brand, model, variant, screen_size, storage, carrier),
            1,
            "phone brand/model/variant/storage/carrier match",
        ),
        _query(
            _join_terms(brand, model, variant, screen_size, storage),
            2,
            "phone brand/model/variant/storage match",
        ),
        _query(
            _join_terms(brand, model, variant, screen_size),
            3,
            "phone brand/model/variant fallback",
        ),
    ]


def _tablet_queries(specs: dict[str, Any]) -> list[dict[str, Any]]:
    brand = _clean(specs.get("brand"))
    model = _model_term(specs)
    variant = _clean(specs.get("variant"))
    screen_size = _screen_size_term(specs.get("screen_size"))
    storage = _clean(specs.get("storage_capacity"))
    connectivity = _clean(specs.get("connectivity"))

    return [
        _query(
            _join_terms(brand, model, variant, screen_size, storage, connectivity),
            1,
            "tablet brand/model/variant/storage/connectivity match",
        ),
        _query(
            _join_terms(brand, model, variant, screen_size, storage),
            2,
            "tablet brand/model/variant/storage match",
        ),
        _query(
            _join_terms(brand, model, variant, screen_size),
            3,
            "tablet brand/model/variant fallback",
        ),
    ]


def _monitor_queries(specs: dict[str, Any]) -> list[dict[str, Any]]:
    brand = _clean(specs.get("brand"))
    model = _model_term(specs)
    size = _screen_size_term(specs.get("size"))
    resolution = _clean(specs.get("resolution"))
    refresh_rate = _refresh_rate_term(specs.get("refresh_rate"))

    return [
        _query(
            _join_terms(brand, model, size, resolution, refresh_rate, "monitor"),
            1,
            "monitor exact spec match",
        ),
        _query(
            _join_terms(brand, model, size, resolution, "monitor"),
            2,
            "monitor brand/model/display match",
        ),
        _query(_join_terms(brand, model, "monitor"), 3, "monitor brand/model fallback"),
    ]


def _printer_queries(specs: dict[str, Any]) -> list[dict[str, Any]]:
    brand = _clean(specs.get("brand"))
    model = _model_term(specs)
    printer_type = _clean(specs.get("printer_type"))
    color = _clean(specs.get("color"))

    return [
        _query(
            _join_terms(brand, model, printer_type, color, "printer"),
            1,
            "printer exact spec match",
        ),
        _query(
            _join_terms(brand, model, printer_type, "printer"), 2, "printer type match"
        ),
        _query(_join_terms(brand, model, "printer"), 3, "printer brand/model fallback"),
    ]


def _storage_device_queries(specs: dict[str, Any]) -> list[dict[str, Any]]:
    brand = _clean(specs.get("brand"))
    model = _model_term(specs)
    capacity = _clean(specs.get("capacity"))
    drive_type = _clean(specs.get("drive_type"))
    form_factor = _storage_form_factor_term(specs.get("drive_form_factor"))
    interface = _clean(specs.get("interface"))

    return [
        _query(
            _join_terms(brand, model, capacity, drive_type, form_factor, interface),
            1,
            "storage exact spec match",
        ),
        _query(
            _join_terms(brand, model, capacity, drive_type),
            2,
            "storage brand/model/capacity match",
        ),
        _query(
            _join_terms(capacity, drive_type, form_factor, interface),
            3,
            "storage spec fallback",
        ),
    ]


def _desktop_queries(specs: dict[str, Any]) -> list[dict[str, Any]]:
    brand = _clean(specs.get("brand"))
    model = _model_term(specs)
    model_identifier = _model_identifier_term(specs)
    cpu = _cpu_term(specs)
    ram = _ram_term(specs)
    storage = _storage_term(specs)
    gpu = _dedicated_gpu_term(specs)
    form_factor = _clean(specs.get("form_factor")) or "desktop"

    queries = []

    if model_identifier:
        queries.append(_query(_join_terms(brand, model_identifier), 1, "desktop exact model number"))
        queries.append(_query(model_identifier, 1, "desktop exact model number"))

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


def _model_identifier_term(specs: dict[str, Any]) -> str | None:
    oem_sku = _clean(specs.get("oem_sku"))
    if oem_sku:
        return oem_sku
    search_model = _clean(specs.get("search_model"))
    if search_model and not looks_like_model_number(search_model):
        return None
    model = _clean(specs.get("model"))
    if specs.get("model_is_machine_type") and model:
        return model
    if model and looks_like_model_number(model):
        return model
    if search_model and looks_like_model_number(search_model):
        return search_model
    return None


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
        drive
        for drive in storage
        if isinstance(drive, dict) and _safe_int(drive.get("size_gb")) > 0
    ]
    if not drives:
        return None

    drive = max(drives, key=lambda item: _safe_int(item.get("size_gb")))
    return _marketed_storage_size(drive.get("size_gb"))


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


def _screen_size_term(value: Any) -> str | None:
    text = _clean(value)
    if not text:
        return None
    lowered = (
        text.lower().replace("inch", "").replace("in", "").replace('"', "").strip()
    )
    return f'{lowered}"' if lowered else None


def _refresh_rate_term(value: Any) -> str | None:
    text = _clean(value)
    if not text:
        return None
    lowered = text.lower()
    return text if lowered.endswith("hz") else f"{text}Hz"


def _storage_form_factor_term(value: Any) -> str | None:
    text = _clean(value)
    if not text:
        return None
    return "mSATA" if text.lower() == "msata" else text


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
