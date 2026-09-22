#!/usr/bin/env python3
"""Loopback-only Google OAuth and Calendar/Gmail read broker."""

from __future__ import annotations

import base64
import binascii
import hashlib
import html
import json
import logging
import os
import re
import secrets
import sys
import time
from datetime import datetime
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_API_BASE = "https://www.googleapis.com"
REDIRECT_URI = "http://localhost:1"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]
MAX_BODY_BYTES = 16 * 1024
MAX_UPSTREAM_BYTES = 2 * 1024 * 1024
MAX_GMAIL_BODY_CHARS = 16 * 1024
MAX_RESULTS = 20
TOKEN_REFRESH_SKEW = 60
MESSAGE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
CALENDAR_ID_RE = re.compile(r"^[^/?#]+$")

CALENDAR_FIELDS = ("id", "summary", "description", "primary", "timeZone")
EVENT_FIELDS = ("id", "summary", "status", "start", "end", "location")
GMAIL_FIELDS = ("id", "threadId", "labelIds", "snippet", "internalDate", "sizeEstimate")
GMAIL_HEADER_NAMES = {"From", "To", "Subject", "Date"}


class BrokerError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def atomic_json_write(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def validate_limit(value: object) -> int:
    if type(value) is not int or not 1 <= value <= MAX_RESULTS:
        raise BrokerError(400, "limit must be an integer between 1 and 20")
    return value


def validate_calendar_id(value: object) -> str:
    if not isinstance(value, str) or not value or not CALENDAR_ID_RE.fullmatch(value):
        raise BrokerError(400, "calendar_id is invalid")
    return value


def validate_timestamp(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise BrokerError(400, f"{field} must be an ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise BrokerError(400, f"{field} must be an ISO 8601 timestamp") from error
    if parsed.tzinfo is None:
        raise BrokerError(400, f"{field} must include a timezone")
    return value


def filtered_fields(value: object, fields: tuple[str, ...]) -> dict:
    if not isinstance(value, dict):
        return {}
    return {field: value[field] for field in fields if field in value}


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"br", "p", "div", "li", "tr"}:
            self.parts.append("\n")

    def text(self) -> str:
        return html.unescape("".join(self.parts)).strip()


class GoogleOAuthBroker:
    def __init__(self) -> None:
        credential_dir = Path(os.environ.get("GOOGLE_OAUTH_CREDENTIAL_DIR", "/var/run/google-oauth-client"))
        state_dir = Path(os.environ.get("GOOGLE_OAUTH_STATE_DIR", "/var/lib/google-secretary"))
        self.client_id = (credential_dir / "clientId").read_text(encoding="utf-8").strip()
        self.client_secret = (credential_dir / "clientSecret").read_text(encoding="utf-8").strip()
        if not self.client_id or not self.client_secret:
            raise RuntimeError("Google OAuth client credential files are empty")
        if not state_dir.is_dir():
            raise RuntimeError("Google OAuth state directory is unavailable")
        self.state_dir = state_dir
        self.pending_path = state_dir / "oauth-pending.json"
        self.token_path = state_dir / "token.json"

    def start(self) -> dict:
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
        atomic_json_write(self.pending_path, {"state": state, "code_verifier": verifier, "created_at": int(time.time())})
        query = urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": REDIRECT_URI,
                "response_type": "code",
                "scope": " ".join(SCOPES),
                "access_type": "offline",
                "prompt": "consent",
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return {"authorization_url": f"{AUTH_URI}?{query}", "redirect_uri": REDIRECT_URI, "scopes": SCOPES}

    def exchange(self, callback: str) -> dict:
        if not self.pending_path.exists():
            raise BrokerError(400, "start OAuth authorization before exchanging a code")
        try:
            pending = json.loads(self.pending_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise BrokerError(503, "OAuth broker state is unavailable") from error
        created_at = pending.get("created_at")
        if type(created_at) is not int or int(time.time()) - created_at > 600:
            self.pending_path.unlink(missing_ok=True)
            raise BrokerError(400, "OAuth authorization expired; start a fresh authorization")
        code, state, granted_scopes = self._parse_callback(callback)
        if not set(SCOPES).issubset(granted_scopes):
            raise BrokerError(400, "Google did not grant every required scope")
        if not secrets.compare_digest(str(pending.get("state", "")), state):
            raise BrokerError(400, "OAuth state mismatch")
        payload = urlencode(
            {
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
                "code_verifier": pending["code_verifier"],
            }
        ).encode("utf-8")
        response = self._post_token(payload)
        token_scopes = set(str(response.get("scope", "")).split())
        if not set(SCOPES).issubset(token_scopes):
            raise BrokerError(502, "Google token response is missing a required scope")
        if "refresh_token" not in response:
            raise BrokerError(502, "Google did not issue a refresh token; restart authorization and grant consent")
        response["expires_at"] = int(time.time()) + int(response.get("expires_in", 0))
        response["scopes"] = sorted(token_scopes)
        atomic_json_write(self.token_path, response)
        self.pending_path.unlink(missing_ok=True)
        return self.status()

    def status(self) -> dict:
        if not self.token_path.exists():
            return {"authenticated": False, "scopes": SCOPES}
        try:
            token = json.loads(self.token_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise BrokerError(503, "Google OAuth token state is unavailable") from error
        if not isinstance(token, dict):
            raise BrokerError(503, "Google OAuth token state is invalid")
        return {
            "authenticated": bool(token.get("refresh_token")) and self._has_required_scopes(token),
            "expires_at": token.get("expires_at"),
            "scopes": token.get("scopes", SCOPES),
        }

    def ready(self) -> dict:
        self._access_token()
        self._google_request("/calendar/v3/users/me/calendarList", {"maxResults": "1"})
        return {"status": "ready", "authenticated": True, "scopes": SCOPES}

    def calendar_list(self) -> list[dict]:
        response = self._google_request("/calendar/v3/users/me/calendarList", {"maxResults": "250"})
        items = response.get("items", []) if isinstance(response, dict) else []
        if not isinstance(items, list):
            raise BrokerError(502, "Google returned an invalid calendar list")
        return [filtered_fields(item, CALENDAR_FIELDS) for item in items]

    def calendar_events(self, calendar_id: str = "primary", start: str | None = None, end: str | None = None, limit: int = MAX_RESULTS) -> list[dict]:
        calendar_id = validate_calendar_id(calendar_id)
        limit = validate_limit(limit)
        query = {"maxResults": str(limit)}
        if start is not None:
            query["timeMin"] = validate_timestamp(start, "start")
        if end is not None:
            query["timeMax"] = validate_timestamp(end, "end")
        response = self._google_request(f"/calendar/v3/calendars/{quote(calendar_id, safe='')}/events", query)
        items = response.get("items", []) if isinstance(response, dict) else []
        if not isinstance(items, list):
            raise BrokerError(502, "Google returned an invalid event list")
        return [filtered_fields(item, EVENT_FIELDS) for item in items[:limit]]

    def gmail_list(self, query: str = "", limit: int = MAX_RESULTS) -> list[dict]:
        if not isinstance(query, str):
            raise BrokerError(400, "query must be a string")
        limit = validate_limit(limit)
        request_query = {"maxResults": str(limit)}
        if query:
            request_query["q"] = query
        response = self._google_request("/gmail/v1/users/me/messages", request_query)
        items = response.get("messages", []) if isinstance(response, dict) else []
        if not isinstance(items, list):
            raise BrokerError(502, "Google returned an invalid Gmail message list")
        result = []
        for item in items[:limit]:
            if not isinstance(item, dict) or not self._valid_message_id(item.get("id")):
                continue
            metadata = self._google_request(f"/gmail/v1/users/me/messages/{item['id']}", {"format": "metadata"})
            result.append(self._gmail_metadata(metadata))
        return result

    def gmail_get(self, message_id: str) -> dict:
        if not self._valid_message_id(message_id):
            raise BrokerError(400, "message_id is invalid")
        message = self._google_request(f"/gmail/v1/users/me/messages/{message_id}", {"format": "full"})
        result = self._gmail_metadata(message)
        result["body"] = self._gmail_body(message)
        return result

    @staticmethod
    def _valid_message_id(message_id: object) -> bool:
        return isinstance(message_id, str) and bool(MESSAGE_ID_RE.fullmatch(message_id))

    def _gmail_metadata(self, message: object) -> dict:
        result = filtered_fields(message, GMAIL_FIELDS)
        if isinstance(message, dict):
            payload = message.get("payload")
            headers = payload.get("headers") if isinstance(payload, dict) else None
            if isinstance(headers, list):
                selected = [
                    {"name": header["name"], "value": header["value"]}
                    for header in headers
                    if isinstance(header, dict)
                    and header.get("name") in GMAIL_HEADER_NAMES
                    and isinstance(header.get("value"), str)
                ]
                if selected:
                    result["headers"] = selected
        return result

    def _gmail_body(self, message: object) -> str:
        payload = message.get("payload") if isinstance(message, dict) else None
        plain = self._find_part(payload, "text/plain")
        if plain is not None:
            return plain[:MAX_GMAIL_BODY_CHARS]
        html_body = self._find_part(payload, "text/html")
        if html_body is None:
            return ""
        parser = _HTMLText()
        parser.feed(html_body)
        return parser.text()[:MAX_GMAIL_BODY_CHARS]

    def _find_part(self, part: object, mime_type: str) -> str | None:
        if not isinstance(part, dict):
            return None
        if part.get("mimeType") == mime_type:
            body = part.get("body")
            data = body.get("data") if isinstance(body, dict) else None
            if isinstance(data, str):
                try:
                    padded = data + "=" * (-len(data) % 4)
                    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="replace")
                except (binascii.Error, ValueError, UnicodeError):
                    raise BrokerError(502, "Google returned invalid Gmail content")
        parts = part.get("parts")
        if isinstance(parts, list):
            for child in parts:
                found = self._find_part(child, mime_type)
                if found is not None:
                    return found
        return None

    def _access_token(self, force_refresh: bool = False) -> str:
        token = self._read_token()
        access_token = token.get("access_token")
        expires_at = token.get("expires_at")
        if not force_refresh and isinstance(access_token, str) and access_token and isinstance(expires_at, int) and expires_at > int(time.time()) + TOKEN_REFRESH_SKEW:
            return access_token
        refresh_token = token.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise BrokerError(503, "Google OAuth authorization is required")
        payload = urlencode(
            {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode("utf-8")
        response = self._post_token(payload)
        new_access_token = response.get("access_token")
        expires_in = response.get("expires_in")
        if not isinstance(new_access_token, str) or not new_access_token or type(expires_in) is not int:
            raise BrokerError(502, "Google returned an invalid refresh response")
        token.update(response)
        token["refresh_token"] = refresh_token
        token["expires_at"] = int(time.time()) + expires_in
        token["scopes"] = token.get("scopes", SCOPES)
        atomic_json_write(self.token_path, token)
        return new_access_token

    @staticmethod
    def _has_required_scopes(token: dict) -> bool:
        scopes = token.get("scopes")
        if not isinstance(scopes, list):
            scopes = str(token.get("scope", "")).split()
        return set(SCOPES).issubset({scope for scope in scopes if isinstance(scope, str)})

    def _read_token(self) -> dict:
        if not self.token_path.exists():
            raise BrokerError(503, "Google OAuth authorization is required")
        try:
            token = json.loads(self.token_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise BrokerError(503, "Google OAuth token state is unavailable") from error
        if not isinstance(token, dict):
            raise BrokerError(503, "Google OAuth token state is invalid")
        if not self._has_required_scopes(token):
            raise BrokerError(503, "Google OAuth authorization requires reauthorization")
        return token

    def _google_request(self, path: str, query: dict[str, str] | None = None) -> dict:
        access_token = self._access_token()
        for attempt in range(2):
            request_url = f"{GOOGLE_API_BASE}{path}"
            if query:
                request_url = f"{request_url}?{urlencode(query)}"
            request = Request(
                request_url,
                headers={"Accept": "application/json", "Authorization": f"Bearer {access_token}", "User-Agent": "Hermes-Google-Read-Broker/1.0"},
                method="GET",
            )
            try:
                with urlopen(request, timeout=15) as response:
                    raw = response.read(MAX_UPSTREAM_BYTES + 1)
                    if len(raw) > MAX_UPSTREAM_BYTES:
                        raise BrokerError(502, "Google response exceeded size limit")
                    data = json.loads(raw.decode("utf-8")) if raw else {}
                    if not isinstance(data, dict):
                        raise BrokerError(502, "Google returned invalid JSON")
                    return data
            except HTTPError as error:
                if error.code == 401 and attempt == 0:
                    access_token = self._access_token(force_refresh=True)
                    continue
                logging.info("Google API request failed path=%s status=%s", path, error.code)
                raise BrokerError(502 if error.code >= 400 else 503, f"Google API request failed (HTTP {error.code})") from error
            except (URLError, TimeoutError, OSError) as error:
                logging.info("Google API request unavailable path=%s reason=%s", path, error)
                raise BrokerError(503, "Google API is unavailable") from error
            except json.JSONDecodeError as error:
                raise BrokerError(502, "Google returned invalid JSON") from error
        raise BrokerError(502, "Google API authorization failed")

    def _parse_callback(self, callback: str) -> tuple[str, str, set[str]]:
        if not isinstance(callback, str) or not callback.startswith("http"):
            raise BrokerError(400, "callback_url must be the full localhost redirect URL")
        parsed = urlparse(callback)
        if parsed.scheme != "http" or parsed.hostname != "localhost" or parsed.port != 1 or parsed.path not in {"", "/"}:
            raise BrokerError(400, "callback_url must match the configured localhost redirect URI")
        params = parse_qs(parsed.query)
        code = (params.get("code") or [""])[0]
        state = (params.get("state") or [""])[0]
        granted_scopes = set((params.get("scope") or [""])[0].split())
        if not code or not state or not granted_scopes:
            raise BrokerError(400, "callback_url is missing code, state, or granted scopes")
        return code, state, granted_scopes

    def _post_token(self, payload: bytes) -> dict:
        request = Request(TOKEN_URI, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
        try:
            with urlopen(request, timeout=15) as response:
                data = json.loads(response.read(32 * 1024).decode("utf-8"))
                if not isinstance(data, dict):
                    raise BrokerError(502, "Google returned an invalid token response")
                return data
        except HTTPError as error:
            logging.info("Google token request failed status=%s", error.code)
            raise BrokerError(502, f"Google token request failed (HTTP {error.code})") from error
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            logging.info("Google token service unavailable: %s", error)
            raise BrokerError(503, "Google OAuth service is unavailable") from error


class Handler(BaseHTTPRequestHandler):
    server_version = "hermes-google-oauth-broker/2"

    def log_message(self, format: str, *args: object) -> None:
        logging.info("google-oauth-broker %s", format % args)

    def send_json(self, status: int, payload: object) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def broker(self) -> GoogleOAuthBroker:
        try:
            return GoogleOAuthBroker()
        except (OSError, RuntimeError, json.JSONDecodeError) as error:
            logging.error("broker is not configured: %s", error)
            raise BrokerError(503, "Google OAuth broker is not configured") from error

    def body(self) -> dict:
        length = self.headers.get("Content-Length")
        if length is None or not length.isdigit() or int(length) > MAX_BODY_BYTES:
            raise BrokerError(400, "invalid request body length")
        try:
            payload = json.loads(self.rfile.read(int(length)).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise BrokerError(400, "request body must be valid JSON") from error
        if not isinstance(payload, dict):
            raise BrokerError(400, "request body must be a JSON object")
        return payload

    @staticmethod
    def query(path: str, allowed: set[str]) -> tuple[str, dict[str, str]]:
        parsed = urlparse(path)
        values = parse_qs(parsed.query, keep_blank_values=True)
        if set(values) - allowed or any(len(items) != 1 for items in values.values()):
            raise BrokerError(400, "unsupported query parameter")
        return parsed.path, {key: values[key][0] for key in values}

    def do_GET(self) -> None:
        try:
            path, query = self.query(self.path, {"calendar_id", "start", "end", "limit", "query"})
            if path == "/health":
                self.send_json(200, {"status": "ok"})
            elif path == "/ready" and not query:
                self.send_json(200, self.broker().ready())
            elif path == "/oauth/status" and not query:
                self.send_json(200, self.broker().status())
            elif path == "/calendar/list" and not query:
                self.send_json(200, {"calendars": self.broker().calendar_list()})
            elif path == "/calendar/events":
                self.send_json(
                    200,
                    {
                        "events": self.broker().calendar_events(
                            query.get("calendar_id", "primary"),
                            query.get("start"),
                            query.get("end"),
                            int(query["limit"]) if "limit" in query else MAX_RESULTS,
                        )
                    },
                )
            elif path == "/gmail/messages":
                self.send_json(200, {"messages": self.broker().gmail_list(query.get("query", ""), int(query["limit"]) if "limit" in query else MAX_RESULTS)})
            else:
                match = re.fullmatch(r"/gmail/messages/([A-Za-z0-9_-]+)", path)
                if match and not (set(query)):
                    self.send_json(200, self.broker().gmail_get(match.group(1)))
                else:
                    raise BrokerError(404, "route not found")
        except (BrokerError, ValueError) as error:
            if isinstance(error, ValueError):
                error = BrokerError(400, "limit must be an integer between 1 and 20")
            self.send_json(error.status, {"error": error.message})

    def do_POST(self) -> None:
        try:
            path, query = self.query(self.path, set())
            if query:
                raise BrokerError(400, "query parameters are not accepted")
            if path == "/oauth/start":
                if self.body() != {}:
                    raise BrokerError(400, "request body must be empty")
                self.send_json(200, self.broker().start())
            elif path == "/oauth/exchange":
                payload = self.body()
                if set(payload) != {"callback_url"}:
                    raise BrokerError(400, "only callback_url is accepted")
                self.send_json(200, self.broker().exchange(payload["callback_url"]))
            else:
                raise BrokerError(404, "route not found")
        except BrokerError as error:
            self.send_json(error.status, {"error": error.message})

    def do_PUT(self) -> None:
        self.send_json(405, {"error": "method not allowed"})

    def do_PATCH(self) -> None:
        self.send_json(405, {"error": "method not allowed"})

    def do_DELETE(self) -> None:
        self.send_json(405, {"error": "method not allowed"})


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = ThreadingHTTPServer(("127.0.0.1", 8792), Handler)
    server.daemon_threads = True
    logging.info("starting Google OAuth broker on 127.0.0.1:8792")
    server.serve_forever()


if __name__ == "__main__":
    main()
