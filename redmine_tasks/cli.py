"""Command-line interface for Redmine task management."""

import argparse
from datetime import date
import json
import re
import sys
import unicodedata

from .client import RedmineClient
from .config import Config, TaskError
from .ui import Style, progress_bar, render_table


class HelpFormatter(argparse.HelpFormatter):
    def add_usage(self, usage, actions, groups, prefix=None):
        super().add_usage(usage, actions, groups, prefix="ús: " if prefix is None else prefix)


class ArgumentParser(argparse.ArgumentParser):
    """Keep argparse help and common diagnostics in Catalan on any system locale."""

    def __init__(self, *args, **kwargs):
        add_help = kwargs.pop("add_help", True)
        kwargs.setdefault("formatter_class", HelpFormatter)
        super().__init__(*args, add_help=False, **kwargs)
        self._positionals.title = "arguments posicionals"
        self._optionals.title = "opcions"
        if add_help:
            self.add_argument("-h", "--help", action="help",
                              help="Mostra aquesta ajuda i surt")

    def error(self, message):
        translations = {
            "the following arguments are required:": "cal indicar els arguments següents:",
            "unrecognized arguments:": "arguments no reconeguts:",
            "invalid choice:": "opció no vàlida:",
            "choose from": "tria entre",
            "expected one argument": "cal indicar un valor",
            "expected at least one argument": "cal indicar almenys un valor",
            "expected at most one argument": "es pot indicar com a màxim un valor",
            "not allowed with argument": "no es pot combinar amb l’argument",
            "ambiguous option:": "opció ambigua:",
            "could match": "pot correspondre a",
            "ignored explicit argument": "valor explícit no admès",
        }
        for source, target in translations.items():
            message = message.replace(source, target)
        message = re.sub(r"expected (\d+) arguments?", r"cal indicar \1 valors", message)
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {message}\n")


def positive(value):
    try:
        result = int(value)
        if result > 0:
            return result
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("Fes servir un identificador enter positiu.")


def percentage(value):
    try:
        result = int(value)
        if 0 <= result <= 100:
            return result
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("El percentatge ha d’estar entre 0 i 100.")


def due_date(value):
    if value == "":
        return ""
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() == value:
            return value
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("Fes servir una data AAAA-MM-DD.")


def custom_field(value):
    key, separator, content = value.partition("=")
    if not separator or not key.isdecimal() or int(key) <= 0:
        raise argparse.ArgumentTypeError("Fes servir --field ID=VALOR amb un ID positiu.")
    return {"id": int(key), "value": content}


def normalize(value):
    return "".join(c for c in unicodedata.normalize("NFD", str(value).casefold())
                   if not unicodedata.combining(c))


def resolve(value, options, label):
    matches = [item for item in options if str(item["id"]) == str(value)
               or normalize(item["name"]) == normalize(value)]
    if len(matches) != 1:
        choices = ", ".join(f"{item['id']}={item['name']}" for item in options)
        raise TaskError(f"{label} desconegut o ambigu: {value}. Opcions: {choices or '(cap)'}.")
    return matches[0]["id"]


def parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="Sortida JSON per a automatització")
    common.add_argument("--env-file", default=argparse.SUPPRESS, metavar="FITXER",
                        help="Fitxer de credencials (per defecte ~/.env)")
    root = ArgumentParser(description="Gestiona les teves tasques de Redmine.", parents=[common])
    commands = root.add_subparsers(dest="command", title="ordres", metavar="ORDRE")
    aliases = {"list": "listar", "show": "ver", "projects": "proyectos",
               "catalogs": "catalogos", "check": "comprobar", "create": "crear",
               "edit": "editar", "comment": "comentar", "status": "estado"}

    def command(name, help_text):
        item = commands.add_parser(name, aliases=[aliases[name]] if name in aliases else [], help=help_text,
                                   description=help_text, parents=[common])
        item.set_defaults(command=name)
        return item

    listing = command("list", "Llista les tasques (per defecte: les meves tasques obertes)")
    listing.add_argument("--project", "--proyecto", help="ID o identificador del projecte")
    listing.add_argument("--status", "--estado", default="open", help="open, all, closed, nom o ID")
    listing.add_argument("--priority", "--prioridad", help="Nom o ID de la prioritat")
    listing.add_argument("--assignee", "--asignado", default="me", help="me, all, none o ID d’usuari")
    detail = command("show", "Mostra els detalls, els comentaris i els estats permesos")
    detail.add_argument("id", type=positive, help="ID de la tasca")
    command("projects", "Llista els projectes accessibles")
    catalogs = command("catalogs", "Mostra els estats, els tipus, les prioritats i els camps")
    catalogs.add_argument("--project", "--proyecto", help="Limita els tipus i els camps a aquest projecte")
    command("check", "Comprova la connexió i l’usuari autenticat")

    for name, help_text in [("create", "Crea una tasca"), ("edit", "Edita una tasca")]:
        item = command(name, help_text)
        if name == "create":
            item.add_argument("--project", "--proyecto", help="ID o identificador del projecte")
            item.add_argument("--interactive", action="store_true", help="Obre l’assistent encara que s’indiquin tots els camps")
            item.add_argument("--review", action="store_true", help="Proposa una revisió amb Codex abans de confirmar")
        else:
            item.add_argument("id", type=positive, help="ID de la tasca")
        item.add_argument("--title", "--titulo", help="Títol de la tasca")
        item.add_argument("--description", "--descripcion", help="Descripció de la tasca")
        item.add_argument("--tracker", "--tipo", default="Tasca" if name == "create" else None,
                          help="Nom o ID del tipus (per defecte: Tasca en crear)")
        item.add_argument("--priority", "--prioridad", help="Nom o ID de la prioritat")
        item.add_argument("--assignee", "--asignado", help="me, none o ID d’usuari")
        item.add_argument("--due-date", "--vencimiento", type=due_date, help='AAAA-MM-DD; "" elimina la data')
        item.add_argument("--progress", "--porcentaje", type=percentage, help="Percentatge completat (0–100)")
        item.add_argument("--field", "--campo", type=custom_field, action="append", help="ID=VALOR; es pot repetir")
        item.add_argument("--dry-run", action="store_true", help="Mostra la petició sense enviar-la")

    comment = command("comment", "Afegeix un comentari")
    comment.add_argument("id", type=positive, help="ID de la tasca")
    comment.add_argument("text", help="Text del comentari en català")
    comment.add_argument("--dry-run", action="store_true", help="Mostra la petició sense enviar-la")
    status = command("status", "Canvia a l’estat permès indicat")
    status.add_argument("id", type=positive, help="ID de la tasca")
    status.add_argument("name", help="Nom o ID de l’estat")
    status.add_argument("--dry-run", action="store_true", help="Mostra la petició sense enviar-la")
    review = command("review", "Revisa un esborrany amb Codex sense crear cap tasca")
    review.add_argument("--title", required=True, help="Títol de l’esborrany")
    review.add_argument("--description", default="", help="Descripció de l’esborrany")
    review.add_argument("--project", help="Projecte opcional per donar context a la revisió")
    return root


def assignee(value, client):
    value = {"yo": "me", "sin": "none"}.get(value, value)
    if value == "me":
        return client.current_user()["id"]
    if value == "none":
        return None
    if str(value).isdecimal() and int(value) > 0:
        return int(value)
    raise TaskError("Assignació no vàlida. Fes servir me, none o un ID d’usuari positiu.")


def issue_fields(args, client):
    fields = {}
    for argument, field in [("title", "subject"), ("description", "description"),
                            ("due_date", "due_date"), ("progress", "done_ratio")]:
        value = getattr(args, argument)
        if value is not None:
            if argument == "title" and not value.strip():
                raise TaskError("El títol no pot estar buit.")
            fields[field] = value
    if args.priority is not None:
        fields["priority_id"] = resolve(args.priority, client.priorities(), "Prioritat")
    if args.assignee is not None or args.command == "create":
        fields["assigned_to_id"] = assignee(args.assignee or "me", client)
    if args.tracker is not None or args.command == "create" or args.field:
        reference = args.project if args.command == "create" else client.issue(args.id)["project"]["id"]
        project = client.project(reference)
        if args.command == "create":
            fields["project_id"] = project["id"]
        if args.tracker is not None:
            fields["tracker_id"] = resolve(args.tracker, project.get("trackers", []), "Tipus")
        if args.field:
            allowed = {field["id"] for field in project.get("issue_custom_fields", [])}
            selected = {}
            for custom in args.field:
                if custom["id"] not in allowed:
                    raise TaskError(f"El camp {custom['id']} no està disponible en aquest projecte.")
                if custom["id"] in selected:
                    raise TaskError(f"Camp personalitzat duplicat: {custom['id']}.")
                selected[custom["id"]] = custom
            fields["custom_fields"] = list(selected.values())
    if not fields:
        raise TaskError("Indica almenys un camp per editar.")
    return fields


def run(args, client):
    review_result = None
    if args.command == "review":
        from .review import review_draft

        project = client.project(args.project) if args.project else None
        return {"review": review_draft(args.title, args.description, project)}
    if args.command == "create":
        interactive = (args.interactive or args.project is None or args.title is None
                       or (args.review and not args.dry_run))
        if interactive:
            from .workflow import prepare_issue

            if not sys.stdin.isatty():
                raise TaskError("L’assistent requereix un terminal. Indica --project i --title; "
                                "per revisar sense terminal, fes servir review o --review --dry-run.")
            if not prepare_issue(args, client):
                return {"result": "cancelled"}
        elif args.review:
            from .review import review_draft

            review_result = review_draft(args.title, args.description or "", client.project(args.project))
            args.title = review_result["title"]
            args.description = review_result["description"]
    if args.command == "check":
        user = client.current_user()
        return {"url": client.config.url, "user": {
            key: user.get(key) for key in ("id", "login", "firstname", "lastname")
        }}
    if args.command == "projects":
        return {"projects": client.pages("/projects.json", "projects")}
    if args.command == "catalogs":
        result = {"statuses": client.statuses(), "priorities": client.priorities()}
        if args.project:
            project = client.project(args.project)
            result.update(trackers=project.get("trackers", []),
                          fields=project.get("issue_custom_fields", []))
        else:
            result["trackers"] = client.get("/trackers.json")["trackers"]
        return result
    if args.command == "show":
        return {"issue": client.issue(args.id)}
    if args.command == "list":
        states = {"open": "open", "all": "*", "closed": "closed",
                  "abiertos": "open", "todos": "*", "cerrados": "closed"}
        status = states.get(args.status)
        if status is None:
            status = resolve(args.status, client.statuses(), "Estat")
        assigned = {"me": "me", "none": "!*", "yo": "me", "sin": "!*"}.get(args.assignee)
        if assigned is None and args.assignee not in {"all", "todos"}:
            assigned = assignee(args.assignee, client)
        params = {"status_id": status, "assigned_to_id": assigned, "sort": "priority:desc,updated_on:desc"}
        if args.project:
            params["project_id"] = client.project(args.project)["id"]
        if args.priority:
            params["priority_id"] = resolve(args.priority, client.priorities(), "Prioritat")
        issues = client.pages("/issues.json", "issues", **params)
        return {"total": len(issues), "issues": issues}

    method = "PUT"
    path = f"/issues/{args.id}.json" if args.command != "create" else "/issues.json"
    if args.command in {"create", "edit"}:
        fields = issue_fields(args, client)
        if args.command == "create":
            method = "POST"
    elif args.command == "comment":
        if not args.text.strip():
            raise TaskError("El comentari no pot estar buit.")
        fields = {"notes": args.text}
    else:
        issue = client.issue(args.id)
        allowed = issue.get("allowed_statuses")
        if allowed is None:
            raise TaskError("Redmine no informa de les transicions permeses per a aquesta tasca.")
        fields = {"status_id": resolve(args.name, allowed, "Estat permès")}
    body = {"issue": fields}
    if args.dry_run:
        result = {"dry_run": True, "method": method, "path": path, "body": body}
        if review_result is not None:
            result["review"] = review_result
        return result
    response = client.request(method, path, body=body)
    issue_id = response["issue"]["id"] if args.command == "create" else args.id
    return {"result": "created" if args.command == "create" else "updated",
            "id": issue_id, "url": f"{client.config.url}/issues/{issue_id}"}


def safe_text(value):
    # Strip terminal control sequences from server-provided content.
    return "".join(c if c >= " " or c == "\n" else " " for c in str(value)).replace("\x7f", " ")


def named(value):
    return value.get("name", "—") if isinstance(value, dict) else value or "—"


def _display_list(data, style):
    total = data["total"]
    count_label = f"{total} {'tasca' if total == 1 else 'tasques'}"
    print(style.heading(count_label))
    if not data["issues"]:
        print(style.dim("No s’han trobat tasques."))
        return
    rows = []
    for issue in data["issues"]:
        due = safe_text(issue.get("due_date") or "")
        rows.append([
            style.bold(f"#{issue['id']}"),
            style.status(safe_text(named(issue.get("status")))),
            style.priority(safe_text(named(issue.get("priority")))),
            safe_text(named(issue.get("project"))),
            due if due else style.dim("sense data"),
            safe_text(issue["subject"]),
        ])
    headers = ["ID", "Estat", "Prioritat", "Projecte", "Venciment", "Títol"]
    for line in render_table(headers, rows, style=style, flex_col=5):
        print(line)


def _display_show(issue, style):
    print(style.heading(safe_text(f"#{issue['id']} — {issue['subject']}")))
    print(style.rule())
    for label, key in [("Projecte", "project"), ("Estat", "status"), ("Tipus", "tracker"),
                       ("Prioritat", "priority"), ("Assignat", "assigned_to"),
                       ("Venciment", "due_date")]:
        value = safe_text(named(issue.get(key)))
        if key == "status":
            value = style.status(value)
        elif key == "priority":
            value = style.priority(value)
        print(f"  {style.dim(f'{label:<14}')} {value}")
    done = issue.get("done_ratio") or 0
    print(f"  {style.dim('Completat'.ljust(14))} {progress_bar(done, style=style)}")

    print("\n" + style.bold("Descripció"))
    print(style.rule(40))
    description = safe_text(issue.get("description") or "")
    print(description if description.strip() else style.dim("(buida)"))

    custom_fields = issue.get("custom_fields", [])
    if custom_fields:
        print("\n" + style.bold("Camps personalitzats"))
        print(style.rule(40))
        for field in custom_fields:
            val = safe_text(field.get("value") or "—")
            print(safe_text(f"  {style.dim(str(field['id']))} {field['name']}: {val}"))

    allowed = issue.get("allowed_statuses", [])
    if allowed:
        print("\n" + style.bold("Estats permesos"))
        print(style.rule(40))
        for status in allowed:
            print(safe_text(f"  {style.dim(str(status['id']))} {style.status(safe_text(status['name']))}"))

    journals = issue.get("journals", [])
    if journals:
        print("\n" + style.bold("Historial i comentaris"))
        print(style.rule(40))
        for journal in journals:
            header = safe_text(f"{journal.get('created_on', '')} — {named(journal.get('user'))}")
            print(style.info(style.bold(header)))
            if journal.get("notes"):
                for note_line in safe_text(journal["notes"]).splitlines():
                    print(f"  {note_line}")
            for detail in journal.get("details", []):
                old_v = safe_text(detail.get("old_value") or "—")
                new_v = safe_text(detail.get("new_value") or "—")
                print(safe_text(f"  {style.dim(detail.get('name', ''))}: {old_v} → {new_v}"))


def display(data, command):
    style = Style(sys.stdout)
    if command == "list":
        _display_list(data, style)
    elif command == "projects":
        projects = data["projects"]
        print(style.heading(f"{len(projects)} {'projecte' if len(projects) == 1 else 'projectes'}"))
        if not projects:
            print(style.dim("No hi ha projectes disponibles."))
            return
        rows = [[style.bold(str(p["id"])), style.cyan(safe_text(p["identifier"])), safe_text(p["name"])]
                for p in projects]
        for line in render_table(["ID", "Identificador", "Nom"], rows, style=style, flex_col=2):
            print(line)
    elif command == "show":
        _display_show(data["issue"], style)
    elif command == "catalogs":
        labels = {"statuses": "Estats", "priorities": "Prioritats",
                  "trackers": "Tipus", "fields": "Camps"}
        for group, items in data.items():
            print(style.heading(labels[group]))
            if not items:
                print(style.dim("  (cap)"))
                continue
            for item in items:
                item_id = style.dim(str(item["id"]).rjust(4))
                print(safe_text(f"  {item_id}  {item['name']}"))
    elif command == "review":
        proposal = data["review"]
        print(style.heading("Proposta de revisió"))
        print(style.rule(40))
        print(style.bold("Títol proposat: ") + safe_text(proposal["title"]))
        print("\n" + safe_text(proposal["description"]))
        for warning in proposal["warnings"]:
            print(style.warn(safe_text(f"Pendent de concretar: {warning}")))
    elif data.get("dry_run"):
        print(style.warn("Simulació: no s’ha enviat cap canvi a Redmine."))
        print(safe_text(json.dumps(data, ensure_ascii=False, indent=2)))
    elif command == "check":
        user = data["user"]
        print(style.ok(safe_text(f"Connexió correcta: {data['url']}")))
        full_name = f"{user.get('firstname') or ''} {user.get('lastname') or ''}".strip()
        user_id = style.dim(f"(ID {user['id']})")
        print(f"  {style.dim('Usuari:')} {safe_text(full_name)} {user_id}")
    elif "result" in data:
        if data["result"] == "cancelled":
            print(style.warn("Operació cancel·lada. No s’ha creat cap tasca."))
            return
        message = "Tasca creada" if data["result"] == "created" else "Tasca actualitzada"
        print(style.ok(safe_text(f"{message}: #{data['id']} — {data['url']}")))
    else:
        print(safe_text(json.dumps(data, ensure_ascii=False, indent=2)))


def main(argv=None):
    cli = parser()
    args = cli.parse_args(argv)
    if args.command is None:
        args = cli.parse_args([*(argv if argv is not None else sys.argv[1:]), "list"])
    try:
        client = None
        if args.command != "review" or args.project:
            config = Config.load(getattr(args, "env_file", None))
            client = RedmineClient(config)
        result = run(args, client)
        if getattr(args, "json", False):
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            display(result, args.command)
        return 0
    except TaskError as exc:
        message = str(exc)
        if "config" in locals():
            message = message.replace(config.token, "[ocult]")
        err_style = Style(sys.stderr)
        prefix = err_style.err("Error: ") if err_style.enabled else "Error: "
        print(prefix + safe_text(message), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nOperació interrompuda.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
