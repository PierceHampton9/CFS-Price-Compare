"""Display labels for pricing sources and source-level basis values."""

from __future__ import annotations

import re
from typing import Any


SOURCE_LABELS = {
    "amazon_renewed": "Amazon Renewed",
    "ebay": "eBay",
    "refurb_io": "Refurb.io",
}

SOURCE_BASIS_LABELS = {
    "ebay_active": "eBay active listing median",
    "ebay_asking_adjusted": "eBay active listing conservative estimate",
    "ebay_fallback": "eBay fallback",
    "ebay_mixed": "eBay comparable listings",
    "ebay_sold": "eBay comparable listings",
    "verified_refurb_io": "verified Refurb.io listings",
    "weighted_source_quotes": "weighted source quotes",
}


def format_source_name(value: Any) -> str:
    """Return the user-facing name for a source key."""
    key = str(value or "unknown").strip().lower()
    return SOURCE_LABELS.get(key, str(value or "unknown"))


def format_source_basis(value: Any) -> str:
    """Return the user-facing label for a source basis key."""
    if value in (None, ""):
        return ""
    key = str(value).strip()
    return SOURCE_BASIS_LABELS.get(key, key)


def format_cpu_value(value: Any) -> str:
    """Return a CPU value with conventional product-name casing."""
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"\bI([3579])(?=(?:[-\s]?\d|\b))", r"i\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\bRyzen\b", "Ryzen", text, flags=re.IGNORECASE)
    text = re.sub(r"\bIntel\b", "Intel", text, flags=re.IGNORECASE)
    text = re.sub(r"\bCore\b", "Core", text, flags=re.IGNORECASE)
    return text
