# Repository invariants

Unless a task explicitly changes one of these constraints, preserve them.

1. Desired state remains reproducible from Git and referenced secret systems.
2. No secret material is committed or echoed in reports.
3. Argo CD references resolve to existing paths, revisions, and value files.
4. Kustomizations include every intended existing resource.
5. Resource identity changes are treated as delete-and-create until proven otherwise.
6. Storage migrations preserve ownership, access modes, snapshot compatibility,
   data integrity, and rollback.
7. Authentication changes preserve an administrative recovery path.
8. Routing changes preserve a verified path during migration or define an
   explicit maintenance window and rollback.
9. Backup changes define and validate a restore path; backup creation alone is insufficient.
10. Static validation is not reported as live-cluster verification.
11. Unrelated user changes remain untouched.
12. Agents do not commit, push, rewrite history, or mutate the cluster unless
    explicitly requested.
