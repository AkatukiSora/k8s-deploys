#!/usr/bin/env python3
"""Tests for the bounded Google Calendar/Gmail read broker."""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("server.py")
spec = importlib.util.spec_from_file_location("google_oauth_broker", MODULE_PATH)
assert spec is not None and spec.loader is not None
broker_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(broker_module)


class GoogleReadBrokerTests(unittest.TestCase):
    def make_broker(self, token: dict | None = None):
        directory = tempfile.TemporaryDirectory()
        root = Path(directory.name)
        credentials = root / "credentials"
        state = root / "state"
        credentials.mkdir()
        state.mkdir()
        (credentials / "clientId").write_text("client-id", encoding="utf-8")
        (credentials / "clientSecret").write_text("client-secret", encoding="utf-8")
        if token is not None:
            (state / "token.json").write_text(json.dumps(token), encoding="utf-8")
        environment = {
            "GOOGLE_OAUTH_CREDENTIAL_DIR": str(credentials),
            "GOOGLE_OAUTH_STATE_DIR": str(state),
        }
        return directory, environment, broker_module.GoogleOAuthBroker

    def test_requests_only_broad_readonly_scopes(self):
        self.assertEqual(
            broker_module.SCOPES,
            [
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/calendar.readonly",
            ],
        )

    def test_calendar_events_are_bounded_and_filter_scheduling_fields(self):
        directory, environment, broker_type = self.make_broker(
            {"refresh_token": "refresh", "access_token": "access", "expires_at": 9999999999, "scopes": broker_module.SCOPES}
        )
        try:
            with patch.dict(os.environ, environment, clear=False):
                broker = broker_type()
                with patch.object(
                    broker,
                    "_google_request",
                    return_value={
                        "items": [
                            {
                                "id": "event-1",
                                "summary": "Planning",
                                "start": {"dateTime": "2026-09-22T10:00:00Z"},
                                "end": {"dateTime": "2026-09-22T11:00:00Z"},
                                "location": "Room 1",
                                "description": "private detail",
                                "attendees": [{"email": "hidden@example.com"}],
                            }
                        ]
                    },
                ) as request:
                    result = broker.calendar_events("primary", "2026-09-22T00:00:00Z", None, 20)
            request.assert_called_once_with(
                "/calendar/v3/calendars/primary/events",
                {"maxResults": "20", "timeMin": "2026-09-22T00:00:00Z"},
            )
            self.assertEqual(result, [{"id": "event-1", "summary": "Planning", "start": {"dateTime": "2026-09-22T10:00:00Z"}, "end": {"dateTime": "2026-09-22T11:00:00Z"}, "location": "Room 1"}])
        finally:
            directory.cleanup()

    def test_calendar_events_reject_limits_above_twenty(self):
        directory, environment, broker_type = self.make_broker()
        try:
            with patch.dict(os.environ, environment, clear=False):
                broker = broker_type()
                with self.assertRaises(broker_module.BrokerError):
                    broker.calendar_events("primary", None, None, 21)
        finally:
            directory.cleanup()

    def test_gmail_list_enriches_metadata_and_drops_payload_body(self):
        directory, environment, broker_type = self.make_broker(
            {"refresh_token": "refresh", "access_token": "access", "expires_at": 9999999999, "scopes": broker_module.SCOPES}
        )
        try:
            with patch.dict(os.environ, environment, clear=False):
                broker = broker_type()
                responses = iter(
                    [
                        {"messages": [{"id": "abc-123", "threadId": "thread-1"}]},
                        {
                            "id": "abc-123",
                            "threadId": "thread-1",
                            "labelIds": ["INBOX"],
                            "snippet": "A preview",
                            "internalDate": "1758500000000",
                            "sizeEstimate": 42,
                            "payload": {"body": {"data": "must-not-return"}},
                        },
                    ]
                )
                with patch.object(broker, "_google_request", side_effect=lambda path, query: next(responses)) as request:
                    result = broker.gmail_list("from:alice@example.com", 1)
            self.assertEqual(result, [{"id": "abc-123", "threadId": "thread-1", "labelIds": ["INBOX"], "snippet": "A preview", "internalDate": "1758500000000", "sizeEstimate": 42}])
            self.assertEqual(request.call_args_list[0].args, ("/gmail/v1/users/me/messages", {"maxResults": "1", "q": "from:alice@example.com"}))
            self.assertEqual(request.call_args_list[1].args, ("/gmail/v1/users/me/messages/abc-123", {"format": "metadata"}))
        finally:
            directory.cleanup()

    def test_gmail_get_returns_plain_text_and_caps_body(self):
        directory, environment, broker_type = self.make_broker(
            {"refresh_token": "refresh", "access_token": "access", "expires_at": 9999999999, "scopes": broker_module.SCOPES}
        )
        try:
            plain = "plain text\n" + ("x" * broker_module.MAX_GMAIL_BODY_CHARS)
            encoded = base64.urlsafe_b64encode(plain.encode()).decode().rstrip("=")
            html = base64.urlsafe_b64encode(b"<b>ignored html</b>").decode().rstrip("=")
            with patch.dict(os.environ, environment, clear=False):
                broker = broker_type()
                with patch.object(
                    broker,
                    "_google_request",
                    return_value={
                        "id": "abc-123",
                        "threadId": "thread-1",
                        "payload": {
                            "mimeType": "multipart/alternative",
                            "parts": [
                                {"mimeType": "text/plain", "body": {"data": encoded}},
                                {"mimeType": "text/html", "body": {"data": html}},
                            ],
                        },
                    },
                ):
                    result = broker.gmail_get("abc-123")
            self.assertEqual(result["id"], "abc-123")
            self.assertEqual(len(result["body"]), broker_module.MAX_GMAIL_BODY_CHARS)
            self.assertTrue(result["body"].startswith("plain text\n"))
            self.assertNotIn("ignored html", result["body"])
        finally:
            directory.cleanup()

    def test_gmail_get_rejects_invalid_message_id(self):
        directory, environment, broker_type = self.make_broker()
        try:
            with patch.dict(os.environ, environment, clear=False):
                with self.assertRaises(broker_module.BrokerError):
                    broker_type().gmail_get("../../token.json")
        finally:
            directory.cleanup()

    def test_expired_access_token_is_refreshed_and_persisted_by_broker(self):
        directory, environment, broker_type = self.make_broker(
            {"refresh_token": "refresh-secret", "access_token": "old-access", "expires_at": 1, "scopes": broker_module.SCOPES}
        )
        try:
            with patch.dict(os.environ, environment, clear=False):
                broker = broker_type()
                with patch.object(broker, "_post_token", return_value={"access_token": "new-access", "expires_in": 3600}) as refresh:
                    self.assertEqual(broker._access_token(), "new-access")
            refresh.assert_called_once()
            saved = json.loads((Path(environment["GOOGLE_OAUTH_STATE_DIR"]) / "token.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["refresh_token"], "refresh-secret")
            self.assertEqual(saved["access_token"], "new-access")
        finally:
            directory.cleanup()

    def test_old_calendar_grant_requires_reauthorization(self):
        directory, environment, broker_type = self.make_broker(
            {
                "refresh_token": "refresh-secret",
                "access_token": "old-access",
                "expires_at": 9999999999,
                "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
            }
        )
        try:
            with patch.dict(os.environ, environment, clear=False):
                broker = broker_type()
                self.assertFalse(broker.status()["authenticated"])
                with self.assertRaises(broker_module.BrokerError):
                    broker.ready()
        finally:
            directory.cleanup()

    def test_status_does_not_return_tokens_and_ready_probes_google(self):
        directory, environment, broker_type = self.make_broker(
            {"refresh_token": "refresh-secret", "access_token": "access-secret", "expires_at": 9999999999, "scopes": broker_module.SCOPES}
        )
        try:
            with patch.dict(os.environ, environment, clear=False):
                broker = broker_type()
                with patch.object(broker, "_google_request", return_value={"items": []}) as request:
                    ready = broker.ready()
            self.assertEqual(ready["status"], "ready")
            request.assert_called_once_with("/calendar/v3/users/me/calendarList", {"maxResults": "1"})
            status = broker.status()
            serialized = json.dumps(status)
            self.assertNotIn("access-secret", serialized)
            self.assertNotIn("refresh-secret", serialized)
            self.assertNotIn("access_token", status)
            self.assertNotIn("refresh_token", status)
        finally:
            directory.cleanup()


if __name__ == "__main__":
    unittest.main()
