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
        self.assertEqual(window.state.report_text, "report text")
        self.assertEqual(window.state.report_error, "")
        self.assertIsNone(window.pricing_thread)

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

    def __init__(self, device_type, specs, _parent=None) -> None:
        self.device_type = device_type
        self.specs = dict(specs)
        self.completed = FakeSignal()
        self.failed = FakeSignal()
        self.finished = FakeSignal()
        FakePricingThread.created.append(self)

    def start(self) -> None:
        self.completed.emit("report text")
        self.finished.emit()

    def deleteLater(self) -> None:
        pass


if __name__ == "__main__":
    unittest.main()
