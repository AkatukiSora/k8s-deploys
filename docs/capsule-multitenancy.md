# Capsule Multi-Tenancy Rollout

This document captures the first rollout phase for Capsule-based multi-tenancy.

## Current Decisions

- Namespace ownership is implemented with Capsule.
- `forceTenantPrefix=true` is enabled, so tenant namespaces must start with the tenant name.
- `Tenant Owner` is driven by OIDC group membership and mapped through `TenantOwner` resources.
- `Tenant User` is driven by OIDC group membership and gets namespaced `edit` permissions only.
- Tenant namespaces must not create `OnePasswordItem` resources.
- `soras-tenant` is a temporary exception for existing applications that manage
  `OnePasswordItem` resources through GitOps.
- Tenant namespaces must not create Argo CD `Application` or `ApplicationSet` resources.
- Argo CD `AppProject` resources are platform-managed.

## OIDC Groups

Kubernetes API groups use the API server prefix and therefore appear as `oidc:*` subjects inside RBAC and Capsule resources.

- `oidc:app:k8s:tenant:<tenant>:owner`
- `oidc:app:k8s:tenant:<tenant>:user`

Argo CD consumes the groups claim directly from its own OIDC provider.

- `app:argocd:project:<tenant>:admin`
- `app:argocd:project:<tenant>:sync`
- `app:argocd:project:<tenant>:readonly`

## Argo CD Layout

- Root app stays on the `default` project.
- The `default` project is reduced to root-app duties only:
  - source repo is this repository only
  - destination is `argocd` namespace only
  - allowed resources are `Application` and `AppProject` only
- All existing platform applications move to the `platform` project.
- Tenant projects are declared separately and can expose logs through project roles, but tenants still cannot create `Application` manifests themselves in this phase.

## 1Password Guardrail

`OnePasswordItem` is intentionally excluded from tenant self-service.

Reasons:

- A shared operator would otherwise allow a tenant to try syncing secrets outside its intended scope.
- Namespace RBAC on `Secret` is not enough if the tenant can drive the external secret fetch itself.

The current phase therefore keeps `OnePasswordItem` under platform-only management.

## Adding a Tenant

1. Copy `tenants/_template` to `tenants/<tenant>`.
2. Replace every `__TENANT__` placeholder.
3. Extend Authentik blueprints with the new Kubernetes and Argo CD groups.
4. Add or update the team-to-app parent relations in Authentik.
5. Apply the tenant manifests.
6. Add platform-managed Argo CD `Application` manifests into the tenant `AppProject` if needed.
