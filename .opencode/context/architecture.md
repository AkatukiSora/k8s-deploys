# Architecture context

Load this file as project context, but verify every task-relevant statement against current repository files.

## Reconciliation model

The repository follows an Argo CD App-of-Apps pattern:

- `apps-root.yaml` is the root Application and references `installs/` at `targetRevision: master`.
- `installs/*.yaml` defines child Applications, commonly with automated `prune` and `selfHeal`.
- Child Applications select repository paths, upstream Helm charts, or both through multi-source `sources` entries.
- Helm Applications commonly use a repository source with `ref: repo` or `ref: values` and `$repo/...` or `$values/...` `valueFiles`.
- Automated reconciliation means committed desired state can be reflected in the cluster without a separate imperative deployment step.

## Common dependency chains

When changing a component, inspect the complete chain where applicable:

```text
apps-root.yaml
-> installs/<component>.yaml
-> Application source(s), chart, ref, and valueFiles
-> apps/<component>/...
-> Kustomization / Helm values / Kubernetes resources
-> referenced Secret, Service, PVC, RBAC, Ingress and monitoring resources
```

Kustomization directories include component overlays and security dashboards, Prometheus rules, and Kyverno policies. `OnePasswordItem` resources provide Secret material in multiple applications. CRDs and their consuming resources can have ordering requirements.

Do not assume a component is self-contained because its manifests are in one directory.

## High-risk domains

Treat the following as architecture-sensitive:

- Argo CD Application hierarchy, source paths, multi-source references, prune behavior and sync ordering;
- BGP, MetalLB, ingress, DNS and network policy;
- authentication, OIDC, Authentik, RBAC and Secret management;
- Ceph CSI, StorageClass, PVC, VolumeSnapshot and restore paths;
- VolSync, database backup, recovery and retention;
- admission policies, Pod Security and Kyverno;
- monitoring rules whose metric names or labels depend on runtime configuration.
