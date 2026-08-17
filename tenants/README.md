# Tenant Manifests

Each tenant should live under either:

- `tenants/platform/<tenant>/`
- `tenants/workloads/<tenant>/`

Current rollout rules:

- `Tenant Owner` is mapped by OIDC group through Capsule.
- `Tenant User` receives namespaced `edit` permissions only.
- Tenant namespaces must use the tenant prefix because `forceTenantPrefix=true` is enabled in Capsule.
- Tenant workloads cannot create `OnePasswordItem` resources.
- Tenant workloads cannot create Argo CD `Application` or `ApplicationSet` resources.
- Argo CD `AppProject` objects are platform-managed.

Use `tenants/_template/` as the starting point for a new tenant.
