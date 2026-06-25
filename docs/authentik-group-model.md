# Authentik Group Model

This document describes the 3-layer group model used for organizing users and permissions in Authentik.

## Layer Structure

```
cohort:* = People classification/affiliation (no direct permissions)
team:*   = Permission bundles directly assigned to people
app:*    = Minimal permissions interpreted by each application
```

## Role of Each Layer

### `cohort:*` Groups

- **Purpose**: People classification and affiliation labels
- **Permissions**: None (no direct permissions)
- **Usage**: Organize users into logical groups (e.g., NKC-Member, Family, Friend)
- **Example**: `cohort:nkc-member`, `cohort:family`, `cohort:friend`

### `team:*` Groups

- **Purpose**: Permission bundles directly assigned to people
- **Permissions**: Inherited from `app:*` groups
- **Usage**: Assign users to functional roles (e.g., Owner, Developer, Media User)
- **Example**: `team:owner`, `team:dev-user`, `team:media-user`, `team:storage-user`

### `app:*` Groups

- **Purpose**: Minimal permissions interpreted by each application
- **Permissions**: Application-specific roles (e.g., admin, user, editor, viewer)
- **Usage**: Applications check membership in these groups
- **Example**: `app:coder:global:user`, `app:nextcloud:global:user`, `app:grafana:global:editor`

## Standard Assignments

### Administrator

```
team:owner
```

### NKC-Member who uses Coder

```
cohort:nkc-member
team:dev-user
```

### NKC-Member who only uses Nextcloud

```
cohort:nkc-member
team:storage-user
```

### Family member who uses Immich

```
cohort:family
team:media-user
```

### Family member who uses both Immich and Nextcloud

```
cohort:family
team:media-user
team:storage-user
```

### Friend who has Coder access

```
cohort:friend
team:dev-user
```

### Friend who only wants photo sharing

```
cohort:friend
team:media-user
```

## Migration Notes

### Deprecated Groups (Do Not Remove)

- `team:infra` → `team:owner` (use this instead)
- `team:app-dev` → `team:dev-user` (use this instead, re-evaluate automatic assignments)
- `team:guest` → DEPRECATED (use appropriate cohort/team combinations)

### Migration Strategy

1. **Do NOT remove deprecated groups immediately** - users need time to migrate
2. **Create new team groups** first (as done in this blueprint)
3. **Assign new team groups** to users
4. **Keep old teams as deprecated** to avoid breaking access
5. **Later remove** old teams once all users have migrated


## Invitation Enrollment

Invitation-based enrollment uses the `invite-enrollment` flow. The invitation fixed data can assign groups in either of these ways:

### Explicit group list

Use `invite_groups` when the invitation should grant an arbitrary safe combination of people-facing groups:

```yaml
invite_groups:
  - cohort:friend
  - team:media-user
  - team:storage-user
```

Only `cohort:*` and `team:*` groups are accepted by the flow. `team:owner` is explicitly denied so administrative access cannot be granted by invitation.

### Shorthand invite kind

Use `invite_kind` when one of the standard combinations is enough:

| `invite_kind` | Assigned groups |
| --- | --- |
| `friend-media` | `cohort:friend`, `team:media-user` |
| `friend-dev` | `cohort:friend`, `team:dev-user` |
| `friend-storage` | `cohort:friend`, `team:storage-user` |
| `family-media` | `cohort:family`, `team:media-user` |
| `family-storage` | `cohort:family`, `team:storage-user` |
| `family-media-storage` | `cohort:family`, `team:media-user`, `team:storage-user` |
| `nkc-dev` | `cohort:nkc-member`, `team:dev-user` |
| `nkc-storage` | `cohort:nkc-member`, `team:storage-user` |

The flow prefers `invite_groups` when both keys are present, and falls back to `invite_kind` only when `invite_groups` is empty.

## OIDC Claims

Each application's scope mapping filters to `app:<app>:` prefix, ensuring only `app:*` groups are exposed:

```python
# Coder example
[group.name for group in request.user.all_groups() if group.name.startswith("app:coder:")]

# Nextcloud example
[group.name for group in request.user.all_groups() if group.name.startswith("app:nextcloud:")]
```

This means `team:*` and `cohort:*` groups are never directly visible to applications.

## Application Access Policies

Application access policies continue to target `app:*` groups:

- `app:coder:global:user` → Coder read access
- `app:nextcloud:global:user` → Nextcloud read access
- `app:grafana:global:editor` → Grafana editor access
- etc.

`team:*` groups are not used in application policies - users get permissions through their `team:*` group's `app:*` parent relationships.
