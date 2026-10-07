---
name: snowflake-workspace
description: "MANDATORY for Snowflake workspace operations. Workspace lifecycle (CREATE/ALTER/DROP/RENAME), file MOVEMENT (upload, download, list, remove, copy) via the `cortex ws` CLI subcommand, RBAC (GRANT READ/WRITE), shared-workspace publishing (`ALTER WORKSPACE ... COMMIT` to make uploads visible to other users), dropped-user recovery (DROPPED_USER$), replication setup, account-wide audit. Git-backed (git-synced) workspaces are a PRIVATE workspace connected to a git repo: they are created ONLY in the Snowsight UI (Projects » Workspaces » From Git repository) — there is no CREATE WORKSPACE DDL/CLI for them; a shared workspace CANNOT be git-backed (collaborate via each user's own git-backed workspace + git push/pull, not RBAC grants); and there is no reliable public way to tell whether a workspace is git-backed via SQL/CLI (DESCRIBE/SHOW WORKSPACES don't report it — check in the Snowsight UI). Use when the user uploads, downloads, lists, removes, or copies files in a Snowflake workspace; creates/alters/drops a workspace; shares or revokes access; recovers content from a dropped user; sets up workspace replication; or asks anything referencing snow://workspace URIs, USER$ schemas, LOCAL schema workspaces, DEFAULT$/My Workspace, secondary replicas, or workspace administration. Triggers: workspace, workspaces, snow://workspace, USER$, DEFAULT$, personal workspace, shared workspace, git-backed workspace, git-synced workspace, connect workspace to git, LOCAL workspace, ALTER WORKSPACE, GRANT WORKSPACE, list workspace, files in workspace, what's in my workspace, secondary replica, read-only replica, dropped user."
---

## Recognition: when this skill applies

If the user names a Snowflake object using any of these shapes, it is **likely a workspace** — not a table/view/share — treat it as a workspaces operation and load this skill:

- FQN with `USER$<u>` as the database (`USER$ADMIN.PUBLIC.MY_WS`, `USER$.PUBLIC.DEFAULT$`)
- Any `snow://workspace/...` URI
- Anything named `DEFAULT$` ("My Workspace" in Snowsight)
- The literal word "workspace" in the user's prompt
- A `<DB>.<SCHEMA>.<NAME>` where `SHOW TABLES` returns nothing but `SHOW WORKSPACES IN SCHEMA <DB>.<SCHEMA>` does

# Snowflake Workspaces

Working with Snowflake Workspaces from CoCo. Router skill: identify the operation, then load the relevant reference.

## Git-backed workspaces: hard rules (read first)

A **git-backed** (git-synced) workspace is a **private** workspace connected to a Git repo. Three rules override any default instinct — full detail in `references/workspace-types.md`:

- **Creating one is UI-only.** Snowsight **Projects » Workspaces » From Git repository**. There is **no `CREATE WORKSPACE` DDL/CLI** for it; never SQL-create a workspace and "attach git later."
- **A shared workspace cannot be git-backed** (and a git-backed workspace can't be shared). Teams collaborate by each using their **own git-backed workspace** + conventional `git` push/pull — **not** `GRANT … ON WORKSPACE`.
- **You cannot determine git-backed status from SQL/CLI.** `DESCRIBE WORKSPACE`/`SHOW WORKSPACES` return **no** repository/branch/git-status column — do not invent one or claim they report it. Say there is **no reliable public way** to tell and point the user to **check in the Snowsight** UI.

## File operations: `cortex ws` via bash

Upload, download, list, remove, and copy run through the **`cortex ws`** CLI subcommand (alias for `cortex workspace`), invoked via `bash`. Three verbs — `cp`, `ls`, `rm` — using an scp-style `DB.SCHEMA.WS:/<absolute-path>` grammar. The CLI builds the `snow://workspace/...` URI internally; you don't build URIs or compute sanitized mount names.

| Command | Intent |
|---|---|
| `cortex ws cp <local> <DB.SCH.WS>:/<remote>` | Upload |
| `cortex ws cp <DB.SCH.WS>:/<remote> <local>` | Download |
| `cortex ws cp <DB.SCH.WS>:/<src> <DB.SCH.WS>:/<dst>` | Server-side copy (same workspace) |
| `cortex ws cp <SRC_DB.SCH.WS>:/<src> <DST_DB.SCH.WS>:/<dst>` | Server-side copy (cross workspace) |
| `cortex ws ls <DB.SCH.WS>:/<prefix>` | List (use `:/` for workspace root) |
| `cortex ws rm <DB.SCH.WS>:/<path>` | Remove |

**FQN identifier rules.** Each of the three FQN segments follows Snowflake identifier rules: **unquoted identifiers are case-insensitive** (Snowflake uppercases them before matching, so `my_db.public.my_ws` resolves to `MY_DB.PUBLIC.MY_WS`); **double-quoted identifiers preserve case** and may contain special characters including `.` and `:`; **embed a literal `"` inside a quoted identifier by doubling it (`""`)**. Pass the FQN exactly as the user gave it. Example: `MY_DB.PUBLIC."weird:ws":/path` is a valid spec where the workspace's actual name is `weird:ws`.

**Gotchas.**
- **Path after `:` must start with `/`.** `DB.SCH.WS:reports/q2.pdf` is a parse error; use `DB.SCH.WS:/reports/q2.pdf`. `DB.SCH.WS:/` lists the root.
- **Single-quote globs on upload** so bash doesn't expand them before the CLI sees them: `cortex ws cp './data/*.csv' DB.SCH.WS:/data/`. Snowflake PUT accepts `*`/`?` within a single directory only — `**` and recursive globs error at parse time.
- **`ls` and `rm` reject all glob characters** in the path — Snowflake LIST/REMOVE don't expand them.
- **`cp` cannot rename** — destination basename always equals source basename. To rename: `cp` to a target with the same basename under the new prefix, then `rm` the original (e.g. `cortex ws cp DB.SCH.WS:/old/foo.py DB.SCH.WS:/new/foo.py && cortex ws rm DB.SCH.WS:/old/foo.py`).
- **GET flattens directory structure** — files from different remote subdirectories land in the same local directory and collide on duplicate names. Download a single file or a single-prefix subset.

**Shared-workspace publish behavior.** On non-`USER$` workspaces, other users only see what's in `head`:
- **Upload** stays in `live` — uploads do NOT publish until you run `ALTER WORKSPACE <fqn> COMMIT` via SQL. The COMMIT also destroys `live`; the next write recreates it.
- **Server-side copy** auto-publishes immediately. No COMMIT needed.
- **Remove** auto-publishes irreversibly — no `ABORT` recovery. **Always confirm with the user before `cortex ws rm` on a non-`USER$` workspace.**

For flags not listed here, run `cortex ws --help` or `cortex ws cp --help`. Don't invoke routinely — the table above covers the common cases.

## Other workspace operations: run SQL

Lifecycle (CREATE/ALTER/DROP), RBAC (GRANT/REVOKE), shared-workspace `ALTER WORKSPACE ... COMMIT` publishing, replication setup, and recovery are SQL — invoke whichever SQL execution tool is available on the current surface. If that tool exposes a `skill_used` parameter, set it to `"snowflake-workspace"` for skill audits.

For these flows you need a verified FQN. Load `references/target-resolution.md` when:

- The user gave a partial name (e.g., "MY_WS") and you need to resolve it via `SHOW TERSE WORKSPACES`.
- `cortex ws` errored with "does not exist or not authorized" and you need to confirm the right target before retrying.
- The user gave no target at all and you need to ask which workspace.

For non-targeted SQL (`SHOW WORKSPACES`, account-wide inventory) target resolution is not needed.

## Workspace types

Three types, identified from the FQN:

| FQN pattern | Type | Notes |
|---|---|---|
| `USER$<u>.PUBLIC.<name>` | Personal (incl. Snowsight's `DEFAULT$` "My Workspace") | Single-user |
| `USER$<u>.LOCAL.<name>` | Personal LOCAL | Single-user, **does not replicate** |
| `<other_db>.<schema>.<name>` | Shared | Multi-user (RBAC) |

For per-type semantics (RBAC, replication exclusion), load `references/workspace-types.md`.

### Git-backed (git-synced) workspaces — a *private* workspace, not a fourth FQN

A **git-backed** (a.k.a. git-synced) workspace is a **private** workspace connected to a Git repo — it lives under `USER$<u>.PUBLIC` like any personal workspace, so it is **not** a distinct FQN pattern you can recognize from the name. The three rules that override default instincts — UI-only creation, git-not-RBAC collaboration, and no public detection — are in the "Git-backed workspaces: hard rules" callout above; for the full semantics load `references/workspace-types.md`.

## Operation routing

| User intent | What to do |
|---|---|
| Upload, download, list, remove, copy files | `cortex ws cp/ls/rm` via bash — see the "File operations" section above. |
| Create, alter, drop, rename a **regular** (personal/shared, non-git) workspace | Standard Snowflake DDL via SQL. Both DROP and RENAME are reversible: `UNDROP WORKSPACE <fqn>` restores a dropped workspace; an `ALTER WORKSPACE ... RENAME TO ...` can be undone by renaming back. |
| Create a **git-backed** workspace | UI-only — Snowsight **Projects » Workspaces » From Git repository**. Never `CREATE WORKSPACE` for this; a git-backed workspace is private and cannot be shared. See "Git-backed workspaces" above and "UI-only operations" below. |
| Tell whether a workspace **is git-backed** | Not determinable from public SQL/CLI (`SHOW`/`DESCRIBE WORKSPACE` don't reveal it). Say so and redirect to the Snowsight UI. See "Git-backed workspaces" above. |
| List workspaces | `SHOW TERSE WORKSPACES` with the narrowest scope. For partial-name lookup: `target-resolution.md`. |
| Grant/revoke access | `GRANT/REVOKE READ\|WRITE\|OWNERSHIP ON WORKSPACE <fqn> TO ROLE <role>`. Per-type details: `workspace-types.md` (Shared). |
| Recover dropped-user workspaces | See `recovery.md`. |
| Convert between Snowsight URL ↔ FQN+path | See `snowsight-urls.md`. |
| Set up replication | Standard replication-group / failover-group syntax — [Snowflake docs](https://docs.snowflake.com/en/user-guide/ui-snowsight/workspaces-replication). LOCAL workspaces don't replicate (`workspace-types.md`). |
| UI-only ops (git push/pull, per-file publish, OAuth, bulk migration) | Redirect to Snowsight, do NOT attempt SQL. See "UI-only operations" below. |

## UI-only operations — DO NOT shell out

The following operations cannot be performed via SQL, the cortex CLI, or `bash`. They require the Snowsight Workspaces UI. When you see any of these signals, redirect to Snowsight; do NOT run `git`, `curl`, or SQL workarounds:

- **Creating a git-backed workspace** — the whole creation flow (repo URL, API integration, OAuth/PAT auth) is Snowsight **Projects » Workspaces » From Git repository**. There is no `CREATE WORKSPACE` DDL for a git-backed workspace; do **not** SQL-create a workspace and try to attach git afterward.
- `git push`, `git pull`, `commit and push` — git from a workspace is UI-only
- "publish only X file" — per-file publish is UI-only (SQL `COMMIT` is all-or-nothing)
- OAuth setup, GitHub auth setup
- Bulk migration of workspaces between accounts

Even when the user's phrasing is ambiguous (could be a local repo, could be a workspace), prefer asking the user over running `git push`.

## SQL execution rules

- For non-file-op SQL, use the surface's SQL execution tool — not bash `snow sql`.
- If that tool exposes a `skill_used` parameter, set it to `"snowflake-workspace"` (powers skill audits).
