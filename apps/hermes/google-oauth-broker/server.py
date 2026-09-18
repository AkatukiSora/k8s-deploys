#!/usr/bin/env python3
"""Loopback-only Google OAuth broker for the Hermes secretary workflow."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import sys
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
REDIRECT_URI = "http://localhost:1"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.events.owned",
    "https://www.googleapis.com/auth/calendar.calendars",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
]
MAX_BODY_BYTES = 16 * 1024


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
        pending = json.loads(self.pending_path.read_text(encoding="utf-8"))
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
        token = json.loads(self.token_path.read_text(encoding="utf-8"))
        return {
            "authenticated": bool(token.get("refresh_token")),
            "expires_at": token.get("expires_at"),
            "scopes": token.get("scopes", SCOPES),
        }

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
            logging.info("Google token exchange failed status=%s", error.code)
            raise BrokerError(400, f"Google token exchange failed (HTTP {error.code})") from error
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            logging.info("Google token exchange unavailable: %s", error)
            raise BrokerError(503, "Google OAuth service is unavailable") from error


class Handler(BaseHTTPRequestHandler):
    server_version = "hermes-google-oauth-broker/1"

    def log_message(self, format: str, *args: object) -> None:
        logging.info("google-oauth-broker %s", format % args)

    def send_json(self, status: int, payload: dict) -> None:
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

    def do_GET(self) -> None:
        try:
            if self.path == "/health":
                self.send_json(200, {"status": "ok"})
            elif self.path == "/oauth/status":
                self.send_json(200, self.broker().status())
            else:
                raise BrokerError(404, "route not found")
        except BrokerError as error:
            self.send_json(error.status, {"error": error.message})

    def do_POST(self) -> None:
        try:
            if self.path == "/oauth/start":
                self.send_json(200, self.broker().start())
            elif self.path == "/oauth/exchange":
                payload = self.body()
                if set(payload) != {"callback_url"}:
                    raise BrokerError(400, "only callback_url is accepted")
                self.send_json(200, self.broker().exchange(payload["callback_url"]))
            else:
                raise BrokerError(404, "route not found")
        except BrokerError as error:
            self.send_json(error.status, {"error": error.message})

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
