# Hermes Agent bootstrap

This is an intentionally internal-only, manually synchronized bootstrap for
Hermes Agent. The child Argo CD Application has no automated sync policy:
creation of `installs/hermes.yaml` creates the Application, but an operator
must review and synchronize its resources before the workload starts.

## Security boundary

- The image is pinned to the official `v2026.9.7` multi-architecture image
  digest. Do not replace it with a floating tag.
- There is no Service, Ingress, dashboard, API exposure, host mount, or
  privileged mode. The Discord gateway accepts only the users stored in the
  1Password-managed `hermes-discord` Secret.
- Kubernetes API observation is deliberately separate from GitHub access. The
  ServiceAccount remains `automountServiceAccountToken: false`; only the Hermes
  container receives an explicit short-lived projected token. Pod `fsGroup: 10000`
  makes that token readable by the non-root Hermes process without exposing it to
  other containers. Its custom ClusterRole is read-only and excludes Secrets,
  ConfigMaps, RBAC resources, exec/attach/port-forward/proxy subresources,
  arbitrary CRDs, and all mutation verbs. `kubectl` is installed into an
  ephemeral volume by a checksum-verified init container and is available through
  `PATH`.
- NetworkPolicy denies all ingress and egress by default. Hermes may resolve
  DNS through `kube-system`, make TCP/443 connections only to public IPv4
  addresses, and reach the documented Kubernetes API VIP only on TCP/6443. It
  cannot otherwise access RFC1918, loopback, link-local, shared-address,
  documentation, multicast, or reserved IPv4 ranges. IPv6 egress is denied.
- `/opt/data` is the only persistent path. It holds Hermes configuration,
  memory, skills, sessions, and ChatGPT/Codex OAuth credentials. It is a
  `ReadWriteOnce` Ceph RBD volume and the Deployment uses `Recreate`; never
  run a second Hermes gateway against this volume.
- The `hermes-config` ConfigMap has two roles. An init container copies
  `config.yaml` and `SOUL.md` to the PVC only when each file is absent, while
  the running Hermes container mounts the same ConfigMap read-only as its
  Managed Scope. Every leaf setting in the Git-managed `config.yaml` therefore
  wins over the writable PVC configuration, shell environment, and runtime
  configuration commands. The PVC remains writable for non-managed settings
  and durable state such as OAuth, sessions, memories, skills, cron, logs, and
  the state database.
- The first recovery migration archives the existing files under
  `/opt/data/.hermes-bootstrap-recovery-v1/` before atomically installing the
  Git bootstrap files. A missing or malformed completion marker blocks startup
  rather than guessing whether an interrupted migration is safe to resume.

The official image starts its s6 supervisor as root to prepare `/opt/data` and
then runs Hermes services as UID/GID 10000. The container is not privileged,
cannot escalate privileges, uses the RuntimeDefault seccomp profile, and drops
all Linux capabilities before adding only the capabilities required for that
documented bootstrap. Runtime acceptance must verify that the network-facing
Hermes processes run as UID/GID 10000.

Discord requires explicit user mention in server channels and threads except
for the configured private control channel, never reads historical channel
messages, does not create threads or reactions, never mentions users, roles,
or everyone, and isolates all group and thread sessions per user.
`DISCORD_BOT_TOKEN` and `DISCORD_ALLOWED_USERS` are projected from the
`hermes-discord` 1Password item and must never be copied into Git.

The normal parent model is Terra at Medium effort. Delegated children default
to Luna at High effort for long, well-specified, read-only investigation such
as web search, status collection, log review, and repetitive validation. They
are limited to one flat child with no automatic approval. `delegate_task` has
one global child model and no per-task model parameter: keep the Luna default
for inexpensive workers. For a difficult, high-value design decision, switch
the parent for that turn with `/model gpt-5.6-sol --once`; this leaves the Luna
delegation default intact, and the per-model reasoning override applies High
effort to Sol. Use Kanban rather than `delegate_task` when a
durable queued task requires a per-task model override.

Discord progress visibility is enabled through interim assistant messages and
accumulated tool-progress updates. Background delegation completion and failure
notices should return to the originating thread automatically. Use `/agents`
to inspect an in-flight delegation (child activity, tool, and elapsed work),
and `/verbose` to toggle detailed gateway progress when needed. `tool_progress`
reports only a newly encountered tool type and is intentionally accumulated
into one update rather than emitting one Discord message per tool call. Tool
previews are capped at 160 characters to limit information exposure in Discord.

The `hermes-config` ConfigMap is mounted as Hermes Managed Scope at
`/etc/hermes-managed` through the deployment-owned `HERMES_MANAGED_DIR` value.
The mounted files are read-only and must remain inaccessible for mutation by
the Hermes runtime. Git-managed configuration leaves therefore remain effective
even when a writable PVC `config.yaml` contains different values. This is a
key-level policy overlay, not a hard sandbox: do not depend on it to stop a
process with Kubernetes-level authority from changing its own environment or
mounts.

## GitHub App automation

Hermes is intended to make repository changes through GitHub rather than by
mutating the Kubernetes desired state directly. The GitHub App credentials are
stored in a 1Password item named `hermes-github-app` in the same vault used by
Hermes. Before synchronization, create that item with these exact fields:

- `appId`: the numeric GitHub App ID (not the Client ID).
- `installationId`: the installation ID for the App installation that contains
  the repositories Hermes may operate on.
- `privateKey`: the PEM-encoded GitHub App private key.

The private key is mounted only into the `github-token-broker` container.
Hermes never receives it. The broker signs a short-lived JWT whose `iss` claim
is the numeric App ID, mints an installation access token, writes the token to
a memory-backed `emptyDir`, and refreshes it ten minutes before expiry. A
refresh failure leaves the previous token in place and retries once per minute.
The token volume is read-only in the Hermes container.

The init container installs a pinned, checksum-verified GitHub CLI v2.100.0
into an ephemeral volume. No custom container registry is required. The
immutable ConfigMap provides these commands to Hermes:

- `gh`: wraps GitHub CLI and reads the current installation token on every
  invocation. Use it for Issues, pull requests, checks, comments, and API
  queries.
- `git-credential-hermes`: is configured automatically for HTTPS GitHub
  remotes and reads the current token on every credential request.
- `github-commit-staged <headline> [body]`: converts the current staged Git
  index into one GraphQL `createCommitOnBranch` operation. It refuses the
  repository default branch, uses `expectedHeadOid` for optimistic locking,
  and accepts only regular `100644` files because the GraphQL file-change API
  cannot preserve executable, symlink, or submodule modes. GitHub creates the
  commit, so supported commits are GitHub-signed and shown as Verified.

The intended autonomous flow is: fetch or clone the repository, create or
checkout a non-default work branch, edit and validate files, `git add` the
chosen changes, call `github-commit-staged`, then use `gh` to create or update
a pull request and to read/respond to its discussion. Do not put a long-lived
GitHub token in Hermes configuration. The default branch should be protected
so desired-state changes require a pull request; the App itself does not need a
per-commit approval gate.

Recommended initial GitHub App repository permissions are `Contents: Read &
write`, `Pull requests: Read & write`, `Issues: Read & write`, `Checks: Read`,
`Actions: Read`, and `Commit statuses: Read`. Keep `Administration` and
`Workflows` disabled unless a later use case explicitly requires them, and
install the App only on repositories Hermes should control.

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
6. Before the migration sync, record or back up the unmasked PVC copies of
   `config.yaml` and `SOUL.md` if they exist. After sync, verify that both are
   writable regular files owned by UID/GID 10000, then make and restart-test a
   harmless runtime configuration change.
7. Verify the GitHub broker without printing the token: check that
   `/var/run/github-token/expires_at` exists in the Hermes container and run
   `gh api rate_limit`. Clone/fetch an allowed repository over HTTPS, create a
   test work branch, stage a harmless regular-file change, run
   `github-commit-staged`, and confirm the resulting commit is Verified before
   opening a test pull request.

Use `gpt-5.6-terra` with Medium effort as the normal Hermes model. Switch to
`gpt-5.6-sol` with High effort only for difficult, high-value design tasks.
Reserve `gpt-5.6-luna` with High effort for clear, repeatable auxiliary work.

## Rollback

Revert the Deployment or set its replica count to zero through Git; preserve
the PVC. Do not delete the Application with cascading deletion and do not
delete `hermes-data` until backup and data-retention consequences have been
reviewed.
