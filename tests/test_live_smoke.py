import json
from pathlib import Path
import tempfile
import unittest

from pc_pricer.live_smoke import run_live_smoke


class LiveSmokeTests(unittest.TestCase):
    def test_run_live_smoke_writes_summary_files(self):
        config = _write_config(
            """
sources:
  ebay:
    enabled: true
  refurb_io:
    enabled: true
  amazon_renewed:
    enabled: false
""".strip()
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "smoke"
            payload = run_live_smoke(
                config_path=str(config),
                output_dir=output_dir,
                price_cases=[
                    {
                        "name": "fake_laptop",
                        "min_comparables": 1,
                        "price_floor_cad": 100,
                        "price_ceiling_cad": 500,
                        "specs": {
                            "device_type": "computer",
                            "brand": "Lenovo",
                            "model": "ThinkPad X13 Yoga Gen 2",
                            "form_factor": "laptop",
                            "cpu_short": "i5-1135G7",
                            "ram_gb": 16,
                        },
                    }
                ],
                refurb_urls=["https://ca.refurb.io/products/example"],
                source_factory=lambda _config: [FakeEbaySource()],
                html_fetcher=lambda _url: _refurb_fixture(),
            )

            summary_json = output_dir / "live_smoke_summary.json"
            summary_text = output_dir / "live_smoke_summary.txt"
            summary_json_exists = summary_json.exists()
            summary_text_exists = summary_text.exists()
            saved_payload = json.loads(summary_json.read_text(encoding="utf-8"))
            summary_text_value = summary_text.read_text(encoding="utf-8")

        config.unlink(missing_ok=True)
        self.assertEqual(payload["overall_status"], "ok")
        self.assertTrue(summary_json_exists)
        self.assertTrue(summary_text_exists)
        self.assertEqual(saved_payload["summary"]["error"], 0)
        self.assertIn("fake_laptop", summary_text_value)

    def test_run_live_smoke_marks_missing_comparables_as_error(self):
        config = _write_config(
            """
sources:
  ebay:
    enabled: true
  refurb_io:
    enabled: false
  amazon_renewed:
    enabled: false
""".strip()
        )

        payload = run_live_smoke(
            config_path=str(config),
            price_cases=[
                {
                    "name": "empty_case",
                    "specs": {
                        "device_type": "computer",
                        "brand": "Lenovo",
                        "model": "ThinkPad X13 Yoga Gen 2",
                        "form_factor": "laptop",
                    },
                }
            ],
            source_factory=lambda _config: [EmptyEbaySource()],
            html_fetcher=lambda _url: "",
        )

        config.unlink(missing_ok=True)
        self.assertEqual(payload["overall_status"], "error")
        errors = [check for check in payload["checks"] if check["severity"] == "error"]
        self.assertTrue(any(check["name"] == "empty_case" for check in errors))

    def test_detected_spec_smoke_case_checks_identifier_and_queries(self):
        config = _write_config(
            """
sources:
  ebay:
    enabled: true
  refurb_io:
    enabled: false
  amazon_renewed:
    enabled: false
""".strip()
        )

        payload = run_live_smoke(
            config_path=str(config),
            price_cases=[
                {
                    "name": "detected_case",
                    "require_identification": True,
                    "required_query_terms": ["ThinkPad X13 Yoga Gen 2"],
                    "specs": {
                        "device_type": "computer",
                        "brand": "LENOVO",
                        "model": "20W9S23S00",
                        "model_is_machine_type": True,
                        "form_factor": "laptop",
                        "cpu_short": "i7-1185G7",
                        "ram_gb": 16,
                        "storage": [{"size_gb": 238, "type": "SSD"}],
                    },
                }
            ],
            source_factory=lambda _config: [DetectedCaseSource()],
            html_fetcher=lambda _url: "",
        )

        config.unlink(missing_ok=True)
        self.assertEqual(payload["overall_status"], "ok")
        case = next(check for check in payload["checks"] if check["name"] == "detected_case")
        self.assertEqual(case["result"]["device_identification"]["status"], "identified")

    def test_run_live_smoke_warns_on_refurb_io_partial_parse(self):
        config = _write_config(
            """
sources:
  ebay:
    enabled: false
  refurb_io:
    enabled: true
  amazon_renewed:
    enabled: false
""".strip()
        )

        payload = run_live_smoke(
            config_path=str(config),
            price_cases=[],
            refurb_urls=["https://ca.refurb.io/products/example"],
            source_factory=lambda _config: [],
            html_fetcher=lambda _url: "<html><body><h1>Refurb Product</h1><span>$199.00</span></body></html>",
        )

        config.unlink(missing_ok=True)
        self.assertEqual(payload["overall_status"], "warning")
        warnings = [check for check in payload["checks"] if check["severity"] == "warning"]
        self.assertTrue(any(check["name"] == "refurb_io_live_parser_1" for check in warnings))


class FakeEbaySource:
    name = "ebay"
    enabled = True

    def check_credentials(self):
        return {"message": "OAuth token request succeeded."}

    def search(self, _query, _max_results):
        return [
            {
                "source": "ebay",
                "title": "Lenovo ThinkPad X13 Yoga Gen 2 i5-1135G7 16GB",
                "item_price_cad": 300.0,
                "shipping_cad": 0.0,
                "total_price_cad": 300.0,
                "shipping_is_estimated": False,
                "condition_raw": "Used",
                "condition_norm": None,
                "is_sold": False,
                "location": "Canada",
                "url": "https://www.ebay.ca/itm/example",
            }
        ]


class EmptyEbaySource:
    name = "ebay"
    enabled = True

    def check_credentials(self):
        return {"message": "OAuth token request succeeded."}

    def search(self, _query, _max_results):
        return []


class DetectedCaseSource:
    name = "ebay"
    enabled = True

    def check_credentials(self):
        return {"message": "OAuth token request succeeded."}

    def search(self, query, _max_results):
        if "ThinkPad X13 Yoga Gen 2" not in query:
            return []
        return [
            {
                "source": "ebay",
                "title": "Lenovo ThinkPad X13 Yoga Gen 2 i7-1185G7 16GB 512GB SSD",
                "item_price_cad": 520.0,
                "shipping_cad": 0.0,
                "total_price_cad": 520.0,
                "shipping_is_estimated": False,
                "condition_raw": "Used",
                "condition_norm": None,
                "is_sold": False,
                "location": "Canada",
                "url": "https://www.ebay.ca/itm/detected",
            }
        ]


def _write_config(text):
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".yaml")
    try:
        handle.write(text)
        return Path(handle.name)
    finally:
        handle.close()


def _refurb_fixture():
    return (Path(__file__).parent / "fixtures" / "refurb_io" / "optiplex_7050_out_of_stock.html").read_text(
        encoding="utf-8"
    )


if __name__ == "__main__":
    unittest.main()
