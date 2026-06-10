import unittest
from pathlib import Path

from pc_pricer.gui_pricing import price_gui_values

CONFIG_PATH = Path("tests/gui_pricing_config.yaml")


class GuiPricingTests(unittest.TestCase):
    def tearDown(self):
        CONFIG_PATH.unlink(missing_ok=True)

    def test_prices_gui_values_through_pipeline(self):
        source = FakeSource(
            {
                "Apple iPhone 13 128GB unlocked": [
                    _listing("Apple iPhone 13 128GB unlocked", 420),
                ],
                "Apple iPhone 13 128GB": [],
                "Apple iPhone 13": [],
            }
        )

        result, report = price_gui_values(
            "phone",
            {
                "brand": "Apple",
                "model": "iPhone 13",
                "storage": "128",
                "carrier": "unlocked",
                "condition": "good",
            },
            source=source,
        )

        self.assertEqual(result["count"], 1)
        self.assertIn("Manual phone:    Apple iPhone 13 128GB unlocked", report)
        self.assertEqual(source.calls[0], ("Apple iPhone 13 128GB unlocked", 20))

    def test_invalid_gui_condition_uses_neutral_error_message(self):
        with self.assertRaises(RuntimeError) as exc:
            price_gui_values(
                "phone",
                {
                    "brand": "Apple",
                    "model": "iPhone 13",
                    "storage": "128",
                    "condition": "broken",
                },
                source=FakeSource({}),
            )

        self.assertIn("Invalid condition 'broken'", str(exc.exception))

    def test_gui_pricing_reports_disabled_amazon_status(self):
        CONFIG_PATH.write_text(
            """
sources:
  ebay:
    enabled: false
  refurb_io:
    enabled: false
  amazon_renewed:
    enabled: false
""".strip(),
            encoding="utf-8",
        )

        result, report = price_gui_values(
            "phone",
            {
                "brand": "Apple",
                "model": "iPhone 13",
                "storage": "128",
                "carrier": "unlocked",
                "condition": "good",
            },
            config_path=str(CONFIG_PATH),
        )

        amazon_status = next(status for status in result["source_statuses"] if status["source"] == "amazon_renewed")
        self.assertEqual(amazon_status["status"], "disabled")
        self.assertIn("Amazon Renewed: disabled", report)


class FakeSource:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def search(self, query, max_results):
        self.calls.append((query, max_results))
        return self.results.get(query, [])


def _listing(title, price):
    return {
        "source": "ebay",
        "title": title,
        "item_price_cad": price,
        "shipping_cad": 0,
        "total_price_cad": price,
        "shipping_is_estimated": False,
        "condition_raw": "Used",
        "condition_norm": None,
        "is_sold": False,
        "url": "https://www.ebay.ca/itm/example",
    }


if __name__ == "__main__":
    unittest.main()
