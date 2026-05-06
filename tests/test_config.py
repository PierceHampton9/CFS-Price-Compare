from pathlib import Path
import unittest
from unittest.mock import patch

from pc_pricer.config import default_config_path, load_config


CONFIG_PATH = Path("tests/config_test.yaml")


class ConfigTests(unittest.TestCase):
    def tearDown(self):
        CONFIG_PATH.unlink(missing_ok=True)

    def test_missing_config_returns_defaults(self):
        config = load_config("tests/missing_config.yaml")

        self.assertEqual(config["default_condition"], "good")
        self.assertEqual(config["default_limit"], 10)
        self.assertEqual(config["sources"]["ebay"]["marketplace"], "EBAY_CA")

    def test_loads_simple_values_and_nested_source_config(self):
        CONFIG_PATH.write_text(
            """
default_condition: any
default_limit: 4
wide_iqr_ratio: 0.5
sources:
  ebay:
    enabled: false
    marketplace: EBAY_US
""".strip(),
            encoding="utf-8",
        )

        config = load_config(CONFIG_PATH)

        self.assertEqual(config["default_condition"], "any")
        self.assertEqual(config["default_limit"], 4)
        self.assertEqual(config["wide_iqr_ratio"], 0.5)
        self.assertIs(config["sources"]["ebay"]["enabled"], False)
        self.assertEqual(config["sources"]["ebay"]["marketplace"], "EBAY_US")
        self.assertEqual(config["support_limit"], 5)

    def test_rejects_unsupported_indentation(self):
        CONFIG_PATH.write_text("sources:\n ebay:\n", encoding="utf-8")

        with self.assertRaises(RuntimeError):
            load_config(CONFIG_PATH)

    def test_default_config_path_uses_working_directory_for_source_runs(self):
        with patch("pc_pricer.config.sys.frozen", False, create=True):
            self.assertEqual(default_config_path(), Path.cwd() / "config.yaml")

    def test_default_config_path_uses_exe_directory_for_packaged_runs(self):
        exe_path = Path("C:/release/pc_pricer.exe")
        with patch("pc_pricer.config.sys.frozen", True, create=True), patch(
            "pc_pricer.config.sys.executable", str(exe_path)
        ):
            self.assertEqual(default_config_path(), exe_path.parent / "config.yaml")


if __name__ == "__main__":
    unittest.main()
