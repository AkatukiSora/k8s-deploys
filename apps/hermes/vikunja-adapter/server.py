#!/usr/bin/env python3
"""Loopback-only, bounded Vikunja API v1 task adapter for Vikunja 2.x.

The Hermes container never receives the Vikunja bearer token. This sidecar is
the only token consumer and exposes only the secretary task operations below.
"""

from __future__ import annotations

import copy
import json
import logging
import math
import os
import re
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

LIST_QUERY_KEYS = {"page", "per_page", "s", "sort_by", "order_by", "filter_by", "filter_value", "filter_comparator"}
TASK_FIELDS = {"title", "description", "due_date", "start_date", "end_date", "priority", "reminders"}
MAX_BODY_BYTES = 32 * 1024
MAX_TITLE_LENGTH = 512
MAX_DESCRIPTION_LENGTH = 16 * 1024
ID_RE = re.compile(r"^[1-9][0-9]*$")
USER_AGENT = "Hermes-Vikunja-Adapter/1.1 (Vikunja-2.x; API-v1)"


class AdapterError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


# Local bounded write contract and validation helpers.
MAX_ID = 9223372036854775807
UNSET_DATE = "0001-01-01T00:00:00Z"
RFC3339_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$")
DATE_FIELDS = {"due_date", "start_date", "end_date"}
LABEL_QUERY_KEYS = {"page", "per_page", "s"}
RELATION_INVERSES = {
    "subtask": "parenttask", "parenttask": "subtask", "related": "related",
    "duplicateof": "duplicates", "duplicates": "duplicateof", "blocking": "blocked",
    "blocked": "blocking", "precedes": "follows", "follows": "precedes",
    "copiedfrom": "copiedto", "copiedto": "copiedfrom",
}
UI_RELATION_KINDS = frozenset(RELATION_INVERSES) - {"duplicateof"}
MUTABLE_TASK_FIELDS = (
    "title", "description", "done", "project_id", "due_date", "start_date", "end_date",
    "priority", "reminders", "labels", "related_tasks", "assignees", "repeat_after",
    "repeat_mode", "hex_color", "percent_done", "cover_image_attachment_id", "position",
    "bucket_id", "is_favorite",
)
MUTATION_LOCK = threading.RLock()


class UpstreamError(Exception):
    """Sanitized upstream failure; never retains a response body or URL."""
    def __init__(self, status: int | None, category: str):
        super().__init__(category)
        self.status = status
        self.category = category


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_UPSTREAM_OPENER = build_opener(NoRedirectHandler())


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
        self.base_url, self.token = base_url, token

    def request(self, method: str, path: str, payload: dict | None = None,
                query: dict[str, str] | None = None) -> tuple[int, object]:
        if not path.startswith("/api/v1/") or "?" in path or "#" in path:
            raise UpstreamError(None, "invalid_path")
        url = self.base_url + path
        if query:
            url += "?" + urlencode(query)
        body = None if payload is None else json.dumps(payload, separators=(",", ":"), allow_nan=False).encode()
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self.token}",
                   "User-Agent": USER_AGENT}
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with _UPSTREAM_OPENER.open(request, timeout=10) as response:
                raw = response.read(MAX_BODY_BYTES + 1)
                if len(raw) > MAX_BODY_BYTES:
                    raise UpstreamError(response.status, "response_too_large")
                try:
                    data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                                      parse_constant=_reject_nonfinite) if raw else {}
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                    raise UpstreamError(response.status, "invalid_json") from None
                return response.status, data
        except HTTPError as error:
            status = error.code
            error.close()
            raise UpstreamError(status, "http_error") from None
        except (URLError, TimeoutError, OSError):
            raise UpstreamError(None, "unavailable") from None


VIKUNJA_CLIENT_FACTORY = VikunjaClient


def _reject_nonfinite(value: str):
    raise ValueError("non-finite number")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def positive_id(value: object, name: str) -> int:
    if type(value) is not int or not 1 <= value <= MAX_ID:
        raise AdapterError(400, f"{name} must be a positive integer")
    return value


def parse_path_id(value: str, name: str) -> int:
    if not ID_RE.fullmatch(value):
        raise AdapterError(400, f"{name} must be a canonical positive integer")
    if len(value) > len(str(MAX_ID)):
        raise AdapterError(400, f"{name} is out of range")
    number = int(value)
    if number > MAX_ID:
        raise AdapterError(400, f"{name} is out of range")
    return number


def parse_rfc3339(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not RFC3339_RE.fullmatch(value):
        raise AdapterError(400, f"{field} must be a valid RFC3339 whole-second timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise AdapterError(400, f"{field} must be a valid timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AdapterError(400, f"{field} must include a UTC offset")
    try:
        normalized = parsed.astimezone(timezone.utc).replace(microsecond=0)
    except OverflowError:
        raise AdapterError(400, f"{field} is outside the supported UTC range") from None
    if normalized == datetime.min.replace(tzinfo=timezone.utc):
        raise AdapterError(400, f"{field} must not equal Vikunja's unset-date sentinel")
    return normalized


def read_datetime(value: object) -> datetime | None:
    if value == UNSET_DATE:
        return None
    if not isinstance(value, str):
        raise AdapterError(502, "Vikunja returned an invalid task date")
    fraction = re.search(r"\.(\d+)(?=Z|[+-]\d{2}:\d{2}$)", value)
    if fraction and len(fraction.group(1)) > 6:
        raise AdapterError(502, "Vikunja returned a task date with unsupported precision")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise AdapterError(502, "Vikunja returned an invalid task date") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AdapterError(502, "Vikunja returned an invalid task date")
    try:
        normalized = parsed.astimezone(timezone.utc)
    except OverflowError:
        raise AdapterError(502, "Vikunja returned an invalid task date") from None
    return None if normalized == datetime.min.replace(tzinfo=timezone.utc) else normalized


def format_datetime(value: datetime) -> str:
    utc_value = value.astimezone(timezone.utc)
    text = (f"{utc_value.year:04d}-{utc_value.month:02d}-{utc_value.day:02d}"
            f"T{utc_value.hour:02d}:{utc_value.minute:02d}:{utc_value.second:02d}")
    if utc_value.microsecond:
        text += "." + f"{utc_value.microsecond:06d}".rstrip("0")
    return text + "Z"


def wire_datetime(value: object, field: str, *, allow_clear: bool) -> str:
    if value is None and allow_clear:
        return UNSET_DATE
    return format_datetime(parse_rfc3339(value, field))


def _timestamp(value: datetime) -> int:
    utc_value = value.astimezone(timezone.utc)
    delta = utc_value - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def validate_reminder_input(value: object) -> None:
    if not isinstance(value, list) or len(value) > 32:
        raise AdapterError(400, "reminders must be an array with at most 32 entries")
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            raise AdapterError(400, "each reminder must be an object")
        keys = set(item)
        if keys == {"reminder"}:
            stamp = _timestamp(parse_rfc3339(item["reminder"], "reminder"))
            semantic = ("absolute", stamp)
        elif keys == {"relative_to", "relative_period"}:
            relation, period = item["relative_to"], item["relative_period"]
            if not isinstance(relation, str) or relation not in DATE_FIELDS:
                raise AdapterError(400, "relative reminder has an unsupported date field")
            if type(period) is not int or not -31536000 <= period <= 31536000:
                raise AdapterError(400, "relative reminder period must be an integer within one year")
            semantic = ("relative", relation, period)
        else:
            raise AdapterError(400, "reminder must use exactly one supported schema")
        if semantic in seen:
            raise AdapterError(400, "duplicate reminders are not allowed")
        seen.add(semantic)


def validate_reminders(value: object, dates: dict[str, object], *, from_upstream: bool = False) -> tuple[list[dict], set[tuple]]:
    invalid_status = 502 if from_upstream else 400
    if not isinstance(value, list) or len(value) > 32:
        raise AdapterError(invalid_status, "Vikunja returned invalid task reminders" if from_upstream else "reminders must be an array with at most 32 entries")
    date_map = {field: read_datetime(dates.get(field, UNSET_DATE)) for field in DATE_FIELDS}
    wire, semantics, instants = [], set(), set()
    for item in value:
        if not isinstance(item, dict):
            raise AdapterError(invalid_status, "Vikunja returned invalid task reminders" if from_upstream else "each reminder must be an object")
        keys = set(item)
        if not from_upstream and keys == {"reminder"}:
            relation, period = "", 0
            instant = parse_rfc3339(item["reminder"], "reminder")
            stamp = _timestamp(instant)
            semantic = ("absolute", stamp)
            wire.append({"reminder": format_datetime(instant), "relative_to": "", "relative_period": 0})
        elif not from_upstream and keys == {"relative_to", "relative_period"}:
            relation, period = item["relative_to"], item["relative_period"]
            if not isinstance(relation, str) or relation not in DATE_FIELDS:
                raise AdapterError(400, "relative reminder has an unsupported date field")
            if type(period) is not int or not -31536000 <= period <= 31536000:
                raise AdapterError(400, "relative reminder period must be an integer within one year")
            base = date_map[relation]
            if base is None:
                raise AdapterError(400, "relative reminder requires its base date")
            stamp = _timestamp(base) + period * 1_000_000
            semantic = ("relative", relation, period, stamp)
            wire.append({"reminder": UNSET_DATE, "relative_to": relation, "relative_period": period})
        elif from_upstream and keys == {"reminder", "relative_to", "relative_period"}:
            relation, period, absolute = item["relative_to"], item["relative_period"], item["reminder"]
            if not isinstance(absolute, str) or type(period) is not int:
                raise AdapterError(502, "Vikunja returned invalid task reminders")
            if relation == "":
                instant = read_datetime(absolute)
                if instant is None or period != 0:
                    raise AdapterError(502, "Vikunja returned invalid task reminders")
                stamp = _timestamp(instant)
                semantic = ("absolute", stamp)
                wire.append({"reminder": format_datetime(instant), "relative_to": "", "relative_period": 0})
            elif isinstance(relation, str) and relation in DATE_FIELDS:
                if not -31536000 <= period <= 31536000:
                    raise AdapterError(502, "Vikunja returned invalid task reminders")
                read_datetime(absolute)
                base = date_map[relation]
                if base is None:
                    raise AdapterError(400, "existing relative reminder has an unset base date")
                stamp = _timestamp(base) + period * 1_000_000
                semantic = ("relative", relation, period, stamp)
                wire.append({"reminder": UNSET_DATE, "relative_to": relation, "relative_period": period})
            else:
                raise AdapterError(502, "Vikunja returned invalid task reminders")
        else:
            raise AdapterError(invalid_status, "Vikunja returned invalid task reminders" if from_upstream else "reminder must use exactly one supported schema")
        unix_second = stamp // 1_000_000
        if unix_second in instants:
            raise AdapterError(invalid_status, "Vikunja returned duplicate reminder instants" if from_upstream else "reminders cannot resolve to the same instant")
        instants.add(unix_second)
        semantics.add(semantic)
    return wire, semantics


def validate_task_fields(payload: object, create: bool) -> dict:
    if not isinstance(payload, dict):
        raise AdapterError(400, "request body must be a JSON object")
    allowed = TASK_FIELDS | ({"project_id"} if create else set())
    if set(payload) - allowed:
        raise AdapterError(400, "unsupported task field")
    if create and ("project_id" not in payload or "title" not in payload):
        raise AdapterError(400, "project_id and title are required")
    if not create and not payload:
        raise AdapterError(400, "at least one mutable task field is required")
    result = {}
    for field, value in payload.items():
        if field == "project_id":
            result[field] = positive_id(value, field)
        elif field == "title":
            if not isinstance(value, str) or not value.strip() or len(value) > MAX_TITLE_LENGTH:
                raise AdapterError(400, "title must be non-empty and within the length limit")
            result[field] = value
        elif field == "description":
            if not isinstance(value, str) or len(value) > MAX_DESCRIPTION_LENGTH:
                raise AdapterError(400, "description must be a string within the length limit")
            result[field] = value
        elif field in DATE_FIELDS:
            if value is None and create:
                raise AdapterError(400, "create cannot clear a date")
            result[field] = wire_datetime(value, field, allow_clear=not create)
        elif field == "priority":
            if type(value) is not int or not 0 <= value <= 5:
                raise AdapterError(400, "priority must be an integer between 0 and 5")
            result[field] = value
        elif field == "reminders":
            if value is None:
                raise AdapterError(400, "reminders must be an array; use [] to clear")
            validate_reminder_input(value)
            result[field] = value
    if create:
        create_dates = {field: result.get(field, UNSET_DATE) for field in DATE_FIELDS}
        effective_dates(create_dates)
        if "reminders" in result:
            validate_reminders(result["reminders"], create_dates)
    return result


def validate_task(task: object, task_id: int) -> dict:
    if not isinstance(task, dict):
        raise AdapterError(502, "Vikunja returned an invalid task")
    expected = {
        "id": int, "project_id": int, "title": str, "description": str, "done": bool,
        "priority": int, "due_date": str, "start_date": str, "end_date": str,
        "labels": list, "related_tasks": dict, "assignees": list,
        "repeat_after": int, "repeat_mode": int, "hex_color": str,
        "cover_image_attachment_id": int, "is_favorite": bool,
    }
    # Vikunja serialises an empty labels/assignees collection as JSON null.
    for collection in ("labels", "assignees"):
        if task.get(collection) is None and collection in task:
            task[collection] = []
    for field, kind in expected.items():
        if field not in task or type(task[field]) is not kind:
            raise AdapterError(502, "Vikunja returned an incomplete task")
    if type(task["id"]) is not int or task["id"] != task_id or not 1 <= task_id <= MAX_ID:
        raise AdapterError(502, "Vikunja returned an invalid task ID")
    if not 1 <= task["project_id"] <= MAX_ID or task["priority"] < 0 or task["repeat_after"] < 0:
        raise AdapterError(502, "Vikunja returned invalid task fields")
    for field in DATE_FIELDS:
        read_datetime(task[field])
    for field in ("percent_done", "position"):
        if type(task.get(field)) not in (int, float) or not math.isfinite(task[field]):
            raise AdapterError(502, "Vikunja returned invalid task fields")
    if type(task.get("bucket_id")) is not int or task["bucket_id"] < 0:
        raise AdapterError(502, "Vikunja returned invalid task fields")
    for label in task["labels"]:
        if not isinstance(label, dict) or type(label.get("id")) is not int or not 1 <= label["id"] <= MAX_ID:
            raise AdapterError(502, "Vikunja returned invalid task labels")
    for kind, related in task["related_tasks"].items():
        if kind not in RELATION_INVERSES or not isinstance(related, list):
            raise AdapterError(502, "Vikunja returned invalid task relations")
        for item in related:
            if not isinstance(item, dict) or type(item.get("id")) is not int or not 1 <= item["id"] <= MAX_ID:
                raise AdapterError(502, "Vikunja returned invalid task relations")
    if "reminders" not in task:
        raise AdapterError(502, "Vikunja returned an incomplete task")
    reminders = task["reminders"]
    if reminders is not None and not isinstance(reminders, list):
        raise AdapterError(502, "Vikunja returned invalid task reminders")
    return task


def relation_pairs(task: dict) -> set[tuple[str, int]]:
    return {(kind, item["id"]) for kind, values in task["related_tasks"].items() for item in values}


def reminder_semantics(reminders: object, task: dict, *, verify_relative_instant: bool = False) -> set[tuple]:
    if reminders is None:
        reminders = []
    if not isinstance(reminders, list):
        raise AdapterError(502, "Vikunja returned invalid task reminders")
    dates = {field: read_datetime(task[field]) for field in DATE_FIELDS}
    result, instants = set(), set()
    for item in reminders:
        if not isinstance(item, dict):
            raise AdapterError(502, "Vikunja returned invalid task reminders")
        keys = set(item)
        if keys == {"reminder"}:
            absolute, relation, period = item["reminder"], "", 0
        elif keys == {"relative_to", "relative_period"}:
            absolute, relation, period = None, item["relative_to"], item["relative_period"]
        elif keys == {"reminder", "relative_to", "relative_period"}:
            absolute, relation, period = item["reminder"], item["relative_to"], item["relative_period"]
        else:
            raise AdapterError(502, "Vikunja returned invalid task reminders")
        if type(period) is not int:
            raise AdapterError(502, "Vikunja returned invalid task reminders")
        if relation == "":
            if not isinstance(absolute, str):
                raise AdapterError(502, "Vikunja returned invalid task reminders")
            instant = read_datetime(absolute)
            if instant is None or period != 0:
                raise AdapterError(502, "Vikunja returned invalid task reminders")
            stamp, semantic = _timestamp(instant), ("absolute", _timestamp(instant))
        elif isinstance(relation, str) and relation in DATE_FIELDS:
            if absolute is not None and not isinstance(absolute, str):
                raise AdapterError(502, "Vikunja returned invalid task reminders")
            if isinstance(absolute, str) and absolute != UNSET_DATE:
                read_datetime(absolute)
            base = dates[relation]
            if base is None:
                raise AdapterError(400, "existing relative reminder has an unset base date")
            if not -31536000 <= period <= 31536000:
                raise AdapterError(400, "existing reminder period is outside the supported range")
            stamp = _timestamp(base) + period * 1_000_000
            if verify_relative_instant:
                actual_instant = read_datetime(absolute)
                if actual_instant is None or _timestamp(actual_instant) != stamp:
                    raise AdapterError(502, "Vikunja returned an inconsistent relative reminder")
            semantic = ("relative", relation, period, stamp)
        else:
            raise AdapterError(502, "Vikunja returned invalid task reminders")
        unix_second = stamp // 1_000_000
        if unix_second in instants:
            raise AdapterError(502, "Vikunja returned duplicate reminder instants")
        instants.add(unix_second)
        result.add(semantic)
    return result


def field_equal(field: str, expected: object, actual: object, task: dict) -> bool:
    if field in DATE_FIELDS:
        return read_datetime(expected) == read_datetime(actual)
    if field == "labels":
        return {item["id"] for item in expected} == {item["id"] for item in actual}
    if field == "related_tasks":
        return relation_pairs({"related_tasks": expected}) == relation_pairs({"related_tasks": actual})
    if field == "reminders":
        return reminder_semantics(expected, task) == reminder_semantics(actual, task, verify_relative_instant=True)
    return type(expected) is type(actual) and expected == actual


def effective_dates(task: dict) -> None:
    start, end = read_datetime(task["start_date"]), read_datetime(task["end_date"])
    if start is not None and end is not None and start > end:
        raise AdapterError(400, "start_date must not be after end_date")


class MutationContext:
    def __init__(self, operation: str, task_id: int | None):
        self.operation, self.task_id = operation, task_id
        self.write_state, self.verification, self.write_succeeded = "not_attempted", "not_run", False


def failure_json(error: AdapterError, context: MutationContext) -> dict:
    return {"error": error.message, "write_state": context.write_state, "task_id": context.task_id,
            "operation": context.operation, "verification": context.verification}


def upstream_request(client, method: str, path: str, payload=None, query=None):
    try:
        return client.request(method, path, payload, query)
    except UpstreamError as error:
        status = error.status if error.status in {400, 401, 403, 404, 409, 422, 429, 503} else 502
        raise AdapterError(status, "Vikunja request failed") from None
    except AdapterError:
        raise
    except Exception:
        raise AdapterError(502, "Vikunja request failed") from None


def read_task(client, task_id: int, context: MutationContext | None = None) -> dict:
    if context is not None and context.write_succeeded:
        context.verification = "unavailable"
    status, data = upstream_request(client, "GET", f"/api/v1/tasks/{task_id}")
    if status != 200:
        raise AdapterError(502, "Vikunja task read failed")
    try:
        return validate_task(data, task_id)
    except AdapterError:
        if context is not None and context.write_succeeded:
            context.verification = "failed"
        raise


def perform_write(client, context: MutationContext, method: str, path: str,
                  payload: dict | None, expected_status: int) -> object:
    context.write_state = "unknown"
    try:
        status, result = client.request(method, path, payload)
    except UpstreamError as error:
        if error.status is not None and 400 <= error.status < 500:
            context.write_state = "rejected"
        raise AdapterError(502, "Vikunja write request failed") from None
    except Exception:
        raise AdapterError(502, "Vikunja write request failed") from None
    if 400 <= status < 500:
        context.write_state = "rejected"
        raise AdapterError(502, "Vikunja rejected the write request")
    if status != expected_status or not isinstance(result, dict):
        raise AdapterError(502, "Vikunja returned an invalid write response")
    context.write_succeeded, context.write_state = True, "applied_unverified"
    return result


def verify_task(context: MutationContext, actual: dict, expected: dict,
                fields: set[str], *, create: bool = False) -> None:
    try:
        effective_dates(actual)
        if create:
            fields = set(fields) | {"project_id"}
            if actual["done"] is not False:
                raise AdapterError(502, "created task verification failed")
        else:
            fields = set(MUTABLE_TASK_FIELDS)
        for field in fields:
            if field not in expected or field not in actual:
                if field in expected or field in actual:
                    raise AdapterError(502, "task readback verification failed")
                continue
            if not field_equal(field, expected[field], actual[field], expected):
                raise AdapterError(502, "task readback verification failed")
    except AdapterError:
        context.verification = "failed"
        raise AdapterError(502, "task readback verification failed") from None


def task_create(client, context: MutationContext, payload: dict) -> dict:
    project_id = payload["project_id"]
    body = {key: value for key, value in payload.items() if key != "project_id"}
    fields = set(body)
    if "reminders" in body:
        dates = {field: body.get(field, UNSET_DATE) for field in DATE_FIELDS}
        body["reminders"], _ = validate_reminders(body["reminders"], dates)
    result = perform_write(client, context, "PUT", f"/api/v1/projects/{project_id}/tasks", body, 201)
    task_id = result.get("id")
    if type(task_id) is not int or not 1 <= task_id <= MAX_ID:
        context.write_state, context.write_succeeded = "unknown", False
        raise AdapterError(502, "Vikunja returned an invalid created task ID")
    context.task_id = task_id
    verified = read_task(client, task_id, context)
    expected = copy.deepcopy(verified)
    expected["project_id"], expected["done"] = project_id, False
    for field in fields:
        expected[field] = payload[field]
    verify_task(context, verified, expected, fields, create=True)
    return verified


def task_update(client, context: MutationContext, task_id: int, changes: dict) -> dict:
    original = read_task(client, task_id)
    merged = copy.deepcopy(original)
    merged.update(changes)
    effective_dates(merged)
    old_reminders = original.get("reminders") or []
    if "reminders" in changes:
        merged["reminders"], _ = validate_reminders(changes["reminders"], merged)
        expected_reminders = changes["reminders"]
    else:
        merged["reminders"], _ = validate_reminders(old_reminders, merged, from_upstream=True)
        expected_reminders = old_reminders
    expected = copy.deepcopy(merged)
    expected["reminders"] = expected_reminders
    response = perform_write(client, context, "POST", f"/api/v1/tasks/{task_id}", merged, 200)
    if type(response.get("id")) is not int or response["id"] != task_id:
        context.write_state, context.write_succeeded = "unknown", False
        raise AdapterError(502, "Vikunja returned an invalid task update response")
    verified = read_task(client, task_id, context)
    verify_task(context, verified, expected, set(changes))
    return verified


def validate_label_payload(payload: object) -> int:
    if not isinstance(payload, dict) or set(payload) != {"label_id"}:
        raise AdapterError(400, "label operation requires exactly label_id")
    return positive_id(payload["label_id"], "label_id")


def validate_relation_payload(payload: object, base_id: int) -> tuple[int, str]:
    if not isinstance(payload, dict) or set(payload) != {"other_task_id", "relation_kind"}:
        raise AdapterError(400, "relation operation requires other_task_id and relation_kind")
    other_id, kind = positive_id(payload["other_task_id"], "other_task_id"), payload["relation_kind"]
    if not isinstance(kind, str) or kind not in RELATION_INVERSES:
        raise AdapterError(400, "relation_kind is unsupported")
    if other_id == base_id:
        raise AdapterError(400, "a task cannot relate to itself")
    return other_id, kind


def task_label_change(client, context: MutationContext, task_id: int, label_id: int, *, add: bool) -> dict:
    task = read_task(client, task_id)
    before = {label["id"] for label in task["labels"]}
    present = label_id in before
    if add and not present:
        status, catalog = upstream_request(client, "GET", "/api/v1/labels", None, {"s": str(label_id)})
        if status != 200 or not isinstance(catalog, list):
            raise AdapterError(502, "Vikunja label catalog read failed")
        if not any(isinstance(label, dict) and type(label.get("id")) is int and label["id"] == label_id for label in catalog):
            raise AdapterError(400, "label is not available to this account")
        perform_write(client, context, "PUT", f"/api/v1/tasks/{task_id}/labels", {"label_id": label_id}, 201)
    elif not add and present:
        perform_write(client, context, "DELETE", f"/api/v1/tasks/{task_id}/labels/{label_id}", None, 200)
    else:
        return task
    verified = read_task(client, task_id, context)
    after = {label["id"] for label in verified["labels"]}
    expected = before | {label_id} if add else before - {label_id}
    if after != expected:
        context.verification = "failed"
        raise AdapterError(502, "label association readback verification failed")
    return verified


def task_relation_change(client, context: MutationContext, base_id: int, other_id: int,
                         kind: str, *, add: bool) -> dict:
    base, other = read_task(client, base_id), read_task(client, other_id)
    inverse = RELATION_INVERSES[kind]
    base_before, other_before = relation_pairs(base), relation_pairs(other)
    forward, backward = (kind, other_id) in base_before, (inverse, base_id) in other_before
    if forward != backward:
        raise AdapterError(409, "relation state is inconsistent; no change was made")
    if add and not forward:
        perform_write(client, context, "PUT", f"/api/v1/tasks/{base_id}/relations",
                      {"other_task_id": other_id, "relation_kind": kind}, 201)
    elif not add and forward:
        perform_write(client, context, "DELETE", f"/api/v1/tasks/{base_id}/relations/{kind}/{other_id}", None, 200)
    else:
        return base
    verified_base, verified_other = read_task(client, base_id, context), read_task(client, other_id, context)
    expected_base = base_before | {(kind, other_id)} if add else base_before - {(kind, other_id)}
    expected_other = other_before | {(inverse, base_id)} if add else other_before - {(inverse, base_id)}
    if relation_pairs(verified_base) != expected_base or relation_pairs(verified_other) != expected_other:
        context.verification = "failed"
        raise AdapterError(502, "relation readback verification failed")
    return verified_base


class Handler(BaseHTTPRequestHandler):
    server_version = "hermes-vikunja-adapter/1"

    def log_message(self, format: str, *args: object) -> None:
        # Query strings may contain user search text; do not log them.
        return

    def send_json(self, status: int, data: object) -> None:
        encoded = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def read_body(self) -> object:
        length = self.headers.get("Content-Length")
        if length is None or not re.fullmatch(r"[0-9]+", length):
            raise AdapterError(400, "invalid request body length")
        size = int(length)
        if size > MAX_BODY_BYTES:
            raise AdapterError(400, "request body exceeds size limit")
        raw = self.rfile.read(size)
        if len(raw) != size:
            raise AdapterError(400, "request body is incomplete")
        try:
            return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_reject_nonfinite)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            raise AdapterError(400, "request body must be valid JSON") from None

    def client(self):
        try:
            return VIKUNJA_CLIENT_FACTORY()
        except Exception:
            raise AdapterError(503, "Vikunja adapter is not configured") from None

    def allowed_query(self, query: str, allowed: set[str]) -> dict[str, str]:
        try:
            parsed = parse_qs(query, keep_blank_values=False, strict_parsing=True) if query else {}
        except ValueError:
            raise AdapterError(400, "unsupported query parameter") from None
        if set(parsed) - allowed or any(len(values) != 1 for values in parsed.values()):
            raise AdapterError(400, "unsupported query parameter")
        return {key: values[0] for key, values in parsed.items()}

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self.send_json(200, {"status": "ok"})
                return
            task_match = re.fullmatch(r"/tasks/([^/]+)", parsed.path)
            if parsed.path not in {"/ready", "/projects", "/tasks", "/labels"} and task_match is None:
                raise AdapterError(404, "route not found")
            task_id = parse_path_id(task_match.group(1), "task_id") if task_match else None
            if parsed.path == "/labels":
                query = self.allowed_query(parsed.query, LABEL_QUERY_KEYS)
            elif parsed.path in {"/projects", "/tasks"}:
                query = self.allowed_query(parsed.query, LIST_QUERY_KEYS)
            else:
                if parsed.query:
                    raise AdapterError(400, "unsupported query parameter")
                query = {}
            client = self.client()
            if parsed.path == "/ready":
                _, data = upstream_request(client, "GET", "/api/v1/projects")
                self.send_json(200, {"status": "ready", "project_count": len(data) if isinstance(data, list) else None})
            elif parsed.path in {"/projects", "/tasks", "/labels"}:
                upstream_path = {"/projects": "/api/v1/projects", "/tasks": "/api/v1/tasks",
                                 "/labels": "/api/v1/labels"}[parsed.path]
                _, data = upstream_request(client, "GET", upstream_path, query=query)
                self.send_json(200, data)
            else:
                _, data = upstream_request(client, "GET", f"/api/v1/tasks/{task_id}")
                self.send_json(200, data)
        except AdapterError as error:
            self.send_json(error.status, {"error": error.message})
        except Exception:
            self.send_json(500, {"error": "internal adapter error"})

    def mutation(self, operation: str, task_id: int | None, validate, execute) -> None:
        context = MutationContext(operation, task_id)
        try:
            payload = validate()
            client = self.client()
            with MUTATION_LOCK:
                result = execute(client, context, payload)
            self.send_json(201 if operation == "tasks.create" else 200, result)
        except AdapterError as error:
            self.send_json(error.status, failure_json(error, context))
        except Exception:
            self.send_json(500, failure_json(AdapterError(500, "internal adapter error"), context))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.query:
            self.send_json(400, failure_json(AdapterError(400, "query parameters are not allowed"), MutationContext("route", None)))
            return
        if parsed.path == "/tasks":
            self.mutation("tasks.create", None, lambda: validate_task_fields(self.read_body(), True),
                          task_create)
            return
        match = re.fullmatch(r"/tasks/([^/]+)", parsed.path)
        if match and match.group(1).isdigit():
            try:
                task_id = parse_path_id(match.group(1), "task_id")
            except AdapterError as error:
                self.send_json(error.status, failure_json(error, MutationContext("tasks.update", None)))
                return
            self.mutation("tasks.update", task_id, lambda: validate_task_fields(self.read_body(), False),
                          lambda client, context, body: task_update(client, context, task_id, body))
            return
        match = re.fullmatch(r"/tasks/([^/]+)/labels/(add|remove)", parsed.path)
        if match:
            try:
                task_id = parse_path_id(match.group(1), "task_id")
            except AdapterError as error:
                self.send_json(error.status, failure_json(error, MutationContext("tasks.labels", None)))
                return
            action = match.group(2)
            self.mutation(f"tasks.labels.{action}", task_id, lambda: validate_label_payload(self.read_body()),
                          lambda client, context, label_id: task_label_change(client, context, task_id, label_id, add=action == "add"))
            return
        match = re.fullmatch(r"/tasks/([^/]+)/relations/(add|remove)", parsed.path)
        if match:
            try:
                task_id = parse_path_id(match.group(1), "task_id")
            except AdapterError as error:
                self.send_json(error.status, failure_json(error, MutationContext("tasks.relations", None)))
                return
            action = match.group(2)
            self.mutation(f"tasks.relations.{action}", task_id,
                          lambda: validate_relation_payload(self.read_body(), task_id),
                          lambda client, context, pair: task_relation_change(client, context, task_id, pair[0], pair[1], add=action == "add"))
            return
        self.send_json(404, failure_json(AdapterError(404, "route not found"), MutationContext("route", None)))

    def reject_method(self) -> None:
        self.send_json(405, failure_json(AdapterError(405, "method not allowed"), MutationContext("route", None)))

    def do_PUT(self) -> None:
        self.reject_method()

    def do_PATCH(self) -> None:
        self.reject_method()

    def do_DELETE(self) -> None:
        self.reject_method()


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.ERROR, format="%(asctime)s %(levelname)s %(message)s")
    server = ThreadingHTTPServer(("127.0.0.1", 8791), Handler)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    main()
