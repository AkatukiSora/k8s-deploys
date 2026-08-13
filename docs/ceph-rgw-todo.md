# Ceph RGW TODO

Updated: 2026-08-14

## Completed

- RGW is running on node2 and bound to `192.168.8.102:7480`.
- Internal and Cloudflare Tunnel endpoints support path-style SigV4 requests.
- Rook external CephCluster and external RGW ObjectStore are GitOps-managed.
- 1Password Operator supplies the external Ceph and RGW Admin Ops credentials.
- An ObjectBucketClaim created a bucket and credentials; private upload and
  public presigned GET returned HTTP `200`.
- Existing `ceph-csi` remains separate from Rook and owns RBD/CephFS PVC
  provisioning.
- The Mender Artifact bucket is provisioned through an ObjectBucketClaim and
  Mender is configured with private and Cloudflare-proxied public RGW
  endpoints.

## Remaining

- [ ] Replace temporary `s3-rgw.pve.internal` host mappings with authoritative
  DNS.
- [ ] Move PVE/LXC RGW networking, CoreDNS, and Cloudflare Tunnel configuration
  into infrastructure-as-code.
- [ ] Decide and implement a TCP/7480 firewall policy if required.
- [ ] Investigate expired presigned URL responses returning HTTP `500`.
- [ ] Define RGW HA topology and migration plan.
- [ ] Investigate an OSS-compatible Mender Artifact upload path or Cloudflare
  mitigation; Mender direct signed upload requires Enterprise.
- [ ] A 309 MB Mender GUI upload currently fails at the Cloudflare request-size
  limit. Test production-size download, range requests, and Cloudflare cache
  behavior after selecting the upload path.
- [ ] Rotate the Cloudflare Tunnel token if it is exposed through a systemd
  command line.
