import io
import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from redmine_tasks.client import NoRedirect, RedmineClient
from redmine_tasks.config import Config, TaskError


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.client = RedmineClient(Config("https://example.test", "secret-token"))
        self.client.opener = MagicMock()

    def response(self, content):
        self.client.opener.open.return_value.__enter__.return_value.read.return_value = content

    def test_request_headers_body_and_query(self):
        self.response(b'{"issue":{"id":12}}')
        result = self.client.request("POST", "/issues.json", params={"search": "En procés", "unused": None}, body={"issue": {"subject": "Reunió"}})
        self.assertEqual(result["issue"]["id"], 12)
        req = self.client.opener.open.call_args.args[0]
        self.assertEqual(req.get_header("X-redmine-api-key"), "secret-token")
        self.assertNotIn("secret-token", req.full_url)
        self.assertEqual(parse_qs(urlsplit(req.full_url).query), {"search": ["En procés"]})
        self.assertEqual(json.loads(req.data)["issue"]["subject"], "Reunió")
        self.assertEqual(self.client.opener.open.call_args.kwargs["timeout"], 25)

    def test_empty_update_response(self):
        self.response(b"")
        self.assertEqual(self.client.request("PUT", "/issues/12.json", body={"issue": {}}), {})

    def test_pagination_even_when_server_caps_page_size(self):
        with patch.object(self.client, "get", side_effect=[
            {"issues": [{"id": 1}], "total_count": 3},
            {"issues": [{"id": 2}, {"id": 3}], "total_count": 3},
        ]) as get:
            self.assertEqual(self.client.pages("/issues.json", "issues", status_id="open"), [{"id": 1}, {"id": 2}, {"id": 3}])
            self.assertEqual([call.kwargs["offset"] for call in get.call_args_list], [0, 1])

    def test_empty_page_stops_pagination(self):
        with patch.object(self.client, "get", return_value={"issues": [], "total_count": 3}) as get:
            self.assertEqual(self.client.pages("/issues.json", "issues"), [])
            get.assert_called_once()

    def test_http_failures_and_validation_messages(self):
        for code in (401, 403, 404, 422, 500, 302):
            with self.subTest(code=code):
                self.client.opener.open.side_effect = HTTPError(
                    "https://example.test", code, "error", {},
                    io.BytesIO(b'{"errors":["Required field secret-token"]}'),
                )
                with self.assertRaises(TaskError) as caught:
                    self.client.request("PUT", "/issues/12.json", body={"issue": {}})
                self.assertIn(str(code), str(caught.exception))
                self.assertNotIn("secret-token", str(caught.exception))
                if code == 422:
                    self.assertIn("Required field", str(caught.exception))

    def test_network_failure_does_not_retry_writes(self):
        self.client.opener.open.side_effect = URLError("secret-token")
        with self.assertRaises(TaskError) as caught:
            self.client.request("POST", "/issues.json", body={"issue": {}})
        self.assertNotIn("secret-token", str(caught.exception))
        self.client.opener.open.assert_called_once()

    def test_invalid_json(self):
        self.response(b"<html>Login</html>")
        with self.assertRaisesRegex(TaskError, "JSON"):
            self.client.get("/issues.json")

    def test_unexpected_json_shape(self):
        self.response(b"[]")
        with self.assertRaisesRegex(TaskError, "format"):
            self.client.get("/issues.json")

    def test_redirects_are_not_followed(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.test"))


if __name__ == "__main__":
    unittest.main()
