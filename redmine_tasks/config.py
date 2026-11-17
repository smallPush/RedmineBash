"""Local configuration: never execute the contents of an .env file."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


class TaskError(Exception):
    """An error suitable for display to the user."""


def read_env(path):
    values = {}
    try:
        lines = Path(path).expanduser().read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return values
    except (OSError, UnicodeError) as exc:
        raise TaskError("No es pot llegir el fitxer de configuració.") from exc
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        if not separator or key.strip() not in {"TOKEN_REDMINE", "REDMINE_URL"}:
            continue
        value = value.strip()
        if value.startswith(("'", '"')):
            quote = value[0]
            end = value.find(quote, 1)
            if end == -1 or value[end + 1:].strip().split("#", 1)[0].strip():
                raise TaskError("Valor entre cometes no vàlid a la configuració.")
            value = value[1:end]
        else:
            value = value.split(" #", 1)[0].rstrip()
        values[key.strip()] = value
    return values


@dataclass(frozen=True)
class Config:
    url: str
    token: str = field(repr=False)

    @classmethod
    def load(cls, env_file=None):
        values = read_env(env_file or Path.home() / ".env")
        token = os.environ.get("TOKEN_REDMINE", values.get("TOKEN_REDMINE", ""))
        url = os.environ.get("REDMINE_URL", values.get("REDMINE_URL", "")).rstrip("/")
        if not token or not token.strip():
            raise TaskError("Defineix TOKEN_REDMINE a l’entorn o a ~/.env.")
        if any(ord(char) < 32 or ord(char) == 127 for char in token):
            raise TaskError("TOKEN_REDMINE conté caràcters no vàlids.")
        if not url:
            raise TaskError("Defineix REDMINE_URL a l’entorn o a ~/.env.")
        try:
            parts = urlsplit(url)
            valid = (
                parts.scheme == "https" and parts.hostname and not parts.username
                and not parts.password and not parts.query and not parts.fragment
            )
            parts.port
        except ValueError:
            valid = False
        if not valid:
            raise TaskError("REDMINE_URL ha de ser un URL HTTPS sense credencials, consulta ni fragment.")
        return cls(url, token)
