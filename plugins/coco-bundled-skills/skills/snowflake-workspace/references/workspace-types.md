# Workspace Types

Per-type semantics. The FQN classification is in `SKILL.md`.

## Personal — `USER$<u>.PUBLIC.<name>`

**`USER$` shorthand.** For the calling user's own workspaces, write `USER$.PUBLIC.<name>` (no username). Snowflake resolves the user server-side. Use the full `USER$<USERNAME>.PUBLIC.<name>` form only when referring to **another user's** PDB workspace (rare; a shared workspace is usually the right answer).

The Snowsight-auto-created `USER$<u>.PUBLIC.DEFAULT$` ("My Workspace") is a personal workspace — no special handling.

## Personal LOCAL — `USER$<u>.LOCAL.<name>`

Lives under the user's PDB but in the special `LOCAL` schema. Same single-user semantics as personal.

**Defining property: `LOCAL` data does not replicate.** Use cases:

- **Writable on a secondary replica** where the PDB is read-only-replicated. The canonical question: *"my PUBLIC is read-only — where can I write?"* → `LOCAL`.
- Strictly local data that should never replicate (security, regional residency).
- Per-replica logs / caches.

**Anti-uses:**

- Anything that needs to be visible from other accounts (won't replicate).
- Anything that needs to survive a PDB restore from another region.
- Sharing with other users (single-user — use a shared workspace).

If the user asks to put data that needs to replicate into LOCAL, **warn explicitly** before proceeding; suggest `USER$.PUBLIC.<name>` (replicated personal) or a shared workspace.

## Shared — `<other_db>.<schema>.<name>`

Multi-user, RBAC-gated. Grant on the workspace, not on individual files:

```sql
GRANT READ  ON WORKSPACE <fqn> TO ROLE <role>;
GRANT WRITE ON WORKSPACE <fqn> TO ROLE <role>;   -- includes READ
SHOW GRANTS ON WORKSPACE <fqn>;                  -- audit
```

`OWNERSHIP` includes implicit READ + WRITE; transfer with `GRANT OWNERSHIP`.

For shared-workspace file-op visibility (live/head, when COMMIT matters), see the "File operations" section in `SKILL.md`.
