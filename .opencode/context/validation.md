# Validation guidance

## Baseline

Always inspect:

- `git status --short`;
- the complete relevant `git diff`;
- changed resource identities and paths;
- references to changed names, namespaces and files.

## YAML and Kubernetes

Use tools available in the repository or environment. Typical checks include:

```bash
git diff --check
yamllint <changed paths>
kubectl kustomize <affected directory>
kustomize build <affected directory>
helm template <release> <chart> -f <values>
kubeconform -summary -strict -ignore-missing-schemas <rendered or changed manifests>
```

Do not run commands merely because they are listed here. Select commands relevant to the changed files and installed tools. The repository's current CI workflow only lints and schema-validates `installs/security-*.yaml`, `apps/security`, and the workflow itself; it does not validate general application manifests.

## Limitations to report

Explicitly report:

- ignored or unavailable CRD schemas;
- upstream charts that were not downloaded or rendered;
- Argo CD multi-source rendering behavior not evaluated;
- references that can only be resolved in the cluster;
- runtime metrics, DNS, BGP, storage, identity-provider or backup behavior not observed;
- validation commands skipped because tools were unavailable.

## Result vocabulary

Use these distinctions:

- static syntax validated;
- rendered output validated;
- cross-reference consistency reviewed;
- runtime verification required;
- not evaluable with available evidence.
