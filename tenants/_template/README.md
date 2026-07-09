# Tenant Template

Replace every `__TENANT__` placeholder before applying these manifests.

Files:

- `tenant-owner.yaml`: maps the OIDC owner group into Capsule ownership.
- `tenant.yaml`: creates the Capsule tenant and grants tenant users the built-in `edit` role in tenant namespaces.
- `argocd-project.yaml`: platform-managed Argo CD project definition and project-scoped RBAC groups.

Group model:

- Kubernetes owner group: `oidc:app:k8s:tenant:__TENANT__:owner`
- Kubernetes user group: `oidc:app:k8s:tenant:__TENANT__:user`
- Argo CD admin group: `app:argocd:project:__TENANT__:admin`
- Argo CD sync group: `app:argocd:project:__TENANT__:sync`
- Argo CD readonly group: `app:argocd:project:__TENANT__:readonly`

Expected namespace examples:

- `__TENANT__-dev`
- `__TENANT__-staging`
- `__TENANT__-prod`
