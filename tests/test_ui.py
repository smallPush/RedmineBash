import io
import os
import unittest
from unittest.mock import patch

from redmine_tasks.cli import display
from redmine_tasks.ui import Style, pad_cell, progress_bar, render_table, visible_len


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


class UiTests(unittest.TestCase):
    def test_style_respects_tty_and_no_color(self):
        with patch.dict(os.environ, {}, clear=True):
            plain = Style(io.StringIO())
            tty = Style(FakeTTY())
            self.assertFalse(plain.enabled)
            self.assertEqual(plain.bold("hola"), "hola")
            self.assertTrue(tty.enabled)
            self.assertEqual(tty.bold("hola"), "\x1b[1mhola\x1b[0m")
            self.assertEqual(visible_len(tty.bold("hola")), 4)

        with patch.dict(os.environ, {"NO_COLOR": "1"}, clear=True):
            disabled = Style(FakeTTY())
            self.assertFalse(disabled.enabled)
            self.assertEqual(disabled.status("En procés"), "En procés")

    def test_progress_bar_clamps_and_renders(self):
        self.assertEqual(progress_bar(0), "[░░░░░░░░░░] 0%")
        self.assertEqual(progress_bar(50), "[█████░░░░░] 50%")
        self.assertEqual(progress_bar(140), "[██████████] 100%")
        self.assertEqual(progress_bar(None), "[░░░░░░░░░░] 0%")

    def test_render_table_aligns_ansi_and_truncates_on_tty(self):
        tty = Style(FakeTTY())
        with patch.dict(os.environ, {"FORCE_COLOR": "1"}, clear=True):
            tty = Style(FakeTTY())
        rows = [
            [tty.bold("#1"), tty.status("Nova"), "Títol molt llarg que s'ha de retallar"],
            [tty.bold("#20"), tty.status("Tancada"), "Curt"],
        ]
        lines = render_table(["ID", "Estat", "Títol"], rows, style=tty, flex_col=2, max_width=32)
        self.assertEqual(len(lines), 4)
        self.assertEqual(visible_len(lines[0]), visible_len(lines[1]))
        self.assertEqual(visible_len(lines[2]), visible_len(lines[3]))
        self.assertIn("…", lines[2])

    def test_pad_cell_accounts_for_ansi(self):
        tty = Style(FakeTTY())
        cell = tty.green("OK")
        self.assertEqual(visible_len(pad_cell(cell, 6)), 6)

    def test_display_list_and_show_plain_output(self):
        out = io.StringIO()
        with patch("sys.stdout", out), patch.dict(os.environ, {}, clear=True):
            display({
                "total": 1,
                "issues": [{
                    "id": 42,
                    "subject": "Revisar còpies",
                    "status": {"id": 1, "name": "Nova"},
                    "priority": {"id": 2, "name": "Normal"},
                    "project": {"id": 10, "name": "Infra"},
                    "due_date": None,
                }],
            }, "list")
            display({
                "issue": {
                    "id": 42,
                    "subject": "Revisar còpies",
                    "project": {"name": "Infra"},
                    "status": {"name": "Nova"},
                    "tracker": {"name": "Tasca"},
                    "priority": {"name": "Normal"},
                    "assigned_to": {"name": "Anna"},
                    "due_date": "2026-12-01",
                    "done_ratio": 40,
                    "description": "Detall",
                    "custom_fields": [],
                    "allowed_statuses": [],
                    "journals": [],
                }
            }, "show")
        text = out.getvalue()
        self.assertIn("1 tasca", text)
        self.assertIn("#42", text)
        self.assertIn("Revisar còpies", text)
        self.assertIn("[████░░░░░░] 40%", text)


if __name__ == "__main__":
    unittest.main()
