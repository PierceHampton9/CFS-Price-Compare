"""Amazon Renewed source backed by optional Playwright automation."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import re
from typing import Any, Callable
from urllib import parse

DEFAULT_BASE_URL = "https://www.amazon.ca"

HtmlFetcher = Callable[[str], str]


@dataclass
class AmazonCandidate:
    title: str
    item_price_cad: float | None
    url: str
    available: bool | None
    condition_raw: str | None
    shipping_cad: float | None
    shipping_is_estimated: bool
    prime_signal: bool | None
    asin: str | None = None
    source_specs: dict[str, Any] | None = None


class AmazonRenewedSource:
    name = "amazon_renewed"

    def __init__(
        self,
        enabled: bool = True,
        base_url: str = DEFAULT_BASE_URL,
        browser: str = "chromium",
        channel: str | None = "msedge",
        headless: bool = True,
        timeout_ms: int = 15000,
        max_product_pages: int = 5,
        page_fetcher: HtmlFetcher | None = None,
    ) -> None:
        self.enabled = enabled
        self.base_url = base_url.rstrip("/")
        self._base_host = _validated_base_host(self.base_url)
        self.browser = browser
        self.channel = channel.strip() if isinstance(channel, str) and channel.strip() else None
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.max_product_pages = max_product_pages
        self._page_fetcher = page_fetcher
        self.last_search_stats: dict[str, Any] = {}

    def search(self, query: str, max_results: int) -> list[dict[str, Any]]:
        """Search Amazon.ca Renewed with Playwright and return standardized listings."""
        if not self.enabled:
            return []

        if self._page_fetcher is not None:
            return self._search_with_fetcher(query, max_results, self._page_fetcher)
        return self._search_with_browser(query, max_results)

    def _search_with_fetcher(self, query: str, max_results: int, fetcher: HtmlFetcher) -> list[dict[str, Any]]:
        search_url = self._search_url(query)
        self.last_search_stats = {
            "search_url": search_url,
            "search_urls": [],
            "candidate_count": 0,
            "detail_page_count": 0,
            "detail_urls": [],
            "detail_error_count": 0,
        }

        listings = []
        fetched_detail_urls: set[str] = set()
        seen_listing_urls: set[str] = set()
        for current_search_url in self._search_urls(query):
            search_detail_fetches = 0
            self.last_search_stats["search_urls"].append(current_search_url)
            search_html = fetcher(current_search_url)
            if _looks_like_blocked_page(search_html):
                raise RuntimeError(
                    "Amazon Renewed search returned a robot-check, captcha, or interstitial page instead of results."
                )
            candidates = parse_search_results(search_html, self.base_url, self._base_host)
            candidates = _rank_search_candidates(candidates, query)
            self.last_search_stats["candidate_count"] += len(candidates)

            for candidate in candidates:
                if candidate.url in seen_listing_urls:
                    continue

                enriched = candidate
                if search_detail_fetches < self.max_product_pages and candidate.url not in fetched_detail_urls:
                    fetched_detail_urls.add(candidate.url)
                    search_detail_fetches += 1
                    self.last_search_stats["detail_page_count"] += 1
                    self.last_search_stats["detail_urls"].append(candidate.url)
                    try:
                        detail_html = fetcher(candidate.url)
                    except Exception:
                        detail_html = ""
                        self.last_search_stats["detail_error_count"] += 1
                    if detail_html:
                        enriched = _merge_candidate(candidate, parse_product_page(detail_html, candidate.url))
                listing = _listing_from_candidate(enriched)
                if listing:
                    seen_listing_urls.add(candidate.url)
                    listings.append(listing)
                if len(listings) >= max_results:
                    return listings
        return listings

    def _search_url(self, query: str, *, renewed_department: bool = True) -> str:
        params = {
            "k": query,
        }
        if renewed_department:
            params["i"] = "amazon-renewed"
        return f"{self.base_url}/s?{parse.urlencode(params)}"

    def _search_urls(self, query: str) -> list[str]:
        renewed_url = self._search_url(query, renewed_department=True)
        broad_url = self._search_url(query, renewed_department=False)
        return [renewed_url, broad_url]

    def _search_with_browser(self, query: str, max_results: int) -> list[dict[str, Any]]:
        def run(page: Any) -> list[dict[str, Any]]:
            return self._search_with_page(query, max_results, page)

        return self._with_playwright_page(run)

    def _search_with_page(self, query: str, max_results: int, page: Any) -> list[dict[str, Any]]:
        search_url = self._search_url(query)
        self.last_search_stats = {
            "search_url": search_url,
            "search_urls": [],
            "candidate_count": 0,
            "detail_page_count": 0,
            "detail_urls": [],
            "detail_error_count": 0,
        }

        listings = []
        fetched_detail_urls: set[str] = set()
        seen_listing_urls: set[str] = set()
        for current_search_url in self._search_urls(query):
            search_detail_fetches = 0
            self.last_search_stats["search_urls"].append(current_search_url)
            _load_page(page, current_search_url, self.timeout_ms)
            _scroll_search_results(page)
            search_html = page.content()
            if _looks_like_blocked_page(search_html):
                raise RuntimeError(
                    "Amazon Renewed search returned a robot-check, captcha, or interstitial page instead of results."
                )

            candidates = extract_search_candidates_from_page(page, self.base_url, self._base_host)
            if not candidates:
                candidates = parse_search_results(search_html, self.base_url, self._base_host)
            candidates = _rank_search_candidates(candidates, query)
            self.last_search_stats["candidate_count"] += len(candidates)

            for candidate in candidates:
                if candidate.url in seen_listing_urls:
                    continue

                enriched = candidate
                if search_detail_fetches < self.max_product_pages and candidate.url not in fetched_detail_urls:
                    fetched_detail_urls.add(candidate.url)
                    search_detail_fetches += 1
                    self.last_search_stats["detail_page_count"] += 1
                    self.last_search_stats["detail_urls"].append(candidate.url)
                    try:
                        _load_page(page, candidate.url, self.timeout_ms)
                        detail_html = page.content()
                    except Exception:
                        detail_html = ""
                        self.last_search_stats["detail_error_count"] += 1
                    if detail_html:
                        enriched = _merge_candidate(candidate, parse_product_page(detail_html, candidate.url))
                listing = _listing_from_candidate(enriched)
                if listing:
                    seen_listing_urls.add(candidate.url)
                    listings.append(listing)
                if len(listings) >= max_results:
                    return listings
        return listings

    def _playwright_fetch(self, url: str) -> str:
        return self._with_playwright_fetcher(lambda fetcher: fetcher(url))

    def _with_playwright_fetcher(self, action: Callable[[HtmlFetcher], Any]) -> Any:
        def run(page: Any) -> Any:
            def fetch(url: str) -> str:
                _load_page(page, url, self.timeout_ms)
                return page.content()

            return action(fetch)

        return self._with_playwright_page(run)

    def _with_playwright_page(self, action: Callable[[Any], Any]) -> Any:
        try:
            from playwright.sync_api import (  # type: ignore[import-not-found]
                Error as PlaywrightError,
                TimeoutError as PlaywrightTimeoutError,
                sync_playwright,
            )
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Amazon Renewed source requires optional Playwright support. "
                'Install with `python -m pip install -e ".[amazon]"` and run '
                "`python -m playwright install chromium`."
            ) from exc

        try:
            with sync_playwright() as playwright:
                browser_type = getattr(playwright, self.browser, None)
                if browser_type is None:
                    raise RuntimeError(f"Unsupported Playwright browser {self.browser!r}.")

                launch_options: dict[str, Any] = {"headless": self.headless}
                if self.channel:
                    launch_options["channel"] = self.channel
                browser = browser_type.launch(**launch_options)
                try:
                    context = browser.new_context(
                        locale="en-CA",
                        timezone_id="America/Toronto",
                        viewport={"width": 1366, "height": 900},
                    )
                    try:
                        page = context.new_page()
                        return action(page)
                    finally:
                        context.close()
                finally:
                    browser.close()
        except RuntimeError:
            raise
        except (PlaywrightTimeoutError, PlaywrightError) as exc:
            raise RuntimeError(f"Amazon Renewed browser request failed: {exc}") from exc


def extract_search_candidates_from_page(
    page: Any,
    base_url: str = DEFAULT_BASE_URL,
    base_host: str | None = None,
) -> list[AmazonCandidate]:
    """Extract candidate rows from the rendered Amazon page DOM."""
    try:
        rows = page.evaluate(_SEARCH_RESULT_EXTRACTOR)
    except Exception:
        return []
    return candidates_from_search_rows(rows, base_url, base_host)


def candidates_from_search_rows(
    rows: Any,
    base_url: str = DEFAULT_BASE_URL,
    base_host: str | None = None,
) -> list[AmazonCandidate]:
    """Convert rendered Amazon DOM rows into candidate listings."""
    if not isinstance(rows, list):
        return []

    host = base_host or _validated_base_host(base_url)
    candidates = []
    seen_urls = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        href = _product_href(str(row.get("url") or ""))
        url = _absolute_url(href, base_url, host) if href else None
        title = _normalize_space(row.get("title")) or _title_from_text(_normalize_space(row.get("text")))
        if not title or not url or url in seen_urls:
            continue
        seen_urls.add(url)
        text = _normalize_space(f"{title} {row.get('text') or ''}")
        candidates.append(
            AmazonCandidate(
                title=title,
                item_price_cad=_money(row.get("price_text")) or _fallback_price(text),
                url=url,
                available=_availability(text),
                condition_raw=_condition_signal(text, title),
                shipping_cad=0.0 if _free_shipping(text) else None,
                shipping_is_estimated=not _free_shipping(text),
                prime_signal=_prime_signal(text),
                asin=_clean_asin(row.get("asin")),
                source_specs=_specs_from_text(text),
            )
        )
    return candidates


_SEARCH_RESULT_EXTRACTOR = r"""
() => {
  const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const rows = [];
  const seen = new Set();

  const productLinks = [
    ...document.querySelectorAll(
      'a[href*="/dp/"], a[href*="/gp/product/"], a[href*="/sspa/click"], a[href*="/slredirect/"]'
    )
  ];

  const addRow = (link) => {
    if (!link) {
      return;
    }
    const href = link.href || link.getAttribute("href") || "";
    if (!href || seen.has(href)) {
      return;
    }

    const container =
      link.closest('[data-component-type="s-search-result"]') ||
      link.closest(".s-result-item") ||
      link.closest("[data-asin]") ||
      link.closest("[cel_widget_id]") ||
      link.closest("div");
    if (!container) {
      return;
    }

    const asin = container.getAttribute("data-asin") || "";
    const titleNode =
      link.closest("h2") ||
      link.querySelector("h2") ||
      container.querySelector("h2") ||
      container.querySelector("[data-cy='title-recipe']") ||
      link;
    const priceNode =
      container.querySelector(".a-price .a-offscreen") ||
      container.querySelector(".a-price") ||
      container.querySelector("[data-a-color='price']");
    const title = normalize(
      link.getAttribute("aria-label") ||
      titleNode.innerText ||
      titleNode.textContent ||
      ""
    );
    const text = normalize(container.innerText || container.textContent || "");

    seen.add(href);
    rows.push({
      asin,
      title,
      url: href,
      price_text: normalize(priceNode && (priceNode.innerText || priceNode.textContent)),
      text
    });
  };

  for (const container of document.querySelectorAll('[data-component-type="s-search-result"], .s-result-item, [data-asin]')) {
    const link = container.querySelector(
      'h2 a[href], a.a-link-normal[href*="/dp/"], a[href*="/gp/product/"], a[href*="/sspa/click"], a[href*="/slredirect/"]'
    );
    addRow(link);
  }

  for (const link of productLinks) {
    addRow(link);
  }

  return rows.slice(0, 30);
}
"""


def parse_search_results(html: str, base_url: str = DEFAULT_BASE_URL, base_host: str | None = None) -> list[AmazonCandidate]:
    """Parse Amazon search result HTML into candidate listings."""
    parser = _AmazonSearchParser()
    parser.feed(html)
    host = base_host or _validated_base_host(base_url)
    candidates = []
    for card in parser.cards:
        text = _normalize_space(" ".join(card.text_parts))
        title = card.title or _title_from_text(text)
        url = _absolute_url(card.url, base_url, host) if card.url else None
        if not title or not url:
            continue
        condition = _condition_signal(text, title)
        candidates.append(
            AmazonCandidate(
                title=title,
                item_price_cad=_money(card.price_text) or _fallback_price(text),
                url=url,
                available=_availability(text),
                condition_raw=condition,
                shipping_cad=0.0 if _free_shipping(text) else None,
                shipping_is_estimated=not _free_shipping(text),
                prime_signal=_prime_signal(text),
                asin=card.asin,
                source_specs=_specs_from_text(title),
            )
        )
    return candidates


def parse_product_page(html: str, url: str = "") -> AmazonCandidate:
    """Parse an Amazon product detail page into a candidate listing."""
    parser = _AmazonProductParser()
    parser.feed(html)
    text = _normalize_space(" ".join(parser.text_parts))
    title = parser.title or _title_from_text(text)
    condition = parser.condition or _condition_signal(text, title or "")
    return AmazonCandidate(
        title=title or "",
        item_price_cad=_money(parser.price_text),
        url=url,
        available=_availability(text),
        condition_raw=condition,
        shipping_cad=0.0 if _free_shipping(text) else None,
        shipping_is_estimated=not _free_shipping(text),
        prime_signal=_prime_signal(text),
        asin=parser.asin,
        source_specs=_specs_from_text(f"{title or ''} {text}"),
    )


class _SearchCard:
    def __init__(self, asin: str | None = None) -> None:
        self.asin = asin
        self.title: str | None = None
        self.url: str | None = None
        self.price_text = ""
        self.text_parts: list[str] = []


class _AmazonSearchParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.cards: list[_SearchCard] = []
        self._current: _SearchCard | None = None
        self._depth = 0
        self._capture_title = False
        self._title_parts: list[str] = []
        self._capture_price = False
        self._price_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = _attrs(attrs)
        if self._current is None and attrs_dict.get("data-component-type") == "s-search-result":
            self._current = _SearchCard(attrs_dict.get("data-asin"))
            self._depth = 1
            return
        if self._current is not None:
            self._depth += 1
            product_href = _product_href(attrs_dict.get("href"))
            if tag == "a" and not self._current.url and product_href:
                self._current.url = product_href
                self._capture_title = True
                self._title_parts = []
            classes = attrs_dict.get("class") or ""
            if "a-price" in classes:
                self._capture_price = True
                self._price_parts = []

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        if self._capture_title and tag == "a":
            title = _normalize_space(" ".join(self._title_parts))
            if title and not self._current.title:
                self._current.title = title
            self._capture_title = False
        if self._capture_price and tag in {"span", "div"}:
            price_text = _normalize_space(" ".join(self._price_parts))
            if price_text and not self._current.price_text:
                self._current.price_text = price_text
            self._capture_price = False
        self._depth -= 1
        if self._depth <= 0:
            self.cards.append(self._current)
            self._current = None

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return
        text = _normalize_space(data)
        if not text:
            return
        self._current.text_parts.append(text)
        if self._capture_title:
            self._title_parts.append(text)
        if self._capture_price:
            self._price_parts.append(text)


class _AmazonProductParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self.price_text = ""
        self.condition: str | None = None
        self.asin: str | None = None
        self.text_parts: list[str] = []
        self._capture_id: str | None = None
        self._capture_class: str | None = None
        self._capture_parts: list[str] = []
        self._price_scope_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = _attrs(attrs)
        element_id = attrs_dict.get("id") or ""
        classes = attrs_dict.get("class") or ""
        if self._price_scope_depth:
            self._price_scope_depth += 1
        if element_id in {"productTitle", "availability", "renewedProgramDescriptionBtf_feature_div"}:
            self._capture_id = element_id
            self._capture_parts = []
        elif _is_product_price_container_id(element_id):
            self._price_scope_depth = 1
            self._capture_id = "price"
            self._capture_parts = []
        elif self._price_scope_depth and "a-price" in classes:
            self._capture_class = "price"
            self._capture_parts = []
        if attrs_dict.get("name") == "ASIN" and attrs_dict.get("value"):
            self.asin = attrs_dict.get("value")

    def handle_endtag(self, tag: str) -> None:
        if self._capture_id:
            text = _normalize_space(" ".join(self._capture_parts))
            if self._capture_id == "productTitle" and text:
                self.title = text
            elif self._capture_id == "price" and text and not self.price_text:
                self.price_text = text
            elif self._capture_id == "renewedProgramDescriptionBtf_feature_div" and text:
                self.condition = _condition_signal(text, self.title or "")
            self._capture_id = None
            self._capture_parts = []
        if self._capture_class == "price":
            text = _normalize_space(" ".join(self._capture_parts))
            if text and not self.price_text:
                self.price_text = text
            self._capture_class = None
            self._capture_parts = []
        if self._price_scope_depth:
            self._price_scope_depth -= 1

    def handle_data(self, data: str) -> None:
        text = _normalize_space(data)
        if not text:
            return
        self.text_parts.append(text)
        if self._capture_id or self._capture_class:
            self._capture_parts.append(text)


def _listing_from_candidate(candidate: AmazonCandidate) -> dict[str, Any] | None:
    if candidate.item_price_cad is None or candidate.item_price_cad <= 0:
        return None
    if not candidate.condition_raw:
        return None
    total_price = candidate.item_price_cad + (candidate.shipping_cad or 0.0)
    return {
        "source": "amazon_renewed",
        "item_id": candidate.asin,
        "title": candidate.title,
        "item_price_cad": candidate.item_price_cad,
        "shipping_cad": candidate.shipping_cad,
        "total_price_cad": round(total_price, 2),
        "shipping_is_estimated": candidate.shipping_is_estimated,
        "condition_raw": candidate.condition_raw,
        "condition_norm": None,
        "url": candidate.url,
        "location": "Canada",
        "is_sold": False,
        "available": candidate.available,
        "availability": _availability_label(candidate.available),
        "source_specs": candidate.source_specs or {},
        "shipping_assumption": "prime_or_free" if candidate.shipping_cad == 0 else "unknown",
        "prime_signal": candidate.prime_signal,
    }


def _merge_candidate(base: AmazonCandidate, detail: AmazonCandidate) -> AmazonCandidate:
    detail_title = detail.title if _usable_product_title(detail.title) else ""
    return AmazonCandidate(
        title=detail_title or base.title,
        item_price_cad=detail.item_price_cad if detail.item_price_cad is not None else base.item_price_cad,
        url=base.url,
        available=detail.available if detail.available is not None else base.available,
        condition_raw=detail.condition_raw or base.condition_raw,
        shipping_cad=detail.shipping_cad if detail.shipping_cad is not None else base.shipping_cad,
        shipping_is_estimated=detail.shipping_is_estimated and base.shipping_is_estimated,
        prime_signal=detail.prime_signal if detail.prime_signal is not None else base.prime_signal,
        asin=detail.asin or base.asin,
        source_specs={**(base.source_specs or {}), **(detail.source_specs or {})},
    )


def _usable_product_title(title: str | None) -> bool:
    text = _normalize_space(title)
    if not text:
        return False
    lowered = text.lower()
    if len(text) > 350:
        return False
    if "{" in text or "}" in text or "display:" in lowered or "@media" in lowered:
        return False
    return True


def _is_product_price_container_id(value: str) -> bool:
    if value in {
        "priceblock_ourprice",
        "priceblock_dealprice",
        "priceblock_saleprice",
        "corePriceDisplay_desktop_feature_div",
        "corePrice_feature_div",
        "apex_desktop",
        "price_inside_buybox",
        "newBuyBoxPrice",
    }:
        return True
    lowered = value.lower()
    return lowered.startswith("corepricedisplay") or lowered.startswith("coreprice_feature")


def _rank_search_candidates(candidates: list[AmazonCandidate], query: str) -> list[AmazonCandidate]:
    tokens = _query_tokens(query)
    if not tokens:
        return candidates

    indexed = list(enumerate(candidates))
    indexed.sort(key=lambda item: (-_candidate_score(item[1], tokens), item[0]))
    return [candidate for _index, candidate in indexed]


def _candidate_score(candidate: AmazonCandidate, tokens: list[str]) -> float:
    text = _normalize_match_text(f"{candidate.title} {' '.join(str(value) for value in (candidate.source_specs or {}).values())}")
    compact_text = text.replace(" ", "")
    score = 0.0
    for token in tokens:
        if token in text or token.replace(" ", "") in compact_text:
            score += 1.0
    if candidate.condition_raw:
        score += 0.25
    lowered_url = candidate.url.lower()
    if "/sspa/" in lowered_url or "sp_csd=" in lowered_url or "spons" in lowered_url:
        score -= 1.0
    return score


def _query_tokens(query: str) -> list[str]:
    ignored = {
        "amazon",
        "renewed",
        "renewal",
        "refurbished",
        "laptop",
        "notebook",
        "computer",
        "pc",
        "intel",
        "core",
        "gb",
        "ssd",
        "ram",
    }
    tokens = []
    for token in re.findall(r"[a-z0-9]+", query.lower()):
        if len(token) < 2 or token in ignored:
            continue
        normalized = token
        if normalized not in tokens:
            tokens.append(normalized)
    return tokens


def _load_page(page: Any, url: str, timeout_ms: int) -> None:
    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    _dismiss_soft_interstitials(page)
    try:
        page.wait_for_load_state("networkidle", timeout=3000)
    except Exception:
        pass


def _scroll_search_results(page: Any) -> None:
    try:
        page.wait_for_selector('a[href*="/dp/"], a[href*="/gp/product/"], [data-asin]', timeout=5000)
    except Exception:
        return
    for y in [0, 700, 1400, 0]:
        try:
            page.evaluate("(scrollY) => window.scrollTo(0, scrollY)", y)
            page.wait_for_timeout(200)
        except Exception:
            return


def _dismiss_soft_interstitials(page: Any) -> None:
    for selector in [
        "input#sp-cc-accept",
        "input[name='accept']",
        "button:has-text('Continue shopping')",
    ]:
        try:
            locator = page.locator(selector)
            if locator.count():
                locator.first.click(timeout=1000)
        except Exception:
            continue


def _looks_like_blocked_page(html: str) -> bool:
    lowered = html.lower()
    if "interest-based ads notice" in lowered and "robot check" not in lowered and "captcha" not in lowered:
        return False
    return any(
        marker in lowered
        for marker in [
            "enter the characters you see below",
            "robot check",
            "captcha",
            "sorry, we just need to make sure you're not a robot",
        ]
    )


def _condition_signal(text: str, title: str) -> str | None:
    combined = f"{title} {text}".lower()
    if "premium renewed" in combined:
        return "Premium Renewed"
    if "amazon renewed" in combined:
        return "Amazon Renewed"
    if "renewed" in combined or "refurbished" in combined or "pre-owned" in combined or "restored" in combined:
        return "Renewed"
    if "like new" in combined:
        return "Like New"
    return None


def _availability(text: str) -> bool | None:
    lowered = text.lower()
    if re.search(r"\b(currently unavailable|out of stock|temporarily unavailable)\b", lowered):
        return False
    if re.search(r"\b(in stock|add to cart|only \d+ left)\b", lowered):
        return True
    return None


def _prime_signal(text: str) -> bool | None:
    lowered = text.lower()
    if "prime" in lowered:
        return True
    return None


def _free_shipping(text: str) -> bool:
    lowered = text.lower()
    return "free delivery" in lowered or "free shipping" in lowered or "prime" in lowered


def _specs_from_text(text: str) -> dict[str, Any]:
    specs: dict[str, Any] = {}
    brand = _brand_from_title(text)
    ram_gb = _first_gb_after_marker(text, ["ram", "memory"]) or _first_gb_value(text)
    storage_gb = _storage_gb(text)
    cpu_short = _cpu_short(text)
    if brand:
        specs["brand"] = brand
    if ram_gb:
        specs["ram_gb"] = ram_gb
    if storage_gb:
        specs["storage_gb"] = storage_gb
    if cpu_short:
        specs["cpu_short"] = cpu_short
    return specs


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
    if re.search(r"\b(i\s*phones?|iphones?|i\s*pads?|ipads?|macbooks?|imacs?)\b", title, flags=re.IGNORECASE):
        return "Apple"
    return None


def _first_gb_after_marker(text: str, markers: list[str]) -> int | None:
    for marker in markers:
        match = re.search(rf"(\d+)\s*GB\s+{marker}\b|{marker}\s*:?\s*(\d+)\s*GB", text, flags=re.IGNORECASE)
        if match:
            return int(next(group for group in match.groups() if group))
    return None


def _first_gb_value(text: str) -> int | None:
    match = re.search(r"(\d+)\s*GB", text, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _storage_gb(text: str) -> int | None:
    matches = list(re.finditer(r"(\d+(?:\.\d+)?)\s*(TB|GB)", text, flags=re.IGNORECASE))
    if not matches:
        return None
    values = []
    for match in matches:
        amount = float(match.group(1))
        unit = match.group(2).lower()
        gb = int(amount * 1024) if unit == "tb" else int(amount)
        values.append(gb)
    return max(values)


def _cpu_short(text: str) -> str | None:
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
            return _normalize_space(match.group(0))
    return None


def _money(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "")
    split_price = re.search(r"\$\s*([0-9]+)\s+([0-9]{2})\b", text)
    if split_price:
        amount = round(float(f"{split_price.group(1)}.{split_price.group(2)}"), 2)
        return amount if amount > 0 else None
    match = re.search(r"\$?\s*([0-9]+(?:\.[0-9]{2})?)", text)
    if not match:
        return None
    amount = round(float(match.group(1)), 2)
    return amount if amount > 0 else None


def _fallback_price(text: str) -> float | None:
    prices = [
        _money(match.group(0))
        for match in re.finditer(r"\$\s*[0-9][0-9,]*(?:(?:\.|\s+)[0-9]{2})?", text)
    ]
    prices = [price for price in prices if price is not None and price >= 20]
    return min(prices) if prices else None


def _title_from_text(text: str) -> str | None:
    parts = [part.strip() for part in re.split(r"\s{2,}|\n", text) if part.strip()]
    return parts[0] if parts else None


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


def _clean_asin(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if re.fullmatch(r"[A-Z0-9]{10}", text):
        return text
    return None


def _product_href(href: str | None) -> str | None:
    if not href:
        return None
    if _is_product_href(href):
        return href
    parsed = parse.urlparse(href)
    query = parse.parse_qs(parsed.query)
    for key in ["url", "u"]:
        for value in query.get(key, []):
            nested = parse.unquote(value)
            if _is_product_href(nested):
                return nested
    return None


def _is_product_href(href: str | None) -> bool:
    if not href:
        return False
    return bool(re.search(r"/(?:dp|gp/product)/[A-Z0-9]{10}\b", href, flags=re.IGNORECASE))


def _validated_base_host(base_url: str) -> str:
    parsed = parse.urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Amazon base_url must be an HTTP(S) URL with a host.")
    return parsed.hostname


def _attrs(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
    return {key.lower(): value for key, value in attrs if value is not None}


def _normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_match_text(value: Any) -> str:
    lowered = str(value or "").lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    normalized = re.sub(r"\s+", " ", lowered).strip()
    return f" {normalized} "
