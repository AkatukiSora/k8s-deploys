"""Contract tests for automatic Cilium GitOps registration and adoption."""

import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]


def load_yaml(path):
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


class CiliumGitOpsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = load_yaml(ROOT / "installs/cilium.yaml")
        cls.values = load_yaml(ROOT / "apps/cilium/values.yaml")

    def test_root_and_child_use_master_and_expected_path(self):
        root = load_yaml(ROOT / "apps-root.yaml")
        self.assertEqual(root["spec"]["source"]["path"], "installs")
        self.assertEqual(
            root["spec"]["source"]["repoURL"],
            "https://github.com/AkatukiSora/k8s-deploys.git",
        )
        self.assertEqual(root["spec"]["source"]["targetRevision"], "master")
        sources = self.application["spec"]["sources"]
        self.assertEqual(sources[0]["chart"], "cilium")
        self.assertEqual(sources[0]["repoURL"], "https://helm.cilium.io/")
        self.assertEqual(sources[1]["ref"], "repo")
        self.assertEqual(sources[1]["repoURL"], root["spec"]["source"]["repoURL"])
        self.assertEqual(
            sources[1]["targetRevision"], root["spec"]["source"]["targetRevision"]
        )
        self.assertRegex(sources[0]["targetRevision"], r"^\d+\.\d+\.\d+$")
        self.assertEqual(
            self.application["spec"]["destination"]["namespace"], "kube-system"
        )

    def test_automatic_policy_and_protection(self):
        metadata = self.application["metadata"]
        annotations = metadata["annotations"]
        self.assertEqual(
            {
                option.strip()
                for option in annotations["argocd.argoproj.io/sync-options"].split(",")
            },
            {"Prune=false", "Delete=false"},
        )
        self.assertEqual(annotations["argocd.argoproj.io/sync-wave"], "-10")
        policy = self.application["spec"]["syncPolicy"]
        self.assertEqual(
            policy["automated"], {"prune": False, "selfHeal": True, "allowEmpty": False}
        )
        self.assertIn("ServerSideApply=true", policy["syncOptions"])
        self.assertFalse(
            any(
                option in {"Force=true", "Replace=true"}
                for option in policy["syncOptions"]
            )
        )

    def test_steady_values_are_the_only_linked_values(self):
        helm = self.application["spec"]["sources"][0]["helm"]
        self.assertEqual(helm["valueFiles"], ["$repo/apps/cilium/values.yaml"])
        self.assertNotIn("values-migration.yaml", helm["valueFiles"])
        self.assertEqual(self.values["devices"], "eth0")
        self.assertFalse(self.values["operator"]["unmanagedPodWatcher"]["restart"])
        self.assertFalse(self.values["kubeProxyReplacement"])
        self.assertTrue(self.values["policyAuditMode"])
        self.assertTrue(self.values["encryption"]["enabled"])
        self.assertEqual(self.values["encryption"]["type"], "wireguard")
        self.assertFalse(self.values["encryption"]["nodeEncryption"])
        self.assertEqual(self.values["ipam"]["mode"], "cluster-pool")
        self.assertEqual(
            self.values["ipam"]["operator"]["clusterPoolIPv4PodCIDRList"],
            ["10.245.0.0/16"],
        )
        self.assertEqual(self.values["k8sServiceHost"], "localhost")
        self.assertEqual(self.values["k8sServicePort"], 7445)
        self.assertEqual(self.values["ipv4NativeRoutingCIDR"], "10.245.0.0/16")
        self.assertEqual(self.values["routingMode"], "native")


if __name__ == "__main__":
    unittest.main()
