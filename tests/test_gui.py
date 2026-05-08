import os
import unittest
from unittest.mock import patch

from pc_pricer import gui


class GuiImportTests(unittest.TestCase):
    def test_gui_entry_point_imports_without_pyside_installed(self):
        self.assertTrue(callable(gui.main))

    def test_main_window_constructs_when_pyside_is_available(self):
        app = self._qt_app()
        window = gui.MainWindow()

        self.assertEqual(window.windowTitle(), "CFS Price Compare")

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
        self.assertTrue(any("1. Lenovo ThinkPad" in label for label in labels))
        self.assertTrue(any("Open in browser" in label for label in labels))

        window.close()

    def test_report_page_does_not_render_unsafe_listing_links_when_pyside_is_available(self):
        self._qt_app()
        window = gui.MainWindow()
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

        window.close()

    def test_report_page_prints_current_report_when_pyside_is_available(self):
        self._qt_app()
        window = gui.MainWindow()
        window.state.report_text = "Price estimate\nMedian price: $300.00 CAD"
        FakeTextDocument.created.clear()

        with patch("pc_pricer.gui.QPrinter", FakePrinter), patch(
            "pc_pricer.gui.QPrintDialog", FakePrintDialog
        ), patch("pc_pricer.gui.QTextDocument", FakeTextDocument):
            window.report_page.print_report()

        self.assertIn("CFS Price Report", FakeTextDocument.created[-1].html)
        self.assertIn("Median price: $300.00 CAD", FakeTextDocument.created[-1].html)
        self.assertIsInstance(FakeTextDocument.created[-1].printed_to, FakePrinter)

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
    def __init__(self, printer, _parent=None) -> None:
        self.printer = printer

    def exec(self):
        try:
            from PySide6.QtWidgets import QDialog
        except ModuleNotFoundError:
            return 1
        return QDialog.Accepted


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


if __name__ == "__main__":
    unittest.main()
