# Vikunja bounded write activation policy (DRAFT — NOT DEPLOYED)

This document is an operator conversation draft only. It is deliberately not
referenced by `kustomization.yaml`, `config.yaml`, Hermes Managed Scope, Cron,
`SOUL.md`, or any runtime skill. It does not grant permission, enable a route,
or authorize a live request. Existing scheduled Vikunja workflows remain
read-only.

## Authorization boundary

- Perform a write only in response to a clear, current, explicit user request
  for that specific task operation. Do not infer authorization from token
  grants, role, prior requests, saved preferences, a task suggestion, or a
  generated plan.
- Do not perform writes from Cron, background automation, notifications,
  summaries, reconciliation, or another user's session.
- Confirm the target task/project and intended field values in the interaction
  when the request does not identify them unambiguously. Never guess a default
  project, label, relation direction, or date/time.
- Each CLI invocation is one bounded operation. A sequence such as create then
  add a label/relation is not atomic; report the created task ID and any
  operation not completed or not verified.

## Allowed operations

Use only the mounted `vikunja-tasks` CLI and its fixed loopback adapter:

- Read projects, tasks, and labels.
- Create a task in an explicitly selected project.
- Update title, description, priority, due/start/end dates, or the complete
  reminder list. Omitted fields stay unchanged; `--clear-*` flags explicitly
  clear only the selected value.
- Add or remove one existing label association by exact ID.
- Add or remove one relation by exact task IDs and a supported relation kind.
  The base task remains the task named first; for example, `subtask` means the
  base task is the child of the other task. Do not substitute an API alias or
  infer a kind from natural-language ambiguity.

The API has 11 relation kinds; the CLI offers the 10 kinds exposed in the UI.
`duplicateof` is intentionally not offered by the UI. The adapter verifies the
inverse relation on both tasks after a relation change.

## Prohibited operations

Never use an alternate client, direct HTTP request, or a wider Vikunja API grant
to perform an operation outside the allowlist. Do not complete/reopen, delete,
move, duplicate, bulk-edit, assign users, edit recurrence, comments, attachments,
ACLs, webhooks, or create/edit/delete label catalog entries. Do not update raw
Vikunja task fields such as `done`, `project_id` on update, `labels`,
`related_tasks`, `assignees`, `position`, or `bucket_id` through scalar update.
Token permission to perform a route is not user authorization to use it.

## Failure handling

Every mutation is serialized within this adapter and must be verified by a fresh
read. Report the adapter's operation, task ID, `write_state`, and
`verification` values without exposing token data or raw upstream errors.

- `not_attempted`: validation or pre-write read failed; do not claim a mutation.
- `rejected`: Vikunja definitively rejected the write; explain the safe error.
- `unknown`: the write request may have reached Vikunja but its result is
  unknown; stop and request status confirmation before any further write.
- `applied_unverified`: a write response succeeded but readback failed or
  mismatched; stop and request read-only/manual reconciliation.

Never retry, compensate, delete, or mark an ambiguous write successful. Task
creation is not idempotent. Relation inconsistency or an unpreservable task
schema requires stopping before a write. Adapter read-modify-write cannot guard
against edits made concurrently in the Vikunja UI; do not claim atomicity.

## Separate runtime activation gate

Before any production write capability is enabled, an operator must separately
approve and record: a reviewed signed PR; an explicit Argo CD sync/rollout;
running adapter and CLI hashes matching the reviewed sources; value-free
confirmation of effective grants and token expiry (currently reported expiry is
unknown); a controlled non-user test project, two test tasks and an existing
test label; reminder delivery side-effect suppression; and an identified
operator responsible for cleanup. Test cleanup uses separately authorized
operator permissions because deletion is intentionally absent from the adapter.

Synthetic fixture tests, source edits, render output, and Deployment checksum
annotations are not live write proof and do not satisfy this gate. Do not create
test tasks, read secret values, probe live write routes, or sync resources as
part of implementing or reading this draft.
