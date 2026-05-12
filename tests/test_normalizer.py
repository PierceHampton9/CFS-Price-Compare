import unittest

from pc_pricer.normalizer import normalize_condition, normalize_listing, normalize_listings


class NormalizerTests(unittest.TestCase):
    def test_ebay_condition_mappings(self):
        cases = {
            "New": "mint",
            "Open box": "excellent",
            "Certified - Refurbished": "excellent",
            "Excellent - Refurbished": "excellent",
            "Very Good - Refurbished": "good",
            "Good - Refurbished": "good",
            "Seller refurbished": "good",
            "Used": "good",
            "For parts or not working": "parts",
        }

        for raw_condition, expected in cases.items():
            with self.subTest(raw_condition=raw_condition):
                self.assertEqual(normalize_condition("ebay", raw_condition), expected)

    def test_condition_matching_ignores_case_and_extra_spaces(self):
        self.assertEqual(normalize_condition("EBAY", "  Open   box  "), "excellent")

    def test_unknown_condition_returns_none(self):
        self.assertIsNone(normalize_condition("ebay", "Like new-ish"))

    def test_unknown_source_returns_none(self):
        self.assertIsNone(normalize_condition("unknown", "Used"))

    def test_refurb_io_condition_mappings(self):
        self.assertEqual(normalize_condition("refurb_io", "Grade A"), "good")
        self.assertEqual(normalize_condition("refurb_io", "A-Grade"), "good")
        self.assertEqual(normalize_condition("refurb_io", "Grade C"), "parts")

    def test_normalize_listing_returns_copy_with_condition_norm(self):
        listing = {
            "source": "ebay",
            "condition_raw": "Used",
            "condition_norm": None,
            "title": "Dell OptiPlex",
        }

        normalized = normalize_listing(listing)

        self.assertEqual(normalized["condition_norm"], "good")
        self.assertIsNone(listing["condition_norm"])
        self.assertIsNot(normalized, listing)

    def test_normalize_listings_normalizes_each_listing(self):
        listings = [
            {"source": "ebay", "condition_raw": "New"},
            {"source": "ebay", "condition_raw": "For parts or not working"},
        ]

        normalized = normalize_listings(listings)

        self.assertEqual([listing["condition_norm"] for listing in normalized], ["mint", "parts"])


if __name__ == "__main__":
    unittest.main()
