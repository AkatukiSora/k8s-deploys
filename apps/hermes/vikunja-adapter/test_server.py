#!/usr/bin/env python3
"""Regression tests for the bounded Vikunja adapter."""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("server.py")
spec = importlib.util.spec_from_file_location("vikunja_adapter", MODULE_PATH)
assert spec is not None and spec.loader is not None
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _):
        return b"[]"


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
                patch.object(adapter, "urlopen", fake_urlopen),
            ):
                adapter.VikunjaClient().request("GET", "/api/v1/tasks")

            self.assertEqual(captured[0].get_header("User-agent"), "Hermes-Vikunja-Adapter/1.0")


if __name__ == "__main__":
    unittest.main()
