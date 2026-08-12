# Nextcloud high-availability operations

## Availability contract

The desired state provides node-loss resilience only after all of these
conditions hold:

- Nextcloud and Authentik application replicas are Available on different
  worker nodes.
- Each CNPG cluster has three healthy instances on distinct worker nodes and a
  synchronous standby.
- The `*-rw` service has a promoted primary after a controlled failover.
- External Ceph MON quorum, CephFS/RBD health, and the storage network are
  healthy.
- Cloudflare Tunnel redundancy described in
  `nextcloud-ha-cloudflare-tunnel-todo.md` is complete.

The PostgreSQL RPO=0 target applies only to loss of one worker while the
synchronous standby and Ceph are healthy. It does not cover a Ceph-wide,
object-store, site, or correlated network failure.

## CNPG rollout gates

Apply the Nextcloud and Authentik PostgreSQL changes one cluster at a time.
Before advancing, confirm:

1. All three Pods are Ready, each on a distinct worker, with distinct RBD PVCs.
2. `kubectl get cluster -n <namespace>` reports three ready instances.
3. `pg_stat_replication` from the primary shows a synchronous standby.
4. The Cluster reports continuous archiving and successful backup.
5. Trigger a plugin Backup and verify it completes. The scheduled backup uses
   `prefer-standby`, with primary fallback when no suitable standby exists.
6. Perform a planned failover in an approved maintenance test and verify both
   WAL archiving and a subsequent plugin backup from the new topology.

If no synchronous standby is available, investigate and restore it before
weakening the policy. Disabling synchronous replication abandons the RPO=0
target and requires an explicit operational decision.

## Nextcloud application rollout gates

The Nextcloud chart is configured for two web Pods with a Kubernetes CronJob,
not a cron sidecar. Confirm that the generated CronJob is the only scheduled
`cron.php` executor and that both web Pods mount the existing RWX CephFS PVC.

Before treating the service as node-loss tolerant, test login, OIDC token
refresh, WebDAV, upload/download, concurrent file locking, and access through
the external URL while one web Pod is unavailable. Confirm that the Nextcloud
PDB permits one voluntary disruption and that another Ready endpoint remains.

## Version upgrades

Do not perform a Nextcloud application or database schema upgrade with mixed
web application versions. For upgrades:

1. Enable Nextcloud maintenance mode.
2. Require successful pre-upgrade CephFS snapshot and CNPG Backup.
3. Temporarily set the web Deployment to one replica and `Recreate`.
4. Run the upgrade and repairs, then validate the application.
5. Restore two replicas and the `RollingUpdate` strategy, wait for both Ready
   endpoints, then disable maintenance mode.

Leave maintenance mode enabled if an upgrade or repair fails.
