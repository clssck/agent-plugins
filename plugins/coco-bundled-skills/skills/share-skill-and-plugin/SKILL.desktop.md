---
name: share-skill-and-plugin
description: >
  Share or unshare a local skill or plugin to users within the same account by
  executing the Cortex Extension share SQL directly. Use when the user says
  "share skill", "publish skill", "share my skill", "share plugin", "publish
  plugin", "share my plugin", "share with users", "share publicly", "upload to
  cortex extension", "publish my skill", "publish my plugin", "make available",
  "add to skill catalog", "add to catalog", "add skill to catalog", "add plugin
  to catalog", "add my skill to the catalog", "publish to skill catalog",
  "publish to the catalog", "submit to skill catalog", "put in the skill
  catalog", "unshare skill", "unshare plugin", "stop sharing", "remove shared",
  "revoke access", "remove from catalog", "delete from catalog" or "delete shared". 
  This is for publishing a local skill or plugin TO the catalog; to install or pull 
  an existing skill FROM the catalog, use find-skill-and-plugin instead. 
  Does not handle consumer/install flows. Does not handle sharing across accounts.
argument-hint: "[local skill or plugin path | DB.SCHEMA.EXTENSION FQN]"
tools: ["ask_user_question"]
---

## (CoCo Desktop Only) When to Use

User wants to share, re-share, or stop sharing a local **skill** or **plugin**
(see trigger phrases in `description:`). Same-account sharing only.

The skill **publishes to the Snowflake skill catalog** using SQL via the
desktop's active Snowflake connection.

## Artifact type (`<artifact_type>`)

Before Step 2, set `<artifact_type>` ∈ {`skill`, `plugin`}. This selects
manifest parsing, CREATE `TYPE`, upload layout, and type guards.

**Detection order** (Step 1):

1. User says "skill" or "plugin" explicitly.
2. Directory contains `SKILL.md` at root → `skill`.
3. Dot-prefixed subdirectory contains `plugin.json` → `plugin`.
4. Re-share / unshare via FQN or `snow://skill_catalog/...` → `DESCRIBE`
   `type` column is authoritative (`skill` or `plugin`).
5. Both markers present, or neither → ⚠️ **one disambiguation picker**
   (the labels defined under
   § **Artifact type**).

Carry `<artifact_noun>` = "skill" or "plugin" for user-facing copy.

## Cortex Extension — user-facing one-liner

> A **Cortex Extension** is the Snowflake schema-level object that backs every
> shared skill or plugin (one extension per shared artifact). It stores the
> files as a live version and holds the `READ` grants that control who can use
> it.

Surface once per run before the first publish/unshare SQL the user will see.

## Plugin structure (when `<artifact_type> = plugin`)

A plugin directory contains a **hidden manifest directory** (name starts with
`.`) with `plugin.json`. Common names: `.cortex-plugin/`, `.claude-plugin/`.
Discover at runtime; do not assume a fixed name.

| Field | Purpose |
| ----- | ------- |
| `name` | Extension object name (uppercase transform in Step 2) |
| `description` | Cortex Extension `COMMENT` on first share |
| `version` | Informational only |

Files upload **flat** under `versions/live/`, preserving local structure
(including the manifest directory). No `skills/<basename>/` wrapper.

## Skill structure (when `<artifact_type> = skill`)

Root `SKILL.md` with YAML frontmatter (`name`, `description`, `summary`,
`info`, `version`). Files upload under
`versions/live/skills/<skill_basename>/` where `<skill_basename>` is
kebab-case from `name`.

## Runtime modes

Packaging **files** differs by runtime. Schema ladder, extension DDL, grants,
and unshare are SQL-only in both modes.

| Mode | When | Source | Upload |
| ---- | ---- | ------ | ------ |
| **Desktop** | CoCo Desktop (active SQL connection) | Local path | `PUT file://…` via active connection |

**Upload fallback:** If `PUT file://…` fails with a non-limit error, ask the
user to upload their skill/plugin folder to their personal workspace, then use
`COPY FILES` from the workspace stage. Resolve the workspace path once:

```sql
DESCRIBE WORKSPACE USER$<CURRENT_USER()>.PUBLIC."DEFAULT$";
```

Skill workspace hints: `…/versions/live/.snowflake/cortex/skills/<folder>/` or
`…/.snowflake/si/skills/<folder>/`. See
[workspaces/personal-skills-sync/SKILL.md](../snowflake-workspace/SKILL.md).

**Unshare** (`1→4→5`) uses SQL only — no upload.

## Interactive prompts

Every fixed-choice stop uses `ask_user_question` with locked labels in
the labels defined under.

Audience state (both artifact types): `<share_choice>` (1/2/3),
`<share_roles>`, `<discoverable_value>`.

## Do Not Do

- Do not route to generic catalog browse when intent is share / unshare.
- Do not present stopping-point choices as markdown lists when
  `ask_user_question` is available.
- Do not handle install / consume flows.
- Do not bounce the user to Skill Manager UI for unshare.
- Do not silently change DISCOVERABLE or audience on content-only re-share.
- Do not ALTER / upload / COMMIT when manifest `name` ≠ catalog FQN — pivot to
  first-time share on the new name.
- Do not share a **skill** into a non-skill extension or a **plugin** into a
  non-plugin extension.
- Do not use `TYPE = 'SKILL'` on plugin extensions or omit `TYPE = 'PLUGIN'`
  on plugin CREATE.
- Do not run `cortex skill catalog publish` or `cortex plugin publish` CLI
  commands — these use the CLI connection, not the desktop's active connection.

## Workflow

Load each step file before executing.

1. [step_1_collect_inputs.md](step_1_collect_inputs.md)
2. Share: [step_2_publish.md](step_2_publish.md) — SQL only (desktop connection)
3. Share: [step_3_apply_share_options.md](step_3_apply_share_options.md)
4. Unshare: [step_4_unshare.md](step_4_unshare.md)
5. Both: [step_5_report_result.md](step_5_report_result.md)

## Routing

| Intent | Path | Flow |
| ------ | ---- | ---- |
| `share-first-time` / `…-update-share-options` | SQL | `1→2→3→5` |
| `share-resync` | SQL | `1→2→5` |
| `unshare` | n/a | `1→4→5` |
| Renamed artifact | n/a | pivot `share-first-time` on new name |

## Shared identifiers

- **Extension name:** manifest `name` → uppercase, `-`/whitespace → `_`.
- **Skill stage folder:** kebab-case from `name` → `skills/<skill_basename>/`.
- **Personal DB:** `USER$<CURRENT_USER()>`.
- **Schema ladder:** `SKILL_SHARING`, `SKILL_SHARING_<8HEX>`,
  `SKILL_SHARING_<8HEX>_<XXXX>`.
- **Share URI:** `snow://skill_catalog/<DB>.<SCHEMA>.<EXTENSION>/…`
- **COMMENT cap:** 1024 chars.

## SQL quoting

Double-quote identifiers; dollar-quote string literals (`$$…$$`).

## Failure contract

Surface Snowflake error + failing statement. No silent retries.

### Stage file size and count limits

When syncing files to the Cortex Extension stage (`versions/live/…`), the
server enforces account limits (defaults: **50 files**, **2 MB per file**,
**10 MB total**). Limits may differ per account.

**Example error** (wording varies by which limit was hit):

```text
Error: Failed to sync skill files for <DB>.<SCHEMA>.<EXTENSION> Cortex Extension
'<EXTENSION>' version exceeds the configured size or file-count limits:
file count 51 exceeds the maximum of 50
```

**Detect a stage-limit error** when the message (case-insensitive) contains
`exceeds the configured size or file-count limits`, or any fragment below:

| Limit violated | Message fragment |
| -------------- | ---------------- |
| File count > max | `file count {count} exceeds the maximum of {maxCount}` |
| Total size > max | `total size {bytes} bytes exceeds the maximum of {maxBytes}` |
| Any file > max | `per-file size limit of {maxBytesPerFile} bytes exceeded by: {filePaths}…` |

**On stage-limit error — all publish modes** (`PUT` / `COPY FILES`, or `COMMIT`
after upload):

1. **Stop immediately.** Do **not** fall back to another upload path or retry
   the same upload in a loop.
2. Surface the **verbatim** server error.
3. Tell the user which limit was violated when the fragment makes it clear
   (file count, total size, or per-file size).
4. Advise them to **adjust the local skill or plugin** (fewer/smaller files) and
   share again, or **contact Snowflake support** to raise the account limit.
5. If a live version was opened (`ADD LIVE VERSION` succeeded), you **must**
   still run `ALTER CORTEX EXTENSION <id> ABORT;` (ignore ABORT failure).
   Stopping does **not** mean skipping ABORT — without it, the `SYNC_<ts>`
   open version leaks.

### Cortex Extensions feature not enabled

On first `CORTEX EXTENSION` statement failure (parse / unsupported feature),
stop and tell the user sharing via Cortex Extensions is not enabled; contact
support. Do not retry or upload.
