# Operational review guidance

For operationally material changes, determine:

- expected reconciliation sequence;
- temporary coexistence requirements;
- observable success signals;
- failure signals;
- rollback trigger;
- rollback action;
- data-loss, lockout or connectivity risk;
- which facts require live-cluster observation.

## Escalate to Sol

Terra should normally use Sol when one or more of these applies:

- storage, backup or recovery design changes;
- networking or routing migration;
- authentication, authorization or Secret-management architecture;
- Argo CD hierarchy, multi-source reference, or prune-impact changes;
- multiple valid designs with materially different failure modes;
- an irreversible or difficult rollback;
- contradictory investigation results;
- a task that remains unresolved after bounded Luna implementation and verification.

Routine changes that follow an existing pattern should normally remain Terra -> Luna.

## Live-cluster operations

`luna-cluster-operator` is the only agent with Kubernetes write permission. Terra
may invoke it only for an explicitly requested live operation with the target
context, namespace, exact command intent, success criteria, and rollback or
recovery action. All other agents may use the permitted read-only Kubernetes
commands for scoped runtime investigation.
