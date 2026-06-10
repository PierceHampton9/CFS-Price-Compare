"""Capacity parsing helpers shared by pricing filters."""

from __future__ import annotations

import re


def capacity_values_gb(text: str) -> set[int]:
    """Return storage-like capacity values found in free text."""
    values = set()
    lowered = text.lower()
    for left, right in re.findall(r"\b(\d{2,4})\s*/\s*(\d{2,4})\s*(?:gb|g)?\b", lowered):
        values.add(int(left))
        values.add(int(right))
    for amount, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(tb|gb|g)\b", lowered):
        parsed = float(amount)
        values.add(int(parsed * 1024) if unit == "tb" else int(parsed))
    return values
