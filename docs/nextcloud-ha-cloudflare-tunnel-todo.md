# Nextcloud HA: Cloudflare Tunnel follow-up

## Status

Nextcloud and Authentik workload/database high availability is managed in this
repository. Cloudflare Tunnel redundancy is intentionally **not** managed here,
because its controller/chart is maintained in a separate repository.

## Required Cloudflare Tunnel work

Implement and validate the following in the repository that owns the
Cloudflare Tunnel controller:

1. Keep a single active tunnel controller unless its chart version documents
   leader election and active-active reconciliation.
2. Configure the controller-created `controlled-cloudflared-connector` with
   two replicas.
3. Require hostname-level anti-affinity or equivalent `DoNotSchedule`
   topology spread for connector Pods.
4. Add a connector PDB with `maxUnavailable: 0` and resource requests.
5. Preserve the existing tunnel identity, DNS records, ingress class, and
   external secret references.
6. Render the pinned chart and ensure only one owner manages every connector
   resource; do not patch a Helm/controller-owned Deployment from a second
   Argo CD source.
7. Verify two Connected connectors on distinct workers, then test external
   Nextcloud access while one connector node is unavailable.

## Dependency boundary

The Nextcloud node-loss availability target is not met until this work is
complete. It also depends on external Ceph MON quorum and storage/network
health, which cannot be guaranteed by these Kubernetes manifests alone.
