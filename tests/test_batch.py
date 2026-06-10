import tempfile
from pathlib import Path
import unittest

from pc_pricer.batch import batch_template_csv, load_batch_csv


class BatchImportTests(unittest.TestCase):
    def test_load_batch_csv_validates_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "devices.csv"
            path.write_text(
                "\n".join(
                    [
                        "item_id,device_type,brand,model,condition,form_factor,cpu,ram,storage,storage_type",
                        "001,computer,Lenovo,ThinkPad X13 Yoga,good,laptop,i5-1135G7,16,512,SSD",
                        "002,computer,Lenovo,ThinkPad,good,,i5-1135G7,16,512,SSD",
                    ]
                ),
                encoding="utf-8",
            )

            items = load_batch_csv(path)

        self.assertEqual(len(items), 2)
        self.assertTrue(items[0].is_valid)
        self.assertEqual(items[0].item_id, "001")
        self.assertEqual(items[0].device_type, "computer")
        self.assertEqual(items[0].values["form_factor"], "laptop")
        self.assertFalse(items[1].is_valid)
        self.assertIn("Form factor is required.", items[1].errors)

    def test_batch_template_omits_computer_storage_type(self):
        template = batch_template_csv()

        self.assertIn("item_id,device_type,brand,model,condition,form_factor,cpu,ram,storage,oem_sku", template)
        self.assertNotIn("storage_type", template.splitlines()[0])

    def test_load_batch_csv_allows_model_number_without_computer_form_factor(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "devices.csv"
            path.write_text(
                "\n".join(
                    [
                        "item_id,device_type,brand,model,condition,form_factor",
                        "001,computer,Lenovo,20W9S23S00,good,",
                    ]
                ),
                encoding="utf-8",
            )

            items = load_batch_csv(path)

        self.assertTrue(items[0].is_valid)
        self.assertEqual(items[0].values["model"], "20W9S23S00")

    def test_load_batch_csv_requires_key_columns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "devices.csv"
            path.write_text("brand,model\nLenovo,ThinkPad\n", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "item_id"):
                load_batch_csv(path)

    def test_load_batch_csv_reports_blank_device_type_directly(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "devices.csv"
            path.write_text(
                "\n".join(
                    [
                        "item_id,device_type,brand,model,condition,form_factor",
                        "001,,Lenovo,ThinkPad,good,laptop",
                    ]
                ),
                encoding="utf-8",
            )

            items = load_batch_csv(path)

        self.assertFalse(items[0].is_valid)
        self.assertIn("Device type is required.", items[0].errors)

    def test_template_contains_excel_friendly_headers_and_examples(self):
        template = batch_template_csv()

        self.assertIn("item_id,device_type,brand,model,condition", template)
        self.assertIn("001,computer,Lenovo,ThinkPad X13 Yoga,good", template)
        self.assertIn("002,phone,Apple,iPhone 13,good", template)

    def test_static_all_devices_template_columns_stay_aligned(self):
        items = load_batch_csv(Path("batch-templates/batch-template-all-devices.csv"))
        storage = items[-1]

        self.assertTrue(storage.is_valid)
        self.assertEqual(storage.device_type, "storage")
        self.assertEqual(storage.values["capacity"], "1TB")
        self.assertEqual(storage.values["drive_type"], "ssd")
        self.assertEqual(storage.values["drive_form_factor"], "m.2")
        self.assertEqual(storage.values["interface"], "nvme")
        self.assertEqual(storage.values["notes"], "Example storage row")


if __name__ == "__main__":
    unittest.main()
