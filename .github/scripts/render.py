#!/usr/bin/env python3
"""Render every Argo CD Application under installs/ and list container images.

render  ROOT OUT   Render each Application in ROOT/installs to OUT/<name>.yaml
                   with helm/kustomize, the way Argo CD would. Exit 1 if any
                   Application fails to render.
images  DIR        Print the sorted unique container image references found in
                   the rendered manifests under DIR.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

SELF_REPO = "AkatukiSora/k8s-deploys"
YAML_SUFFIXES = {".yaml", ".yml"}


def run(cmd: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}\n{result.stderr.strip()}")
    return result.stdout


def expand_braces(pattern: str) -> list[str]:
    match = re.search(r"\{([^{}]*)\}", pattern)
    if not match:
        return [pattern]
    head, tail = pattern[: match.start()], pattern[match.end() :]
    return [p for option in match.group(1).split(",") for p in expand_braces(head + option + tail)]


def render_helm(chart: str, release: str, namespace: str, values: list[str], extra: list[str]) -> str:
    cmd = ["helm", "template", release, chart, "--namespace", namespace, "--include-crds", *extra]
    for value_file in values:
        cmd += ["--values", value_file]
    return run(cmd)


def render_directory(path: Path, directory: dict) -> str:
    if (path / "kustomization.yaml").exists() or (path / "kustomization.yml").exists():
        return run(["kustomize", "build", "--enable-helm", str(path)])
    excludes = expand_braces(directory["exclude"]) if "exclude" in directory else []
    files = path.rglob("*") if directory.get("recurse") else path.glob("*")
    documents: list[dict] = []
    for file in sorted(files):
        relative = file.relative_to(path).as_posix()
        if file.suffix not in YAML_SUFFIXES or any(fnmatch.fnmatch(relative, p) for p in excludes):
            continue
        # Files without `kind` (for example Helm values files) are not manifests.
        documents += [d for d in yaml.safe_load_all(file.read_text(encoding="utf-8")) if isinstance(d, dict) and "kind" in d]
    return yaml.safe_dump_all(documents)


def render_application(app: dict, root: Path, work: Path) -> str:
    spec = app["spec"]
    namespace = spec["destination"].get("namespace", "default")
    sources = spec.get("sources") or [spec["source"]]
    refs = {s["ref"]: root for s in sources if "ref" in s and SELF_REPO in s["repoURL"]}
    outputs: list[str] = []
    for index, source in enumerate(sources):
        helm = source.get("helm", {})
        values = []
        for value_file in helm.get("valueFiles", []):
            if value_file.startswith("$"):
                name, _, rest = value_file[1:].partition("/")
                values.append(str(refs[name] / rest))
            else:
                values.append(value_file)
        if "valuesObject" in helm:
            inline = work / f"values-{index}.yaml"
            inline.write_text(yaml.safe_dump(helm["valuesObject"]), encoding="utf-8")
            values.append(str(inline))
        release = helm.get("releaseName", app["metadata"]["name"])
        revision = source["targetRevision"]
        url = source["repoURL"]
        if "chart" in source:
            if url.startswith("oci://"):
                outputs.append(render_helm(f"{url.rstrip('/')}/{source['chart']}", release, namespace, values, ["--version", revision]))
            else:
                outputs.append(render_helm(source["chart"], release, namespace, values, ["--repo", url, "--version", revision]))
        elif "path" in source:
            if SELF_REPO in url:
                path = root / source["path"]
            else:
                checkout = work / f"git-{index}"
                run(["git", "clone", "--quiet", "--depth", "1", "--branch", revision, url, str(checkout)])
                path = checkout / source["path"]
            if (path / "Chart.yaml").exists():
                run(["helm", "dependency", "build", str(path)])
                outputs.append(render_helm(str(path), release, namespace, values, []))
            else:
                outputs.append(render_directory(path, source.get("directory", {})))
    return "\n---\n".join(outputs)


def render(root: Path, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    failures = 0
    for manifest in sorted((root / "installs").glob("*.y*ml")):
        for app in yaml.safe_load_all(manifest.read_text(encoding="utf-8")):
            if not isinstance(app, dict) or app.get("kind") != "Application":
                continue
            name = app["metadata"]["name"]
            try:
                with tempfile.TemporaryDirectory() as work:
                    (out / f"{name}.yaml").write_text(render_application(app, root, Path(work)), encoding="utf-8")
                print(f"ok    {name}")
            except RuntimeError as error:
                failures += 1
                print(f"FAIL  {name}\n{error}", file=sys.stderr)
    return 1 if failures else 0


IMAGE_LINE = re.compile(r"^[ \t]*(?:-[ \t]+)?image:[ \t]*[\"']?([^\s\"'#]+)", re.MULTILINE)


def images(directory: Path) -> None:
    found: set[str] = set()
    for file in sorted(directory.glob("*.yaml")):
        found.update(IMAGE_LINE.findall(file.read_text(encoding="utf-8")))
    print("\n".join(sorted(found)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    render_parser = sub.add_parser("render")
    render_parser.add_argument("root", type=Path)
    render_parser.add_argument("out", type=Path)
    images_parser = sub.add_parser("images")
    images_parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    if args.command == "render":
        sys.exit(render(args.root.resolve(), args.out))
    images(args.directory)
