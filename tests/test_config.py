import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from redmine_tasks.config import Config, TaskError, read_env


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / ".env"

    def test_env_file_is_data_not_shell(self):
        self.path.write_text(
            '# comment\nexport TOKEN_REDMINE="$(touch /tmp/do-not-execute)" # comment\n'
            'REDMINE_URL=https://example.test/redmine/ # server\nIGNORE=value\n',
            encoding="utf-8",
        )
        values = read_env(self.path)
        self.assertEqual(values["TOKEN_REDMINE"], "$(touch /tmp/do-not-execute)")
        self.assertEqual(values["REDMINE_URL"], "https://example.test/redmine/")
        self.assertNotIn("IGNORE", values)

    def test_environment_takes_precedence(self):
        self.path.write_text("TOKEN_REDMINE=file-secret\nREDMINE_URL=https://file.test\n")
        with patch.dict(os.environ, {"TOKEN_REDMINE": "env-secret", "REDMINE_URL": "https://env.test/"}, clear=True):
            config = Config.load(self.path)
        self.assertEqual(config.token, "env-secret")
        self.assertEqual(config.url, "https://env.test")
        self.assertNotIn("env-secret", repr(config))

    def test_file_fallback(self):
        self.path.write_text("TOKEN_REDMINE='file-secret'\nREDMINE_URL='https://file.test/'\n")
        with patch.dict(os.environ, {}, clear=True):
            config = Config.load(self.path)
        self.assertEqual(config.token, "file-secret")
        self.assertEqual(config.url, "https://file.test")

    def test_missing_or_empty_token_or_url(self):
        for content in (None, "TOKEN_REDMINE=\n", "TOKEN_REDMINE=secret\n"):
            if content is not None:
                self.path.write_text(content)
            with patch.dict(os.environ, {}, clear=True), self.assertRaises(TaskError):
                Config.load(self.path)

    def test_invalid_configuration(self):
        for url in ("http://example.test", "https://user:pass@example.test", "https://example.test?key=secret", "https://example.test/#fragment", "https://example.test:invalid"):
            with self.subTest(url=url), patch.dict(os.environ, {"TOKEN_REDMINE": "secret", "REDMINE_URL": url}, clear=True):
                with self.assertRaises(TaskError):
                    Config.load(self.path)
        self.path.write_text('TOKEN_REDMINE="unterminated\n')
        with self.assertRaises(TaskError):
            read_env(self.path)


if __name__ == "__main__":
    unittest.main()
