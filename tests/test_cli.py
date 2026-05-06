import io
from pathlib import Path
import unittest
from unittest.mock import patch

from pc_pricer import cli


CONFIG_PATH = Path("tests/cli_test_config.yaml")


class CliTests(unittest.TestCase):
    def tearDown(self):
        CONFIG_PATH.unlink(missing_ok=True)

    def test_setup_command_writes_credentials(self):
        stdout = io.StringIO()
        argv = ["pc_pricer", "setup", "--env-file", str(CONFIG_PATH)]

        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
            "pc_pricer.cli.run_setup", return_value=CONFIG_PATH
        ) as setup:
            cli.main()

        setup.assert_called_once_with(str(CONFIG_PATH))
        output = stdout.getvalue()
        self.assertIn("Saved eBay credentials to:", output)
        self.assertIn("pc_pricer ebay-check", output)

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

    def test_ebay_check_command_reports_success(self):
        class FakeEbaySource:
            def __init__(self, marketplace="EBAY_CA"):
                self.marketplace = marketplace
                self.checked = False

            def check_credentials(self):
                self.checked = True
                return {
                    "status": "oauth_token_minted",
                    "message": "OAuth token request succeeded.",
                }

        stdout = io.StringIO()
        argv = ["pc_pricer", "ebay-check"]

        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
            "pc_pricer.cli.EbaySource", FakeEbaySource
        ):
            cli.main()

        output = stdout.getvalue()
        self.assertIn("eBay credential configuration found.", output)
        self.assertIn("OAuth token request succeeded.", output)
        self.assertIn("Marketplace: EBAY_CA", output)

    def test_ebay_check_command_reports_runtime_errors(self):
        class FailingEbaySource:
            def __init__(self, marketplace="EBAY_CA"):
                self.marketplace = marketplace

            def check_credentials(self):
                raise RuntimeError("Missing eBay credentials")

        stderr = io.StringIO()
        argv = ["pc_pricer", "ebay-check"]

        with patch("sys.argv", argv), patch("sys.stderr", stderr), patch(
            "pc_pricer.cli.EbaySource", FailingEbaySource
        ):
            with self.assertRaises(SystemExit) as exc:
                cli.main()

        self.assertEqual(exc.exception.code, 1)
        self.assertIn("Missing eBay credentials", stderr.getvalue())

    def test_price_query_command_prints_report(self):
        class FakeEbaySource:
            def __init__(self, marketplace="EBAY_CA"):
                self.marketplace = marketplace

            def search(self, query, max_results):
                self.query = query
                self.max_results = max_results
                return [
                    _listing("Listing 1", 220, is_sold=False),
                    _listing("Listing 2", 280, is_sold=True),
                ]

        stdout = io.StringIO()
        argv = ["pc_pricer", "price-query", "ThinkPad", "X13", "--limit", "2"]

        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
            "pc_pricer.cli.EbaySource", FakeEbaySource
        ):
            cli.main()

        output = stdout.getvalue()
        self.assertIn("Price estimate", output)
        self.assertIn("Median price:      $250.00 CAD", output)
        self.assertIn("Sold / asking:     1 sold, 1 asking", output)
        self.assertIn("Supporting listings", output)
        self.assertIn("Queries used:", output)
        self.assertIn("  ThinkPad X13", output)
        self.assertNotIn("Tunknown", output)
        self.assertIn("Condition: good (Used)", output)
        self.assertIn("Target condition:  good", output)

    def test_price_query_command_uses_config_defaults(self):
        instances = []

        class FakeEbaySource:
            def __init__(self, marketplace="EBAY_CA"):
                self.marketplace = marketplace
                instances.append(self)

            def search(self, query, max_results):
                self.query = query
                self.max_results = max_results
                return [
                    _listing("Used laptop", 200, condition_raw="Used"),
                    _listing("New laptop", 800, condition_raw="New"),
                ]

        CONFIG_PATH.write_text(
            """
default_condition: any
default_limit: 2
support_limit: 1
sources:
  ebay:
    marketplace: EBAY_US
""".strip(),
            encoding="utf-8",
        )
        stdout = io.StringIO()
        argv = ["pc_pricer", "price-query", "ThinkPad", "--config", str(CONFIG_PATH)]

        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
            "pc_pricer.cli.EbaySource", FakeEbaySource
        ):
            cli.main()

        self.assertEqual(instances[0].marketplace, "EBAY_US")
        self.assertEqual(instances[0].max_results, 2)
        output = stdout.getvalue()
        self.assertIn("Conservative est.: $450.00 CAD - $475.00 CAD", output)
        self.assertIn("Asking median:     $500.00 CAD", output)
        self.assertIn("Target condition:  any", output)
        self.assertIn("Filtered out:      0", output)

    def test_price_query_flags_override_config_defaults(self):
        instances = []

        class FakeEbaySource:
            def __init__(self, marketplace="EBAY_CA"):
                self.marketplace = marketplace
                instances.append(self)

            def search(self, _query, max_results):
                self.max_results = max_results
                return [
                    _listing("Used laptop", 200, condition_raw="Used"),
                    _listing("New laptop", 800, condition_raw="New"),
                ]

        CONFIG_PATH.write_text(
            """
default_condition: any
default_limit: 9
sources:
  ebay:
    marketplace: EBAY_US
""".strip(),
            encoding="utf-8",
        )
        stdout = io.StringIO()
        argv = [
            "pc_pricer",
            "price-query",
            "ThinkPad",
            "--config",
            str(CONFIG_PATH),
            "--condition",
            "good",
            "--limit",
            "1",
            "--marketplace",
            "EBAY_CA",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
            "pc_pricer.cli.EbaySource", FakeEbaySource
        ):
            cli.main()

        self.assertEqual(instances[0].marketplace, "EBAY_CA")
        self.assertEqual(instances[0].max_results, 1)
        output = stdout.getvalue()
        self.assertIn("Conservative est.: $180.00 CAD - $190.00 CAD", output)
        self.assertIn("Target condition:  good", output)

    def test_price_query_sorts_misordered_asking_discount_config(self):
        class FakeEbaySource:
            def __init__(self, marketplace="EBAY_CA"):
                self.marketplace = marketplace

            def search(self, _query, _max_results):
                return [_listing("Used laptop", 200, condition_raw="Used")]

        CONFIG_PATH.write_text(
            """
asking_discount_low: 0.20
asking_discount_high: 0.10
sources:
  ebay:
    marketplace: EBAY_CA
""".strip(),
            encoding="utf-8",
        )
        stdout = io.StringIO()
        argv = ["pc_pricer", "price-query", "ThinkPad", "--config", str(CONFIG_PATH)]

        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
            "pc_pricer.cli.EbaySource", FakeEbaySource
        ):
            cli.main()

        output = stdout.getvalue()
        self.assertIn("Conservative est.: $160.00 CAD - $180.00 CAD", output)
        self.assertIn("Pricing basis:    active asking listings, discounted 10-20%", output)

    def test_price_query_command_filters_condition_and_parts_by_default(self):
        class FakeEbaySource:
            def __init__(self, marketplace="EBAY_CA"):
                self.marketplace = marketplace

            def search(self, _query, _max_results):
                return [
                    _listing("Used laptop", 200, condition_raw="Used"),
                    _listing("New laptop", 800, condition_raw="New"),
                    _listing("ThinkPad motherboard", 300, condition_raw="Used"),
                ]

        stdout = io.StringIO()
        argv = ["pc_pricer", "price-query", "ThinkPad"]

        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
            "pc_pricer.cli.EbaySource", FakeEbaySource
        ):
            cli.main()

        output = stdout.getvalue()
        self.assertIn("Conservative est.: $180.00 CAD - $190.00 CAD", output)
        self.assertIn("Comparables:       1", output)
        self.assertIn("Filtered out:      2", output)
        self.assertIn("condition mismatch: 1", output)
        self.assertIn("parts/accessory listing: 1", output)
        self.assertIn("Used laptop", output)
        self.assertNotIn("New laptop", output)
        self.assertNotIn("ThinkPad motherboard", output)

    def test_price_query_command_can_disable_condition_filter(self):
        class FakeEbaySource:
            def __init__(self, marketplace="EBAY_CA"):
                self.marketplace = marketplace

            def search(self, _query, _max_results):
                return [
                    _listing("Used laptop", 200, condition_raw="Used"),
                    _listing("New laptop", 800, condition_raw="New"),
                ]

        stdout = io.StringIO()
        argv = ["pc_pricer", "price-query", "ThinkPad", "--condition", "any"]

        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
            "pc_pricer.cli.EbaySource", FakeEbaySource
        ):
            cli.main()

        output = stdout.getvalue()
        self.assertIn("Conservative est.: $450.00 CAD - $475.00 CAD", output)
        self.assertIn("Asking median:     $500.00 CAD", output)
        self.assertIn("Target condition:  any", output)
        self.assertIn("Filtered out:      0", output)

    def test_price_query_command_can_print_json(self):
        class FakeEbaySource:
            def __init__(self, marketplace="EBAY_CA"):
                self.marketplace = marketplace

            def search(self, _query, _max_results):
                return [_listing("Listing", 250)]

        stdout = io.StringIO()
        argv = ["pc_pricer", "price-query", "laptop", "--json"]

        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
            "pc_pricer.cli.EbaySource", FakeEbaySource
        ):
            cli.main()

        self.assertIn('"median_price_cad": 250.0', stdout.getvalue())

    def test_price_manual_command_prints_report_from_manual_specs(self):
        class FakeEbaySource:
            def __init__(self, marketplace="EBAY_CA"):
                self.marketplace = marketplace

            def search(self, query, max_results):
                self.query = query
                self.max_results = max_results
                return [_listing("Manual laptop listing", 300)]

        stdout = io.StringIO()
        argv = [
            "pc_pricer",
            "price-manual",
            "--brand",
            "Lenovo",
            "--model",
            "ThinkPad X13 Yoga",
            "--form-factor",
            "laptop",
            "--cpu",
            "i5-1135G7",
            "--ram",
            "16",
            "--storage",
            "512",
            "--limit-per-query",
            "4",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
            "pc_pricer.cli.EbaySource", FakeEbaySource
        ):
            cli.main()

        output = stdout.getvalue()
        self.assertIn("Manual specs:    Lenovo ThinkPad X13 Yoga i5-1135G7 16GB", output)
        self.assertIn("Queries used:", output)
        self.assertIn("T2: Lenovo ThinkPad X13 Yoga i5-1135G7 16GB", output)
        self.assertIn("Conservative est.: $270.00 CAD - $285.00 CAD", output)
        self.assertIn("Asking median:     $300.00 CAD", output)
        self.assertIn("Asking prices only", output)

    def test_price_manual_command_can_print_json(self):
        class FakeEbaySource:
            def __init__(self, marketplace="EBAY_CA"):
                self.marketplace = marketplace

            def search(self, _query, _max_results):
                return [_listing("Manual desktop listing", 200)]

        stdout = io.StringIO()
        argv = [
            "pc_pricer",
            "price-manual",
            "--form-factor",
            "desktop",
            "--cpu",
            "i5-7500",
            "--ram",
            "16",
            "--storage",
            "256",
            "--json",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
            "pc_pricer.cli.EbaySource", FakeEbaySource
        ):
            cli.main()

        output = stdout.getvalue()
        self.assertIn('"median_price_cad": 200.0', output)
        self.assertIn('"input_method": "manual"', output)

    def test_price_detect_command_prints_report_from_detected_specs(self):
        class FakeEbaySource:
            def __init__(self, marketplace="EBAY_CA"):
                self.marketplace = marketplace

            def search(self, query, max_results):
                self.query = query
                self.max_results = max_results
                return [_listing("Detected laptop listing", 300)]

        specs = {
            "brand": "Lenovo",
            "model": "ThinkPad X13 Yoga",
            "oem_sku": None,
            "form_factor": "laptop",
            "cpu": "Intel Core i5-1135G7",
            "cpu_short": "i5-1135G7",
            "ram_gb": 16,
            "search_model": "ThinkPad X13 Yoga",
            "serial_number": "private-serial",
        }

        stdout = io.StringIO()
        argv = ["pc_pricer", "price-detect", "--limit-per-query", "4"]

        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
            "pc_pricer.cli.EbaySource", FakeEbaySource
        ), patch("pc_pricer.cli.detect_specs", return_value=specs) as detect:
            cli.main()

        detect.assert_called_once_with(include_raw=False)
        output = stdout.getvalue()
        self.assertIn("Detected specs:    Lenovo ThinkPad X13 Yoga i5-1135G7 16GB", output)
        self.assertIn("Queries used:", output)
        self.assertIn("T2: Lenovo ThinkPad X13 Yoga i5-1135G7 16GB", output)
        self.assertIn("Conservative est.: $270.00 CAD - $285.00 CAD", output)
        self.assertNotIn("private-serial", output)

    def test_price_detect_command_can_print_json_with_raw_specs(self):
        class FakeEbaySource:
            def __init__(self, marketplace="EBAY_CA"):
                self.marketplace = marketplace

            def search(self, _query, _max_results):
                return [_listing("Detected laptop listing", 300)]

        specs = {
            "brand": "Lenovo",
            "model": "ThinkPad X13 Yoga",
            "form_factor": "laptop",
            "cpu_short": "i5-1135G7",
            "ram_gb": 16,
            "raw": {"ComputerSystem": {"Model": "ThinkPad X13 Yoga"}},
        }

        stdout = io.StringIO()
        argv = ["pc_pricer", "price-detect", "--raw", "--json"]

        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
            "pc_pricer.cli.EbaySource", FakeEbaySource
        ), patch("pc_pricer.cli.detect_specs", return_value=specs):
            cli.main()

        output = stdout.getvalue()
        self.assertIn('"median_price_cad": 300.0', output)
        self.assertIn('"raw": {', output)

    def test_price_detect_command_json_omits_serial_number_by_default(self):
        class FakeEbaySource:
            def __init__(self, marketplace="EBAY_CA"):
                self.marketplace = marketplace

            def search(self, _query, _max_results):
                return [_listing("Detected laptop listing", 300)]

        specs = {
            "brand": "Lenovo",
            "model": "ThinkPad X13 Yoga",
            "form_factor": "laptop",
            "cpu_short": "i5-1135G7",
            "ram_gb": 16,
            "serial_number": "private-serial",
        }

        stdout = io.StringIO()
        argv = ["pc_pricer", "price-detect", "--json"]

        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
            "pc_pricer.cli.EbaySource", FakeEbaySource
        ), patch("pc_pricer.cli.detect_specs", return_value=specs):
            cli.main()

        output = stdout.getvalue()
        self.assertIn('"median_price_cad": 300.0', output)
        self.assertNotIn("private-serial", output)

    def test_price_detect_command_reports_no_results(self):
        class FakeEbaySource:
            def __init__(self, marketplace="EBAY_CA"):
                self.marketplace = marketplace

            def search(self, _query, _max_results):
                return []

        specs = {
            "brand": "Lenovo",
            "model": "ThinkPad X13 Yoga",
            "form_factor": "laptop",
            "cpu_short": "i5-1135G7",
            "ram_gb": 16,
        }

        stdout = io.StringIO()
        argv = ["pc_pricer", "price-detect"]

        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
            "pc_pricer.cli.EbaySource", FakeEbaySource
        ), patch("pc_pricer.cli.detect_specs", return_value=specs):
            cli.main()

        output = stdout.getvalue()
        self.assertIn("Detected specs:    Lenovo ThinkPad X13 Yoga i5-1135G7 16GB", output)
        self.assertIn("Queries used:", output)
        self.assertIn("No usable comparable listings found.", output)

    def test_price_detect_command_reports_no_generated_queries(self):
        searched = []

        class FakeEbaySource:
            def __init__(self, marketplace="EBAY_CA"):
                self.marketplace = marketplace

            def search(self, _query, _max_results):
                searched.append(True)
                return []

        stdout = io.StringIO()
        argv = ["pc_pricer", "price-detect"]

        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
            "pc_pricer.cli.EbaySource", FakeEbaySource
        ), patch("pc_pricer.cli.detect_specs", return_value={}):
            cli.main()

        output = stdout.getvalue()
        self.assertEqual(searched, [])
        self.assertIn("No usable comparable listings found.", output)
        self.assertIn("No usable search queries", output)

    def test_price_detect_command_reports_detection_errors(self):
        stderr = io.StringIO()
        argv = ["pc_pricer", "price-detect"]

        with patch("sys.argv", argv), patch("sys.stderr", stderr), patch(
            "pc_pricer.cli.detect_specs", side_effect=RuntimeError("Windows only")
        ):
            with self.assertRaises(SystemExit) as exc:
                cli.main()

        self.assertEqual(exc.exception.code, 1)
        self.assertIn("Windows only", stderr.getvalue())


def _listing(title, total_price, is_sold=False, condition_raw="Used"):
    return {
        "source": "ebay",
        "title": title,
        "item_price_cad": total_price,
        "shipping_cad": 0,
        "total_price_cad": total_price,
        "shipping_is_estimated": False,
        "condition_raw": condition_raw,
        "condition_norm": None,
        "is_sold": is_sold,
        "query_tier": 1,
        "url": "https://www.ebay.ca/itm/example",
    }


if __name__ == "__main__":
    unittest.main()
