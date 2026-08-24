---
name: snowflake-workspace
description: >-
  MANDATORY for Snowflake workspace operations: workspace lifecycle (CREATE/ALTER/DROP/RENAME),
  file MOVEMENT (upload, download, list, remove, copy) via the `cortex ws` CLI subcommand, RBAC
  (GRANT READ/WRITE), shared-workspace publishing (`ALTER WORKSPACE ... COMMIT` to make uploads
  visible to other users), dropped-user recovery (DROPPED_USER$), replication setup, account-wide
  audit. Use when the user uploads, downloads, lists, removes, or copies files in a workspace;
  creates, alters, or drops a workspace; shares or revokes access; recovers content from a dropped
  user; sets up workspace replication; or references snow://workspace URIs, USER$ schemas, LOCAL
  schema workspaces, DEFAULT$/My Workspace, or secondary/read-only replicas. Triggers: workspace,
  workspaces, snow://workspace, USER$, DEFAULT$, personal workspace, shared workspace, ALTER
  WORKSPACE, GRANT WORKSPACE, list workspace, files in workspace, "what's in my workspace",
  secondary replica, dropped user.
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

For per-type semantics (RBAC, replication exclusion), load `references/workspace-types.md`. Git operations on any workspace type are UI-only — see the "UI-only operations" section below.

## Operation routing

| User intent | What to do |
|---|---|
| Upload, download, list, remove, copy files | `cortex ws cp/ls/rm` via bash — see the "File operations" section above. |
| Create, alter, drop, rename a workspace | Standard Snowflake DDL via SQL. Both DROP and RENAME are reversible: `UNDROP WORKSPACE <fqn>` restores a dropped workspace; an `ALTER WORKSPACE ... RENAME TO ...` can be undone by renaming back. |
| List workspaces | `SHOW TERSE WORKSPACES` with the narrowest scope. For partial-name lookup: `target-resolution.md`. |
| Grant/revoke access | `GRANT/REVOKE READ\|WRITE\|OWNERSHIP ON WORKSPACE <fqn> TO ROLE <role>`. Per-type details: `workspace-types.md` (Shared). |
| Recover dropped-user workspaces | See `recovery.md`. |
| Convert between Snowsight URL ↔ FQN+path | See `snowsight-urls.md`. |
| Set up replication | Standard replication-group / failover-group syntax — [Snowflake docs](https://docs.snowflake.com/en/user-guide/ui-snowsight/workspaces-replication). LOCAL workspaces don't replicate (`workspace-types.md`). |
| UI-only ops (git push/pull, per-file publish, OAuth, bulk migration) | Redirect to Snowsight, do NOT attempt SQL. See "UI-only operations" below. |

## UI-only operations — DO NOT shell out

The following operations cannot be performed via SQL, the cortex CLI, or `bash`. They require the Snowsight Workspaces UI. When you see any of these signals, redirect to Snowsight; do NOT run `git`, `curl`, or SQL workarounds:

- `git push`, `git pull`, `commit and push` — git from a workspace is UI-only
- "publish only X file" — per-file publish is UI-only (SQL `COMMIT` is all-or-nothing)
- OAuth setup, GitHub auth setup
- Bulk migration of workspaces between accounts

Even when the user's phrasing is ambiguous (could be a local repo, could be a workspace), prefer asking the user over running `git push`.

## SQL execution rules

- For non-file-op SQL, use the surface's SQL execution tool — not bash `snow sql`.
- If that tool exposes a `skill_used` parameter, set it to `"snowflake-workspace"` (powers skill audits).
