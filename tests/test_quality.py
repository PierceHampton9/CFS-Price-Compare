import unittest

from pc_pricer.quality import add_listing_quality_flags


class QualityTests(unittest.TestCase):
    def test_flags_asking_only_results(self):
        result = add_listing_quality_flags(
            {
                "confidence_flags": [],
                "pricing_basis": "asking_adjusted",
                "sold_count": 0,
                "asking_count": 2,
            },
            [_listing()],
        )

        self.assertIn("asking_prices_only", result["pricing_limitations"])
        self.assertEqual(result["confidence_flags"], [])

    def test_does_not_flag_active_retailer_results_as_asking_only(self):
        result = add_listing_quality_flags(
            {
                "confidence_flags": [],
                "pricing_basis": "weighted_sources",
                "sold_count": 0,
                "asking_count": 2,
            },
            [_listing(source="amazon_renewed")],
        )

        self.assertNotIn("asking_prices_only", result["pricing_limitations"])

    def test_flags_unknown_and_high_shipping(self):
        result = add_listing_quality_flags(
            {
                "confidence_flags": [],
                "sold_count": 1,
                "asking_count": 1,
            },
            [
                _listing(shipping_cad=None, shipping_is_estimated=True),
                _listing(item_price_cad=100, shipping_cad=40),
            ],
            high_shipping_cad=75,
            high_shipping_ratio=0.25,
        )

        self.assertIn("unknown_shipping", result["listing_warnings"])
        self.assertIn("high_shipping", result["listing_warnings"])
        self.assertEqual(result["confidence_flags"], [])

    def test_flags_non_canadian_locations(self):
        result = add_listing_quality_flags(
            {
                "confidence_flags": [],
                "sold_count": 1,
                "asking_count": 0,
            },
            [
                _listing(location="Calgary, AB, CA"),
                _listing(location="Harrisburg, PA, US"),
            ],
        )

        self.assertIn("non_canadian_location", result["listing_warnings"])

    def test_flags_mixed_storage_when_target_storage_differs(self):
        result = add_listing_quality_flags(
            {
                "confidence_flags": [],
                "sold_count": 0,
                "asking_count": 2,
            },
            [
                _listing(title="Lenovo ThinkPad X13 Yoga 16GB 256GB SSD", target_storage_gb=256),
                _listing(title="Lenovo ThinkPad X13 Yoga 16GB 512GB SSD", target_storage_gb=256),
            ],
        )

        self.assertIn("mixed_storage", result["listing_warnings"])


def _listing(
    item_price_cad=100,
    shipping_cad: float | None = 0,
    shipping_is_estimated=False,
    location="Calgary, AB, CA",
    source="ebay",
    title="Listing",
    target_storage_gb=None,
):
    listing = {
        "source": source,
        "title": title,
        "item_price_cad": item_price_cad,
        "shipping_cad": shipping_cad,
        "shipping_is_estimated": shipping_is_estimated,
        "location": location,
    }
    if target_storage_gb is not None:
        listing["target_storage_gb"] = target_storage_gb
    return listing


if __name__ == "__main__":
    unittest.main()
