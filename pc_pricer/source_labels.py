"""Display labels for pricing sources and source-level basis values."""

from __future__ import annotations

from typing import Any


SOURCE_LABELS = {
    "amazon_renewed": "Amazon Renewed",
    "ebay": "eBay",
    "refurb_io": "Refurb.io",
}

SOURCE_BASIS_LABELS = {
    "ebay_asking_adjusted": "eBay filtered asking median",
    "ebay_fallback": "eBay fallback",
    "ebay_mixed": "eBay sold and asking listings",
    "ebay_sold": "eBay sold listings",
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
