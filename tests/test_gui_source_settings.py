from pathlib import Path
import unittest

from pc_pricer.gui_source_settings import load_source_settings, save_source_settings


CONFIG_PATH = Path("tests/gui_source_settings_config.yaml")


class GuiSourceSettingsTests(unittest.TestCase):
    def tearDown(self):
        CONFIG_PATH.unlink(missing_ok=True)

    def test_loads_default_source_settings(self):
        settings = load_source_settings("tests/missing_gui_source_settings.yaml")

        self.assertEqual(
            settings,
            {
                "ebay": True,
                "refurb_io": True,
                "amazon_renewed": False,
            },
        )

    def test_saves_source_settings_and_amazon_edge_defaults(self):
        saved = save_source_settings(
            {
                "ebay": True,
                "refurb_io": True,
                "amazon_renewed": True,
            },
            CONFIG_PATH,
        )

        self.assertIs(saved["amazon_renewed"], True)

        text = CONFIG_PATH.read_text(encoding="utf-8")
        self.assertIn("amazon_renewed:", text)
        self.assertIn("enabled: true", text)
        self.assertIn("channel: msedge", text)
        self.assertIn("headless: false", text)

        self.assertEqual(load_source_settings(CONFIG_PATH)["amazon_renewed"], True)


if __name__ == "__main__":
    unittest.main()
