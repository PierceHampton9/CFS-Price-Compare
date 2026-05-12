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
        self.assertIn("Sources:           eBay: 5, retailer: 2", report)
        self.assertIn("Confidence flags: none", report)

    def test_formats_filter_summary_when_present(self):
        report = format_price_report(
            {
                "median_price_cad": 250,
                "iqr_low_cad": 200,
                "iqr_high_cad": 300,
                "count": 3,
                "sold_count": 0,
                "asking_count": 3,
                "source_counts": {"ebay": 3},
                "query_tier": None,
                "target_condition": "good",
                "excluded_count": 3,
                "excluded_reasons": {
                    "condition_mismatch": 1,
                    "parts_or_accessory": 1,
                    "unknown_condition": 1,
                },
                "confidence_flags": [],
                "supporting_listings": [],
            }
        )

        self.assertIn("Target condition:  good", report)
        self.assertIn("Filtered out:      3", report)
        self.assertIn("condition mismatch: 1", report)
        self.assertIn("parts/accessory listing: 1", report)
        self.assertIn("unknown condition: 1", report)

    def test_formats_detected_specs_and_queries_when_present(self):
        report = format_price_report(
            {
                "median_price_cad": 300,
                "iqr_low_cad": 280,
                "iqr_high_cad": 320,
                "count": 2,
                "sold_count": 0,
                "asking_count": 2,
                "source_counts": {"ebay": 2},
                "query_tier": 2,
                "specs": {
                    "brand": "Lenovo",
                    "model": "ThinkPad X13 Yoga",
                    "cpu_short": "i5-1135G7",
                    "ram_gb": 16,
                },
                "queries": [
                    {
                        "text": "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB",
                        "tier": 2,
                    }
                ],
                "confidence_flags": [],
                "supporting_listings": [],
            }
        )

        self.assertIn("Detected specs:    Lenovo ThinkPad X13 Yoga i5-1135G7 16GB", report)
        self.assertIn("Queries used:", report)
        self.assertIn("T2: Lenovo ThinkPad X13 Yoga i5-1135G7 16GB", report)

    def test_formats_manual_non_computer_specs(self):
        report = format_price_report(
            {
                "median_price_cad": 420,
                "iqr_low_cad": 400,
                "iqr_high_cad": 450,
                "count": 2,
                "sold_count": 0,
                "asking_count": 2,
                "source_counts": {"ebay": 2},
                "query_tier": 1,
                "specs": {
                    "device_type": "monitor",
                    "brand": "Dell",
                    "model": "U2419H",
                    "size": '24"',
                    "resolution": "1080p",
                    "refresh_rate": "60Hz",
                    "input_method": "manual",
                },
                "confidence_flags": [],
                "supporting_listings": [],
            }
        )

        self.assertIn('Manual monitor:    Dell U2419H 24" 1080p 60Hz', report)

    def test_formats_manual_phone_variant_and_screen_size(self):
        report = format_price_report(
            {
                "median_price_cad": 650,
                "iqr_low_cad": 620,
                "iqr_high_cad": 680,
                "count": 2,
                "sold_count": 0,
                "asking_count": 2,
                "source_counts": {"ebay": 2},
                "query_tier": 1,
                "specs": {
                    "device_type": "phone",
                    "brand": "Apple",
                    "model": "iPhone 13",
                    "variant": "Pro Max",
                    "screen_size": '6.7"',
                    "storage_capacity": "128GB",
                    "carrier": "unlocked",
                    "input_method": "manual",
                },
                "confidence_flags": [],
                "supporting_listings": [],
            }
        )

        self.assertIn('Manual phone:    Apple iPhone 13 Pro Max 6.7" 128GB unlocked', report)

    def test_unknown_device_type_does_not_render_as_computer(self):
        report = format_price_report(
            {
                "median_price_cad": 100,
                "iqr_low_cad": 90,
                "iqr_high_cad": 110,
                "count": 1,
                "sold_count": 0,
                "asking_count": 1,
                "source_counts": {"ebay": 1},
                "query_tier": 1,
                "specs": {
                    "device_type": "scanner",
                    "brand": "Fujitsu",
                    "model": "ScanSnap",
                    "cpu": "not relevant",
                    "ram_gb": 8,
                    "input_method": "manual",
                },
                "confidence_flags": [],
                "supporting_listings": [],
            }
        )

        self.assertNotIn("Manual scanner:", report)
        self.assertNotIn("Fujitsu ScanSnap not relevant 8GB", report)

    def test_detected_specs_hide_machine_type_model(self):
        report = format_price_report(
            {
                "median_price_cad": 300,
                "iqr_low_cad": 280,
                "iqr_high_cad": 320,
                "count": 2,
                "sold_count": 0,
                "asking_count": 2,
                "source_counts": {"ebay": 2},
                "query_tier": 3,
                "specs": {
                    "brand": "LENOVO",
                    "model": "20W9S23S00",
                    "model_is_machine_type": True,
                    "cpu_short": "i7-1185G7",
                    "ram_gb": 16,
                },
                "confidence_flags": [],
                "supporting_listings": [],
            }
        )

        self.assertIn("Detected specs:    LENOVO i7-1185G7 16GB", report)
        self.assertNotIn("20W9S23S00", report)

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

    def test_formats_asking_adjusted_estimate_and_separate_warnings(self):
        report = format_price_report(
            {
                "count": 2,
                "median_price_cad": 500,
                "asking_median_price_cad": 500,
                "conservative_low_cad": 450,
                "conservative_high_cad": 475,
                "iqr_low_cad": 450,
                "iqr_high_cad": 550,
                "sold_count": 0,
                "asking_count": 2,
                "source_counts": {"ebay": 2},
                "query_tier": 2,
                "pricing_basis": "asking_adjusted",
                "asking_only_discount_low": 0.05,
                "asking_only_discount_high": 0.10,
                "confidence_flags": ["low_comparable_count"],
                "pricing_limitations": ["asking_prices_only"],
                "listing_warnings": ["unknown_shipping", "non_canadian_location"],
                "supporting_listings": [],
            }
        )

        self.assertIn("Conservative est.: $450.00 CAD - $475.00 CAD", report)
        self.assertIn("Asking median:     $500.00 CAD", report)
        self.assertIn("Pricing basis:    active asking listings, discounted 5-10%", report)
        self.assertIn("Confidence flags: Low comparable count", report)
        self.assertIn("Pricing limits:   Asking prices only", report)
        self.assertIn("Listing warnings: Unknown shipping", report)
        self.assertIn("Non-Canadian location", report)
        self.assertNotIn("Sold / asking:", report)

    def test_formats_configured_asking_adjustment_percentages(self):
        report = format_price_report(
            {
                "count": 1,
                "median_price_cad": 500,
                "asking_median_price_cad": 500,
                "conservative_low_cad": 400,
                "conservative_high_cad": 450,
                "iqr_low_cad": 500,
                "iqr_high_cad": 500,
                "sold_count": 0,
                "asking_count": 1,
                "source_counts": {"ebay": 1},
                "query_tier": 2,
                "pricing_basis": "asking_adjusted",
                "asking_only_discount_low": 0.10,
                "asking_only_discount_high": 0.20,
                "confidence_flags": [],
                "supporting_listings": [],
            }
        )

        self.assertIn("Pricing basis:    active asking listings, discounted 10-20%", report)

    def test_formats_unknown_asking_discount_range_without_fake_percent(self):
        report = format_price_report(
            {
                "count": 1,
                "median_price_cad": 500,
                "asking_median_price_cad": 500,
                "conservative_low_cad": 450,
                "conservative_high_cad": 475,
                "iqr_low_cad": 500,
                "iqr_high_cad": 500,
                "sold_count": 0,
                "asking_count": 1,
                "source_counts": {"ebay": 1},
                "query_tier": 2,
                "pricing_basis": "asking_adjusted",
                "confidence_flags": [],
                "supporting_listings": [],
            }
        )

        self.assertIn("Pricing basis:    active asking listings, discounted unknown range", report)

    def test_formats_mixed_and_unknown_pricing_basis(self):
        mixed_report = format_price_report(
            {
                "count": 2,
                "median_price_cad": 300,
                "iqr_low_cad": 280,
                "iqr_high_cad": 320,
                "sold_count": 1,
                "asking_count": 1,
                "source_counts": {"ebay": 2},
                "query_tier": 2,
                "pricing_basis": "mixed",
                "confidence_flags": [],
                "supporting_listings": [],
            }
        )
        unknown_report = format_price_report(
            {
                "count": 1,
                "median_price_cad": 300,
                "iqr_low_cad": 300,
                "iqr_high_cad": 300,
                "sold_count": 0,
                "asking_count": 0,
                "source_counts": {"ebay": 1},
                "query_tier": 2,
                "pricing_basis": "unknown",
                "confidence_flags": [],
                "supporting_listings": [],
            }
        )

        self.assertIn("Pricing basis:    sold and asking listings", mixed_report)
        self.assertIn("Pricing basis:    unknown", unknown_report)

    def test_formats_source_quotes_and_source_errors(self):
        report = format_price_report(
            {
                "count": 1,
                "median_price_cad": 433.33,
                "iqr_low_cad": 300,
                "iqr_high_cad": 500,
                "sold_count": 0,
                "asking_count": 1,
                "source_counts": {"ebay": 1, "refurb_io": 1},
                "query_tier": 1,
                "pricing_basis": "weighted_sources",
                "source_basis": "weighted_source_quotes",
                "source_quotes": [
                    {"source": "ebay", "price_cad": 300, "verified": False, "weight": 1, "listing_count": 1},
                    {"source": "refurb_io", "price_cad": 500, "verified": True, "weight": 2, "listing_count": 1},
                ],
                "source_errors": [{"source": "amazon_renewed", "message": "blocked"}],
                "source_diagnostics": [
                    {
                        "source": "refurb_io",
                        "title": "Lenovo ThinkPad X13 Yoga",
                        "source_match_verified": False,
                        "source_match_reasons": ["storage_mismatch"],
                        "filter_exclusion_reason": None,
                        "generated_query_text": "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB",
                    }
                ],
                "confidence_flags": ["source_disagreement", "source_unavailable"],
                "supporting_listings": [],
            }
        )

        self.assertIn("Median price:      $433.33 CAD", report)
        self.assertIn("Source quote range:  $300.00 CAD - $500.00 CAD", report)
        self.assertIn("Sources:           eBay: 1, Refurb.io: 1", report)
        self.assertIn("Pricing basis:    weighted source quote average", report)
        self.assertIn("Source basis:     weighted source quotes", report)
        self.assertIn("Source quotes:    eBay: $300.00 CAD, weight 1, 1 listing", report)
        self.assertIn("Refurb.io: $500.00 CAD verified, weight 2, 1 listing", report)
        self.assertIn("Source errors:    Amazon Renewed", report)
        self.assertIn("Source diagnostics:", report)
        self.assertIn("Refurb.io: not verified - Lenovo ThinkPad X13 Yoga", report)
        self.assertIn("match: storage_mismatch", report)
        self.assertIn("Source disagreement", report)

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
