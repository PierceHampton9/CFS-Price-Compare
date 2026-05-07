"""Form definitions and validation for the GUI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEVICE_TYPES = ["computer", "phone", "tablet", "monitor", "printer", "storage"]
CONDITIONS = ["good", "excellent", "mint", "any"]
COMPUTER_FORM_FACTORS = ["laptop", "desktop", "all-in-one"]
COMPUTER_MODES = ["auto", "manual"]


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    required: bool = False
    options: tuple[str, ...] = ()
    placeholder: str = ""


COMMON_FIELDS = [
    FieldSpec("brand", "Brand", placeholder="Apple, Dell, Lenovo, Brother"),
    FieldSpec("model", "Model", placeholder="iPhone 13, U2419H, ThinkPad T14"),
    FieldSpec("condition", "Condition", required=True, options=tuple(CONDITIONS)),
]


FIELD_SETS: dict[str, list[FieldSpec]] = {
    "computer": [
        FieldSpec("form_factor", "Form factor", required=True, options=tuple(COMPUTER_FORM_FACTORS)),
        *COMMON_FIELDS,
        FieldSpec("oem_sku", "OEM SKU", placeholder="Optional exact OEM identifier"),
        FieldSpec("variant", "Variant", placeholder="Optional, such as Pro or Air"),
        FieldSpec("screen_size", "Screen size", placeholder='Optional, such as 14"'),
        FieldSpec("cpu", "CPU", placeholder="i5-1135G7, M1 Pro"),
        FieldSpec("ram", "RAM (GB)", placeholder="16"),
        FieldSpec("storage", "Storage (GB)", placeholder="512"),
        FieldSpec("storage_type", "Storage type", options=("SSD", "HDD", "NVMe", "eMMC")),
        FieldSpec("gpu", "GPU", placeholder="Optional dedicated GPU"),
    ],
    "phone": [
        *COMMON_FIELDS,
        FieldSpec("variant", "Variant", placeholder="Optional, such as mini, Pro, Pro Max, Plus"),
        FieldSpec("screen_size", "Screen size", placeholder="Optional, such as 6.1"),
        FieldSpec("storage", "Storage (GB)", required=True, placeholder="128"),
        FieldSpec("carrier", "Carrier/unlocked", options=("unlocked", "locked", "unknown")),
    ],
    "tablet": [
        *COMMON_FIELDS,
        FieldSpec("variant", "Variant", placeholder="Optional, such as FE, Plus, Pro, Air"),
        FieldSpec("screen_size", "Screen size", placeholder="Optional, such as 11 or 12.9"),
        FieldSpec("storage", "Storage (GB)", required=True, placeholder="128"),
        FieldSpec("connectivity", "Connectivity", options=("Wi-Fi", "cellular", "unknown")),
    ],
    "monitor": [
        *COMMON_FIELDS,
        FieldSpec("size", "Screen size", required=True, placeholder="24"),
        FieldSpec("resolution", "Resolution", placeholder="1080p, 1440p, 4K"),
        FieldSpec("refresh_rate", "Refresh rate", placeholder="60Hz"),
    ],
    "printer": [
        *COMMON_FIELDS,
        FieldSpec("printer_type", "Printer type", options=("laser", "inkjet", "label", "unknown")),
        FieldSpec("color", "Color", options=("mono", "color", "unknown")),
    ],
    "storage": [
        FieldSpec("brand", "Brand", placeholder="Optional, such as Samsung or WD"),
        FieldSpec("model", "Model", placeholder="Optional, such as 970 EVO Plus"),
        FieldSpec("condition", "Condition", required=True, options=tuple(CONDITIONS)),
        FieldSpec("capacity", "Capacity", required=True, placeholder="1TB, 512GB"),
        FieldSpec("drive_type", "Drive type", required=True, options=("ssd", "hdd")),
        FieldSpec("drive_form_factor", "Drive form factor", options=("1.8", "2.5", "3.5", "m.2", "msata")),
        FieldSpec("interface", "Interface", options=("SATA", "NVMe", "USB", "SAS", "unknown")),
    ],
}


def fields_for_device(device_type: str) -> list[FieldSpec]:
    """Return GUI field definitions for a device type."""
    return list(FIELD_SETS.get(device_type, []))


def validate_device_type(device_type: str | None) -> list[str]:
    if device_type in DEVICE_TYPES:
        return []
    return ["Choose a device type."]


def validate_computer_mode(mode: str | None) -> list[str]:
    if mode in COMPUTER_MODES:
        return []
    return ["Choose auto-detect or manual entry."]


def validate_specs(device_type: str, values: dict[str, Any]) -> list[str]:
    """Return user-facing validation messages for required GUI fields."""
    fields = fields_for_device(device_type)
    errors = [
        f"{field.label} is required."
        for field in fields
        if field.required and not _present(values.get(field.name))
    ]

    if device_type != "storage" and not _present(values.get("brand")):
        errors.append("Brand is required.")
    if device_type != "storage" and not _present(values.get("model")):
        errors.append("Model is required.")

    if device_type == "computer" and not (
        _present(values.get("model")) or _present(values.get("cpu"))
    ):
        errors.append("Enter at least a model or CPU for computer pricing.")

    return errors


def _present(value: Any) -> bool:
    return value is not None and str(value).strip() != ""
