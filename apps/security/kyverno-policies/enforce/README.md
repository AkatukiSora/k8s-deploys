# Enforce Policies

This directory holds policies that block non-compliant resources instead of only
reporting them. Each policy must be listed in `../kustomization.yaml` to take
effect, and must document its scope and rollback here.

## coder-worker-sandbox

- Scope: Pods in the `coder-worker` namespace only. The webhook uses a
  `request.namespace` match condition, so `failurePolicy: Fail` does not affect
  other namespaces if Kyverno is unavailable.
- Mutates: `runtimeClassName: gvisor`, `automountServiceAccountToken: false`,
  and a default seccomp profile of `RuntimeDefault`.
- Validates: gVisor runtime, seccomp `RuntimeDefault`/`Localhost`, and CPU,
  memory, and ephemeral-storage limits.
- Rollback: remove `enforce/coder-worker-sandbox.yaml` from the kustomization.
  Pods already running keep their settings; new Pods are no longer mutated.
