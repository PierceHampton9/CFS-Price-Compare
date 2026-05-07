"""Filter listings before price aggregation."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any


GLOBAL_PARTS_TITLE_PATTERNS = [
    r"\bfor parts\b",
    r"\bparts only\b",
    r"\bnot working\b",
    r"\bnot functional\b",
]

DEVICE_PARTS_TITLE_PATTERNS = {
    "computer": [
        r"\bmotherboard\b",
        r"\bmainboard\b",
        r"\blogic board\b",
        r"\bscreen replacement\b",
        r"\breplacement\s+(lcd|screen|keyboard|battery|cable)\b",
        r"\b(lcd|screen|keyboard|battery|cable)\s+replacement\b",
        r"\b(keyboard|battery|screen|cable)\s+only\b",
        r"\bpalm\s*rest\b",
        r"\bpalmrest\b",
        r"\bhinge\b",
        r"\bbezel\b",
        r"\bbottom case\b",
    ],
    "phone": [
        r"\bcase\s+for\b",
        r"\bcover\s+for\b",
        r"\bfor\s+(?!sale\b|resale\b)\S+(?:\s+\S+){0,4}\s+(case|cover)\b",
        r"\bscreen protector\b",
        r"\btempered glass\b",
        r"\bcharging cable\b",
        r"\blightning cable\b",
        r"\busb[-\s]?c cable\b",
        r"\breplacement\s+(screen|display|lcd|battery|camera|back glass)\b",
        r"\b(screen|display|lcd|battery|camera|back glass)\s+replacement\b",
        r"\bicloud locked\b",
        r"\bactivation locked\b",
        r"\bpasscode locked\b",
        r"\bblacklisted\b",
    ],
    "tablet": [
        r"\bcase\s+for\b",
        r"\bcover\s+for\b",
        r"\bfor\s+(?!sale\b|resale\b)\S+(?:\s+\S+){0,4}\s+(case|cover)\b",
        r"\bkeyboard case\b",
        r"\bscreen protector\b",
        r"\btempered glass\b",
        r"\bcharging cable\b",
        r"\busb[-\s]?c cable\b",
        r"\breplacement\s+(screen|display|lcd|battery|digitizer)\b",
        r"\b(screen|display|lcd|battery|digitizer)\s+replacement\b",
        r"\bicloud locked\b",
        r"\bactivation locked\b",
        r"\bpasscode locked\b",
    ],
    "monitor": [
        r"\bmonitor stand\b",
        r"\bstand\s+for\b",
        r"\bwall mount\b",
        r"\bvesa mount\b",
        r"\bpower adapter\b",
        r"\bac adapter\b",
        r"\bcontroller board\b",
        r"\breplacement panel\b",
        r"\breplacement\s+lcd\s+panel\b",
        r"\blcd panel\s+(only|for)\b",
        r"\bpanel replacement\b",
    ],
    "printer": [
        r"\bink cartridge\b",
        r"\btoner cartridge\b",
        r"\bcartridge\s+for\b",
        r"\bdrum unit\b",
        r"\bprinthead\b",
        r"\bprint head\b",
        r"\bfuser\b",
        r"\bpaper tray\b",
        r"\bmaintenance kit\b",
    ],
    "storage": [
        r"\benclosure\b",
        r"\bcaddy\b",
        r"\bdock\b",
        r"\bdocking station\b",
        r"\bsata\s+(to|->)\s+usb\s+adapter\b",
        r"\benclosure adapter\b",
        r"\busb[-\s]?c?\s+cable\s+only\b",
        r"\bsata cable only\b",
        r"\bdrive tray\b",
        r"\bmounting bracket\b",
        r"\bheatsink\s+for\b",
        r"\bfor\s+.+\bheatsink\b",
    ],
}

def filter_listings(
    listings: list[dict[str, Any]],
    target_condition: str | None = "good",
    device_type: str | None = None,
) -> dict[str, Any]:
    """Return listings suitable for aggregation plus simple exclusion counts."""
    condition = _clean_condition(target_condition)
    clean_device_type = _clean_device_type(device_type)
    included = []
    excluded_reasons: Counter[str] = Counter()

    for listing in listings:
        reason = exclusion_reason(listing, condition, device_type=clean_device_type)
        if reason:
            excluded_reasons[reason] += 1
            continue
        included.append(listing)

    return {
        "listings": included,
        "excluded_count": sum(excluded_reasons.values()),
        "excluded_reasons": dict(excluded_reasons),
        "target_condition": condition or "any",
    }


def exclusion_reason(
    listing: dict[str, Any],
    target_condition: str | None = "good",
    device_type: str | None = None,
) -> str | None:
    """Return a short reason if a listing should not be used as a comparable."""
    if _looks_like_parts_listing(listing, device_type=device_type):
        return "parts_or_accessory"

    condition = _clean_condition(target_condition)
    listing_condition = _clean_condition(listing.get("condition_norm"))
    if condition and not listing_condition:
        return "unknown_condition"
    if condition and listing_condition != condition:
        return "condition_mismatch"

    return None


def _looks_like_parts_listing(listing: dict[str, Any], device_type: str | None = None) -> bool:
    if _clean_condition(listing.get("condition_norm")) == "parts":
        return True

    clean_device_type = _clean_device_type(device_type or listing.get("device_type"))
    title = str(listing.get("title") or "").lower()
    patterns = [
        *GLOBAL_PARTS_TITLE_PATTERNS,
        *DEVICE_PARTS_TITLE_PATTERNS.get(clean_device_type, []),
    ]
    return any(re.search(pattern, title) for pattern in patterns)


def _clean_condition(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text or text == "any":
        return None
    return text


def _clean_device_type(value: Any) -> str:
    text = str(value or "computer").strip().lower()
    return text or "computer"
