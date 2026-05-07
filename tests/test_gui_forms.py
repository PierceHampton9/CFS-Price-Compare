import unittest

from pc_pricer.gui_forms import (
    fields_for_device,
    validate_computer_mode,
    validate_device_type,
    validate_specs,
)


class GuiFormsTests(unittest.TestCase):
    def test_fields_for_device_marks_required_fields(self):
        fields = fields_for_device("phone")
        required = {field.name for field in fields if field.required}

        self.assertIn("brand", required)
        self.assertIn("model", required)
        self.assertIn("condition", required)
        self.assertIn("storage", required)

    def test_device_type_validation(self):
        self.assertEqual(validate_device_type("phone"), [])
        self.assertEqual(validate_device_type(None), ["Choose a device type."])

    def test_computer_mode_validation(self):
        self.assertEqual(validate_computer_mode("auto"), [])
        self.assertEqual(validate_computer_mode("manual"), [])
        self.assertEqual(validate_computer_mode(None), ["Choose auto-detect or manual entry."])

    def test_phone_requires_brand_model_condition_and_storage(self):
        errors = validate_specs("phone", {"brand": "Apple", "model": "iPhone 13"})

        self.assertIn("Condition is required.", errors)
        self.assertIn("Storage (GB) is required.", errors)

    def test_storage_requires_capacity_drive_type_and_condition(self):
        errors = validate_specs("storage", {"capacity": "1TB"})

        self.assertIn("Condition is required.", errors)
        self.assertIn("Drive type is required.", errors)
        self.assertNotIn("Brand is required.", errors)
        self.assertNotIn("Model is required.", errors)

    def test_computer_requires_form_factor_and_model_or_cpu(self):
        errors = validate_specs(
            "computer",
            {
                "brand": "Apple",
                "condition": "good",
            },
        )

        self.assertIn("Form factor is required.", errors)
        self.assertIn("Enter at least a model or CPU for computer pricing.", errors)


if __name__ == "__main__":
    unittest.main()
