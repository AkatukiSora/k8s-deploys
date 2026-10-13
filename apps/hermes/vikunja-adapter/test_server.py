#!/usr/bin/env python3
"""Regression tests for the bounded Vikunja adapter."""

from __future__ import annotations

import importlib.util
import os
import threading
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen


MODULE_PATH = Path(__file__).with_name("server.py")
spec = importlib.util.spec_from_file_location("vikunja_adapter", MODULE_PATH)
assert spec is not None and spec.loader is not None
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)

READ_PROXY_PATH = MODULE_PATH.parent.parent / "vikunja-read-proxy" / "server.py"
read_proxy_spec = importlib.util.spec_from_file_location("vikunja_read_proxy_regression", READ_PROXY_PATH)
assert read_proxy_spec is not None and read_proxy_spec.loader is not None
read_proxy = importlib.util.module_from_spec(read_proxy_spec)
read_proxy_spec.loader.exec_module(read_proxy)


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _):
        return b"[]"


class RedirectTargetHandler(BaseHTTPRequestHandler):
    calls = []

    def do_GET(self):
        self.__class__.calls.append(self.headers.get("Authorization"))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *_):
        pass


class RedirectSourceHandler(BaseHTTPRequestHandler):
    target = ""

    def do_GET(self):
        self.send_response(302)
        self.send_header("Location", self.target)
        self.end_headers()

    def log_message(self, *_):
        pass


class VikunjaClientTests(unittest.TestCase):
    def test_request_uses_a_stable_user_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            token_path = Path(directory) / "token"
            token_path.write_text("token-is-not-logged\n", encoding="utf-8")
            captured = []

            def fake_urlopen(request, timeout):
                captured.append(request)
                self.assertEqual(timeout, 10)
                return FakeResponse()

            with (
                patch.dict(
                    os.environ,
                    {
                        "VIKUNJA_BASE_URL": "https://vikunja.akatuki-host.com",
                        "VIKUNJA_TOKEN_FILE": str(token_path),
                    },
                    clear=False,
                ),
                patch.object(adapter._UPSTREAM_OPENER, "open", fake_urlopen),
            ):
                adapter.VikunjaClient().request("GET", "/api/v1/tasks")

            self.assertEqual(captured[0].get_header("User-agent"), adapter.USER_AGENT)
            self.assertIn("Vikunja-2.x", adapter.USER_AGENT)
            self.assertIn("API-v1", adapter.USER_AGENT)

    def test_upstream_redirect_is_not_followed_to_another_origin(self):
        target = ThreadingHTTPServer(("127.0.0.1", 0), RedirectTargetHandler)
        source = ThreadingHTTPServer(("127.0.0.1", 0), RedirectSourceHandler)
        RedirectTargetHandler.calls = []
        RedirectSourceHandler.target = f"http://127.0.0.1:{target.server_port}/collect"
        threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in (target, source)]
        for thread in threads:
            thread.start()
        try:
            request = Request(f"http://127.0.0.1:{source.server_port}/redirect",
                              headers={"Authorization": "Bearer synthetic-token"})
            with self.assertRaises(HTTPError) as result:
                adapter._UPSTREAM_OPENER.open(request, timeout=3)
            self.assertEqual(result.exception.code, 302)
            self.assertEqual(RedirectTargetHandler.calls, [])
        finally:
            for server in (source, target):
                server.shutdown()
                server.server_close()
    def test_read_proxy_rejects_all_mutating_http_methods(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), read_proxy.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                request = Request(f"http://127.0.0.1:{server.server_port}/v1/tasks", method=method)
                with self.subTest(method=method), self.assertRaises(HTTPError) as result:
                    urlopen(request, timeout=3)
                self.assertEqual(result.exception.code, 405)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
