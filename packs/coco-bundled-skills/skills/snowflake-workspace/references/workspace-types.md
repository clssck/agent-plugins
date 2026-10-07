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

## Git-backed (git-synced) — a *private* workspace connected to a Git repo

A git-backed workspace is **a kind of Personal workspace** (it lives under `USER$<u>.PUBLIC`), connected to an external Git repository. It is **mutually exclusive with Shared**: a shared workspace cannot be git-backed, and a git-backed workspace cannot be shared via RBAC.

- **Creation is UI-only.** Created only in Snowsight via **Projects » Workspaces » From Git repository** (repo URL + API integration + OAuth2 / PAT / public-repo auth). There is **no `CREATE WORKSPACE` DDL** and no `cortex` path for a git-backed workspace — you cannot SQL-create a workspace and attach git afterward. Redirect to the UI.
- **Collaboration is via git, not RBAC.** Each collaborator works in their **own git-backed workspace** and uses conventional `git` push/pull against the shared remote — this is how you collaborate with people inside and outside Snowflake. Do not use `GRANT READ`/`WRITE ON WORKSPACE` to "share" a git-backed workspace.
- **Git operations are UI-only.** `git push`/`pull`/commit/branch-switch run through internal `SYSTEM$WORKSPACE_REPO_*` functions the Snowsight backend invokes; there is no public SQL/CLI equivalent. See the "UI-only operations" section in `SKILL.md`.
- **You cannot detect git-backed status.** `DESCRIBE WORKSPACE` has **no** `repository_url`/`git_url`/`branch` column (don't invent one); its only git-adjacent fields are undocumented `*_git_commit_hash`/`*_source_location_uri`. The authoritative repo origin/branch/status lives in internal `SYSTEM$WORKSPACE_STATUS.repo.origin` / `SYSTEM$WORKSPACE_REPO_*` / `gitRepositoryDetails` calls that are **not exposed to public SQL/CLI**, and `SHOW WORKSPACES` doesn't report it. There is no reliable public way to determine git-backed status — say so and point the user to check in the Snowsight UI.
