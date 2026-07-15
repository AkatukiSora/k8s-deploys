#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cluster_file="$root/talos/cluster/config.json"
inventory_file="$root/talos/inventory/nodes.json"
requested_node="${1:-}"

fail() {
  printf '%s\n' "error: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "required command is not available: $1"
}

require_command jq
require_command talosctl
[[ -n "${TALOS_SECRETS_FILE:-}" ]] || fail "TALOS_SECRETS_FILE must point to the secrets.yaml downloaded from 1Password"
[[ -f "$TALOS_SECRETS_FILE" ]] || fail "TALOS_SECRETS_FILE does not exist: $TALOS_SECRETS_FILE"

secrets_file=$(realpath "$TALOS_SECRETS_FILE")
case "$secrets_file" in
  "$root/talos/secrets/secrets.yaml") ;;
  "$root"/*) fail "TALOS_SECRETS_FILE must be outside the repository or talos/secrets/secrets.yaml" ;;
esac

jq -e '
  .clusterName != "" and
  .talosVersion != "" and
  .kubernetesVersion != "" and
  (.kubernetesEndpoint | startswith("https://")) and
  .vip != "" and
  .proxmox.qemuGuestAgentSchematic != "" and
  (.managementNetwork.dnsServers | length > 0)
' "$cluster_file" >/dev/null || fail "cluster configuration is incomplete"

if [[ -n "$requested_node" ]]; then
  jq -e --arg node "$requested_node" '.nodes[] | select(.name == $node)' "$inventory_file" >/dev/null || fail "unknown node: $requested_node"
  node_filter=(--arg node "$requested_node" '.nodes[] | select(.name == $node)')
else
  node_filter=('.nodes[]')
fi

cluster_name=$(jq -r '.clusterName' "$cluster_file")
talos_version=$(jq -r '.talosVersion' "$cluster_file")
kubernetes_version=$(jq -r '.kubernetesVersion' "$cluster_file")
kubernetes_endpoint=$(jq -r '.kubernetesEndpoint' "$cluster_file")
vip=$(jq -r '.vip' "$cluster_file")
qemu_guest_agent_schematic=$(jq -r '.proxmox.qemuGuestAgentSchematic' "$cluster_file")
gateway=$(jq -r '.managementNetwork.gateway' "$cluster_file")

mapfile -t controlplane_interfaces < <(jq -r '.nodes[] | select(.role == "controlplane") | .management.interface' "$inventory_file" | sort -u)
[[ ${#controlplane_interfaces[@]} -eq 1 ]] || fail "all control planes must use one management interface for the VIP"
vip_interface=${controlplane_interfaces[0]}

mkdir -p "$root/talos/.tmp" "$root/talos/generated"
stage=$(mktemp -d "$root/talos/.tmp/generate.XXXXXX")
output_dir="$stage/output"
mkdir "$output_dir"
cleanup() {
  [[ -z "$stage" ]] || rm -rf "$stage"
}
trap cleanup EXIT HUP INT TERM

common_patch="$root/talos/patches/common/network.yaml"
controlplane_patch="$root/talos/patches/controlplane/oidc.yaml"
worker_patch="$root/talos/patches/worker/common.yaml"
vip_patch="$stage/layer2-vip.yaml"
proxmox_patch="$stage/proxmox-qemu-guest-agent.yaml"
cat >"$vip_patch" <<EOF
apiVersion: v1alpha1
kind: Layer2VIPConfig
name: $vip
link: $vip_interface
EOF
cat >"$proxmox_patch" <<EOF
machine:
  install:
    image: factory.talos.dev/installer/$qemu_guest_agent_schematic:$talos_version
EOF

render_node_patch() {
  local node_json="$1"
  local output="$2"
  local name address interface mtu disk
  name=$(jq -r '.name' <<<"$node_json")
  address=$(jq -r '.management.address' <<<"$node_json")
  interface=$(jq -r '.management.interface' <<<"$node_json")
  mtu=$(jq -r '.management.mtu' <<<"$node_json")
  disk=$(jq -r '.installDisk' <<<"$node_json")

  cat >"$output" <<EOF
machine:
  network:
    interfaces:
      - interface: $interface
        mtu: $mtu
        addresses:
          - $address
        routes:
          - network: 0.0.0.0/0
            gateway: $gateway
EOF

  jq -r '.dhcpInterfaces[] | [.interface, .mtu] | @tsv' <<<"$node_json" |
    while IFS=$'\t' read -r dhcp_interface dhcp_mtu; do
      cat >>"$output" <<EOF
      - interface: $dhcp_interface
        mtu: $dhcp_mtu
        dhcp: true
EOF
    done

  cat >>"$output" <<EOF
  install:
    disk: $disk
---
apiVersion: v1alpha1
kind: HostnameConfig
hostname: $name
auto: off
EOF
}

generate_node() {
  local node_json="$1"
  local name role node_patch extra_patch output_type
  name=$(jq -r '.name' <<<"$node_json")
  role=$(jq -r '.role' <<<"$node_json")
  extra_patch=$(jq -r '.patch' <<<"$node_json")
  node_patch="$stage/$name.node.yaml"
  render_node_patch "$node_json" "$node_patch"

  case "$role" in
    controlplane)
      output_type=controlplane
      talosctl gen config "$cluster_name" "$kubernetes_endpoint" \
        --with-secrets "$secrets_file" \
        --talos-version "$talos_version" \
        --kubernetes-version "$kubernetes_version" \
        --with-docs=false \
        --with-examples=false \
        --config-patch "@$common_patch" \
        --config-patch "@$proxmox_patch" \
        --config-patch-control-plane "@$controlplane_patch" \
        --config-patch-control-plane "@$vip_patch" \
        --config-patch "@$node_patch" \
        --config-patch "@$root/talos/$extra_patch" \
        --output-types "$output_type" \
        --output "$output_dir/$name.yaml"
      ;;
    worker)
      output_type=worker
      talosctl gen config "$cluster_name" "$kubernetes_endpoint" \
        --with-secrets "$secrets_file" \
        --talos-version "$talos_version" \
        --kubernetes-version "$kubernetes_version" \
        --with-docs=false \
        --with-examples=false \
        --config-patch "@$common_patch" \
        --config-patch "@$proxmox_patch" \
        --config-patch-worker "@$worker_patch" \
        --config-patch "@$node_patch" \
        --config-patch "@$root/talos/$extra_patch" \
        --output-types "$output_type" \
        --output "$output_dir/$name.yaml"
      ;;
    *) fail "node $name has an invalid role: $role" ;;
  esac
}

while IFS= read -r node_json; do
  generate_node "$node_json"
done < <(jq -c "${node_filter[@]}" "$inventory_file")

if [[ -z "$requested_node" ]]; then
  talosctl gen config "$cluster_name" "$kubernetes_endpoint" \
    --with-secrets "$secrets_file" \
    --talos-version "$talos_version" \
    --kubernetes-version "$kubernetes_version" \
    --with-docs=false \
    --with-examples=false \
    --output-types talosconfig \
    --output "$output_dir/talosconfig"

  mapfile -t controlplane_ips < <(jq -r '.nodes[] | select(.role == "controlplane") | .management.address | split("/")[0]' "$inventory_file")
  talosctl --talosconfig "$output_dir/talosconfig" config endpoints "${controlplane_ips[@]}"
fi

if [[ -z "$requested_node" ]]; then
  replacement="$root/talos/.tmp/generated.$RANDOM"
  mv "$output_dir" "$replacement"
  previous="$root/talos/.tmp/generated.previous.$RANDOM"
  if [[ -e "$root/talos/generated" ]]; then
    mv "$root/talos/generated" "$previous"
  fi
  mv "$replacement" "$root/talos/generated"
  rm -rf "$previous"
else
  mv "$output_dir/$requested_node.yaml" "$root/talos/generated/$requested_node.yaml"
fi

printf 'Generated Talos MachineConfig%s.\n' "${requested_node:+ for $requested_node}"
