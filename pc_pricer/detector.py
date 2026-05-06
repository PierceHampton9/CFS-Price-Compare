"""Windows hardware spec detection."""

from __future__ import annotations

import json
import platform
import re
import subprocess
from typing import Any


POWERSHELL_SCRIPT = r"""
$ErrorActionPreference = "Stop"

$data = [ordered]@{
    ComputerSystem = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop |
        Select-Object Manufacturer, Model, SystemType, PCSystemType
    ComputerSystemProduct = Get-CimInstance Win32_ComputerSystemProduct -ErrorAction Stop |
        Select-Object Vendor, Name, Version, IdentifyingNumber, SKUNumber
    SystemEnclosure = Get-CimInstance Win32_SystemEnclosure -ErrorAction Stop |
        Select-Object ChassisTypes
    BIOS = Get-CimInstance Win32_BIOS -ErrorAction Stop |
        Select-Object Manufacturer, SerialNumber, SMBIOSBIOSVersion
    Processor = Get-CimInstance Win32_Processor -ErrorAction Stop |
        Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed
    PhysicalMemory = @(Get-CimInstance Win32_PhysicalMemory -ErrorAction Stop |
        Select-Object Capacity, Speed, Manufacturer, PartNumber)
    DiskDrive = @(Get-CimInstance Win32_DiskDrive -ErrorAction Stop |
        Select-Object Model, Size, MediaType, InterfaceType)
    VideoController = @(Get-CimInstance Win32_VideoController -ErrorAction Stop |
        Select-Object Name, AdapterRAM)
}

$data | ConvertTo-Json -Depth 5
"""


GENERIC_VALUES = {
    "",
    "none",
    "null",
    "not available",
    "not specified",
    "o.e.m.",
    "oem",
    "system manufacturer",
    "system product name",
    "to be filled by o.e.m.",
    "default string",
}


def detect_specs(include_raw: bool = False) -> dict[str, Any]:
    """Detect this Windows computer's useful pricing specs."""
    raw = collect_windows_specs()
    specs = specs_from_raw(raw)
    if include_raw:
        specs["raw"] = raw
    return specs


def collect_windows_specs() -> dict[str, Any]:
    """Collect raw specs from Windows CIM as JSON."""
    if platform.system() != "Windows":
        raise RuntimeError("Automatic spec detection currently only supports Windows.")

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            POWERSHELL_SCRIPT,
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    if completed.returncode != 0:
        message = completed.stderr.strip() or "PowerShell spec detection failed."
        raise RuntimeError(message)

    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("PowerShell returned invalid JSON.") from exc


def specs_from_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """Turn raw CIM output into the small spec shape the rest of the app needs."""
    computer = _dict(raw.get("ComputerSystem"))
    product = _dict(raw.get("ComputerSystemProduct"))
    enclosure = _dict(raw.get("SystemEnclosure"))
    processor = _dict(raw.get("Processor"))
    memory_modules = [
        module for module in _list(raw.get("PhysicalMemory")) if _safe_int(module.get("Capacity")) > 0
    ]
    disks = _list(raw.get("DiskDrive"))
    video = _list(raw.get("VideoController"))

    brand = _first_clean(
        product.get("Vendor"),
        computer.get("Manufacturer"),
    )
    model = _first_clean(
        product.get("Name"),
        computer.get("Model"),
        product.get("Version"),
    )
    model_is_machine_type = _looks_like_lenovo_machine_type(brand, model or "")
    search_model = _search_model(model, model_is_machine_type)
    oem_sku = _first_clean(
        product.get("SKUNumber"),
    )
    serial_number = _first_clean(
        product.get("IdentifyingNumber"),
        _dict(raw.get("BIOS")).get("SerialNumber"),
    )

    cpu_name = _clean_text(processor.get("Name"))
    ram_gb = _bytes_to_gb(sum(_safe_int(module.get("Capacity")) for module in memory_modules))
    storage = [_disk_summary(disk) for disk in disks if _safe_int(disk.get("Size")) > 0]
    gpu_names = [_clean_text(gpu.get("Name")) for gpu in video]
    gpu_names = [name for name in gpu_names if name and "basic display" not in name.lower()]

    warnings: list[str] = []
    if not brand:
        warnings.append("Could not detect manufacturer.")
    if not model:
        warnings.append("Could not detect model.")
    if not oem_sku:
        warnings.append("Could not detect OEM SKU.")
    if not cpu_name:
        warnings.append("Could not detect CPU.")
    if not ram_gb:
        warnings.append("Could not detect RAM.")
    if not storage:
        warnings.append("Could not detect storage.")

    return {
        "brand": brand,
        "model": model,
        "search_model": search_model,
        "model_is_machine_type": model_is_machine_type,
        "oem_sku": oem_sku,
        "serial_number": serial_number,
        "form_factor": _form_factor(computer, enclosure, model),
        "cpu": cpu_name,
        "cpu_short": _cpu_short_name(cpu_name),
        "cpu_cores": _safe_int(processor.get("NumberOfCores")) or None,
        "cpu_threads": _safe_int(processor.get("NumberOfLogicalProcessors")) or None,
        "ram_gb": ram_gb,
        "ram_modules": len(memory_modules),
        "storage": storage,
        "gpu": ", ".join(dict.fromkeys(gpu_names)) or None,
        "warnings": warnings,
    }


def _disk_summary(disk: dict[str, Any]) -> dict[str, Any]:
    return {
        "size_gb": _bytes_to_gb(_safe_int(disk.get("Size"))),
        "type": _storage_type(disk),
        "model": _clean_text(disk.get("Model")),
    }


def _storage_type(disk: dict[str, Any]) -> str | None:
    media_type = (_clean_text(disk.get("MediaType")) or "").lower()
    model = (_clean_text(disk.get("Model")) or "").lower()

    if "ssd" in media_type or "ssd" in model or "nvme" in model:
        return "SSD"
    if "hdd" in media_type or "hard disk" in media_type:
        return "HDD"
    return None


def _form_factor(
    computer: dict[str, Any],
    enclosure: dict[str, Any],
    model: str | None,
) -> str | None:
    chassis_types = enclosure.get("ChassisTypes") or []
    if not isinstance(chassis_types, list):
        chassis_types = [chassis_types]

    chassis_values = {_safe_int(value) for value in chassis_types}
    if chassis_values & {8, 9, 10, 14, 30, 31, 32}:
        return "laptop"
    if 13 in chassis_values:
        return "all-in-one"
    if chassis_values & {3, 4, 5, 6, 7, 15, 16, 35}:
        return "desktop"

    pc_type = _safe_int(computer.get("PCSystemType"))
    model_text = (model or "").lower()

    if pc_type == 3:
        return "laptop"
    if "all-in-one" in model_text or "aio" in model_text:
        return "all-in-one"
    if pc_type == 2:
        return "desktop"
    return None


def _cpu_short_name(cpu_name: str | None) -> str | None:
    if not cpu_name:
        return None

    patterns = [
        r"\b(i[3579]-\d{3,5}[A-Z0-9]{0,4})\b",
        r"\b(Ryzen\s+[3579]\s+\d{3,5}[A-Z0-9]{0,4})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, cpu_name, flags=re.IGNORECASE)
        if match:
            return _clean_text(match.group(1))
    return cpu_name


def _search_model(model: str | None, model_is_machine_type: bool) -> str | None:
    model_text = _clean_text(model)
    if not model_text:
        return None

    if model_is_machine_type:
        return None

    return model_text


def _looks_like_lenovo_machine_type(brand: str | None, model: str) -> bool:
    brand_text = (brand or "").lower()
    if "lenovo" not in brand_text:
        return False
    return bool(re.fullmatch(r"[0-9A-Z]{4}[0-9A-Z]{4,6}", model.strip(), flags=re.IGNORECASE))


def _first_clean(*values: Any) -> str | None:
    for value in values:
        cleaned = _clean_text(value)
        if cleaned and cleaned.lower() not in GENERIC_VALUES:
            return cleaned
    return None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    text = text.replace("(R)", "").replace("(TM)", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _bytes_to_gb(value: int) -> int | None:
    if value <= 0:
        return None
    return round(value / 1024 / 1024 / 1024)


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []
