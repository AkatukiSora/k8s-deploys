# `k8s-deploys` agent rules

## Repository purpose

This repository is a GitOps source for a Kubernetes environment reconciled by Argo CD. Treat repository changes as operational changes, not merely text edits.

## High-level structure

- `apps-root.yaml` is the root Argo CD Application and points to `installs/`.
- `installs/*.yaml` primarily defines child Argo CD Applications.
- `apps/<component>/` contains component manifests, Helm values, Kustomize resources, policies, dashboards, scripts, or documentation.
- Many Applications use Argo CD multi-source: an upstream Helm chart plus this repository as a `ref` source for `$repo/...` or `$values/...` Helm value files, and sometimes a repository path containing additional manifests.
- Some areas use Kustomize, so inclusion in `kustomization.yaml` is part of correctness.
- OnePassword `OnePasswordItem` resources are used for Secret material; do not introduce plaintext secret values.

Inspect the current repository before relying on these summaries. Current files are authoritative.

## GitOps safety

Argo CD automated reconciliation commonly includes `prune` and `selfHeal`. Therefore:

- deletion, rename, namespace change, `kind` change, or Application source-path change may delete live resources;
- a file move is not automatically a harmless refactor;
- temporary coexistence and migration ordering must be explicit for networking, storage, authentication, backup, and database changes;
- identify rollback requirements before implementing a potentially destructive change.

## Secret handling

- Never add plaintext passwords, access tokens, private keys, recovery keys, or secret values.
- Follow existing external-secret or Secret-reference patterns.
- Do not print secret values in reports or validation output.

## Working-tree discipline

- Preserve unrelated user changes.
- Inspect `git status` and the relevant diff before editing.
- Do not commit, push, reset, switch branches, rebase, or rewrite history unless the user explicitly requests it.
- Only one implementation agent may write to the same working tree at a time.

## Cluster interaction

The normal workflow is repository-only and static-validation-only. Read-only
cluster inspection is permitted when task scope and credentials are appropriate.
Live-cluster writes are permitted only through the dedicated
`luna-cluster-operator` agent invoked explicitly by Terra for a stated live
operation.

Do not run live-cluster mutation commands outside `luna-cluster-operator`, including:

- `kubectl apply`, `create`, `replace`, `delete`, `patch`, or `edit`;
- `helm upgrade`, `install`, or `uninstall`;
- `argocd app sync` or destructive Argo CD operations.

The dedicated operator must receive the target context, namespace, exact intended
operation, success criteria, and rollback or recovery action before a mutation.
Do not claim runtime verification from static manifests.

## Validation principles

Use the narrowest relevant validation and expand when appropriate:

1. inspect the semantic diff;
2. run `git diff --check`;
3. parse or lint modified YAML;
4. run `kubectl kustomize` or `kustomize build` for affected Kustomizations;
5. run `helm template` for affected chart/value combinations where practical;
6. run `kubeconform` when schemas are available;
7. search for dangling resource names, paths, namespaces, ports, labels, selectors, Secret references, PVC references, and Application source references.

The repository CI workflow, `.github/workflows/security-ci.yaml`, runs `yamllint` and `kubeconform` only for security manifests. It is not repository-wide validation. A validator passing with missing CRD schemas does not prove that custom resources are correct.

## Agent responsibilities

- Terra owns user intent, task scope, final judgment, and final response.
- Sol handles difficult decisions, but normally delegates changes to Luna or returns `DELEGATION_REQUIRED` to Terra.
- Luna Context gathers and compresses evidence without editing.
- Luna Implement performs one bounded, decided implementation contract.
- Luna Verify independently reviews the working-tree diff without editing.
- Luna Cluster Operator performs explicitly requested live-cluster reads or
  writes without modifying repository files.

When an agent without cluster write permission identifies a necessary live
mutation, it must complete remaining safe non-mutating work and return a
`DELEGATION_REQUIRED` packet to Terra. Only Terra can then invoke the dedicated
cluster operator.

The detailed behavior of each agent is defined in `.opencode/agents/`.
