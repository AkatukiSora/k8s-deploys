# Hermes Agent bootstrap

This is an intentionally internal-only, manually synchronized bootstrap for
Hermes Agent. The child Argo CD Application has no automated sync policy:
creation of `installs/hermes.yaml` creates the Application, but an operator
must review and synchronize its resources before the workload starts.

## Security boundary

- The main `hermes` container uses the official Hermes Agent `0.21.7` image,
  pinned to `sha256:444b42594e7f467425872fc35e077a227d377f0fe0726bc818706d62175fad8b`.
  The init containers and other existing sidecars remain pinned to the prior
  `v2026.9.7` image digest `sha256:63bfb6d732f49a55d453e801057273785cc61e0f6ee43db3fa2f2a79846301b7`;
  `vikunja-read-proxy` remains pinned to the `0.21.7` digest above. Do not
  replace any of these pins with a floating tag.
- There is no Service, Ingress, dashboard, API exposure, host mount, or
  privileged mode. The Discord gateway accepts only the users stored in the
  1Password-managed `hermes-discord` Secret.
- Kubernetes API observation is deliberately separate from GitHub access. The
  ServiceAccount remains `automountServiceAccountToken: false`; only the Hermes
  container receives an explicit short-lived projected token. Pod `fsGroup: 10000`
  makes that token readable by the non-root Hermes process without exposing it to
  other containers. Its custom ClusterRole is read-only and permits cluster-wide
  observation of workload metadata and ConfigMaps. Pod logs are granted through
  an explicit `pods/log` rule with only `get`; logs and ConfigMaps can contain
  sensitive operational data and must not be copied into issues or chat without
  redaction. Read-only rules also cover the CRDs of the platform components
  deployed from this repository (Argo CD, CloudNativePG and Barman Cloud, Rook
  Ceph, Kyverno and its policy reports, MetalLB, Prometheus Operator rules and
  monitors, VolSync) and CRD definitions. The role excludes Secrets, RBAC
  resources, exec/attach/port-forward/proxy subresources, any other CRD, and all
  mutation verbs. `kubectl` is installed into an
  ephemeral volume by a checksum-verified init container and is available through
  `PATH`.
- NetworkPolicy denies all ingress and egress by default. Hermes may resolve
  DNS through `kube-system`, make TCP/443 connections only to public IPv4
  addresses, and reach the documented Kubernetes API VIP only on TCP/6443. It
  cannot otherwise access RFC1918, loopback, link-local, shared-address,
  documentation, multicast, or reserved IPv4 ranges. IPv6 egress is denied.
- Internal integration traffic is explicitly limited to the Argo CD server on
  its TCP/80 Service and TCP/8080 Pod ports, and Grafana on its TCP/80 Service
  and TCP/3000 Pod ports. Both ports are required because CNI implementations
  can evaluate NetworkPolicy before or after Service DNAT. The `hermes-webhook` Service is
  `ClusterIP` only and the TCP/8644 ingress policy accepts traffic solely from
  the kube-prometheus-stack Alertmanager selector in `monitoring`; it has no
  Ingress or external Cloudflare route. These resources are inert until the
  corresponding dedicated 1Password credentials and webhook configuration are
  installed. Internal HTTP is a documented interim risk pending encrypted
  east-west traffic in issue #62; NetworkPolicy constrains reachability but
  does not provide transport encryption.
- `/opt/data` is the only persistent path. It holds Hermes configuration,
  memory, skills, sessions, ChatGPT/Codex OAuth credentials, and the default
  Kanban board (`kanban.db`) with its logs, attachments, and workspaces. It is
  a `ReadWriteOnce` Ceph RBD volume and the Deployment uses `Recreate`; never
  run a second Hermes gateway or a second Kanban dispatcher against this volume.
  A Pod restart terminates an in-flight worker process and loses its transient
  model context, but not its task record: the restarted embedded dispatcher
  detects the dead local PID/claim and requeues the durable card for a bounded
  retry. Workers must commit/push durable code changes and persist handoff
  details to the Kanban card rather than rely on process-local state.
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

### Discord Kanban visibility

`platform_toolsets.discord` retains the `hermes-cli` tool bundle and adds
`kanban` for normal Discord conversations. Upstream availability and ownership
guards exclude `delegate_task` children; no other platform is opted in. Native
Discord/admin API tools are not enabled by this setting.

The `hermes-config` Managed Scope applies this setting after manual sync; start
a new Discord session to pick it up. Because the Deployment uses `Recreate`,
rollout interrupts an in-flight worker; confirm the Kanban worker queue is idle
before synchronizing. Roll back by reverting this change (including the config
checksum and main image) and manually synchronizing. Runtime tool visibility
and image behavior have not yet been verified.

Run the offline manifest checks with
`python3 apps/hermes/test_kanban_visibility.py -v` (requires PyYAML).
To also test the isolated upstream availability and delegated-child ownership
functions, set `HERMES_SOURCE_DIR` to a local copy of the pinned image's
source. The test harness hashes each required file against the digest this
PR pins before compiling or executing any of it, and rejects a mismatch
instead of running unverified code; it does not fetch or trust the directory
contents itself. Those source checks skip without that variable; they do not
start a gateway, assemble complete model schemas, mutate a board, or test
dispatch.

## Coding and infrastructure orchestration

The default interactive parent is Claude Sonnet 5.5 / Anthropic at Medium effort.
It owns the user conversation and can define the task scope, acceptance criteria,
and validation. Use a Kanban card routed to GPT-6.1 Sol / OpenAI-Codex when a
requirement is ambiguous, an architecture or risk decision is unresolved, or
failure diagnosis requires judgment. Do not spend Sol on routine implementation
after that contract is clear; use Luna for specified execution. Escalate to Sol
when acceptance criteria conflict, requirements are missing, a security boundary
or migration is involved, a Terraform plan is unexpectedly broad, multiple
Kubernetes networking/storage/auth layers are affected, or retries have become
unexplained trial and error.

Delegated children default to GPT-6 Luna at XHigh effort with OpenAI/Codex
Priority Processing and have an explicit Claude Sonnet 5.5 fallback. The
`cron.model` and `cron.model_provider` defaults remain GPT-6 Luna / OpenAI-Codex
at XHigh and Standard processing; `delegation.request_overrides` does not apply
to that scheduler. Cron still inherits the top-level fallback chain, so a Codex
failure can route it to Sonnet while Luna remains its primary model. Kanban cards
select their model individually: use GPT-6 Luna / OpenAI-Codex for decided
execution and GPT-6.1 Sol / OpenAI-Codex for unresolved decisions. Kanban workers
run at Standard processing. A card without an explicit model override uses the
Sonnet / Anthropic profile default, not Luna. The top-level fallback chain
applies to Kanban CLI workers; an OpenAI-routed card can fall back to Sonnet,
and a candidate on the currently failing backend is skipped. Luna implements
already-decided features and bug fixes, makes targeted Terraform/Ansible/manifest
changes, writes tests and documentation, investigates bounded questions, and
runs mechanical validation. It must not choose a specification, architecture,
priority, or acceptable risk. Each handoff must state the objective, context,
constraints, non-goals, likely files, dependencies, acceptance criteria, exact
validation commands, risk level, and the condition that requires escalation
rather than a guess.

The durable Kanban dispatcher admits at most six concurrent workers, including
six assigned to the same profile. The planner classifies each card before
creation: a decision-free, testable execution card uses `gpt-6-luna`; an
ambiguous requirement, cross-layer architecture decision, unexplained failure,
or high-risk judgment card uses `gpt-6.1-sol`. Complexity alone does not require
Sol if the contract is already decided. A short card may still require Sol if
it makes a security or migration decision. Sol separates the dependencies and
ownership, then creates decision-free Luna implementation cards. Sol also
reviews high-risk results. `gpt-6-astra` is a human-approved escalation, never
an automatic Kanban route.

Set the selected exact `model` and `provider: openai-codex` on *every* card
when using `kanban_create` (or `--model` / `--provider` via the CLI). Include a
short selection rationale in its body. For existing blocked/todo/ready cards,
inspect and correct a stale model override before unblocking or dispatching.
The dispatcher does not infer difficulty from the title or body: it uses the
persisted override and otherwise falls back to the profile default (Sonnet).
This is classification by the planning agent at card creation, not a universal
automatic classifier for externally created cards. The committed `SOUL.md` is
the policy reference, but bootstrap does not overwrite a pre-existing PVC
`/opt/data/SOUL.md`: apply and read back policy changes on the live PVC as a
separate operational step, without replacing unrelated user-authored content.
The current live policy was updated alongside this change. A Git sync alone
will not activate later SOUL edits. Cards that write the same
file or external state remain serial. Workers report changed files, exact
validation results, remaining risks, and blockers; Sol reads that evidence
before integrating, retrying, or changing scope.

A typical issue uses a Sol planning/judgment card only when requirements or risk
remain unresolved, up to six independent Luna workers after the contract is
clear, and a validation/review card. Sol performs the final decision review for
high-risk IAM/RBAC, authentication/authorization, NetworkPolicy/firewall/routing,
secrets, database migrations, destructive Terraform potential, control-plane,
or production changes. Trust acceptance criteria, mechanical validation, diff
review, and LLM review in that order.

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

## Smart command approvals

Managed Scope pins `approvals.mode: smart`, adds `approvals.smart_policy` to the
guardian's trusted system prompt, and shortens the approval prompt timeout with
`approvals.timeout: 30`. This is an auxiliary-LLM judgment, not a parser,
sandbox, detector bypass, or interpreter allowlist. Commands and detector
descriptions remain untrusted data. Approval is for one exact command only; no
unattended approval mode is enabled.

No human reviews shell code in this deployment, so the guardian decides
mechanically and **approves by default**. The policy judges effects, not syntax,
length, unfamiliar imports, or detector categories, and denies only payloads
that clearly do one of the following. The categories follow the published
reviewer policies of Claude Code auto mode and Codex auto-review, which block
exfiltration, credential probing, persistent security weakening, and
irreversible destruction and approve routine work.

- **Exfiltration**: sending secrets or private data to an untrusted destination.
  Reading or printing data locally is not exfiltration.
- **Credential access**: reading credential files, secret stores, private keys,
  browser profiles, or process environments, because the output enters the
  model context.
- **Broad or unscoped destruction**: wildcard targets over a parent directory,
  unresolved variables or command substitutions in the target path, `/`, `~`,
  `$HOME`, `/etc`, `/opt/data`, `/opt/hermes`, mount points, `git clean`/`reset`
  of unrelated work, `kubectl delete --all` or of namespaces, `DROP`/`TRUNCATE`,
  block-device writes, mass process kills. Deleting one specific named file or
  directory below a workspace, worktree, or scratch path is fine.
- **Tampering with safeguards**: approval settings, managed configuration,
  SOUL, hooks, authentication files, access settings, Hermes state and Kanban
  databases.
- **Remote or obfuscated code**: piping a download into a shell, executing
  base64, hex, or otherwise opaque decoded text.
- **Malicious activity**: ransomware, persistence, reverse shells, miners,
  attacks on third parties.
- **Operations forbidden here**: local `git commit`, `push`, `rebase`, `merge`,
  `tag`, `cherry-pick`, `am`, force or default-branch pushes, merging a pull
  request, and `hermes kanban` (commits use the signed-commit helpers; Kanban is
  operated through MCP tools).
- **Reviewer manipulation**: text imitating the `<command>` delimiter, a
  system/operator message, or a verdict addressed to the reviewer, and
  confusable characters in command names, paths, URLs, or shell structure.

The guardian sees the command text, not the contents of a script that the
command merely runs. Unseen local scripts, unknown imports, and `unsafe_load`
are therefore approved when the command line itself matches no denial category;
this is an accepted risk of the permissive stance, bounded by the deny floors,
the 30-second prompt timeout, and the fact that the policy is model guidance
rather than a sandbox.

`ESCALATE` is reserved for changes to shared live state whose timing a human
must confirm: Argo CD sync and scoped Kubernetes mutations (apply, patch, delete
of named resources, scale, rollout restart). Everything else is approved.

The runtime lets a present operator override a guardian `DENY`, which shows an
approval prompt. `approvals.timeout: 30` makes that prompt expire after 30
seconds, and an unanswered prompt is refused, so a guardian `DENY` effectively
resolves to deny. The timeout applies to every approval prompt, including the
Argo CD and Kubernetes timing confirmation: answer within 30 seconds or ask for
the action again. A timed-out prompt also tells the agent to stop the current
workflow and wait for the user. `auxiliary.approval.timeout` (the guardian model
call) is unchanged. To keep always-forbidden categories from ever prompting,
`approvals.deny` lists glob floors that are answered without the guardian model
or a person: local `git commit`/`push`/`rebase`/`merge`/`tag`/`cherry-pick`/`am`
(also with leading git options), `hermes kanban`, and `gh pr merge`. The globs
are matched per shell command word, so quoted prose such as `echo "git commit"`
is not blocked. The validator checks that every fixture marked `floor` is
matched and that no safe fixture is.

Tirith, secret redaction, protected-instruction handling, and existing deny
behavior are unchanged. A provider failure or a verdict that is not a single
recognised word still escalates, because the runtime fails closed; with the
short timeout that prompt expires into a refusal. The fallback chain and the
one-word reply rule keep that rare.

Run from the repository root after activating a Python environment containing
PyYAML and the installed Hermes runtime's dependencies. The image's own virtual
environment may lack PyYAML; use a prepared test environment rather than adding
packages to a running gateway. `--runtime` selects source separately from the
Python environment: test against `/opt/hermes`, not a stale source checkout.

```bash
git diff --check
python3 apps/hermes/validate-smart-approval.py --runtime /opt/hermes \
  --output .smart-approval-evidence/offline.json
/opt/kubernetes-bin/kubectl kustomize apps/hermes
# Commands in the fixtures are NEVER executed. Select each route explicitly:
python3 apps/hermes/validate-smart-approval.py --runtime /opt/hermes --live \
  --route-index 0 --output .smart-approval-evidence/luna.json
# Use --route-index 1 for Haiku and --route-index 2 for Sonnet.
```

`approval-fixtures.json` records examples that must be approved (`safe`), escalated for timing (`timing`), and denied (`denied`); each denial category above has at least one fixture, and ordinary work such as unseen local scripts, unknown imports, and writes outside scratch is expected to be approved.
The offline validator checks byte-exact rendered configuration, source and
rendered checksums, trusted/untrusted prompt separation, strict verdict mapping,
and fail-closed provider failures. Mock responses test wiring only; they do not
prove policy classification. Fixtures can supply the exact detector `description`, including the
`execute_code` warning, instead of testing every payload with a generic label.
The opt-in live check uses the installed guardian and real responses on the
selected route against an in-process staged Managed Scope. It
disables fallback only in that test process, records the actual route, and
never writes the running gateway configuration or executes fixture payloads.
It requires runtime modules under `/opt/hermes` (override with `--runtime`) and
the Kustomize binary (override with `--kubectl`). Fixture and validator files
are operator/test assets, not mounted runtime code.

The guardian's shell-comment preprocessing is not a complete shell parser;
ambiguous quoting or hidden effects must not be assumed safe. Passing fixtures
does not guarantee all possible commands or the deployed gateway behavior.
The approval guardian runs on GPT-6 Luna / OpenAI-Codex. When that provider is
unavailable or rate limited, `auxiliary.approval.fallback_chain` tries Claude
Haiku 5.5 first and Claude Sonnet 5.5 second; the validator pins this order.
The policy cannot repair authentication failures: an auxiliary provider 401,
timeout, or malformed verdict fails closed to escalation. Historical Anthropic
401s alone do not establish the cause of every escalation. Verify authenticated
requests separately rather than weakening approval controls or moving to an
unapproved paid API.

Activation requires operator review and manual Argo CD synchronization after
PR #144's model-routing dependency is present. Do not synchronize while Kanban
workers are running: the checksum change causes a `Recreate` rollout. After
activation, verify the effective managed approval keys and an innocuous flagged
read-only calculation through the normal interactive approval path. Negative
fixtures must only be classified, never executed. Roll back by reverting this
policy and checksum change through Git and manually synchronizing; preserve
the PVC, credentials, and live-only SOUL blocks. No live change is performed
by adding or validating this overlay.

## Google OAuth broker

The Google OAuth broker sidecar establishes a least-privilege, durable OAuth
grant for the secretary workflow. Its `hermes-google-oauth-client`
1Password item supplies `clientId` and `clientSecret` only to the broker as
read-only files; Hermes and every other sidecar do not mount that Secret. A
Desktop OAuth client JSON download is not required: the broker uses those two
fields with Google's fixed authorization and token endpoints.

The broker persists only its PKCE transaction state and OAuth token on the
dedicated `hermes-google-secretary-data` PVC, mounted solely into the broker
and its state-preparation init container. The shared Hermes PVC does not mount
this OAuth state. It requests exactly the broad `gmail.readonly` and
`calendar.readonly` scopes; changing from the previous Calendar grant requires
reauthorization. It cannot send, modify, archive, label, or delete Gmail, and
it exposes no Calendar write or pagination operation.

The read-only `/opt/hermes-tools/google-secretary-auth` client is tokenless: it
calls only the loopback broker and accepts no credential, token, URL, method, or
payload override. Its fixed operations are `calendar-list`, `calendar-events`
(with optional `--start`/`--end` and `--limit` 1–20), `gmail-list` (query and
limit 1–20), and `gmail-get` (validated message ID). Calendar events return
minimal scheduling fields. Gmail list returns bounded metadata/snippets; Gmail
get returns text/plain content, falling back to HTML stripped to text, with a
16 KiB body cap. The broker owns token refresh and all Google API requests.

Use `google-secretary-auth start` to obtain an authorization URL, then provide
the complete `http://localhost:1/...` callback URL on standard input to its
exchange command; do not place it in command-line arguments. The authorization
code and token are never returned by the broker or committed. `/oauth/status`
returns metadata only; the broker's `/ready` endpoint refreshes the token when
needed and makes an authenticated Calendar probe. Verify `/ready` after
exchange before scheduling any secretary job.

Rollback: revert this change, synchronize Hermes, and verify the Deployment
recreated its Pod. The OAuth client credential and token remain in 1Password
and the PVC respectively; neither is deleted by rollback.

## Vikunja task adapter

Hermes manages Vikunja tasks through a loopback-only adapter sidecar. The
adapter is the sole bearer-token consumer: it receives the `token` field from
the 1Password-managed `hermes-vikunja` Secret as a read-only file at
`/var/run/vikunja-api/token`; the Hermes container never mounts that Secret.

The 1Password item must contain the `token` field before this application is
synchronized. The minimum route grants for this adapter are projects
`read_all`; tasks `read_all`, `read_one`, `create`, and `update`; labels
`read_all`; `tasks_labels` `create` and `delete`; and `tasks_relations`
`create` and `delete`. Existing permission evidence is user-reported, not a
live write test; it reports extra grants and an unknown expiry. Do not read or
print the token, infer that extra grants authorize broader assistant actions,
or rotate/change grants as part of this static implementation. Confirm effective
grants and expiry as separate operator prerequisites before runtime activation.

The bounded `vikunja-tasks` client is mounted read-only at
`/opt/hermes-tools/vikunja-tasks`. It talks only to the local adapter, which
binds `127.0.0.1:8791`, hard-codes
`https://vikunja.akatuki-host.com/api/v1` as its upstream, and rejects upstream
redirects. Read commands cover projects, tasks, and the label catalog. The only
write operations are task creation; title, description, priority, date, and
reminder updates; label association add/remove; and task relation add/remove.
Task/project deletion, completion/reopen, movement, duplicate, assignees,
comments, attachments, bulk operations, and label catalog CRUD are not exposed,
even if the token has those grants. Omitted update fields are preserved; each
mutation is serialized and must pass a fresh readback before success is returned.
Relation changes verify both tasks and the inverse relation. Timeout or mismatch
is reported as unknown/applied-unverified without retry or compensation; create
is not idempotent. The adapter cannot prevent concurrent edits from the Vikunja
UI, so read-modify-write can still lose an external update.

`write-enable-policy.md` is a dormant operator conversation draft. It is not in
the Kustomization, deployed configuration, Hermes Managed Scope, Cron, or runtime
skills. Existing scheduled workflows remain read-only. Source changes, fixture
success, and ConfigMap checksums do not activate writes or prove live token
permissions; activation requires a separately approved and verified runtime
procedure.

This adapter is deliberately retained on API v1 for the Vikunja 2.6.0 upgrade:
v1 remains supported throughout the 2.x series. API v2 has different paths,
verbs, query names, pagination envelopes, and error semantics, so it requires
a separately reviewed adapter migration rather than an unsafe path-prefix
replacement. Plan that migration before Vikunja 3.0, when upstream intends to
deprecate v1. Do not add a v1/v2 fallback because it could conceal a partial
upgrade.

The sidecar's readiness probe calls `/ready`, which makes a value-free
authenticated `GET /api/v1/projects` probe. This uses the same least-privilege
project-read permission required by the adapter's normal task workflow; it does
not require access to the user-management route. The adapter is bound to
loopback and is not exposed through a Service or NetworkPolicy. Fixture tests
use synthetic data and ephemeral fake servers only; they do not make live write
requests or establish production write capability. The existing public TCP/443
egress policy covers the public Vikunja URL; no private-network rule is added.

Rollback: revert the adapter change, synchronize Hermes, and confirm the
Deployment has recreated its Pod. The Pod template includes the SHA-256 values
of the adapter and CLI scripts; every script change must update its matching
checksum annotation, which forces rollout despite the repository's stable
ConfigMap names. Do not treat a ConfigMap-only sync as proof that running code
changed. Rollback stops new Vikunja operations but preserves all Vikunja data
and the 1Password item.

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
- `github-update-branch-staged [--dry-run] <second-parent-ref> <headline> [body]`:
  brings the default branch into a pull-request work branch after the
  conflicts have been resolved locally and the complete resolved tree is
  staged. GraphQL `createCommitOnBranch` cannot create a two-parent commit, so
  this helper uploads only the staged differences from the second parent as
  Git blobs and a tree, then creates the commit through the Git data API with
  the work branch head and the second parent as parents. No author or
  committer is supplied, so GitHub signs it as the App installation. The
  helper requires the local and remote work-branch heads to match, the second
  parent to be an ancestor of the default branch, no unmerged index entries,
  the remote tree to equal the staged tree, and the new commit to be
  Verified. It then fast-forwards the work branch without force and aligns
  local `HEAD` with `git reset --mixed`. It refuses the default branch and
  regular-file modes other than `100644` and `100755`. `--dry-run` creates
  and verifies the commit objects but does not move the branch. This is not a
  pull-request merge and grants no approval-policy exception; the approval
  guardian judges each invocation like any other command.

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

## Argo CD and Grafana integration bootstrap

The repository creates a non-interactive local Argo CD account named `hermes`
with only the `apiKey` capability. It is assigned an observation role for all
Applications and can sync and retrieve logs for all Applications. It cannot use
Application overrides, resource actions, exec, or any Argo CD administrative
API. Do not assign it to human Authentik groups or reuse an administrator token.

Provision separate 1Password items and project them as read-only Kubernetes
Secrets: an Argo CD `apiKey` token and a Grafana Viewer service-account token.
The `hermes-argocd` and `hermes-grafana` items are reconciled by the 1Password
operator and injected only into the Hermes container as
`ARGOCD_AUTH_TOKEN` and `GRAFANA_SERVICE_ACCOUNT_TOKEN`; their values must
never be printed, committed, or copied into Hermes configuration.

The Deployment installs the checksum-verified Argo CD CLI version matching the
in-cluster Argo CD server. Use it only with the internal server and plaintext
transport parameters: `argocd --server "$ARGOCD_SERVER" --plaintext --grpc-web
app list`, `app get <name>`, `app logs <name>`, and—only after an explicit
operator request—`app sync <name>`. The API token is read automatically from
`ARGOCD_AUTH_TOKEN`; do not pass it as a command-line flag.

`grafana-read` is a repository-managed, read-only wrapper for the Grafana HTTP
API. It permits only `whoami`, `datasources`, `search [query]`, `dashboard
<uid>`, and `alert-rules`; it has no arbitrary-path or mutation mode. It uses
the service-account token internally and never prints it. Grafana configuration
changes remain GitHub PR → review → Argo CD reconciliation.

Alertmanager-to-Hermes webhook delivery remains disabled. Hermes requires HMAC
validation for webhook payloads, while Alertmanager has no native HMAC-signing
mechanism. Do not expose TCP/8644 via an Ingress. Revisit this only after the
planned encrypted east-west service-traffic layer is available.

## PVC backup

`hermes-data` (`/opt/data`: configuration, sessions in `state.db`, skills,
memory, OAuth credentials) is backed up by a VolSync `ReplicationSource`
(`volsync.yaml`) using the same method as the other stateful applications in
this repository: a Ceph RBD `VolumeSnapshot` is cloned and uploaded by restic
to a Backblaze B2 repository.

- Schedule: every 6 hours at minute 30. Retention: 7 daily, 5 weekly and
  6 monthly snapshots; the repository is pruned every 7 days.
- The snapshot is crash-consistent, not application-consistent. SQLite files
  (`state.db`) are recovered through their journal on the next start, as after
  a Pod crash. Writes made between the last snapshot and a failure are lost.
- The restic repository credentials come from the `volsync-restic-hermes-data`
  Secret, generated by the 1Password operator from the item referenced in
  `onepassworditem-volsync-restic.yaml`. The item must provide
  `RESTIC_REPOSITORY`, `RESTIC_PASSWORD`, `AWS_ACCESS_KEY_ID` and
  `AWS_SECRET_ACCESS_KEY`. Keep the restic password outside this cluster as
  well: without it the repository cannot be read.
- `networkpolicy-volsync-mover-egress.yaml` lets only the VolSync mover Pods
  (label `app.kubernetes.io/created-by: volsync`) resolve DNS and reach public
  IPv4 addresses on TCP/443, because the namespace is default-deny.
- `hermes-google-secretary-data` is not backed up. It holds only OAuth state
  that can be re-authorized.

Check the backup:

```sh
kubectl -n hermes get replicationsource hermes-data
```

`LAST SYNC` is populated after the first successful run. To restore, create a
`ReplicationDestination` for a new PVC in the same pattern as
`apps/restore/volsync-restores.yaml` and mount it on a scratch Pod; do not
restore over the live `hermes-data` while the Hermes Pod is running.

## Bootstrap and acceptance

1. Manually synchronize the `hermes` Application and confirm that the PVC is
   Bound and the Pod is Healthy.
2. Confirm the process and capability boundary: s6 PID 1 may run as root, but
   Hermes services must run as UID/GID 10000. Do not weaken the security
   context if this check fails; collect evidence and reassess first.
3. Complete the Codex device OAuth flow from an authorized operator session.
   The resulting credentials must stay on `/opt/data`, never in Git or a
   Kubernetes Secret.
4. Restart the Pod and verify that OAuth state persists, only approved DNS and
   public HTTPS egress works, and a deliberately harmless Kanban card survives
   the restart. Confirm that the previous worker is reclaimed/requeued by the
   embedded dispatcher, then completes exactly once after its retry; do not
   create a second dispatcher or a second Pod to test this.
5. Confirm the first `hermes-data` VolSync backup completes (see
   [PVC backup](#pvc-backup)) and prove an isolated restore before enabling
   automated sync/prune/self-heal.
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

The Managed Scope defaults the interactive parent to Claude Sonnet 5.5 /
Anthropic at Medium effort. The top-level fallback chain lets the conversation
fall back to GPT-6.1 Sol and lets an OpenAI-routed Kanban card fall back to
Sonnet; a candidate on the currently failing backend is skipped. Select
`gpt-6-luna` / `openai-codex` for bounded execution cards and
`gpt-6.1-sol` / `openai-codex` for unresolved decisions. A card without an
explicit model override uses the Sonnet profile default; it is not implicitly a
Luna worker. Delegated children default to GPT-6 Luna / XHigh / Priority
Processing and have an explicit Sonnet fallback. The `compression`,
`title_generation`, `approval`, and `goal_judge` auxiliary tasks use GPT-6 Luna
with Claude Haiku 5.5 as their fallback. Cron remains pinned to GPT-6 Luna /
OpenAI-Codex as its primary model, but inherits the top-level fallback chain and
can fail over to Sonnet on a Codex-side failure. Do not automatically select or fall back to GPT-6
Astra or Fable.

The `checksum/hermes-config` Pod-template annotation is the SHA-256 of
`apps/hermes/config.yaml`; update it with every configuration edit so an Argo
CD synchronization recreates the Pod and rereads Managed Scope. Because the
Deployment uses `Recreate`, synchronization interrupts any in-flight Kanban
worker; synchronize only when no card is running. After sync, exercise one
non-destructive delegated task and confirm that the provider accepts Priority
Processing without exposing credentials.

Unpinned cron jobs retain a provider/model snapshot and fail closed after a
global model change. After rollout, re-save each affected job's inference axes
or explicitly pin it to `gpt-6-luna` / `openai-codex`, then verify its next
execution. Inspect every nonterminal Kanban card before dispatch and replace
stale `model_override` values; a missing override inherits the Sonnet profile
default and must not be treated as a Luna worker.

## Rollback

Revert the Deployment or set its replica count to zero through Git; preserve
the PVC. Do not delete the Application with cascading deletion and do not
delete `hermes-data` until backup and data-retention consequences have been
reviewed.
