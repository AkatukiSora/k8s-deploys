# Free Mender on Kubernetes

The repository deploys the MongoDB Community Operator v0.13.0, a protected
`mender` namespace and `mender-artifacts` ObjectBucketClaim, a single-member
operator-managed MongoDB ReplicaSet, and finally Mender OSS chart 8.2.0
(application 4.1.3). The independently removable `mender-publication`
Application publishes the core at `mender.sora-lab.dev`.

Cloudflare terminates TLS; Tunnel-to-gateway HTTP is intentional. Existing
tunnel configuration and hosts are immutable. No origin TLS, cert-manager,
credential-copy Job, transformed Secret, or Retain StorageClass is used.

## Production services

The chart's bundled MongoDB and ingress are disabled. The operator-generated
`mender-mongodb-connection` Secret is referenced directly by every rendered
Mender MongoDB consumer through component `customEnvs`. The MongoDB password is
projected from the configured 1Password item and no password is stored in Git.

Artifact storage uses the existing `rook-ceph-external-rgw` StorageClass. The
OBC-generated Secret and ConfigMap are referenced directly by Mender
`customEnvs`; no credential-copy or transformed Secret is used. The accepted
StorageClass Delete reclaim risk is documented and the OBC is annotated against
Argo prune/delete. Backup and restore design is deferred before production data
is accepted.

Mender uses path-style S3 URLs:

```text
DEPLOYMENTS_AWS_URI=http://192.168.8.102:7480
DEPLOYMENTS_AWS_EXTERNAL_URI=https://s3.sora-lab.dev
DEPLOYMENTS_AWS_BUCKET=mender-artifacts
DEPLOYMENTS_AWS_FORCE_PATH_STYLE=true
```

The API gateway storage proxy is disabled. The private URI is for Mender
workloads and the public URI is for device Artifact URLs. Secret values remain
in external secret systems.

The OSS deployment does not provide Mender Enterprise's direct signed-upload
workflow. A 309 MB GUI upload currently fails at the Cloudflare request-size
limit; `s3.sora-lab.dev` is also Cloudflare-proxied. Do not treat the current
configuration as validated for production-size browser uploads. An
OSS-compatible upload path or Cloudflare mitigation is required before device
Artifact releases.

## Rollback and validation

Remove `mender-publication` to withdraw the hostname while leaving core state
intact. Stop/remove core only after device and data maintenance planning; do
not delete the OBC or namespace during routine rollback. Static validation
renders all Kustomizations and the pinned Helm chart, checks resource identity,
direct mappings, and absence of chart MongoDB/ingress/TLS/fake credential
resources. Runtime DNS, Cloudflare connector labels, OBC-generated keys,
operator readiness, storage, production-size upload/download and range
requests, and backup restore still require cluster checks.

Keep one tested local Mender break-glass administrator. Do not apply Authentik
forward-auth to device or artifact paths.
