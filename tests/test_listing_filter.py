import unittest

from pc_pricer.listing_filter import exclusion_reason, filter_listings


class ListingFilterTests(unittest.TestCase):
    def test_filters_to_target_condition(self):
        listings = [
            _listing("Used laptop", "good"),
            _listing("New laptop", "mint"),
            _listing("Unknown laptop", None),
        ]

        result = filter_listings(listings, target_condition="good")

        self.assertEqual([listing["title"] for listing in result["listings"]], ["Used laptop"])
        self.assertEqual(result["excluded_count"], 2)
        self.assertEqual(result["excluded_reasons"], {"condition_mismatch": 2})
        self.assertEqual(result["target_condition"], "good")

    def test_any_condition_keeps_non_parts_listings(self):
        listings = [
            _listing("Used laptop", "good"),
            _listing("New laptop", "mint"),
        ]

        result = filter_listings(listings, target_condition="any")

        self.assertEqual(len(result["listings"]), 2)
        self.assertEqual(result["excluded_count"], 0)
        self.assertEqual(result["target_condition"], "any")

    def test_excludes_parts_and_accessory_titles(self):
        listings = [
            _listing("Lenovo ThinkPad X13 Yoga", "good"),
            _listing("Lenovo ThinkPad X13 Yoga motherboard i5-1135G7", "mint"),
            _listing("ThinkPad X13 Yoga replacement keyboard", "good"),
            _listing("ThinkPad X13 Yoga for parts", "parts"),
        ]

        result = filter_listings(listings, target_condition="any")

        self.assertEqual([listing["title"] for listing in result["listings"]], ["Lenovo ThinkPad X13 Yoga"])
        self.assertEqual(result["excluded_reasons"], {"parts_or_accessory": 3})

    def test_exclusion_reason_prefers_parts_over_condition_mismatch(self):
        listing = _listing("ThinkPad X13 Yoga motherboard", "mint")

        self.assertEqual(exclusion_reason(listing, target_condition="good"), "parts_or_accessory")


def _listing(title, condition_norm):
    return {
        "title": title,
        "condition_norm": condition_norm,
    }


if __name__ == "__main__":
    unittest.main()
