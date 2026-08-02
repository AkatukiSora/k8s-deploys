# Architecture context

Verify every task-relevant statement against current repository files.

## Reconciliation model

The repository follows an Argo CD App-of-Apps pattern:

- the root Application references `installs/`;
- child Applications select repository paths and/or upstream Helm charts;
- committed desired state may be reconciled without an imperative deployment step.

## Common dependency chain

```text
apps-root.yaml
-> installs/<component>.yaml
-> Application source(s)
-> apps/<component>/...
-> Kustomization / Helm values / Kubernetes resources
-> referenced Secret, Service, PVC, RBAC, Ingress and monitoring resources
```

Do not assume a component is self-contained because its files share a directory.

## Architecture-sensitive domains

- Argo CD hierarchy, source paths, prune, and sync ordering;
- BGP, MetalLB, ingress, DNS, and network policy;
- authentication, OIDC, Authentik, RBAC, certificates, and secrets;
- Ceph CSI, StorageClass, PVC, snapshots, and restore paths;
- VolSync, database backup, recovery, and retention;
- admission policies, Pod Security, and Kyverno;
- monitoring rules dependent on runtime metric names and labels.
