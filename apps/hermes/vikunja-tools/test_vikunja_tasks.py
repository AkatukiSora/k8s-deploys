#!/usr/bin/env python3
"""Offline tests for the bounded Vikunja CLI."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import json
import re
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("vikunja-tasks")
loader = importlib.machinery.SourceFileLoader("vikunja_tasks_cli", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
cli = importlib.util.module_from_spec(spec)
loader.exec_module(cli)


class FakeResponse:
    status = 201

    def __init__(self, payload=b'{"id":1}'):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.payload


class VikunjaCliTests(unittest.TestCase):
    def invoke(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", [str(SCRIPT), *args]), redirect_stdout(output), redirect_stderr(errors):
            cli.main()
        return output.getvalue(), errors.getvalue()

    def test_read_commands_and_label_catalog_use_fixed_local_routes(self):
        calls = []
        with patch.object(cli, "request", side_effect=lambda *args, **kwargs: calls.append((args, kwargs))):
            self.invoke("projects", "list", "--page", "2", "--per-page", "20", "--search", "work")
            self.invoke("tasks", "list")
            self.invoke("tasks", "get", "5")
            self.invoke("labels", "list", "--search", "urgent")
        self.assertEqual(calls[0], (("GET", "/projects"), {"query": {"page": 2, "per_page": 20, "s": "work"}}))
        self.assertEqual(calls[1], (("GET", "/tasks"), {"query": {"page": None, "per_page": None, "s": None}}))
        self.assertEqual(calls[2], (("GET", "/tasks/5"), {}))
        self.assertEqual(calls[3], (("GET", "/labels"), {"query": {"page": None, "per_page": None, "s": "urgent"}}))

    def test_create_preserves_zero_and_empty_fields_and_serializes_reminders(self):
        calls = []
        with patch.object(cli, "request", side_effect=lambda *args, **kwargs: calls.append((args, kwargs))):
            self.invoke("tasks", "create", "--project", "7", "--title", "new", "--priority", "0",
                        "--description", "", "--reminders-json", "[]")
        self.assertEqual(calls, [(("POST", "/tasks", {"title": "new", "description": "", "priority": 0,
                                                         "reminders": [], "project_id": 7}), {})])

    def test_update_maps_clear_flags_and_reminder_clear(self):
        calls = []
        with patch.object(cli, "request", side_effect=lambda *args, **kwargs: calls.append((args, kwargs))):
            self.invoke("tasks", "update", "42", "--clear-due", "--clear-start", "--clear-end",
                        "--clear-reminders", "--description", "")
        self.assertEqual(calls, [(("POST", "/tasks/42", {"description": "", "due_date": None,
                                                         "start_date": None, "end_date": None, "reminders": []}), {})])

    def test_clear_and_value_flags_are_mutually_exclusive(self):
        for args in (("tasks", "update", "1", "--due", "2027-01-01T00:00:00Z", "--clear-due"),
                     ("tasks", "update", "1", "--reminders-json", "[]", "--clear-reminders")):
            with self.subTest(args=args), patch.object(cli, "request") as request:
                with self.assertRaises(SystemExit):
                    self.invoke(*args)
                request.assert_not_called()

    def test_empty_update_and_complete_are_not_exposed(self):
        with patch.object(cli, "request") as request:
            with self.assertRaises(SystemExit):
                self.invoke("tasks", "update", "1")
            with self.assertRaises(SystemExit):
                self.invoke("tasks", "complete", "1")
            request.assert_not_called()

    def test_malformed_or_nonfinite_reminder_json_is_rejected_before_request(self):
        with patch.object(cli, "request") as request:
            for value in ("{", "[NaN]", '[{"reminder":"2027-01-01T00:00:00Z","reminder":"2027-01-02T00:00:00Z"}]'):
                with self.subTest(value=value), self.assertRaises(SystemExit):
                    self.invoke("tasks", "update", "1", "--reminders-json", value)
            request.assert_not_called()

    def test_label_and_relation_commands_use_only_fixed_routes(self):
        calls = []
        with patch.object(cli, "request", side_effect=lambda *args, **kwargs: calls.append((args, kwargs))):
            self.invoke("tasks", "labels", "add", "1", "--label", "11")
            self.invoke("tasks", "labels", "remove", "1", "--label", "11")
            self.invoke("tasks", "relations", "add", "2", "--other", "1", "--kind", "subtask")
            self.invoke("tasks", "relations", "remove", "2", "--other", "1", "--kind", "subtask")
        self.assertEqual(calls, [
            (("POST", "/tasks/1/labels/add", {"label_id": 11}), {}),
            (("POST", "/tasks/1/labels/remove", {"label_id": 11}), {}),
            (("POST", "/tasks/2/relations/add", {"other_task_id": 1, "relation_kind": "subtask"}), {}),
            (("POST", "/tasks/2/relations/remove", {"other_task_id": 1, "relation_kind": "subtask"}), {}),
        ])

    def test_relation_help_documents_orientation_and_hidden_api_kind(self):
        output = io.StringIO()
        with patch.object(sys, "argv", [str(SCRIPT), "tasks", "relations", "add", "--help"]), \
             redirect_stdout(output), self.assertRaises(SystemExit):
            cli.main()
        self.assertIn("duplicateof exists in the API but is not offered by the UI",
                      re.sub(r"\s+", " ", output.getvalue()))

    def test_error_response_is_structured_on_stderr_and_unknown_fields_are_dropped(self):
        raw = json.dumps({"error": "safe failure", "write_state": "applied_unverified", "task_id": 17,
                          "operation": "tasks.update", "verification": "unavailable",
                          "raw_upstream": "do not display", "task_text": "private"}).encode()
        error = HTTPError("http://127.0.0.1:8791/tasks/17", 502, "bad gateway", Message(), io.BytesIO(raw))
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(cli, "urlopen", side_effect=error), redirect_stdout(stdout), redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as result:
                cli.request("POST", "/tasks/17", {"title": "private"})
        self.assertEqual(result.exception.code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn('"write_state":"applied_unverified"', stderr.getvalue())
        self.assertIn('"task_id":17', stderr.getvalue())
        self.assertNotIn("raw_upstream", stderr.getvalue())
        self.assertNotIn("private", stderr.getvalue())

    def test_success_uses_fixed_loopback_endpoint_and_prints_json(self):
        captured = []
        with patch.object(cli, "urlopen", side_effect=lambda request, timeout: (captured.append((request, timeout)) or FakeResponse())):
            stdout, stderr = self.invoke("tasks", "create", "--project", "7", "--title", "x")
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout), {"id": 1})
        request, timeout = captured[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8791/tasks")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(timeout, 15)


if __name__ == "__main__":
    unittest.main()
