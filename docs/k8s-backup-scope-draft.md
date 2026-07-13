# Kubernetes Backup Scope Draft

Updated: 2026-07-13 UTC

## Included

### Barman / CNPG

| Namespace         | Resource             | Reason                                              |
| ----------------- | -------------------- | --------------------------------------------------- |
| `immich-postgres` | `immich-postgres`    | Immich metadata and application state               |
| `authentik`       | `authentik-postgres` | Authentication data for multiple apps               |
| `vikunja`         | `vikunja-postgres`   | Vikunja task data                                   |
| `coder`           | `coder-postgres`     | Coder workspace definitions and control-plane state |
| `monitoring`      | `grafana-postgres`   | Grafana users, dashboards, and auth-related state   |

### VolSync / Restic

| Namespace    | Resource                                                                                       | Reason                                                             |
| ------------ | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `immich`     | `immich-library`                                                                               | Photo and video library data                                       |
| `vikunja`    | `vikunja-data`                                                                                 | Vikunja persistent application data                                |
| `monitoring` | `prometheus-kube-prometheus-stack-prometheus-db-prometheus-kube-prometheus-stack-prometheus-0` | Monitoring history and externally used Prometheus state            |
| `monitoring` | Alertmanager PVC                                                                               | Alertmanager silences and notification state                       |
| `influxdb`   | `influx-db-influxdb2`                                                                          | InfluxDB data, auth bootstrap state, and external access use cases |

## Excluded

| Namespace      | Resource                     | Reason                                                |
| -------------- | ---------------------------- | ----------------------------------------------------- |
| `cryptpad`     | `cryptpad-pvc`               | Application planned for removal                       |
| `uptime-kuma`  | `uptime-kuma-pvc`            | Application planned for removal                       |
| `uptime-kuma`  | `data-uptime-kuma-mariadb-0` | Application planned for removal                       |
| `coder-worker` | workspace home PVCs          | Disposable per-user workspace storage                 |
| `nextcloud`    | all PVCs                     | Not currently in use; planned migration to CNPG later |
| `nextcloud`    | redis PVCs                   | Rebuildable cache/queue data                          |

## Pending

| Namespace  | Resource                                       | Current view                                                          |
| ---------- | ---------------------------------------------- | --------------------------------------------------------------------- |
| `influxdb` | `influx-db-influxdb-data-influx-db-influxdb-0` | Likely an old leftover PVC; current `influxdb2` pod does not mount it |

## Notes

- Snapshot implementation starts with RBD only because all currently included PVC workloads are on `ceph-rbd`.
- CephFS snapshot support can be added later if a future in-scope workload requires it.
- Immich should be restored as a recovery set: `immich-library` snapshot plus `immich-postgres` PITR.
