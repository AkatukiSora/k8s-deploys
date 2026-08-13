# Mender OSS Server Deployment

## Deployed State

- Mender OSS is installed in the existing Kubernetes cluster with the official Helm chart.
- The deployment sets `global.enterprise: false` and publishes
  `https://mender.sora-lab.dev` through the separate Tunnel Ingress.
- Local Mender authentication is used. Authentik is not in the Mender authentication path.
- MongoDB, NATS, Redis, Mender signing keys, S3 credentials, and TLS secrets are stored in Kubernetes Secrets or the existing secret-management system.
- MongoDB is a Mender-dedicated, TLS-enabled, one-member ReplicaSet with a persistent volume.
- NATS and Redis have storage and restart behavior appropriate for this personal deployment.
- Mender accesses private Ceph RGW over the Proxmox network and uses
  `https://s3.sora-lab.dev` for public device Artifact URLs through Cloudflare
  Tunnel.
- A local break-glass Mender administrator exists and is stored in the password manager.
- The Docker Compose evaluation stack is not used by production devices.

## Known Requirements

- Mender does not support PostgreSQL. CloudNativePG cannot replace its MongoDB datastore.
- MongoDB Community Operator is the intended Kubernetes management mechanism.
- A one-member MongoDB ReplicaSet is selected to minimize personal deployment resource usage.
- Mender MongoDB connection data must be supplied through a Secret containing `MONGO` and `MONGO_URL`.
- External Ceph RGW is supplied through an S3 credentials Secret. Mender uses the private RGW URI for API operations and `https://s3.sora-lab.dev` as its signed external URI.
- The chart ingress and origin TLS are disabled; Cloudflare terminates TLS.
- The Mender Helm chart version and Mender image version must be pinned to immutable compatible releases.
- The gateway must allow Artifact upload/download durations suitable for rootfs images.
- A 309 MB GUI upload fails at the Cloudflare request-size limit. Mender's
  direct signed-upload workflow requires Enterprise, so an OSS-compatible
  upload path or Cloudflare mitigation remains required.

## Inputs Still Needed

- Kubernetes namespace, ingress class, and StorageClass names.
- MongoDB persistent-volume size, resource requests, and backup target/retention.
- NATS and Redis resource/storage choices.
- Private Ceph RGW HTTP endpoint, S3 Secret, region, and path-style setting.
- Cloudflare Tunnel hostname and maximum Artifact transfer limits.
- Mender Helm chart and image versions to pin.
- Secret delivery method, such as External Secrets, SOPS, or manually created Secrets.

## Completion Evidence

- Helm release is healthy and all Mender workloads are ready.
- Mender UI is available at the public FQDN with a valid certificate.
- A local administrator can log in and obtain a Mender management JWT.
- Basic public Mender and RGW paths are deployed; production-size Artifact
  upload/download and range-request validation remain pending.
- MongoDB backup and restore are tested before production device enrollment.
