#!/usr/bin/env python3
"""Regression tests for the read-only Vikunja facade."""

from __future__ import annotations

import importlib.util
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("server.py")
spec = importlib.util.spec_from_file_location("vikunja_read_proxy", MODULE_PATH)
assert spec is not None and spec.loader is not None
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


class AdapterHandler(BaseHTTPRequestHandler):
    calls = []
    def do_GET(self):
        self.__class__.calls.append((self.path, self.headers.get("Authorization")))
        payload = b'[{"id":1,"title":"not printed by test"}]'
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)
    def log_message(self, *_): pass


class ReadProxyTests(unittest.TestCase):
    def setUp(self):
        self.adapter = ThreadingHTTPServer(("127.0.0.1", 0), AdapterHandler)
        self.adapter_thread = threading.Thread(target=self.adapter.serve_forever, daemon=True); self.adapter_thread.start()
        proxy.ADAPTER_BASE_URL = f"http://127.0.0.1:{self.adapter.server_port}"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), proxy.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.adapter.shutdown(); self.adapter.server_close()
    def request(self, method, path, headers=None):
        return urlopen(Request(f"http://127.0.0.1:{self.server.server_port}{path}", method=method, headers=headers or {}), timeout=3)
    def test_tasks_are_forwarded_without_caller_authorization(self):
        with self.request("GET", "/v1/tasks?per_page=1", {"Authorization": "Bearer caller-secret"}) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())[0]["id"], 1)
        self.assertEqual(AdapterHandler.calls[-1], ("/tasks?per_page=1", None))
    def test_write_methods_are_rejected(self):
        with self.assertRaises(HTTPError) as result: self.request("POST", "/v1/tasks")
        self.assertEqual(result.exception.code, 405)

if __name__ == "__main__": unittest.main()
