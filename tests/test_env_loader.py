import os
import unittest
from pathlib import Path
from unittest.mock import patch

from pc_pricer.env_loader import default_env_path, load_env_file


class EnvLoaderTests(unittest.TestCase):
    def test_loads_key_value_pairs(self):
        env_path = _test_env_path()
        try:
            env_path.write_text(
                "\n".join(
                    [
                        "EBAY_CLIENT_ID=client-id",
                        "EBAY_CLIENT_SECRET='client-secret'",
                        "# ignored comment",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                load_env_file(env_path)

                self.assertEqual(os.environ["EBAY_CLIENT_ID"], "client-id")
                self.assertEqual(os.environ["EBAY_CLIENT_SECRET"], "client-secret")
        finally:
            env_path.unlink(missing_ok=True)

    def test_does_not_override_existing_shell_values(self):
        env_path = _test_env_path()
        try:
            env_path.write_text("EBAY_CLIENT_ID=file-value", encoding="utf-8")

            with patch.dict(os.environ, {"EBAY_CLIENT_ID": "shell-value"}, clear=True):
                load_env_file(env_path)

                self.assertEqual(os.environ["EBAY_CLIENT_ID"], "shell-value")
        finally:
            env_path.unlink(missing_ok=True)

    def test_can_override_existing_shell_values_for_gui_runs(self):
        env_path = _test_env_path()
        try:
            env_path.write_text("EBAY_CLIENT_ID=file-value", encoding="utf-8")

            with patch.dict(os.environ, {"EBAY_CLIENT_ID": "shell-value"}, clear=True):
                load_env_file(env_path, override=True)

                self.assertEqual(os.environ["EBAY_CLIENT_ID"], "file-value")
        finally:
            env_path.unlink(missing_ok=True)

    def test_missing_file_is_ok(self):
        env_path = _test_env_path()
        env_path.unlink(missing_ok=True)
        with patch.dict(os.environ, {}, clear=True):
            load_env_file(env_path)

            self.assertEqual(dict(os.environ), {})

    def test_default_env_path_uses_working_directory_for_source_runs(self):
        with patch("pc_pricer.env_loader.sys.frozen", False, create=True):
            self.assertEqual(default_env_path(), Path.cwd() / ".env")

    def test_default_env_path_uses_exe_directory_for_packaged_runs(self):
        exe_path = Path("C:/release/pc_pricer.exe")
        with patch("pc_pricer.env_loader.sys.frozen", True, create=True), patch(
            "pc_pricer.env_loader.sys.executable", str(exe_path)
        ):
            self.assertEqual(default_env_path(), exe_path.parent / ".env")


def _test_env_path() -> Path:
    return Path("tests") / "env_loader_test.env"


if __name__ == "__main__":
    unittest.main()
