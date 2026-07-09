"""Filter listings before price aggregation."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from pc_pricer.capacity import capacity_values_gb


GLOBAL_PARTS_TITLE_PATTERNS = [
    r"\bfor parts\b",
    r"\bparts only\b",
    r"\bnot working\b",
    r"\bnot functional\b",
    r"\bas[-\s]?is\b",
    r"\bfor repair\b",
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
        r"\bmain board\b",
        r"\bvideo board\b",
        r"\breplacement panel\b",
        r"\breplacement\s+lcd\s+panel\b",
        r"\blcd panel\s+(only|for)\b",
        r"\bpanel replacement\b",
    ],
    "printer": [
        r"\bink\s+(?:cartri\w*|toner|refill|refills)\b",
        r"\btoner\s+(?:cartri\w*|refill|refills)\b",
        r"\bcartri\w*\s+for\b",
        r"\b(?:compatible|replacement)\s+(?:ink|toner|cartri\w*)\b",
        r"\b(?:ink|toner|cartri\w*)\s+(?:compatible|replacement)\b",
        r"\bprinter\s+(?:ink|toner|cartri\w*)\b",
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

DEVICE_VARIANT_PATTERNS = {
    # Keep variant-token filtering limited to devices with stable resale variant words.
    # Laptop titles use words like Pro/Air/Plus too loosely, so laptops rely on model and screen size.
    "phone": {
        "pro max": [r"\bpro\s+max\b"],
        "pro": [r"\bpro\b"],
        "mini": [r"\bmini\b"],
        "plus": [r"\bplus\b", r"(?<=\d)\+"],
        "max": [r"\bmax\b"],
        "fe": [r"\bfe\b", r"\bs\d+\s*fe\b"],
    },
    "tablet": {
        "pro": [r"\bpro\b"],
        "mini": [r"\bmini\b"],
        "plus": [r"\bplus\b", r"(?<=\d)\+"],
        "fe": [r"\bfe\b"],
        "air": [r"\bair\b"],
    },
}

KNOWN_BRANDS = {
    "acer",
    "apple",
    "asus",
    "brother",
    "canon",
    "crucial",
    "dell",
    "epson",
    "hp",
    "hynix",
    "kingston",
    "lenovo",
    "lexmark",
    "lg",
    "microsoft",
    "msi",
    "oyen",
    "pny",
    "samsung",
    "sandisk",
    "seagate",
    "sk hynix",
    "toshiba",
    "western digital",
    "wd",
}

GENERIC_MODEL_TOKENS = {
    "apple",
    "core",
    "desktop",
    "dell",
    "gen",
    "hp",
    "intel",
    "laptop",
    "lenovo",
    "monitor",
    "nvme",
    "pc",
    "pro",
    "ram",
    "samsung",
    "ssd",
    "ultrasharp",
    "windows",
}

CONDITION_RANK = {
    "good": 1,
    "excellent": 2,
    "mint": 3,
}


def filter_listings(
    listings: list[dict[str, Any]],
    target_condition: str | None = "good",
    device_type: str | None = None,
    target_specs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return listings suitable for aggregation plus simple exclusion counts."""
    condition = _clean_condition(target_condition)
    clean_device_type = _clean_device_type(device_type)
    included = []
    excluded_reasons: Counter[str] = Counter()

    for listing in listings:
        reason = exclusion_reason(
            listing,
            condition,
            device_type=clean_device_type,
            target_specs=target_specs,
        )
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
    target_specs: dict[str, Any] | None = None,
) -> str | None:
    """Return a short reason if a listing should not be used as a comparable."""
    if listing.get("available") is False:
        return "unavailable_listing"
    if _looks_like_parts_listing(listing, device_type=device_type):
        return "parts_or_accessory"
    if _looks_like_variant_mismatch(listing, device_type=device_type, target_specs=target_specs):
        return "variant_mismatch"
    spec_reason = _listing_spec_mismatch_reason(listing, device_type=device_type, target_specs=target_specs)
    if spec_reason:
        return spec_reason

    condition = _clean_condition(target_condition)
    listing_condition = _clean_condition(listing.get("condition_norm"))
    if condition and not listing_condition:
        return "unknown_condition"
    if condition and not _condition_matches_target(listing_condition, condition):
        return "condition_mismatch"

    return None


def _condition_matches_target(listing_condition: str | None, target_condition: str | None) -> bool:
    if not target_condition:
        return True
    if not listing_condition:
        return False
    target_rank = CONDITION_RANK.get(target_condition)
    listing_rank = CONDITION_RANK.get(listing_condition)
    if target_rank is None:
        return listing_condition == target_condition
    if listing_rank is None:
        return False
    return target_rank <= listing_rank <= target_rank + 1


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


def _listing_spec_mismatch_reason(
    listing: dict[str, Any],
    device_type: str | None = None,
    target_specs: dict[str, Any] | None = None,
) -> str | None:
    title = str(listing.get("title") or "")
    if not title.strip():
        return None

    clean_device_type = _clean_device_type(device_type or (target_specs or {}).get("device_type"))
    if _looks_like_multi_unit_listing(title):
        return "quantity_or_bundle"
    if _looks_like_incomplete_listing(title, clean_device_type):
        return "incomplete_listing"
    if not isinstance(target_specs, dict):
        return None
    if clean_device_type == "storage" and _looks_like_storage_capacity_variation(title, target_specs):
        return "quantity_or_bundle"
    if _has_conflicting_brand(title, target_specs):
        return "brand_mismatch"
    if _has_conflicting_model(title, clean_device_type, target_specs):
        return "model_mismatch"
    if clean_device_type in {"computer", "phone", "tablet"} and _has_conflicting_storage_capacity(
        title,
        target_specs,
        clean_device_type,
    ):
        return "storage_mismatch"
    if clean_device_type == "storage" and _has_conflicting_storage_device(title, target_specs, listing):
        return "model_mismatch"
    if clean_device_type == "computer" and _has_conflicting_ram(title, target_specs):
        return "ram_mismatch"
    if clean_device_type == "computer" and _has_conflicting_cpu(title, target_specs):
        return "cpu_mismatch"
    if clean_device_type == "phone" and _has_conflicting_carrier(title, target_specs):
        return "carrier_mismatch"
    return None


def _looks_like_multi_unit_listing(title: str) -> bool:
    lowered = title.lower()
    patterns = [
        r"\blot\s+of\s+\d+\b",
        r"\blot[-\s]*\d+\b",
        r"\blot\s*$",
        r"\bwholesale\s+lot\b",
        r"\bpack\s+of\s+\d+\b",
        r"\bbundle\s+of\s+\d+\b",
        r"^\s*\d+\s*x\b",
        r"\b\d+\s*x\s+(?:apple|dell|hp|lenovo|samsung|monitor|laptop|desktop|iphone|ipad|ssd)\b",
        r"\bqty[:\s]*\d+\b",
        r"\bquantity[:\s]*\d+\b",
    ]
    return any(re.search(pattern, lowered) for pattern in patterns)


def _looks_like_storage_capacity_variation(title: str, target_specs: dict[str, Any]) -> bool:
    if not _target_storage_gb(target_specs):
        return False
    return len(capacity_values_gb(title)) > 1


def _looks_like_incomplete_listing(title: str, device_type: str) -> bool:
    lowered = title.lower()
    if device_type == "monitor" and re.search(r"\b(no|without)\s+(?:monitor\s+)?stand\b|\bstand\s+not\s+included\b|\bno\s+base\b", lowered):
        return True
    if device_type == "computer" and re.search(r"\b(no|without)\s+(?:hdd|ssd|hard\s+drive|storage|ram|memory)\b", lowered):
        return True
    if device_type == "computer" and re.search(r"\bboots?\s+(?:only\s+)?to\s+bios\b|\bbios\s+only\b", lowered):
        return True
    if device_type in {"phone", "tablet"} and re.search(r"\b(?:lcd|screen|display).{0,25}\b(?:shadow|burn[-\s]?in|defect|damage)\b|\bno\s+touch\s+id\b", lowered):
        return True
    if device_type == "printer" and re.search(r"\b(no|without)\s+(?:ink|toner|cartridge|cartridges)\b", lowered):
        return True
    if device_type == "storage" and re.search(r"\b(no|without)\s+(?:drive|ssd|hdd)\b", lowered):
        return True
    return False


def _has_conflicting_brand(title: str, target_specs: dict[str, Any]) -> bool:
    target_brand = _brand_key(target_specs.get("brand"))
    if not target_brand:
        return False
    title_text = _normalized_text(title)
    if _brand_present(title_text, target_brand):
        return False
    return any(_brand_present(title_text, brand) for brand in KNOWN_BRANDS if brand != target_brand)


def _has_conflicting_model(title: str, device_type: str, target_specs: dict[str, Any]) -> bool:
    target_model = str(target_specs.get("search_model") or target_specs.get("model") or "").strip()
    if not target_model:
        return False

    title_text = _normalized_text(title)
    target_text = _normalized_text(target_model)
    target_tokens = _model_tokens(target_model)
    if not target_tokens:
        return False

    target_gen = _generation_number(target_text)
    listing_gen = _generation_number(title_text)
    if target_gen and listing_gen and target_gen != listing_gen:
        return True

    target_iphone = _iphone_model_number(target_text)
    listing_iphone = _iphone_model_number(title_text)
    if target_iphone and listing_iphone and target_iphone != listing_iphone:
        return True

    target_numeric = _numeric_model_tokens(target_tokens)
    listing_numeric = _numeric_model_tokens(re.findall(r"[a-z0-9]+", title_text))
    shared_family = any(token in title_text for token in target_tokens if not token.isdigit())
    if target_numeric and listing_numeric and shared_family and not target_numeric.intersection(listing_numeric):
        return True

    if _model_context_present(title_text, target_specs, target_tokens):
        return not all(token in title_text for token in target_tokens)

    return False


def _has_conflicting_storage_device(title: str, target_specs: dict[str, Any], listing: dict[str, Any] | None = None) -> bool:
    model = str(target_specs.get("search_model") or target_specs.get("model") or "").strip()
    if not model:
        return False
    title_text = _normalized_text(title)
    tokens = _model_tokens(model)
    if not tokens:
        return False
    if not _model_context_present(title_text, target_specs, tokens):
        if listing and _safe_int(listing.get("query_tier")) >= 3:
            return True
        return False
    return not all(token in title_text for token in tokens)


def _has_conflicting_storage_capacity(title: str, target_specs: dict[str, Any], device_type: str | None = None) -> bool:
    target_capacity = _target_storage_gb(target_specs)
    if not target_capacity:
        return False
    capacities = capacity_values_gb(title)
    if not capacities:
        return False
    if device_type == "computer" and target_capacity >= 512:
        lower_bound = target_capacity / 2
        upper_bound = target_capacity * 2
        return not any(lower_bound <= capacity <= upper_bound for capacity in capacities)
    if device_type == "computer" and target_capacity >= 128:
        allowed = _adjacent_computer_storage_capacities(target_capacity)
        return not any(capacity in allowed for capacity in capacities)
    return target_capacity not in capacities


def _adjacent_computer_storage_capacities(target_capacity: int) -> set[int]:
    if target_capacity <= 128:
        return {128, 256}
    if target_capacity <= 256:
        return {256, 512}
    common = [512, 1024, 2048]
    nearest = min(common, key=lambda value: abs(value - target_capacity))
    index = common.index(nearest)
    allowed = {nearest}
    if index > 0:
        allowed.add(common[index - 1])
    if index + 1 < len(common):
        allowed.add(common[index + 1])
    return allowed


def _has_conflicting_ram(title: str, target_specs: dict[str, Any]) -> bool:
    try:
        target_ram = int(target_specs.get("ram_gb") or 0)
    except (TypeError, ValueError):
        target_ram = 0
    if not target_ram:
        return False
    ram_values = _ram_values_gb(title)
    if not ram_values:
        return False
    return target_ram not in ram_values


def _has_conflicting_cpu(title: str, target_specs: dict[str, Any]) -> bool:
    target_cpu = str(target_specs.get("cpu_short") or target_specs.get("cpu") or "").strip()
    if not target_cpu:
        return False
    apple_target = _apple_silicon_token(target_cpu)
    if apple_target:
        listing_apple = _apple_silicon_token(title)
        if listing_apple and listing_apple != apple_target:
            return True
        title_text = _normalized_text(title)
        return any(
            marker in title_text
            for marker in [" intel ", " core i3 ", " core i5 ", " core i7 ", " core i9 ", " i3 ", " i5 ", " i7 ", " i9 ", " ryzen "]
        )
    listing_cpus = _cpu_tokens(title)
    if not listing_cpus:
        return False
    target_key = re.sub(r"[^a-z0-9]+", "", target_cpu.lower())
    if not target_key:
        return False
    target_without_suffix = target_key[:-1] if target_key[-1:].isalpha() and any(char.isdigit() for char in target_key) else target_key
    return not any(
        cpu == target_key
        or cpu == target_without_suffix
        or cpu.startswith(target_key)
        or cpu.startswith(target_without_suffix)
        for cpu in listing_cpus
    )


def _has_conflicting_carrier(title: str, target_specs: dict[str, Any]) -> bool:
    target_carrier = str(target_specs.get("carrier") or "").strip().lower()
    if target_carrier != "unlocked":
        return False
    title_text = _normalized_text(title)
    if " unlocked " in title_text or " fully unlocked " in title_text:
        return False
    locked_markers = [
        " locked ",
        " at t ",
        " att ",
        " verizon ",
        " t mobile ",
        " tmobile ",
        " sprint ",
        " cricket ",
        " rogers ",
        " bell ",
        " telus ",
    ]
    return any(marker in title_text for marker in locked_markers)


def _brand_key(value: Any) -> str:
    return str(value or "").strip().lower()


def _brand_present(title_text: str, brand: str) -> bool:
    if brand == "hp":
        return " hp " in title_text or " hewlett packard " in title_text
    if brand == "wd":
        return " wd " in title_text
    if brand == "western digital":
        return " western digital " in title_text
    return f" {brand} " in title_text


def _model_tokens(value: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", value.lower())
    return [token for token in tokens if token not in GENERIC_MODEL_TOKENS and token not in {"gb", "tb", "ssd", "hdd"}]


def _numeric_model_tokens(tokens: list[str]) -> set[str]:
    return {token for token in tokens if re.fullmatch(r"\d{2,5}[a-z]?", token)}


def _generation_number(text: str) -> str | None:
    match = re.search(r"\bgen\s+(\d{1,2})\b", text)
    return match.group(1) if match else None


def _iphone_model_number(text: str) -> str | None:
    match = re.search(r"\biphone\s+(\d{1,2})(?:\s|$)", text)
    return match.group(1) if match else None


def _model_context_present(title_text: str, target_specs: dict[str, Any], target_tokens: list[str]) -> bool:
    brand = _brand_key(target_specs.get("brand"))
    return (
        (brand and _brand_present(title_text, brand))
        or any(token in title_text for token in target_tokens if len(token) >= 3)
    )


def _target_storage_gb(target_specs: dict[str, Any]) -> int:
    storage = target_specs.get("storage")
    if isinstance(storage, list):
        sizes = [
            _safe_int(drive.get("size_gb"))
            for drive in storage
            if isinstance(drive, dict) and _safe_int(drive.get("size_gb")) > 0
        ]
        if sizes:
            return max(sizes)
    for key in ["storage_capacity", "capacity"]:
        parsed = _capacity_text_gb(target_specs.get(key))
        if parsed:
            return parsed
    return 0


def _ram_values_gb(title: str) -> set[int]:
    values = set()
    lowered = title.lower()
    for match in re.finditer(r"(\d+)\s*gb\s*(?:ram|memory|ddr\d?)\b|\b(?:ram|memory)\s*:?\s*(\d+)\s*gb\b", lowered):
        value = match.group(1) or match.group(2)
        if value:
            values.add(int(value))
    for match in re.finditer(r"\b(\d+)\s*gb\b(?!\s*(?:ssd|hdd|nvme|emmc|solid\s+state|hard\s+drive))", lowered):
        value = int(match.group(1))
        if value <= 128:
            values.add(value)
    return values


def _cpu_tokens(title: str) -> set[str]:
    tokens = set()
    lowered = title.lower()
    patterns = [
        r"\bi[3579][-\s]?(\d{4,5}[a-z0-9]{0,3})\b",
        r"\bcore\s+i[3579][-\s]?(\d{4,5}[a-z0-9]{0,3})\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, lowered):
            prefix_match = re.search(r"\bi([3579])", match.group(0))
            if prefix_match:
                tokens.add(f"i{prefix_match.group(1)}{match.group(1)}")
    return {re.sub(r"[^a-z0-9]+", "", token) for token in tokens}


def _apple_silicon_token(value: Any) -> str | None:
    text = str(value or "").lower()
    match = re.search(r"\bm([1-4])(?:\s+(pro|max|ultra))?\b", text)
    if not match:
        return None
    suffix = match.group(2) or ""
    return f"m{match.group(1)}{suffix}"


def _capacity_text_gb(value: Any) -> int:
    text = str(value or "").strip().lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*(tb|gb|g)\b", text)
    if not match:
        return 0
    amount = float(match.group(1))
    return int(amount * 1024) if match.group(2) == "tb" else int(amount)


def _normalized_text(value: Any) -> str:
    return f" {re.sub(r'[^a-z0-9]+', ' ', str(value or '').lower()).strip()} "


def _safe_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed


def _looks_like_variant_mismatch(
    listing: dict[str, Any],
    device_type: str | None = None,
    target_specs: dict[str, Any] | None = None,
) -> bool:
    if not isinstance(target_specs, dict):
        return False

    clean_device_type = _clean_device_type(device_type or target_specs.get("device_type"))
    title = str(listing.get("title") or "").lower()
    if not title:
        return False

    if clean_device_type in DEVICE_VARIANT_PATTERNS and _has_conflicting_variant(
        title,
        clean_device_type,
        target_specs,
    ):
        return True

    return _has_conflicting_screen_size(title, target_specs)


def _has_conflicting_variant(
    title: str,
    device_type: str,
    target_specs: dict[str, Any],
) -> bool:
    target_text = " ".join(
        str(part)
        for part in [
            target_specs.get("model"),
            target_specs.get("search_model"),
            target_specs.get("variant"),
        ]
        if part
    ).lower()
    if not target_text:
        return False

    target_variants = _detected_variants(target_text, device_type)
    listing_variants = _detected_variants(title, device_type)

    if not target_variants:
        return bool(listing_variants)

    return target_variants != listing_variants


def _detected_variants(text: str, device_type: str) -> set[str]:
    text = _variant_detection_text(text)
    variants = set()
    for variant, patterns in DEVICE_VARIANT_PATTERNS.get(device_type, {}).items():
        if any(re.search(pattern, text) for pattern in patterns):
            variants.add(variant)

    if "pro max" in variants:
        variants.discard("pro")
        variants.discard("max")
    return variants


def _variant_detection_text(text: str) -> str:
    clean = text.lower()
    protected_phrases = [
        r"\bwindows\s+(?:10|11)\s+pro(?:fessional)?\b",
        r"\bwin(?:dows)?\s*(?:10|11)\s+pro(?:fessional)?\b",
        r"\boffice\s+(?:pro|professional)(?:\s+plus)?\b",
    ]
    for phrase in protected_phrases:
        clean = re.sub(phrase, " ", clean)
    return clean


def _has_conflicting_screen_size(title: str, target_specs: dict[str, Any]) -> bool:
    target_size = _screen_size_number(target_specs.get("screen_size"))
    if not target_size:
        return False

    listing_sizes = set()
    for match in re.finditer(r'(?<![\d.])(\d{1,2}(?:\.\d)?)\s*-?\s*(?:"|inch(?:es)?\b|in\b)', title):
        listing_size = _screen_size_number(match.group(1))
        if listing_size:
            listing_sizes.add(listing_size)

    if not listing_sizes:
        return False
    return target_size not in listing_sizes


def _screen_size_number(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    text = re.sub(r'\s*(inch(?:es)?|in|")\s*$', "", text).strip()
    try:
        number = float(text)
    except ValueError:
        return None
    return f"{number:g}"


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
