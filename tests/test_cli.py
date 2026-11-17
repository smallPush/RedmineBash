import contextlib
import io
import json
import unittest
from unittest.mock import MagicMock, patch

from redmine_tasks.cli import display, main, parser, resolve, run
from redmine_tasks.config import Config, TaskError


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.config = Config("https://example.test", "secret-token")
        self.client.current_user.return_value = {"id": 1043, "firstname": "User"}
        self.client.project.return_value = {
            "id": 1443, "trackers": [{"id": 6, "name": "Tasca"}],
            "issue_custom_fields": [{"id": 15, "name": "Entorn"}],
        }
        self.client.priorities.return_value = [{"id": 2, "name": "Normal"}]
        self.client.statuses.return_value = [{"id": 2, "name": "En procés"}]
        self.client.issue.return_value = {
            "id": 107162, "project": {"id": 1443},
            "allowed_statuses": [{"id": 2, "name": "En procés"}],
        }
        self.client.pages.return_value = []
        self.client.request.return_value = {}

    def invoke(self, *argv):
        return run(parser().parse_args(argv), self.client)

    def test_default_list_and_filters(self):
        self.invoke("list")
        self.client.pages.assert_called_once_with(
            "/issues.json", "issues", status_id="open", assigned_to_id="me", sort="priority:desc,updated_on:desc"
        )
        self.client.pages.reset_mock()
        self.invoke("list", "--status", "en proces", "--project", "1443", "--assignee", "none", "--priority", "Normal")
        params = self.client.pages.call_args.kwargs
        self.assertEqual(params["status_id"], 2)
        self.assertEqual(params["assigned_to_id"], "!*")
        self.assertEqual(params["project_id"], 1443)
        self.assertEqual(params["priority_id"], 2)

    def test_all_assignees_includes_unassigned(self):
        self.invoke("list", "--assignee", "all", "--status", "all")
        params = self.client.pages.call_args.kwargs
        self.assertIsNone(params["assigned_to_id"])
        self.assertEqual(params["status_id"], "*")

    def test_resolve_names_ids_and_ambiguity(self):
        options = [{"id": 2, "name": "En procés"}]
        self.assertEqual(resolve("en proces", options, "Estat"), 2)
        self.assertEqual(resolve("2", options, "Estat"), 2)
        with self.assertRaisesRegex(TaskError, "Opcions: 2=En procés"):
            resolve("unknown", options, "Estat")
        with self.assertRaises(TaskError):
            resolve("En procés", options * 2, "Estat")

    def test_create_payload_defaults(self):
        self.client.request.return_value = {"issue": {"id": 123}}
        result = self.invoke("create", "--project", "1443", "--title", "Example")
        self.assertEqual(result["url"], "https://example.test/issues/123")
        self.client.request.assert_called_once_with("POST", "/issues.json", body={"issue": {
            "subject": "Example", "assigned_to_id": 1043, "project_id": 1443, "tracker_id": 6,
        }})

    def test_edit_sends_only_requested_fields_and_clears_values(self):
        self.invoke("edit", "107162", "--description", "", "--assignee", "none", "--due-date", "", "--progress", "0")
        self.client.request.assert_called_once_with("PUT", "/issues/107162.json", body={"issue": {
            "description": "", "assigned_to_id": None, "due_date": "", "done_ratio": 0,
        }})
        self.client.project.assert_not_called()

    def test_custom_field_payload_and_validation(self):
        result = self.invoke("edit", "107162", "--field", "15=INT", "--dry-run")
        self.assertEqual(result["body"]["issue"]["custom_fields"], [{"id": 15, "value": "INT"}])
        with self.assertRaises(TaskError):
            self.invoke("edit", "107162", "--field", "999=INT")
        with self.assertRaises(TaskError):
            self.invoke("edit", "107162", "--field", "15=INT", "--field", "15=PRO")

    def test_comment_payload(self):
        self.invoke("comment", "107162", "Seguiment")
        self.client.request.assert_called_once_with("PUT", "/issues/107162.json", body={"issue": {"notes": "Seguiment"}})

    def test_only_allowed_transitions(self):
        self.invoke("status", "107162", "En procés")
        self.client.request.assert_called_once_with("PUT", "/issues/107162.json", body={"issue": {"status_id": 2}})
        self.client.request.reset_mock()
        with self.assertRaises(TaskError):
            self.invoke("status", "107162", "Tancat")
        self.client.request.assert_not_called()
        self.client.issue.return_value.pop("allowed_statuses")
        with self.assertRaises(TaskError):
            self.invoke("status", "107162", "En procés")

    def test_dry_run_never_writes_or_exposes_token(self):
        commands = [
            ("create", "--project", "1443", "--title", "Example"),
            ("edit", "107162", "--title", "Example"),
            ("comment", "107162", "Example"),
            ("status", "107162", "En procés"),
        ]
        for command in commands:
            with self.subTest(command=command):
                result = self.invoke(*command, "--dry-run")
                self.assertTrue(result["dry_run"])
                self.assertNotIn("secret-token", json.dumps(result))
        self.client.request.assert_not_called()

    def test_empty_edits_titles_and_comments_fail(self):
        for command in [("edit", "107162"), ("edit", "107162", "--title", "  "), ("comment", "107162", " ")]:
            with self.subTest(command=command), self.assertRaises(TaskError):
                self.invoke(*command)
        self.client.request.assert_not_called()

    def test_invalid_cli_arguments(self):
        for command in [("show", "0"), ("edit", "1", "--progress", "101"),
                        ("edit", "1", "--due-date", "2026-02-30"),
                        ("edit", "1", "--field", "bad")]:
            with self.subTest(command=command), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                parser().parse_args(command)
            self.assertEqual(caught.exception.code, 2)

    def test_no_command_defaults_to_list_with_global_options(self):
        for argv in ([], ["--json"], ["--json", "list"], ["list", "--json"]):
            with self.subTest(argv=argv), patch("redmine_tasks.cli.Config.load", return_value=self.client.config), patch("redmine_tasks.cli.RedmineClient", return_value=self.client), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(argv), 0)
                if "--json" in argv:
                    self.assertEqual(json.loads(output.getvalue()), {"total": 0, "issues": []})

    def test_error_exit_and_stderr(self):
        self.client.pages.side_effect = TaskError("Failure secret-token")
        with patch("redmine_tasks.cli.Config.load", return_value=self.client.config), patch("redmine_tasks.cli.RedmineClient", return_value=self.client), contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(main(["list"]), 1)
            self.assertNotIn("secret-token", error.getvalue())

    def test_help_is_catalan_for_root_and_subcommands(self):
        for command in ([], ["list"], ["show"], ["projects"], ["catalogs"],
                        ["check"], ["create"], ["edit"], ["comment"], ["status"], ["review"]):
            with self.subTest(command=command), contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaises(SystemExit) as caught:
                    parser().parse_args([*command, "--help"])
                self.assertEqual(caught.exception.code, 0)
                text = output.getvalue()
                self.assertIn("Mostra aquesta ajuda i surt", text)
                self.assertIn("opcions:", text)
                self.assertEqual(text.count("ús: "), 1)
                self.assertNotIn("usage:", text)
                self.assertNotIn("show this help message", text)

    def test_parser_diagnostics_are_catalan(self):
        cases = [(["show"], "cal indicar els arguments següents"),
                 (["unknown"], "opció no vàlida"),
                 (["edit", "1", "--title"], "cal indicar un valor"),
                 (["list", "--unknown"], "arguments no reconeguts")]
        for argv, expected in cases:
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()) as output:
                with self.assertRaises(SystemExit) as caught:
                    parser().parse_args(argv)
                self.assertEqual(caught.exception.code, 2)
                self.assertIn(expected, output.getvalue())

    def test_legacy_commands_and_options_resolve_to_english_interface(self):
        pairs = [("listar", "list"), ("ver", "show"), ("proyectos", "projects"),
                 ("catalogos", "catalogs"), ("comprobar", "check"),
                 ("crear", "create"), ("editar", "edit"),
                 ("comentar", "comment"), ("estado", "status")]
        suffixes = {"show": ["107162"], "create": ["--proyecto", "1443", "--titulo", "Example"],
                    "edit": ["107162"], "comment": ["107162", "Seguiment"],
                    "status": ["107162", "En procés"]}
        for old, new in pairs:
            with self.subTest(command=old):
                args = parser().parse_args([old, *suffixes.get(new, [])])
                self.assertEqual(args.command, new)
        self.invoke("listar", "--estado", "abiertos", "--asignado", "yo", "--proyecto", "1443")
        self.assertEqual(self.client.pages.call_args.kwargs["assigned_to_id"], "me")
        self.assertEqual(self.client.pages.call_args.kwargs["status_id"], "open")
        self.invoke("editar", "107162", "--asignado", "sin", "--dry-run")
        self.client.request.assert_not_called()

    def test_json_contract_uses_english_keys_and_result_values(self):
        user = self.invoke("check")
        self.assertIn("user", user)
        self.assertNotIn("usuario", user)
        catalogs = self.invoke("catalogs", "--project", "1443")
        self.assertEqual(set(catalogs), {"statuses", "priorities", "trackers", "fields"})
        result = self.invoke("comment", "107162", "Seguiment")
        self.assertEqual(result["result"], "updated")
        with contextlib.redirect_stdout(io.StringIO()) as output:
            display(result, "comment")
            self.assertIn("Tasca actualitzada", output.getvalue())
            self.assertNotIn("updated", output.getvalue())


if __name__ == "__main__":
    unittest.main()
