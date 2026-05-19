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
        self.assertEqual(
            result["excluded_reasons"],
            {
                "condition_mismatch": 1,
                "unknown_condition": 1,
            },
        )
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

    def test_keeps_complete_systems_that_mention_common_parts(self):
        listings = [
            _listing("ThinkPad X13 Yoga with backlit keyboard", "good"),
            _listing("ThinkPad X13 Yoga new battery 16GB RAM", "good"),
            _listing("ThinkPad X13 Yoga LCD touchscreen laptop", "good"),
            _listing("ThinkPad X13 Yoga charger cable included", "good"),
        ]

        result = filter_listings(listings, target_condition="good")

        self.assertEqual(
            [listing["title"] for listing in result["listings"]],
            [listing["title"] for listing in listings],
        )
        self.assertEqual(result["excluded_count"], 0)

    def test_exclusion_reason_prefers_parts_over_condition_mismatch(self):
        listing = _listing("ThinkPad X13 Yoga motherboard", "mint")

        self.assertEqual(exclusion_reason(listing, target_condition="good"), "parts_or_accessory")

    def test_excludes_unavailable_listings_before_other_checks(self):
        listing = _listing("ThinkPad X13 Yoga", "good")
        listing["available"] = False

        self.assertEqual(exclusion_reason(listing, target_condition="good"), "unavailable_listing")

    def test_unknown_condition_has_separate_reason(self):
        listing = _listing("ThinkPad X13 Yoga", None)

        self.assertEqual(exclusion_reason(listing, target_condition="good"), "unknown_condition")

    def test_phone_filter_excludes_common_accessories_and_locked_units(self):
        listings = [
            _listing("Apple iPhone 13 128GB Unlocked", "good"),
            _listing("For iPhone 13 case shockproof cover", "good"),
            _listing("iPhone 13 tempered glass screen protector", "good"),
            _listing("iPhone 13 replacement battery", "good"),
            _listing("Apple iPhone 13 iCloud locked", "good"),
        ]

        result = filter_listings(listings, target_condition="any", device_type="phone")

        self.assertEqual(
            [listing["title"] for listing in result["listings"]],
            ["Apple iPhone 13 128GB Unlocked"],
        )
        self.assertEqual(result["excluded_reasons"], {"parts_or_accessory": 4})

    def test_phone_filter_keeps_full_devices_with_bundled_accessories(self):
        listings = [
            _listing("Apple iPhone 13 128GB for sale with bundled cover", "good"),
            _listing("Apple iPhone 13 unlocked with case included", "good"),
        ]

        result = filter_listings(listings, target_condition="any", device_type="phone")

        self.assertEqual(
            [listing["title"] for listing in result["listings"]],
            [listing["title"] for listing in listings],
        )
        self.assertEqual(result["excluded_count"], 0)

    def test_phone_filter_excludes_unrequested_model_variants(self):
        listings = [
            _listing("Apple iPhone 13 128GB Unlocked", "good"),
            _listing("Apple iPhone 13 mini 128GB Unlocked", "good"),
            _listing("Apple iPhone 13 Pro 128GB Unlocked", "good"),
            _listing("Apple iPhone 13 Pro Max 128GB Unlocked", "good"),
        ]

        result = filter_listings(
            listings,
            target_condition="any",
            device_type="phone",
            target_specs={"device_type": "phone", "model": "iPhone 13"},
        )

        self.assertEqual(
            [listing["title"] for listing in result["listings"]],
            ["Apple iPhone 13 128GB Unlocked"],
        )
        self.assertEqual(result["excluded_reasons"], {"variant_mismatch": 3})

    def test_phone_filter_keeps_requested_variant(self):
        listings = [
            _listing("Apple iPhone 13 Pro Max 128GB Unlocked", "good"),
            _listing("Apple iPhone 13 Pro 128GB Unlocked", "good"),
        ]

        result = filter_listings(
            listings,
            target_condition="any",
            device_type="phone",
            target_specs={"device_type": "phone", "model": "iPhone 13", "variant": "Pro Max"},
        )

        self.assertEqual(
            [listing["title"] for listing in result["listings"]],
            ["Apple iPhone 13 Pro Max 128GB Unlocked"],
        )
        self.assertEqual(result["excluded_reasons"], {"variant_mismatch": 1})

    def test_phone_filter_excludes_generic_listing_when_target_has_variant(self):
        listings = [
            _listing("Apple iPhone 13 128GB Unlocked", "good"),
            _listing("Apple iPhone 13 Pro Max 128GB Unlocked", "good"),
        ]

        result = filter_listings(
            listings,
            target_condition="any",
            device_type="phone",
            target_specs={"device_type": "phone", "model": "iPhone 13", "variant": "Pro Max"},
        )

        self.assertEqual(
            [listing["title"] for listing in result["listings"]],
            ["Apple iPhone 13 Pro Max 128GB Unlocked"],
        )
        self.assertEqual(result["excluded_reasons"], {"variant_mismatch": 1})

    def test_phone_filter_excludes_base_model_when_variant_lives_in_model_name(self):
        listings = [
            _listing("Apple iPhone 13 128GB Unlocked", "good"),
            _listing("Apple iPhone 13 Pro 128GB Unlocked", "good"),
        ]

        result = filter_listings(
            listings,
            target_condition="any",
            device_type="phone",
            target_specs={"device_type": "phone", "model": "iPhone 13 Pro"},
        )

        self.assertEqual(
            [listing["title"] for listing in result["listings"]],
            ["Apple iPhone 13 Pro 128GB Unlocked"],
        )
        self.assertEqual(result["excluded_reasons"], {"variant_mismatch": 1})

    def test_tablet_filter_excludes_base_model_when_target_has_variant(self):
        listings = [
            _listing("Apple iPad 10.9 64GB Wi-Fi", "good"),
            _listing("Apple iPad Air 10.9 64GB Wi-Fi", "good"),
        ]

        result = filter_listings(
            listings,
            target_condition="any",
            device_type="tablet",
            target_specs={"device_type": "tablet", "model": "iPad Air"},
        )

        self.assertEqual(
            [listing["title"] for listing in result["listings"]],
            ["Apple iPad Air 10.9 64GB Wi-Fi"],
        )
        self.assertEqual(result["excluded_reasons"], {"variant_mismatch": 1})

    def test_phone_filter_handles_plus_symbol_variant_on_listing(self):
        listings = [
            _listing("Apple iPhone 8 64GB Unlocked", "good"),
            _listing("Apple iPhone 8+ 64GB Unlocked", "good"),
        ]

        result = filter_listings(
            listings,
            target_condition="any",
            device_type="phone",
            target_specs={"device_type": "phone", "model": "iPhone 8"},
        )

        self.assertEqual(
            [listing["title"] for listing in result["listings"]],
            ["Apple iPhone 8 64GB Unlocked"],
        )
        self.assertEqual(result["excluded_reasons"], {"variant_mismatch": 1})

    def test_tablet_filter_excludes_common_accessories(self):
        listings = [
            _listing("Samsung Galaxy Tab S7 256GB Wi-Fi", "good"),
            _listing("Galaxy Tab S7 keyboard case", "good"),
            _listing("Samsung Tab S7 replacement digitizer", "good"),
        ]

        result = filter_listings(listings, target_condition="any", device_type="tablet")

        self.assertEqual(
            [listing["title"] for listing in result["listings"]],
            ["Samsung Galaxy Tab S7 256GB Wi-Fi"],
        )
        self.assertEqual(result["excluded_reasons"], {"parts_or_accessory": 2})

    def test_tablet_filter_excludes_unrequested_variants_and_screen_sizes(self):
        listings = [
            _listing('Samsung Galaxy Tab S7 11" 128GB Wi-Fi', "good"),
            _listing('Samsung Galaxy Tab S7 FE 12.4" 128GB Wi-Fi', "good"),
            _listing('Samsung Galaxy Tab S7+ 12.4" 128GB Wi-Fi', "good"),
        ]

        result = filter_listings(
            listings,
            target_condition="any",
            device_type="tablet",
            target_specs={
                "device_type": "tablet",
                "model": "Galaxy Tab S7",
                "screen_size": '11"',
            },
        )

        self.assertEqual(
            [listing["title"] for listing in result["listings"]],
            ['Samsung Galaxy Tab S7 11" 128GB Wi-Fi'],
        )
        self.assertEqual(result["excluded_reasons"], {"variant_mismatch": 2})

    def test_screen_size_filter_only_fires_when_listing_exposes_size(self):
        listings = [
            _listing("Samsung Galaxy Tab S7 128GB Wi-Fi", "good"),
            _listing('Samsung Galaxy Tab S7 12.4" 128GB Wi-Fi', "good"),
        ]

        result = filter_listings(
            listings,
            target_condition="any",
            device_type="tablet",
            target_specs={
                "device_type": "tablet",
                "model": "Galaxy Tab S7",
                "screen_size": '11"',
            },
        )

        self.assertEqual([listing["title"] for listing in result["listings"]], ["Samsung Galaxy Tab S7 128GB Wi-Fi"])
        self.assertEqual(result["excluded_reasons"], {"variant_mismatch": 1})

    def test_computer_filter_excludes_obvious_screen_size_mismatches(self):
        listings = [
            _listing('Apple MacBook Pro 14" M1 Pro 16GB', "good"),
            _listing('Apple MacBook Pro 16" M1 Pro 16GB', "good"),
        ]

        result = filter_listings(
            listings,
            target_condition="any",
            device_type="computer",
            target_specs={
                "device_type": "computer",
                "form_factor": "laptop",
                "model": "MacBook Pro",
                "screen_size": '14"',
            },
        )

        self.assertEqual([listing["title"] for listing in result["listings"]], ['Apple MacBook Pro 14" M1 Pro 16GB'])
        self.assertEqual(result["excluded_reasons"], {"variant_mismatch": 1})

    def test_computer_filter_handles_hyphenated_screen_size(self):
        listings = [
            _listing("Apple MacBook Pro 14-inch M1 Pro 16GB", "good"),
            _listing("Apple MacBook Pro 16-inch M1 Pro 16GB", "good"),
        ]

        result = filter_listings(
            listings,
            target_condition="any",
            device_type="computer",
            target_specs={
                "device_type": "computer",
                "form_factor": "laptop",
                "model": "MacBook Pro",
                "screen_size": '14"',
            },
        )

        self.assertEqual(
            [listing["title"] for listing in result["listings"]],
            ["Apple MacBook Pro 14-inch M1 Pro 16GB"],
        )
        self.assertEqual(result["excluded_reasons"], {"variant_mismatch": 1})

    def test_screen_size_filter_keeps_listing_without_size(self):
        listings = [
            _listing("Apple MacBook Pro M1 Pro 16GB", "good"),
            _listing("Apple MacBook Pro 16-inch M1 Pro 16GB", "good"),
        ]

        result = filter_listings(
            listings,
            target_condition="any",
            device_type="computer",
            target_specs={
                "device_type": "computer",
                "form_factor": "laptop",
                "model": "MacBook Pro",
                "screen_size": '14"',
            },
        )

        self.assertEqual(
            [listing["title"] for listing in result["listings"]],
            ["Apple MacBook Pro M1 Pro 16GB"],
        )
        self.assertEqual(result["excluded_reasons"], {"variant_mismatch": 1})

    def test_monitor_filter_excludes_mounts_and_parts(self):
        listings = [
            _listing("Dell U2419H 24 inch monitor", "good"),
            _listing("Dell U2419H monitor stand", "good"),
            _listing("Dell U2419H controller board", "good"),
        ]

        result = filter_listings(listings, target_condition="any", device_type="monitor")

        self.assertEqual([listing["title"] for listing in result["listings"]], ["Dell U2419H 24 inch monitor"])
        self.assertEqual(result["excluded_reasons"], {"parts_or_accessory": 2})

    def test_monitor_filter_keeps_full_monitor_lcd_panel_phrasing(self):
        listings = [
            _listing('Dell U2419H 24" IPS LCD Panel Monitor', "good"),
            _listing("Dell U2419H replacement LCD panel", "good"),
        ]

        result = filter_listings(listings, target_condition="any", device_type="monitor")

        self.assertEqual(
            [listing["title"] for listing in result["listings"]],
            ['Dell U2419H 24" IPS LCD Panel Monitor'],
        )
        self.assertEqual(result["excluded_reasons"], {"parts_or_accessory": 1})

    def test_printer_filter_excludes_consumables_and_parts(self):
        listings = [
            _listing("Brother HL-L2390DW laser printer", "good"),
            _listing("Brother HL-L2390DW toner cartridge", "good"),
            _listing("Brother HL-L2390DW printhead replacement", "good"),
        ]

        result = filter_listings(listings, target_condition="any", device_type="printer")

        self.assertEqual([listing["title"] for listing in result["listings"]], ["Brother HL-L2390DW laser printer"])
        self.assertEqual(result["excluded_reasons"], {"parts_or_accessory": 2})

    def test_storage_filter_excludes_enclosures_and_adapters(self):
        listings = [
            _listing("Samsung 970 EVO Plus 1TB SSD NVMe", "good"),
            _listing("M.2 NVMe SSD enclosure", "good"),
            _listing("SATA to USB adapter cable", "good"),
        ]

        result = filter_listings(listings, target_condition="any", device_type="storage")

        self.assertEqual(
            [listing["title"] for listing in result["listings"]],
            ["Samsung 970 EVO Plus 1TB SSD NVMe"],
        )
        self.assertEqual(result["excluded_reasons"], {"parts_or_accessory": 2})

    def test_storage_filter_keeps_bundled_cables_but_excludes_cable_only(self):
        listings = [
            _listing("Seagate 2TB Portable HDD with USB-C Cable", "good"),
            _listing("USB-C cable only for external HDD", "good"),
            _listing("SATA to USB adapter for SSD", "good"),
        ]

        result = filter_listings(listings, target_condition="any", device_type="storage")

        self.assertEqual(
            [listing["title"] for listing in result["listings"]],
            ["Seagate 2TB Portable HDD with USB-C Cable"],
        )
        self.assertEqual(result["excluded_reasons"], {"parts_or_accessory": 2})

    def test_device_specific_accessory_words_do_not_apply_to_computers(self):
        listing = _listing("Desktop computer with carrying case", "good")

        self.assertIsNone(exclusion_reason(listing, target_condition="good", device_type="computer"))


def _listing(title, condition_norm):
    return {
        "title": title,
        "condition_norm": condition_norm,
    }


if __name__ == "__main__":
    unittest.main()
