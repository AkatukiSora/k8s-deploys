# Ceph RGW Runbook

Updated: 2026-08-14

## Scope

This runbook covers the external Proxmox-managed Ceph RGW used by Kubernetes
workloads. Rook manages RGW buckets, users, and ObjectBucketClaims; it does
not manage Ceph daemons, MONs, OSDs, RGW networking, or Cloudflare Tunnel.

## Endpoints

- Provider RGW: `192.168.8.102:7480` on node2.
- Internal endpoint: `http://s3-rgw.pve.internal:7480`.
- Public endpoint: `https://s3.sora-lab.dev` through Cloudflare Tunnel.
- S3 requests use path-style addressing and SigV4.
- RGW is private. Cloudflare Tunnel must preserve the request host, path,
  method, query string, and every `X-Amz-*` parameter.
- `s3.sora-lab.dev` is Cloudflare-proxied. Its request-size limit prevents a
  309 MB Mender OSS GUI Artifact upload; the Mender API upload path is also
  Cloudflare-proxied. Mender Enterprise direct signed upload is not available
  in the current OSS deployment.

## Rook External Cluster

- Argo CD Application: `rook-ceph-external`.
- Namespace: `rook-ceph`.
- Operator: Rook `v1.18.6` with RBD and CephFS CSI disabled. Existing
  `ceph-csi` charts remain the only provisioners for PVC storage.
- External CephCluster: `rook-ceph-external`.
- External CephObjectStore: `external-rgw` at `192.168.8.102:7480`.
- ObjectBucketClaim StorageClass: `rook-ceph-external-rgw`.

Rook requires these Kubernetes Secrets, all synchronized by 1Password
Operator. Do not commit their values.

| Secret | Purpose | Required fields |
| --- | --- | --- |
| `rook-ceph-mon` | External cluster metadata | `admin-secret`, `fsid`, `mon-secret` |
| `rook-ceph-operator-creds` | CephX health-check identity | `userID`, `userKey` |
| `rgw-admin-ops-user` | RGW Admin Ops API | `accessKey`, `secretKey` |

`client.healthchecker` and the RGW Admin Ops user are provider-Ceph
identities. GitOps synchronizes their existing credentials to Kubernetes; it
does not create or recreate those identities in Ceph.

## Workload Bucket Provisioning

Create an ObjectBucketClaim in the workload namespace with
`storageClassName: rook-ceph-external-rgw`. A successful claim creates a
bucket, an RGW user, a credential Secret, and a ConfigMap containing the
bucket endpoint and name.

```yaml
apiVersion: objectbucket.io/v1alpha1
kind: ObjectBucketClaim
metadata:
  name: example-bucket
  namespace: example-workload
spec:
  generateBucketName: example-bucket
  storageClassName: rook-ceph-external-rgw
```

Use the private endpoint for in-cluster S3 API operations. To issue public
presigned URLs, sign path-style requests against `https://s3.sora-lab.dev`.
An unsigned public request must remain rejected.

## Verification

```bash
kubectl get application rook-ceph-external -n argocd
kubectl get cephcluster rook-ceph-external -n rook-ceph
kubectl get cephobjectstore external-rgw -n rook-ceph
kubectl get storageclass rook-ceph-external-rgw
```

Expected states are Argo CD `Synced Healthy`, CephCluster `Connected`, and
CephObjectStore `Ready`.

An OBC smoke test verified bucket creation, private S3 upload, and a public
presigned GET through `s3.sora-lab.dev` with HTTP `200`. Delete temporary OBCs
and their namespaces after testing so the generated bucket and credentials are
removed.

## Provider Ceph Health

- Ceph FSID: `5bef1c02-f871-4b70-ba18-c6cce8221916`.
- MON endpoints: `192.168.8.101:3300` and `192.168.8.102:3300`.
- `mon_max_pg_per_osd` is configured as `300`.
- `mon_target_pg_per_osd` is configured as `100`.

Before changing PG settings or removing maintenance flags, inspect:

```bash
ceph health detail
ceph osd pool autoscale-status
ceph config show mon.node1 mon_max_pg_per_osd
ceph config show mon.node2 mon_max_pg_per_osd
```

## Deferred Infrastructure

- Replace temporary CoreDNS and cloudflared hosts entries for
  `s3-rgw.pve.internal` with authoritative DNS.
- Put PVE RGW service configuration, VRF local route, CoreDNS host entry, and
  Cloudflare Tunnel configuration in dedicated infrastructure-as-code.
- Define a restrictive TCP/7480 firewall policy if connectivity requirements
  demand one.
- Add HAProxy, a VIP, and multiple RGW daemons without changing the internal
  FQDN.
- Investigate RGW's HTTP `500 UnknownError` response for expired presigned
  URLs; valid presigned requests are verified.
- Rotate the Cloudflare Tunnel token if its systemd invocation exposes it in
  process or status output.
