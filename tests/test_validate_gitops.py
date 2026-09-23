"""Regression tests for repository-level GitOps static validation."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / ".github" / "scripts" / "validate_gitops.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_gitops", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GitOpsValidatorTests(unittest.TestCase):
    def test_rejects_deprecated_kubernetes_api(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            manifest = repository / "apps" / "example" / "deployment.yaml"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(
                "apiVersion: apps/v1beta1\nkind: Deployment\nmetadata:\n  name: example\n",
                encoding="utf-8",
            )

            errors = validator.validate_repository(repository)

        self.assertIn(
            "apps/example/deployment.yaml: deprecated apiVersion apps/v1beta1",
            errors,
        )

    def test_rejects_missing_kustomization_resource(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            kustomization = repository / "apps" / "example" / "kustomization.yaml"
            kustomization.parent.mkdir(parents=True)
            kustomization.write_text("resources:\n  - missing.yaml\n", encoding="utf-8")

            errors = validator.validate_repository(repository)

        self.assertIn(
            "apps/example/kustomization.yaml: resource missing.yaml does not exist",
            errors,
        )

    def test_allows_remote_kustomization_resource(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            kustomization = repository / "apps" / "example" / "kustomization.yaml"
            kustomization.parent.mkdir(parents=True)
            kustomization.write_text(
                "resources:\n  - https://example.invalid/resource.yaml\n",
                encoding="utf-8",
            )

            errors = validator.validate_repository(repository)

        self.assertEqual([], errors)

    def test_allows_git_hub_kustomization_resource(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            kustomization = repository / "apps" / "example" / "kustomization.yaml"
            kustomization.parent.mkdir(parents=True)
            kustomization.write_text(
                "resources:\n  - github.com/example/project/config?ref=v1.0.0\n",
                encoding="utf-8",
            )

            errors = validator.validate_repository(repository)

        self.assertEqual([], errors)

    def test_rejects_missing_local_application_source_path(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            application = repository / "installs" / "example.yaml"
            application.parent.mkdir(parents=True)
            application.write_text(
                "apiVersion: argoproj.io/v1alpha1\n"
                "kind: Application\n"
                "metadata:\n  name: example\n"
                "spec:\n"
                "  source:\n"
                "    repoURL: https://github.com/AkatukiSora/k8s-deploys.git\n"
                "    path: apps/missing\n",
                encoding="utf-8",
            )

            errors = validator.validate_repository(repository)

        self.assertIn(
            "installs/example.yaml: local source path apps/missing does not exist",
            errors,
        )

    def test_rejects_application_source_path_that_is_not_a_directory(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            source_file = repository / "apps" / "not-a-directory.yaml"
            source_file.parent.mkdir(parents=True)
            source_file.write_text("key: value\n", encoding="utf-8")
            application = repository / "installs" / "example.yaml"
            application.parent.mkdir(parents=True, exist_ok=True)
            application.write_text(
                "apiVersion: argoproj.io/v1alpha1\n"
                "kind: Application\n"
                "metadata:\n  name: example\n"
                "spec:\n"
                "  source:\n"
                "    repoURL: https://github.com/AkatukiSora/k8s-deploys.git\n"
                "    path: apps/not-a-directory.yaml\n",
                encoding="utf-8",
            )

            errors = validator.validate_repository(repository)

        self.assertIn(
            "installs/example.yaml: local source path apps/not-a-directory.yaml "
            "is not a directory",
            errors,
        )

    def test_rejects_absolute_and_traversing_repository_references(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            application = repository / "installs" / "example.yaml"
            application.parent.mkdir(parents=True)
            application.write_text(
                "apiVersion: argoproj.io/v1alpha1\n"
                "kind: Application\n"
                "metadata:\n  name: example\n"
                "spec:\n"
                "  source:\n"
                "    repoURL: https://github.com/AkatukiSora/k8s-deploys.git\n"
                "    path: /etc\n"
                "    helm:\n"
                "      valueFiles:\n        - $repo/../outside.yaml\n",
                encoding="utf-8",
            )

            errors = validator.validate_repository(repository)

        self.assertIn(
            "installs/example.yaml: local source path /etc must be repository-relative",
            errors,
        )
        self.assertIn(
            "installs/example.yaml: Helm value file $repo/../outside.yaml "
            "must be repository-relative",
            errors,
        )

    def test_rejects_pod_monitor_without_namespace(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            monitor = repository / "apps" / "monitoring" / "monitor.yaml"
            monitor.parent.mkdir(parents=True)
            monitor.write_text(
                "apiVersion: monitoring.coreos.com/v1\n"
                "kind: PodMonitor\n"
                "metadata:\n  name: example\n"
                "spec:\n"
                "  selector:\n    matchLabels:\n      app: example\n"
                "  podMetricsEndpoints:\n    - port: metrics\n",
                encoding="utf-8",
            )

            errors = validator.validate_repository(repository)

        self.assertIn(
            "apps/monitoring/monitor.yaml: PodMonitor must set metadata.namespace",
            errors,
        )

    def test_rejects_prometheus_pod_monitor_selector_regression(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            values = repository / "apps" / "kube-prometheus-stack" / "values.yaml"
            values.parent.mkdir(parents=True)
            values.write_text(
                "prometheus:\n"
                "  prometheusSpec:\n"
                "    podMonitorSelector:\n"
                "      matchLabels:\n        app: restricted\n"
                "    podMonitorNamespaceSelector: {}\n",
                encoding="utf-8",
            )

            errors = validator.validate_repository(repository)

        self.assertIn(
            "apps/kube-prometheus-stack/values.yaml: "
            "prometheus.prometheusSpec.podMonitorSelector must be {}",
            errors,
        )

    def test_rejects_mediamtx_policy_without_metrics_ingress(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            policy = repository / "apps" / "mediamtx" / "networkpolicy.yaml"
            policy.parent.mkdir(parents=True)
            policy.write_text(
                "apiVersion: networking.k8s.io/v1\n"
                "kind: NetworkPolicy\n"
                "metadata:\n  name: mediamtx-ingress\n  namespace: mediamtx\n"
                "spec:\n  podSelector: {}\n  policyTypes:\n    - Ingress\n",
                encoding="utf-8",
            )

            errors = validator.validate_repository(repository)

        self.assertIn(
            "apps/mediamtx/networkpolicy.yaml: missing monitoring TCP/9998 ingress",
            errors,
        )

    def test_handles_non_mapping_network_policy_labels(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            policy = repository / "apps" / "mediamtx" / "networkpolicy.yaml"
            policy.parent.mkdir(parents=True)
            policy.write_text(
                "apiVersion: networking.k8s.io/v1\n"
                "kind: NetworkPolicy\n"
                "metadata:\n  name: mediamtx-ingress\n  namespace: mediamtx\n"
                "spec:\n"
                "  ingress:\n"
                "    - from:\n"
                "        - namespaceSelector:\n            matchLabels: []\n"
                "      ports:\n        - protocol: TCP\n          port: 9998\n",
                encoding="utf-8",
            )

            errors = validator.validate_repository(repository)

        self.assertIn(
            "apps/mediamtx/networkpolicy.yaml: missing monitoring TCP/9998 ingress",
            errors,
        )

    def test_rejects_malformed_manifest_field_types(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            policy = repository / "apps" / "mediamtx" / "networkpolicy.yaml"
            policy.parent.mkdir(parents=True)
            policy.write_text(
                "apiVersion: []\nkind: NetworkPolicy\nmetadata: {}\nspec:\n  ingress: null\n",
                encoding="utf-8",
            )

            errors = validator.validate_repository(repository)

        self.assertIn(
            "apps/mediamtx/networkpolicy.yaml: apiVersion must be a string",
            errors,
        )
        self.assertIn(
            "apps/mediamtx/networkpolicy.yaml: missing monitoring TCP/9998 ingress",
            errors,
        )


if __name__ == "__main__":
    unittest.main()
