import unittest

from pc_pricer.aggregator import aggregate_listings
from pc_pricer.reporter import format_price_report


class ReporterTests(unittest.TestCase):
    def test_formats_price_summary(self):
        report = format_price_report(
            {
                "median_price_cad": 325,
                "iqr_low_cad": 300,
                "iqr_high_cad": 360,
                "count": 7,
                "sold_count": 4,
                "asking_count": 3,
                "source_counts": {"ebay": 5, "retailer": 2},
                "query_tier": 1,
                "confidence_flags": [],
                "supporting_listings": [],
            }
        )

        self.assertIn("Median price:      $325.00 CAD", report)
        self.assertIn("Comparable range:  $300.00 CAD - $360.00 CAD", report)
        self.assertIn("Comparables:       7", report)
        self.assertIn("Sold / asking:     4 sold, 3 asking", report)
        self.assertIn("Sources:           ebay: 5, retailer: 2", report)
        self.assertIn("Confidence flags: none", report)

    def test_formats_confidence_flags(self):
        report = format_price_report(
            {
                "count": 2,
                "median_price_cad": 200,
                "iqr_low_cad": 100,
                "iqr_high_cad": 300,
                "sold_count": 0,
                "asking_count": 2,
                "source_counts": {"ebay": 2},
                "query_tier": 3,
                "confidence_flags": ["low_comparable_count", "wide_price_range"],
                "supporting_listings": [],
            }
        )

        self.assertIn("Confidence flags: Low comparable count, Wide price range", report)

    def test_formats_no_comparables(self):
        report = format_price_report(
            {
                "count": 0,
                "confidence_flags": ["no_comparables"],
                "supporting_listings": [],
            }
        )

        self.assertIn("No usable comparable listings found.", report)
        self.assertIn("Confidence flags: No usable comparable listings", report)

    def test_formats_supporting_listings(self):
        report = format_price_report(
            {
                "median_price_cad": 325,
                "iqr_low_cad": 300,
                "iqr_high_cad": 360,
                "count": 1,
                "sold_count": 0,
                "asking_count": 1,
                "source_counts": {"ebay": 1},
                "query_tier": 2,
                "confidence_flags": [],
                "supporting_listings": [
                    {
                        "source": "ebay",
                        "title": "Lenovo ThinkPad X13 Yoga",
                        "item_price_cad": 300,
                        "shipping_cad": 25,
                        "total_price_cad": 325,
                        "shipping_is_estimated": False,
                        "condition_raw": "Used",
                        "condition_norm": "good",
                        "is_sold": False,
                        "query_tier": 2,
                        "url": "https://www.ebay.ca/itm/example",
                    }
                ],
            }
        )

        self.assertIn("Supporting listings", report)
        self.assertIn("1. Lenovo ThinkPad X13 Yoga", report)
        self.assertIn("$325.00 CAD total ($300.00 CAD item + $25.00 CAD shipping)", report)
        self.assertIn("Status:    asking", report)
        self.assertIn("Condition: good (Used)", report)
        self.assertIn("Tier:      2", report)

    def test_unknown_shipping_is_not_called_total(self):
        report = format_price_report(
            {
                "median_price_cad": 180,
                "iqr_low_cad": 180,
                "iqr_high_cad": 180,
                "count": 1,
                "sold_count": 0,
                "asking_count": 1,
                "source_counts": {"ebay": 1},
                "query_tier": 2,
                "confidence_flags": [],
                "supporting_listings": [
                    {
                        "title": "Dell OptiPlex",
                        "item_price_cad": 180,
                        "shipping_cad": None,
                        "total_price_cad": 180,
                        "shipping_is_estimated": True,
                    }
                ],
            }
        )

        self.assertIn("$180.00 CAD item price + unknown shipping", report)
        self.assertNotIn("$180.00 CAD total", report)

    def test_formats_real_aggregation_result(self):
        aggregation = aggregate_listings(
            [
                {
                    "source": "ebay",
                    "title": "Listing 1",
                    "item_price_cad": 200,
                    "shipping_cad": 20,
                    "total_price_cad": 220,
                    "shipping_is_estimated": False,
                    "condition_raw": "Used",
                    "condition_norm": "good",
                    "is_sold": False,
                    "query_tier": 1,
                    "url": "https://www.ebay.ca/itm/1",
                },
                {
                    "source": "ebay",
                    "title": "Listing 2",
                    "item_price_cad": 260,
                    "shipping_cad": 20,
                    "total_price_cad": 280,
                    "shipping_is_estimated": False,
                    "condition_raw": "Used",
                    "condition_norm": "good",
                    "is_sold": True,
                    "query_tier": 1,
                    "url": "https://www.ebay.ca/itm/2",
                },
            ],
            warn_below_comparables=1,
        )

        report = format_price_report(aggregation)

        self.assertIn("Median price:      $250.00 CAD", report)
        self.assertIn("Sold / asking:     1 sold, 1 asking", report)
        self.assertIn("Supporting listings", report)
        self.assertIn("Condition: good (Used)", report)


if __name__ == "__main__":
    unittest.main()
