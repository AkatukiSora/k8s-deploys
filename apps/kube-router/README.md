# kube-router service proxy

This Application runs kube-router v2.10.0 only as the Kubernetes Service proxy.
Flannel pod networking, MetalLB BGP, service load-balancer allocation, firewalling,
CNI management, and NetworkPolicy implementation remain outside this Application.

## Cutover

1. Generate and statically validate MachineConfigs with `talos-validate`; confirm every
   control-plane and worker config contains `cluster.proxy.disabled: true`.
2. Review the Argo diff and sync this Application first. Confirm the kube-router DaemonSet is
   scheduled on every node, including control planes, with its init container waiting for the
   existing kube-proxy. Do not sync the staged MetalLB unmatched-UDP reject yet.
3. Apply the generated Talos MachineConfigs to all nodes in a planned all-node cutover; the
   waiting init containers then clean up kube-proxy nftables state and start kube-router.
4. Confirm every kube-router pod is Ready and no host kube-proxy process remains.
5. Validate Service traffic, nftables/IPVS state, and existing Flannel pod routing.
   Only after post-IPVS validation may the staged MetalLB unmatched-UDP reject be deployed.

## Rollback

1. Revert or remove this Application from Argo CD management and wait for kube-router to stop;
   its termination cleanup removes kube-router service rules.
2. Remove or revert the `proxy.yaml` reference in `talos/scripts/generate.sh`.
3. Regenerate all MachineConfigs and apply them to all nodes to restore Talos-managed kube-proxy.
4. Confirm kube-proxy is running and validate Service traffic before restoring any optional
   MetalLB UDP-reject change.

## Validation

Static validation covers YAML syntax, Application path references, the narrow RBAC watch scope,
and generated Talos proxy-disabled assertions. Runtime validation must be performed after the
all-node cutover; repository validation does not prove service traffic or nftables behavior.
