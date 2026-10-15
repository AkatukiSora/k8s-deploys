#!/usr/bin/env python3
"""Offline tests for github-tools/github-update-branch-staged using a fake gh."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parent / "github-tools" / "github-update-branch-staged"

FAKE_GH = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json, os, sys
    args = sys.argv[1:]
    assert args[0] == "api" and args[1] == "-X"
    method, path = args[2], args[3]
    body = json.loads(sys.stdin.read() or "{}") if "--input" in args else None
    with open(os.environ["FAKE_LOG"], "a") as log:
        log.write(json.dumps([method, path, body]) + "\\n")
    out = {}
    if method == "GET" and path == "repos/o/r":
        out = {"default_branch": "master"}
    elif method == "GET" and "/git/ref/heads/" in path:
        out = {"object": {"sha": os.environ["FAKE_REMOTE_HEAD"]}}
    elif method == "GET" and "/compare/" in path:
        out = {"status": os.environ.get("FAKE_COMPARE", "behind")}
    elif method == "POST" and path.endswith("/git/blobs"):
        out = {"sha": "b" * 40}
    elif method == "POST" and path.endswith("/git/trees"):
        out = {"sha": os.environ["FAKE_TREE"]}
    elif method == "POST" and path.endswith("/git/commits"):
        out = {"sha": "c" * 40, "verification": {"verified": os.environ.get("FAKE_VERIFIED", "1") == "1", "reason": "valid"}}
    else:
        sys.exit("unexpected request: %s %s" % (method, path))
    print(json.dumps(out))
    """
)


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()


class UpdateBranchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.repo = root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "master")
        git(self.repo, "config", "user.email", "t@example.invalid")
        git(self.repo, "config", "user.name", "t")
        git(self.repo, "remote", "add", "origin", "https://github.com/o/r.git")
        (self.repo / "a.txt").write_text("base\n")
        git(self.repo, "add", "a.txt")
        git(self.repo, "commit", "-q", "-m", "base")
        git(self.repo, "checkout", "-q", "-b", "feat/x")
        (self.repo / "b.txt").write_text("feature\n")
        git(self.repo, "add", "b.txt")
        git(self.repo, "commit", "-q", "-m", "feature")
        self.head = git(self.repo, "rev-parse", "HEAD")
        self.second = git(self.repo, "rev-parse", "master")
        (self.repo / "a.txt").write_text("resolved\n")
        git(self.repo, "add", "a.txt")
        self.tree = git(self.repo, "write-tree")
        self.gh = root / "gh"
        self.gh.write_text(FAKE_GH)
        self.gh.chmod(0o755)
        self.log = root / "log"
        self.env = {
            **os.environ,
            "HERMES_GH": str(self.gh),
            "FAKE_LOG": str(self.log),
            "FAKE_REMOTE_HEAD": self.head,
            "FAKE_TREE": self.tree,
        }

    def run_tool(self, *args: str, **overrides: str) -> subprocess.CompletedProcess[str]:
        env = {**self.env, **overrides}
        return subprocess.run(["python3", str(TOOL), *args], cwd=self.repo, env=env, text=True, capture_output=True)

    def requests(self) -> list[list]:
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_dry_run_creates_two_parent_commit_without_author_or_ref_update(self) -> None:
        result = self.run_tool("--dry-run", "master", "Merge master into feat/x")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["parents"], [self.head, self.second])
        self.assertFalse(report["updated"])
        commit = [r for r in self.requests() if r[1].endswith("/git/commits")][0][2]
        self.assertEqual(commit["parents"], [self.head, self.second])
        self.assertNotIn("author", commit)
        self.assertNotIn("committer", commit)
        self.assertFalse([r for r in self.requests() if r[0] == "PATCH"])
        tree = [r for r in self.requests() if r[1].endswith("/git/trees")][0][2]
        self.assertEqual(sorted(e["path"] for e in tree["tree"]), ["a.txt", "b.txt"])

    def test_refuses_default_branch(self) -> None:
        git(self.repo, "checkout", "-q", "master")
        result = self.run_tool("--dry-run", "master", "x")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("default branch", result.stderr)

    def test_refuses_unverified_commit_and_does_not_update_branch(self) -> None:
        result = self.run_tool("master", "x", FAKE_VERIFIED="0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not Verified", result.stderr)
        self.assertFalse([r for r in self.requests() if r[0] == "PATCH"])

    def test_refuses_tree_mismatch(self) -> None:
        result = self.run_tool("master", "x", FAKE_TREE="1" * 40)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("differs from staged tree", result.stderr)
        self.assertFalse([r for r in self.requests() if r[1].endswith("/git/commits")])

    def test_refuses_stale_remote_head(self) -> None:
        result = self.run_tool("master", "x", FAKE_REMOTE_HEAD="2" * 40)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not synchronized", result.stderr)

    def test_refuses_second_parent_outside_default_branch(self) -> None:
        result = self.run_tool("master", "x", FAKE_COMPARE="ahead")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("is not an ancestor", result.stderr)
        self.assertFalse([r for r in self.requests() if r[1].endswith("/git/blobs")])

    def test_requires_staged_difference(self) -> None:
        git(self.repo, "reset", "-q", "--hard", "master")
        git(self.repo, "checkout", "-q", "-B", "feat/y", "master")
        env = {**self.env, "FAKE_REMOTE_HEAD": git(self.repo, "rev-parse", "HEAD")}
        result = subprocess.run(["python3", str(TOOL), "--dry-run", "master", "x"], cwd=self.repo, env=env, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("nothing to merge", result.stderr)


if __name__ == "__main__":
    unittest.main()
