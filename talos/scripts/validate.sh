#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cluster_file="$root/talos/cluster/config.json"
inventory_file="$root/talos/inventory/nodes.json"

fail() {
  printf '%s\n' "error: $*" >&2
  exit 1
}

command -v jq >/dev/null 2>&1 || fail "required command is not available: jq"
command -v talosctl >/dev/null 2>&1 || fail "required command is not available: talosctl"

jq -e '(.nodes | length) > 0' "$inventory_file" >/dev/null || fail "inventory has no nodes"
vip=$(jq -r '.vip' "$cluster_file")
qemu_guest_agent_schematic=$(jq -r '.proxmox.qemuGuestAgentSchematic' "$cluster_file")
[[ $(jq -r '([.nodes[].name] | length) == ([.nodes[].name] | unique | length)' "$inventory_file") == true ]] || fail "duplicate hostname in inventory"
[[ $(jq -r '([.nodes[].management.address] | length) == ([.nodes[].management.address] | unique | length)' "$inventory_file") == true ]] || fail "duplicate management IP in inventory"
[[ $(jq -r '([.nodes[].ceph.address] | length) == ([.nodes[].ceph.address] | unique | length)' "$inventory_file") == true ]] || fail "duplicate Ceph IP in inventory"
[[ $(jq -r '([.nodes[].ceph.macAddress] | length) == ([.nodes[].ceph.macAddress] | unique | length)' "$inventory_file") == true ]] || fail "duplicate Ceph MAC in inventory"

[[ $(jq -r --arg vip "$vip" '[.nodes[].management.address | split("/")[0]] | index($vip) == null' "$inventory_file") == true ]] || fail "VIP duplicates a node IP"
[[ $(jq -r '.kubernetesEndpoint | contains("c.k8s.internal")' "$cluster_file") == true ]] || fail "Kubernetes endpoint must use c.k8s.internal"
[[ $(jq -r '.talosVersion != "" and .kubernetesVersion != ""' "$cluster_file") == true ]] || fail "Talos and Kubernetes versions must be set"
[[ $(jq -r '[.nodes[] | select(.role == "controlplane") | .management.interface] | unique | length == 1' "$inventory_file") == true ]] || fail "control plane VIP interfaces differ"
[[ $(jq -r '(.managementNetwork.dnsServers | length) == (.managementNetwork.dnsServers | unique | length)' "$cluster_file") == true ]] || fail "duplicate DNS server in common configuration"
[[ $(jq -r 'all(.nodes[]; ([.dhcpInterfaces[].interface] | length) == ([.dhcpInterfaces[].interface] | unique | length))' "$inventory_file") == true ]] || fail "duplicate DHCP interface in node configuration"
[[ $(jq -r 'all(.nodes[]; .ceph.address | startswith("192.168.8."))' "$inventory_file") == true ]] || fail "Ceph IPs must use 192.168.8.0/24"
[[ $(jq -r 'all(.nodes[]; . as $node | .ceph.mtu == 9000 and .ceph.interface != .management.interface and ([.dhcpInterfaces[].interface] | index($node.ceph.interface) | not))' "$inventory_file") == true ]] || fail "invalid Ceph interface configuration"
[[ $(jq -r 'all(.nodes[]; if .role == "worker" then (.transit.address != null and .transit.interface != null and .transit.mtu == 9000) else (.transit == null) end)' "$inventory_file") == true ]] || fail "transit is required only for workers and must use MTU 9000"
[[ $(jq -r 'all(.nodes[]; if .role == "worker" then (.transit.address | startswith("192.168.10.") and endswith("/24")) else true end)' "$inventory_file") == true ]] || fail "transit IPs must use 192.168.10.0/24"
[[ $(jq -r '([.nodes[] | select(.role == "worker") | .transit.address] | length) == ([.nodes[] | select(.role == "worker") | .transit.address] | unique | length)' "$inventory_file") == true ]] || fail "duplicate transit IP in inventory"
[[ $(jq -r '([.nodes[] | select(.role == "worker") | (.transit.macAddress | ascii_downcase)] | length) == ([.nodes[] | select(.role == "worker") | (.transit.macAddress | ascii_downcase)] | unique | length)' "$inventory_file") == true ]] || fail "duplicate transit MAC in inventory"
[[ $(jq -r 'all(.nodes[]; . as $node | if .role == "worker" then (.transit.interface != .management.interface and .transit.interface != .ceph.interface and ([.dhcpInterfaces[].interface] | index($node.transit.interface) | not)) else true end)' "$inventory_file") == true ]] || fail "transit interface conflicts with another network interface"

expected_nodes=$(jq -r '.nodes | length' "$inventory_file")
controlplanes=$(jq -r '[.nodes[] | select(.role == "controlplane")] | length' "$inventory_file")
[[ $controlplanes -eq 3 ]] || fail "exactly three control planes are required"

TALOS_SECRETS_FILE="${TALOS_SECRETS_FILE:-}" bash "$root/talos/scripts/generate.sh"

for config in "$root"/talos/generated/*.yaml; do
  name=${config##*/}
  content=$(<"$config")
  [[ "$content" == version:\ v1alpha1* && "$content" == *$'\nmachine:'* ]] || fail "$name is not a generated MachineConfig"
  [[ "$content" == *$'\n    proxy:\n        disabled: true'* ]] || fail "$name does not disable the Talos cluster proxy"
  [[ "$content" == *"factory.talos.dev/installer/$qemu_guest_agent_schematic"* ]] || fail "$name is missing the QEMU guest-agent installer image"
  if [[ $name == c*.yaml ]]; then
    [[ "$content" == *"kind: Layer2VIPConfig"* && "$content" == *"name: $vip"* ]] || fail "$name is missing the control plane VIP"
  else
    [[ "$content" != *"Layer2VIPConfig"* ]] || fail "$name must not contain a VIP"
  fi
  node=${name%.yaml}
  ceph_address=$(jq -r --arg node "$node" '.nodes[] | select(.name == $node) | .ceph.address' "$inventory_file")
  ceph_interface=$(jq -r --arg node "$node" '.nodes[] | select(.name == $node) | .ceph.interface' "$inventory_file")
  [[ "$content" == *"- $ceph_address"* && "$content" == *"interface: $ceph_interface"* ]] || fail "$name is missing the Ceph interface"
  transit_address=$(jq -r --arg node "$node" '.nodes[] | select(.name == $node) | .transit.address // empty' "$inventory_file")
  transit_interface=$(jq -r --arg node "$node" '.nodes[] | select(.name == $node) | .transit.interface // empty' "$inventory_file")
  if [[ -n "$transit_address" ]]; then
    [[ "$content" == *"- $transit_address"* && "$content" == *"interface: $transit_interface"* ]] || fail "$name is missing the transit interface"
  else
    [[ "$content" != *"192.168.10."* ]] || fail "$name must not contain the worker transit address"
  fi
done

[[ -f "$root/talos/generated/talosconfig" ]] || fail "talosconfig was not generated"
mapfile -t controlplane_ips < <(jq -r '.nodes[] | select(.role == "controlplane") | .management.address | split("/")[0]' "$inventory_file")
talosconfig=$(<"$root/talos/generated/talosconfig")
for ip in "${controlplane_ips[@]}"; do
  [[ "$talosconfig" == *"$ip"* ]] || fail "talosconfig is missing control plane endpoint $ip"
done
[[ "$talosconfig" != *"$vip"* ]] || fail "talosconfig must not use the VIP"

first_hashes=$(mktemp)
second_hashes=$(mktemp)
cleanup() {
  rm -f "$first_hashes" "$second_hashes"
}
trap cleanup EXIT HUP INT TERM

# talosconfig contains a newly issued client certificate on every generation.
# It is intentionally excluded from MachineConfig determinism checks.
(cd "$root/talos/generated" && sha256sum ./*.yaml) | sort >"$first_hashes"
TALOS_SECRETS_FILE="${TALOS_SECRETS_FILE:-}" bash "$root/talos/scripts/generate.sh"
(cd "$root/talos/generated" && sha256sum ./*.yaml) | sort >"$second_hashes"
if ! cmp -s "$first_hashes" "$second_hashes"; then
  diff -u "$first_hashes" "$second_hashes" >&2 || true
  fail "MachineConfig generation is not deterministic"
fi

[[ -z $(git ls-files -- talos/generated talos/secrets/secrets.yaml) ]] || fail "generated output or plaintext secrets are tracked by Git"
git check-ignore -q talos/generated/c1.yaml || fail "generated output is not ignored by Git"
git check-ignore -q talos/secrets/secrets.yaml || fail "plaintext secrets are not ignored by Git"

generated_count=$(set -- "$root"/talos/generated/*.yaml; printf '%s\n' "$#")
[[ $generated_count -eq $expected_nodes ]] || fail "generated node count does not match inventory"
printf 'Talos static validation passed for %s nodes.\n' "$expected_nodes"
