import unittest
from unittest.mock import patch

from pc_pricer.sources.amazon_renewed import (
    AmazonRenewedSource,
    candidates_from_search_rows,
    parse_product_page,
    parse_search_results,
    _looks_like_blocked_page,
)


class AmazonRenewedSourceTests(unittest.TestCase):
    def test_parse_search_results_extracts_product_candidates(self):
        candidates = parse_search_results(_search_html())

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].asin, "B0AMAZON01")
        self.assertEqual(candidates[0].title, "Lenovo ThinkPad X13 Yoga Renewed i5-1135G7 16GB 256GB")
        self.assertEqual(candidates[0].item_price_cad, 599.99)
        self.assertEqual(candidates[0].url, "https://www.amazon.ca/Lenovo-ThinkPad/dp/B0AMAZON01")
        self.assertEqual(candidates[0].condition_raw, "Amazon Renewed")
        self.assertIs(candidates[0].available, True)
        self.assertEqual(candidates[0].shipping_cad, 0.0)
        self.assertEqual(candidates[0].source_specs["ram_gb"], 16)
        self.assertEqual(candidates[0].source_specs["storage_gb"], 256)
        self.assertEqual(candidates[0].source_specs["cpu_short"], "i5-1135G7")

    def test_parse_product_page_extracts_detail_fields(self):
        candidate = parse_product_page(_product_html(), "https://www.amazon.ca/dp/B0AMAZON01")

        self.assertEqual(candidate.title, "Lenovo ThinkPad X13 Yoga Renewed i5-1135G7 16GB 256GB")
        self.assertEqual(candidate.item_price_cad, 579.99)
        self.assertEqual(candidate.condition_raw, "Amazon Renewed")
        self.assertEqual(candidate.asin, "B0AMAZON01")
        self.assertIs(candidate.available, True)

    def test_parse_product_page_ignores_recommendation_prices(self):
        candidate = parse_product_page(
            """
<html>
  <body>
    <input type="hidden" name="ASIN" value="B0AMAZON01">
    <span id="productTitle">Lenovo ThinkPad X13 Yoga Renewed i5-1135G7 16GB 256GB</span>
    <div id="availability">In Stock</div>
    <div id="renewedProgramDescriptionBtf_feature_div">Amazon Renewed product</div>
    <div id="sp_detail_thematicCard">
      <span>Suggested item</span>
      <span class="a-price"><span class="a-offscreen">$1,799.99</span></span>
    </div>
  </body>
</html>
""",
            "https://www.amazon.ca/dp/B0AMAZON01",
        )

        self.assertIsNone(candidate.item_price_cad)

    def test_parse_product_page_prefers_product_price_over_recommendations(self):
        candidate = parse_product_page(
            """
<html>
  <body>
    <input type="hidden" name="ASIN" value="B0AMAZON01">
    <span id="productTitle">Lenovo ThinkPad X13 Yoga Renewed i5-1135G7 16GB 256GB</span>
    <div id="corePriceDisplay_desktop_feature_div">
      <span class="a-price"><span class="a-offscreen">$579.99</span></span>
    </div>
    <div id="availability">In Stock</div>
    <div id="renewedProgramDescriptionBtf_feature_div">Amazon Renewed product</div>
    <div id="sp_detail_thematicCard">
      <span>Suggested item</span>
      <span class="a-price"><span class="a-offscreen">$1,799.99</span></span>
    </div>
  </body>
</html>
""",
            "https://www.amazon.ca/dp/B0AMAZON01",
        )

        self.assertEqual(candidate.item_price_cad, 579.99)

    def test_parse_product_page_ignores_stray_zero_before_product_price(self):
        candidate = parse_product_page(
            """
<html>
  <body>
    <input type="hidden" name="ASIN" value="B0AMAZON01">
    <span id="productTitle">Dell U2419H Monitor Amazon Renewed</span>
    <div id="corePriceDisplay_desktop_feature_div">
      <span id="basisPrice">0</span>
      <span class="a-price">
        <span class="a-offscreen">$219.99</span>
      </span>
    </div>
    <div id="availability">In Stock</div>
    <div id="renewedProgramDescriptionBtf_feature_div">Amazon Renewed product</div>
  </body>
</html>
""",
            "https://www.amazon.ca/dp/B0AMAZON01",
        )

        self.assertEqual(candidate.item_price_cad, 219.99)

    def test_candidates_from_rendered_rows_do_not_require_legacy_card_shape(self):
        candidates = candidates_from_search_rows(
            [
                {
                    "asin": "B0AMAZON01",
                    "title": "Lenovo ThinkPad X13 Yoga Renewed i5-1135G7 16GB 256GB",
                    "url": "https://www.amazon.ca/Lenovo-ThinkPad/dp/B0AMAZON01/ref=sr_1_1",
                    "price_text": "$599.99",
                    "text": "Amazon Renewed In stock Prime FREE Delivery",
                }
            ]
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].url, "https://www.amazon.ca/Lenovo-ThinkPad/dp/B0AMAZON01/ref=sr_1_1")
        self.assertEqual(candidates[0].item_price_cad, 599.99)
        self.assertEqual(candidates[0].condition_raw, "Amazon Renewed")

    def test_candidates_from_rendered_rows_extract_redirect_links(self):
        candidates = candidates_from_search_rows(
            [
                {
                    "asin": "",
                    "title": "Dell Latitude Renewed i5-1135G7 16GB 256GB",
                    "url": "https://www.amazon.ca/sspa/click?url=%2FDell-Latitude%2Fdp%2FB0AMAZON02",
                    "price_text": "$449.99",
                    "text": "Renewed In stock",
                }
            ]
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].url, "https://www.amazon.ca/Dell-Latitude/dp/B0AMAZON02")

    def test_candidates_infer_apple_brand_from_iphone_title(self):
        candidates = candidates_from_search_rows(
            [
                {
                    "asin": "B09LNW3CY2",
                    "title": "iPhone 13, 128GB, Midnight - Unlocked (Renewed)",
                    "url": "https://www.amazon.ca/Apple-iPhone-13-128GB-Midnight/dp/B09LNW3CY2",
                    "price_text": "$399.99",
                    "text": "Renewed In stock",
                }
            ]
        )

        self.assertEqual(candidates[0].source_specs["brand"], "Apple")

    def test_candidates_prefer_explicit_brand_over_apple_product_word(self):
        candidates = candidates_from_search_rows(
            [
                {
                    "asin": "B0SAMSUNG1",
                    "title": "Samsung iPhone compatible wireless charger Renewed",
                    "url": "https://www.amazon.ca/Samsung-Charger/dp/B0SAMSUNG1",
                    "price_text": "$39.99",
                    "text": "Renewed In stock",
                }
            ]
        )

        self.assertEqual(candidates[0].source_specs["brand"], "Samsung")

    def test_search_uses_injected_browser_fetcher_and_detail_pages(self):
        fetched = []

        def fetcher(url):
            fetched.append(url)
            if "/s?" in url:
                return _search_html(title="Lenovo ThinkPad X13 Yoga i5-1135G7 16GB 256GB", price=None)
            return _product_html(price="579.99")

        source = AmazonRenewedSource(page_fetcher=fetcher, max_product_pages=2)
        listings = source.search("Lenovo ThinkPad X13 Yoga Renewed", 1)

        self.assertEqual(len(listings), 1)
        self.assertEqual(len(fetched), 2)
        self.assertIn("i=amazon-renewed", fetched[0])
        self.assertEqual(listings[0]["source"], "amazon_renewed")
        self.assertEqual(listings[0]["total_price_cad"], 579.99)
        self.assertEqual(listings[0]["condition_raw"], "Amazon Renewed")
        self.assertEqual(listings[0]["availability"], "in_stock")
        self.assertEqual(source.last_search_stats["candidate_count"], 1)
        self.assertEqual(source.last_search_stats["detail_page_count"], 1)

    def test_search_opens_detail_page_even_when_search_card_looks_complete(self):
        fetched = []

        def fetcher(url):
            fetched.append(url)
            if "/s?" in url:
                return _search_html()
            return _product_html(price="579.99")

        source = AmazonRenewedSource(page_fetcher=fetcher, max_product_pages=2)
        listings = source.search("Lenovo ThinkPad X13 Yoga Renewed", 1)

        self.assertEqual(len(listings), 1)
        self.assertEqual(len(fetched), 2)
        self.assertIn("/s?", fetched[0])
        self.assertIn("/dp/B0AMAZON01", fetched[1])
        self.assertEqual(listings[0]["total_price_cad"], 579.99)

    def test_search_falls_back_to_broad_amazon_search_when_renewed_department_is_empty(self):
        fetched = []

        def fetcher(url):
            fetched.append(url)
            if "i=amazon-renewed" in url:
                return "<html><body>No results</body></html>"
            if "/s?" in url:
                return _search_html(
                    title="iPhone 13, 128GB, Midnight - Unlocked (Renewed)",
                    price="$399.99",
                    url="/Apple-iPhone-13-128GB-Midnight/dp/B09LNW3CY2",
                )
            return _product_html(
                title="iPhone 13, 128GB, Midnight - Unlocked (Renewed)",
                price="399.99",
                asin="B09LNW3CY2",
            )

        source = AmazonRenewedSource(page_fetcher=fetcher, max_product_pages=1)
        listings = source.search("Apple iPhone 13 128GB Renewed", 5)

        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0]["item_id"], "B09LNW3CY2")
        self.assertIn("i=amazon-renewed", fetched[0])
        self.assertNotIn("i=amazon-renewed", fetched[1])
        self.assertEqual(source.last_search_stats["search_urls"], fetched[:2])

    def test_search_tops_up_partial_renewed_department_results_from_broad_search(self):
        fetched = []

        def fetcher(url):
            fetched.append(url)
            if "i=amazon-renewed" in url:
                return _search_html(
                    title="iPhone 13, 128GB, Midnight - Unlocked (Renewed)",
                    price="$419.99",
                    url="/Apple-iPhone-13-128GB-Midnight/dp/B09LNW3CY2",
                )
            if "/s?" in url:
                return _search_html(
                    title="iPhone 13, 128GB, Blue - Unlocked (Renewed)",
                    price="$399.99",
                    url="/Apple-iPhone-13-128GB-Blue/dp/B09PHONE02",
                    asin="B09PHONE02",
                )
            if "B09LNW3CY2" in url:
                return _product_html(
                    title="iPhone 13, 128GB, Midnight - Unlocked (Renewed)",
                    price="419.99",
                    asin="B09LNW3CY2",
                )
            return _product_html(
                title="iPhone 13, 128GB, Blue - Unlocked (Renewed)",
                price="399.99",
                asin="B09PHONE02",
            )

        source = AmazonRenewedSource(page_fetcher=fetcher, max_product_pages=1)
        listings = source.search("Apple iPhone 13 128GB Renewed", 2)

        self.assertEqual([listing["item_id"] for listing in listings], ["B09LNW3CY2", "B09PHONE02"])
        self.assertEqual(len(source.last_search_stats["search_urls"]), 2)
        self.assertEqual(source.last_search_stats["detail_page_count"], 1)

    def test_detail_page_budget_applies_across_search_urls(self):
        fetched = []

        def fetcher(url):
            fetched.append(url)
            if "i=amazon-renewed" in url:
                return _search_html(
                    title="Apple iPhone 13 128GB renewed-style decorative case",
                    price=None,
                    url="/Decorative-Case/dp/B0CASE0001",
                )
            if "/s?" in url:
                return _search_html(
                    title="iPhone 13, 128GB, Midnight - Unlocked (Renewed)",
                    price="$399.99",
                    url="/Apple-iPhone-13-128GB-Midnight/dp/B09LNW3CY2",
                    asin="B09LNW3CY2",
                )
            if "B0CASE0001" in url:
                return "<html><body>Case accessory</body></html>"
            return _product_html(
                title="iPhone 13, 128GB, Midnight - Unlocked (Renewed)",
                price="399.99",
                asin="B09LNW3CY2",
            )

        source = AmazonRenewedSource(page_fetcher=fetcher, max_product_pages=1)
        listings = source.search("Apple iPhone 13 128GB Renewed", 1)

        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0]["item_id"], "B09LNW3CY2")
        self.assertEqual(source.last_search_stats["detail_page_count"], 1)
        self.assertIn("/Decorative-Case/dp/B0CASE0001", source.last_search_stats["detail_urls"][0])
        self.assertNotIn("/Apple-iPhone-13-128GB-Midnight/dp/B09LNW3CY2", source.last_search_stats["detail_urls"])

    def test_rendered_search_continues_scanning_after_detail_page_limit(self):
        page = _RenderedSearchPage(
            rows=[
                {
                    "asin": "B0CASE0001",
                    "title": "Apple iPhone 13 128GB renewed-style decorative case",
                    "url": "/Decorative-Case/dp/B0CASE0001",
                    "price_text": "",
                    "text": "In stock",
                },
                {
                    "asin": "B09LNW3CY2",
                    "title": "iPhone 13, 128GB, Midnight - Unlocked (Renewed)",
                    "url": "/Apple-iPhone-13-128GB-Midnight/dp/B09LNW3CY2",
                    "price_text": "$399.99",
                    "text": "Renewed In stock",
                },
            ],
            detail_pages={
                "https://www.amazon.ca/Decorative-Case/dp/B0CASE0001": "<html><body>Case accessory</body></html>",
            },
        )

        source = AmazonRenewedSource(max_product_pages=1)
        listings = source._search_with_page("Apple iPhone 13 128GB Renewed", 5, page)

        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0]["item_id"], "B09LNW3CY2")
        self.assertEqual(source.last_search_stats["detail_page_count"], 1)
        self.assertEqual(
            source.last_search_stats["detail_urls"],
            ["https://www.amazon.ca/Decorative-Case/dp/B0CASE0001"],
        )

    def test_search_ranks_query_token_match_ahead_of_weaker_sponsored_rows(self):
        fetched = []

        def fetcher(url):
            fetched.append(url)
            if "/s?" in url:
                return _ranked_search_html()
            if "B0EXACT000" in url:
                return _product_html(price="495.00", asin="B0EXACT000")
            return _product_html(title="Lenovo ThinkPad E16 Renewed 16GB 512GB", price="1399.99", asin="B0SPONSOR1")

        source = AmazonRenewedSource(page_fetcher=fetcher, max_product_pages=1)
        listings = source.search("Lenovo ThinkPad X13 Yoga i5-1135G7 16GB Renewed", 5)

        self.assertGreaterEqual(len(listings), 1)
        self.assertIn("B0EXACT000", fetched[1])
        self.assertEqual(listings[0]["item_id"], "B0EXACT000")

    def test_missing_price_returns_no_listing(self):
        source = AmazonRenewedSource(page_fetcher=lambda _url: _search_html(price=None), max_product_pages=0)

        self.assertEqual(source.search("ThinkPad Renewed", 5), [])

    def test_zero_price_returns_no_listing(self):
        source = AmazonRenewedSource(page_fetcher=lambda _url: _search_html(price="$0.00"), max_product_pages=0)

        self.assertEqual(source.search("ThinkPad Renewed", 5), [])

    def test_non_renewed_result_returns_no_listing(self):
        source = AmazonRenewedSource(
            page_fetcher=lambda _url: _search_html(
                title="Lenovo ThinkPad X13 Yoga i5-1135G7 16GB 256GB",
                include_renewed=False,
            ),
            max_product_pages=0,
        )

        self.assertEqual(source.search("ThinkPad Renewed", 5), [])

    def test_disabled_source_does_not_fetch(self):
        source = AmazonRenewedSource(enabled=False, page_fetcher=lambda _url: self.fail("should not fetch"))

        self.assertEqual(source.search("ThinkPad Renewed", 5), [])

    def test_playwright_failure_is_reported(self):
        source = AmazonRenewedSource()
        with patch.object(source, "_with_playwright_page", side_effect=RuntimeError("requires Playwright")):
            with self.assertRaisesRegex(RuntimeError, "requires Playwright"):
                source.search("ThinkPad Renewed", 5)

    def test_robot_check_page_is_reported_as_source_error(self):
        source = AmazonRenewedSource(
            page_fetcher=lambda _url: "<html><title>Robot Check</title>Enter the characters you see below</html>"
        )

        with self.assertRaisesRegex(RuntimeError, "robot-check"):
            source.search("ThinkPad Renewed", 5)

    def test_interest_based_ads_notice_is_not_treated_as_robot_check(self):
        html = """
<html>
  <body>
    Interest-Based Ads Notice
    Continue Shopping
    Results
    <div data-component-type="s-search-result"></div>
  </body>
</html>
"""

        self.assertFalse(_looks_like_blocked_page(html))

    def test_rejects_product_urls_outside_amazon_host(self):
        html = _search_html(url="https://evil.example/dp/B0AMAZON01")

        self.assertEqual(parse_search_results(html), [])

    def test_extracts_product_url_from_amazon_redirect_link(self):
        html = _search_html(url="/sspa/click?url=%2FLenovo-ThinkPad%2Fdp%2FB0AMAZON01%2Fref%3Dsr_1_1")

        candidates = parse_search_results(html)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].url, "https://www.amazon.ca/Lenovo-ThinkPad/dp/B0AMAZON01/ref=sr_1_1")

    def test_product_detail_specs_use_page_text_when_title_is_sparse(self):
        candidate = parse_product_page(
            """
<html>
  <body>
    <input type="hidden" name="ASIN" value="B0AMAZON01">
    <span id="productTitle">Lenovo ThinkPad X13 Yoga Amazon Renewed</span>
    <div id="corePriceDisplay_desktop_feature_div">
      <span class="a-price">$579.99</span>
    </div>
    <div id="availability">In Stock</div>
    <div id="renewedProgramDescriptionBtf_feature_div">Amazon Renewed product</div>
    <ul>
      <li>Intel Core i5-1135G7</li>
      <li>16GB RAM</li>
      <li>256GB SSD</li>
    </ul>
  </body>
</html>
""",
            "https://www.amazon.ca/dp/B0AMAZON01",
        )

        self.assertEqual(candidate.source_specs["ram_gb"], 16)
        self.assertEqual(candidate.source_specs["storage_gb"], 256)
        self.assertEqual(candidate.source_specs["cpu_short"], "i5-1135G7")

    def test_skips_one_failed_detail_page_and_keeps_later_candidates(self):
        def fetcher(url):
            if "/s?" in url:
                return _two_result_search_html()
            if url.endswith("B0AMAZON01"):
                raise RuntimeError("dead detail page")
            return _product_html(title="Dell Latitude Renewed i5-1135G7 16GB 256GB", price="449.99", asin="B0AMAZON02")

        source = AmazonRenewedSource(page_fetcher=fetcher, max_product_pages=2)
        listings = source.search("laptop renewed", 5)

        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0]["item_id"], "B0AMAZON02")

    def test_detail_page_css_blob_does_not_replace_search_title(self):
        def fetcher(url):
            if "/s?" in url:
                return _search_html(title="Lenovo ThinkPad X13 Yoga Gen 2 i5-1135G7 16GB 256GB Renewed")
            return """
<html>
    <body>
    <style>.grid-container { display: block; }</style>
    <div id="corePriceDisplay_desktop_feature_div">
      <span class="a-price">$495.00</span>
    </div>
    <div id="availability">In Stock</div>
    <div id="renewedProgramDescriptionBtf_feature_div">Amazon Renewed product</div>
  </body>
</html>
"""

        source = AmazonRenewedSource(page_fetcher=fetcher, max_product_pages=1)
        listings = source.search("Lenovo ThinkPad X13 Yoga i5-1135G7 16GB Renewed", 5)

        self.assertEqual(listings[0]["title"], "Lenovo ThinkPad X13 Yoga Gen 2 i5-1135G7 16GB 256GB Renewed")


def _search_html(
    title="Lenovo ThinkPad X13 Yoga Renewed i5-1135G7 16GB 256GB",
    price="$599.99",
    url="/Lenovo-ThinkPad/dp/B0AMAZON01",
    include_renewed=True,
    asin="B0AMAZON01",
):
    price_html = (
        f"""
        <span class="a-price">
          <span class="a-offscreen">{price}</span>
        </span>
        """
        if price is not None
        else ""
    )
    renewed_html = "<span>Amazon Renewed</span>" if include_renewed else ""
    return f"""
<html>
  <body>
    <div data-component-type="s-search-result" data-asin="{asin}">
      <h2><a href="{url}"><span>{title}</span></a></h2>
      {price_html}
      {renewed_html}
      <span>In stock</span>
      <span>Prime FREE Delivery</span>
    </div>
  </body>
</html>
"""


def _two_result_search_html():
    return """
<html>
  <body>
    <div data-component-type="s-search-result" data-asin="B0AMAZON01">
      <h2><a href="/Lenovo-ThinkPad/dp/B0AMAZON01"><span>Lenovo ThinkPad X13 Yoga i5-1135G7 16GB 256GB</span></a></h2>
    </div>
    <div data-component-type="s-search-result" data-asin="B0AMAZON02">
      <h2><a href="/Dell-Latitude/dp/B0AMAZON02"><span>Dell Latitude i5-1135G7 16GB 256GB</span></a></h2>
    </div>
  </body>
</html>
"""


def _ranked_search_html():
    return """
<html>
  <body>
    <div data-component-type="s-search-result" data-asin="B0SPONSOR1">
      <h2><a href="/sspa/click?url=%2FLenovo-ThinkPad-E16%2Fdp%2FB0SPONSOR1"><span>Lenovo ThinkPad E16 Renewed 16GB 512GB</span></a></h2>
      <span class="a-price"><span class="a-offscreen">$1,399.99</span></span>
      <span>Amazon Renewed</span>
      <span>In stock</span>
    </div>
    <div data-component-type="s-search-result" data-asin="B0EXACT000">
      <h2><a href="/Lenovo-ThinkPad-X13-Yoga-Gen/dp/B0EXACT000"><span>Lenovo ThinkPad X13 Yoga Gen 2 i5-1135G7 16GB 256GB W11H Renewed</span></a></h2>
      <span class="a-price"><span class="a-offscreen">$495.00</span></span>
      <span>Amazon Renewed</span>
      <span>In stock</span>
    </div>
  </body>
</html>
"""


def _product_html(
    title="Lenovo ThinkPad X13 Yoga Renewed i5-1135G7 16GB 256GB",
    price="579.99",
    asin="B0AMAZON01",
):
    return f"""
<html>
  <body>
    <input type="hidden" name="ASIN" value="{asin}">
    <span id="productTitle">{title}</span>
    <div id="corePriceDisplay_desktop_feature_div">
      <span class="a-price">${price}</span>
    </div>
    <div id="availability">In Stock</div>
    <div id="renewedProgramDescriptionBtf_feature_div">Amazon Renewed product</div>
    <div>Prime FREE Delivery</div>
  </body>
</html>
"""


class _RenderedSearchPage:
    def __init__(self, rows, detail_pages):
        self.rows = rows
        self.detail_pages = detail_pages
        self.current_url = ""

    def goto(self, url, wait_until=None, timeout=None):
        self.current_url = url

    def wait_for_load_state(self, state, timeout=None):
        return None

    def wait_for_selector(self, selector, timeout=None):
        return None

    def wait_for_timeout(self, timeout):
        return None

    def evaluate(self, script, *args):
        if "document.querySelectorAll" in script:
            return self.rows
        return None

    def content(self):
        if "/s?" in self.current_url:
            return "<html><body>Results</body></html>"
        return self.detail_pages.get(self.current_url, "<html><body></body></html>")

    def locator(self, selector):
        return _MissingLocator()


class _MissingLocator:
    def count(self):
        return 0

    @property
    def first(self):
        return self

    def click(self, timeout=None):
        return None


if __name__ == "__main__":
    unittest.main()
