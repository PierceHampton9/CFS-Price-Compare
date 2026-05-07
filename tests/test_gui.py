import unittest

from pc_pricer import gui


class GuiImportTests(unittest.TestCase):
    def test_gui_entry_point_imports_without_pyside_installed(self):
        self.assertTrue(callable(gui.main))


if __name__ == "__main__":
    unittest.main()
