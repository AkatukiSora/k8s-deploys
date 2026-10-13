"""Offline manifest checks and optional isolated upstream Kanban gate tests.

Run from the repository root:
  python3 apps/hermes/test_kanban_visibility.py -v
  HERMES_SOURCE_DIR=/path/to/verified/hermes-source \
    python3 apps/hermes/test_kanban_visibility.py -v

The optional tests exercise selected upstream availability/ownership functions,
not a gateway, model schema assembly, board mutation or dispatcher.
"""
from __future__ import annotations

import ast
import hashlib
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import yaml

APP = Path(__file__).resolve().parent
IMAGE = "nousresearch/hermes-agent@sha256:444b42594e7f467425872fc35e077a227d377f0fe0726bc818706d62175fad8b"
SOURCE = os.environ.get("HERMES_SOURCE_DIR", "")
SOURCE_SHA256 = {
    "tools/kanban_toolset_context.py": "73c473524ce149a1421cb0745df02f6518a231bdc1344a3f4f8024aed6e16f72",
    "tools/kanban_tools.py": "e5f48cb0b471c8624322d6d452be959a1f9505ef11398f67a6f079aeaab0d02f",
    "model_tools.py": "872ca571c17379c8df19c0bcf639919bb0cb3a2706efc08e4dc6a1f3d8789662",
    "hermes_cli/tools_config.py": "786dafe9c52214c65cc225220328ffccf11ffb3669b9748c3cebf0c07c92f09c",
}


def verified_sources(root: Path) -> dict[str, str]:
    """Verify pinned-image bytes before executing or inspecting any source.

    Keep and use the checked bytes; reopening a path after verification would
    introduce a check/use race. Hashes match both published CPU architectures.
    """
    checked = {}
    for relative, expected in SOURCE_SHA256.items():
        with (root / relative).open("rb") as stream:
            content = stream.read(1024 * 1024 + 1)
        if len(content) > 1024 * 1024 or hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f"source does not match pinned image: {relative}")
        checked[relative] = content.decode("utf-8")
    return checked


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.config = yaml.safe_load((APP / "config.yaml").read_text())
        self.deployment = yaml.safe_load((APP / "deployment.yaml").read_text())

    def test_only_discord_has_explicit_kanban_opt_in(self):
        self.assertEqual(self.config["platform_toolsets"], {"discord": ["hermes-cli", "kanban"]})
        self.assertNotIn("kanban", self.config.get("toolsets") or [])

    def test_no_native_discord_api_tools_added(self):
        self.assertNotIn("hermes-discord", self.config["platform_toolsets"]["discord"])
        self.assertNotIn("discord", self.config["platform_toolsets"]["discord"])
        self.assertNotIn("discord_admin", self.config["platform_toolsets"]["discord"])

    def test_main_agent_uses_verified_image(self):
        containers = self.deployment["spec"]["template"]["spec"]["containers"]
        agent = next(item for item in containers if item["name"] == "hermes")
        self.assertEqual(agent["image"], IMAGE)

    def test_managed_config_checksum(self):
        digest = hashlib.sha256((APP / "config.yaml").read_bytes()).hexdigest()
        self.assertEqual(self.deployment["spec"]["template"]["metadata"]["annotations"]["checksum/hermes-config"], digest)

    def test_existing_worker_routing_is_preserved(self):
        self.assertEqual(self.config["delegation"]["model"], "gpt-6-luna")
        self.assertEqual(self.config["delegation"]["reasoning_effort"], "xhigh")
        self.assertFalse(self.config["delegation"]["orchestrator_enabled"])


@unittest.skipUnless(SOURCE, "set HERMES_SOURCE_DIR to the verified pinned-image source")
class SourceGateTests(unittest.TestCase):
    def setUp(self):
        root = Path(SOURCE)
        context_file = root / "tools/kanban_toolset_context.py"
        self.assertTrue(context_file.is_file(), "image lacks platform-scoped Kanban support")
        self.sources = verified_sources(root)
        # Execute only the reviewed, stdlib-only ContextVar module and selected
        # gate functions; do not import the image's agent or initialize tools.
        self.context = types.ModuleType("tools.kanban_toolset_context")
        exec(compile(self.sources["tools/kanban_toolset_context.py"], str(context_file), "exec"), self.context.__dict__)
        tree = ast.parse(self.sources["tools/kanban_tools.py"])
        names = {"_profile_has_kanban_toolset", "_visible", "_check_kanban_mode", "_check_kanban_orchestrator_mode", "_Reject", "_reject_delegated_child_mutation"}
        nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
        self.assertEqual({node.name for node in nodes}, names)
        for node in nodes:
            if isinstance(node, ast.FunctionDef):
                node.decorator_list = []
        self.child = False
        self.worker = True
        self.fixture_config = {"platform_toolsets": {"discord": ["hermes-cli", "kanban"]}}
        self.scope = {
            "os": os,
            "load_config": lambda: self.fixture_config,
            "_is_delegated_child_context": lambda: self.child,
            "_is_dispatcher_owned_worker": lambda: self.worker,
            "_delegation_ctx": lambda name, default: self.child if name == "is_delegated_child_process_context" else default,
            "tool_error": lambda message: message,
        }
        exec(compile(ast.fix_missing_locations(ast.Module(body=[node for node in nodes], type_ignores=[])), str(root / "tools/kanban_tools.py"), "exec"), self.scope)
        self.modules = patch.dict("sys.modules", {"tools.kanban_toolset_context": self.context})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.env = patch.dict(os.environ)
        self.env.start()
        self.addCleanup(self.env.stop)
        os.environ.pop("HERMES_KANBAN_TASK", None)

    def visible(self, selection, *, routing=False):
        with self.context.scoped_kanban_toolset_selection(selection):
            fn = "_check_kanban_orchestrator_mode" if routing else "_check_kanban_mode"
            return self.scope[fn]()

    def test_discord_parent_sees_lifecycle_and_routing(self):
        self.assertTrue(self.visible(["hermes-cli", "kanban"]))
        self.assertTrue(self.visible(["hermes-cli", "kanban"], routing=True))

    def test_other_platform_does_not_borrow_discord_opt_in(self):
        self.assertFalse(self.visible(["hermes-cli"]))
        self.assertFalse(self.visible(["hermes-cli"], routing=True))

    def test_wildcard_is_not_opt_in(self):
        self.assertFalse(self.visible(["all"]))
        self.assertFalse(self.visible(["*"]))

    def test_delegated_child_is_hidden_even_with_explicit_selection(self):
        self.child = True
        self.assertFalse(self.visible(["hermes-cli", "kanban"]))
        self.assertFalse(self.visible(["hermes-cli", "kanban"], routing=True))

    def test_delegated_child_cannot_inherit_worker_ownership(self):
        self.child = True
        os.environ["HERMES_KANBAN_TASK"] = "fixture-task"
        self.assertFalse(self.visible(["hermes-cli", "kanban"]))
        with self.assertRaises(self.scope["_Reject"]):
            self.scope["_reject_delegated_child_mutation"]("kanban_create")

    def test_dispatcher_worker_retains_lifecycle_only(self):
        os.environ["HERMES_KANBAN_TASK"] = "fixture-task"
        self.assertTrue(self.visible(["hermes-cli"]))
        self.assertFalse(self.visible(["hermes-cli"], routing=True))

    def test_selection_context_does_not_leak(self):
        self.assertTrue(self.visible(["kanban"]))
        self.assertIsNone(self.context.kanban_toolset_requested())
        self.assertFalse(self.visible(["hermes-cli"]))

    def test_image_schema_assembly_uses_scoped_selection(self):
        text = self.sources["model_tools.py"]
        self.assertIn("with scoped_kanban_toolset_selection(enabled_toolsets):", text)
        tree = ast.parse(self.sources["hermes_cli/tools_config.py"])
        assignment = next(node for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "_DEFAULT_OFF_TOOLSETS" for target in node.targets))
        self.assertIn("kanban", ast.literal_eval(assignment.value))

    def test_modified_source_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative, text in self.sources.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(text.encode("utf-8"))
            self.assertEqual(verified_sources(root), self.sources)
            for relative, text in self.sources.items():
                with self.subTest(source=relative):
                    path = root / relative
                    path.write_bytes((text + "\n# modified\n").encode("utf-8"))
                    with self.assertRaisesRegex(ValueError, "source does not match pinned image"):
                        verified_sources(root)
                    path.write_bytes(text.encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
