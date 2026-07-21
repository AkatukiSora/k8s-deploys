# CNPG Recovery And External Ingress Runbook

Updated: 2026-07-15 UTC

## Scope

This runbook covers recovery of the CNPG databases backed up with Barman Cloud and the resulting Cloudflare Tunnel `502 Bad Gateway` investigation.

Affected CNPG clusters:

- `authentik/authentik-postgres`
- `coder/coder-postgres`
- `immich-postgres/immich-postgres`
- `vikunja/vikunja-postgres`
- `monitoring/grafana-postgres`

## Recovery Order

1. Restore VolSync PVCs and wait for every `ReplicationDestination` to report `Successful`.
2. Create required namespaces, 1Password items, generated Secrets, and Barman `ObjectStore` resources.
3. Create each CNPG `Cluster` with `bootstrap.recovery.source: backup`.
4. Wait for every cluster to report `Cluster in healthy state` with `Ready 1/1`.
5. Deploy `apps-root.yaml`.
6. Verify the Git-managed Barman plugin configuration has reconciled and every cluster remains healthy.
7. Start and validate application backends before treating external ingress as recovered.

Do not deploy application workloads before their databases are healthy. This avoids application initialization against an incomplete recovery.

## Barman Recovery With Existing Archives

The Barman Cloud plugin checks its write destination before a recovery job starts. A cluster cannot use the existing recovery archive as its WAL archive destination: the plugin fails with:

```text
WAL archive check failed for server <cluster>: Expected empty archive
```

`isWALArchiver: false` alone is insufficient when `spec.plugins` still contains the Barman `barmanObjectName`; the recovery job still performs the destination check.

For a temporary recovery that must read from the existing archive and cannot use a distinct write prefix:

1. Remove `spec.plugins` from the live `Cluster` resource.
2. Retain `spec.externalClusters`; it supplies the Barman plugin and read-only recovery source.
3. If failed recovery Jobs have exhausted retries, delete the uninitialized Cluster and its CNPG-created PVC, then recreate the Cluster without `spec.plugins`.
4. After recovery is healthy, deploy AppRoot so Argo CD restores the Git-managed plugin configuration.

Example live-only patch:

```bash
kubectl -n <namespace> patch cluster <cluster> --type=json \
  -p='[{"op":"remove","path":"/spec/plugins"}]'
```

Only delete a Cluster/PVC after confirming that recovery did not create a usable primary. Preserve `ObjectStore`, Barman credentials, and VolSync-restored PVCs.

After AppRoot reconciles, verify both the Cluster state and plugin configuration:

```bash
kubectl get clusters.postgresql.cnpg.io -A
kubectl get cluster.postgresql.cnpg.io -A \
  -o jsonpath='{range .items[*]}{.metadata.namespace}{"/"}{.metadata.name}{" plugins="}{range .spec.plugins[*]}{.name}{":"}{.isWALArchiver}{end}{"\n"}{end}'
```

## Restored Database Ownership

CNPG creates the default application role `app`. The recovered databases retained their original object owners (`authentik`, `vikunja`, `coder`, and `grafana`), while workloads connect with the generated `app` role.

Symptoms include:

```text
permission denied for schema public
must be owner of table migration
permission denied for table migration_log
```

Repair ownership as the CNPG `postgres` superuser. Substitute the database and restored owner for the affected application:

```bash
kubectl -n <namespace> exec <cluster>-1 -c postgres -- \
  psql -v ON_ERROR_STOP=1 -U postgres -d <database> \
  -c 'REASSIGN OWNED BY <restored-owner> TO app;' \
  -c 'ALTER DATABASE <database> OWNER TO app;' \
  -c 'ALTER SCHEMA public OWNER TO app;' \
  -c 'GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO app;' \
  -c 'GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO app;'
```

Applied mappings in this recovery:

| Namespace | Database | Restored owner | Target role |
| --- | --- | --- | --- |
| `authentik` | `authentik` | `authentik` | `app` |
| `vikunja` | `vikunja` | `vikunja` | `app` |
| `coder` | `coder` | `coder` | `app` |
| `monitoring` | `grafana` | `grafana` | `app` |

Restart the affected deployments after the grants. Confirm their Pods are Ready and their Services have ready EndpointSlices.

## Cloudflare Tunnel 502 Diagnosis

Cloudflare Tunnel `502 Bad Gateway` with a connected connector means `cloudflared` cannot reach the configured origin. It is not itself evidence of tunnel failure.

Inspect the connector logs:

```bash
kubectl -n cloudflare-tunnel-ingress-controller logs \
  deploy/controlled-cloudflared-connector --since=15m
```

The incident produced errors such as:

```text
dial tcp <service-cluster-ip>:80: connect: connection refused
originService=http://authentik-server.authentik.svc.cluster.local:80
```

This points to the Kubernetes backend, not Cloudflare routing. Check the backend in this order:

```bash
kubectl get pods -n <namespace>
kubectl get endpointslice -n <namespace> \
  -l kubernetes.io/service-name=<service>
kubectl logs -n <namespace> <pod> --previous
```

The recovered application Pods must be Ready before the Service accepts connections. In this incident, fixing restored PostgreSQL ownership made the Authentik, Vikunja, Coder, and Grafana backends Ready and eliminated the 502 responses.

## External Validation

Use HTTP status responses to validate the complete path through Cloudflare, Tunnel, Service, and backend:

```bash
curl -I --max-time 15 https://auth.akatuki-host.com
curl -I --max-time 15 https://grafana.akatuki-host.com
curl -I --max-time 15 https://vikunja.akatuki-host.com
curl -I --max-time 15 https://coder.akatuki-host.com
```

Expected successful responses can be `200 OK` or an application authentication redirect such as `302 Found`; they must not be Cloudflare `502`.
