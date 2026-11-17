"""Redmine REST API client."""

import json
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .config import TaskError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the key to another destination or repeat writes.
        return None


class RedmineClient:
    def __init__(self, config):
        self.config = config
        self.opener = build_opener(NoRedirect())

    def request(self, method, path, params=None, body=None):
        url = self.config.url + path
        if params:
            url += "?" + urlencode({k: v for k, v in params.items() if v is not None})
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        req = Request(url, data=data, method=method, headers={
            "X-Redmine-API-Key": self.config.token,
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
        })
        try:
            with self.opener.open(req, timeout=25) as response:
                raw = response.read()
                result = json.loads(raw) if raw.strip() else {}
                if not isinstance(result, dict):
                    raise TaskError("Redmine ha retornat un format de resposta inesperat.")
                return result
        except HTTPError as exc:
            messages = {
                401: "Credencial no vàlida o API REST no habilitada.",
                403: "No tens permís per a aquesta operació.",
                404: "No es troba el recurs sol·licitat.",
                422: "Redmine ha rebutjat els camps enviats.",
            }
            message = messages.get(exc.code, "La petició a Redmine ha fallat.")
            if exc.code == 422:
                try:
                    errors = json.loads(exc.read()).get("errors", [])
                    if isinstance(errors, list):
                        message += " " + "; ".join(str(error) for error in errors)
                except (ValueError, OSError, AttributeError):
                    pass
            exc.close()
            message = message.replace(self.config.token, "[ocult]")
            raise TaskError(f"HTTP {exc.code}: {message}") from None
        except (URLError, TimeoutError, socket.timeout, OSError):
            raise TaskError("No es pot connectar amb Redmine. Comprova la xarxa, la VPN i el certificat TLS.") from None
        except (ValueError, UnicodeError):
            raise TaskError("Redmine ha retornat una resposta JSON no vàlida.") from None

    def get(self, path, **params):
        return self.request("GET", path, params=params)

    def pages(self, path, key, **params):
        offset = 0
        items = []
        while True:
            data = self.get(path, **dict(params, limit=100, offset=offset))
            batch = data.get(key, [])
            items.extend(batch)
            offset += len(batch)
            if not batch or offset >= data.get("total_count", offset):
                return items

    def current_user(self):
        return self.get("/users/current.json")["user"]

    def issue(self, issue_id):
        return self.get(f"/issues/{issue_id}.json", include="journals,allowed_statuses")["issue"]

    def project(self, reference):
        # Project identifiers occupy a single URL path segment.
        from urllib.parse import quote

        ref = quote(str(reference), safe="")
        return self.get(f"/projects/{ref}.json", include="trackers,issue_custom_fields")["project"]

    def statuses(self):
        return self.get("/issue_statuses.json")["issue_statuses"]

    def priorities(self):
        return self.get("/enumerations/issue_priorities.json")["issue_priorities"]
