import unittest

from pc_pricer.sources.refurb_io import RefurbIoSource, parse_product_html


class RefurbIoSourceTests(unittest.TestCase):
    def test_parses_in_stock_product(self):
        product = parse_product_html(
            _product_html(
                title="Lenovo ThinkPad X13 Yoga 13 Touch Laptop Core i5-1145G7 16 GB 256 GB",
                price="499.00",
                availability="https://schema.org/InStock",
                condition="Grade A",
            )
        )

        self.assertEqual(product.title, "Lenovo ThinkPad X13 Yoga 13 Touch Laptop Core i5-1145G7 16 GB 256 GB")
        self.assertEqual(product.item_price_cad, 499.00)
        self.assertIs(product.available, True)
        self.assertEqual(product.condition_raw, "Grade A")
        self.assertEqual(product.shipping_cad, 0.0)
        self.assertEqual(product.specs["ram_gb"], 16)
        self.assertEqual(product.specs["storage_gb"], 256)
        self.assertEqual(product.specs["cpu_short"], "i5-1145G7")

    def test_parses_sold_out_product(self):
        product = parse_product_html(
            _product_html(
                title="Dell OptiPlex 7050 Desktop i5-6500 8GB 256GB",
                price="199.00",
                availability="https://schema.org/OutOfStock",
                stock_text="Sold out",
            )
        )

        self.assertIs(product.available, False)

    def test_prefers_sale_price_from_json_ld(self):
        product = parse_product_html(
            _product_html(
                title="HP EliteBook 840 G6 Laptop i5-8365U 16GB 512GB",
                price="349.00",
                extra_prices="$1,299 $349",
            )
        )

        self.assertEqual(product.item_price_cad, 349.00)

    def test_maps_condition_grade_through_normalizer_shape(self):
        product = parse_product_html(
            _product_html(
                title="Apple MacBook Pro 13 Laptop i5 8GB 256GB - Refurbished",
                price="599.00",
                condition="A-Grade",
            )
        )

        self.assertEqual(product.condition_raw, "A-Grade")

    def test_missing_or_malformed_price_returns_no_listing(self):
        urls = ["https://ca.refurb.io/products/bad-price"]

        source = RefurbIoSource(
            json_get=lambda _url, _headers: _search_payload(urls),
            http_get=lambda _url, _headers: _product_html(
                title="Lenovo ThinkPad X1 Carbon",
                price=None,
                extra_prices="Price unavailable",
            ),
        )

        self.assertEqual(source.search("ThinkPad", 3), [])

    def test_search_fetches_top_candidate_product_pages(self):
        urls = [
            "https://ca.refurb.io/products/lenovo-thinkpad-x13",
            "https://ca.refurb.io/products/dell-latitude",
        ]
        fetched = []

        def http_get(url, _headers):
            fetched.append(url)
            return _product_html(
                title="Lenovo ThinkPad X13 Yoga Laptop i5-1145G7 16GB 256GB",
                price="499.00",
            )

        source = RefurbIoSource(json_get=lambda _url, _headers: _search_payload(urls), http_get=http_get)
        listings = source.search("ThinkPad X13", 1)

        self.assertEqual(fetched, [urls[0]])
        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0]["source"], "refurb_io")
        self.assertEqual(listings[0]["total_price_cad"], 499.00)
        self.assertEqual(listings[0]["availability"], "in_stock")

    def test_rejects_product_urls_outside_configured_host(self):
        source = RefurbIoSource(
            base_url="https://ca.refurb.io",
            json_get=lambda _url, _headers: _search_payload(
                [
                    "file:///etc/passwd",
                    "https://evil.example/products/bad",
                    "/products/lenovo-thinkpad-x13",
                ]
            ),
            http_get=lambda url, _headers: _product_html(
                title=f"Fetched {url}",
                price="499.00",
            ),
        )

        listings = source.search("ThinkPad X13", 5)

        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0]["url"], "https://ca.refurb.io/products/lenovo-thinkpad-x13")

    def test_skips_one_failed_product_fetch_and_keeps_later_candidates(self):
        urls = [
            "https://ca.refurb.io/products/dead",
            "https://ca.refurb.io/products/good",
        ]

        def http_get(url, _headers):
            if url.endswith("/dead"):
                raise RuntimeError("dead product page")
            return _product_html(
                title="Lenovo ThinkPad X13 Yoga Laptop i5-1145G7 16GB 256GB",
                price="499.00",
            )

        source = RefurbIoSource(json_get=lambda _url, _headers: _search_payload(urls), http_get=http_get)

        listings = source.search("ThinkPad X13", 5)

        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0]["url"], "https://ca.refurb.io/products/good")

    def test_user_agent_uses_package_version(self):
        seen_headers = []

        def http_get(_url, headers):
            seen_headers.append(headers)
            return _product_html(
                title="Lenovo ThinkPad X13 Yoga Laptop i5-1145G7 16GB 256GB",
                price="499.00",
            )

        source = RefurbIoSource(
            json_get=lambda _url, _headers: _search_payload(["https://ca.refurb.io/products/good"]),
            http_get=http_get,
        )

        source.search("ThinkPad X13", 1)

        self.assertEqual(seen_headers[0]["User-Agent"], "CFS-Price-Compare/0.4.2")

    def test_parses_newer_cpu_short_names(self):
        apple = parse_product_html(
            _product_html(title="Apple MacBook Air Laptop M2 8GB 256GB", price="699.00", processor="M2")
        )
        ultra = parse_product_html(
            _product_html(
                title="Lenovo ThinkPad Laptop Core Ultra 7 155U 16GB 512GB",
                price="899.00",
                processor="Core Ultra 7 155U",
            )
        )

        self.assertEqual(apple.specs["cpu_short"], "M2")
        self.assertEqual(ultra.specs["cpu_short"], "Core Ultra 7 155U")


def _product_html(
    title,
    price,
    availability="https://schema.org/InStock",
    condition="Grade A",
    stock_text="29 in stock, ready to be shipped",
    extra_prices="",
    processor="Core i5-1145G7",
):
    price_json = f'"price": "{price}",' if price is not None else ""
    return f"""
<html>
  <head>
    <meta property="og:title" content="{title}">
    <script type="application/ld+json">
      {{
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "{title}",
        "sku": "SKU-123",
        "offers": {{
          "@type": "Offer",
          {price_json}
          "priceCurrency": "CAD",
          "availability": "{availability}"
        }}
      }}
    </script>
  </head>
  <body>
    <h1>{title}</h1>
    <div>{extra_prices}</div>
    <div>Availability: {stock_text}</div>
    <div>Free Delivery Across Canada</div>
    <table>
      <tr><th>Brand</th><td>Lenovo</td></tr>
      <tr><th>Model</th><td>ThinkPad X13 Yoga Gen 2</td></tr>
      <tr><th>Memory</th><td>16GB</td></tr>
      <tr><th>Storage</th><td>256GB SSD</td></tr>
      <tr><th>Processor</th><td>{processor}</td></tr>
      <tr><th>Condition</th><td>{condition}</td></tr>
    </table>
  </body>
</html>
"""


def _search_payload(urls):
    return {
        "resources": {
            "results": {
                "products": [{"url": url} for url in urls],
            },
        },
    }


if __name__ == "__main__":
    unittest.main()
