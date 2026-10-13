# Ceph traffic stall caused by reverse-path filtering on a VRF bridge

## Summary

Kubernetes worker nodes could establish neither stable Ceph MON/OSD
communication nor RBD-backed PVC provisioning. The immediate cause was
reverse-path filtering (`rp_filter`) on the Proxmox node's `vrfbr_main`
receive path. The traffic entered through a VRF/bridge path whose reverse
route did not resolve through the same interface, so the kernel dropped it.

The permanent fix was not to globally disable `rp_filter`. Ceph traffic was
moved to a dedicated Layer 2 VLAN (`192.168.8.0/24`) with a dedicated Talos
interface on every Kubernetes node. This gives the Ceph client and MON/OSD
traffic a symmetric, directly routed path and removes the former Kubernetes
subnet SNAT rule.

## Impact

- Ceph CSI RBD provisioning and attach operations could stall or time out.
- Existing RBD clients retained old MON/OSD sessions after the endpoint
  migration, contributing to severe host I/O pressure until node1 restarted.
- CSI errors such as `DeadlineExceeded` and `operation already exists` were
  secondary symptoms caused by operations waiting on an unhealthy network
  path; they were not the original fault.

## Evidence for the cause

### The service was not simply down

Ceph daemons were running, and node-local checks did not explain the failure.
The failure depended on the source network and the receiving host/path, which
is characteristic of routing or host packet validation rather than a stopped
MON or OSD.

### Disabling reverse-path validation changed the result

During a bounded test, setting `rp_filter=0` on the affected receive path
allowed an infrastructure LXC connection to a Ceph OSD port to succeed. The
previous value was restored after the test. This isolated reverse-path
validation as the packet-drop mechanism without leaving a broad security
relaxation in place.

### The topology had an asymmetric path

The Kubernetes network and Ceph endpoint network crossed VRF/bridge routing
domains. A packet's ingress interface and the interface selected by the
reverse route lookup could differ. Strict reverse-path filtering rejects that
traffic before the target application can use it.

This is especially easy to create with a combination of:

- Linux VRFs and policy routing;
- bridge/VXLAN or EVPN forwarding;
- Kubernetes Pod networks and host networking;
- SNAT that obscures the original source or changes the return path.

## Why this looked like a storage failure

RBD provisioning is a chain of operations rather than a single MON request:

1. The CSI controller contacts MONs to create or locate an image.
2. The nodeplugin maps and mounts the RBD image on the worker.
3. The kernel RBD client communicates with OSDs on their dynamically assigned
   TCP ports.

Any break in that chain can produce generic CSI timeout, attach, mount, or
stale-operation errors. Testing only TCP `3300` or `6789` is insufficient:
working MON connectivity does not prove OSD data connectivity.

## Permanent remediation

The deployed design is:

- Ceph public and cluster networks: `192.168.8.0/24`.
- Proxmox node interfaces: `192.168.8.101` and `192.168.8.102`.
- Talos worker/control-plane Ceph interfaces: dedicated VLAN 8 NICs with MTU
  9000.
- Ceph MON endpoints in Ceph CSI configuration: VLAN 8 addresses.
- Kubernetes subnet SNAT: removed.

This makes a worker's RBD client communicate directly on VLAN 8. A validation
write from worker `w1` showed packets from `192.168.8.51` directly to OSDs at
`192.168.8.101/.102` on ports such as `6802` and `6812`; the Proxmox NAT
POSTROUTING chain had no SNAT rule.

## Reusable diagnostic procedure

Use this sequence for Ceph, DNS, BGP, ingress, or other failures that may be
caused by asymmetric routing.

### 1. Establish the exact failing flow

Record all five relevant properties:

- source namespace, Pod, node, and source IP;
- destination service, node, and destination IP/port;
- ingress interface on the destination host;
- reverse route selected on that host;
- whether NAT changes either direction.

Do not conclude from a successful host-local check that a remote client can
reach the same socket.

### 2. Observe the destination host

Capture on the actual ingress interface, not only the expected bridge:

```bash
tcpdump -ni <ingress-interface> 'host <source-ip> and host <destination-ip>'
ip route get <source-ip> from <destination-ip> iif <ingress-interface>
ip rule show
ip route show table all
```

Interpretation:

- No SYN on the destination host: investigate the upstream path.
- SYN arrives but no normal response: inspect host firewall, policy routing,
  `rp_filter`, VRF socket settings, and local routes.
- SYN/RST from the destination host: the packet reached the host, but local
  delivery or socket selection rejected it.
- Connection succeeds only when `rp_filter` is relaxed: treat asymmetric
  routing as the defect; do not stop at the temporary workaround.

### 3. Check reverse-path filtering explicitly

```bash
sysctl net.ipv4.conf.all.rp_filter
sysctl net.ipv4.conf.default.rp_filter
sysctl net.ipv4.conf.<ingress-interface>.rp_filter
```

For VRF systems, also inspect the VRF master, bridge, VLAN, and physical
interfaces. Per-interface values can differ from the global defaults.

`rp_filter=1` is strict and requires the reverse route to use the receiving
interface. `rp_filter=2` is loose and only requires a route to exist. A
temporary `0` test can prove the mechanism, but it is not a safe default
remediation for a multi-tenant or exposed network.

### 4. Verify the complete protocol path

For Ceph RBD, test both control and data paths:

```bash
# MON v2/v1 and an OSD-port range test from the actual client node
nc -vz -w2 <mon-ip> 3300
nc -vz -w2 <mon-ip> 6789
nc -vz -w2 <osd-ip> 6800

# Confirm dynamic provisioning, node mount, and data I/O.
kubectl get pvc -A -o wide
kubectl get volumeattachment
kubectl -n ceph-csi logs deploy/<rbd-provisioner> -c csi-rbdplugin --since=30m
```

For non-Ceph services, use the equivalent application transaction instead of
only a port probe. A TCP handshake alone does not prove that return traffic,
authentication, or data-plane connections work.

### 5. Remove stale secondary state only after fixing the path

Network recovery may leave stale CSI operations, kernel RBD sessions, or
client retries. Restarting CSI or a node before confirming the path can hide
the evidence without fixing the defect. Once direct connectivity is verified,
restart only the affected component and validate its normal operation.

## Preventive design rules

- Keep storage traffic on a dedicated, documented network when practical.
- Avoid relying on SNAT for east-west storage traffic; it hides the real
  client and makes reverse-path analysis harder.
- Treat VRF, NAT, routing policy, and firewall changes as one flow design,
  including the return route.
- Include source-address and interface assertions in storage migration tests.
- Test a fresh PVC, mount, and write/read operation after any Ceph network
  change. Existing mounted volumes can conceal a broken new-client path.
- Record both MON and OSD endpoints in validation evidence.

## Current validation result

After the VLAN 8 migration:

- Ceph MON quorum and all OSDs were up.
- All placement groups were `active+clean`.
- Ceph CSI provisioner and nodeplugin workloads were ready.
- A newly created RBD PVC was provisioned, mounted on `w1`, written, and read
  successfully.
- Packet capture confirmed the direct, non-SNAT VLAN 8 OSD path.

The cluster still reported the pre-existing `too many PGs per OSD` health
warning. It is capacity/tuning work and is unrelated to this traffic stall.
