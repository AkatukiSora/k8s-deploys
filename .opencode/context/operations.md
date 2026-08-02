# Operational review guidance

For material changes determine:

- expected reconciliation sequence;
- temporary coexistence requirements;
- observable success and failure signals;
- rollback trigger and action;
- data-loss, lockout, or connectivity risk;
- runtime-only facts requiring observation.

## Send to General/Sol

Use General/Sol for:

- storage, backup, database, or recovery design;
- networking or routing migration;
- authentication, authorization, certificates, or secret-management design;
- Argo CD hierarchy, source path, sync order, or prune-impact changes;
- multiple valid approaches with materially different failure modes;
- difficult rollback or irreversible effects;
- contradictory evidence or cross-component architecture decisions.

Routine changes following an established pattern do not require Sol.
