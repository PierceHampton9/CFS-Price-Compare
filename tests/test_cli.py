import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pc_pricer import cli


CONFIG_PATH = Path("tests/cli_test_config.yaml")


class CliTests(unittest.TestCase):
    def setUp(self):
        self.refurb_patcher = patch("pc_pricer.sources.factory.RefurbIoSource", DisabledRefurbSource)
        self.ebay_factory_patcher = patch("pc_pricer.sources.factory.EbaySource", DelegatingEbaySource)
        self.refurb_patcher.start()
        self.ebay_factory_patcher.start()

    def tearDown(self):
        self.ebay_factory_patcher.stop()
        self.refurb_patcher.stop()
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
        self.assertIn("Location:  Calgary, AB, Canada", output)
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
        self.assertNotIn("Sold / asking:", output)
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
        self.assertIn("Conservative est.: $475.00 CAD - $500.00 CAD", output)
        self.assertIn("eBay median:       $500.00 CAD", output)
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
        self.assertIn("Conservative est.: $475.00 CAD - $500.00 CAD", output)
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
        self.assertIn("Pricing basis:    eBay active listings, discounted 10-20%", output)

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
        self.assertIn("Conservative est.: $475.00 CAD - $500.00 CAD", output)
        self.assertIn("Comparables:       2", output)
        self.assertIn("Filtered out:      1", output)
        self.assertIn("parts/accessory listing: 1", output)
        self.assertIn("Used laptop", output)
        self.assertIn("New laptop", output)
        self.assertNotIn("ThinkPad motherboard", output)

    def test_price_query_command_uses_device_type_for_accessory_filtering(self):
        class FakeEbaySource:
            def __init__(self, marketplace="EBAY_CA"):
                self.marketplace = marketplace

            def search(self, _query, _max_results):
                return [
                    _listing("Apple iPhone 13 128GB Unlocked", 400),
                    _listing("For iPhone 13 case shockproof cover", 20),
                ]

        stdout = io.StringIO()
        argv = ["pc_pricer", "price-query", "iPhone", "13", "--device-type", "phone", "--condition", "any"]

        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
            "pc_pricer.cli.EbaySource", FakeEbaySource
        ):
            cli.main()

        output = stdout.getvalue()
        self.assertIn("Comparables:       1", output)
        self.assertIn("parts/accessory listing: 1", output)
        self.assertIn("Apple iPhone 13 128GB Unlocked", output)
        self.assertNotIn("For iPhone 13 case", output)

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
        self.assertIn("Conservative est.: $475.00 CAD - $500.00 CAD", output)
        self.assertIn("eBay median:       $500.00 CAD", output)
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
        self.assertIn("Conservative est.: $285.00 CAD - $300.00 CAD", output)
        self.assertIn("eBay median:       $300.00 CAD", output)
        self.assertIn("eBay active listing estimate", output)

    def test_price_manual_command_prices_phone_specs(self):
        class FakeEbaySource:
            def __init__(self, marketplace="EBAY_CA"):
                self.marketplace = marketplace

            def search(self, query, max_results):
                self.query = query
                self.max_results = max_results
                return [_listing("iPhone 13 128GB unlocked", 420)]

        stdout = io.StringIO()
        argv = [
            "pc_pricer",
            "price-manual",
            "--device-type",
            "phone",
            "--brand",
            "Apple",
            "--model",
            "iPhone 13",
            "--storage",
            "128",
            "--carrier",
            "unlocked",
            "--limit-per-query",
            "4",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
            "pc_pricer.cli.EbaySource", FakeEbaySource
        ):
            cli.main()

        output = stdout.getvalue()
        self.assertIn("Manual phone:    Apple iPhone 13 128GB unlocked", output)
        self.assertIn("T1: Apple iPhone 13 128GB unlocked", output)
        self.assertIn("T2: Apple iPhone 13 128GB", output)
        self.assertIn("Conservative est.: $399.00 CAD - $420.00 CAD", output)

    def test_price_manual_command_accepts_variant_and_screen_size(self):
        class FakeEbaySource:
            def __init__(self, marketplace="EBAY_CA"):
                self.marketplace = marketplace

            def search(self, _query, _max_results):
                return [_listing("iPhone 13 Pro Max 128GB unlocked", 650)]

        stdout = io.StringIO()
        argv = [
            "pc_pricer",
            "price-manual",
            "--device-type",
            "phone",
            "--brand",
            "Apple",
            "--model",
            "iPhone 13",
            "--variant",
            "pro max",
            "--screen-size",
            "6.7",
            "--storage",
            "128",
            "--carrier",
            "unlocked",
            "--json",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
            "pc_pricer.cli.EbaySource", FakeEbaySource
        ):
            cli.main()

        output = stdout.getvalue()
        self.assertIn('"variant": "Pro Max"', output)
        self.assertIn('"screen_size": "6.7\\""', output)
        self.assertIn('"text": "Apple iPhone 13 Pro Max 6.7\\" 128GB unlocked"', output)

    def test_price_manual_command_normalizes_storage_form_factor_alias(self):
        class FakeEbaySource:
            def __init__(self, marketplace="EBAY_CA"):
                self.marketplace = marketplace

            def search(self, _query, _max_results):
                return [_listing("Samsung 970 EVO Plus 1.5TB NVMe", 70)]

        stdout = io.StringIO()
        argv = [
            "pc_pricer",
            "price-manual",
            "--device-type",
            "storage",
            "--brand",
            "Samsung",
            "--model",
            "970 EVO Plus",
            "--storage",
            "1500",
            "--drive-type",
            "ssd",
            "--drive-form-factor",
            "m2",
            "--interface",
            "nvme",
            "--json",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
            "pc_pricer.cli.EbaySource", FakeEbaySource
        ):
            cli.main()

        output = stdout.getvalue()
        self.assertIn('"device_type": "storage"', output)
        self.assertIn('"capacity": "1.5TB"', output)
        self.assertIn('"drive_type": "SSD"', output)
        self.assertIn('"drive_form_factor": "m.2"', output)
        self.assertIn('"interface": "NVMe"', output)
        self.assertIn('"text": "Samsung 970 EVO Plus 1.5TB SSD m.2 NVMe"', output)

    def test_price_manual_command_displays_canonical_monitor_specs(self):
        class FakeEbaySource:
            def __init__(self, marketplace="EBAY_CA"):
                self.marketplace = marketplace

            def search(self, _query, _max_results):
                return [_listing("Dell U2419H monitor", 120)]

        stdout = io.StringIO()
        argv = [
            "pc_pricer",
            "price-manual",
            "--device-type",
            "monitor",
            "--brand",
            "Dell",
            "--model",
            "U2419H",
            "--size",
            "24",
            "--resolution",
            "1080p",
            "--refresh-rate",
            "60",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
            "pc_pricer.cli.EbaySource", FakeEbaySource
        ):
            cli.main()

        output = stdout.getvalue()
        self.assertIn('Manual monitor:    Dell U2419H 24" 1080p 60Hz', output)
        self.assertIn('T1: Dell U2419H 24" 1080p 60Hz monitor', output)

    def test_price_manual_command_requires_form_factor_for_computers(self):
        stderr = io.StringIO()
        argv = ["pc_pricer", "price-manual", "--brand", "Lenovo", "--model", "ThinkPad"]

        with patch("sys.argv", argv), patch("sys.stderr", stderr):
            with self.assertRaises(SystemExit) as exc:
                cli.main()

        self.assertEqual(exc.exception.code, 1)
        self.assertIn("Computer pricing requires a form factor", stderr.getvalue())

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
        self.assertIn("Conservative est.: $285.00 CAD - $300.00 CAD", output)
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

    def test_validate_batch_command_reports_invalid_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "devices.csv"
            path.write_text(
                "\n".join(
                    [
                        "item_id,device_type,brand,model,condition,form_factor",
                        "001,computer,Lenovo,ThinkPad,good,",
                    ]
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            argv = ["pc_pricer", "validate-batch", str(path)]

            with patch("sys.argv", argv), patch("sys.stdout", stdout):
                with self.assertRaises(SystemExit) as exc:
                    cli.main()

        self.assertEqual(exc.exception.code, 1)
        output = stdout.getvalue()
        self.assertIn("Batch validation", output)
        self.assertIn("Invalid: 1", output)
        self.assertIn("Form factor is required.", output)

    def test_export_template_command_writes_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "template.csv"
            stdout = io.StringIO()
            argv = ["pc_pricer", "export-template", "--output", str(path)]

            with patch("sys.argv", argv), patch("sys.stdout", stdout):
                cli.main()

            contents = path.read_text(encoding="utf-8")

        self.assertIn("Saved batch CSV template", stdout.getvalue())
        self.assertIn("item_id,device_type,brand,model,condition", contents)
        self.assertIn("ThinkPad X13 Yoga", contents)

    def test_price_batch_command_writes_reports_and_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "devices.csv"
            output_dir = Path(temp_dir) / "reports"
            input_path.write_text(
                "\n".join(
                    [
                        "item_id,device_type,brand,model,condition,form_factor,cpu,ram,storage,storage_type",
                        "001,computer,Lenovo,ThinkPad X13 Yoga,good,laptop,i5-1135G7,16,512,SSD",
                    ]
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            argv = ["pc_pricer", "price-batch", str(input_path), "--output", str(output_dir)]

            with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
                "pc_pricer.cli._pricing_sources", return_value=[StaticSource()]
            ):
                cli.main()

            summary = output_dir / "batch_summary.csv"
            results = output_dir / "batch_results.json"
            report = output_dir / "reports" / "001_001.txt"
            results_exists = results.exists()
            summary_text = summary.read_text(encoding="utf-8")
            report_text = report.read_text(encoding="utf-8")

        self.assertIn("Batch complete: 1 completed, 0 failed.", stdout.getvalue())
        self.assertTrue(results_exists)
        self.assertIn("001", summary_text)
        self.assertIn("Price estimate", report_text)
        self.assertIn("Lenovo ThinkPad", report_text)

    def test_price_batch_command_keeps_summary_after_unexpected_row_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "devices.csv"
            output_dir = Path(temp_dir) / "reports"
            input_path.write_text(
                "\n".join(
                    [
                        "item_id,device_type,brand,model,condition,form_factor,cpu,ram,storage,storage_type",
                        "001,computer,Lenovo,ThinkPad X13 Yoga,good,laptop,i5-1135G7,16,512,SSD",
                        "002,computer,Dell,OptiPlex 7050,good,desktop,i5-7500,16,256,SSD",
                    ]
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            argv = ["pc_pricer", "price-batch", str(input_path), "--output", str(output_dir)]

            with patch("sys.argv", argv), patch("sys.stdout", stdout), patch(
                "pc_pricer.cli._pricing_sources", return_value=[UnexpectedOnceSource()]
            ):
                cli.main()

            summary_text = (output_dir / "batch_summary.csv").read_text(encoding="utf-8")
            results_text = (output_dir / "batch_results.json").read_text(encoding="utf-8")
            second_report_exists = (output_dir / "reports" / "002_002.txt").exists()

        self.assertIn("Batch complete: 1 completed, 1 failed.", stdout.getvalue())
        self.assertIn("unexpected source failure", summary_text)
        self.assertIn("Dell OptiPlex 7050", summary_text)
        self.assertIn("unexpected source failure", results_text)
        self.assertTrue(second_report_exists)


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


class DisabledRefurbSource:
    name = "refurb_io"

    def __init__(self, *args, **kwargs):
        self.enabled = False

    def search(self, _query, _max_results):
        return []


class DelegatingEbaySource:
    def __new__(cls, *args, **kwargs):
        return cli.EbaySource(*args, **kwargs)


class StaticSource:
    name = "ebay"
    enabled = True

    def search(self, _query, _max_results):
        return [_listing("Lenovo ThinkPad listing", 300)]


class UnexpectedOnceSource:
    name = "ebay"
    enabled = True

    def __init__(self):
        self.calls = 0

    def search(self, _query, _max_results):
        self.calls += 1
        if self.calls == 1:
            raise ValueError("unexpected source failure")
        return [_listing("Dell OptiPlex listing", 250)]


if __name__ == "__main__":
    unittest.main()
