import unittest

from pc_pricer.gui_forms import (
    fields_for_device,
    option_label,
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

    def test_computer_fields_do_not_ask_for_storage_type(self):
        field_names = {field.name for field in fields_for_device("computer")}

        self.assertIn("storage", field_names)
        self.assertNotIn("storage_type", field_names)

    def test_condition_options_are_best_to_worst_with_good_recommended(self):
        condition = next(field for field in fields_for_device("phone") if field.name == "condition")

        self.assertEqual(condition.options, ("mint", "excellent", "good", "any"))
        self.assertEqual(condition.default, "good")
        self.assertEqual(option_label(condition, "good"), "Good (recommended)")

    def test_option_labels_capitalize_user_facing_choices(self):
        phone = {field.name: field for field in fields_for_device("phone")}
        storage = {field.name: field for field in fields_for_device("storage")}

        self.assertEqual(option_label(phone["carrier"], "unlocked"), "Unlocked")
        self.assertEqual(option_label(storage["drive_type"], "ssd"), "SSD")
        self.assertEqual(option_label(storage["drive_form_factor"], "m.2"), "M.2")

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

    def test_computer_model_number_can_defer_form_factor_to_lookup(self):
        errors = validate_specs(
            "computer",
            {
                "brand": "Lenovo",
                "model": "20W9S23S00",
                "condition": "good",
            },
        )

        self.assertNotIn("Form factor is required.", errors)


if __name__ == "__main__":
    unittest.main()
