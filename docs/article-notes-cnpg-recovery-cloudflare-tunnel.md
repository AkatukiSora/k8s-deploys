# Article Notes: CNPG Recovery And Cloudflare Tunnel 502

Updated: 2026-07-15 UTC

## Possible Title

`CloudNativePG + Barman Cloud復元後にCloudflare Tunnelが502になったときの調査と復旧`

## Core Story

- A connected Cloudflare Tunnel can still return `502 Bad Gateway` when Kubernetes origin Services have no ready backend.
- The visible ingress error was the final symptom, not the root cause.
- The root cause was an ownership mismatch introduced by restoring a database that retained application-specific owners into a fresh CNPG cluster whose generated application role is `app`.
- Database recovery, application readiness, Service endpoints, and external HTTP responses should be validated as one recovery chain.

## Suggested Structure

1. Environment and recovery topology
2. Why a connected Tunnel can return 502
3. Reading `cloudflared` origin errors
4. Finding the non-ready backend Pods
5. Diagnosing PostgreSQL ownership drift after recovery
6. Repairing ownership safely with `REASSIGN OWNED`
7. Revalidating EndpointSlices and external HTTP responses
8. Barman archive destination caveat during recovery
9. Recovery checklist and prevention ideas

## Technical Points To Include

- A log entry such as `dial tcp <ClusterIP>:80: connect: connection refused` identifies the origin/backend boundary as the failure point.
- `kubectl get endpointslice` is more useful than only checking that a Service exists: a ClusterIP Service can exist without ready endpoints.
- CNPG Barman recovery requires `bootstrap.recovery.source` and an `externalClusters` plugin reference.
- A Barman write destination must be empty when the plugin performs WAL archive validation. Reusing the recovery prefix as the active WAL write destination fails with `Expected empty archive`.
- Removing `isWALArchiver` is not enough if `spec.plugins` still references the same Barman object store; remove the live plugin configuration for the recovery phase while retaining `externalClusters`.
- Argo CD/AppRoot can restore the Git-managed plugin configuration after the recovery Cluster is healthy.
- Restored objects owned by `authentik`, `vikunja`, `coder`, or `grafana` are inaccessible to a newly generated CNPG `app` role until ownership is reassigned.

## Evidence Worth Capturing

- Cloudflared origin error with Service ClusterIP and origin FQDN.
- Application log examples:
  - `permission denied for schema public`
  - `must be owner of table migration`
  - `permission denied for table migration_log`
- Before/after `EndpointSlice` readiness.
- Before/after external HTTP response status:
  - Authentik: `302`
  - Grafana: `302`
  - Vikunja: `200`
  - Coder: `200`

## Commands To Present

- `kubectl logs` for `cloudflared`
- `kubectl get pods`, `service`, and `endpointslice`
- `kubectl exec ... psql` ownership inspection and repair
- `kubectl rollout restart deployment/...`
- `curl -I` for external validation

## Safety And Redaction Notes

- Do not publish 1Password vault IDs, item IDs, S3 access keys, Barman credentials, Tunnel tokens, Cloudflare Access state parameters, or private cluster addresses.
- Replace hostnames, namespaces, databases, and roles with placeholders where the deployment identity should remain private.
- State clearly that deleting a failed CNPG Cluster/PVC is only appropriate before a usable primary exists, and that backup ObjectStores and restored data PVCs must be preserved.
- Do not recommend reusing an existing Barman archive prefix as the new cluster's WAL write destination.

## Follow-up Angle

Describe a future automation improvement: a controlled post-recovery ownership reconciliation step for CNPG application databases, followed by an application readiness gate before declaring ingress recovery complete.
