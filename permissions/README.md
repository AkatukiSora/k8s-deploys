# Permissions

This directory contains cluster and Argo CD permission manifests that should not live under `installs/`.

Scope:

- Argo CD projects and RBAC configuration
- Future Kubernetes RBAC manifests for tenant/platform separation

Non-goals:

- Application installation definitions
- Tenant workload manifests

`installs/permissions.yaml` is the Argo CD entrypoint for this directory.
