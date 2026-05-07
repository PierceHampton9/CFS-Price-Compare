import unittest

from pc_pricer.pricing_pipeline import price_specs


class PricingPipelineTests(unittest.TestCase):
    def test_prices_specs_with_tiered_queries_and_dedupes_results(self):
        source = FakeSource(
            {
                "20XW004AUS": [
                    _listing("Exact SKU laptop", 500, "https://www.ebay.ca/itm/1", item_id="item-1"),
                    _listing("Duplicate exact SKU laptop", 500, "https://www.ebay.ca/itm/dup-a", item_id="dup"),
                ],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB": [
                    _listing("Duplicate better title", 520, "https://www.ebay.ca/itm/dup-b", item_id="dup"),
                    _listing("New laptop", 900, "https://www.ebay.ca/itm/new", condition_raw="New", item_id="new"),
                    _listing("X13 Yoga motherboard", 250, "https://www.ebay.ca/itm/board", item_id="board"),
                ],
                "Lenovo ThinkPad X13 Yoga": [
                    _listing("Family listing", 540, "https://www.ebay.ca/itm/3", item_id="item-3"),
                ],
            }
        )

        result = price_specs(_laptop_specs(), source, limit_per_query=5, target_condition="good")

        self.assertEqual(source.calls, [
            ("20XW004AUS", 5),
            ("Lenovo ThinkPad X13 Yoga i5-1135G7 16GB", 5),
            ("Lenovo ThinkPad X13 Yoga", 5),
        ])
        self.assertEqual(result["raw_listing_count"], 6)
        self.assertEqual(result["deduped_listing_count"], 5)
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["median_price_cad"], 500.00)
        self.assertEqual(result["query_tier"], 1)
        self.assertEqual(result["excluded_reasons"], {
            "condition_mismatch": 1,
            "parts_or_accessory": 1,
        })
        self.assertEqual([listing["query_tier"] for listing in result["supporting_listings"]], [1, 1, 3])
        self.assertEqual(result["queries"][0]["text"], "20XW004AUS")
        self.assertNotIn("raw", result["specs"])
        self.assertNotIn("serial_number", result["specs"])

    def test_no_queries_returns_clear_empty_result(self):
        result = price_specs({}, FakeSource({}), limit_per_query=5)

        self.assertEqual(result["count"], 0)
        self.assertEqual(result["queries"], [])
        self.assertIn("no_queries", result["confidence_flags"])
        self.assertIn("no_comparables", result["confidence_flags"])

    def test_url_dedupe_still_works_without_item_ids(self):
        source = FakeSource(
            {
                "20XW004AUS": [
                    _listing("Listing 1", 500, "https://www.ebay.ca/itm/1"),
                ],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB": [
                    _listing("Listing 1 duplicate", 520, "https://www.ebay.ca/itm/1"),
                ],
                "Lenovo ThinkPad X13 Yoga": [],
            }
        )

        result = price_specs(_laptop_specs(), source, limit_per_query=5)

        self.assertEqual(result["raw_listing_count"], 2)
        self.assertEqual(result["deduped_listing_count"], 1)
        self.assertEqual(result["median_price_cad"], 500.00)

    def test_dedupes_when_only_one_copy_has_item_id(self):
        source = FakeSource(
            {
                "20XW004AUS": [
                    _listing("Listing 1", 500, "https://www.ebay.ca/itm/1", item_id="item-1"),
                ],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB": [
                    _listing("Listing 1 duplicate", 520, "https://www.ebay.ca/itm/1"),
                ],
                "Lenovo ThinkPad X13 Yoga": [],
            }
        )

        result = price_specs(_laptop_specs(), source, limit_per_query=5)

        self.assertEqual(result["raw_listing_count"], 2)
        self.assertEqual(result["deduped_listing_count"], 1)
        self.assertEqual(result["median_price_cad"], 500.00)

    def test_passes_aggregation_options(self):
        source = FakeSource(
            {
                "20XW004AUS": [
                    _listing("Listing 1", 500, "https://www.ebay.ca/itm/1"),
                    _listing("Listing 2", 520, "https://www.ebay.ca/itm/2"),
                ],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB": [],
                "Lenovo ThinkPad X13 Yoga": [],
            }
        )

        result = price_specs(
            _laptop_specs(),
            source,
            limit_per_query=5,
            warn_below_comparables=2,
            support_limit=1,
        )

        self.assertEqual(result["confidence_flags"], [])
        self.assertEqual(result["pricing_limitations"], ["asking_prices_only"])
        self.assertEqual(result["pricing_basis"], "asking_adjusted")
        self.assertEqual(result["conservative_low_cad"], 484.5)
        self.assertEqual(result["conservative_high_cad"], 510.0)
        self.assertEqual(len(result["supporting_listings"]), 1)

    def test_passes_device_type_to_listing_filter(self):
        source = FakeSource(
            {
                "Apple iPhone 13 128GB unlocked": [
                    _listing("Apple iPhone 13 128GB Unlocked", 400, "https://www.ebay.ca/itm/phone"),
                    _listing("For iPhone 13 case shockproof cover", 20, "https://www.ebay.ca/itm/case"),
                ],
                "Apple iPhone 13 128GB": [],
                "Apple iPhone 13": [],
            }
        )

        result = price_specs(_phone_specs(), source, limit_per_query=5, target_condition="any")

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["median_price_cad"], 400)
        self.assertEqual(result["excluded_reasons"], {"parts_or_accessory": 1})

    def test_filters_phone_variant_mismatches_from_pipeline(self):
        source = FakeSource(
            {
                "Apple iPhone 13 128GB unlocked": [
                    _listing("Apple iPhone 13 128GB Unlocked", 400, "https://www.ebay.ca/itm/phone"),
                    _listing("Apple iPhone 13 mini 128GB Unlocked", 300, "https://www.ebay.ca/itm/mini"),
                ],
                "Apple iPhone 13 128GB": [],
                "Apple iPhone 13": [],
            }
        )

        result = price_specs(_phone_specs(), source, limit_per_query=5, target_condition="any")

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["median_price_cad"], 400)
        self.assertEqual(result["excluded_reasons"], {"variant_mismatch": 1})


class FakeSource:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def search(self, query, max_results):
        self.calls.append((query, max_results))
        return self.results.get(query, [])


def _laptop_specs():
    return {
        "brand": "Lenovo",
        "model": "ThinkPad X13 Yoga",
        "oem_sku": "20XW004AUS",
        "form_factor": "laptop",
        "cpu": "Intel Core i5-1135G7",
        "cpu_short": "i5-1135G7",
        "ram_gb": 16,
        "serial_number": "not reported",
        "raw": {"secret": "not reported"},
    }


def _phone_specs():
    return {
        "device_type": "phone",
        "brand": "Apple",
        "model": "iPhone 13",
        "search_model": "iPhone 13",
        "storage_capacity": "128GB",
        "carrier": "unlocked",
    }


def _listing(title, price, url, condition_raw="Used", item_id=None):
    return {
        "source": "ebay",
        "item_id": item_id,
        "title": title,
        "item_price_cad": price,
        "shipping_cad": 0,
        "total_price_cad": price,
        "shipping_is_estimated": False,
        "condition_raw": condition_raw,
        "condition_norm": None,
        "is_sold": False,
        "query_tier": None,
        "url": url,
    }


if __name__ == "__main__":
    unittest.main()
