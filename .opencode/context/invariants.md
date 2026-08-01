# Repository invariants

Unless a task explicitly and knowingly changes one of these constraints, preserve them.

1. Desired state remains reproducible from Git and referenced external secret systems.
2. No secret material is committed or echoed in reports.
3. Argo CD references point to existing paths, revisions, source refs, charts, and value files.
4. Kustomization resources point to existing files and include every intended manifest.
5. Resource identity changes are treated as delete-and-create operations until proven otherwise.
6. Storage migrations preserve data ownership, access modes, snapshot compatibility and rollback requirements.
7. Authentication changes preserve an administrative recovery path.
8. Routing changes preserve a verified path during migration or provide an explicit maintenance window and rollback.
9. Backup changes state the restore path; successful backup creation alone is not sufficient.
10. Static validation is not reported as live-cluster verification.
11. Unrelated user changes remain untouched.
12. Agents do not commit, push, rewrite history, or mutate the live cluster unless the user explicitly requests that action.
