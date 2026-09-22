#!/usr/bin/env python3
"""Tests for the tokenless Google secretary CLI."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("google-secretary-auth")
loader = importlib.machinery.SourceFileLoader("google_secretary_auth", str(MODULE_PATH))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
cli = importlib.util.module_from_spec(spec)
loader.exec_module(cli)


class GoogleSecretaryCliTests(unittest.TestCase):
    def test_calendar_events_cli_has_only_bounded_semantic_arguments(self):
        args = cli.build_parser().parse_args(
            ["calendar-events", "--calendar-id", "primary", "--start", "2026-09-22T00:00:00Z", "--limit", "20"]
        )
        self.assertEqual(args.command, "calendar-events")
        self.assertEqual(args.limit, 20)
        self.assertEqual(cli.path_for(args), "/calendar/events?calendar_id=primary&start=2026-09-22T00%3A00%3A00Z&limit=20")

    def test_gmail_get_cli_rejects_path_traversal_message_ids(self):
        with patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit):
                cli.build_parser().parse_args(["gmail-get", "../../token.json"])

    def test_gmail_list_cli_rejects_limit_above_twenty(self):
        with patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit):
                cli.build_parser().parse_args(["gmail-list", "--limit", "21"])


if __name__ == "__main__":
    unittest.main()
