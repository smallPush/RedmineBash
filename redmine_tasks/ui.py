"""Terminal visual styling, aligned tables, and progress bars (no dependencies)."""

import os
import re
import shutil
import sys


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def supports_color(stream=None):
    """Return whether ANSI colors should be emitted for the given stream."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    target = stream or sys.stdout
    return hasattr(target, "isatty") and target.isatty()


def visible_len(text):
    """Return display length of text excluding ANSI escape sequences."""
    return len(_ANSI_RE.sub("", text))


def truncate(text, max_width):
    """Truncate plain text to max_width using an ellipsis if needed."""
    if max_width <= 0:
        return ""
    if len(text) <= max_width:
        return text
    if max_width == 1:
        return "…"
    return text[: max_width - 1] + "…"


class Style:
    """Lightweight ANSI styler that degrades cleanly to plain text."""

    def __init__(self, stream=None):
        self.stream = stream or sys.stdout
        self.enabled = supports_color(self.stream)

    def _wrap(self, code, text):
        text = str(text)
        if not self.enabled or not text:
            return text
        return f"\x1b[{code}m{text}\x1b[0m"

    def bold(self, text):
        return self._wrap("1", text)

    def dim(self, text):
        return self._wrap("2", text)

    def red(self, text):
        return self._wrap("31", text)

    def green(self, text):
        return self._wrap("32", text)

    def yellow(self, text):
        return self._wrap("33", text)

    def blue(self, text):
        return self._wrap("34", text)

    def magenta(self, text):
        return self._wrap("35", text)

    def cyan(self, text):
        return self._wrap("36", text)

    def heading(self, text):
        return self._wrap("1;36", text)

    def ok(self, text):
        return self.green(f"✓ {text}")

    def warn(self, text):
        return self.yellow(f"! {text}")

    def err(self, text):
        return self.red(f"✗ {text}")

    def info(self, text):
        return self.cyan(f"• {text}")

    def rule(self, width=None):
        cols = width or min(terminal_width(), 88)
        return self.dim("─" * cols)

    def status(self, name):
        lower = name.casefold()
        if any(word in lower for word in ("tancad", "resol", "finalitz", "closed", "done")):
            return self.green(name)
        if any(word in lower for word in ("procés", "curs", "progress", "desenvolup", "revis")):
            return self.yellow(name)
        if any(word in lower for word in ("nov", "obert", "new", "open")):
            return self.cyan(name)
        if any(word in lower for word in ("rebutj", "bloquej", "cancel", "reject", "block")):
            return self.red(name)
        return name

    def priority(self, name):
        lower = name.casefold()
        if any(word in lower for word in ("immediat", "urgent", "crític", "critic")):
            return self._wrap("1;31", name)
        if any(word in lower for word in ("alt", "high")):
            return self.red(name)
        if any(word in lower for word in ("baix", "low")):
            return self.dim(name)
        return name


def terminal_width(default=100):
    """Return terminal column width with a safe fallback."""
    return shutil.get_terminal_size((default, 24)).columns


def progress_bar(percent, width=10, style=None):
    """Render a compact progress bar such as [████░░░░░░] 40%."""
    try:
        value = max(0, min(100, int(percent or 0)))
    except (TypeError, ValueError):
        value = 0
    filled = round(value / 100 * width)
    bar = "█" * filled + "░" * (width - filled)
    if style and style.enabled:
        color = style.green if value == 100 else style.cyan if value > 0 else style.dim
        return f"[{color(bar)}] {value}%"
    return f"[{bar}] {value}%"


def pad_cell(text, width):
    """Right-pad text to width accounting for ANSI escape codes."""
    gap = width - visible_len(text)
    return text + (" " * gap if gap > 0 else "")


def render_table(headers, rows, style=None, flex_col=None, max_width=None):
    """Render an aligned borderless table fitted to terminal width.

    Each row may contain plain strings or ANSI-styled strings. If flex_col is
    set, that column's plain values are truncated to fit within max_width.
    """
    if not rows:
        return []
    style = style or Style()
    cols = len(headers)
    widths = [visible_len(h) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], visible_len(cell))

    limit = max_width or terminal_width()
    sep = "  "
    total = sum(widths) + len(sep) * (cols - 1)
    if flex_col is not None and total > limit and style.stream.isatty():
        other = total - widths[flex_col]
        available = max(16, limit - other)
        widths[flex_col] = min(widths[flex_col], available)

    lines = [
        sep.join(style.bold(pad_cell(h, widths[i])) for i, h in enumerate(headers)),
        style.dim(sep.join("─" * widths[i] for i in range(cols))),
    ]
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            if i == flex_col and visible_len(cell) > widths[i] and "\x1b[" not in cell:
                cell = truncate(cell, widths[i])
            cells.append(pad_cell(cell, widths[i]))
        lines.append(sep.join(cells))
    return lines
