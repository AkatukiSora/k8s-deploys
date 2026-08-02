# Validation guidance

## Baseline

Inspect:

- `git status --short`;
- the complete relevant diff;
- changed resource identities and paths;
- references to changed names, namespaces, files, ports, labels, selectors,
  Secrets, PVCs, and Application sources.

## Typical static checks

Select only relevant installed tools:

```bash
git diff --check
yamllint <changed paths>
kubectl kustomize <affected directory>
kustomize build <affected directory>
helm template <release> <chart> -f <values>
kubeconform -summary -strict -ignore-missing-schemas <manifests>
```

## Report limitations

Explicitly report:

- ignored or unavailable CRD schemas;
- charts not downloaded or rendered;
- ApplicationSet or templating behavior not evaluated;
- references resolvable only in the cluster;
- runtime DNS, BGP, storage, identity-provider, metrics, or backup behavior not observed;
- checks skipped because tools were unavailable.

Use precise terms:

- static syntax validated;
- rendered output validated;
- cross-reference consistency reviewed;
- runtime verification required;
- not evaluable with available evidence.
