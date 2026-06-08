"""Shared helpers for exact model and OEM identifiers."""

from __future__ import annotations

from typing import Any
import re


def model_identifier(specs: dict[str, Any]) -> str | None:
    """Return the exact model identifier worth looking up, if one is present."""
    oem_sku = _clean(specs.get("oem_sku"))
    if oem_sku:
        return oem_sku
    model = _clean(specs.get("model"))
    search_model = _clean(specs.get("search_model"))
    if model and (specs.get("model_is_machine_type") or looks_like_model_number(model)):
        return model
    if search_model and looks_like_model_number(search_model):
        return search_model
    return None


def looks_like_model_number(value: Any) -> bool:
    """Return whether a value should be treated as an exact identifier."""
    text = _clean(value)
    if not text:
        return False
    if len(text) < 6 or len(text) > 24:
        return False
    if " " in text:
        return False
    if not re.search(r"[A-Za-z]", text) or not re.search(r"\d", text):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9._-]+", text))


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None
