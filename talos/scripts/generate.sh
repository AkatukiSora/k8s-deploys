#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
patches="$root/talos/patches"
secrets_file="${TALOS_SECRETS_FILE:-$root/talos/secrets/secret.yaml}"
output_dir="${TALOS_OUTPUT_DIR:-$root/talos/generated}"
node="${1:-}"

fail() {
  printf '%s\n' "error: $*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: mise run talos-generate -- <node>

Renders one untracked Talos MachineConfig into talos/generated/<node>.yaml.
Nodes: c1 c2 c3 w1 w2 w3 w4

Environment:
  TALOS_SECRETS_FILE  Path to the existing cluster secrets.yaml.
  TALOS_OUTPUT_DIR    Output directory (default: talos/generated).
EOF
}

case "$node" in
  c1|c2|c3|w1|w2|w3|w4) ;;
  -h|--help|"") usage; exit 0 ;;
  *) fail "unknown node: $node" ;;
esac

command -v talosctl >/dev/null 2>&1 || fail "required command is not available: talosctl"
[[ -f "$secrets_file" ]] || fail "Talos secrets file not found: $secrets_file"

mkdir -p "$output_dir"

args=(
  gen config "k8s-soralab" "https://c.k8s.internal:6443"
  --with-secrets "$secrets_file"
  --talos-version v1.13.6
  --kubernetes-version v1.36.2
  --with-docs=false
  --with-examples=false
  --config-patch "@$patches/common.yaml"
)

if [[ "$node" == c* ]]; then
  args+=(--config-patch-control-plane "@$patches/roles/controlplane.yaml" --output-types controlplane)
else
  args+=(--config-patch-worker "@$patches/roles/worker.yaml" --output-types worker)
fi

args+=(--config-patch "@$patches/nodes/$node.yaml" --output "$output_dir/$node.yaml" --force)
talosctl "${args[@]}"

printf 'Rendered %s\n' "$output_dir/$node.yaml"
