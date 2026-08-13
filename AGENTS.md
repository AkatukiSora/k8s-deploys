# `k8s-deploys` agent rules

This repository is an Argo CD GitOps source. Treat repository changes as
operational changes, not merely text edits.

## Agent routing

- Build and Plan own the user conversation, task scope, final judgment, and final response.
- Explore uses Luna for high-volume read-only investigation.
- General uses Sol for non-trivial architecture and design decisions.
- Luna Implement performs one coarse-grained, already-decided change.
- Luna Verify independently checks high-risk changes.

Use the shortest safe path. Do not invoke every agent by default.

Delegate high-I/O work when it requires broad cross-file searches, substantial
history or documentation review, large logs or rendered output, or repetitive
coherent edits across several files. Keep isolated one- or two-file work in the
primary agent when delegation overhead would be larger than the work.

Send architecture decisions to General/Sol. Do not ask Luna to invent a design.

## Repository shape

- `apps-root.yaml` is the root Argo CD Application and points to `installs/`.
- `installs/*.yaml` primarily defines child Argo CD Applications.
- `apps/<component>/` contains component manifests, Helm values, Kustomize
  resources, policies, dashboards, scripts, or documentation.
- Some Applications combine an upstream Helm chart with files in this repository.
- Some components use Kustomize; inclusion in `kustomization.yaml` is part of correctness.

Inspect current files before relying on this summary.

## GitOps safety

Automated reconciliation may include prune and self-heal. Treat deletion,
rename, namespace or kind change, Application source-path change, and rendered
resource removal as potentially destructive.

Networking, storage, authentication, backup, and database changes require
explicit migration ordering, observability, and rollback where material.

## Secrets

Never add or print plaintext passwords, tokens, private keys, recovery keys, or
secret values. Follow existing external-secret and secret-reference patterns.

## Working tree

- Preserve unrelated user changes.
- Inspect `git status` and the relevant diff before editing.
- Only one writer agent may modify a working tree at a time.
- Do not commit, push, reset, switch branches, or rewrite history unless the user explicitly requests it.
- Never bypass commit signing or create an unsigned commit unless the user explicitly authorizes that exception. If signing is unavailable, stage intended repository changes, continue independent safe work, and leave the repository ready for a later signed commit; do not reset, amend, or otherwise rewrite history without explicit approval.

## Cluster interaction

Default to repository-only work and static validation. Do not mutate the live
cluster with `kubectl apply/delete/patch/edit`, Helm install/upgrade/uninstall,
or Argo CD sync operations unless explicitly requested and separately scoped.

Static manifests do not prove runtime behavior.

For temporary runtime or diagnostic changes, use explicitly scoped cluster commands rather than committing transient desired-state changes to Git. Record the command, observed result, and required reconciliation before ending the task.

### Temporary live-cluster changes

Argo CD self-heal overwrites out-of-band changes. When a temporary `kubectl`
change is necessary, temporarily disable self-heal **only** for the affected
Application, apply and verify the change, then restore self-heal before ending
the operation. Record the Application, exact commands, purpose, observed
result, restoration confirmation, and the Git-managed reconciliation required.
Do not disable automated prune unless the operation specifically requires it
and its deletion risk has been reviewed.

Before treating a live change as risky, inspect the deployed workload and its
data path rather than assuming its impact from the manifest alone. For example,
an uninitialised service with no users, devices, or application data may permit
a disruptive restart or reset; a deployed service with persistent data requires
an explicit impact assessment, backup/recovery consideration, and a rollback
plan. Record the observed basis for that decision.

## Context files

Load these only when relevant:

- `.opencode/context/architecture.md`
- `.opencode/context/invariants.md`
- `.opencode/context/validation.md`
- `.opencode/context/operations.md`
