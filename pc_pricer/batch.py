"""Batch CSV import helpers for pricing multiple devices."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pc_pricer.gui_forms import DEVICE_TYPES, fields_for_device, validate_specs
from pc_pricer.spec_builder import build_manual_specs, manual_device_type


BATCH_FIELDS = [
    "item_id",
    "device_type",
    "brand",
    "model",
    "condition",
    "form_factor",
    "cpu",
    "ram",
    "storage",
    "storage_type",
    "oem_sku",
    "variant",
    "screen_size",
    "gpu",
    "carrier",
    "connectivity",
    "size",
    "resolution",
    "refresh_rate",
    "printer_type",
    "color",
    "capacity",
    "drive_type",
    "drive_form_factor",
    "interface",
    "notes",
]


@dataclass
class BatchItem:
    row_number: int
    item_id: str
    device_type: str
    values: dict[str, Any]
    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors


def load_batch_csv(path: str | Path) -> list[BatchItem]:
    """Load and validate a batch CSV file."""
    csv_path = Path(path)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise RuntimeError("Batch CSV has no header row.")

        fieldnames = [_canonical_field_name(name) for name in reader.fieldnames]
        if "item_id" not in fieldnames:
            raise RuntimeError("Batch CSV is missing required column: item_id.")
        if "device_type" not in fieldnames:
            raise RuntimeError("Batch CSV is missing required column: device_type.")

        items = []
        for row_number, raw_row in enumerate(reader, start=2):
            row = {
                _canonical_field_name(key): _clean_cell(value)
                for key, value in raw_row.items()
                if key is not None
            }
            if _row_is_empty(row):
                continue
            items.append(_batch_item_from_row(row_number, row))

    if not items:
        raise RuntimeError("Batch CSV does not contain any device rows.")
    return items


def validate_batch_items(items: list[BatchItem]) -> list[BatchItem]:
    """Revalidate edited batch items and return updated copies."""
    return [_batch_item_from_row(item.row_number, _row_from_item(item)) for item in items]


def batch_template_csv() -> str:
    """Return a CSV template users can open in Excel."""
    lines = []
    output = _StringWriter(lines)
    writer = csv.DictWriter(output, fieldnames=BATCH_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerow(
        {
            "item_id": "001",
            "device_type": "computer",
            "brand": "Lenovo",
            "model": "ThinkPad X13 Yoga",
            "condition": "good",
            "form_factor": "laptop",
            "cpu": "i5-1135G7",
            "ram": "16",
            "storage": "512",
            "storage_type": "SSD",
        }
    )
    writer.writerow(
        {
            "item_id": "002",
            "device_type": "phone",
            "brand": "Apple",
            "model": "iPhone 13",
            "condition": "good",
            "variant": "Pro Max",
            "screen_size": "6.7",
            "storage": "128",
            "carrier": "unlocked",
        }
    )
    return "".join(lines)


def batch_summary_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build flat summary rows from completed GUI/CLI batch item dictionaries."""
    rows = []
    for index, item in enumerate(items, start=1):
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        rows.append(
            {
                "order": index,
                "item_id": item.get("item_id") or "",
                "device_type": item.get("device_type") or "",
                "status": item.get("status") or "",
                "summary": item.get("summary") or "",
                "estimate_low_cad": result.get("conservative_low_cad") or result.get("price_low_cad") or "",
                "estimate_high_cad": result.get("conservative_high_cad") or result.get("price_high_cad") or "",
                "median_price_cad": result.get("median_price_cad") or result.get("asking_median_price_cad") or "",
                "comparables": result.get("count") if result else "",
                "confidence_flags": ", ".join(str(flag) for flag in result.get("confidence_flags", [])) if result else "",
                "error": item.get("error") or "",
            }
        )
    return rows


def write_batch_summary_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    """Write a batch summary CSV."""
    summary_path = Path(path)
    fieldnames = [
        "order",
        "item_id",
        "device_type",
        "status",
        "summary",
        "estimate_low_cad",
        "estimate_high_cad",
        "median_price_cad",
        "comparables",
        "confidence_flags",
        "error",
    ]
    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def specs_for_batch_item(item: BatchItem) -> dict[str, Any]:
    """Return pipeline-ready specs for a validated batch item."""
    specs = build_manual_specs(item.device_type, item.values)
    specs["batch_item_id"] = item.item_id
    return specs


def _batch_item_from_row(row_number: int, row: dict[str, str]) -> BatchItem:
    item_id = row.get("item_id", "").strip()
    errors = []
    if not item_id:
        errors.append("Item ID is required.")

    try:
        device_type = manual_device_type(row.get("device_type"))
    except RuntimeError as exc:
        device_type = row.get("device_type", "").strip().lower()
        errors.append(str(exc))

    values = _values_for_device(row, device_type)
    if device_type in DEVICE_TYPES:
        errors.extend(validate_specs(device_type, values))
        try:
            build_manual_specs(device_type, values)
        except RuntimeError as exc:
            errors.append(str(exc))

    return BatchItem(
        row_number=row_number,
        item_id=item_id,
        device_type=device_type,
        values=values,
        errors=_dedupe_errors(errors),
    )


def _values_for_device(row: dict[str, str], device_type: str) -> dict[str, str]:
    field_names = {field.name for field in fields_for_device(device_type)}
    field_names.update({"notes"})
    return {
        key: value
        for key, value in row.items()
        if key in field_names and value not in ("", None)
    }


def _row_from_item(item: BatchItem) -> dict[str, str]:
    row = {"item_id": item.item_id, "device_type": item.device_type}
    row.update({key: str(value) for key, value in item.values.items() if value not in (None, "")})
    return row


def _canonical_field_name(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _clean_cell(value: Any) -> str:
    return str(value or "").strip()


def _row_is_empty(row: dict[str, str]) -> bool:
    return not any(value.strip() for value in row.values())


def _dedupe_errors(errors: list[str]) -> list[str]:
    deduped = []
    for error in errors:
        if error and error not in deduped:
            deduped.append(error)
    return deduped


class _StringWriter:
    def __init__(self, lines: list[str]) -> None:
        self.lines = lines

    def write(self, value: str) -> int:
        self.lines.append(value)
        return len(value)
