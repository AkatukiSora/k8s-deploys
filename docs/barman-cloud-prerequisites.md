# Barman Cloud Prerequisites

Updated: 2026-07-13 UTC

## Implemented in GitOps

- `cert-manager` install application: `installs/cert-manager.yaml`
- `plugin-barman-cloud` install application: `installs/plugin-barman-cloud.yaml`
- Plugin release pin: `v0.13.0`
- Plugin image: `ghcr.io/cloudnative-pg/plugin-barman-cloud:v0.13.0`
- Sidecar image: `ghcr.io/cloudnative-pg/plugin-barman-cloud-sidecar:v0.13.0`

## Required external inputs before enabling backups on clusters

Each PostgreSQL cluster needs an object store path and S3 credentials.

Recommended B2 path layout in bucket `soras-home-k8s-backup`:

- `cnpg/immich-postgres`
- `cnpg/authentik-postgres`
- `cnpg/vikunja-postgres`
- `cnpg/coder-postgres`
- `cnpg/grafana-postgres`

Recommended `ObjectStore` names:

- `immich-postgres-barman-store`
- `authentik-postgres-barman-store`
- `vikunja-postgres-barman-store`
- `coder-postgres-barman-store`
- `grafana-postgres-barman-store`

Recommended 1Password item names and required keys:

- `k8s-barman-s3-immich-postgres`
- `k8s-barman-s3-authentik-postgres`
- `k8s-barman-s3-vikunja-postgres`
- `k8s-barman-s3-coder-postgres`
- `k8s-barman-s3-grafana-postgres`

For each item, create these keys:

- `ACCESS_KEY_ID`
- `ACCESS_SECRET_KEY`
- `ENDPOINT_URL`
- `DESTINATION_PATH`

Suggested values:

- `ENDPOINT_URL`: `https://s3.us-west-004.backblazeb2.com`
- `DESTINATION_PATH`: `s3://soras-home-k8s-backup/cnpg/<cluster-name>`

Optional additional key if you want to set region explicitly:

- `AWS_REGION`

## Next repo changes after item IDs are available

1. Add `OnePasswordItem` for each cluster's Barman credential secret.
2. Add `ObjectStore` resources in the same namespaces as the target CNPG clusters.
3. Add `spec.plugins` with `isWALArchiver: true` to each `Cluster`.
4. Add `ScheduledBackup` with `method: plugin` for each cluster.
5. Add restore overlays/runbooks for scratch recovery and PITR.
