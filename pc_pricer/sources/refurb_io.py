"""Refurb.io Canada listing source."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import json
import re
from typing import Any, Callable
from urllib import error, parse, request

from pc_pricer import __version__


DEFAULT_BASE_URL = "https://ca.refurb.io"
SEARCH_PATH = "/search/suggest.json"

HtmlHttpGet = Callable[[str, dict[str, str]], str]
JsonHttpGet = Callable[[str, dict[str, str]], dict[str, Any]]


@dataclass
class ParsedProduct:
    title: str
    item_price_cad: float | None
    available: bool | None
    condition_raw: str | None
    specs: dict[str, Any]
    shipping_cad: float | None
    shipping_is_estimated: bool
    sku: str | None


class RefurbIoSource:
    name = "refurb_io"

    def __init__(
        self,
        enabled: bool = True,
        base_url: str = DEFAULT_BASE_URL,
        http_get: HtmlHttpGet | None = None,
        json_get: JsonHttpGet | None = None,
    ) -> None:
        self.enabled = enabled
        self.base_url = base_url.rstrip("/")
        self._base_host = _validated_base_host(self.base_url)
        self._http_get = http_get or _http_get_text
        self._json_get = json_get or _http_get_json

    def search(self, query: str, max_results: int) -> list[dict[str, Any]]:
        """Search Refurb.io Canada and return standardized listings."""
        if not self.enabled:
            return []

        urls = self._search_product_urls(query, max_results)
        listings = []
        for url in urls[:max_results]:
            try:
                html = self._http_get(url, _headers())
            except RuntimeError:
                continue
            product = parse_product_html(html)
            listing = _listing_from_product(product, url)
            if listing:
                listings.append(listing)
        return listings

    def _search_product_urls(self, query: str, max_results: int) -> list[str]:
        params = {
            "q": query,
            "resources[type]": "product",
            "resources[limit]": str(max_results),
            "resources[options][unavailable_products]": "last",
        }
        url = f"{self.base_url}{SEARCH_PATH}?{parse.urlencode(params)}"
        payload = self._json_get(url, _headers())
        products = (((payload.get("resources") or {}).get("results") or {}).get("products") or [])

        urls = []
        for product in products:
            if not isinstance(product, dict):
                continue
            product_url = product.get("url")
            if not product_url:
                continue
            absolute_url = _absolute_url(str(product_url), self.base_url, self._base_host)
            if absolute_url:
                urls.append(absolute_url)
        return _dedupe_urls(urls)


def parse_product_html(html: str) -> ParsedProduct:
    """Parse a Refurb.io product page into source-native fields."""
    parser = _ProductHtmlParser()
    parser.feed(html)

    json_products = _json_products(parser.json_ld)
    title = (
        _meta_value(parser.metas, "og:title")
        or _first_value(json_products, "name")
        or parser.h1_text()
        or ""
    )
    text_lines = parser.text_lines()
    full_text = "\n".join(text_lines)
    specs = _product_specs(text_lines, full_text, title)
    condition = specs.get("condition") or _condition_from_title(title)
    price = (
        _meta_money(parser.metas, "product:price:amount")
        or _json_price(json_products)
        or _fallback_price(full_text)
    )
    available = _availability(json_products, full_text)
    shipping_cad, shipping_is_estimated = _shipping(full_text)

    return ParsedProduct(
        title=title,
        item_price_cad=price,
        available=available,
        condition_raw=condition,
        specs=specs,
        shipping_cad=shipping_cad,
        shipping_is_estimated=shipping_is_estimated,
        sku=_first_value(json_products, "sku") or _labeled_value(text_lines, ["SKU"]),
    )


def _listing_from_product(product: ParsedProduct, url: str) -> dict[str, Any] | None:
    if product.item_price_cad is None:
        return None

    shipping = product.shipping_cad
    total_price = product.item_price_cad + (shipping or 0.0)
    return {
        "source": "refurb_io",
        "item_id": product.sku,
        "title": product.title,
        "item_price_cad": product.item_price_cad,
        "shipping_cad": shipping,
        "total_price_cad": round(total_price, 2),
        "shipping_is_estimated": product.shipping_is_estimated,
        "condition_raw": product.condition_raw,
        "condition_norm": None,
        "url": url,
        "location": "Canada",
        "is_sold": False,
        "available": product.available,
        "availability": _availability_label(product.available),
        "source_specs": product.specs,
        "shipping_assumption": "free_delivery" if shipping == 0 else "unknown",
    }


class _ProductHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.metas: dict[str, str] = {}
        self.json_ld: list[str] = []
        self._script_type: str | None = None
        self._script_parts: list[str] = []
        self._h1_depth = 0
        self._h1_parts: list[str] = []
        self._texts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value for key, value in attrs if value is not None}
        if tag.lower() == "meta":
            key = attrs_dict.get("property") or attrs_dict.get("name")
            content = attrs_dict.get("content")
            if key and content:
                self.metas[key.lower()] = content.strip()
        elif tag.lower() == "script":
            self._script_type = (attrs_dict.get("type") or "").lower()
            self._script_parts = []
        elif tag.lower() == "h1":
            self._h1_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script":
            if self._script_type == "application/ld+json":
                text = "".join(self._script_parts).strip()
                if text:
                    self.json_ld.append(text)
            self._script_type = None
            self._script_parts = []
        elif tag.lower() == "h1" and self._h1_depth:
            self._h1_depth -= 1

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split()).strip()
        if not text:
            return
        if self._script_type:
            self._script_parts.append(data)
            return
        if self._h1_depth:
            self._h1_parts.append(text)
        self._texts.append(text)

    def h1_text(self) -> str | None:
        text = " ".join(self._h1_parts).strip()
        return text or None

    def text_lines(self) -> list[str]:
        return self._texts


def _product_specs(lines: list[str], full_text: str, title: str) -> dict[str, Any]:
    specs: dict[str, Any] = {}
    values = {
        "brand": _labeled_value(lines, ["Brand"]),
        "model": _labeled_value(lines, ["Model"]),
        "memory": _labeled_value(lines, ["Memory", "RAM"]),
        "storage": _labeled_value(lines, ["Storage", "Hard Drive"]),
        "processor": _labeled_value(lines, ["Processor", "Processor Type", "CPU"]),
        "condition": _labeled_value(lines, ["Condition"]),
        "screen_size": _labeled_value(lines, ["Screen Size"]),
    }
    for key, value in values.items():
        if value:
            specs[key] = value

    memory_gb = _gb_number(specs.get("memory") or title)
    storage_gb = _storage_gb(specs.get("storage") or title)
    cpu_short = _cpu_short(specs.get("processor") or title)
    if memory_gb:
        specs["ram_gb"] = memory_gb
    if storage_gb:
        specs["storage_gb"] = storage_gb
    if cpu_short:
        specs["cpu_short"] = cpu_short
    if not specs.get("brand"):
        specs["brand"] = _brand_from_title(title or full_text)
    return specs


def _labeled_value(lines: list[str], labels: list[str]) -> str | None:
    label_keys = {label.lower() for label in labels}
    for index, line in enumerate(lines):
        clean = line.strip()
        lowered = clean.lower()
        for label in label_keys:
            if lowered == label:
                return _next_value(lines, index + 1, label_keys)
            if lowered.startswith(f"{label}:"):
                return clean.split(":", 1)[1].strip() or None
            if lowered.startswith(f"{label} |"):
                return clean.split("|", 1)[1].strip() or None
    return None


def _next_value(lines: list[str], start: int, labels: set[str]) -> str | None:
    for line in lines[start:]:
        clean = line.strip()
        if not clean:
            continue
        if clean.lower() in labels:
            return None
        return clean
    return None


def _condition_from_title(title: str) -> str | None:
    match = re.search(r"refurbished\s*\(([^)]+)\)", title, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    if "refurbished" in title.lower():
        return "Refurbished"
    return None


def _availability(json_products: list[dict[str, Any]], text: str) -> bool | None:
    for product in json_products:
        offers = product.get("offers")
        for offer in _as_list(offers):
            availability = str(offer.get("availability") or "").lower()
            if "instock" in availability:
                return True
            if "outofstock" in availability or "soldout" in availability:
                return False

    lowered = text.lower()
    if re.search(r"\b(sold out|out of stock|unavailable)\b", lowered):
        return False
    if re.search(r"\b(in stock|ready to be shipped|add to cart)\b", lowered):
        return True
    return None


def _shipping(text: str) -> tuple[float | None, bool]:
    lowered = text.lower()
    if "free delivery" in lowered or "free shipping" in lowered:
        return 0.0, False
    return None, True


def _json_products(json_ld: list[str]) -> list[dict[str, Any]]:
    products = []
    for text in json_ld:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        for item in _walk_json(payload):
            if isinstance(item, dict) and str(item.get("@type") or "").lower() == "product":
                products.append(item)
    return products


def _walk_json(value: Any) -> list[Any]:
    if isinstance(value, list):
        items = []
        for item in value:
            items.extend(_walk_json(item))
        return items
    if isinstance(value, dict):
        items = [value]
        for item in value.values():
            items.extend(_walk_json(item))
        return items
    return []


def _json_price(products: list[dict[str, Any]]) -> float | None:
    prices = []
    for product in products:
        for offer in _as_list(product.get("offers")):
            for key in ["price", "lowPrice"]:
                price = _money(offer.get(key))
                if price is not None:
                    prices.append(price)
    return min(prices) if prices else None


def _fallback_price(text: str) -> float | None:
    prices = [_money(match.group(1)) for match in re.finditer(r"\$\s*([0-9][0-9,]*(?:\.\d{2})?)", text)]
    prices = [price for price in prices if price is not None and price >= 50]
    return min(prices) if prices else None


def _meta_value(metas: dict[str, str], key: str) -> str | None:
    return metas.get(key.lower())


def _meta_money(metas: dict[str, str], key: str) -> float | None:
    return _money(_meta_value(metas, key))


def _first_value(products: list[dict[str, Any]], key: str) -> str | None:
    for product in products:
        value = product.get(key)
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    return None


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _money(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    try:
        return round(float(text), 2)
    except ValueError:
        return None


def _gb_number(value: Any) -> int | None:
    text = str(value or "")
    match = re.search(r"(\d+)\s*GB", text, flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def _storage_gb(value: Any) -> int | None:
    text = str(value or "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*(TB|GB)", text, flags=re.IGNORECASE)
    if not match:
        return None
    size = float(match.group(1))
    unit = match.group(2).lower()
    return int(size * 1024) if unit == "tb" else int(size)


def _cpu_short(value: Any) -> str | None:
    text = str(value or "")
    patterns = [
        r"\bcore\s+ultra\s+\d\s+\d{3}[a-z]?\b",
        r"\bi[3579]\s*[- ]?\d{3,5}[a-z0-9]{0,4}\b",
        r"\bm[1234](?:\s+(?:pro|max|ultra))?\b",
        r"\bryzen\s*\d\s*[- ]?\d{3,5}[a-z0-9]{0,4}\b",
        r"\bxeon\s+\w[-\w]*\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return re.sub(r"\s+", " ", match.group(0)).strip()
    return None


def _brand_from_title(title: str) -> str | None:
    for brand in [
        "Lenovo",
        "Dell",
        "HP",
        "Apple",
        "Acer",
        "Asus",
        "Samsung",
        "Microsoft",
        "Toshiba",
        "MSI",
        "LG",
        "Razer",
        "Google",
    ]:
        if re.search(rf"\b{re.escape(brand)}\b", title, flags=re.IGNORECASE):
            return brand
    return None


def _availability_label(available: bool | None) -> str:
    if available is True:
        return "in_stock"
    if available is False:
        return "out_of_stock"
    return "unknown"


def _absolute_url(url: str, base_url: str, base_host: str) -> str | None:
    absolute = parse.urljoin(f"{base_url}/", url)
    parsed = parse.urlparse(absolute)
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.hostname != base_host:
        return None
    return absolute


def _validated_base_host(base_url: str) -> str:
    parsed = parse.urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Refurb.io base_url must be an HTTP(S) URL with a host.")
    return parsed.hostname


def _dedupe_urls(urls: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for url in urls:
        key = url.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(url)
    return deduped


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
        "User-Agent": f"CFS-Price-Compare/{__version__}",
    }


def _http_get_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    text = _http_get_text(url, headers)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Refurb.io search response was not valid JSON.") from exc


def _http_get_text(url: str, headers: dict[str, str]) -> str:
    req = request.Request(url, headers=headers, method="GET")
    try:
        with request.urlopen(req, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        raise RuntimeError(f"Refurb.io request failed with HTTP {exc.code}.") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Refurb.io request failed: {exc.reason}") from exc
