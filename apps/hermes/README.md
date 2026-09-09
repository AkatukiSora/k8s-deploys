# Hermes Agent bootstrap

This is an intentionally internal-only, manually synchronized bootstrap for
Hermes Agent. The child Argo CD Application has no automated sync policy:
creation of `installs/hermes.yaml` creates the Application, but an operator
must review and synchronize its resources before the workload starts.

## Security boundary

- The image is pinned to the official `v2026.9.7` multi-architecture image
  digest. Do not replace it with a floating tag.
- There is no Service, Ingress, dashboard, API exposure, Kubernetes API token,
  host mount, or privileged mode. The Discord gateway accepts only the users
  stored in the 1Password-managed `hermes-discord` Secret.
- NetworkPolicy denies all ingress and egress by default. Hermes may resolve
  DNS through `kube-system` and make TCP/443 connections only to public IPv4
  addresses. It cannot access RFC1918, loopback, link-local, shared-address,
  documentation, multicast, or reserved IPv4 ranges. IPv6 egress is denied.
- `/opt/data` is the only persistent path. It holds Hermes configuration,
  memory, skills, sessions, and ChatGPT/Codex OAuth credentials. It is a
  `ReadWriteOnce` Ceph RBD volume and the Deployment uses `Recreate`; never
  run a second Hermes gateway against this volume.

The official image starts its s6 supervisor as root to prepare `/opt/data` and
then runs Hermes services as UID/GID 10000. The container is not privileged,
cannot escalate privileges, uses the RuntimeDefault seccomp profile, and drops
all Linux capabilities before adding only the capabilities required for that
documented bootstrap. Runtime acceptance must verify that the network-facing
Hermes processes run as UID/GID 10000.

Discord requires explicit user mention in server channels and threads, never
reads historical channel messages, does not create threads or reactions, never
mentions users, roles, or everyone, and isolates all group and thread sessions
per user. `DISCORD_BOT_TOKEN` and `DISCORD_ALLOWED_USERS` are the only
Kubernetes Secret keys. They are projected from the `hermes-discord` 1Password
item and must never be copied into Git.

## Bootstrap and acceptance

1. Manually synchronize the `hermes` Application and confirm that the PVC is
   Bound and the Pod is Healthy.
2. Confirm the process and capability boundary: s6 PID 1 may run as root, but
   Hermes services must run as UID/GID 10000. Do not weaken the security
   context if this check fails; collect evidence and reassess first.
3. Complete the Codex device OAuth flow from an authorized operator session.
   The resulting credentials must stay on `/opt/data`, never in Git or a
   Kubernetes Secret.
4. Restart the Pod and verify that OAuth state persists and that only approved
   DNS and public HTTPS egress works.
5. Prove a VolSync snapshot backup and an isolated restore before adding a
   `ReplicationSource` or enabling automated sync/prune/self-heal.

Use `gpt-5.6-terra` with Medium effort as the normal Hermes model. Switch to
`gpt-5.6-sol` with High effort only for difficult, high-value tasks. Reserve
`gpt-5.6-luna` for clear, repeatable auxiliary work.

## Rollback

Revert the Deployment or set its replica count to zero through Git; preserve
the PVC. Do not delete the Application with cascading deletion and do not
delete `hermes-data` until backup and data-retention consequences have been
reviewed.
