import unittest

from pc_pricer.pricing_pipeline import price_specs, reprice_existing_result


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
            ("Lenovo 20XW004AUS", 5),
            ("20XW004AUS", 5),
            ("Lenovo ThinkPad X13 Yoga i5-1135G7 16GB", 5),
            ("Lenovo ThinkPad X13 Yoga", 5),
        ])
        self.assertEqual(result["raw_listing_count"], 6)
        self.assertEqual(result["deduped_listing_count"], 5)
        self.assertEqual(result["count"], 4)
        self.assertEqual(result["median_price_cad"], 520.00)
        self.assertEqual(result["query_tier"], 1)
        self.assertEqual(result["excluded_reasons"], {
            "parts_or_accessory": 1,
        })
        self.assertEqual([listing["query_tier"] for listing in result["supporting_listings"]], [1, 1, 2, 3])
        self.assertEqual(result["queries"][0]["text"], "Lenovo 20XW004AUS")
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

    def test_ignores_broad_fallback_when_specific_tier_has_enough_comparables(self):
        source = FakeSource(
            {
                "Dell OptiPlex 7060 i5-8500 16GB 256GB SSD": [
                    _listing(f"Dell OptiPlex 7060 i5-8500 16GB 256GB SSD #{index}", price, f"https://www.ebay.ca/itm/{index}")
                    for index, price in enumerate([300, 310, 320, 330, 340], start=1)
                ],
                "i5-8500 16GB 256GB SSD desktop": [
                    _listing("Dell OptiPlex 7060 i5-8500 16GB 256GB SSD", 150, "https://www.ebay.ca/itm/broad")
                ],
                "i5-8500 16GB desktop": [],
            },
            name="ebay",
        )

        result = price_specs(
            {
                "device_type": "computer",
                "brand": "Dell",
                "model": "OptiPlex 7060",
                "search_model": "OptiPlex 7060",
                "form_factor": "desktop",
                "cpu_short": "i5-8500",
                "ram_gb": 16,
                "storage": [{"size_gb": 256, "type": "SSD"}],
            },
            source,
            limit_per_query=5,
            target_condition="any",
            warn_below_comparables=5,
        )

        self.assertEqual(result["count"], 5)
        self.assertEqual(result["median_price_cad"], 320.00)
        self.assertEqual(result["excluded_reasons"], {"lower_tier_fallback": 1})
        self.assertEqual({listing["query_tier"] for listing in result["all_comparable_listings"]}, {1})

    def test_keeps_broad_fallback_until_specific_tier_meets_comparable_target(self):
        source = FakeSource(
            {
                "Dell OptiPlex 7060 i5-8500 16GB 256GB SSD": [
                    _listing(f"Dell OptiPlex 7060 i5-8500 16GB 256GB SSD #{index}", price, f"https://www.ebay.ca/itm/{index}")
                    for index, price in enumerate([300, 310, 320, 330, 340], start=1)
                ],
                "i5-8500 16GB 256GB SSD desktop": [
                    _listing("Dell OptiPlex 7060 i5-8500 16GB 256GB SSD fallback", 350, "https://www.ebay.ca/itm/fallback")
                ],
                "i5-8500 16GB desktop": [],
            },
            name="ebay",
        )

        result = price_specs(
            {
                "device_type": "computer",
                "brand": "Dell",
                "model": "OptiPlex 7060",
                "search_model": "OptiPlex 7060",
                "form_factor": "desktop",
                "cpu_short": "i5-8500",
                "ram_gb": 16,
                "storage": [{"size_gb": 256, "type": "SSD"}],
            },
            source,
            limit_per_query=5,
            target_condition="any",
            warn_below_comparables=10,
        )

        self.assertEqual(result["count"], 6)
        self.assertNotIn("lower_tier_fallback", result["excluded_reasons"])
        self.assertEqual({listing["query_tier"] for listing in result["all_comparable_listings"]}, {1, 2})

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

    def test_filters_missing_phone_variant_from_pipeline(self):
        source = FakeSource(
            {
                "Apple iPhone 13 Pro 128GB unlocked": [
                    _listing("Apple iPhone 13 128GB Unlocked", 400, "https://www.ebay.ca/itm/base"),
                    _listing("Apple iPhone 13 Pro 128GB Unlocked", 650, "https://www.ebay.ca/itm/pro"),
                ],
                "Apple iPhone 13 Pro 128GB": [],
                "Apple iPhone 13 Pro": [],
            }
        )

        result = price_specs(_phone_pro_specs(), source, limit_per_query=5, target_condition="any")

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["median_price_cad"], 650)
        self.assertEqual(result["excluded_reasons"], {"variant_mismatch": 1})

    def test_verified_refurb_io_quote_weights_with_ebay_pricing(self):
        ebay = FakeSource(
            {
                "20XW004AUS": [_listing("eBay ThinkPad X13 Yoga", 300, "https://www.ebay.ca/itm/1")],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB": [],
                "Lenovo ThinkPad X13 Yoga": [],
            },
            name="ebay",
        )
        refurb = FakeSource(
            {
                "20XW004AUS": [_refurb_listing("Lenovo ThinkPad X13 Yoga Laptop i5-1135G7 16GB 256GB", 500)],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB": [],
                "Lenovo ThinkPad X13 Yoga": [],
            },
            name="refurb_io",
        )

        result = price_specs(_laptop_specs(), [ebay, refurb], limit_per_query=5)

        self.assertEqual(result["median_price_cad"], 430.83)
        self.assertEqual(result["iqr_low_cad"], 292.50)
        self.assertEqual(result["iqr_high_cad"], 500.00)
        self.assertEqual(result["source_basis"], "weighted_source_quotes")
        self.assertEqual(result["pricing_basis"], "weighted_sources")
        self.assertEqual(result["source_counts"], {"ebay": 1, "refurb_io": 1})
        self.assertEqual(result["excluded_reasons"], {})
        self.assertIn("source_disagreement", result["confidence_flags"])
        self.assertEqual([quote["source"] for quote in result["source_quotes"]], ["ebay", "refurb_io"])
        self.assertEqual([quote["weight"] for quote in result["source_quotes"]], [1, 2])
        self.assertEqual(result["supporting_listings"][0]["source"], "refurb_io")
        self.assertEqual(result["source_diagnostics"][0]["source"], "refurb_io")
        self.assertIs(result["source_diagnostics"][0]["source_match_verified"], True)
        self.assertIs(result["source_diagnostics"][0]["included_in_pricing"], True)

    def test_weak_refurb_io_match_falls_back_to_ebay(self):
        ebay = FakeSource(
            {
                "20XW004AUS": [_listing("eBay ThinkPad X13 Yoga", 300, "https://www.ebay.ca/itm/1")],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB": [],
                "Lenovo ThinkPad X13 Yoga": [],
            },
            name="ebay",
        )
        refurb = FakeSource(
            {
                "20XW004AUS": [_refurb_listing("Dell Latitude Laptop i5-1135G7 16GB 256GB", 500, model="Latitude")],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB": [],
                "Lenovo ThinkPad X13 Yoga": [],
            },
            name="refurb_io",
        )

        result = price_specs(_laptop_specs(), [ebay, refurb], limit_per_query=5)

        self.assertEqual(result["median_price_cad"], 300.00)
        self.assertEqual(result["source_basis"], "ebay_asking_adjusted")
        self.assertEqual(result["source_counts"], {"ebay": 1})
        self.assertEqual(result["source_diagnostics"][0]["source_match_reasons"], ["model_mismatch"])
        self.assertIs(result["source_diagnostics"][0]["included_in_pricing"], False)

    def test_refurb_io_uses_broader_retailer_query_when_model_is_known(self):
        refurb = FakeSource(
            {
                "20XW004AUS": [],
                "Lenovo ThinkPad X13 Yoga": [
                    _refurb_listing("Lenovo ThinkPad X13 Yoga Laptop i5-1135G7 16GB 256GB", 525)
                ],
            },
            name="refurb_io",
        )

        result = price_specs(_laptop_specs(), [refurb], limit_per_query=5)

        self.assertEqual(
            refurb.calls,
            [
                ("Lenovo 20XW004AUS", 5),
                ("20XW004AUS", 5),
                ("Lenovo ThinkPad X13 Yoga", 5),
            ],
        )
        self.assertEqual(result["median_price_cad"], 525.00)
        self.assertEqual(result["source_diagnostics"][0]["query_text"], "Lenovo ThinkPad X13 Yoga")
        self.assertEqual(
            result["source_diagnostics"][0]["generated_query_text"],
            "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB",
        )

    def test_model_number_query_can_verify_retailer_result_by_specs(self):
        specs = {
            "device_type": "computer",
            "brand": "Lenovo",
            "model": "20W9S23S00",
            "form_factor": "laptop",
            "cpu_short": "i7-1185G7",
            "ram_gb": 16,
            "storage": [{"size_gb": 512, "type": "SSD"}],
        }
        refurb = FakeSource(
            {
                "Lenovo 20W9S23S00": [
                    _refurb_listing(
                        "Lenovo ThinkPad X1 Carbon Gen 9 Laptop i7-1185G7 16GB 512GB",
                        650,
                        model="ThinkPad X1 Carbon Gen 9",
                    )
                ],
            },
            name="refurb_io",
        )

        result = price_specs(specs, [refurb], limit_per_query=5)

        self.assertEqual(refurb.calls[0], ("Lenovo 20W9S23S00", 5))
        self.assertEqual(result["device_identification"]["status"], "identified")
        self.assertEqual(result["specs"]["search_model"], "ThinkPad X1 Carbon Gen 9")
        self.assertEqual(result["median_price_cad"], 650.00)
        self.assertEqual(result["source_diagnostics"][0]["source_match_reasons"], [])
        self.assertIs(result["source_diagnostics"][0]["source_match_verified"], True)

    def test_manufacturer_lookup_enriches_model_number_before_pricing_queries(self):
        specs = {
            "device_type": "computer",
            "brand": "Lenovo",
            "model": "20W9S23S00",
            "model_is_machine_type": True,
        }
        source = FakeSource(
            {
                "Lenovo 20W9S23S00": [],
                "20W9S23S00": [],
                "Lenovo ThinkPad X1 Carbon Gen 9 i7-1185G7 16GB": [
                    _listing(
                        "Lenovo ThinkPad X1 Carbon Gen 9 i7-1185G7 16GB 512GB",
                        700,
                        "https://www.ebay.ca/itm/x1",
                    )
                ],
                "Lenovo ThinkPad X1 Carbon Gen 9": [],
            },
            name="ebay",
        )

        result = price_specs(
            specs,
            [source],
            limit_per_query=5,
            manufacturer_lookup=lambda _specs, _identifier: {
                "source": "manufacturer:lenovo",
                "title": "Lenovo ThinkPad X1 Carbon Gen 9 Laptop",
                "url": "https://psref.lenovo.com/Search?kw=20W9S23S00",
                "score": 13,
                "confidence": "high",
                "enriched_specs": {
                    "search_model": "ThinkPad X1 Carbon Gen 9",
                    "form_factor": "laptop",
                    "cpu_short": "i7-1185G7",
                    "ram_gb": 16,
                    "storage": [{"size_gb": 512, "type": "NVMe"}],
                },
            },
        )

        self.assertEqual(result["device_identification"]["source"], "manufacturer:lenovo")
        self.assertEqual(result["specs"]["search_model"], "ThinkPad X1 Carbon Gen 9")
        self.assertEqual(result["median_price_cad"], 700.00)
        self.assertIn(("Lenovo ThinkPad X1 Carbon Gen 9 i7-1185G7 16GB", 5), source.calls)

    def test_refurb_io_only_verified_result_works(self):
        refurb = FakeSource(
            {
                "20XW004AUS": [_refurb_listing("Lenovo ThinkPad X13 Yoga Laptop i5-1135G7 16GB 256GB", 525)],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB": [],
                "Lenovo ThinkPad X13 Yoga": [],
            },
            name="refurb_io",
        )

        result = price_specs(_laptop_specs(), [refurb], limit_per_query=5)

        self.assertEqual(result["median_price_cad"], 525.00)
        self.assertEqual(result["source_basis"], "weighted_source_quotes")
        self.assertEqual(result["pricing_basis"], "weighted_sources")
        self.assertEqual(result["source_counts"], {"refurb_io": 1})

    def test_verified_amazon_renewed_quote_weights_with_ebay_pricing(self):
        ebay = FakeSource(
            {
                "20XW004AUS": [_listing("eBay ThinkPad X13 Yoga", 300, "https://www.ebay.ca/itm/1")],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB": [],
                "Lenovo ThinkPad X13 Yoga": [],
            },
            name="ebay",
        )
        amazon = FakeSource(
            {
                "Lenovo ThinkPad X13 Yoga Renewed": [],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB Renewed": [
                    _amazon_listing("Lenovo ThinkPad X13 Yoga Laptop Amazon Renewed i5-1135G7 16GB 256GB", 600)
                ],
            },
            name="amazon_renewed",
        )

        result = price_specs(_laptop_specs(), [ebay, amazon], limit_per_query=5)

        self.assertEqual(
            amazon.calls,
            [
                ("Lenovo 20XW004AUS Renewed", 5),
                ("20XW004AUS Renewed", 5),
                ("Lenovo ThinkPad X13 Yoga i5-1135G7 16GB Renewed", 5),
                ("Lenovo ThinkPad X13 Yoga Renewed", 5),
            ],
        )
        amazon_status = next(status for status in result["source_statuses"] if status["source"] == "amazon_renewed")
        self.assertEqual(amazon_status["query_count"], 4)
        self.assertEqual(amazon_status["raw_listing_count"], 1)
        self.assertEqual(result["median_price_cad"], 497.50)
        self.assertEqual(result["iqr_low_cad"], 292.50)
        self.assertEqual(result["iqr_high_cad"], 600.00)
        self.assertEqual(result["source_basis"], "weighted_source_quotes")
        self.assertEqual(result["source_counts"], {"ebay": 1, "amazon_renewed": 1})
        self.assertEqual(result["excluded_reasons"], {})
        self.assertEqual([quote["source"] for quote in result["source_quotes"]], ["ebay", "amazon_renewed"])
        self.assertEqual([quote["weight"] for quote in result["source_quotes"]], [1, 2])
        self.assertEqual(result["supporting_listings"][0]["source"], "amazon_renewed")
        self.assertIs(result["source_diagnostics"][0]["source_match_verified"], True)
        self.assertIs(result["source_diagnostics"][0]["included_in_pricing"], True)

    def test_amazon_and_refurb_quotes_weight_with_ebay_when_verified(self):
        ebay = FakeSource(
            {
                "20XW004AUS": [_listing("eBay ThinkPad X13 Yoga", 300, "https://www.ebay.ca/itm/1")],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB": [],
                "Lenovo ThinkPad X13 Yoga": [],
            },
            name="ebay",
        )
        refurb = FakeSource(
            {
                "20XW004AUS": [_refurb_listing("Lenovo ThinkPad X13 Yoga Laptop i5-1135G7 16GB 256GB", 500)],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB": [],
                "Lenovo ThinkPad X13 Yoga": [],
            },
            name="refurb_io",
        )
        amazon = FakeSource(
            {
                "Lenovo ThinkPad X13 Yoga Renewed": [],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB Renewed": [
                    _amazon_listing("Lenovo ThinkPad X13 Yoga Laptop Amazon Renewed i5-1135G7 16GB 256GB", 700)
                ],
            },
            name="amazon_renewed",
        )

        result = price_specs(_laptop_specs(), [ebay, refurb, amazon], limit_per_query=5)

        self.assertEqual(result["median_price_cad"], 538.50)
        self.assertEqual([quote["source"] for quote in result["source_quotes"]], ["ebay", "refurb_io", "amazon_renewed"])
        self.assertEqual([quote["weight"] for quote in result["source_quotes"]], [1, 2, 2])
        self.assertEqual(result["source_counts"], {"ebay": 1, "refurb_io": 1, "amazon_renewed": 1})
        self.assertEqual(result["excluded_reasons"], {})

    def test_laptop_cpu_suffix_omission_is_not_a_cpu_mismatch(self):
        refurb = FakeSource(
            {
                "20XW004AUS": [
                    _refurb_listing(
                        "Lenovo ThinkPad X13 Yoga Laptop i5-1135G7 16GB 256GB",
                        525,
                    )
                ],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB": [],
                "Lenovo ThinkPad X13 Yoga": [],
            },
            name="refurb_io",
        )
        specs = dict(_laptop_specs(), cpu_short="i5-1135G7U")

        result = price_specs(specs, [refurb], limit_per_query=5)

        self.assertEqual(result["median_price_cad"], 525.00)
        self.assertIs(result["source_diagnostics"][0]["source_match_verified"], True)

    def test_laptop_form_factor_text_is_not_required_for_verified_source_match(self):
        refurb = FakeSource(
            {
                "20XW004AUS": [
                    _refurb_listing("Lenovo ThinkPad X13 Yoga i5-1135G7 16GB 256GB", 525)
                ],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB": [],
                "Lenovo ThinkPad X13 Yoga": [],
            },
            name="refurb_io",
        )

        result = price_specs(_laptop_specs(), [refurb], limit_per_query=5)

        self.assertEqual(result["median_price_cad"], 525.00)
        self.assertNotIn("form_factor_mismatch", result["source_diagnostics"][0]["source_match_reasons"])

    def test_surface_pro_tablet_label_does_not_block_verified_source_match(self):
        refurb = FakeSource(
            {
                "Microsoft Surface Pro 7 128GB": [
                    _refurb_listing(
                        "Microsoft Surface Pro 7 i5-1035G4 8GB 128GB",
                        425,
                        model="Surface Pro 7",
                        ram_gb=8,
                        storage_gb=128,
                        url="https://ca.refurb.io/products/surface-pro-7",
                    )
                ],
                "Microsoft Surface Pro 7": [],
            },
            name="refurb_io",
        )

        result = price_specs(_surface_pro_tablet_specs(), [refurb], limit_per_query=5)

        self.assertEqual(result["median_price_cad"], 425.00)
        self.assertIs(result["source_diagnostics"][0]["source_match_verified"], True)
        self.assertNotIn("device_type_mismatch", result["source_diagnostics"][0]["source_match_reasons"])

    def test_ram_and_storage_mismatches_are_excluded_from_pricing(self):
        ebay = FakeSource(
            {
                "20XW004AUS": [_listing("eBay ThinkPad X13 Yoga", 300, "https://www.ebay.ca/itm/1")],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB": [],
                "Lenovo ThinkPad X13 Yoga": [],
            },
            name="ebay",
        )
        refurb = FakeSource(
            {
                "20XW004AUS": [
                    _refurb_listing(
                        "Lenovo ThinkPad X13 Yoga Laptop i5-1135G7 8GB 256GB",
                        500,
                        ram_gb=8,
                        storage_gb=256,
                        url="https://ca.refurb.io/products/ram",
                    ),
                    _refurb_listing(
                        "Lenovo ThinkPad X13 Yoga Laptop i5-1135G7 16GB 128GB",
                        520,
                        ram_gb=16,
                        storage_gb=128,
                        url="https://ca.refurb.io/products/storage",
                    ),
                ],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB": [],
                "Lenovo ThinkPad X13 Yoga": [],
            },
            name="refurb_io",
        )

        specs = dict(_laptop_specs(), storage=[{"size_gb": 256, "type": "SSD"}])
        result = price_specs(specs, [ebay, refurb], limit_per_query=5)

        self.assertEqual(result["median_price_cad"], 300.00)
        self.assertEqual(result["source_counts"], {"ebay": 1})
        self.assertEqual(result["excluded_reasons"], {"ram_mismatch": 1, "storage_mismatch": 1})

    def test_weak_amazon_renewed_match_falls_back_to_ebay(self):
        ebay = FakeSource(
            {
                "20XW004AUS": [_listing("eBay ThinkPad X13 Yoga", 300, "https://www.ebay.ca/itm/1")],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB": [],
                "Lenovo ThinkPad X13 Yoga": [],
            },
            name="ebay",
        )
        amazon = FakeSource(
            {
                "Lenovo ThinkPad X13 Yoga Renewed": [],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB Renewed": [
                    _amazon_listing("Dell Latitude Laptop Amazon Renewed i5-1135G7 16GB 256GB", 600, model="Latitude")
                ],
            },
            name="amazon_renewed",
        )

        result = price_specs(_laptop_specs(), [ebay, amazon], limit_per_query=5)

        self.assertEqual(result["median_price_cad"], 300.00)
        self.assertEqual(result["source_basis"], "ebay_asking_adjusted")
        self.assertEqual(result["source_diagnostics"][0]["source_match_reasons"], ["brand_mismatch", "model_mismatch"])
        self.assertIs(result["source_diagnostics"][0]["included_in_pricing"], False)

    def test_source_failure_is_reported_without_crashing(self):
        ebay = FakeSource(
            {
                "20XW004AUS": [_listing("eBay ThinkPad X13 Yoga", 300, "https://www.ebay.ca/itm/1")],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB": [],
                "Lenovo ThinkPad X13 Yoga": [],
            },
            name="ebay",
        )
        failing = FailingSource("refurb_io")

        result = price_specs(_laptop_specs(), [ebay, failing], limit_per_query=5)

        self.assertEqual(result["median_price_cad"], 300.00)
        self.assertIn("source_unavailable", result["confidence_flags"])
        self.assertEqual(result["source_errors"][0]["source"], "refurb_io")
        refurb_status = next(status for status in result["source_statuses"] if status["source"] == "refurb_io")
        self.assertEqual(refurb_status["error_count"], 3)
        self.assertEqual(refurb_status["errors"], ["source unavailable", "source unavailable", "source unavailable"])

    def test_ebay_only_behavior_remains_asking_adjusted(self):
        source = FakeSource(
            {
                "20XW004AUS": [
                    _listing("Listing 1", 500, "https://www.ebay.ca/itm/1"),
                    _listing("Listing 2", 520, "https://www.ebay.ca/itm/2"),
                ],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB": [],
                "Lenovo ThinkPad X13 Yoga": [],
            },
            name="ebay",
        )

        result = price_specs(_laptop_specs(), [source], limit_per_query=5, warn_below_comparables=2)

        self.assertEqual(result["median_price_cad"], 510.00)
        self.assertEqual(result["pricing_basis"], "asking_adjusted")
        self.assertEqual(result["conservative_low_cad"], 484.5)
        self.assertEqual(result["conservative_high_cad"], 510.0)

    def test_reprices_existing_result_after_user_removes_comparable(self):
        source = FakeSource(
            {
                "20XW004AUS": [
                    _listing("Listing 1", 300, "https://www.ebay.ca/itm/1"),
                    _listing("Listing 2", 500, "https://www.ebay.ca/itm/2"),
                ],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB": [],
                "Lenovo ThinkPad X13 Yoga": [],
            },
            name="ebay",
        )
        result = price_specs(_laptop_specs(), [source], limit_per_query=5, warn_below_comparables=2)
        removed_id = result["all_comparable_listings"][1]["comparable_id"]

        repriced = reprice_existing_result(result, {removed_id})

        self.assertEqual(repriced["count"], 1)
        self.assertEqual(repriced["median_price_cad"], 300.00)
        self.assertEqual(repriced["excluded_reasons"]["user_removed_comparable"], 1)
        self.assertIs(repriced["all_comparable_listings"][1]["excluded_by_user"], True)

    def test_reprice_preserves_metadata_when_verified_retailer_is_removed(self):
        ebay = FakeSource(
            {
                "20XW004AUS": [_listing("eBay ThinkPad X13 Yoga", 300, "https://www.ebay.ca/itm/1")],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB": [],
                "Lenovo ThinkPad X13 Yoga": [],
            },
            name="ebay",
        )
        refurb = FakeSource(
            {
                "20XW004AUS": [_refurb_listing("Lenovo ThinkPad X13 Yoga Laptop i5-1135G7 16GB 256GB", 500)],
                "Lenovo ThinkPad X13 Yoga i5-1135G7 16GB": [],
                "Lenovo ThinkPad X13 Yoga": [],
            },
            name="refurb_io",
        )
        result = price_specs(_laptop_specs(), [ebay, refurb], limit_per_query=5)
        removed_id = next(
            listing["comparable_id"]
            for listing in result["all_comparable_listings"]
            if listing["source"] == "refurb_io"
        )

        repriced = reprice_existing_result(result, {removed_id})

        self.assertEqual(repriced["median_price_cad"], 300.00)
        self.assertEqual(repriced["source_basis"], "ebay_asking_adjusted")
        self.assertEqual(repriced["source_counts"], {"ebay": 1})
        self.assertEqual(repriced["excluded_reasons"]["user_removed_comparable"], 1)
        self.assertEqual(len(repriced["all_comparable_listings"]), 2)
        self.assertTrue(
            next(
                listing
                for listing in repriced["all_comparable_listings"]
                if listing["source"] == "refurb_io"
            )["excluded_by_user"]
        )
        self.assertEqual(repriced["source_diagnostics"][0]["source"], "refurb_io")


class FakeSource:
    def __init__(self, results, name="ebay"):
        self.results = results
        self.calls = []
        self.name = name

    def search(self, query, max_results):
        self.calls.append((query, max_results))
        return self.results.get(query, [])


class FailingSource:
    def __init__(self, name):
        self.name = name

    def search(self, _query, _max_results):
        raise RuntimeError("source unavailable")


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


def _phone_pro_specs():
    return {
        "device_type": "phone",
        "brand": "Apple",
        "model": "iPhone 13 Pro",
        "search_model": "iPhone 13 Pro",
        "storage_capacity": "128GB",
        "carrier": "unlocked",
    }


def _surface_pro_tablet_specs():
    return {
        "device_type": "tablet",
        "brand": "Microsoft",
        "model": "Surface Pro 7",
        "search_model": "Surface Pro 7",
        "storage_capacity": "128GB",
        "form_factor": "2-in-1",
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


def _refurb_listing(
    title,
    price,
    model="ThinkPad X13 Yoga Gen 2",
    ram_gb=16,
    storage_gb=256,
    url="https://ca.refurb.io/products/example",
):
    return {
        "source": "refurb_io",
        "title": title,
        "item_price_cad": price,
        "shipping_cad": 0,
        "total_price_cad": price,
        "shipping_is_estimated": False,
        "condition_raw": "Grade A",
        "condition_norm": None,
        "is_sold": False,
        "available": True,
        "url": url,
        "source_specs": {
            "brand": "Lenovo",
            "model": model,
            "ram_gb": ram_gb,
            "storage_gb": storage_gb,
            "cpu_short": "i5-1135G7",
        },
    }


def _amazon_listing(title, price, model="ThinkPad X13 Yoga Gen 2"):
    return {
        "source": "amazon_renewed",
        "title": title,
        "item_price_cad": price,
        "shipping_cad": 0,
        "total_price_cad": price,
        "shipping_is_estimated": False,
        "condition_raw": "Amazon Renewed",
        "condition_norm": None,
        "is_sold": False,
        "available": True,
        "url": "https://www.amazon.ca/dp/B0AMAZON01",
        "source_specs": {
            "brand": "Lenovo" if model != "Latitude" else "Dell",
            "model": model,
            "ram_gb": 16,
            "storage_gb": 256,
            "cpu_short": "i5-1135G7",
        },
    }


if __name__ == "__main__":
    unittest.main()
