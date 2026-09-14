"""Regression checks for Git-managed CloudNativePG Prometheus discovery."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PODMONITOR = ROOT / "apps/kube-prometheus-stack/cnpg-podmonitor.yaml"


class CnpgMonitoringTests(unittest.TestCase):
    def test_central_podmonitor_discovers_cnpg_instances_cluster_wide(self):
        manifest = PODMONITOR.read_text()

        self.assertIn("kind: PodMonitor", manifest)
        self.assertIn("namespaceSelector:\n    any: true", manifest)
        self.assertIn("key: cnpg.io/cluster", manifest)
        self.assertIn("operator: Exists", manifest)
        self.assertIn("port: metrics", manifest)

        prometheus_values = (ROOT / "apps/kube-prometheus-stack/values.yaml").read_text()
        self.assertIn("podMonitorSelector: {}", prometheus_values)
        self.assertIn("podMonitorNamespaceSelector: {}", prometheus_values)

    def test_cnpg_operator_is_monitored(self):
        manifest = PODMONITOR.read_text()

        self.assertIn("name: cnpg-controller-manager", manifest)
        self.assertIn("namespace: cnpg-system", manifest)
        self.assertIn("app.kubernetes.io/name: cloudnative-pg", manifest)

    def test_network_is_open_to_prometheus_for_cnpg_clusters_with_ingress_policies(self):
        protected_clusters = [
            ROOT / "apps/authentik-postgres/networkpolicy.yaml",
            ROOT / "apps/immich-postgres/networkpolicy.yaml",
            ROOT / "apps/vikunja-postgres/networkpolicy.yaml",
        ]

        for path in protected_clusters:
            content = path.read_text()
            self.assertIn("kubernetes.io/metadata.name: monitoring", content, path)
            self.assertIn("port: 9187", content, path)

    def test_cnpg_clusters_do_not_rely_on_deprecated_generated_podmonitors(self):
        cluster_files = []
        for path in (ROOT / "apps").rglob("*.yaml"):
            content = path.read_text()
            if "apiVersion: postgresql.cnpg.io/" in content and "kind: Cluster" in content:
                cluster_files.append(path)
                self.assertNotIn("enablePodMonitor: true", content, path)

        self.assertGreater(len(cluster_files), 0)


if __name__ == "__main__":
    unittest.main()
