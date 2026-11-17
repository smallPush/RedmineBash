"""Command-line interface for Redmine task management."""

import argparse
from datetime import date
import json
import re
import sys
import unicodedata

from .client import RedmineClient
from .config import Config, TaskError


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
        item = commands.add_parser(name, aliases=[aliases[name]], help=help_text,
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
            item.add_argument("--project", "--proyecto", required=True, help="ID o identificador del projecte")
        else:
            item.add_argument("id", type=positive, help="ID de la tasca")
        item.add_argument("--title", "--titulo", required=name == "create", help="Títol de la tasca")
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
        return {"dry_run": True, "method": method, "path": path, "body": body}
    response = client.request(method, path, body=body)
    issue_id = response["issue"]["id"] if args.command == "create" else args.id
    return {"result": "created" if args.command == "create" else "updated",
            "id": issue_id, "url": f"{client.config.url}/issues/{issue_id}"}


def safe_text(value):
    # Strip terminal control sequences from server-provided content.
    return "".join(c if c >= " " or c == "\n" else " " for c in str(value)).replace("\x7f", " ")


def named(value):
    return value.get("name", "—") if isinstance(value, dict) else value or "—"


def display(data, command):
    if command == "list":
        print(f"{data['total']} {'tasca' if data['total'] == 1 else 'tasques'}")
        for issue in data["issues"]:
            print(safe_text(f"#{issue['id']} | {named(issue.get('status'))} | "
                            f"{named(issue.get('priority'))} | {named(issue.get('project'))} | "
                            f"{issue['subject']} | Venciment: {issue.get('due_date') or 'sense data'}"))
    elif command == "projects":
        for project in data["projects"]:
            print(safe_text(f"{project['id']} | {project['identifier']} | {project['name']}"))
    elif command == "show":
        issue = data["issue"]
        print(safe_text(f"#{issue['id']} — {issue['subject']}"))
        for label, key in [("Projecte", "project"), ("Estat", "status"), ("Tipus", "tracker"),
                           ("Prioritat", "priority"), ("Assignat", "assigned_to"),
                           ("Venciment", "due_date"), ("Completat (%)", "done_ratio")]:
            value = issue.get(key)
            print(safe_text(f"{label}: {value if value == 0 else named(value)}"))
        print("\nDescripció:\n" + safe_text(issue.get("description") or "(buida)"))
        print("\nCamps personalitzats:")
        for field in issue.get("custom_fields", []):
            print(safe_text(f"{field['id']} — {field['name']}: {field.get('value', '')}"))
        print("\nEstats permesos:")
        for status in issue.get("allowed_statuses", []):
            print(safe_text(f"{status['id']} — {status['name']}"))
        print("\nHistorial i comentaris:")
        for journal in issue.get("journals", []):
            print(safe_text(f"{journal.get('created_on', '')} — {named(journal.get('user'))}"))
            if journal.get("notes"):
                print(safe_text(journal["notes"]))
            for detail in journal.get("details", []):
                print(safe_text(f"  {detail.get('name')}: {detail.get('old_value', '—')} → {detail.get('new_value', '—')}"))
    elif command == "catalogs":
        labels = {"statuses": "Estats", "priorities": "Prioritats",
                  "trackers": "Tipus", "fields": "Camps"}
        for group, items in data.items():
            print(labels[group] + ":")
            for item in items:
                print(safe_text(f"  {item['id']} — {item['name']}"))
    elif data.get("dry_run"):
        print("Simulació: no s’ha enviat cap canvi a Redmine.")
        print(safe_text(json.dumps(data, ensure_ascii=False, indent=2)))
    elif command == "check":
        user = data["user"]
        print(safe_text(f"Connexió correcta: {data['url']}"))
        print(safe_text(f"Usuari: {user.get('firstname') or ''} {user.get('lastname') or ''} (ID {user['id']})"))
    elif "result" in data:
        message = "Tasca creada" if data["result"] == "created" else "Tasca actualitzada"
        print(safe_text(f"{message}: #{data['id']} — {data['url']}"))
    else:
        print(safe_text(json.dumps(data, ensure_ascii=False, indent=2)))


def main(argv=None):
    cli = parser()
    args = cli.parse_args(argv)
    if args.command is None:
        args = cli.parse_args([*(argv if argv is not None else sys.argv[1:]), "list"])
    try:
        config = Config.load(getattr(args, "env_file", None))
        result = run(args, RedmineClient(config))
        if getattr(args, "json", False):
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            display(result, args.command)
        return 0
    except TaskError as exc:
        message = str(exc)
        if "config" in locals():
            message = message.replace(config.token, "[ocult]")
        print("Error: " + safe_text(message), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nOperació interrompuda.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
