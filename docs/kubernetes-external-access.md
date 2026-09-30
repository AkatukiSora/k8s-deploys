# Kubernetes external access

This document defines the desired state for safe external access to the
Kubernetes API. It does not authorize a direct Internet publication of TCP
6443 and it does not replace the Management LAN break-glass path.

## Trust boundaries

```text
External Cloudflare One Client
  -> Cloudflare Access / Gateway
  -> Cloudflare Tunnel private route
  -> Kubernetes API VIP: 10.0.40.99:6443
  -> Authentik OIDC
  -> Kubernetes RBAC
```

Cloudflare determines whether a device and identity may use the private network
path. Kubernetes independently verifies an Authentik OIDC token and applies
RBAC. Neither decision substitutes for the other.

## Authentik assignments

Assign people only through `team:*` groups:

| Assignment | Effect |
| --- | --- |
| `team:k8s-external` | Baseline Cloudflare One enrollment, private Kubernetes Access eligibility, and external WARP profile selection; no Kubernetes API privileges |
| `team:k8s-external-viewer` | Baseline external access plus `app:k8s:cluster:viewer`, bound to a custom cluster-wide read-only role |
| `team:k8s-external-operator` | Baseline external access plus `app:k8s:cluster:operator`; inert until a namespace owner adds a Git-managed `RoleBinding` |
| `team:owner` | Existing `app:k8s:cluster:admin` path; use only for designated administrators |

The Kubernetes OIDC scope mapping exposes only `app:k8s:*`; Cloudflare's OIDC
scope mapping exposes only `app:cloudflare:*`. The groups cannot cross the
boundary through a token claim. Authentik group membership is additive, so the
role teams are not mutually exclusive: never assign both external role teams to
a person. If an exception is needed, document the intended effective privilege
and verify it with a fresh OIDC token before enabling access.

## Kubernetes RBAC

`apps/security/kubernetes-rbac/rbac.yaml` creates:

- a cluster-wide custom viewer binding to `oidc:app:k8s:cluster:viewer`;
- a reusable `authentik-kubernetes-operator` ClusterRole;
- a cluster-admin binding only for `oidc:app:k8s:cluster:admin`.

The operator role intentionally has **no** `ClusterRoleBinding`. Bind it with a
`RoleBinding` in each approved namespace, for example:

```yaml
subjects:
  - kind: Group
    name: oidc:app:k8s:cluster:operator
roleRef:
  kind: ClusterRole
  name: authentik-kubernetes-operator
```

Do not bind it cluster-wide. It permits workload scaling and updates, job
execution, logs, exec, and port-forward in the namespace where it is bound.

## External client configuration

Use `setup-template/kubeconfig-external-oidc.yaml`. It deliberately uses
`https://10.0.40.99:6443`, because the API certificate has the VIP as an IP SAN.
This avoids distributing private DNS to external users. The kubeconfig contains
only the cluster CA and OIDC exec configuration; it contains no client
certificate, private key, password, or static token.

## Required Cloudflare desired state

Cloudflare IaC belongs under `cloudflare/`. The planned resources are:

1. A dedicated `k8s-api-private` tunnel with at least two connectors outside
   the Kubernetes failure domain.
2. A `10.0.40.99/32` private route on that tunnel. It is more specific than the
   existing `10.0.0.0/8` route and must not alter that existing route.
3. A private Access application for TCP `10.0.40.99:6443`, allowing only
   Authentik claim `app:cloudflare:resource:kubernetes:access`, with
   Cloudflare One Client authentication enabled.
4. An `external-k8s` device profile that is selected by
   `app:cloudflare:profile:external-kubernetes`, uses Split Tunnel Include
   mode, and includes only the API VIP plus the documented Cloudflare control
   plane IPs required by Traffic only mode.
5. Gateway Network Allow and lower-priority Block policies for TCP/6443, and a
   TLS Do Not Inspect exception if TLS inspection is enabled in the future.
6. Authentik-to-Cloudflare SCIM with user and group-membership deprovisioning.

The existing Cloudflare account currently has dashboard-managed resources.
Before applying changes, import the existing profiles, Access applications,
policies, IdP, tunnel routes, and Gateway rules into Terraform state and verify
an empty plan. Do not use the temporary read-only discovery token for writes.

## Rollout and rollback

1. Deploy Authentik groups and Kubernetes RBAC, with no user assignment.
2. Import Cloudflare state and add the dedicated tunnel and `/32` route.
3. Enable SCIM, then verify the synchronized external profile group on one
   pilot identity.
4. Create the profile, Access application, and Gateway policies for that pilot.
5. Test OIDC authentication, viewer denial of writes, long-lived Kubernetes
   connections, and general Internet/DNS bypass from the pilot device.

Rollback by removing the pilot's `team:k8s-external` membership, revoking its
Cloudflare session, and removing the namespace RoleBinding if present. Keep the
Management LAN direct path and break-glass credential independent of Authentik,
Cloudflare, and the tunnel.