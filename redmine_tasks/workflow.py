"""Interactive issue composition; only the caller submits confirmed drafts."""

import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

from .cli import assignee, custom_field, due_date, issue_fields, normalize, resolve, safe_text
from .config import TaskError
from .review import review_draft
from .ui import Style, progress_bar


class Cancelled(Exception):
    """The user cancelled issue composition."""


def say(text):
    print(safe_text(text), file=sys.stderr)


def ask(prompt, default=""):
    style = Style(sys.stderr)
    default_hint = style.dim(f" [{default}]") if default else ""
    say(style.bold(prompt) + default_hint + ":")
    value = input().strip()
    if value == ":cancel":
        raise Cancelled
    return value or default


def choose(items, label, default_id=None, search=False):
    if not items:
        raise TaskError(f"No hi ha opcions disponibles: {label}.")
    style = Style(sys.stderr)
    query = ask("Cerca un projecte (Enter per veure’ls tots)") if search else ""
    while True:
        matches = [item for item in items if normalize(query) in
                   normalize(f"{item['name']} {item.get('identifier', '')}")]
        if not matches:
            say(style.warn("No s’ha trobat cap coincidència."))
            query = ask("Cerca un projecte")
            continue
        default = ""
        width = len(str(len(matches)))
        for index, item in enumerate(matches, 1):
            num = style.cyan(f"{index:>{width}}.")
            item_id = style.dim(f"[ID {item['id']}]")
            say(f"  {num} {item['name']} {item_id}")
            if item["id"] == default_id:
                default = str(index)
        value = ask(label + (" (número o text de cerca)" if search else " (número)"), default)
        if value.isdecimal() and 1 <= int(value) <= len(matches):
            return matches[int(value) - 1]
        if search and value and not value.isdecimal():
            query = value
        else:
            say(style.warn("Selecciona un número de la llista."))


def edit_description(original):
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    editor = editor or shutil.which("nano") or shutil.which("vi")
    if not editor:
        say("Escriu la descripció; acaba amb un punt (.) en una línia. :cancel cancel·la.")
        lines = []
        while True:
            line = input()
            if line == ":cancel":
                raise Cancelled
            if line == ".":
                return "\n".join(lines)
            lines.append(line)
    try:
        command = shlex.split(editor)
        if not command:
            raise ValueError
        with tempfile.TemporaryDirectory(prefix="redmine-draft-") as directory:
            path = Path(directory) / "description.txt"
            path.write_text(original, encoding="utf-8")
            say("Edita la descripció, desa el fitxer i tanca l’editor per continuar.")
            completed = subprocess.run([*command, str(path)], check=False)
            if completed.returncode:
                raise TaskError("L’editor ha fallat. Es conserva la descripció anterior.")
            return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError):
        raise TaskError("No s’ha pogut obrir l’editor. Configura VISUAL o EDITOR; "
                        "es conserva la descripció anterior.") from None


def validated(prompt, validator, default=""):
    while True:
        value = ask(prompt, default)
        try:
            validator(value)
            return value
        except (TaskError, argparse.ArgumentTypeError) as exc:
            say(f"Error: {exc}")


def edit_text(args):
    while True:
        title = ask("Títol", args.title or "")
        if title.strip():
            args.title = title
            break
        say("El títol no pot estar buit.")
    args.description = edit_description(args.description or "")


def apply_review(args, project):
    style = Style(sys.stderr)
    say(style.info("Revisant el títol i la descripció amb Codex…"))
    try:
        proposal = review_draft(args.title, args.description or "", project)
    except TaskError as exc:
        say(style.err(f"Error: {exc}"))
        return
    say("\n" + style.heading("Proposta de revisió"))
    say(style.rule(40))
    say(style.bold("Títol proposat: ") + proposal["title"])
    say("\n" + proposal["description"])
    for warning in proposal["warnings"]:
        say(style.warn(f"Pendent de concretar: {warning}"))
    while True:
        action = ask("[a] Aplica la proposta · [d] Descarta-la", "d").casefold()
        if action == "a":
            args.title = proposal["title"]
            args.description = proposal["description"]
            return
        if action == "d":
            return
        say(style.warn("Tria a o d."))


def edit_fields(args, project):
    available = project.get("issue_custom_fields", [])
    if not available:
        say("Aquest projecte no té camps personalitzats disponibles.")
        return
    for field in available:
        say(f"{field['id']} — {field['name']}")
    selected = {field["id"]: field for field in args.field or []}
    while True:
        value = ask("Camp ID=VALOR (Enter per acabar)")
        if not value:
            args.field = list(selected.values()) or None
            return
        try:
            field = custom_field(value)
            if field["id"] not in {item["id"] for item in available}:
                raise TaskError("El camp no està disponible en aquest projecte.")
            selected[field["id"]] = field
        except (TaskError, argparse.ArgumentTypeError) as exc:
            say(f"Error: {exc}")


def preview(args, project, tracker, priority):
    style = Style(sys.stderr)
    say("\n" + style.heading("Revisa la tasca abans de continuar:"))
    say(style.rule(44))
    project_id = style.dim(f"[ID {project['id']}]")
    say(f"  {style.dim('Projecte:'.ljust(12))} {project['name']} {project_id}")
    say(f"  {style.dim('Tipus:'.ljust(12))} {tracker['name']}")
    say(f"  {style.dim('Prioritat:'.ljust(12))} {style.priority(priority['name'])}")
    say(f"  {style.dim('Assignat:'.ljust(12))} {args.assignee}")
    say(f"  {style.dim('Venciment:'.ljust(12))} {args.due_date or style.dim('sense data')}")
    done = args.progress if args.progress is not None else 0
    say(f"  {style.dim('Completat:'.ljust(12))} {progress_bar(done, style=style)}")
    say(f"  {style.dim('Títol:'.ljust(12))} {style.bold(args.title)}")
    say("\n" + style.bold("Descripció:"))
    say(args.description or style.dim("(buida)"))
    for field in args.field or []:
        field_label = style.dim(f"Camp {field['id']}:")
        say(f"  {field_label} {field['value']}")


def prepare_issue(args, client):
    try:
        return _prepare_issue(args, client)
    except (Cancelled, EOFError):
        return False


def _prepare_issue(args, client):
    say("Assistent de creació de tasques. Escriu :cancel per cancel·lar en qualsevol pas.")
    if args.project:
        project = client.project(args.project)
    else:
        selection = choose(client.pages("/projects.json", "projects"), "Selecciona el projecte", search=True)
        project = client.project(selection["id"])
    args.project = str(project["id"])
    trackers = project.get("trackers", [])
    default = next((item["id"] for item in trackers if str(item["id"]) == args.tracker
                    or normalize(item["name"]) == normalize(args.tracker)), None)
    tracker = choose(trackers, "Selecciona el tipus", default_id=default)
    args.tracker = str(tracker["id"])
    if not args.title or not args.title.strip():
        args.title = None
        while not args.title:
            args.title = ask("Títol")
    if args.description is None:
        args.description = edit_description("")
    priorities = [item for item in client.priorities() if item.get("active", True)]
    default = resolve(args.priority, priorities, "Prioritat") if args.priority else next(
        (item["id"] for item in priorities if item.get("is_default") or item["name"] == "Normal"), None)
    priority = choose(priorities, "Selecciona la prioritat", default_id=default)
    args.priority = str(priority["id"])
    user = client.current_user()
    say(f"El teu usuari: {user.get('firstname', '')} {user.get('lastname', '')} [ID {user['id']}]")
    args.assignee = validated("Assignat (me, none o ID d’usuari)",
                              lambda value: assignee(value, client), args.assignee or "me")
    args.due_date = validated("Venciment (AAAA-MM-DD; Enter per conservar, - per eliminar)",
                              lambda value: due_date("" if value == "-" else value), args.due_date or "")
    if args.due_date == "-":
        args.due_date = ""
    if args.review:
        apply_review(args, project)
    while True:
        preview(args, project, tracker, priority)
        submit_label = "Mostra simulació" if args.dry_run else "Crea"
        action = ask(f"[c] {submit_label} · [e] Edita el text · [r] Revisa amb Codex · [f] Camps · [x] Cancel·la", "x").casefold()
        if action == "x":
            return False
        if action == "e":
            try:
                edit_text(args)
            except TaskError as exc:
                say(f"Error: {exc}")
        elif action == "r":
            apply_review(args, project)
        elif action == "f":
            edit_fields(args, project)
        elif action == "c":
            try:
                issue_fields(args, client)
            except TaskError as exc:
                say(f"Error: {exc}")
                continue
            return True
        else:
            say("Tria c, e, r, f o x.")
