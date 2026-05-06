from pathlib import Path
import unittest

from pc_pricer.setup_credentials import run_setup, write_credentials_env


ENV_PATH = Path("tests/setup_credentials.env")


class SetupCredentialsTests(unittest.TestCase):
    def tearDown(self):
        ENV_PATH.unlink(missing_ok=True)

    def test_run_setup_prompts_and_writes_env_file(self):
        prompts = []

        def fake_input(prompt):
            prompts.append(prompt)
            return "client-id"

        def fake_secret(prompt):
            prompts.append(prompt)
            return "client-secret"

        written_path = run_setup(ENV_PATH, input_func=fake_input, secret_input_func=fake_secret)

        self.assertEqual(written_path, ENV_PATH)
        self.assertEqual(prompts, ["eBay Client ID / App ID: ", "eBay Client Secret / Cert ID: "])
        text = ENV_PATH.read_text(encoding="utf-8")
        self.assertIn('EBAY_CLIENT_ID="client-id"', text)
        self.assertIn('EBAY_CLIENT_SECRET="client-secret"', text)

    def test_run_setup_rejects_blank_values(self):
        with self.assertRaises(RuntimeError):
            run_setup(ENV_PATH, input_func=lambda _prompt: "", secret_input_func=lambda _prompt: "secret")

    def test_write_credentials_preserves_other_env_values(self):
        ENV_PATH.write_text("OTHER_VALUE=keep-me\nEBAY_CLIENT_ID=old\n", encoding="utf-8")

        write_credentials_env(ENV_PATH, "new-id", "new-secret")

        text = ENV_PATH.read_text(encoding="utf-8")
        self.assertIn('EBAY_CLIENT_ID="new-id"', text)
        self.assertIn('EBAY_CLIENT_SECRET="new-secret"', text)
        self.assertIn('OTHER_VALUE="keep-me"', text)


if __name__ == "__main__":
    unittest.main()
