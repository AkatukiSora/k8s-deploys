#!/usr/bin/env python3
"""Check that child Applications delete their managed resources safely."""

from pathlib import Path
import sys

import yaml


FINALIZER = "resources-finalizer.argocd.argoproj.io"
TRACKING = "argocd.argoproj.io/tracking-id"

# Namespaces intentionally shared by multiple Applications must not be owned by
# one child Application, so deleting that child cannot delete the namespace.
SHARED_NAMESPACES = {
    "argocd",
    "authentik",  # owned by the authentik Application
    "cnpg-system",
    "kube-system",
    "monitoring",
}

NAMESPACE_OWNERS = {
    "1password": {"1password"},
    "argo-rollouts": {"argo-rollouts"},
    "authentik": {"authentik"},
    "caddy-test": {"caddy-test"},
    "ceph-csi": {"ceph-csi"},
    "cert-manager": {"cert-manager"},
    "cloudflare-tunnel-ingress-controller": {"cloudflare-tunnel-ingress-controller"},
    "coder": {"coder", "coder-worker"},
    "immich": {"immich", "immich-postgres"},
    "influx-db": {"influxdb"},
    "metal-lb": {"metallb"},
    "metrics-server": {"metrics-server"},
    "pjserver-sys": {"pjserver-sys"},
    "security-kyverno": {"kyverno"},
    "security-policy-reporter": {"policy-reporter"},
    "security-trivy-operator": {"trivy-system"},
    "vikunja": {"vikunja"},
    "volsync": {"volsync-system"},
}

NAMESPACE_MANIFESTS = {
    ("authentik", "authentik"): Path("apps/authentik/manifests/namespace.yaml"),
    ("coder", "coder"): Path("apps/coder/namespace.yaml"),
    ("coder", "coder-worker"): Path("apps/coder/namespace.yaml"),
    ("immich", "immich"): Path("apps/immich/manifests/namespace.yaml"),
    ("immich", "immich-postgres"): Path("apps/immich-postgres/namespace.yaml"),
    ("metrics-server", "metrics-server"): Path("apps/metrics-server/namespace.yaml"),
    ("vikunja", "vikunja"): Path("apps/vikunja/manifests/namespace.yaml"),
}


def namespace_tracking_ids(application: dict) -> set[str]:
    metadata = (
        application.get("spec", {})
        .get("syncPolicy", {})
        .get("managedNamespaceMetadata", {})
    )
    annotations = metadata.get("annotations", {})
    return {value for key, value in annotations.items() if key == TRACKING}


def main() -> int:
    errors: list[str] = []
    applications: dict[str, dict] = {}

    for path in sorted(Path("installs").glob("*.yaml")):
        for document in yaml.safe_load_all(path.read_text()):
            if not document or document.get("kind") != "Application":
                continue

            name = document.get("metadata", {}).get("name", path.name)
            applications[name] = document
            if name == "apps-root":
                continue
            finalizers = document.get("metadata", {}).get("finalizers", [])
            if FINALIZER not in finalizers:
                errors.append(f"{path}: {name} lacks {FINALIZER}")

    for name, namespaces in NAMESPACE_OWNERS.items():
        application = applications.get(name)
        if application is None:
            errors.append(f"missing Application manifest: {name}")
            continue

        tracked = namespace_tracking_ids(application)
        for namespace in namespaces:
            expected = f"{name}:/Namespace:{namespace}/{namespace}"
            if expected in tracked:
                continue

            namespace_path = NAMESPACE_MANIFESTS.get(
                (name, namespace), Path("apps") / name / "namespace.yaml"
            )
            if namespace_path.exists() and expected in namespace_path.read_text():
                continue
            errors.append(f"{name}: namespace {namespace} is not tracked for deletion")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Argo CD application deletion safeguards are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
