import unittest

from pc_pricer.query_builder import build_queries


class QueryBuilderTests(unittest.TestCase):
    def test_laptop_queries_start_with_oem_sku(self):
        specs = {
            "brand": "Lenovo",
            "model": "ThinkPad X13 Yoga Gen 2",
            "oem_sku": "20XH001NUS",
            "form_factor": "laptop",
            "cpu_short": "i5-1135G7",
            "ram_gb": 16,
        }

        queries = build_queries(specs)

        self.assertEqual(queries[0]["text"], "20XH001NUS")
        self.assertEqual(queries[0]["tier"], 1)
        self.assertEqual(
            queries[1]["text"],
            "Lenovo ThinkPad X13 Yoga Gen 2 i5-1135G7 16GB",
        )
        self.assertEqual(queries[2]["text"], "Lenovo ThinkPad X13 Yoga Gen 2")

    def test_laptop_without_oem_sku_skips_exact_tier(self):
        specs = {
            "brand": "Lenovo",
            "model": "ThinkPad X1 Carbon",
            "form_factor": "laptop",
            "cpu_short": "i7-8650U",
            "ram_gb": 16,
        }

        queries = build_queries(specs)

        self.assertEqual(queries[0]["tier"], 2)
        self.assertEqual(queries[0]["text"], "Lenovo ThinkPad X1 Carbon i7-8650U 16GB")

    def test_laptop_queries_prefer_search_model(self):
        specs = {
            "brand": "Lenovo",
            "model": "20W9S23S00",
            "search_model": "ThinkPad X1 Carbon Gen 9",
            "form_factor": "laptop",
            "cpu_short": "i7-1185G7",
            "ram_gb": 16,
        }

        queries = build_queries(specs)

        self.assertEqual(queries[0]["text"], "Lenovo ThinkPad X1 Carbon Gen 9 i7-1185G7 16GB")
        self.assertEqual(queries[1]["text"], "Lenovo ThinkPad X1 Carbon Gen 9")
        self.assertNotIn("20W9S23S00", " ".join(query["text"] for query in queries))

    def test_laptop_with_machine_type_model_falls_back_to_specs(self):
        specs = {
            "brand": "Lenovo",
            "model": "20W9S23S00",
            "search_model": None,
            "model_is_machine_type": True,
            "form_factor": "laptop",
            "cpu_short": "i7-1185G7",
            "ram_gb": 16,
            "storage": [{"size_gb": 238, "type": "SSD"}],
        }

        queries = build_queries(specs)

        self.assertEqual(queries[0]["text"], "Lenovo i7-1185G7 16GB 256GB SSD laptop")
        self.assertEqual(queries[0]["tier"], 3)
        self.assertNotIn("20W9S23S00", queries[0]["text"])

    def test_all_in_one_uses_laptop_style_queries(self):
        specs = {
            "brand": "HP",
            "model": "EliteOne 800 G5",
            "oem_sku": "7YX45UT",
            "form_factor": "all-in-one",
            "cpu_short": "i5-9500",
            "ram_gb": 16,
        }

        queries = build_queries(specs)

        self.assertEqual(queries[0]["text"], "7YX45UT")
        self.assertEqual(queries[0]["tier"], 1)
        self.assertEqual(queries[1]["text"], "HP EliteOne 800 G5 i5-9500 16GB")

    def test_desktop_queries_are_spec_led(self):
        specs = {
            "brand": "Dell",
            "model": "OptiPlex 7050",
            "form_factor": "desktop",
            "cpu_short": "i5-7500",
            "ram_gb": 16,
            "storage": [{"size_gb": 238, "type": "SSD"}],
            "gpu": "Intel UHD Graphics 630",
        }

        queries = build_queries(specs)

        self.assertEqual(
            queries[0]["text"],
            "Dell OptiPlex 7050 i5-7500 16GB 256GB SSD",
        )
        self.assertEqual(queries[1]["text"], "i5-7500 16GB 256GB SSD desktop")
        self.assertEqual(queries[2]["text"], "i5-7500 16GB desktop")

    def test_desktop_storage_sizes_can_be_strings(self):
        specs = {
            "brand": "Dell",
            "model": "OptiPlex 7050",
            "form_factor": "desktop",
            "cpu_short": "i5-7500",
            "ram_gb": 16,
            "storage": [
                {"size_gb": "238", "type": "SSD"},
                {"size_gb": 1024, "type": "HDD"},
            ],
        }

        queries = build_queries(specs)

        self.assertEqual(
            queries[0]["text"],
            "Dell OptiPlex 7050 i5-7500 16GB 1TB HDD",
        )

    def test_desktop_includes_dedicated_gpu(self):
        specs = {
            "brand": "HP",
            "model": "Z240",
            "form_factor": "desktop",
            "cpu_short": "i7-6700",
            "ram_gb": 32,
            "storage": [{"size_gb": 512, "type": "SSD"}],
            "gpu": "NVIDIA GeForce GTX 1650",
        }

        queries = build_queries(specs)

        self.assertIn("NVIDIA GeForce GTX 1650", queries[0]["text"])
        self.assertIn("NVIDIA GeForce GTX 1650", queries[1]["text"])

    def test_missing_fields_do_not_make_ugly_queries(self):
        specs = {
            "form_factor": "desktop",
            "ram_gb": 8,
        }

        queries = build_queries(specs)

        self.assertEqual(queries, [])

    def test_phone_queries_use_model_storage_and_carrier(self):
        specs = {
            "device_type": "phone",
            "brand": "Apple",
            "model": "iPhone 13",
            "storage_capacity": "128GB",
            "carrier": "unlocked",
        }

        queries = build_queries(specs)

        self.assertEqual(queries[0]["text"], "Apple iPhone 13 128GB unlocked")
        self.assertEqual(queries[0]["tier"], 1)
        self.assertEqual(queries[1]["text"], "Apple iPhone 13 128GB")
        self.assertEqual(queries[2]["text"], "Apple iPhone 13")

    def test_tablet_queries_use_connectivity(self):
        specs = {
            "device_type": "tablet",
            "brand": "Samsung",
            "model": "Galaxy Tab S7",
            "storage_capacity": "256GB",
            "connectivity": "Wi-Fi",
        }

        queries = build_queries(specs)

        self.assertEqual(queries[0]["text"], "Samsung Galaxy Tab S7 256GB Wi-Fi")
        self.assertEqual(queries[1]["text"], "Samsung Galaxy Tab S7 256GB")

    def test_monitor_queries_include_display_specs(self):
        specs = {
            "device_type": "monitor",
            "brand": "Dell",
            "model": "U2419H",
            "size": "24",
            "resolution": "1080p",
            "refresh_rate": "60",
        }

        queries = build_queries(specs)

        self.assertEqual(queries[0]["text"], 'Dell U2419H 24" 1080p 60Hz monitor')
        self.assertEqual(queries[1]["text"], 'Dell U2419H 24" 1080p monitor')
        self.assertEqual(queries[2]["text"], "Dell U2419H monitor")

    def test_printer_queries_include_printer_type(self):
        specs = {
            "device_type": "printer",
            "brand": "Brother",
            "model": "HL-L2390DW",
            "printer_type": "laser",
            "color": "mono",
        }

        queries = build_queries(specs)

        self.assertEqual(queries[0]["text"], "Brother HL-L2390DW laser mono printer")
        self.assertEqual(queries[1]["text"], "Brother HL-L2390DW laser printer")

    def test_storage_device_queries_separate_form_factor_and_interface(self):
        specs = {
            "device_type": "storage",
            "brand": "Samsung",
            "model": "970 EVO Plus",
            "capacity": "1TB",
            "drive_type": "SSD",
            "drive_form_factor": "m.2",
            "interface": "NVMe",
        }

        queries = build_queries(specs)

        self.assertEqual(queries[0]["text"], "Samsung 970 EVO Plus 1TB SSD m.2 NVMe")
        self.assertEqual(queries[1]["text"], "Samsung 970 EVO Plus 1TB SSD")
        self.assertEqual(queries[2]["text"], "1TB SSD m.2 NVMe")

    def test_storage_device_queries_display_msata_alias_cleanly(self):
        specs = {
            "device_type": "storage",
            "brand": "Kingston",
            "model": "SSDNow",
            "capacity": "240GB",
            "drive_type": "SSD",
            "drive_form_factor": "msata",
            "interface": "SATA",
        }

        queries = build_queries(specs)

        self.assertEqual(queries[0]["text"], "Kingston SSDNow 240GB SSD mSATA SATA")


if __name__ == "__main__":
    unittest.main()
