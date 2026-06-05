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

    def test_load_batch_csv_requires_key_columns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "devices.csv"
            path.write_text("brand,model\nLenovo,ThinkPad\n", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "item_id"):
                load_batch_csv(path)

    def test_template_contains_excel_friendly_headers_and_examples(self):
        template = batch_template_csv()

        self.assertIn("item_id,device_type,brand,model,condition", template)
        self.assertIn("001,computer,Lenovo,ThinkPad X13 Yoga,good", template)
        self.assertIn("002,phone,Apple,iPhone 13,good", template)


if __name__ == "__main__":
    unittest.main()
