import contextlib
import io
import json
import unittest
from unittest.mock import MagicMock, patch

from redmine_tasks.cli import main, parser, run
from redmine_tasks.config import Config, TaskError
from redmine_tasks.workflow import edit_description


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.config = Config("https://example.test", "secret-token")
        self.client.pages.return_value = [
            {"id": 12, "name": "Other", "identifier": "other"},
            {"id": 2118, "name": "Dades Obertes - v3 - DKAN", "identifier": "dades-obertes-v3-dkan"},
        ]
        self.project = {
            "id": 2118, "name": "Dades Obertes - v3 - DKAN",
            "trackers": [{"id": 6, "name": "Tasca"}, {"id": 7, "name": "Evolutiu"}],
            "issue_custom_fields": [{"id": 22, "name": "Bloquejat"}],
        }
        self.client.project.return_value = self.project
        self.client.priorities.return_value = [{"id": 2, "name": "Normal", "is_default": True}]
        self.client.current_user.return_value = {"id": 1043, "firstname": "User"}
        self.client.request.return_value = {"issue": {"id": 123}}

    def invoke(self, arguments, answers):
        args = parser().parse_args(arguments)
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", side_effect=answers), patch("redmine_tasks.workflow.edit_description", return_value="h2. Objectiu\nGestionar les cues"), contextlib.redirect_stderr(io.StringIO()):
            return run(args, self.client)

    def test_search_select_compose_and_confirm(self):
        result = self.invoke(["create"], ["dkan", "1", "2", "Gestió de cues", "", "", "", "c"])
        self.assertEqual(result["id"], 123)
        self.client.project.assert_any_call(2118)
        self.client.request.assert_called_once_with("POST", "/issues.json", body={"issue": {
            "subject": "Gestió de cues", "description": "h2. Objectiu\nGestionar les cues",
            "due_date": "", "priority_id": 2, "assigned_to_id": 1043,
            "project_id": 2118, "tracker_id": 7,
        }})

    def test_search_recovers_from_no_matches_and_invalid_number(self):
        result = self.invoke(["create"], ["missing", "dkan", "8", "1", "1", "Cues", "", "", "", "x"])
        self.assertEqual(result, {"result": "cancelled"})
        self.client.request.assert_not_called()

    def test_cancellation_and_eof_never_write(self):
        for answers in ([":cancel"], ["dkan", "1", ":cancel"], []):
            with self.subTest(answers=answers):
                args = parser().parse_args(["create"])
                with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", side_effect=answers or EOFError), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(run(args, self.client), {"result": "cancelled"})
        self.client.request.assert_not_called()

    def test_empty_confirmation_cancels(self):
        result = self.invoke(
            ["create", "--interactive", "--project", "2118", "--title", "Cues", "--description", "Objectiu"],
            ["", "", "", "", ""],
        )
        self.assertEqual(result["result"], "cancelled")
        self.client.request.assert_not_called()

    def test_edit_then_confirm(self):
        result = self.invoke(["create", "--interactive", "--project", "2118", "--title", "Original", "--description", "Original"],
                             ["", "", "", "", "e", "Revisat", "c"])
        self.assertEqual(result["result"], "created")
        self.assertEqual(self.client.request.call_args.kwargs["body"]["issue"]["subject"], "Revisat")

    def test_empty_prefilled_title_is_prompted_and_tracker_id_is_preserved(self):
        self.invoke(["create", "--interactive", "--project", "2118", "--title", "", "--description", "Objectiu", "--tracker", "7"],
                    ["", "Títol completat", "", "", "", "c"])
        fields = self.client.request.call_args.kwargs["body"]["issue"]
        self.assertEqual(fields["subject"], "Títol completat")
        self.assertEqual(fields["tracker_id"], 7)

    def test_custom_fields_and_invalid_dates(self):
        self.invoke(["create", "--interactive", "--project", "2118", "--title", "Cues", "--description", "Objectiu"],
                    ["", "", "invalid-user", "none", "2026-02-30", "2026-12-01", "f", "999=0", "22=0", "", "c"])
        fields = self.client.request.call_args.kwargs["body"]["issue"]
        self.assertEqual(fields["custom_fields"], [{"id": 22, "value": "0"}])
        self.assertIsNone(fields["assigned_to_id"])
        self.assertEqual(fields["due_date"], "2026-12-01")

    def test_dry_run_and_json_keep_prompts_off_stdout(self):
        with patch("redmine_tasks.cli.Config.load", return_value=self.client.config), patch("redmine_tasks.cli.RedmineClient", return_value=self.client), patch("sys.stdin.isatty", return_value=True), patch("builtins.input", side_effect=["dkan", "1", "1", "Cues", "", "", "", "c"]), patch("redmine_tasks.workflow.edit_description", return_value="Objectiu"), contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(main(["create", "--dry-run", "--json"]), 0)
            result = json.loads(stdout.getvalue())
            self.assertTrue(result["dry_run"])
            self.assertIn("Selecciona el projecte", stderr.getvalue())
        self.client.request.assert_not_called()

    def test_review_proposal_must_be_accepted_and_then_confirmed(self):
        proposal = {"title": "Cues revisades", "description": "Objectiu revisat", "warnings": ["Concretar el termini"]}
        with patch("redmine_tasks.workflow.review_draft", return_value=proposal):
            self.invoke(["create", "--project", "2118", "--title", "Original", "--description", "Original", "--review"],
                        ["", "", "", "", "a", "c"])
        self.assertEqual(self.client.request.call_args.kwargs["body"]["issue"]["subject"], "Cues revisades")
        self.client.request.reset_mock()
        with patch("redmine_tasks.workflow.review_draft", return_value=proposal):
            self.invoke(["create", "--project", "2118", "--title", "Original", "--description", "Original", "--review"],
                        ["", "", "", "", "d", "c"])
        self.assertEqual(self.client.request.call_args.kwargs["body"]["issue"]["subject"], "Original")

    def test_review_failure_preserves_original_and_does_not_submit(self):
        with patch("redmine_tasks.workflow.review_draft", side_effect=TaskError("Error de revisió")):
            result = self.invoke(["create", "--project", "2118", "--title", "Original", "--description", "Original", "--review"],
                                 ["", "", "", "", "x"])
        self.assertEqual(result["result"], "cancelled")
        self.client.request.assert_not_called()

    def test_noninteractive_missing_fields_or_review_never_prompt_or_write(self):
        for arguments in (["create"], ["create", "--project", "2118"],
                          ["create", "--project", "2118", "--title", "Example", "--review"]):
            with self.subTest(arguments=arguments), patch("sys.stdin.isatty", return_value=False), patch("builtins.input") as read:
                with self.assertRaisesRegex(TaskError, "terminal"):
                    run(parser().parse_args(arguments), self.client)
                read.assert_not_called()
        self.client.request.assert_not_called()

    def test_noninteractive_review_dry_run_never_writes(self):
        proposal = {"title": "Revisat", "description": "Revisió", "warnings": []}
        with patch("redmine_tasks.review.review_draft", return_value=proposal):
            result = run(parser().parse_args(["create", "--project", "2118", "--title", "Original", "--review", "--dry-run"]), self.client)
        self.assertEqual(result["body"]["issue"]["subject"], "Revisat")
        self.assertEqual(result["review"], proposal)
        self.client.request.assert_not_called()

    def test_standalone_review_needs_no_redmine_credentials(self):
        proposal = {"title": "Cues", "description": "Objectiu", "warnings": []}
        with patch("redmine_tasks.cli.Config.load") as config, patch("redmine_tasks.review.review_draft", return_value=proposal), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["review", "--title", "Cues", "--json"]), 0)
            self.assertEqual(json.loads(output.getvalue()), {"review": proposal})
            config.assert_not_called()

    def test_editor_uses_argument_list_and_keeps_multiline_utf8(self):
        def edit(command, **kwargs):
            from pathlib import Path
            Path(command[-1]).write_text("Descripció\namb dues línies", encoding="utf-8")
            return MagicMock(returncode=0)
        with patch.dict("os.environ", {"VISUAL": 'editor --wait "argument with spaces"'}), patch("redmine_tasks.workflow.subprocess.run", side_effect=edit) as process, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(edit_description("Original"), "Descripció\namb dues línies")
            self.assertEqual(process.call_args.args[0][:3], ["editor", "--wait", "argument with spaces"])
            self.assertNotIn("shell", process.call_args.kwargs)

    def test_editor_failure_and_inline_fallback(self):
        with patch.dict("os.environ", {"VISUAL": "editor"}), patch("redmine_tasks.workflow.subprocess.run", return_value=MagicMock(returncode=1)), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(TaskError, "conserva"):
                edit_description("Original")
        with patch.dict("os.environ", {"VISUAL": "", "EDITOR": ""}), patch("redmine_tasks.workflow.shutil.which", return_value=None), patch("builtins.input", side_effect=["Primera línia", "", "Última línia", "."]), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(edit_description(""), "Primera línia\n\nÚltima línia")


if __name__ == "__main__":
    unittest.main()
