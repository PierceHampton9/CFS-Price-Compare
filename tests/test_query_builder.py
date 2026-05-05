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


if __name__ == "__main__":
    unittest.main()
