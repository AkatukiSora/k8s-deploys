## Summary

- Incident date: 2026-06-22
- Cluster: `admin@k8s-internal`
- Primary symptoms:
  - widespread `ImagePullBackOff` / `ErrImagePull`
  - Ceph RBD-backed workloads stuck on `FailedMount` / `FailedAttachVolume`
- Confirmed root-cause direction:
  - node DNS path to upstream resolvers is timing out
  - external routing/BGP advertisement is incomplete even though the BGP peer is established
  - Ceph had an earlier asymmetric routing problem; after that partial fix, stale CSI operations remained on `w2`

## Final Assessment

There are two related but distinct failure planes.

1. Image pull failures are caused by upstream DNS reachability failure.
2. Ceph CSI on `w2` had stale node-side stage operations; restarting the nodeplugin cleared the immediate stale lock loop, but stage operations still hang, which indicates the underlying network path is still not fully healthy.

The critical network finding is that Talos `dns-resolve-cache` on worker nodes can reach the DNS stub locally, but upstream queries do not complete reliably.

## Evidence Collected

### 1. Image pull failures are DNS failures

Observed event examples:

```text
lookup quay.io on 127.0.0.53:53: i/o timeout
lookup registry-1.docker.io on 127.0.0.53:53: i/o timeout
lookup public.ecr.aws on 127.0.0.53:53: i/o timeout
```

Affected namespaces included:

- `argocd`
- `caddy-test`
- `pjserver-sys`

### 2. Talos host DNS path is failing upstream

Commands used:

```bash
talosctl -n w2.k8s.internal get resolvers
talosctl -n w2.k8s.internal get dnsupstream
talosctl -n w2.k8s.internal logs dns-resolve-cache --tail 200
```

Key result on `w2`:

```text
read udp 10.0.40.52:<ephemeral>->10.0.40.2:53: i/o timeout
```

This proves the failure is not just Pod DNS. The worker host itself cannot complete upstream DNS queries.

### 3. Internal-only lookups can still succeed

On both `w1` and `w3`, `dns-resolve-cache` could still answer `c1.k8s.internal`, while external names repeatedly timed out.

This strongly suggests:

- local or internal name resolution still works
- recursion/forwarding to external destinations is broken

### 4. `w3` also times out against all configured upstreams

`w3` logs showed retry rotation across:

- `10.0.40.2`
- `10.0.30.100`
- `1.1.1.1`

All timed out on external lookups.

This means the issue is broader than a single bad resolver entry on `w2`.

### 5. BGP advertisement gap matches the symptoms

Additional external observation during the incident:

- UniFi BGP peering is established
- required Proxmox-side subnets are not being advertised
- expected subnets such as `10.0.10.0/24` were missing

This is consistent with partial routing convergence or missing NLRI advertisement: a session can be `Established` while advertising incomplete prefixes.

### 6. Ceph CSI stale state on `w2`

Before intervention, `w2` RBD nodeplugin logs showed:

```text
an operation with the given Volume ID ... already exists
Slow GRPC call /csi.v1.Node/NodeStageVolume (32h...)
```

Impacted workloads included:

- `cryptpad`
- `immich`
- `immich-postgres`
- `influxdb`
- `uptime-kuma`

## Actions Performed

### A. Tested a w2-only Talos DNS simplification

Goal:

- check whether extra resolver entries on `w2` were the direct cause

Method:

- temporarily changed `w2` nameservers to `10.0.40.2` only

Result:

- no recovery
- upstream lookups still timed out at `10.0.40.2:53`

Conclusion:

- resolver list drift was not the root cause
- this change was rolled back to avoid config drift

Rollback confirmation:

```bash
talosctl -n w2.k8s.internal get resolvers
```

Current restored state:

```text
["10.0.40.2","10.0.30.100","1.1.1.1"]
```

### B. Restarted `w2` RBD nodeplugin only

Command used:

```bash
kubectl -n ceph-csi delete pod ceph-csi-ceph-csi-rbd-nodeplugin-pp9t4 --wait=true --grace-period=30
kubectl -n ceph-csi wait --for=condition=Ready pod/ceph-csi-ceph-csi-rbd-nodeplugin-d68dm --timeout=180s
```

Result:

- replacement nodeplugin pod became `Ready`
- immediate `operation already exists` spam stopped
- new `NodeStageVolume` calls started from a clean process state

New behavior:

```text
Slow GRPC call /csi.v1.Node/NodeStageVolume (2m29s, 2m59s, 3m29s...)
```

Conclusion:

- stale in-memory CSI lock state was cleared
- the underlying mount/stage path is still hanging, so the backing network/storage path is not fully healthy yet

## Interpretation

### Image Pull Plane

Most likely root cause:

- upstream DNS recursion/return routing is broken outside Kubernetes/Talos
- missing BGP-advertised subnets on the Proxmox/UniFi side are the strongest explanation currently available

Important nuance:

- the failure is not limited to one node-specific resolver list
- `w2` host DNS, `w3` host DNS, and CoreDNS upstream behavior all point to external-path failure

### Ceph Plane

Most likely current state:

- the earlier asymmetric Ceph route issue was at least partially corrected
- controller-side attach progressed
- but node-side stage operations on `w2` were left stale
- after restart, they no longer fail immediately with `already exists`, but now hang, which implies the backend path needed for stage/mount is still unhealthy or partially blackholed

## Required External Fix

This incident is not fully recoverable from inside the cluster alone.

The next required action is to restore correct route advertisement / return routing on the Proxmox <-> UniFi side.

### Highest-priority items to verify externally

1. Confirm which subnets should be advertised but are missing.
2. Verify advertisement and return routing for at least:
   - `10.0.40.0/24`
   - `10.0.30.0/24`
   - `10.0.10.0/24`
   - `10.244.0.0/16`
   - `192.168.5.0/24`
   - `192.168.6.0/24`
3. Confirm that the resolver at `10.0.40.2` has working recursion/forwarding to external DNS again.
4. Confirm that Ceph public/cluster traffic does not return through an unintended Anycast Gateway / asymmetric path.

## Minimal External Verification Commands

When SSH to Proxmox node1 is available, run read-only commands similar to:

```bash
hostname
sysctl net.ipv4.tcp_l3mdev_accept net.ipv4.udp_l3mdev_accept
ip -4 rule show
ip -4 route show table all
ss -lntp | egrep '3300|6789|6800'
```

If FRR/BGP is present:

```bash
vtysh -c "show bgp summary"
vtysh -c "show ip bgp"
```

## Recovery Procedure After External Routing Is Fixed

Run these steps in order.

### 1. Re-check DNS path from Talos

```bash
talosctl -n w2.k8s.internal get dnsupstream
talosctl -n w2.k8s.internal logs dns-resolve-cache --tail 100
talosctl -n w3.k8s.internal logs dns-resolve-cache --tail 100
```

Success criteria:

- no repeated `i/o timeout` or `context deadline exceeded`
- upstream lookups complete for external names

### 2. Re-check image pull recovery

```bash
kubectl get pods -A -o wide
kubectl get events -A --sort-by=.lastTimestamp
```

Success criteria:

- `ImagePullBackOff` stops appearing for new retries
- affected Pods transition toward `Running`

### 3. Re-check Ceph stage/mount recovery

```bash
kubectl -n ceph-csi logs ceph-csi-ceph-csi-rbd-nodeplugin-d68dm -c csi-rbdplugin --since=10m
kubectl get pods -A -o wide
kubectl get volumeattachment
```

Success criteria:

- no new `already exists`
- no long-running `NodeStageVolume`
- affected workloads progress out of `ContainerCreating` / `Init:0/1`

## If Ceph Still Hangs After External Routing Is Fixed

Escalation order:

1. restart kubelet on `w2`

```bash
talosctl -n w2.k8s.internal service restart kubelet
```

2. if still stuck, inspect stale volume attachments and host-level residue on `w2`
3. if still stuck and workload policy allows it, drain/reboot `w2`

## Commands Executed During This Investigation

```bash
kubectl get pods -A -o wide
kubectl get events -A --sort-by=.lastTimestamp
kubectl get pvc -A -o wide
kubectl get volumeattachment
kubectl -n ceph-csi get pods -o wide --show-labels
kubectl -n ceph-csi logs ceph-csi-ceph-csi-rbd-nodeplugin-pp9t4 -c csi-rbdplugin --since=60m
kubectl -n ceph-csi delete pod ceph-csi-ceph-csi-rbd-nodeplugin-pp9t4 --wait=true --grace-period=30
kubectl -n ceph-csi wait --for=condition=Ready pod/ceph-csi-ceph-csi-rbd-nodeplugin-d68dm --timeout=180s
talosctl -n w1.k8s.internal get resolvers
talosctl -n w2.k8s.internal get resolvers
talosctl -n w3.k8s.internal get resolvers
talosctl -n w2.k8s.internal get dnsupstream
talosctl -n w2.k8s.internal logs dns-resolve-cache --tail 200
talosctl -n w1.k8s.internal logs dns-resolve-cache --tail 120
talosctl -n w3.k8s.internal logs dns-resolve-cache --tail 120
```

## Current Status

- DNS issue: not resolved from inside the cluster; external route/BGP correction is still required
- Ceph stale CSI lock loop: partially improved on `w2` by nodeplugin restart
- Ceph workload recovery: not yet complete; stage operations are still hanging
