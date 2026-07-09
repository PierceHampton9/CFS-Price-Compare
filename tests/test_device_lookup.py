import unittest

from pc_pricer.device_lookup import enrich_specs_from_model_lookup, looks_like_model_number, model_identifier


class DeviceLookupTests(unittest.TestCase):
    def test_enriches_computer_specs_from_exact_model_lookup(self):
        source = FakeLookupSource(
            {
                "Lenovo 20ZZS23S00": [
                    {
                        "source": "refurb_io",
                        "title": "Lenovo ThinkPad X1 Carbon Gen 9 Laptop i7-1185G7 16GB 512GB",
                        "url": "https://example.test/device",
                        "source_specs": {
                            "brand": "Lenovo",
                            "model": "ThinkPad X1 Carbon Gen 9",
                            "cpu_short": "i7-1185G7",
                            "ram_gb": 16,
                            "storage_gb": 512,
                        },
                    }
                ]
            }
        )

        enriched, status, lookup_results = enrich_specs_from_model_lookup(
            {
                "device_type": "computer",
                "brand": "Lenovo",
                "model": "20ZZS23S00",
                "model_is_machine_type": True,
            },
            [source],
        )

        self.assertEqual(source.calls, [("Lenovo 20ZZS23S00", 3), ("20ZZS23S00", 3)])
        assert status is not None
        self.assertEqual(status["status"], "identified")
        self.assertEqual(lookup_results[0]["query"], "Lenovo 20ZZS23S00")
        self.assertEqual(enriched["search_model"], "ThinkPad X1 Carbon Gen 9")
        self.assertEqual(enriched["form_factor"], "laptop")
        self.assertEqual(enriched["cpu_short"], "i7-1185G7")
        self.assertEqual(enriched["ram_gb"], 16)
        self.assertEqual(enriched["storage"], [{"size_gb": 512, "type": "SSD"}])

    def test_enriches_known_lenovo_machine_type_from_local_table_before_network_lookup(self):
        source = FakeLookupSource({})

        enriched, status, lookup_results = enrich_specs_from_model_lookup(
            {
                "device_type": "computer",
                "brand": "LENOVO",
                "model": "20W9S23S00",
                "model_is_machine_type": True,
                "cpu_short": "i7-1185G7",
                "ram_gb": 16,
                "storage": [{"size_gb": 238, "type": "SSD"}],
            },
            [source],
        )

        self.assertEqual(source.calls, [])
        self.assertEqual(lookup_results, [])
        assert status is not None
        self.assertEqual(status["status"], "identified")
        self.assertEqual(status["source"], "local:lenovo_machine_type")
        self.assertEqual(enriched["brand"], "LENOVO")
        self.assertEqual(enriched["model"], "20W9S23S00")
        self.assertEqual(enriched["search_model"], "ThinkPad X13 Yoga Gen 2")
        self.assertEqual(enriched["form_factor"], "laptop")

    def test_low_confidence_lookup_does_not_modify_specs(self):
        source = FakeLookupSource(
            {
                "Lenovo 20ZZS23S00": [
                    {
                        "source": "refurb_io",
                        "title": "Dell Latitude laptop i5 16GB",
                        "source_specs": {"brand": "Dell", "model": "Latitude"},
                    }
                ]
            }
        )
        specs = {"device_type": "computer", "brand": "Lenovo", "model": "20ZZS23S00"}

        enriched, status, _lookup_results = enrich_specs_from_model_lookup(specs, [source])

        self.assertEqual(enriched, specs)
        assert status is not None
        self.assertEqual(status["status"], "not_found")

    def test_manufacturer_lookup_runs_before_pricing_source_lookup(self):
        source = FakeLookupSource({})

        enriched, status, lookup_results = enrich_specs_from_model_lookup(
            {
                "device_type": "computer",
                "brand": "Lenovo",
                "model": "20ZZS23S00",
                "model_is_machine_type": True,
            },
            [source],
            manufacturer_lookup=lambda _specs, _identifier: {
                "source": "manufacturer:lenovo",
                "title": "Lenovo ThinkPad X1 Carbon Gen 9 Laptop",
                "url": "https://psref.lenovo.com/Search?kw=20W9S23S00",
                "queries": ["https://psref.lenovo.com/Search?kw=20W9S23S00"],
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

        self.assertEqual(source.calls, [])
        self.assertEqual(lookup_results, [])
        assert status is not None
        self.assertEqual(status["status"], "identified")
        self.assertEqual(status["source"], "manufacturer:lenovo")
        self.assertEqual(enriched["search_model"], "ThinkPad X1 Carbon Gen 9")
        self.assertEqual(enriched["storage"], [{"size_gb": 512, "type": "NVMe"}])

    def test_model_identifier_accepts_oem_sku_or_sku_like_model(self):
        self.assertEqual(model_identifier({"oem_sku": "7YX45UT"}), "7YX45UT")
        self.assertEqual(model_identifier({"model": "20W9S23S00"}), "20W9S23S00")
        self.assertIsNone(model_identifier({"model": "ThinkPad X1 Carbon"}))
        self.assertFalse(looks_like_model_number("Z240"))


class FakeLookupSource:
    name = "refurb_io"
    enabled = True

    def __init__(self, results):
        self.results = results
        self.calls = []

    def search(self, query, max_results):
        self.calls.append((query, max_results))
        return self.results.get(query, [])


if __name__ == "__main__":
    unittest.main()
