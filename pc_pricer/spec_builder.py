"""Build pricing specs from manually entered values."""

from __future__ import annotations

import re
from typing import Any


VALID_CONDITIONS = {"good", "excellent", "mint", "any"}
VALID_DEVICE_TYPES = {"computer", "phone", "tablet", "monitor", "printer", "storage"}


def build_manual_specs(device_type: Any, values: dict[str, Any]) -> dict[str, Any]:
    """Return pipeline-ready specs from manually entered values."""
    clean_device_type = manual_device_type(device_type)
    if clean_device_type == "computer":
        return _manual_computer_specs(values)
    if clean_device_type == "phone":
        return _manual_phone_specs(values)
    if clean_device_type == "tablet":
        return _manual_tablet_specs(values)
    if clean_device_type == "monitor":
        return _manual_monitor_specs(values)
    if clean_device_type == "printer":
        return _manual_printer_specs(values)
    if clean_device_type == "storage":
        return _manual_storage_device_specs(values)
    raise RuntimeError(f"Invalid device type {clean_device_type!r}.")


def gui_values_from_detected_specs(specs: dict[str, Any]) -> dict[str, str]:
    """Convert detected computer specs into editable GUI field values."""
    storage = specs.get("storage") or []
    primary_drive = storage[0] if isinstance(storage, list) and storage else {}
    if not isinstance(primary_drive, dict):
        primary_drive = {}

    values = {
        "form_factor": specs.get("form_factor"),
        "brand": specs.get("brand"),
        "model": specs.get("search_model") or specs.get("model"),
        "oem_sku": specs.get("oem_sku"),
        "variant": specs.get("variant"),
        "screen_size": specs.get("screen_size"),
        "cpu": specs.get("cpu_short") or specs.get("cpu"),
        "ram": specs.get("ram_gb"),
        "storage": primary_drive.get("size_gb"),
        "storage_type": primary_drive.get("type"),
        "gpu": specs.get("gpu"),
    }
    return {key: str(value) for key, value in values.items() if value not in (None, "", [], {})}


def manual_device_type(value: Any) -> str:
    text = (_clean_text(value) or "computer").lower()
    if text not in VALID_DEVICE_TYPES:
        raise RuntimeError(
            "Invalid device type. Use computer, phone, tablet, monitor, printer, or storage."
        )
    return text


def _manual_computer_specs(values: dict[str, Any]) -> dict[str, Any]:
    form_factor = _clean_text(values.get("form_factor"))
    if not form_factor:
        raise RuntimeError("Computer pricing requires a form factor: laptop, desktop, or all-in-one.")

    specs = {
        "device_type": "computer",
        "brand": _clean_text(values.get("brand")),
        "model": _clean_text(values.get("model")),
        "search_model": _clean_text(values.get("model")),
        "oem_sku": _clean_text(values.get("oem_sku")),
        "form_factor": form_factor,
        "variant": _variant(values.get("variant")),
        "screen_size": _screen_size(values.get("screen_size")),
        "cpu": _clean_text(values.get("cpu")),
        "cpu_short": _clean_text(values.get("cpu")),
        "ram_gb": _positive_int_or_none(values.get("ram")),
        "storage": _manual_storage(values.get("storage"), values.get("storage_type")),
        "gpu": _clean_text(values.get("gpu")),
        "input_method": values.get("input_method") or "manual",
    }
    return _without_empty_values(specs)


def _manual_phone_specs(values: dict[str, Any]) -> dict[str, Any]:
    specs = _manual_base_specs(values, "phone")
    specs.update(
        {
            "storage_capacity": _capacity_from_gb(values.get("storage")),
            "variant": _variant(values.get("variant")),
            "screen_size": _screen_size(values.get("screen_size")),
            "carrier": _clean_text(values.get("carrier")),
        }
    )
    return _without_empty_values(specs)


def _manual_tablet_specs(values: dict[str, Any]) -> dict[str, Any]:
    specs = _manual_base_specs(values, "tablet")
    specs.update(
        {
            "storage_capacity": _capacity_from_gb(values.get("storage")),
            "variant": _variant(values.get("variant")),
            "screen_size": _screen_size(values.get("screen_size")),
            "connectivity": _clean_text(values.get("connectivity")),
        }
    )
    return _without_empty_values(specs)


def _manual_monitor_specs(values: dict[str, Any]) -> dict[str, Any]:
    specs = _manual_base_specs(values, "monitor")
    specs.update(
        {
            "size": _screen_size(values.get("size")),
            "resolution": _clean_text(values.get("resolution")),
            "refresh_rate": _refresh_rate(values.get("refresh_rate")),
        }
    )
    return _without_empty_values(specs)


def _manual_printer_specs(values: dict[str, Any]) -> dict[str, Any]:
    specs = _manual_base_specs(values, "printer")
    specs.update(
        {
            "printer_type": _clean_text(values.get("printer_type")),
            "color": _clean_text(values.get("color")),
        }
    )
    return _without_empty_values(specs)


def _manual_storage_device_specs(values: dict[str, Any]) -> dict[str, Any]:
    specs = _manual_base_specs(values, "storage")
    specs.update(
        {
            "capacity": _clean_text(values.get("capacity")) or _capacity_from_gb(values.get("storage")),
            "drive_type": _drive_type(values.get("drive_type")),
            "drive_form_factor": _drive_form_factor(values.get("drive_form_factor")),
            "interface": _storage_interface(values.get("interface")),
        }
    )
    return _without_empty_values(specs)


def _manual_base_specs(values: dict[str, Any], device_type: str) -> dict[str, Any]:
    return {
        "device_type": device_type,
        "brand": _clean_text(values.get("brand")),
        "model": _clean_text(values.get("model")),
        "search_model": _clean_text(values.get("model")),
        "input_method": values.get("input_method") or "manual",
    }


def _without_empty_values(specs: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in specs.items() if value not in (None, [], "")}


def _manual_storage(size_gb: Any, drive_type: Any) -> list[dict[str, Any]]:
    size = _positive_int_or_none(size_gb)
    if not size:
        return []
    return [
        {
            "size_gb": size,
            "type": _storage_type(drive_type),
        }
    ]


def _storage_type(value: Any) -> str:
    text = _clean_text(value) or "SSD"
    return text.upper() if text.lower() in {"ssd", "hdd", "nvme", "emmc"} else text


def _capacity_from_gb(value: Any) -> str | None:
    size = _positive_int_or_none(value)
    if not size:
        return None
    if size >= 1024 and size % 1024 == 0:
        return f"{size // 1024}TB"
    if size >= 1000:
        divisor = 1000 if size % 1000 == 0 else 1024
        tb = round(size / divisor, 1)
        return f"{tb:g}TB"
    return f"{size}GB"


def _drive_form_factor(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None

    normalized = re.sub(r"\s+", "", text.lower()).replace('"', "")
    aliases = {
        "1.8": "1.8",
        "1.8in": "1.8",
        "1.8inch": "1.8",
        "2.5": "2.5",
        "2.5in": "2.5",
        "2.5inch": "2.5",
        "3.5": "3.5",
        "3.5in": "3.5",
        "3.5inch": "3.5",
        "m.2": "m.2",
        "m2": "m.2",
        "msata": "msata",
    }
    return aliases.get(normalized, text)


def _drive_type(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    lowered = text.lower()
    if lowered == "ssd":
        return "SSD"
    if lowered == "hdd":
        return "HDD"
    return text


def _storage_interface(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    normalized = re.sub(r"[\s_-]+", "", text.lower())
    aliases = {
        "nvme": "NVMe",
        "sata": "SATA",
        "usb": "USB",
        "sas": "SAS",
        "pcie": "PCIe",
        "pciexpress": "PCIe",
    }
    return aliases.get(normalized, text)


def _screen_size(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    normalized = re.sub(r'\s*(inch|in|")\s*$', "", text, flags=re.IGNORECASE).strip()
    return f'{normalized}"' if normalized else None


def _variant(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    normalized = re.sub(r"\s+", " ", text).strip()
    aliases = {
        "promax": "Pro Max",
        "pro max": "Pro Max",
        "pro-max": "Pro Max",
        "plus": "Plus",
        "+": "Plus",
        "mini": "mini",
        "fe": "FE",
        "air": "Air",
        "pro": "Pro",
        "max": "Max",
    }
    return aliases.get(normalized.lower(), normalized)


def _refresh_rate(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    normalized = re.sub(r"\s*hz\s*$", "", text, flags=re.IGNORECASE).strip()
    return f"{normalized}Hz" if normalized else None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _positive_int_or_none(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
