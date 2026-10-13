#!/usr/bin/env python3
"""Validate repository-owned GitOps references and selected safety contracts.

This checker is intentionally static: it never contacts a Kubernetes cluster,
Argo CD, Helm repositories, or any workload endpoint.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


DEPRECATED_API_VERSIONS = {
    "apps/v1beta1",
    "apps/v1beta2",
    "batch/v1beta1",
    "extensions/v1beta1",
    "networking.k8s.io/v1beta1",
    "policy/v1beta1",
    "rbac.authorization.k8s.io/v1beta1",
    "storage.k8s.io/v1beta1",
}
YAML_SUFFIXES = {".yaml", ".yml"}


def yaml_files(repository: Path) -> list[Path]:
    return sorted(
        path
        for path in repository.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and path.suffix in YAML_SUFFIXES
        and ".git" not in path.parts
    )


def read_documents(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as manifest:
        return [document for document in yaml.safe_load_all(manifest) if isinstance(document, dict)]


def repository_path(repository: Path, candidate: str) -> Path | None:
    """Resolve a repository-relative path without allowing escapes or symlinks."""
    candidate_path = Path(candidate)
    if candidate_path.is_absolute() or ".." in candidate_path.parts:
        return None
    resolved_repository = repository.resolve()
    resolved_candidate = (resolved_repository / candidate_path).resolve()
    try:
        resolved_candidate.relative_to(resolved_repository)
    except ValueError:
        return None
    return resolved_candidate


def validate_kustomization(
    repository: Path, manifest: Path, document: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    relative_path = manifest.relative_to(repository)
    resources = document.get("resources", [])
    if not isinstance(resources, list):
        return [f"{relative_path}: resources must be a list"]
    for resource in resources:
        if not isinstance(resource, str) or resource.startswith(
            ("http://", "https://", "github.com/")
        ):
            continue
        resolved_resource = repository_path(manifest.parent, resource)
        if resolved_resource is None:
            errors.append(f"{relative_path}: resource {resource} must be repository-relative")
        elif not resolved_resource.exists():
            errors.append(f"{relative_path}: resource {resource} does not exist")
    return errors


def validate_application(
    repository: Path, manifest: Path, document: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    relative_path = manifest.relative_to(repository)
    spec = document.get("spec", {})
    if not isinstance(spec, dict):
        return [f"{relative_path}: spec must be a mapping"]
    sources = spec.get("sources", [spec.get("source", {})])
    if not isinstance(sources, list):
        return [f"{relative_path}: source(s) must be a list or mapping"]
    for source in sources:
        if not isinstance(source, dict):
            continue
        repository_url = source.get("repoURL", "")
        source_path = source.get("path")
        if (
            isinstance(repository_url, str)
            and "github.com/AkatukiSora/k8s-deploys" in repository_url
            and isinstance(source_path, str)
            and source_path
        ):
            resolved_source_path = repository_path(repository, source_path)
            if resolved_source_path is None:
                errors.append(
                    f"{relative_path}: local source path {source_path} must be repository-relative"
                )
            elif not resolved_source_path.exists():
                errors.append(
                    f"{relative_path}: local source path {source_path} does not exist"
                )
            elif not resolved_source_path.is_dir():
                errors.append(
                    f"{relative_path}: local source path {source_path} is not a directory"
                )
        helm = source.get("helm", {})
        if not isinstance(helm, dict):
            continue
        for value_file in helm.get("valueFiles", []):
            if not isinstance(value_file, str) or not value_file.startswith("$repo/"):
                continue
            local_value_file = value_file.removeprefix("$repo/")
            resolved_value_file = repository_path(repository, local_value_file)
            if resolved_value_file is None:
                errors.append(
                    f"{relative_path}: Helm value file {value_file} must be repository-relative"
                )
            elif not resolved_value_file.is_file():
                errors.append(
                    f"{relative_path}: Helm value file {value_file} does not exist"
                )
    return errors


def validate_pod_monitor(
    repository: Path, manifest: Path, document: dict[str, Any]
) -> list[str]:
    relative_path = manifest.relative_to(repository)
    metadata = document.get("metadata", {})
    if not isinstance(metadata, dict) or not isinstance(metadata.get("namespace"), str):
        return [f"{relative_path}: PodMonitor must set metadata.namespace"]
    return []


def has_mediamtx_metrics_ingress(document: dict[str, Any]) -> bool:
    spec = document.get("spec", {})
    if not isinstance(spec, dict):
        return False
    ingress_rules = spec.get("ingress", [])
    if not isinstance(ingress_rules, list):
        return False
    for ingress_rule in ingress_rules:
        if not isinstance(ingress_rule, dict):
            continue
        ports = ingress_rule.get("ports", [])
        if not isinstance(ports, list):
            continue
        permits_metrics_port = any(
            isinstance(port, dict)
            and port.get("protocol") == "TCP"
            and port.get("port") == 9998
            for port in ports
        )
        permits_monitoring = False
        sources = ingress_rule.get("from", [])
        if not isinstance(sources, list):
            continue
        for source in sources:
            if not isinstance(source, dict):
                continue
            namespace_selector = source.get("namespaceSelector")
            if not isinstance(namespace_selector, dict):
                continue
            match_labels = namespace_selector.get("matchLabels")
            if (
                isinstance(match_labels, dict)
                and match_labels.get("kubernetes.io/metadata.name") == "monitoring"
            ):
                permits_monitoring = True
                break
        if permits_metrics_port and permits_monitoring:
            return True
    return False


def validate_prometheus_pod_monitor_discovery(
    repository: Path, manifest: Path, document: dict[str, Any]
) -> list[str]:
    relative_path = manifest.relative_to(repository)
    prometheus = document.get("prometheus", {})
    if not isinstance(prometheus, dict):
        return [f"{relative_path}: prometheus configuration must be a mapping"]
    prometheus_spec = prometheus.get("prometheusSpec", {})
    if not isinstance(prometheus_spec, dict):
        return [f"{relative_path}: prometheus.prometheusSpec must be a mapping"]
    errors: list[str] = []
    for key in ("podMonitorSelector", "podMonitorNamespaceSelector"):
        if prometheus_spec.get(key) != {}:
            errors.append(
                f"{relative_path}: prometheus.prometheusSpec.{key} must be {{}}"
            )
    return errors


def validate_mediamtx_network_policy(
    repository: Path, manifest: Path, document: dict[str, Any]
) -> list[str]:
    if has_mediamtx_metrics_ingress(document):
        return []
    relative_path = manifest.relative_to(repository)
    return [f"{relative_path}: missing monitoring TCP/9998 ingress"]


def validate_repository(repository: Path) -> list[str]:
    """Return all static validation failures in a repository."""
    errors: list[str] = [
        f"{path.relative_to(repository)}: symbolic links are not allowed"
        for path in repository.rglob("*")
        if path.is_symlink() and ".git" not in path.parts
    ]
    for manifest in yaml_files(repository):
        relative_path = manifest.relative_to(repository)
        try:
            documents = read_documents(manifest)
        except yaml.YAMLError as error:
            errors.append(f"{relative_path}: invalid YAML: {error}")
            continue

        for document in documents:
            api_version = document.get("apiVersion")
            if api_version is not None and not isinstance(api_version, str):
                errors.append(f"{relative_path}: apiVersion must be a string")
            elif api_version in DEPRECATED_API_VERSIONS:
                errors.append(
                    f"{relative_path}: deprecated apiVersion {api_version}"
                )
            if manifest.name in {"kustomization.yaml", "kustomization.yml"}:
                errors.extend(validate_kustomization(repository, manifest, document))
            if document.get("kind") == "Application":
                errors.extend(validate_application(repository, manifest, document))
            if document.get("kind") == "PodMonitor":
                errors.extend(validate_pod_monitor(repository, manifest, document))
            if manifest == repository / "apps" / "kube-prometheus-stack" / "values.yaml":
                errors.extend(
                    validate_prometheus_pod_monitor_discovery(repository, manifest, document)
                )
            if (
                manifest == repository / "apps" / "mediamtx" / "networkpolicy.yaml"
                and document.get("kind") == "NetworkPolicy"
            ):
                errors.extend(
                    validate_mediamtx_network_policy(repository, manifest, document)
                )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root to validate",
    )
    arguments = parser.parse_args()
    errors = validate_repository(arguments.repository.resolve())
    if errors:
        print("GitOps static validation failed:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("GitOps static validation passed (static checks only; runtime verification required).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
