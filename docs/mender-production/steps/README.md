# Deployment and follow-up workstreams

The production work is split into independent workstreams. The Mender OSS
deployment and external MongoDB/RGW integration are deployed; remaining work
concerns upload-limit mitigation and production Artifact-path validation.

1. [Cloudflare Tunnel publication](02-cert-manager-dns.md)
2. [Mender Server](03-mender-server.md)
3. [Raspberry Pi Mender integration](04-rpi3-mender-integration.md)

Shared decisions already made:

- Mender OSS Helm deployment; `global.enterprise: false`.
- Local Mender authentication; no Authentik SSO integration.
- Existing Kubernetes cluster on Proxmox.
- Public Mender FQDN: `mender.sora-lab.dev`.
- Cloudflare Tunnel publication; no Mender cert-manager resource.
- Existing Ceph RGW is S3-compatible Artifact and general-purpose object storage.
  See the [Ceph RGW runbook](../../ceph-rgw-runbook.md) and
  [Ceph RGW TODO](../../ceph-rgw-todo.md).
- New Mender environment; no migration from the Docker Compose evaluation stack.
- One-member Kubernetes MongoDB ReplicaSet with backup and restore testing.

These files must not contain passwords, private keys, S3 keys, Cloudflare API tokens, or generated certificates.
