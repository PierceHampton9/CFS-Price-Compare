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


def _product_html(
    title,
    price,
    availability="https://schema.org/InStock",
    condition="Grade A",
    stock_text="29 in stock, ready to be shipped",
    extra_prices="",
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
      <tr><th>Processor</th><td>Core i5-1145G7</td></tr>
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
