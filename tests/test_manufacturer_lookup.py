import unittest

from pc_pricer.manufacturer_lookup import (
    build_manufacturer_lookup,
    candidate_from_manufacturer_page,
    lookup_manufacturer_specs,
    manufacturer_lookup_urls,
)


class ManufacturerLookupTests(unittest.TestCase):
    def test_lenovo_page_enriches_machine_type(self):
        html = """
        <html>
          <head><title>Lenovo ThinkPad X1 Carbon Gen 9 Specifications</title></head>
          <body>
            <h1>Lenovo ThinkPad X1 Carbon Gen 9 Laptop</h1>
            <table>
              <tr><th>Machine Type Model</th><td>ThinkPad X1 Carbon Gen 9</td></tr>
              <tr><th>Processor</th><td>Intel Core i7-1185G7</td></tr>
              <tr><th>Memory</th><td>16GB DDR4 RAM</td></tr>
              <tr><th>Storage</th><td>512GB NVMe SSD</td></tr>
            </table>
            <p>20W9S23S00</p>
          </body>
        </html>
        """

        result = candidate_from_manufacturer_page(
            html,
            "Lenovo",
            "20W9S23S00",
            "https://psref.lenovo.com/Search?kw=20W9S23S00",
        )

        self.assertIsNotNone(result)
        assert result is not None
        specs = result["enriched_specs"]
        self.assertEqual(result["source"], "manufacturer:lenovo")
        self.assertGreaterEqual(result["score"], 12)
        self.assertEqual(specs["search_model"], "ThinkPad X1 Carbon Gen 9")
        self.assertEqual(specs["form_factor"], "laptop")
        self.assertEqual(specs["cpu_short"], "i7-1185G7")
        self.assertEqual(specs["ram_gb"], 16)
        self.assertEqual(specs["storage"], [{"size_gb": 512, "type": "NVMe"}])

    def test_hp_page_enriches_product_number(self):
        html = """
        <html>
          <head><title>HP EliteOne 800 G5 All-in-One PC</title></head>
          <body>
            <h1>HP EliteOne 800 G5 All-in-One PC</h1>
            <dl>
              <dt>Product Name</dt><dd>HP EliteOne 800 G5 All-in-One</dd>
              <dt>Processor</dt><dd>Intel Core i5-9500</dd>
              <dt>Memory</dt><dd>16 GB DDR4 memory</dd>
              <dt>Hard Drive</dt><dd>256 GB SSD</dd>
            </dl>
            <p>Product number 7YX45UT</p>
          </body>
        </html>
        """

        result = lookup_manufacturer_specs(
            {"brand": "HP"},
            "7YX45UT",
            fetcher=lambda _url: html,
            max_pages=1,
        )

        self.assertIsNotNone(result)
        assert result is not None
        specs = result["enriched_specs"]
        self.assertEqual(specs["search_model"], "HP EliteOne 800 G5 All-in-One")
        self.assertEqual(specs["form_factor"], "all-in-one")
        self.assertEqual(specs["cpu_short"], "i5-9500")
        self.assertEqual(specs["ram_gb"], 16)
        self.assertEqual(specs["storage"], [{"size_gb": 256, "type": "SSD"}])

    def test_dell_page_enriches_service_tag_or_model(self):
        html = """
        <html>
          <head><title>Dell OptiPlex 7060 Desktop Support</title></head>
          <body>
            <h1>Dell OptiPlex 7060 Desktop</h1>
            <table>
              <tr><td>Product</td><td>Dell OptiPlex 7060</td></tr>
              <tr><td>CPU</td><td>Intel Core i5-8500</td></tr>
              <tr><td>RAM</td><td>16GB RAM</td></tr>
              <tr><td>Storage</td><td>256GB SSD</td></tr>
            </table>
            <p>ABC1234</p>
          </body>
        </html>
        """

        result = candidate_from_manufacturer_page(
            html,
            "Dell",
            "ABC1234",
            "https://www.dell.com/support/home/en-ca/product-support/servicetag/ABC1234/overview",
        )

        self.assertIsNotNone(result)
        assert result is not None
        specs = result["enriched_specs"]
        self.assertEqual(specs["search_model"], "Dell OptiPlex 7060")
        self.assertEqual(specs["form_factor"], "desktop")
        self.assertEqual(specs["cpu_short"], "i5-8500")

    def test_low_confidence_or_wrong_brand_is_rejected(self):
        html = "<html><title>Dell Latitude</title><body>Dell Latitude 7420 20W9S23S00</body></html>"

        result = candidate_from_manufacturer_page(
            html,
            "Lenovo",
            "20W9S23S00",
            "https://example.test",
        )

        self.assertIsNone(result)

    def test_brand_identifier_only_page_is_not_enough_to_identify(self):
        html = "<html><title>Lenovo support</title><body>Lenovo 20W9S23S00</body></html>"

        result = candidate_from_manufacturer_page(
            html,
            "Lenovo",
            "20W9S23S00",
            "https://pcsupport.lenovo.com/search?query=20W9S23S00",
        )

        self.assertIsNone(result)

    def test_lookup_exits_after_first_high_confidence_candidate(self):
        calls = []
        good_html = """
        <html>
          <title>Lenovo ThinkPad X1 Carbon Gen 9</title>
          <body>
            <h1>Lenovo ThinkPad X1 Carbon Gen 9 Laptop</h1>
            <table>
              <tr><th>Product Name</th><td>ThinkPad X1 Carbon Gen 9</td></tr>
              <tr><th>Processor</th><td>Intel Core i7-1185G7</td></tr>
              <tr><th>Memory</th><td>16GB RAM</td></tr>
              <tr><th>Storage</th><td>512GB SSD</td></tr>
            </table>
            20W9S23S00
          </body>
        </html>
        """

        def fetcher(url):
            calls.append(url)
            return good_html

        result = lookup_manufacturer_specs(
            {"brand": "Lenovo"},
            "20W9S23S00",
            fetcher=fetcher,
            max_pages=4,
        )

        self.assertIsNotNone(result)
        self.assertEqual(len(calls), 1)

    def test_configured_lookup_is_opt_in_and_caches_by_brand_identifier(self):
        self.assertIsNone(build_manufacturer_lookup({}))

        calls = []
        html = """
        <html>
          <title>HP EliteOne 800 G5 All-in-One PC</title>
          <body>
            <h1>HP EliteOne 800 G5 All-in-One PC</h1>
            <dl>
              <dt>Product Name</dt><dd>HP EliteOne 800 G5 All-in-One</dd>
              <dt>Processor</dt><dd>Intel Core i5-9500</dd>
            </dl>
            7YX45UT
          </body>
        </html>
        """

        lookup = build_manufacturer_lookup(
            {
                "manufacturer_lookup": {
                    "enabled": True,
                    "max_pages": 1,
                    "timeout_seconds": 1,
                }
            }
        )
        self.assertIsNotNone(lookup)
        assert lookup is not None

        from pc_pricer import manufacturer_lookup as manufacturer_module

        original_fetch = manufacturer_module._fetch_url
        try:
            manufacturer_module._fetch_url = lambda url, timeout_seconds: calls.append((url, timeout_seconds)) or html
            first = lookup({"brand": "HP"}, "7YX45UT")
            second = lookup({"brand": "HP"}, "7YX45UT")
        finally:
            manufacturer_module._fetch_url = original_fetch

        self.assertIs(first, second)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], 1)

    def test_unknown_brand_still_gets_generic_official_search_urls(self):
        urls = manufacturer_lookup_urls("Framework", "FRANBMCP07")

        self.assertIn("https://www.framework.com/search?q=FRANBMCP07", urls)
        self.assertIn("https://support.framework.com/search?q=FRANBMCP07", urls)


if __name__ == "__main__":
    unittest.main()
