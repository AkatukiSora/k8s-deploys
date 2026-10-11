#!/usr/bin/env python3
"""Offline deployment invariants for the bounded Vikunja write adapter."""
from __future__ import annotations

import hashlib
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
DEPLOYMENT = ROOT / "deployment.yaml"
KUSTOMIZATION = ROOT / "kustomization.yaml"
ADAPTER = ROOT / "vikunja-adapter" / "server.py"
CLI = ROOT / "vikunja-tools" / "vikunja-tasks"
POLICY = ROOT / "write-enable-policy.md"
ALLOWED_CHANGE_PATHS = {
    "apps/hermes/vikunja-adapter/server.py",
    "apps/hermes/vikunja-adapter/test_server.py",
    "apps/hermes/vikunja-adapter/test_write_contract.py",
    "apps/hermes/vikunja-tools/vikunja-tasks",
    "apps/hermes/vikunja-tools/test_vikunja_tasks.py",
    "apps/hermes/deployment.yaml",
    "apps/hermes/README.md",
    "apps/hermes/write-enable-policy.md",
    "apps/hermes/test_vikunja_write_deployment.py",
}


def container_block(text: str, name: str) -> str:
    containers = text.index("      containers:\n")
    marker = f"        - name: {name}\n"
    start = text.index(marker, containers)
    next_container = re.search(r"^        - name: ", text[start + len(marker):], re.MULTILINE)
    end = start + len(marker) + next_container.start() if next_container else len(text)
    return text[start:end]


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render() -> str:
    kubectl = Path("/opt/kubernetes-bin/kubectl")
    result = subprocess.run([str(kubectl), "kustomize", str(ROOT)], cwd=REPO,
                            check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"kubectl kustomize failed: {result.stderr.strip()}")
    return result.stdout


class VikunjaWriteDeploymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.deployment = DEPLOYMENT.read_text(encoding="utf-8")
        cls.kustomization = KUSTOMIZATION.read_text(encoding="utf-8")
        cls.rendered = render()
        cls.adapter = ADAPTER.read_text(encoding="utf-8")
        cls.cli = CLI.read_text(encoding="utf-8")

    def assert_checksum(self, key: str, source: Path):
        expected = checksum(source)
        pattern = rf"(?m)^\s+{re.escape(key)}:\s+([0-9a-f]{{64}})\s*$"
        for rendered, text in (("source deployment", self.deployment), ("rendered deployment", self.rendered)):
            match = re.search(pattern, text)
            self.assertIsNotNone(match, f"{key} missing from {rendered}")
            assert match is not None
            self.assertEqual(match.group(1), expected, f"stale {key} in {rendered}")

    def test_only_scoped_paths_changed(self):
        result = subprocess.run(["git", "status", "--short"], cwd=REPO,
                                check=False, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        changed = set()
        for line in result.stdout.splitlines():
            if len(line) < 4:
                continue
            path = line[3:].strip()
            if path.startswith(".d1-validation-pycache/") or "/__pycache__/" in path:
                continue
            changed.add(path)
        self.assertLessEqual(changed, ALLOWED_CHANGE_PATHS)

    def test_source_and_rendered_script_checksums_match(self):
        self.assert_checksum("checksum/hermes-vikunja-adapter", ADAPTER)
        self.assert_checksum("checksum/hermes-vikunja-tools", CLI)

    def test_both_read_only_generated_configmaps_render(self):
        self.assertIn("name: hermes-vikunja-adapter", self.rendered)
        self.assertIn("server.py: |", self.rendered)
        self.assertIn("name: hermes-vikunja-tools", self.rendered)
        self.assertIn("vikunja-tasks: |", self.rendered)
        self.assertIn("vikunja-adapter/server.py", self.kustomization)
        self.assertIn("vikunja-tasks=vikunja-tools/vikunja-tasks", self.kustomization)
        self.assertIn("readOnly: true", self.deployment)

    def test_token_file_is_mounted_only_into_adapter(self):
        adapter_container = container_block(self.deployment, "vikunja-adapter")
        hermes_container = container_block(self.deployment, "hermes")
        self.assertIn("name: vikunja-api-secret", adapter_container)
        self.assertIn("mountPath: /var/run/vikunja-api", adapter_container)
        self.assertIn("readOnly: true", adapter_container)
        self.assertNotIn("vikunja-api-secret", hermes_container)
        self.assertNotIn("VIKUNJA_TOKEN_FILE", hermes_container)
        self.assertNotIn("VIKUNJA_BASE_URL", hermes_container)
        self.assertIn("secretName: hermes-vikunja", self.deployment)

    def test_adapter_is_fixed_https_loopback_and_not_published(self):
        adapter_container = container_block(self.deployment, "vikunja-adapter")
        self.assertIn('VIKUNJA_BASE_URL', adapter_container)
        self.assertIn("https://vikunja.akatuki-host.com", adapter_container)
        self.assertIn('ThreadingHTTPServer(("127.0.0.1", 8791)', self.adapter)
        self.assertIn('parsed.scheme != "https"', self.adapter)
        self.assertIn("NoRedirectHandler", self.adapter)
        self.assertNotRegex(self.deployment, r"containerPort:\s*8791\b")
        self.assertNotIn("service-vikunja-adapter", self.kustomization)

    def test_completion_and_arbitrary_write_surface_are_absent(self):
        self.assertNotIn("/complete", self.adapter)
        self.assertNotIn("tasks_complete", self.cli)
        self.assertIn("def do_PATCH", self.adapter)
        self.assertIn("def do_DELETE", self.adapter)
        self.assertNotIn("urlopen(Request(url", self.adapter)
        self.assertNotIn("https://", self.cli)

    def test_policy_remains_dormant_and_read_facade_stays_read_only(self):
        self.assertTrue(POLICY.is_file())
        self.assertIn("DRAFT — NOT DEPLOYED", POLICY.read_text(encoding="utf-8"))
        self.assertNotIn("write-enable-policy", self.kustomization)
        self.assertNotIn("write-enable-policy", self.deployment)
        read_source = (ROOT / "vikunja-read-proxy" / "server.py").read_text(encoding="utf-8")
        read_tests = (ROOT / "vikunja-adapter" / "test_server.py").read_text(encoding="utf-8")
        self.assertIn("def do_POST", read_source)
        self.assertIn("do_PUT = do_POST", read_source)
        self.assertIn("do_PATCH = do_POST", read_source)
        self.assertIn("do_DELETE = do_POST", read_source)
        self.assertIn("test_read_proxy_rejects_all_mutating_http_methods", read_tests)
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            self.assertIn(f'"{method}"', read_tests)


if __name__ == "__main__":
    unittest.main()
