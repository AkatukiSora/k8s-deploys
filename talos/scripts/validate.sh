#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
patches="$root/talos/patches"
secrets_file="${TALOS_SECRETS_FILE:-$root/talos/secrets/secret.yaml}"

fail() {
  printf '%s\n' "error: $*" >&2
  exit 1
}

command -v python3 >/dev/null 2>&1 || fail "required command is not available: python3"
python3 - "$root" <<'PY'
import sys
from pathlib import Path
import yaml

root = Path(sys.argv[1])
patches = root / "talos/patches"
nodes = {"c1": "10.0.40.11", "c2": "10.0.40.12", "c3": "10.0.40.13",
         "w1": "10.0.40.51", "w2": "10.0.40.52", "w3": "10.0.40.53", "w4": "10.0.40.54"}
ceph = {"c1": "192.168.8.11", "c2": "192.168.8.12", "c3": "192.168.8.13",
         "w1": "192.168.8.51", "w2": "192.168.8.52", "w3": "192.168.8.53", "w4": "192.168.8.54"}

def fail(message):
    raise SystemExit(f"error: {message}")

def docs(path):
    try:
        values = list(yaml.safe_load_all(path.read_text()))
    except (OSError, yaml.YAMLError) as error:
        fail(f"cannot parse YAML {path}: {error}")
    return [value for value in values if value is not None]

common = docs(patches / "common.yaml")
if common != [{"machine": {"install": {"image": "factory.talos.dev/installer/ce4c980550dd2ab1b17bbf2b08801c7eb59418eafe8f279833297925d67c7515:v1.13.6"}, "network": {"nameservers": ["10.0.40.2"]}}}]:
    fail("common patch does not contain the required installer and DNS settings")

controlplane = docs(patches / "roles/controlplane.yaml")
if len(controlplane) != 2 or controlplane[1] != {"apiVersion": "v1alpha1", "kind": "Layer2VIPConfig", "name": "10.0.40.99", "link": "ens18"}:
    fail("control-plane role patch does not contain the required VIP")
worker = docs(patches / "roles/worker.yaml")
rules = [doc for doc in worker if doc.get("kind") == "RoutingRuleConfig"]
expected_rules = [("1000", "10.127.0.0/24", "ens20"), ("1001", "10.127.0.0/24", "ens18")]
if [(rule.get("name"), rule.get("dst"), rule.get("iifName")) for rule in rules] != expected_rules:
    fail("worker role patch must retain both RoutingRuleConfig documents")

for name, management_ip in nodes.items():
    path = patches / f"nodes/{name}.yaml"
    node_docs = docs(path)
    if len(node_docs) != 2 or node_docs[1].get("kind") != "HostnameConfig" or node_docs[1].get("hostname") != name:
        fail(f"{name} patch is missing its HostnameConfig")
    machine = node_docs[0].get("machine", {})
    if machine.get("install", {}).get("disk") != "/dev/sda":
        fail(f"{name} patch has the wrong install disk")
    interfaces = {item["interface"]: item for item in machine.get("network", {}).get("interfaces", [])}
    management = interfaces.get("ens18", {})
    if management.get("mtu") != 1450 or management.get("addresses") != [management_ip + "/24"]:
        fail(f"{name} patch has the wrong management network")
    if management.get("routes") != [{"network": "0.0.0.0/0", "gateway": "10.0.40.1"}]:
        fail(f"{name} patch has the wrong default route")
    expected_ceph_interface = "ens20" if name.startswith("c") else "ens19"
    if interfaces.get(expected_ceph_interface, {}).get("addresses") != [ceph[name] + "/24"]:
        fail(f"{name} patch has the wrong Ceph address")
    if interfaces[expected_ceph_interface].get("mtu") != 9000:
        fail(f"{name} patch has the wrong Ceph MTU")
    if name.startswith("c"):
        if interfaces.get("ens19", {}).get("mtu") != 1500 or not interfaces["ens19"].get("dhcp"):
            fail(f"{name} patch is missing DHCP on ens19")
    elif interfaces.get("ens20", {}).get("addresses") != [f"192.168.10.5{name[1]}/24"] or interfaces["ens20"].get("mtu") != 9000:
        fail(f"{name} patch has the wrong transit network")
    if name == "w4" and machine.get("kubelet", {}).get("extraArgs", {}).get("node-labels") != "workload.sora-lab.dev/mongodb-avx2=true":
        fail("w4 patch is missing the MongoDB AVX2 workload label")

for path in [patches / "common.yaml", patches / "roles/controlplane.yaml", patches / "roles/worker.yaml", *sorted((patches / "nodes").glob("*.yaml"))]:
    if not path.is_file():
        fail(f"required patch is missing: {path}")

print("Talos static patch validation passed for common, two roles, and seven nodes.")
PY

[[ -z $(git ls-files -- talos/generated talos/secrets/secret.yaml talos/secrets/secrets.yaml) ]] || fail "generated output or plaintext secrets are tracked by Git"
git check-ignore -q talos/generated/c1.yaml || fail "generated output is not ignored by Git"
git check-ignore -q talos/secrets/secret.yaml || fail "plaintext secrets are not ignored by Git"
git check-ignore -q talos/secrets/secrets.yaml || fail "legacy plaintext secrets are not ignored by Git"

if [[ ! -f "$secrets_file" ]]; then
  printf '%s\n' "Talos render validation skipped: secret file not found (static-only validation)."
  exit 0
fi

command -v talosctl >/dev/null 2>&1 || fail "required command is not available for render validation: talosctl"
render_dir=$(mktemp -d "$root/talos/.tmp/validate.XXXXXX")
cleanup() { rm -rf "$render_dir"; }
trap cleanup EXIT HUP INT TERM

common_patch="$patches/common.yaml"
controlplane_patch="$patches/roles/controlplane.yaml"
worker_patch="$patches/roles/worker.yaml"

talosctl gen config "k8s-soralab" "https://c.k8s.internal:6443" --with-secrets "$secrets_file" --talos-version v1.13.6 --kubernetes-version v1.36.2 --with-docs=false --with-examples=false --config-patch "@$common_patch" --config-patch-control-plane "@$controlplane_patch" --config-patch "@$patches/nodes/c1.yaml" --output-types controlplane --output "$render_dir/c1.yaml"
talosctl gen config "k8s-soralab" "https://c.k8s.internal:6443" --with-secrets "$secrets_file" --talos-version v1.13.6 --kubernetes-version v1.36.2 --with-docs=false --with-examples=false --config-patch "@$common_patch" --config-patch-control-plane "@$controlplane_patch" --config-patch "@$patches/nodes/c2.yaml" --output-types controlplane --output "$render_dir/c2.yaml"
talosctl gen config "k8s-soralab" "https://c.k8s.internal:6443" --with-secrets "$secrets_file" --talos-version v1.13.6 --kubernetes-version v1.36.2 --with-docs=false --with-examples=false --config-patch "@$common_patch" --config-patch-control-plane "@$controlplane_patch" --config-patch "@$patches/nodes/c3.yaml" --output-types controlplane --output "$render_dir/c3.yaml"
talosctl gen config "k8s-soralab" "https://c.k8s.internal:6443" --with-secrets "$secrets_file" --talos-version v1.13.6 --kubernetes-version v1.36.2 --with-docs=false --with-examples=false --config-patch "@$common_patch" --config-patch-worker "@$worker_patch" --config-patch "@$patches/nodes/w1.yaml" --output-types worker --output "$render_dir/w1.yaml"
talosctl gen config "k8s-soralab" "https://c.k8s.internal:6443" --with-secrets "$secrets_file" --talos-version v1.13.6 --kubernetes-version v1.36.2 --with-docs=false --with-examples=false --config-patch "@$common_patch" --config-patch-worker "@$worker_patch" --config-patch "@$patches/nodes/w2.yaml" --output-types worker --output "$render_dir/w2.yaml"
talosctl gen config "k8s-soralab" "https://c.k8s.internal:6443" --with-secrets "$secrets_file" --talos-version v1.13.6 --kubernetes-version v1.36.2 --with-docs=false --with-examples=false --config-patch "@$common_patch" --config-patch-worker "@$worker_patch" --config-patch "@$patches/nodes/w3.yaml" --output-types worker --output "$render_dir/w3.yaml"
talosctl gen config "k8s-soralab" "https://c.k8s.internal:6443" --with-secrets "$secrets_file" --talos-version v1.13.6 --kubernetes-version v1.36.2 --with-docs=false --with-examples=false --config-patch "@$common_patch" --config-patch-worker "@$worker_patch" --config-patch "@$patches/nodes/w4.yaml" --output-types worker --output "$render_dir/w4.yaml"
talosctl gen config "k8s-soralab" "https://c.k8s.internal:6443" --with-secrets "$secrets_file" --talos-version v1.13.6 --kubernetes-version v1.36.2 --with-docs=false --with-examples=false --output-types talosconfig --output "$render_dir/talosconfig"
talosctl --talosconfig "$render_dir/talosconfig" config endpoints 10.0.40.11 10.0.40.12 10.0.40.13

for node in c1 c2 c3 w1 w2 w3 w4; do
  [[ -s "$render_dir/$node.yaml" ]] || fail "Talos did not render $node.yaml"
done
[[ -s "$render_dir/talosconfig" ]] || fail "Talos did not render talosconfig"
printf '%s\n' "Talos static and render validation passed; outputs were written only to a temporary directory."
