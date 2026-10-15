#!/usr/bin/env python3
"""Synthetic contract tests for the bounded Vikunja write adapter."""
from __future__ import annotations

import copy
import importlib.util
import json
import threading
import time
import unittest
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from unittest.mock import patch

MODULE_PATH = Path(__file__).with_name("server.py")
spec = importlib.util.spec_from_file_location("vikunja_adapter_write_contract", MODULE_PATH)
assert spec is not None and spec.loader is not None
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)

UNSET = "0001-01-01T00:00:00Z"
UPSTREAM_EVIDENCE = Path("/opt/data/task-secretary/write-design/upstream-evidence-check.json")
RELATIONS = {
    "subtask": "parenttask",
    "parenttask": "subtask",
    "related": "related",
    "duplicateof": "duplicates",
    "duplicates": "duplicateof",
    "blocking": "blocked",
    "blocked": "blocking",
    "precedes": "follows",
    "follows": "precedes",
    "copiedfrom": "copiedto",
    "copiedto": "copiedfrom",
}
API_KINDS_FROM_UPSTREAM_EVIDENCE = {
    "blocked", "blocking", "copiedfrom", "copiedto", "duplicateof", "duplicates",
    "follows", "parenttask", "precedes", "related", "subtask",
}
UI_KINDS_FROM_UPSTREAM_EVIDENCE = API_KINDS_FROM_UPSTREAM_EVIDENCE - {"duplicateof"}


def task_fixture(task_id: int, *, project_id: int = 7) -> dict:
    return {
        "id": task_id,
        "project_id": project_id,
        "title": f"synthetic task {task_id}",
        "description": "preserve this description",
        "done": False,
        "done_at": UNSET,
        "due_date": UNSET,
        "start_date": UNSET,
        "end_date": UNSET,
        "priority": 2,
        "reminders": [],
        "labels": [{"id": 10, "title": "existing"}],
        "related_tasks": {},
        "assignees": [],
        "repeat_after": 0,
        "repeat_mode": 0,
        "hex_color": "",
        "percent_done": 0.0,
        "cover_image_attachment_id": 0,
        "is_favorite": False,
        "position": float(task_id),
        "bucket_id": 0,
        "attachments": [],
    }


class FakeUpstreamHandler(BaseHTTPRequestHandler):
    tasks: dict[int, dict] = {}
    calls: list[tuple[str, str, object]] = []
    mode = ""
    after_write = False
    next_id = 100
    active_writes = 0
    peak_writes = 0
    lock = threading.Lock()

    def log_message(self, *_):
        pass

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def send_json(self, status: int, value: object):
        body = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_raw(self, status: int, body: bytes):
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def track(self, payload=None):
        self.__class__.calls.append((self.command, self.path, copy.deepcopy(payload)))

    @staticmethod
    def materialize_reminders(task: dict) -> None:
        for reminder in task.get("reminders") or []:
            relation = reminder.get("relative_to")
            if relation in {"due_date", "start_date", "end_date"}:
                base = datetime.fromisoformat(task[relation].replace("Z", "+00:00"))
                computed = base + timedelta(seconds=reminder["relative_period"])
                reminder["reminder"] = computed.strftime("%Y-%m-%dT%H:%M:%SZ")

    def do_GET(self):
        self.track()
        path = urlparse(self.path).path
        if path == "/api/v1/labels":
            self.send_json(200, [{"id": 10, "title": "existing"}, {"id": 11, "title": "new"}, {"id": 12, "title": "parallel"}])
            return
        if path == "/api/v1/projects":
            self.send_json(200, [{"id": 7}])
            return
        parts = path.split("/")
        if len(parts) == 5 and parts[:3] == ["", "api", "v1"] and parts[3] == "tasks":
            task_id = int(parts[4])
            if self.__class__.mode == "readback_503" and self.__class__.after_write:
                self.send_json(503, {"message": "synthetic failure"})
                return
            task = self.__class__.tasks.get(task_id)
            if task is None:
                self.send_json(404, {"message": "not found"})
                return
            if self.__class__.mode == "readback_mismatch" and self.__class__.after_write:
                task = copy.deepcopy(task)
                task["title"] = "unexpected server value"
                task["labels"] = [label for label in task["labels"] if label["id"] != 11]
            if self.__class__.mode in {"relation_base_readback_mismatch", "relation_inverse_readback_mismatch"} and self.__class__.after_write:
                task = copy.deepcopy(task)
                relation_kind, related_id = "related", (2 if task_id == 1 else 1)
                mismatch_here = (
                    self.__class__.mode == "relation_base_readback_mismatch" and task_id == 1
                ) or (
                    self.__class__.mode == "relation_inverse_readback_mismatch" and task_id == 2
                )
                if mismatch_here:
                    task["related_tasks"][relation_kind] = [
                        item for item in task["related_tasks"].get(relation_kind, [])
                        if item["id"] != related_id
                    ]
            self.send_json(200, task)
            return
        self.send_json(404, {"message": "not found"})

    def _write_start(self):
        with self.__class__.lock:
            self.__class__.active_writes += 1
            self.__class__.peak_writes = max(self.__class__.peak_writes, self.__class__.active_writes)
        time.sleep(0.025)

    def _write_end(self):
        with self.__class__.lock:
            self.__class__.active_writes -= 1

    def do_PUT(self):
        payload = self.read_json()
        self.track(payload)
        self._write_start()
        try:
            mode = self.__class__.mode
            path = urlparse(self.path).path
            parts = path.split("/")
            if mode == "cross_project_relation_reject" and len(parts) == 6 and parts[:4] == ["", "api", "v1", "tasks"] and parts[5] == "relations":
                base_id, other_id = int(parts[4]), payload["other_task_id"]
                if self.__class__.tasks[base_id]["project_id"] != self.__class__.tasks[other_id]["project_id"]:
                    self.send_json(403, {"message": "synthetic cross-project permission denial"})
                    return
            if mode == "relation_cycle_reject" and len(parts) == 6 and parts[:4] == ["", "api", "v1", "tasks"] and parts[5] == "relations":
                self.send_json(400, {"message": "synthetic relation cycle rejection"})
                return
            if mode == "write_400":
                self.send_json(400, {"message": "synthetic rejection"})
                return
            if mode == "write_500":
                self.send_json(500, {"message": "synthetic failure"})
                return
            if len(parts) == 6 and parts[:4] == ["", "api", "v1", "projects"] and parts[5] == "tasks":
                project_id = int(parts[4])
                task_id = self.__class__.next_id
                self.__class__.next_id += 1
                task = task_fixture(task_id, project_id=project_id)
                task.update(payload)
                self.materialize_reminders(task)
                self.__class__.tasks[task_id] = task
                self.__class__.after_write = True
                if mode == "create_bad_id":
                    self.send_json(201, {"id": -1})
                elif mode == "write_invalid_json":
                    self.send_raw(201, b"not-json")
                else:
                    self.send_json(201, {"id": task_id})
                return
            if len(parts) == 6 and parts[:4] == ["", "api", "v1", "tasks"] and parts[5] == "labels":
                task = self.__class__.tasks[int(parts[4])]
                label_id = payload["label_id"]
                task["labels"] = [label for label in task["labels"] if label["id"] != label_id]
                task["labels"].append({"id": label_id, "title": f"label {label_id}"})
                self.__class__.after_write = True
                if mode == "write_invalid_json":
                    self.send_raw(201, b"not-json")
                else:
                    self.send_json(201, payload)
                return
            if len(parts) == 6 and parts[:4] == ["", "api", "v1", "tasks"] and parts[5] == "relations":
                base_id = int(parts[4])
                other_id = payload["other_task_id"]
                kind = payload["relation_kind"]
                self._set_relation(base_id, other_id, kind, add=True)
                self.__class__.after_write = True
                self.send_json(201, payload)
                return
            self.send_json(404, {"message": "not found"})
        finally:
            self._write_end()

    @classmethod
    def _set_relation(cls, base_id: int, other_id: int, kind: str, *, add: bool):
        inverse = RELATIONS[kind]
        for task_id, relation_kind, related_id in (
            (base_id, kind, other_id), (other_id, inverse, base_id)
        ):
            relation_map = cls.tasks[task_id].setdefault("related_tasks", {})
            related = relation_map.setdefault(relation_kind, [])
            related[:] = [task for task in related if task.get("id") != related_id]
            if add:
                related.append({"id": related_id})

    def do_POST(self):
        payload = self.read_json()
        self.track(payload)
        self._write_start()
        try:
            mode = self.__class__.mode
            if mode == "write_400":
                self.send_json(400, {"message": "synthetic rejection"})
                return
            if mode == "write_500":
                self.send_json(500, {"message": "synthetic failure"})
                return
            task_id = int(urlparse(self.path).path.split("/")[4])
            updated = copy.deepcopy(payload)
            updated["id"] = task_id
            self.materialize_reminders(updated)
            self.__class__.tasks[task_id] = updated
            self.__class__.after_write = True
            if mode == "write_invalid_json":
                self.send_raw(200, b"not-json")
            else:
                self.send_json(200, {"id": task_id})
        finally:
            self._write_end()

    def do_DELETE(self):
        self.track()
        self._write_start()
        try:
            parts = urlparse(self.path).path.split("/")
            if len(parts) == 7 and parts[5] == "labels":
                task_id, label_id = int(parts[4]), int(parts[6])
                task = self.__class__.tasks[task_id]
                task["labels"] = [label for label in task["labels"] if label["id"] != label_id]
                self.__class__.after_write = True
                self.send_json(200, {})
                return
            if len(parts) == 8 and parts[5] == "relations":
                base_id, kind, other_id = int(parts[4]), parts[6], int(parts[7])
                self._set_relation(base_id, other_id, kind, add=False)
                self.__class__.after_write = True
                self.send_json(200, {})
                return
            self.send_json(404, {"message": "not found"})
        finally:
            self._write_end()


class FakeVikunjaClient:
    """Credential-free test client; it talks only to the ephemeral fake upstream."""
    base_url = ""

    def request(self, method: str, path: str, payload=None, query=None):
        from urllib.parse import urlencode
        suffix = "?" + urlencode(query) if query else ""
        body = None if payload is None else json.dumps(payload).encode()
        request = Request(self.base_url + path + suffix, data=body, method=method,
                          headers={"Content-Type": "application/json"} if body else {})
        try:
            with urlopen(request, timeout=3) as response:
                raw = response.read()
                try:
                    data = json.loads(raw.decode()) if raw else {}
                except (UnicodeDecodeError, json.JSONDecodeError):
                    raise adapter.UpstreamError(response.status, "invalid_json") from None
                return response.status, data
        except HTTPError as error:
            raise adapter.UpstreamError(error.code, "http_error") from None


class WriteContractTests(unittest.TestCase):
    def setUp(self):
        FakeUpstreamHandler.tasks = {1: task_fixture(1), 2: task_fixture(2), 3: task_fixture(3)}
        FakeUpstreamHandler.calls = []
        FakeUpstreamHandler.mode = ""
        FakeUpstreamHandler.after_write = False
        FakeUpstreamHandler.next_id = 100
        FakeUpstreamHandler.active_writes = 0
        FakeUpstreamHandler.peak_writes = 0
        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), FakeUpstreamHandler)
        self.upstream_thread = threading.Thread(target=self.upstream.serve_forever, daemon=True)
        self.upstream_thread.start()
        FakeVikunjaClient.base_url = f"http://127.0.0.1:{self.upstream.server_port}"
        self.adapter = ThreadingHTTPServer(("127.0.0.1", 0), adapter.Handler)
        self.adapter_thread = threading.Thread(target=self.adapter.serve_forever, daemon=True)
        self.adapter_thread.start()
        self.factory_patch = patch.object(adapter, "VIKUNJA_CLIENT_FACTORY", FakeVikunjaClient)
        self.factory_patch.start()
        self.addCleanup(self.factory_patch.stop)

    def tearDown(self):
        self.adapter.shutdown()
        self.adapter.server_close()
        self.upstream.shutdown()
        self.upstream.server_close()

    def request(self, method: str, path: str, body=None, *, raw_body: bytes | None = None):
        data = raw_body if raw_body is not None else (None if body is None else json.dumps(body).encode())
        request = Request(f"http://127.0.0.1:{self.adapter.server_port}{path}", data=data,
                          headers={"Content-Type": "application/json"} if data is not None else {},
                          method=method)
        try:
            with urlopen(request, timeout=4) as response:
                payload = response.read()
                return response.status, json.loads(payload.decode()) if payload else {}
        except HTTPError as error:
            payload = error.read()
            return error.code, json.loads(payload.decode()) if payload else {}

    def post(self, path: str, body):
        return self.request("POST", path, body)

    def assert_failure_state(self, response, *, state: str, task_id, operation: str, verification: str):
        self.assertIn("error", response)
        self.assertEqual(response["write_state"], state)
        self.assertEqual(response["task_id"], task_id)
        self.assertEqual(response["operation"], operation)
        self.assertEqual(response["verification"], verification)

    def test_label_catalog_get_maps_to_upstream_with_only_supported_query(self):
        status, labels = self.request("GET", "/labels?page=2&per_page=20&s=project")
        self.assertEqual(status, 200)
        self.assertEqual([label["id"] for label in labels], [10, 11, 12])
        self.assertEqual(FakeUpstreamHandler.calls[-1][:2], ("GET", "/api/v1/labels?page=2&per_page=20&s=project"))

    def test_create_is_verified_by_task_get_and_returns_created_task(self):
        status, result = self.post("/tasks", {"project_id": 7, "title": "synthetic new", "priority": 0, "description": ""})
        self.assertEqual(status, 201)
        self.assertEqual(result["id"], 100)
        self.assertEqual(result["title"], "synthetic new")
        self.assertEqual(result["priority"], 0)
        self.assertEqual(result["description"], "")
        self.assertEqual([call[0] for call in FakeUpstreamHandler.calls], ["PUT", "GET"])
        self.assertEqual(FakeUpstreamHandler.calls[0][1], "/api/v1/projects/7/tasks")

    def test_create_rejects_reversed_dates_before_client_and_accepts_equal_or_ordered_dates(self):
        payload = {
            "project_id": 7,
            "title": "synthetic dated create",
            "start_date": "2027-01-03T00:00:00Z",
            "end_date": "2027-01-02T00:00:00Z",
        }
        with patch.object(adapter, "VIKUNJA_CLIENT_FACTORY",
                          side_effect=AssertionError("client constructed")) as factory:
            status, response = self.post("/tasks", payload)
            self.assertEqual(status, 400)
            self.assertEqual(response["write_state"], "not_attempted")
            factory.assert_not_called()
        self.assertEqual(FakeUpstreamHandler.calls, [])

        for start_date, end_date in (
            ("2027-01-02T00:00:00Z", "2027-01-02T00:00:00Z"),
            ("2027-01-02T00:00:00Z", "2027-01-03T00:00:00Z"),
        ):
            with self.subTest(start_date=start_date, end_date=end_date):
                status, result = self.post("/tasks", {
                    "project_id": 7,
                    "title": "synthetic dated create",
                    "start_date": start_date,
                    "end_date": end_date,
                })
                self.assertEqual(status, 201)
                self.assertEqual(result["start_date"], start_date)
                self.assertEqual(result["end_date"], end_date)

    def test_update_preserves_unrelated_mutable_fields_and_explicit_zero_values(self):
        before = copy.deepcopy(FakeUpstreamHandler.tasks[1])
        status, result = self.post("/tasks/1", {"title": "changed", "priority": 0, "description": ""})
        self.assertEqual(status, 200)
        self.assertEqual(result["title"], "changed")
        self.assertEqual(result["priority"], 0)
        self.assertEqual(result["description"], "")
        for field in ("done", "project_id", "assignees", "repeat_after", "repeat_mode", "hex_color",
                      "percent_done", "cover_image_attachment_id", "position", "bucket_id", "labels", "related_tasks"):
            self.assertEqual(result[field], before[field], field)
        self.assertEqual([call[0] for call in FakeUpstreamHandler.calls], ["GET", "POST", "GET"])

    def test_date_input_is_normalized_and_null_clears(self):
        status, result = self.post("/tasks/1", {"due_date": "2027-01-02T03:04:05+03:00"})
        self.assertEqual(status, 200)
        self.assertEqual(result["due_date"], "2027-01-02T00:04:05Z")
        self.assertEqual(FakeUpstreamHandler.calls[1][2]["due_date"], "2027-01-02T00:04:05Z")
        status, result = self.post("/tasks/1", {"due_date": None})
        self.assertEqual(status, 200)
        self.assertEqual(result["due_date"], UNSET)

    def test_zero_instant_offsets_are_rejected_before_client_and_year_is_four_digits(self):
        for value in ("0001-01-01T00:00:00+00:00", "0001-01-01T01:00:00+01:00"):
            with self.subTest(value=value):
                with patch.object(adapter, "VIKUNJA_CLIENT_FACTORY",
                                  side_effect=AssertionError("client constructed")) as factory:
                    status, response = self.post("/tasks/1", {"due_date": value})
                    self.assertEqual(status, 400)
                    self.assertEqual(response["write_state"], "not_attempted")
                    factory.assert_not_called()
        self.assertEqual(adapter.format_datetime(datetime(1, 1, 1, tzinfo=adapter.timezone.utc)),
                         "0001-01-01T00:00:00Z")

    def test_out_of_range_timezone_normalization_is_400_before_client(self):
        for value in ("0001-01-01T00:00:00+00:01", "9999-12-31T23:59:59-00:01"):
            with self.subTest(value=value):
                with patch.object(adapter, "VIKUNJA_CLIENT_FACTORY",
                                  side_effect=AssertionError("client constructed")) as factory:
                    status, response = self.post("/tasks/1", {"due_date": value})
                    self.assertEqual(status, 400)
                    self.assertEqual(response["write_state"], "not_attempted")
                    factory.assert_not_called()
        self.assertEqual(FakeUpstreamHandler.calls, [])

    def test_omitted_fields_are_preserved_and_start_end_are_ordered(self):
        FakeUpstreamHandler.tasks[1]["start_date"] = "2027-01-02T00:00:00Z"
        FakeUpstreamHandler.tasks[1]["end_date"] = "2027-01-03T00:00:00Z"
        status, result = self.post("/tasks/1", {"title": "keep dates"})
        self.assertEqual(status, 200)
        self.assertEqual(result["start_date"], "2027-01-02T00:00:00Z")
        status, response = self.post("/tasks/1", {"start_date": "2027-01-04T00:00:00Z"})
        self.assertEqual(status, 400)
        self.assertEqual(response["write_state"], "not_attempted")

    def test_create_and_update_validate_body_fields_before_constructing_client(self):
        self.factory_patch.stop()
        forbidden_factory = patch.object(adapter, "VIKUNJA_CLIENT_FACTORY", side_effect=AssertionError("client constructed"))
        forbidden_factory.start()
        try:
            cases = [
                ("/tasks", {"project_id": 7, "title": "x", "done": True}),
                ("/tasks", {"project_id": 7, "title": "x", "labels": []}),
                ("/tasks", {"project_id": 7, "title": "x", "related_tasks": {}}),
                ("/tasks/1", {"done": True}),
                ("/tasks/1", {"project_id": 9}),
                ("/tasks/1", {"assignees": []}),
                ("/tasks/1", {"repeat_after": 1}),
                ("/tasks/1", {"is_favorite": True}),
                ("/tasks/1", {"position": 5}),
            ]
            for path, payload in cases:
                with self.subTest(path=path, payload=payload):
                    status, response = self.post(path, payload)
                    self.assertEqual(status, 400)
                    self.assertEqual(response["write_state"], "not_attempted")
        finally:
            forbidden_factory.stop()
            self.factory_patch.start()

    def test_unknown_and_denial_routes_do_not_construct_client(self):
        self.factory_patch.stop()
        forbidden_factory = patch.object(adapter, "VIKUNJA_CLIENT_FACTORY", side_effect=AssertionError("client constructed"))
        forbidden_factory.start()
        try:
            for path in ("/tasks/1/complete", "/tasks/1/duplicate", "/projects/7", "/tasks/bulk"):
                status, result = self.post(path, {})
                self.assertIn(status, (404, 405))
                self.assertEqual(result["write_state"], "not_attempted")
        finally:
            forbidden_factory.stop()
            self.factory_patch.start()

    def test_disallowed_http_mutation_methods_never_reach_upstream(self):
        for method in ("PUT", "PATCH", "DELETE"):
            status, result = self.request(method, "/tasks/1", {})
            self.assertEqual(status, 405)
            self.assertEqual(result["write_state"], "not_attempted")
        self.assertEqual(FakeUpstreamHandler.calls, [])

    def test_rejects_duplicate_json_keys_nonfinite_and_non_object_bodies(self):
        cases = [b'{"project_id":7,"title":"a","title":"b"}', b'{"project_id":7,"title":NaN}', b'[]']
        for raw in cases:
            status, result = self.request("POST", "/tasks", raw_body=raw)
            self.assertEqual(status, 400)
            self.assertEqual(result["write_state"], "not_attempted")
        self.assertEqual(FakeUpstreamHandler.calls, [])

    def test_rejects_invalid_utf8_truncated_and_oversized_request_bodies(self):
        for raw in (b"\xff", b'{"project_id":7,"title":"x"'):
            status, result = self.request("POST", "/tasks", raw_body=raw)
            self.assertEqual(status, 400)
            self.assertEqual(result["write_state"], "not_attempted")
        request = Request(f"http://127.0.0.1:{self.adapter.server_port}/tasks", data=b"{}", method="POST",
                          headers={"Content-Type": "application/json", "Content-Length": str(adapter.MAX_BODY_BYTES + 1)})
        try:
            with urlopen(request, timeout=4):
                self.fail("oversized request unexpectedly succeeded")
        except HTTPError as error:
            self.assertEqual(error.code, 400)
            result = json.loads(error.read())
            self.assertEqual(result["write_state"], "not_attempted")
        self.assertEqual(FakeUpstreamHandler.calls, [])

    def test_strict_id_validation_and_integer_bounds(self):
        for path in ("/tasks/0", "/tasks/01", "/tasks/+1", "/tasks/-1", "/tasks/9223372036854775808"):
            status, result = self.post(path, {"title": "x"})
            self.assertIn(status, (400, 404))
            self.assertEqual(result["write_state"], "not_attempted")
        for payload in ({"project_id": True, "title": "x"}, {"project_id": 1.5, "title": "x"},
                        {"project_id": 9223372036854775808, "title": "x"}):
            status, result = self.post("/tasks", payload)
            self.assertEqual(status, 400)
            self.assertEqual(result["write_state"], "not_attempted")
        self.assertEqual(FakeUpstreamHandler.calls, [])

    def test_oversized_path_id_is_http_400_before_client_or_upstream(self):
        with patch.object(adapter, "VIKUNJA_CLIENT_FACTORY",
                          side_effect=AssertionError("client constructed")) as factory:
            status, response = self.post(f"/tasks/{'9' * 5000}/labels/add", {"label_id": 11})
            self.assertEqual(status, 400)
            self.assertEqual(response["write_state"], "not_attempted")
            factory.assert_not_called()
        self.assertEqual(FakeUpstreamHandler.calls, [])

    def test_priority_title_description_limits_and_empty_values(self):
        for value in (True, -1, 6, 1.5):
            status, _ = self.post("/tasks/1", {"priority": value})
            self.assertEqual(status, 400)
        for payload in ({"title": "   "}, {"title": "x" * (adapter.MAX_TITLE_LENGTH + 1)},
                        {"description": "x" * (adapter.MAX_DESCRIPTION_LENGTH + 1)}):
            status, _ = self.post("/tasks/1", payload)
            self.assertEqual(status, 400)
        status, result = self.post("/tasks/1", {"priority": 0, "description": ""})
        self.assertEqual(status, 200)
        self.assertEqual((result["priority"], result["description"]), (0, ""))

    def test_strict_rfc3339_dates_accept_offsets_and_reject_noncanonical_values(self):
        invalid = ["2027-01-02", "2027-01-02T03:04:05", "2027-01-02T03:04:05.1Z",
                   "2027-01-02T03:04Z", "2027-02-30T03:04:05Z", "0001-01-01T00:00:00Z",
                   "2027-01-02T03:04:05 UTC", "2027-01-02T03:04:05+25:00"]
        for value in invalid:
            with self.subTest(value=value):
                status, _ = self.post("/tasks/1", {"due_date": value})
                self.assertEqual(status, 400)
        for value in ("2027-01-02T03:04:05Z", "2027-01-02T03:04:05-05:30"):
            status, _ = self.post("/tasks/1", {"due_date": value})
            self.assertEqual(status, 200)

    def test_date_readback_compares_full_subsecond_instants(self):
        task = task_fixture(1)
        self.assertTrue(adapter.field_equal(
            "due_date", "2027-01-02T02:00:00.100+02:00", "2027-01-02T00:00:00.100Z", task
        ))
        self.assertFalse(adapter.field_equal(
            "due_date", "2027-01-02T00:00:00.100Z", "2027-01-02T00:00:00.900Z", task
        ))

    def test_unrelated_update_preserves_existing_fractional_absolute_reminders(self):
        FakeUpstreamHandler.tasks[1]["reminders"] = [{
            "reminder": "2027-01-03T03:00:00.500+03:00", "relative_to": "", "relative_period": 0,
        }]
        status, _ = self.post("/tasks/1", {"title": "Preserved reminder"})
        self.assertEqual(status, 200)
        writes = [payload for method, path, payload in FakeUpstreamHandler.calls
                  if method == "POST" and path == "/api/v1/tasks/1"]
        self.assertTrue(writes)
        written = writes[0]
        assert isinstance(written, dict)
        reminders = written["reminders"]
        assert isinstance(reminders, list) and reminders
        reminder = reminders[0]
        assert isinstance(reminder, dict)
        self.assertEqual(reminder["reminder"], "2027-01-03T00:00:00.5Z")

    def test_relative_and_absolute_reminders_are_normalized_and_unordered(self):
        FakeUpstreamHandler.tasks[1]["due_date"] = "2027-01-02T00:00:00Z"
        reminders = [
            {"relative_to": "due_date", "relative_period": -60},
            {"reminder": "2027-01-03T00:00:00+00:00"},
        ]
        status, result = self.post("/tasks/1", {"reminders": reminders})
        self.assertEqual(status, 200)
        self.assertEqual(len(result["reminders"]), 2)
        self.assertCountEqual([item["relative_to"] for item in result["reminders"]], ["due_date", ""])
        wire_reminders = FakeUpstreamHandler.calls[1][2]["reminders"]
        self.assertEqual(wire_reminders[0]["reminder"], UNSET)
        self.assertEqual(wire_reminders[1]["reminder"], "2027-01-03T00:00:00Z")

    def test_reminder_clear_and_omission_semantics(self):
        FakeUpstreamHandler.tasks[1]["reminders"] = [{"reminder": "2027-01-02T00:00:00Z", "relative_to": "", "relative_period": 0}]
        status, result = self.post("/tasks/1", {"title": "preserve reminder"})
        self.assertEqual(status, 200)
        self.assertEqual(len(result["reminders"]), 1)
        status, result = self.post("/tasks/1", {"reminders": []})
        self.assertEqual(status, 200)
        self.assertEqual(result["reminders"], [])

    def test_reminder_wire_alias_and_bad_shapes_are_rejected_before_client(self):
        self.factory_patch.stop()
        forbidden_factory = patch.object(adapter, "VIKUNJA_CLIENT_FACTORY",
                                         side_effect=AssertionError("client constructed"))
        forbidden_factory.start()
        try:
            cases = [
                [{"reminder": "2027-01-02T00:00:00Z", "relative_to": "", "relative_period": 0}],
                [{"reminder": "2027-01-02T00:00:00Z"}, {"reminder": "2027-01-02T01:00:00+01:00"}],
                [{"relative_to": "due_date", "relative_period": True}],
            ]
            for reminders in cases:
                with self.subTest(reminders=reminders):
                    status, result = self.post("/tasks/1", {"reminders": reminders})
                    self.assertEqual(status, 400)
                    self.assertEqual(result["write_state"], "not_attempted")
        finally:
            forbidden_factory.stop()
            self.factory_patch.start()
        self.assertEqual(FakeUpstreamHandler.calls, [])

    def test_create_relative_reminder_without_base_fails_before_client(self):
        self.factory_patch.stop()
        try:
            with patch.object(adapter, "VIKUNJA_CLIENT_FACTORY",
                              side_effect=AssertionError("client constructed")) as factory:
                status, response = self.post("/tasks", {
                    "project_id": 7,
                    "title": "synthetic create",
                    "reminders": [{"relative_to": "due_date", "relative_period": 0}],
                })
                self.assertEqual(status, 400)
                self.assertEqual(response["write_state"], "not_attempted")
                factory.assert_not_called()
        finally:
            self.factory_patch.start()
        self.assertEqual(FakeUpstreamHandler.calls, [])

    def test_missing_existing_reminders_schema_fails_closed_before_write(self):
        del FakeUpstreamHandler.tasks[1]["reminders"]
        status, result = self.post("/tasks/1", {"title": "must not write"})
        self.assertEqual(status, 502)
        self.assertEqual(result["write_state"], "not_attempted")
        self.assertEqual(sum(call[0] == "POST" for call in FakeUpstreamHandler.calls), 0)

    def test_reminder_array_bounds_schema_duplicate_instants_and_unset_bases(self):
        invalid_cases = [
            None,
            [{"reminder": "2027-01-02T00:00:00Z", "unexpected": 1}],
            [{"reminder": "2027-01-02T00:00:00Z"}, {"reminder": "2027-01-02T01:00:00+01:00"}],
            [{"relative_to": "due_date", "relative_period": True}],
            [{"relative_to": "due_date", "relative_period": 31536001}],
            [{"relative_to": "due_date", "relative_period": -31536001}],
            [{"relative_to": "other", "relative_period": 0}],
            [{"relative_to": "due_date", "relative_period": 0, "reminder": "2027-01-02T00:00:00Z"}],
            [{"reminder": "0001-01-01T00:00:00Z"}],
            [{"reminder": "2027-01-02T00:00:00Z"}] * 33,
        ]
        for value in invalid_cases:
            with self.subTest(value=value if len(str(value)) < 100 else "large"):
                status, _ = self.post("/tasks/1", {"reminders": value})
                self.assertEqual(status, 400)
        for seconds in (-31536000, -1, 0, 1, 31536000):
            FakeUpstreamHandler.tasks[1]["due_date"] = "2027-01-02T00:00:00Z"
            status, _ = self.post("/tasks/1", {"reminders": [{"relative_to": "due_date", "relative_period": seconds}]})
            self.assertEqual(status, 200)
        FakeUpstreamHandler.tasks[1]["due_date"] = UNSET
        status, response = self.post("/tasks/1", {"reminders": [{"relative_to": "due_date", "relative_period": 0}]})
        self.assertEqual(status, 400)
        self.assertEqual(response["write_state"], "not_attempted")

    def test_clearing_reminder_base_requires_explicit_reminder_clear(self):
        FakeUpstreamHandler.tasks[1]["due_date"] = "2027-01-02T00:00:00Z"
        FakeUpstreamHandler.tasks[1]["reminders"] = [{"reminder": "2027-01-02T00:00:00Z", "relative_to": "due_date", "relative_period": 0}]
        status, response = self.post("/tasks/1", {"due_date": None})
        self.assertEqual(status, 400)
        self.assertEqual(response["write_state"], "not_attempted")
        self.assertEqual(len(FakeUpstreamHandler.calls), 1)
        status, result = self.post("/tasks/1", {"due_date": None, "reminders": []})
        self.assertEqual(status, 200)
        self.assertEqual(result["due_date"], UNSET)
        self.assertEqual(result["reminders"], [])

    def test_label_association_add_remove_are_readback_verified_and_noop_safe(self):
        status, result = self.post("/tasks/1/labels/add", {"label_id": 11})
        self.assertEqual(status, 200)
        self.assertEqual({item["id"] for item in result["labels"]}, {10, 11})
        self.assertEqual([call[0] for call in FakeUpstreamHandler.calls], ["GET", "GET", "PUT", "GET"])
        prior_calls = len(FakeUpstreamHandler.calls)
        status, _ = self.post("/tasks/1/labels/add", {"label_id": 11})
        self.assertEqual(status, 200)
        self.assertEqual(len(FakeUpstreamHandler.calls), prior_calls + 1)
        status, result = self.post("/tasks/1/labels/remove", {"label_id": 11})
        self.assertEqual(status, 200)
        self.assertEqual([item["id"] for item in result["labels"]], [10])
        self.assertEqual(FakeUpstreamHandler.calls[-2][0], "DELETE")

    def test_label_payload_must_be_exact_and_positive_id(self):
        for payload in ({"label_id": True}, {"label_id": 0}, {"label_id": 1.5}, {"label_id": 11, "labels": []}):
            status, response = self.post("/tasks/1/labels/add", payload)
            self.assertEqual(status, 400)
            self.assertEqual(response["write_state"], "not_attempted")
        self.assertEqual(FakeUpstreamHandler.calls, [])

    def test_api_and_ui_relation_kind_sets_match_frozen_upstream_evidence(self):
        if UPSTREAM_EVIDENCE.is_file():
            evidence = json.loads(UPSTREAM_EVIDENCE.read_text(encoding="utf-8"))
            api_kinds = set(evidence["api_kinds"])
            backend_kinds = set(evidence["backend_kinds"])
            ui_kinds = set(evidence["ui_kinds"])
            self.assertEqual(len(api_kinds), evidence["api_count"])
            self.assertEqual(len(ui_kinds), evidence["ui_count"])
            self.assertEqual(api_kinds - ui_kinds, set(evidence["ui_missing"]))
            self.assertEqual(backend_kinds, api_kinds)
        else:
            # Keep offline tests usable when the external D1 evidence bundle is absent.
            api_kinds = API_KINDS_FROM_UPSTREAM_EVIDENCE
            ui_kinds = UI_KINDS_FROM_UPSTREAM_EVIDENCE
        self.assertEqual(set(adapter.RELATION_INVERSES), api_kinds)
        self.assertEqual(set(adapter.UI_RELATION_KINDS), ui_kinds)
        self.assertEqual(len(api_kinds), 11)
        self.assertEqual(len(ui_kinds), 10)

    def test_every_api_relation_kind_adds_and_verifies_inverse(self):
        for kind in sorted(API_KINDS_FROM_UPSTREAM_EVIDENCE):
            with self.subTest(kind=kind):
                FakeUpstreamHandler.calls = []
                FakeUpstreamHandler.tasks[1] = task_fixture(1)
                FakeUpstreamHandler.tasks[2] = task_fixture(2)
                status, result = self.post("/tasks/1/relations/add", {"other_task_id": 2, "relation_kind": kind})
                self.assertEqual(status, 200)
                self.assertEqual(result["related_tasks"][kind][0]["id"], 2)
                other = FakeUpstreamHandler.tasks[2]["related_tasks"]
                self.assertEqual(other[RELATIONS[kind]][0]["id"], 1)
                self.assertEqual([call[0] for call in FakeUpstreamHandler.calls], ["GET", "GET", "PUT", "GET", "GET"])

    def test_relation_rejects_unknown_alias_self_and_partial_pair(self):
        for kind in ("unknown", "blocked_by", "duplicate_of", "parent", "api"):
            status, response = self.post("/tasks/1/relations/add", {"other_task_id": 2, "relation_kind": kind})
            self.assertEqual(status, 400)
            self.assertEqual(response["write_state"], "not_attempted")
        status, response = self.post("/tasks/1/relations/add", {"other_task_id": 1, "relation_kind": "related"})
        self.assertEqual(status, 400)
        self.assertEqual(response["write_state"], "not_attempted")
        FakeUpstreamHandler.tasks[1]["related_tasks"] = {"related": [{"id": 2}]}
        status, response = self.post("/tasks/1/relations/add", {"other_task_id": 2, "relation_kind": "related"})
        self.assertEqual(status, 409)
        self.assertEqual(response["write_state"], "not_attempted")
        self.assertEqual(FakeUpstreamHandler.calls[-2:], [
            ("GET", "/api/v1/tasks/1", None), ("GET", "/api/v1/tasks/2", None)
        ])

    def test_cross_project_relation_permission_denial_is_rejected_without_retry(self):
        FakeUpstreamHandler.tasks[2]["project_id"] = 8
        FakeUpstreamHandler.mode = "cross_project_relation_reject"
        status, response = self.post("/tasks/1/relations/add", {"other_task_id": 2, "relation_kind": "related"})
        self.assertEqual(status, 502)
        self.assert_failure_state(response, state="rejected", task_id=1,
                                  operation="tasks.relations.add", verification="not_run")
        relation_writes = [call for call in FakeUpstreamHandler.calls if call[1].endswith("/relations")]
        self.assertEqual(len(relation_writes), 1)
        self.assertEqual([call[0] for call in FakeUpstreamHandler.calls], ["GET", "GET", "PUT"])

    def test_upstream_relation_cycle_rejection_is_rejected_without_retry(self):
        FakeUpstreamHandler.tasks[1]["related_tasks"] = {"subtask": [{"id": 2}]}
        FakeUpstreamHandler.tasks[2]["related_tasks"] = {"subtask": [{"id": 3}], "parenttask": [{"id": 1}]}
        FakeUpstreamHandler.tasks[3]["related_tasks"] = {"parenttask": [{"id": 2}]}
        FakeUpstreamHandler.mode = "relation_cycle_reject"
        status, response = self.post("/tasks/3/relations/add", {"other_task_id": 1, "relation_kind": "subtask"})
        self.assertEqual(status, 502)
        self.assert_failure_state(response, state="rejected", task_id=3,
                                  operation="tasks.relations.add", verification="not_run")
        relation_writes = [call for call in FakeUpstreamHandler.calls if call[1].endswith("/relations")]
        self.assertEqual(len(relation_writes), 1)
        self.assertEqual([call[0] for call in FakeUpstreamHandler.calls], ["GET", "GET", "PUT"])

    def test_relation_remove_deletes_only_pair_and_verifies_both_sides(self):
        FakeUpstreamHandler._set_relation(1, 2, "blocking", add=True)
        FakeUpstreamHandler.tasks[1]["related_tasks"].setdefault("related", []).append({"id": 3})
        status, result = self.post("/tasks/1/relations/remove", {"other_task_id": 2, "relation_kind": "blocking"})
        self.assertEqual(status, 200)
        self.assertEqual(result["related_tasks"]["related"][0]["id"], 3)
        self.assertNotIn(("blocking", 2), adapter.relation_pairs(result))
        self.assertEqual(adapter.relation_pairs(FakeUpstreamHandler.tasks[2]), set())
        self.assertEqual(FakeUpstreamHandler.calls[2][0], "DELETE")

    def test_partial_write_failures_report_state_and_never_retry(self):
        scenarios = [
            ("write_400", "rejected", 1, "tasks.update", "not_run", 1),
            ("write_500", "unknown", 1, "tasks.update", "not_run", 1),
            ("write_invalid_json", "unknown", 1, "tasks.update", "not_run", 1),
            ("readback_503", "applied_unverified", 1, "tasks.update", "unavailable", 1),
            ("readback_mismatch", "applied_unverified", 1, "tasks.update", "failed", 1),
        ]
        for mode, state, task_id, operation, verification, expected_writes in scenarios:
            with self.subTest(mode=mode):
                FakeUpstreamHandler.calls = []
                FakeUpstreamHandler.mode = mode
                FakeUpstreamHandler.after_write = False
                status, response = self.post("/tasks/1", {"title": "new title"})
                self.assertGreaterEqual(status, 400)
                self.assert_failure_state(response, state=state, task_id=task_id, operation=operation, verification=verification)
                self.assertEqual(sum(call[0] == "POST" for call in FakeUpstreamHandler.calls), expected_writes)
        FakeUpstreamHandler.mode = ""

    def test_create_invalid_id_and_unverified_create_keep_known_state(self):
        FakeUpstreamHandler.mode = "create_bad_id"
        status, response = self.post("/tasks", {"project_id": 7, "title": "new"})
        self.assertEqual(status, 502)
        self.assert_failure_state(response, state="unknown", task_id=None, operation="tasks.create", verification="not_run")
        self.assertEqual(sum(call[0] == "PUT" for call in FakeUpstreamHandler.calls), 1)
        FakeUpstreamHandler.mode = "readback_503"
        FakeUpstreamHandler.after_write = False
        status, response = self.post("/tasks", {"project_id": 7, "title": "new"})
        self.assertEqual(status, 503)
        self.assert_failure_state(response, state="applied_unverified", task_id=101, operation="tasks.create", verification="unavailable")

    def test_label_and_relation_readback_mismatch_is_applied_unverified(self):
        FakeUpstreamHandler.mode = "readback_mismatch"
        status, response = self.post("/tasks/1/labels/add", {"label_id": 11})
        self.assertEqual(status, 502)
        self.assert_failure_state(response, state="applied_unverified", task_id=1, operation="tasks.labels.add", verification="failed")
        self.assertEqual(sum(call[0] == "PUT" for call in FakeUpstreamHandler.calls), 1)

    def test_relation_readback_mismatch_on_either_side_is_applied_unverified(self):
        for mode, mismatched_task_id in (
            ("relation_base_readback_mismatch", 1),
            ("relation_inverse_readback_mismatch", 2),
        ):
            with self.subTest(mode=mode):
                FakeUpstreamHandler.tasks[1] = task_fixture(1)
                FakeUpstreamHandler.tasks[2] = task_fixture(2)
                FakeUpstreamHandler.calls = []
                FakeUpstreamHandler.mode = mode
                FakeUpstreamHandler.after_write = False
                status, response = self.post("/tasks/1/relations/add", {
                    "other_task_id": 2,
                    "relation_kind": "related",
                })
                self.assertEqual(status, 502)
                self.assert_failure_state(response, state="applied_unverified", task_id=1,
                                          operation="tasks.relations.add", verification="failed")
                self.assertEqual([call[1] for call in FakeUpstreamHandler.calls if call[0] == "GET"], [
                    "/api/v1/tasks/1", "/api/v1/tasks/2", "/api/v1/tasks/1", "/api/v1/tasks/2",
                ])
                self.assertEqual(sum(call[0] == "PUT" for call in FakeUpstreamHandler.calls), 1)
                expected = {"id": 2 if mismatched_task_id == 1 else 1}
                self.assertEqual(FakeUpstreamHandler.tasks[mismatched_task_id]["related_tasks"]["related"], [expected])

    def test_mutations_are_serialized_across_handler_threads(self):
        failures = []
        def add_label(task_id, label_id):
            status, response = self.post(f"/tasks/{task_id}/labels/add", {"label_id": label_id})
            if status != 200:
                failures.append(response)
        threads = [threading.Thread(target=add_label, args=(1, 11)),
                   threading.Thread(target=add_label, args=(2, 12))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        self.assertFalse(failures)
        self.assertEqual(FakeUpstreamHandler.peak_writes, 1)

    def test_failure_payloads_never_echo_task_text_or_credentials(self):
        secret_text = "private-title-must-not-appear"
        FakeUpstreamHandler.mode = "write_500"
        status, response = self.post("/tasks/1", {"title": secret_text})
        self.assertEqual(status, 502)
        serialized = json.dumps(response)
        self.assertNotIn(secret_text, serialized)
        self.assertNotIn("Bearer", serialized)
        self.assertNotIn("token", serialized.lower())


if __name__ == "__main__":
    unittest.main()
