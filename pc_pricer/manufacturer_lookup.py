"""Best-effort manufacturer model-number lookup for computer specs."""

from __future__ import annotations

from html import unescape
import json
import re
from typing import Any, Callable
from urllib.parse import quote_plus
from urllib.request import Request, urlopen


ManufacturerFetcher = Callable[[str], str]


BRAND_DOMAINS = {
    "acer": ["acer.com"],
    "apple": ["support.apple.com", "apple.com"],
    "asus": ["asus.com"],
    "dell": ["dell.com"],
    "dynabook": ["dynabook.com"],
    "fujitsu": ["fujitsu.com"],
    "gateway": ["gateway.com"],
    "hp": ["support.hp.com", "partsurfer.hp.com", "hp.com"],
    "lenovo": ["psref.lenovo.com", "pcsupport.lenovo.com", "lenovo.com"],
    "lg": ["lg.com"],
    "microsoft": ["support.microsoft.com", "microsoft.com"],
    "msi": ["msi.com"],
    "panasonic": ["panasonic.com"],
    "samsung": ["samsung.com"],
    "toshiba": ["support.dynabook.com", "toshiba.com"],
}

FORM_FACTOR_MARKERS = {
    "all-in-one": [" all in one ", " all-in-one ", " aio "],
    "laptop": [
        " laptop ",
        " notebook ",
        " ultrabook ",
        " thinkpad ",
        " elitebook ",
        " probook ",
        " latitude ",
        " xps 13 ",
        " xps 15 ",
        " macbook ",
        " surface laptop ",
    ],
    "desktop": [
        " desktop ",
        " tower ",
        " small form factor ",
        " sff ",
        " micro form factor ",
        " optiplex ",
        " thinkcentre ",
        " elitedesk ",
        " prodesk ",
        " imac ",
        " mac mini ",
    ],
}

MODEL_LABELS = [
    "product name",
    "product",
    "model name",
    "marketing name",
    "machine type model",
    "mtm",
    "series",
]

CPU_LABELS = ["processor", "cpu", "processor type"]
RAM_LABELS = ["memory", "standard memory", "installed memory", "ram"]
STORAGE_LABELS = ["storage", "hard drive", "ssd", "drive", "primary storage"]


def lookup_manufacturer_specs(
    specs: dict[str, Any],
    identifier: str,
    fetcher: ManufacturerFetcher | None = None,
    max_pages: int = 4,
    timeout_seconds: float = 8.0,
) -> dict[str, Any] | None:
    """Return a high-confidence manufacturer lookup candidate, or None."""
    brand = _clean(specs.get("brand"))
    if not identifier or not brand:
        return None

    urls = manufacturer_lookup_urls(brand, identifier)
    if not urls:
        return None

    fetch = fetcher or (lambda url: _fetch_url(url, timeout_seconds=timeout_seconds))
    candidates = []
    errors = []
    for url in urls[: max(1, max_pages)]:
        try:
            html = fetch(url)
        except Exception as exc:  # pragma: no cover - network boundary.
            errors.append({"url": url, "message": str(exc)})
            continue
        candidate = candidate_from_manufacturer_page(html, brand, identifier, url)
        if candidate:
            candidates.append(candidate)

    if not candidates:
        return None

    best = max(candidates, key=lambda candidate: candidate["score"])
    if best["score"] < 8:
        return None
    best["queries"] = urls[: max(1, max_pages)]
    if errors:
        best["errors"] = errors
    return best


def manufacturer_lookup_urls(brand: str, identifier: str) -> list[str]:
    """Return official/support search URLs for the brand and identifier."""
    brand_key = _brand_key(brand)
    query = quote_plus(identifier)
    brand_query = quote_plus(f"{brand} {identifier}")
    urls: list[str] = []

    if brand_key == "lenovo":
        urls.extend(
            [
                f"https://psref.lenovo.com/Search?kw={query}",
                f"https://pcsupport.lenovo.com/search?query={query}",
            ]
        )
    elif brand_key == "hp":
        urls.extend(
            [
                f"https://partsurfer.hp.com/partsurfer?searchtext={query}",
                f"https://support.hp.com/ca-en/search?q={query}",
            ]
        )
    elif brand_key == "dell":
        urls.extend(
            [
                f"https://www.dell.com/support/search/en-ca#q={query}",
                f"https://www.dell.com/support/home/en-ca/product-support/servicetag/{query}/overview",
            ]
        )
    elif brand_key == "apple":
        urls.extend(
            [
                f"https://support.apple.com/search?query={brand_query}",
                f"https://www.apple.com/search/{query}",
            ]
        )
    elif brand_key == "microsoft":
        urls.append(f"https://support.microsoft.com/search/results?query={brand_query}")

    domains = BRAND_DOMAINS.get(brand_key, [f"{brand_key}.com"])
    for domain in domains:
        if domain.startswith(("support.", "psref.", "pcsupport.", "partsurfer.")):
            urls.append(f"https://{domain}/search?q={query}")
        elif domain.startswith("www."):
            urls.append(f"https://{domain}/search?q={query}")
            urls.append(f"https://support.{domain[4:]}/search?q={query}")
        else:
            urls.append(f"https://www.{domain}/search?q={query}")
            urls.append(f"https://support.{domain}/search?q={query}")
    return _dedupe(urls)


def candidate_from_manufacturer_page(
    html: str,
    brand: str,
    identifier: str,
    url: str,
) -> dict[str, Any] | None:
    """Parse one manufacturer page/search result into an enriched-spec candidate."""
    if not html:
        return None

    title = _page_title(html)
    labels = _labeled_values(html)
    text = _normalized_text(" ".join([title, _html_text(html), " ".join(labels.values())]))
    if not _identifier_in_text(identifier, text):
        return None
    if brand and not _all_tokens_present(text, brand):
        return None

    specs = _canonical_specs(title, labels, text, brand)
    score = 0
    score += 5
    score += 3 if brand else 0
    if specs.get("search_model"):
        score += 2
    for key in ["form_factor", "cpu_short", "ram_gb"]:
        if specs.get(key):
            score += 1
    if specs.get("storage"):
        score += 1

    return {
        "source": f"manufacturer:{_brand_key(brand)}",
        "title": title or specs.get("search_model") or identifier,
        "url": url,
        "score": score,
        "confidence": _confidence_label(score),
        "enriched_specs": specs,
    }


def _canonical_specs(
    title: str,
    labels: dict[str, str],
    text: str,
    brand: str,
) -> dict[str, Any]:
    model = _first_labeled_value(labels, MODEL_LABELS) or _model_from_title(title, brand)
    cpu = _first_labeled_value(labels, CPU_LABELS) or _cpu_from_text(text)
    ram_gb = _ram_gb(_first_labeled_value(labels, RAM_LABELS) or text)
    storage = _storage_from_text(_first_labeled_value(labels, STORAGE_LABELS) or text)
    form_factor = _form_factor_from_text(" ".join([title, text, model or ""]))
    specs = {
        "device_type": "computer",
        "brand": brand,
        "search_model": model,
        "form_factor": form_factor,
        "cpu_short": _cpu_short(cpu),
        "cpu": cpu,
        "ram_gb": ram_gb,
        "storage": storage,
    }
    return {key: value for key, value in specs.items() if value not in (None, "", [], 0)}


def _labeled_values(html: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)

    row_pattern = re.compile(
        r"(?is)<tr[^>]*>\s*<(?:th|td)[^>]*>(.*?)</(?:th|td)>\s*<td[^>]*>(.*?)</td>\s*</tr>"
    )
    for label, value in row_pattern.findall(html):
        _add_label(labels, label, value)

    dt_pattern = re.compile(r"(?is)<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>")
    for label, value in dt_pattern.findall(html):
        _add_label(labels, label, value)

    json_pattern = re.compile(r'(?is)<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>')
    for payload in json_pattern.findall(html):
        for label, value in _json_ld_values(payload).items():
            labels.setdefault(label, value)

    text = _html_text(html)
    for label in [*MODEL_LABELS, *CPU_LABELS, *RAM_LABELS, *STORAGE_LABELS]:
        match = re.search(rf"\b{re.escape(label)}\b\s*[:\-]\s*([^|\n\r]+)", text, flags=re.IGNORECASE)
        if match:
            labels.setdefault(_label_key(label), _clean(match.group(1)) or "")
    return {key: value for key, value in labels.items() if value}


def _add_label(labels: dict[str, str], label: str, value: str) -> None:
    key = _label_key(_html_text(label))
    clean_value = _clean(_html_text(value))
    if key and clean_value:
        labels.setdefault(key, clean_value)


def _json_ld_values(payload: str) -> dict[str, str]:
    try:
        parsed = json.loads(unescape(payload.strip()))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    values: dict[str, str] = {}
    for item in _flatten_json_ld(parsed):
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name"))
        model = _clean(item.get("model"))
        brand = item.get("brand")
        if isinstance(brand, dict):
            brand = brand.get("name")
        brand_text = _clean(brand)
        if name:
            values.setdefault("product name", name)
        if model:
            values.setdefault("model name", model)
        if brand_text:
            values.setdefault("brand", brand_text)
    return values


def _flatten_json_ld(value: Any) -> list[Any]:
    if isinstance(value, list):
        flattened = []
        for item in value:
            flattened.extend(_flatten_json_ld(item))
        return flattened
    if isinstance(value, dict) and isinstance(value.get("@graph"), list):
        return _flatten_json_ld(value["@graph"])
    return [value]


def _first_labeled_value(labels: dict[str, str], wanted: list[str]) -> str | None:
    for label in wanted:
        value = labels.get(_label_key(label))
        if value:
            return value
    return None


def _page_title(html: str) -> str:
    for pattern in [r"(?is)<h1[^>]*>(.*?)</h1>", r"(?is)<title[^>]*>(.*?)</title>"]:
        match = re.search(pattern, html)
        if match:
            title = _clean(_html_text(match.group(1)))
            if title:
                return title
    return ""


def _model_from_title(title: str, brand: str) -> str | None:
    clean_title = _clean(title)
    if not clean_title:
        return None
    text = re.split(r"\s[|-]\s| - support\b| specifications\b| specs\b", clean_title, maxsplit=1, flags=re.IGNORECASE)[0]
    text = re.sub(r"\b(?:laptop|notebook|desktop|all-in-one|specifications|support)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:intel|core|amd|ryzen)\b.*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d+\s*(?:gb|tb)\b.*$", "", text, flags=re.IGNORECASE)
    if brand:
        text = re.sub(rf"^\s*{re.escape(brand)}\s+", "", text, flags=re.IGNORECASE)
    return _clean(text)


def _form_factor_from_text(value: str) -> str | None:
    text = _normalized_text(value)
    for form_factor, markers in FORM_FACTOR_MARKERS.items():
        if any(marker in text for marker in markers):
            return form_factor
    return None


def _cpu_from_text(value: str) -> str | None:
    match = re.search(
        r"\b((?:Intel\s+)?(?:Core\s+)?i[3579][-\s]?\d{4,5}[A-Za-z0-9]{0,3}|(?:AMD\s+)?Ryzen\s+[3579]\s+\d{4,5}[A-Za-z0-9]{0,3})\b",
        value,
        flags=re.IGNORECASE,
    )
    return _clean(match.group(1)) if match else None


def _cpu_short(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"\b(i[3579][-\s]?\d{4,5}[A-Za-z0-9]{0,3}|Ryzen\s+[3579]\s+\d{4,5}[A-Za-z0-9]{0,3})\b", value, flags=re.IGNORECASE)
    if not match:
        return _clean(value)
    short = re.sub(r"\s+", " ", match.group(1)).strip()
    short = re.sub(r"^(I)([3579])", r"i\2", short, flags=re.IGNORECASE)
    return short


def _ram_gb(value: str) -> int:
    match = re.search(r"\b(\d{1,3})\s*GB\b(?=.{0,30}\b(?:RAM|memory|DDR)\b)|\b(?:RAM|memory)\b.{0,30}\b(\d{1,3})\s*GB\b", value, flags=re.IGNORECASE)
    if not match:
        return 0
    return _safe_int(match.group(1) or match.group(2))


def _storage_from_text(value: str) -> list[dict[str, Any]]:
    match = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(TB|GB)\b.{0,35}?\b(NVMe|SSD|HDD|hard drive|eMMC)\b|\b(NVMe|SSD|HDD|hard drive|eMMC)\b.{0,35}?\b(\d+(?:\.\d+)?)\s*(TB|GB)\b",
        value,
        flags=re.IGNORECASE,
    )
    if not match:
        return []
    if match.group(1):
        amount = float(match.group(1))
        unit = match.group(2)
        drive_type = match.group(3)
    else:
        drive_type = match.group(4)
        amount = float(match.group(5))
        unit = match.group(6)
    size_gb = int(amount * 1024) if str(unit).lower() == "tb" else int(amount)
    return [{"size_gb": size_gb, "type": _drive_type(drive_type)}]


def _drive_type(value: str | None) -> str:
    text = str(value or "").lower()
    if "nvme" in text:
        return "NVMe"
    if "emmc" in text:
        return "eMMC"
    if "hdd" in text or "hard drive" in text:
        return "HDD"
    return "SSD"


def _fetch_url(url: str, timeout_seconds: float) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "CFS-Price-Compare/1.0 (+https://github.com/) Python urllib",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        data = response.read(1_000_000)
        charset = response.headers.get_content_charset() or "utf-8"
    return data.decode(charset, errors="replace")


def _html_text(value: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", value or "")
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _normalized_text(value: Any) -> str:
    return f" {re.sub(r'[^a-z0-9]+', ' ', str(value or '').lower()).strip()} "


def _identifier_in_text(identifier: str, text: str) -> bool:
    compact_identifier = re.sub(r"[^a-z0-9]+", "", identifier.lower())
    compact_text = re.sub(r"[^a-z0-9]+", "", text.lower())
    return bool(compact_identifier and compact_identifier in compact_text)


def _all_tokens_present(text: str, value: str) -> bool:
    tokens = re.findall(r"[a-z0-9]+", value.lower())
    return all(token in text for token in tokens)


def _brand_key(brand: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(brand or "").lower())


def _label_key(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())).strip()


def _confidence_label(score: int) -> str:
    if score >= 11:
        return "high"
    if score >= 8:
        return "medium"
    return "low"


def _dedupe(values: list[str]) -> list[str]:
    deduped = []
    seen = set()
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def _safe_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0
