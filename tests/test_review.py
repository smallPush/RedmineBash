import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from redmine_tasks.config import TaskError
from redmine_tasks.review import review_draft


class ReviewTests(unittest.TestCase):
    def execute(self, proposal):
        def complete(command, **kwargs):
            path = Path(command[command.index("--output-last-message") + 1])
            path.write_text(json.dumps(proposal), encoding="utf-8")
            return MagicMock(returncode=0)
        return complete

    def test_structured_review_and_credential_isolation(self):
        proposal = {"title": "Gestió de cues", "description": "h2. Objectiu\nGestionar les cues", "warnings": ["Concretar l’abast"]}
        project = {"id": 2118, "name": "DKAN", "identifier": "dkan", "secret": "not-context"}
        with patch("redmine_tasks.review.shutil.which", return_value="/bin/codex"), patch("redmine_tasks.review.subprocess.run", side_effect=self.execute(proposal)) as process, patch.dict(os.environ, {"TOKEN_REDMINE": "private-token", "UNRELATED_SECRET": "private-secret"}):
            self.assertEqual(review_draft("Original", "Original description", project), proposal)
            args, kwargs = process.call_args
            self.assertNotIn("TOKEN_REDMINE", kwargs["env"])
            self.assertNotIn("UNRELATED_SECRET", kwargs["env"])
            self.assertNotIn("private-token", kwargs["input"])
            self.assertNotIn("not-context", kwargs["input"])
            self.assertIn("Catalan", kwargs["input"])
            self.assertIn("read-only", args[0])
            self.assertIn("--ignore-user-config", args[0])
            self.assertNotIn("shell", kwargs)
            self.assertLessEqual(kwargs["timeout"], 180)
            self.assertFalse(Path(kwargs["cwd"]).exists())

    def test_missing_codex_and_empty_title(self):
        with patch("redmine_tasks.review.shutil.which", return_value=None), self.assertRaisesRegex(TaskError, "No es troba Codex"):
            review_draft("Title", "")
        with self.assertRaisesRegex(TaskError, "buit"):
            review_draft("  ", "")

    def test_invalid_response_shapes(self):
        proposals = [[], {}, {"title": "", "description": "Text", "warnings": []},
                     {"title": "Text", "description": "Text", "warnings": "invalid"},
                     {"title": "Text", "description": "Text", "warnings": [123]},
                     {"title": "Text", "description": "Text", "warnings": [], "extra": True}]
        for proposal in proposals:
            with self.subTest(proposal=proposal), patch("redmine_tasks.review.shutil.which", return_value="codex"), patch("redmine_tasks.review.subprocess.run", side_effect=self.execute(proposal)), self.assertRaisesRegex(TaskError, "format no vàlid"):
                review_draft("Title", "Text")

    def test_failed_and_timed_out_review(self):
        with patch("redmine_tasks.review.shutil.which", return_value="codex"):
            with patch("redmine_tasks.review.subprocess.run", return_value=MagicMock(returncode=1)), self.assertRaisesRegex(TaskError, "ha fallat"):
                review_draft("Title", "Text")
            with patch("redmine_tasks.review.subprocess.run", side_effect=subprocess.TimeoutExpired("codex", 180)), self.assertRaisesRegex(TaskError, "temps límit"):
                review_draft("Title", "Text")

    def test_missing_output_file(self):
        with patch("redmine_tasks.review.shutil.which", return_value="codex"), patch("redmine_tasks.review.subprocess.run", return_value=MagicMock(returncode=0)), self.assertRaisesRegex(TaskError, "revisió vàlida"):
            review_draft("Title", "Text")


if __name__ == "__main__":
    unittest.main()
