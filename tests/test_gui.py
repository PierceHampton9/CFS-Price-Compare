import os
import unittest

from pc_pricer import gui

try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None


class GuiImportTests(unittest.TestCase):
    def test_gui_entry_point_imports_without_pyside_installed(self):
        self.assertTrue(callable(gui.main))

    def test_main_window_constructs_when_pyside_is_available(self):
        if QApplication is None:
            self.skipTest("PySide6 is not installed")

        app = QApplication.instance() or QApplication([])
        window = gui.MainWindow()

        self.assertEqual(window.windowTitle(), "CFS Price Compare")

        window.close()
        app.quit()


if __name__ == "__main__":
    unittest.main()
