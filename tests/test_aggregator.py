import unittest
from typing import Any

from pc_pricer.aggregator import aggregate_listings


class AggregatorTests(unittest.TestCase):
    def test_aggregates_prices_with_median_and_iqr(self):
        listings = [
            _listing(100, source="ebay", is_sold=True, query_tier=1),
            _listing(200, source="ebay", is_sold=False, query_tier=1),
            _listing(300, source="retailer", is_sold=False, query_tier=2),
            _listing(400, source="retailer", is_sold=True, query_tier=2),
        ]

        result = aggregate_listings(listings, warn_below_comparables=1)

        self.assertEqual(result["median_price_cad"], 250.00)
        self.assertEqual(result["iqr_low_cad"], 175.00)
        self.assertEqual(result["iqr_high_cad"], 325.00)
        self.assertEqual(result["price_low_cad"], 100.00)
        self.assertEqual(result["price_high_cad"], 400.00)
        self.assertEqual(result["count"], 4)
        self.assertEqual(result["sold_count"], 2)
        self.assertEqual(result["asking_count"], 2)
        self.assertEqual(result["source_counts"], {"ebay": 2, "retailer": 2})
        self.assertEqual(result["query_tier"], 1)

    def test_ignores_listings_without_prices(self):
        listings = [
            _listing(200),
            {"source": "ebay", "total_price_cad": None},
            {"source": "ebay"},
        ]

        result = aggregate_listings(listings, warn_below_comparables=1)

        self.assertEqual(result["median_price_cad"], 200.00)
        self.assertEqual(result["count"], 1)

    def test_no_comparables_returns_empty_result_with_flag(self):
        result = aggregate_listings([])

        self.assertIsNone(result["median_price_cad"])
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["confidence_flags"], ["no_comparables"])
        self.assertEqual(result["supporting_listings"], [])

    def test_flags_low_comparable_count(self):
        result = aggregate_listings([_listing(200)], warn_below_comparables=5)

        self.assertIn("low_comparable_count", result["confidence_flags"])

    def test_flags_wide_price_range(self):
        result = aggregate_listings(
            [_listing(100), _listing(100), _listing(500), _listing(500)],
            warn_below_comparables=1,
            wide_iqr_ratio=0.40,
        )

        self.assertIn("wide_price_range", result["confidence_flags"])

    def test_supporting_listings_are_limited_and_near_median_within_tier(self):
        listings = [_listing(price, title=f"Listing {price}") for price in [100, 200, 300, 400, 500, 600]]

        result = aggregate_listings(listings, warn_below_comparables=1, support_limit=3)

        self.assertEqual(len(result["supporting_listings"]), 3)
        self.assertEqual(
            [listing["title"] for listing in result["supporting_listings"]],
            ["Listing 300", "Listing 400", "Listing 200"],
        )
        self.assertNotIn("_price", result["supporting_listings"][0])

    def test_supporting_listings_prioritize_better_query_tiers(self):
        listings = [
            _listing(300, query_tier=3, title="Tier 3 near median"),
            _listing(100, query_tier=1, title="Tier 1 farther from median"),
            _listing(500, query_tier=2, title="Tier 2 farther from median"),
        ]

        result = aggregate_listings(listings, warn_below_comparables=1, support_limit=3)

        self.assertEqual(
            [listing["title"] for listing in result["supporting_listings"]],
            [
                "Tier 1 farther from median",
                "Tier 2 farther from median",
                "Tier 3 near median",
            ],
        )

    def test_supporting_listings_put_unknown_tiers_last(self):
        listings = [
            _listing(300, query_tier=None, title="Unknown tier near median"),
            _listing(100, query_tier=1, title="Known tier farther from median"),
        ]

        result = aggregate_listings(listings, warn_below_comparables=1, support_limit=2)

        self.assertEqual(
            [listing["title"] for listing in result["supporting_listings"]],
            ["Known tier farther from median", "Unknown tier near median"],
        )

    def test_supports_string_prices_and_query_tiers(self):
        result = aggregate_listings(
            [
                _listing("250.50", query_tier="2"),
                _listing("300.50", query_tier="3"),
            ],
            warn_below_comparables=1,
        )

        self.assertEqual(result["median_price_cad"], 275.50)
        self.assertEqual(result["query_tier"], 2)


def _listing(
    price: Any,
    source: str = "ebay",
    is_sold: bool = False,
    query_tier: Any = 1,
    title: str = "Listing",
) -> dict[str, Any]:
    return {
        "source": source,
        "title": title,
        "total_price_cad": price,
        "is_sold": is_sold,
        "query_tier": query_tier,
    }


if __name__ == "__main__":
    unittest.main()
