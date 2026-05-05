import io
import unittest
from unittest.mock import patch

from pc_pricer import cli


class CliTests(unittest.TestCase):
    def test_ebay_search_command_prints_listings(self):
        instances = []

        class FakeEbaySource:
            def __init__(self, marketplace="EBAY_CA"):
                self.marketplace = marketplace
                instances.append(self)

            def search(self, query, max_results):
                self.query = query
                self.max_results = max_results
                return [
                    {
                        "source": "ebay",
                        "title": "Lenovo ThinkPad X13 Yoga",
                        "item_price_cad": 300.00,
                        "shipping_cad": 25.00,
                        "total_price_cad": 325.00,
                        "shipping_is_estimated": False,
                        "condition_raw": "Used",
                        "condition_norm": None,
                        "location": "Calgary, AB, CA",
                        "url": "https://www.ebay.ca/itm/example",
                    }
                ]

        stdout = io.StringIO()
        argv = ["pc_pricer", "ebay-search", "ThinkPad", "X13", "--limit", "3"]

        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
            "pc_pricer.cli.EbaySource", FakeEbaySource
        ):
            cli.main()

        self.assertEqual(instances[0].marketplace, "EBAY_CA")
        self.assertEqual(instances[0].query, "ThinkPad X13")
        self.assertEqual(instances[0].max_results, 3)
        output = stdout.getvalue()
        self.assertIn("Lenovo ThinkPad X13 Yoga", output)
        self.assertIn("$325.00 CAD total", output)
        self.assertIn("Condition: good (Used)", output)
        self.assertIn("https://www.ebay.ca/itm/example", output)

    def test_ebay_search_command_does_not_call_unknown_shipping_total(self):
        class FakeEbaySource:
            def __init__(self, marketplace="EBAY_CA"):
                self.marketplace = marketplace

            def search(self, _query, _max_results):
                return [
                    {
                        "source": "ebay",
                        "title": "Dell OptiPlex",
                        "item_price_cad": 180.00,
                        "shipping_cad": None,
                        "total_price_cad": 180.00,
                        "shipping_is_estimated": True,
                        "condition_raw": "Used",
                        "condition_norm": None,
                        "location": None,
                        "url": "https://www.ebay.ca/itm/example",
                    }
                ]

        stdout = io.StringIO()
        argv = ["pc_pricer", "ebay-search", "OptiPlex"]

        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
            "pc_pricer.cli.EbaySource", FakeEbaySource
        ):
            cli.main()

        output = stdout.getvalue()
        self.assertIn("$180.00 CAD item price + unknown shipping", output)
        self.assertNotIn("$180.00 CAD total", output)

    def test_ebay_search_command_reports_runtime_errors(self):
        class FailingEbaySource:
            def __init__(self, marketplace="EBAY_CA"):
                self.marketplace = marketplace

            def search(self, _query, _max_results):
                raise RuntimeError("Missing eBay credentials")

        stderr = io.StringIO()
        argv = ["pc_pricer", "ebay-search", "laptop"]

        with patch("sys.argv", argv), patch("sys.stderr", stderr), patch(
            "pc_pricer.cli.EbaySource", FailingEbaySource
        ):
            with self.assertRaises(SystemExit) as exc:
                cli.main()

        self.assertEqual(exc.exception.code, 1)
        self.assertIn("Missing eBay credentials", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
