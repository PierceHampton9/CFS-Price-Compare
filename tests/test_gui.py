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

        with patch("pc_pricer.gui.price_gui_values", return_value=({}, "report text")) as price:
            window.price_current_specs()

        price.assert_called_once_with("phone", {"brand": "Apple", "model": "iPhone 13"})
        self.assertEqual(window.state.report_text, "report text")
        self.assertEqual(window.state.report_error, "")

        window.close()

    def _qt_app(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
        except ModuleNotFoundError:
            self.skipTest("PySide6 is not installed")

        return QApplication.instance() or QApplication([])


if __name__ == "__main__":
    unittest.main()
