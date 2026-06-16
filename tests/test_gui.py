import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pc_pricer import gui


class GuiImportTests(unittest.TestCase):
    def test_gui_entry_point_imports_without_pyside_installed(self):
        self.assertTrue(callable(gui.main))

    def test_display_value_formats_cpu_names(self):
        self.assertEqual(gui._display_value("I5-1135G7", "cpu_short"), "i5-1135G7")
        self.assertEqual(gui._display_value("ryzen 5 5600u", "cpu"), "Ryzen 5 5600u")

    def test_batch_status_treats_low_count_as_complete_when_count_is_usable(self):
        self.assertEqual(
            gui._batch_success_status({"count": 5, "confidence_flags": ["low_comparable_count"]}),
            "Complete",
        )

    def test_batch_status_reviews_very_low_count(self):
        self.assertEqual(
            gui._batch_success_status(
                {
                    "count": 2,
                    "confidence_flags": ["low_comparable_count"],
                }
            ),
            "Needs Review",
        )

    def test_batch_status_treats_wide_range_as_warning_when_count_is_usable(self):
        self.assertEqual(
            gui._batch_success_status({"count": 20, "confidence_flags": ["wide_price_range"]}),
            "Complete",
        )

    def test_batch_issue_text_hides_resolved_low_count_for_complete_rows(self):
        item = {
            "status": "Complete",
            "result": {
                "count": 5,
                "confidence_flags": ["low_comparable_count"],
            },
        }

        self.assertEqual(gui._batch_issue_text(item), "")

    def test_batch_status_still_reviews_zero_count_and_source_disagreement(self):
        self.assertEqual(
            gui._batch_success_status({"count": 0, "confidence_flags": ["no_comparables"]}),
            "Needs Review",
        )
        self.assertEqual(
            gui._batch_success_status({"count": 5, "confidence_flags": ["source_disagreement"]}),
            "Needs Review",
        )

    def test_main_window_constructs_when_pyside_is_available(self):
        app = self._qt_app()
        window = gui.MainWindow()

        self.assertEqual(window.windowTitle(), "CFS Price Compare")
        self.assertIs(window.stack.currentWidget(), window.source_page)

        window.close()

    def test_main_window_prices_current_specs_when_pyside_is_available(self):
        self._qt_app()
        window = gui.MainWindow()
        window.state.device_type = "phone"
        window.state.specs = {"brand": "Apple", "model": "iPhone 13"}
        FakePricingThread.created.clear()

        with patch("pc_pricer.gui.PricingThread", FakePricingThread):
            window.price_current_specs()

        self.assertEqual(FakePricingThread.created[-1].device_type, "phone")
        self.assertEqual(FakePricingThread.created[-1].specs, {"brand": "Apple", "model": "iPhone 13"})
        self.assertEqual(window.state.report_result, {"count": 1})
        self.assertEqual(window.state.report_text, "report text")
        self.assertEqual(window.state.report_error, "")
        self.assertIsNone(window.pricing_thread)

        window.close()

    def test_main_window_records_pricing_failure_when_pyside_is_available(self):
        self._qt_app()
        window = gui.MainWindow()
        window.state.device_type = "phone"
        window.state.specs = {"brand": "Apple", "model": "iPhone 13"}
        window.state.report_result = {"count": 1}
        FakePricingThread.created.clear()
        FakePricingThread.next_error = "credentials failed"

        with patch("pc_pricer.gui.PricingThread", FakePricingThread):
            window.price_current_specs()

        self.assertEqual(window.state.report_result, {})
        self.assertEqual(window.state.report_text, "")
        self.assertEqual(window.state.report_error, "credentials failed")
        self.assertIsNone(window.pricing_thread)

        FakePricingThread.next_error = None
        window.close()

    def test_computer_mode_page_runs_auto_detect_thread_when_pyside_is_available(self):
        self._qt_app()
        window = gui.MainWindow()
        window.state.specs = {"condition": "good"}
        FakeDetectionThread.created.clear()

        with patch("pc_pricer.gui.DetectionThread", FakeDetectionThread):
            window.computer_mode_page.start_detection()

        self.assertEqual(FakeDetectionThread.created[-1].parent, window.computer_mode_page)
        self.assertEqual(window.state.specs["brand"], "Lenovo")
        self.assertEqual(window.state.specs["model"], "ThinkPad X13")
        self.assertEqual(window.state.specs["input_method"], "detected")
        self.assertEqual(window.state.specs["condition"], "good")
        self.assertIsNone(window.computer_mode_page.detect_thread)

        window.close()

    def test_computer_mode_page_shows_auto_detect_failure_when_pyside_is_available(self):
        self._qt_app()
        window = gui.MainWindow()
        FakeDetectionThread.created.clear()
        FakeDetectionThread.next_error = "auto detect failed"

        with patch("pc_pricer.gui.DetectionThread", FakeDetectionThread):
            window.computer_mode_page.start_detection()

        self.assertEqual(window.computer_mode_page.error.text(), "auto detect failed")
        self.assertIsNone(window.computer_mode_page.detect_thread)

        FakeDetectionThread.next_error = None
        window.close()

    def test_report_page_renders_structured_report_when_pyside_is_available(self):
        self._qt_app()
        window = gui.MainWindow()
        window.state.report_text = "Price estimate\nMedian price: $300.00 CAD"
        window.state.report_result = {
            "count": 1,
            "pricing_basis": "asking_adjusted",
            "conservative_low_cad": 280,
            "conservative_high_cad": 300,
            "asking_median_price_cad": 300,
            "iqr_low_cad": 275,
            "iqr_high_cad": 325,
            "query_tier": 2,
            "source_counts": {"ebay": 1},
            "source_statuses": [
                {
                    "source": "amazon_renewed",
                    "status": "error",
                    "searched": True,
                    "query_count": 1,
                    "raw_listing_count": 0,
                    "message": "Playwright browser request failed",
                }
            ],
            "source_diagnostics": [
                {
                    "source": "refurb_io",
                    "title": "Lenovo ThinkPad Refurb",
                    "source_match_verified": False,
                    "source_match_reasons": ["storage_mismatch"],
                    "filter_exclusion_reason": None,
                    "query_text": "Lenovo ThinkPad",
                    "price_cad": 350,
                }
            ],
            "confidence_flags": [],
            "pricing_limitations": ["asking_prices_only"],
            "listing_warnings": [],
            "specs": {"device_type": "computer", "brand": "Lenovo", "cpu_short": "i5-1135G7"},
            "raw_listing_count": 1,
            "deduped_listing_count": 1,
            "target_condition": "good",
            "excluded_count": 0,
            "queries": [{"tier": 2, "text": "Lenovo i5-1135G7 16GB"}],
            "supporting_listings": [
                {
                    "title": "Lenovo ThinkPad",
                    "item_price_cad": 300,
                    "shipping_cad": 0,
                    "total_price_cad": 300,
                    "condition_raw": "Used",
                    "condition_norm": "good",
                    "is_sold": False,
                    "query_tier": 2,
                    "query_text": "Lenovo i5-1135G7 16GB",
                    "url": "https://www.ebay.ca/itm/example",
                }
            ],
        }

        window.report_page.refresh()
        labels = [label.text() for label in window.report_page.findChildren(gui.QLabel)]

        self.assertIn("Conservative Estimate", labels)
        self.assertIn("$280.00 CAD - $300.00 CAD", labels)
        self.assertIn("Supporting Listings", labels)
        self.assertNotIn("Source Status", labels)

        window.close()

    def test_report_page_renders_advanced_report_when_pyside_is_available(self):
        self._qt_app()
        window = gui.MainWindow()
        window.state.report_text = "Price estimate\nMedian price: $300.00 CAD"
        window.state.report_mode = "advanced"
        window.state.report_result = {
            "count": 1,
            "pricing_basis": "asking_adjusted",
            "conservative_low_cad": 280,
            "conservative_high_cad": 300,
            "asking_median_price_cad": 300,
            "iqr_low_cad": 275,
            "iqr_high_cad": 325,
            "query_tier": 2,
            "source_counts": {"ebay": 1},
            "source_statuses": [
                {
                    "source": "amazon_renewed",
                    "status": "error",
                    "searched": True,
                    "query_count": 1,
                    "raw_listing_count": 0,
                    "message": "Playwright browser request failed",
                }
            ],
            "source_diagnostics": [
                {
                    "source": "refurb_io",
                    "title": "Lenovo ThinkPad Refurb",
                    "source_match_verified": False,
                    "source_match_reasons": ["storage_mismatch"],
                    "filter_exclusion_reason": None,
                    "query_text": "Lenovo ThinkPad",
                    "price_cad": 350,
                }
            ],
            "confidence_flags": [],
            "pricing_limitations": ["asking_prices_only"],
            "listing_warnings": [],
            "specs": {"device_type": "computer", "brand": "Lenovo", "cpu_short": "i5-1135G7"},
            "raw_listing_count": 1,
            "deduped_listing_count": 1,
            "target_condition": "good",
            "excluded_count": 0,
            "queries": [{"tier": 2, "text": "Lenovo i5-1135G7 16GB"}],
            "supporting_listings": [
                {
                    "source": "ebay",
                    "title": "Lenovo ThinkPad",
                    "item_price_cad": 300,
                    "shipping_cad": 0,
                    "total_price_cad": 300,
                    "condition_raw": "Used",
                    "condition_norm": "good",
                    "is_sold": False,
                    "query_tier": 2,
                    "query_text": "Lenovo i5-1135G7 16GB",
                    "url": "https://www.ebay.ca/itm/example",
                }
            ],
            "all_comparable_listings": [
                {
                    "comparable_id": "url:https://www.ebay.ca/itm/example",
                    "source": "ebay",
                    "title": "Lenovo ThinkPad",
                    "item_price_cad": 300,
                    "shipping_cad": 0,
                    "total_price_cad": 300,
                    "condition_raw": "Used",
                    "condition_norm": "good",
                    "is_sold": False,
                    "query_tier": 2,
                    "query_text": "Lenovo i5-1135G7 16GB",
                    "url": "https://www.ebay.ca/itm/example",
                }
            ],
        }

        window.report_page.refresh()
        labels = [label.text() for label in window.report_page.findChildren(gui.QLabel)]

        self.assertIn("Source Status", labels)
        self.assertIn("Amazon Renewed", labels)
        self.assertTrue(any("Playwright browser request failed" in label for label in labels))
        self.assertIn("Source Diagnostics", labels)
        self.assertIn("Not Verified", labels)
        self.assertTrue(any("Lenovo ThinkPad Refurb" in label for label in labels))
        self.assertIn("Comparable Review", labels)
        self.assertTrue(any("1. Lenovo ThinkPad" in label for label in labels))
        self.assertTrue(any("Open in browser" in label for label in labels))
        self.assertTrue(window.report_page.print_button.isEnabled())

        window.close()

    def test_source_selection_page_renders_pricing_source_toggles_when_pyside_is_available(self):
        self._qt_app()
        window = gui.MainWindow()

        window.source_page.refresh()
        labels = [label.text() for label in window.source_page.findChildren(gui.QLabel)]
        checkboxes = [checkbox.text() for checkbox in window.source_page.findChildren(gui.QCheckBox)]

        self.assertIn("Pricing Sources", labels)
        self.assertIn("eBay", checkboxes)
        self.assertIn("Refurb.io", checkboxes)
        self.assertIn("Amazon Renewed (experimental)", checkboxes)

        window.close()

    def test_main_window_loads_batch_csv_into_batch_page_when_pyside_is_available(self):
        self._qt_app()
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
            window = gui.MainWindow()

            window.load_batch_csv(str(path))

        self.assertIs(window.stack.currentWidget(), window.batch_page)
        self.assertEqual(len(window.state.batch_items), 2)
        self.assertEqual(window.state.batch_items[0]["status"], "Ready")
        self.assertEqual(window.state.batch_items[1]["status"], "Invalid")
        self.assertEqual(window.batch_page.table.columnCount(), 7)
        self.assertEqual(window.batch_page.table.item(0, 0).text(), "1")
        self.assertEqual(window.batch_page.table.item(0, 1).text(), "Computer")
        self.assertEqual(window.batch_page.table.item(0, 3).text(), "")
        self.assertIn("Form factor is required.", window.batch_page.table.item(1, 5).text())
        self.assertIsNotNone(window.batch_page.table.cellWidget(0, 6))

        window.close()

    def test_batch_page_shows_completed_single_estimate_when_pyside_is_available(self):
        self._qt_app()
        window = gui.MainWindow()
        window.state.batch_items = [
            {
                "item_id": "001",
                "device_type": "computer",
                "values": {"brand": "Lenovo", "model": "ThinkPad"},
                "status": "Complete",
                "errors": [],
                "result": {
                    "count": 5,
                    "conservative_low_cad": 280,
                    "conservative_high_cad": 300,
                    "median_price_cad": 300,
                },
                "report_text": "report",
            },
            {
                "item_id": "002",
                "device_type": "phone",
                "values": {"brand": "Apple", "model": "iPhone"},
                "status": "Complete",
                "errors": [],
                "result": {
                    "count": 8,
                    "pricing_basis": "weighted_sources",
                    "median_price_cad": 497.5,
                    "price_low_cad": 300,
                    "price_high_cad": 600,
                },
                "report_text": "report",
            }
        ]

        window.batch_page.refresh()

        self.assertEqual(window.batch_page.table.item(0, 3).text(), "$290.00 CAD")
        self.assertEqual(window.batch_page.table.item(1, 3).text(), "$497.50 CAD")

        window.close()

    def test_batch_page_disables_mutating_controls_while_running_when_pyside_is_available(self):
        self._qt_app()
        window = gui.MainWindow()
        window.state.batch_items = [
            {
                "item_id": "001",
                "device_type": "computer",
                "values": {"brand": "Lenovo", "model": "ThinkPad"},
                "status": "Complete",
                "errors": [],
                "result": {"count": 5},
                "report_text": "completed report",
            }
        ]
        window.batch_pricing_thread = FakeRunningThread()

        window.batch_page.refresh()

        self.assertFalse(window.batch_page.import_button.isEnabled())
        self.assertFalse(window.batch_page.start_button.isEnabled())
        self.assertFalse(window.batch_page.edit_button.isEnabled())
        self.assertFalse(window.batch_page.back_button.isEnabled())
        self.assertFalse(window.batch_page.print_summary_button.isEnabled())
        self.assertFalse(window.batch_page.print_all_button.isEnabled())
        self.assertFalse(window.batch_page.export_all_button.isEnabled())

        window.batch_pricing_thread = None
        window.close()

    def test_batch_page_global_view_waits_for_all_rows_when_pyside_is_available(self):
        self._qt_app()
        window = gui.MainWindow()
        window.state.batch_items = [
            {
                "item_id": "001",
                "device_type": "computer",
                "values": {"brand": "Lenovo", "model": "ThinkPad"},
                "status": "Complete",
                "errors": [],
                "result": {"count": 1},
                "report_text": "report",
            },
            {
                "item_id": "002",
                "device_type": "computer",
                "values": {"brand": "Dell", "model": "OptiPlex"},
                "status": "Ready",
                "errors": [],
            },
        ]

        window.batch_page.refresh()
        self.assertFalse(window.batch_page.view_button.isEnabled())

        window.state.batch_items[1]["result"] = {"count": 1}
        window.state.batch_items[1]["status"] = "Complete"
        window.batch_page.refresh()
        self.assertTrue(window.batch_page.view_button.isEnabled())

        window.close()

    def test_batch_page_prints_summary_view_when_pyside_is_available(self):
        self._qt_app()
        window = gui.MainWindow()
        window.state.batch_source_path = "devices.csv"
        window.state.batch_items = [
            {
                "item_id": "001",
                "device_type": "computer",
                "values": {"brand": "Lenovo", "model": "ThinkPad"},
                "status": "Complete",
                "errors": [],
                "result": {"count": 5, "median_price_cad": 300},
                "report_text": "full report text that should not be printed in summary",
            },
            {
                "item_id": "002",
                "device_type": "phone",
                "values": {"brand": "Apple", "model": "iPhone"},
                "status": "Failed",
                "errors": [],
                "error": "credentials failed",
            },
        ]
        window.batch_page.refresh()
        FakePrintDialog.next_result = gui.QDialog.Accepted
        FakeTextDocument.created.clear()

        with patch("pc_pricer.gui.QPrinter", FakePrinter), patch(
            "pc_pricer.gui.QPrintDialog", FakePrintDialog
        ), patch("pc_pricer.gui.QTextDocument", FakeTextDocument):
            window.batch_page.print_summary()

        document = FakeTextDocument.created[-1]
        self.assertIsInstance(document.printed_to, FakePrinter)
        self.assertIn("CFS Batch Summary", document.html)
        self.assertIn("devices.csv", document.html)
        self.assertIn("Lenovo ThinkPad", document.html)
        self.assertIn("$300.00 CAD", document.html)
        self.assertIn("credentials failed", document.html)
        self.assertNotIn("full report text", document.html)

        window.close()

    def test_source_selection_skips_credentials_when_ebay_is_disabled_when_pyside_is_available(self):
        self._qt_app()
        with patch("pc_pricer.gui.save_source_settings", side_effect=lambda settings: settings), patch(
            "pc_pricer.gui.credentials_present", return_value=False
        ):
            window = gui.MainWindow()
            window.source_page.source_checks["ebay"].setChecked(False)
            window.source_page.source_checks["refurb_io"].setChecked(True)
            window.source_page.source_checks["amazon_renewed"].setChecked(False)

            window.source_page.next_page()

            self.assertIs(window.stack.currentWidget(), window.device_page)
            self.assertEqual(
                window.state.source_settings,
                {"ebay": False, "refurb_io": True, "amazon_renewed": False},
            )

            window.close()

    def test_source_selection_requires_credentials_only_for_selected_ebay_when_pyside_is_available(self):
        self._qt_app()
        with patch("pc_pricer.gui.save_source_settings", side_effect=lambda settings: settings), patch(
            "pc_pricer.gui.credentials_present", return_value=False
        ):
            window = gui.MainWindow()
            window.source_page.source_checks["ebay"].setChecked(True)
            window.source_page.source_checks["refurb_io"].setChecked(True)
            window.source_page.source_checks["amazon_renewed"].setChecked(False)

            window.source_page.next_page()

            self.assertIs(window.stack.currentWidget(), window.credentials_page)

            window.close()

    def test_source_selection_skips_existing_ebay_credentials_when_pyside_is_available(self):
        self._qt_app()
        with patch("pc_pricer.gui.save_source_settings", side_effect=lambda settings: settings), patch(
            "pc_pricer.gui.credentials_present", return_value=True
        ):
            window = gui.MainWindow()
            window.source_page.source_checks["ebay"].setChecked(True)
            window.source_page.source_checks["refurb_io"].setChecked(True)
            window.source_page.source_checks["amazon_renewed"].setChecked(False)

            window.source_page.next_page()

            self.assertIs(window.stack.currentWidget(), window.device_page)

            window.close()

    def test_source_selection_requires_at_least_one_source_when_pyside_is_available(self):
        self._qt_app()
        window = gui.MainWindow()
        for checkbox in window.source_page.source_checks.values():
            checkbox.setChecked(False)

        with patch("pc_pricer.gui.save_source_settings") as save_settings:
            window.source_page.next_page()

        self.assertEqual(window.source_page.error.text(), "Enable at least one pricing source.")
        save_settings.assert_not_called()

        window.close()

    def test_report_page_reevaluates_after_comparable_toggle_when_pyside_is_available(self):
        self._qt_app()
        window = gui.MainWindow()
        base_result = {
            "count": 2,
            "median_price_cad": 400,
            "iqr_low_cad": 350,
            "iqr_high_cad": 450,
            "source_counts": {"ebay": 2},
            "query_tier": 1,
            "confidence_flags": [],
            "target_condition": "good",
            "excluded_count": 0,
            "excluded_reasons": {},
            "pricing_basis": "asking_adjusted",
            "asking_median_price_cad": 400,
            "conservative_low_cad": 380,
            "conservative_high_cad": 400,
            "asking_only_discount_low": 0,
            "asking_only_discount_high": 0.05,
            "reprice_options": {
                "warn_below_comparables": 1,
                "wide_iqr_ratio": 0.4,
                "support_limit": 5,
                "high_shipping_cad": 75,
                "high_shipping_ratio": 0.25,
                "asking_discount_low": 0,
                "asking_discount_high": 0.05,
            },
            "all_comparable_listings": [
                {
                    "comparable_id": "url:https://www.ebay.ca/itm/1",
                    "source": "ebay",
                    "title": "Listing 1",
                    "item_price_cad": 300,
                    "shipping_cad": 0,
                    "total_price_cad": 300,
                    "condition_raw": "Used",
                    "condition_norm": "good",
                    "url": "https://www.ebay.ca/itm/1",
                },
                {
                    "comparable_id": "url:https://www.ebay.ca/itm/2",
                    "source": "ebay",
                    "title": "Listing 2",
                    "item_price_cad": 500,
                    "shipping_cad": 0,
                    "total_price_cad": 500,
                    "condition_raw": "Used",
                    "condition_norm": "good",
                    "url": "https://www.ebay.ca/itm/2",
                },
            ],
            "supporting_listings": [],
        }
        window.state.base_report_result = base_result
        window.state.report_result = base_result
        window.state.report_mode = "advanced"
        window.state.pending_excluded_comparable_ids = {"url:https://www.ebay.ca/itm/2"}

        window.report_page._reevaluate_report()

        self.assertEqual(window.state.report_result["count"], 1)
        self.assertEqual(window.state.report_result["median_price_cad"], 300)
        self.assertEqual(window.state.report_result["excluded_reasons"]["user_removed_comparable"], 1)

        window.close()

    def test_report_page_does_not_render_unsafe_listing_links_when_pyside_is_available(self):
        self._qt_app()
        window = gui.MainWindow()
        window.state.report_text = "Price estimate\nMedian price: $300.00 CAD"
        window.state.report_result = {
            "count": 1,
            "pricing_basis": "asking_adjusted",
            "conservative_low_cad": 280,
            "conservative_high_cad": 300,
            "asking_median_price_cad": 300,
            "iqr_low_cad": 275,
            "iqr_high_cad": 325,
            "query_tier": 2,
            "source_counts": {"ebay": 1},
            "confidence_flags": [],
            "pricing_limitations": [],
            "listing_warnings": [],
            "specs": {"device_type": "computer", "brand": "Lenovo"},
            "raw_listing_count": 1,
            "deduped_listing_count": 1,
            "target_condition": "good",
            "excluded_count": 0,
            "queries": [],
            "supporting_listings": [
                {
                    "title": "Lenovo ThinkPad",
                    "item_price_cad": 300,
                    "shipping_cad": 0,
                    "total_price_cad": 300,
                    "condition_raw": "Used",
                    "condition_norm": "good",
                    "is_sold": False,
                    "query_tier": 2,
                    "url": "javascript:alert(1)",
                }
            ],
        }

        window.report_page.refresh()
        labels = [label.text() for label in window.report_page.findChildren(gui.QLabel)]

        self.assertIn("1. Lenovo ThinkPad", labels)
        self.assertFalse(any("javascript:" in label for label in labels))
        self.assertFalse(any("Open in browser" in label for label in labels))
        self.assertTrue(window.report_page.print_button.isEnabled())

        window.close()

    def test_report_page_disables_print_for_empty_and_error_states_when_pyside_is_available(self):
        self._qt_app()
        window = gui.MainWindow()

        window.report_page.refresh()
        self.assertFalse(window.report_page.print_button.isEnabled())

        window.state.report_error = "credentials failed"
        window.report_page.refresh()
        self.assertFalse(window.report_page.print_button.isEnabled())

        window.close()

    def test_report_page_prints_current_report_when_pyside_is_available(self):
        self._qt_app()
        window = gui.MainWindow()
        window.state.report_text = "Price estimate\nMedian price: $300.00 CAD"
        window.state.report_result = {"count": 1, "median_price_cad": 300, "source_counts": {"ebay": 1}}
        FakeTextDocument.created.clear()
        FakePrintDialog.next_result = gui.QDialog.Accepted

        with patch("pc_pricer.gui.QPrinter", FakePrinter), patch(
            "pc_pricer.gui.QPrintDialog", FakePrintDialog
        ), patch("pc_pricer.gui.QTextDocument", FakeTextDocument):
            window.report_page.print_report()

        self.assertIn("CFS Price Report", FakeTextDocument.created[-1].html)
        self.assertIn("Median price:      $300.00 CAD", FakeTextDocument.created[-1].html)
        self.assertIsInstance(FakeTextDocument.created[-1].printed_to, FakePrinter)

        window.close()

    def test_report_page_does_not_print_without_successful_report_when_pyside_is_available(self):
        self._qt_app()
        window = gui.MainWindow()
        FakeTextDocument.created.clear()
        FakePrintDialog.next_result = gui.QDialog.Accepted

        with patch("pc_pricer.gui.QPrinter", FakePrinter), patch(
            "pc_pricer.gui.QPrintDialog", FakePrintDialog
        ), patch("pc_pricer.gui.QTextDocument", FakeTextDocument):
            window.report_page.print_report()

        self.assertEqual(FakeTextDocument.created, [])

        window.state.report_text = "Pricing failed"
        window.state.report_result = {"count": 0}
        window.state.report_error = "credentials failed"

        with patch("pc_pricer.gui.QPrinter", FakePrinter), patch(
            "pc_pricer.gui.QPrintDialog", FakePrintDialog
        ), patch("pc_pricer.gui.QTextDocument", FakeTextDocument):
            window.report_page.print_report()

        self.assertEqual(FakeTextDocument.created, [])

        window.close()

    def test_report_page_does_not_print_when_dialog_is_rejected_when_pyside_is_available(self):
        self._qt_app()
        window = gui.MainWindow()
        window.state.report_text = "Price estimate\nMedian price: $300.00 CAD"
        window.state.report_result = {"count": 1}
        FakeTextDocument.created.clear()
        FakePrintDialog.next_result = gui.QDialog.Rejected

        with patch("pc_pricer.gui.QPrinter", FakePrinter), patch(
            "pc_pricer.gui.QPrintDialog", FakePrintDialog
        ), patch("pc_pricer.gui.QTextDocument", FakeTextDocument):
            window.report_page.print_report()

        self.assertEqual(FakeTextDocument.created, [])

        FakePrintDialog.next_result = gui.QDialog.Accepted
        window.close()

    def _qt_app(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
        except ModuleNotFoundError:
            self.skipTest("PySide6 is not installed")

        return QApplication.instance() or QApplication([])


class FakeSignal:
    def __init__(self) -> None:
        self.callbacks = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)

    def emit(self, *args) -> None:
        for callback in self.callbacks:
            callback(*args)


class FakePricingThread:
    created = []
    next_error = None

    def __init__(self, device_type, specs, _parent=None) -> None:
        self.device_type = device_type
        self.specs = dict(specs)
        self.completed = FakeSignal()
        self.failed = FakeSignal()
        self.finished = FakeSignal()
        FakePricingThread.created.append(self)

    def start(self) -> None:
        if self.next_error:
            self.failed.emit(self.next_error)
        else:
            self.completed.emit({"count": 1}, "report text")
        self.finished.emit()

    def isRunning(self) -> bool:
        return False

    def deleteLater(self) -> None:
        pass


class FakeDetectionThread:
    created = []
    next_error = None

    def __init__(self, parent=None) -> None:
        self.parent = parent
        self.completed = FakeSignal()
        self.failed = FakeSignal()
        self.finished = FakeSignal()
        FakeDetectionThread.created.append(self)

    def start(self) -> None:
        if self.next_error:
            self.failed.emit(self.next_error)
        else:
            self.completed.emit(
                {
                    "brand": "Lenovo",
                    "search_model": "ThinkPad X13",
                    "form_factor": "laptop",
                    "cpu_short": "i5-1135G7",
                    "ram_gb": 16,
                    "storage": [{"size_gb": 512, "type": "SSD"}],
                }
            )
        self.finished.emit()

    def deleteLater(self) -> None:
        pass


class FakePrinter:
    pass


class FakePrintDialog:
    next_result = None

    def __init__(self, printer, _parent=None) -> None:
        self.printer = printer

    def exec(self):
        return self.next_result


class FakeTextDocument:
    created = []

    def __init__(self) -> None:
        self.html = ""
        self.printed_to = None
        FakeTextDocument.created.append(self)

    def setHtml(self, html):
        self.html = html

    def print_(self, printer):
        self.printed_to = printer


class FakeRunningThread:
    def isRunning(self) -> bool:
        return True


if __name__ == "__main__":
    unittest.main()
