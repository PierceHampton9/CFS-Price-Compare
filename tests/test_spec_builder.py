import unittest

from pc_pricer.spec_builder import build_manual_specs, gui_values_from_detected_specs


class SpecBuilderTests(unittest.TestCase):
    def test_builds_computer_specs_from_gui_values(self):
        specs = build_manual_specs(
            "computer",
            {
                "form_factor": "laptop",
                "brand": "Lenovo",
                "model": "ThinkPad X13 Yoga",
                "cpu": "i5-1135G7",
                "ram": "16",
                "storage": "512",
                "storage_type": "ssd",
                "input_method": "detected",
            },
        )

        self.assertEqual(specs["device_type"], "computer")
        self.assertEqual(specs["ram_gb"], 16)
        self.assertEqual(specs["storage"], [{"size_gb": 512}])
        self.assertEqual(specs["input_method"], "detected")

    def test_builds_computer_specs_from_model_number_without_form_factor(self):
        specs = build_manual_specs(
            "computer",
            {
                "brand": "Lenovo",
                "model": "20W9S23S00",
            },
        )

        self.assertEqual(specs["model"], "20W9S23S00")
        self.assertTrue(specs["model_is_machine_type"])
        self.assertNotIn("search_model", specs)
        self.assertNotIn("form_factor", specs)

    def test_builds_phone_specs_with_canonical_variant_and_screen_size(self):
        specs = build_manual_specs(
            "phone",
            {
                "brand": "Apple",
                "model": "iPhone 13",
                "variant": "pro max",
                "screen_size": "6.7",
                "storage": "128",
                "carrier": "unlocked",
            },
        )

        self.assertEqual(specs["variant"], "Pro Max")
        self.assertEqual(specs["screen_size"], '6.7"')
        self.assertEqual(specs["storage_capacity"], "128GB")

    def test_builds_storage_specs_with_canonical_fields(self):
        specs = build_manual_specs(
            "storage",
            {
                "brand": "Samsung",
                "model": "970 EVO Plus",
                "storage": "1500",
                "drive_type": "ssd",
                "drive_form_factor": "m2",
                "interface": "nvme",
            },
        )

        self.assertEqual(specs["capacity"], "1.5TB")
        self.assertEqual(specs["drive_type"], "SSD")
        self.assertEqual(specs["drive_form_factor"], "m.2")
        self.assertEqual(specs["interface"], "NVMe")

    def test_detected_specs_become_editable_gui_values(self):
        values = gui_values_from_detected_specs(
            {
                "brand": "Lenovo",
                "model": "20XW",
                "search_model": "ThinkPad X13 Yoga",
                "form_factor": "laptop",
                "cpu_short": "i5-1135G7",
                "ram_gb": 16,
                "storage": [{"size_gb": 512, "type": "SSD"}],
            }
        )

        self.assertEqual(values["model"], "ThinkPad X13 Yoga")
        self.assertEqual(values["cpu"], "i5-1135G7")
        self.assertEqual(values["ram"], "16")
        self.assertEqual(values["storage"], "512")

    def test_detected_machine_type_model_does_not_become_gui_search_model(self):
        values = gui_values_from_detected_specs(
            {
                "brand": "Lenovo",
                "model": "20W9S23S00",
                "search_model": None,
                "model_is_machine_type": True,
                "form_factor": "laptop",
                "cpu_short": "i7-1185G7",
                "ram_gb": 16,
            }
        )

        self.assertNotIn("model", values)
        self.assertEqual(values["cpu"], "i7-1185G7")


if __name__ == "__main__":
    unittest.main()
