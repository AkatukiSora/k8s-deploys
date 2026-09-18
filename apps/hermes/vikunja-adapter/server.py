#!/usr/bin/env python3
"""Loopback-only, bounded Vikunja v1 task adapter.

The Hermes container never receives the Vikunja bearer token. This sidecar is
the only token consumer and exposes only the secretary task operations below.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen

LIST_QUERY_KEYS = {"page", "per_page", "s", "sort_by", "order_by", "filter_by", "filter_value", "filter_comparator"}
TASK_FIELDS = {"title", "description", "due_date", "start_date", "end_date", "priority", "done"}
MAX_BODY_BYTES = 32 * 1024
MAX_TITLE_LENGTH = 512
MAX_DESCRIPTION_LENGTH = 16 * 1024
ID_RE = re.compile(r"^[1-9][0-9]*$")


class AdapterError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class VikunjaClient:
    def __init__(self) -> None:
        base_url = os.environ.get("VIKUNJA_BASE_URL", "").rstrip("/")
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or parsed.netloc != "vikunja.akatuki-host.com" or parsed.path:
            raise RuntimeError("VIKUNJA_BASE_URL must be https://vikunja.akatuki-host.com")
        token_path = Path(os.environ.get("VIKUNJA_TOKEN_FILE", "/var/run/vikunja-api/token"))
        token = token_path.read_text(encoding="utf-8").strip()
        if not token:
            raise RuntimeError("Vikunja token file is empty")
        self.base_url = base_url
        self.token = token

    def request(self, method: str, path: str, payload: dict | None = None, query: dict[str, str] | None = None) -> tuple[int, object]:
        if not path.startswith("/api/v1/"):
            raise RuntimeError("invalid upstream path")
        url = f"{self.base_url}{path}"
        if query:
            from urllib.parse import urlencode
            url = f"{url}?{urlencode(query)}"
        body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=10) as response:
                raw = response.read(MAX_BODY_BYTES + 1)
                if len(raw) > MAX_BODY_BYTES:
                    raise AdapterError(502, "upstream response exceeded size limit")
                return response.status, json.loads(raw.decode("utf-8")) if raw else {}
        except HTTPError as error:
            logging.info("vikunja request failed method=%s path=%s status=%s", method, path, error.code)
            raise AdapterError(502 if error.code >= 500 else 400, f"Vikunja request failed (HTTP {error.code})") from error
        except (URLError, TimeoutError, OSError) as error:
            logging.info("vikunja request unavailable method=%s path=%s reason=%s", method, path, error)
            raise AdapterError(503, "Vikunja is unavailable") from error
        except json.JSONDecodeError as error:
            raise AdapterError(502, "Vikunja returned invalid JSON") from error


def parse_id(value: str, name: str) -> int:
    if not ID_RE.fullmatch(value):
        raise AdapterError(400, f"{name} must be a positive integer")
    return int(value)


def validate_datetime(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise AdapterError(400, f"{field} must be an ISO 8601 timestamp")
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise AdapterError(400, f"{field} must be an ISO 8601 timestamp") from error
    if parsed.tzinfo is None:
        raise AdapterError(400, f"{field} must include a timezone")
    return value


def validate_task_fields(payload: object, create: bool) -> dict:
    if not isinstance(payload, dict):
        raise AdapterError(400, "request body must be a JSON object")
    allowed = TASK_FIELDS | ({"project_id"} if create else set())
    unexpected = set(payload) - allowed
    if unexpected:
        raise AdapterError(400, f"unsupported task field: {sorted(unexpected)[0]}")
    if create and "project_id" not in payload:
        raise AdapterError(400, "project_id is required")
    if create and "title" not in payload:
        raise AdapterError(400, "title is required")
    if not create and not payload:
        raise AdapterError(400, "at least one mutable task field is required")

    validated: dict = {}
    for field, value in payload.items():
        if field == "project_id":
            if type(value) is not int or value <= 0:
                raise AdapterError(400, "project_id must be a positive integer")
        elif field == "title":
            if not isinstance(value, str) or not value.strip() or len(value) > MAX_TITLE_LENGTH:
                raise AdapterError(400, "title must be a non-empty string within the length limit")
        elif field == "description":
            if not isinstance(value, str) or len(value) > MAX_DESCRIPTION_LENGTH:
                raise AdapterError(400, "description exceeds the length limit")
        elif field in {"due_date", "start_date", "end_date"}:
            value = validate_datetime(value, field)
        elif field == "priority":
            if type(value) is not int or not 0 <= value <= 5:
                raise AdapterError(400, "priority must be an integer between 0 and 5")
        elif field == "done":
            if not isinstance(value, bool):
                raise AdapterError(400, "done must be a boolean")
        validated[field] = value
    return validated


class Handler(BaseHTTPRequestHandler):
    server_version = "hermes-vikunja-adapter/1"

    def log_message(self, format: str, *args: object) -> None:
        logging.info("adapter %s", format % args)

    def send_json(self, status: int, data: object) -> None:
        encoded = json.dumps(data, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def read_body(self) -> dict:
        length = self.headers.get("Content-Length")
        if length is None or not length.isdigit() or int(length) > MAX_BODY_BYTES:
            raise AdapterError(400, "invalid request body length")
        try:
            return json.loads(self.rfile.read(int(length)).decode("utf-8"))
        except json.JSONDecodeError as error:
            raise AdapterError(400, "request body must be valid JSON") from error

    def client(self) -> VikunjaClient:
        try:
            return VikunjaClient()
        except (OSError, RuntimeError) as error:
            logging.error("adapter is not configured: %s", error)
            raise AdapterError(503, "Vikunja adapter is not configured") from error

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self.send_json(200, {"status": "ok"})
                return
            client = self.client()
            if parsed.path == "/ready":
                _, projects = client.request("GET", "/api/v1/projects")
                project_count = len(projects) if isinstance(projects, list) else None
                self.send_json(200, {"status": "ready", "project_count": project_count})
                return
            if parsed.path == "/projects":
                _, data = client.request("GET", "/api/v1/projects", query=self.allowed_query(parsed.query))
                self.send_json(200, data)
                return
            if parsed.path == "/tasks":
                _, data = client.request("GET", "/api/v1/tasks", query=self.allowed_query(parsed.query))
                self.send_json(200, data)
                return
            match = re.fullmatch(r"/tasks/([1-9][0-9]*)", parsed.path)
            if match:
                _, data = client.request("GET", f"/api/v1/tasks/{match.group(1)}")
                self.send_json(200, data)
                return
            raise AdapterError(404, "route not found")
        except AdapterError as error:
            self.send_json(error.status, {"error": error.message})

    def allowed_query(self, query: str) -> dict[str, str]:
        parsed = parse_qs(query, keep_blank_values=False)
        if set(parsed) - LIST_QUERY_KEYS or any(len(values) != 1 for values in parsed.values()):
            raise AdapterError(400, "unsupported query parameter")
        return {key: values[0] for key, values in parsed.items()}

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            client = self.client()
            if parsed.path == "/tasks":
                payload = validate_task_fields(self.read_body(), create=True)
                project_id = payload.pop("project_id")
                _, created = client.request("PUT", f"/api/v1/projects/{project_id}/tasks", payload)
                task_id = parse_id(str(created.get("id", "")), "created task id")
                _, verified = client.request("GET", f"/api/v1/tasks/{task_id}")
                self.send_json(201, verified)
                return
            match = re.fullmatch(r"/tasks/([1-9][0-9]*)", parsed.path)
            if match:
                task_id = match.group(1)
                changes = validate_task_fields(self.read_body(), create=False)
                _, existing = client.request("GET", f"/api/v1/tasks/{task_id}")
                if not isinstance(existing, dict):
                    raise AdapterError(502, "Vikunja returned an invalid task")
                existing.update(changes)
                client.request("POST", f"/api/v1/tasks/{task_id}", existing)
                _, verified = client.request("GET", f"/api/v1/tasks/{task_id}")
                self.send_json(200, verified)
                return
            match = re.fullmatch(r"/tasks/([1-9][0-9]*)/complete", parsed.path)
            if match:
                task_id = match.group(1)
                _, existing = client.request("GET", f"/api/v1/tasks/{task_id}")
                if not isinstance(existing, dict):
                    raise AdapterError(502, "Vikunja returned an invalid task")
                existing["done"] = True
                client.request("POST", f"/api/v1/tasks/{task_id}", existing)
                _, verified = client.request("GET", f"/api/v1/tasks/{task_id}")
                self.send_json(200, verified)
                return
            raise AdapterError(404, "route not found")
        except AdapterError as error:
            self.send_json(error.status, {"error": error.message})

    def do_PUT(self) -> None:
        self.send_json(405, {"error": "method not allowed"})

    def do_DELETE(self) -> None:
        self.send_json(405, {"error": "method not allowed"})


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = ThreadingHTTPServer(("127.0.0.1", 8791), Handler)
    server.daemon_threads = True
    logging.info("starting loopback Vikunja adapter on 127.0.0.1:8791")
    server.serve_forever()


if __name__ == "__main__":
    main()
