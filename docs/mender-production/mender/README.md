# Free Mender on Kubernetes

The repository deploys the MongoDB Community Operator v0.13.0, a protected
`mender` namespace, a single-member operator-managed MongoDB ReplicaSet, and
Mender OSS chart 8.2.0 (application 4.1.3). The independently removable
`mender-publication` Application publishes the core at `mender.sora-lab.dev`.

Cloudflare terminates TLS; Tunnel-to-gateway HTTP is intentional. Existing
tunnel configuration and hosts are immutable. No origin TLS, cert-manager,
credential-copy Job, transformed Secret, or Retain StorageClass is used.

## Production services

The chart's bundled MongoDB and ingress are disabled. The operator-generated
`mender-mongodb-connection` Secret is referenced directly by every rendered
Mender MongoDB consumer through component `customEnvs`. The MongoDB password is
projected from the configured 1Password item and no password is stored in Git.

Artifact storage uses the private `sora-lab-mender` Backblaze B2 bucket through
its S3-compatible endpoint. Credentials are synchronized directly from the
`mender-backblaze-b2` 1Password item into the `mender-artifacts-b2` Secret; the
bucket name is held in the same-named ConfigMap. No credential is stored in
Git. The prior `mender-artifacts` RGW ObjectBucketClaim remains declared and
protected against Argo prune/delete as a rollback path; do not delete it during
routine operations.

Mender uses path-style S3 URLs:

```text
DEPLOYMENTS_AWS_URI=https://s3.us-west-004.backblazeb2.com
DEPLOYMENTS_AWS_EXTERNAL_URI=https://s3.us-west-004.backblazeb2.com
DEPLOYMENTS_AWS_BUCKET=sora-lab-mender
DEPLOYMENTS_AWS_FORCE_PATH_STYLE=true
```

The API gateway storage proxy is disabled. Mender workloads and devices use the
B2 S3 endpoint. Secret values remain in external secret systems.

The OSS deployment does not provide Mender Enterprise's direct signed-upload
workflow. A 309 MB GUI upload still fails at the Cloudflare request-size limit
before it reaches B2. Do not treat this configuration as validated for
production-size browser uploads. An OSS-compatible upload path or Cloudflare
mitigation is required before device Artifact releases.

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
