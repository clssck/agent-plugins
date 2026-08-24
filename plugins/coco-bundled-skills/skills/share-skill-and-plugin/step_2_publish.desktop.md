# Step 2: Publish the Artifact (Desktop)

Land on `<DB>.<SCHEMA>` (grant USAGE privilege on them to PUBLIC) then make
the shared `<artifact_noun>` exist at `<DB>.<SCHEMA>.<EXTENSION_NAME>` with
the latest local content as a committed live version.

If `<intent> = unshare`, **skip this step entirely**.

Runtime mode: Desktop (SQL-only via active connection). File uploads use
`PUT file://…` via the desktop's active Snowflake connection. If `PUT`
is unavailable, fall back to § **Fallback — COPY FILES from workspace**.
Before issuing any SQL containing `CORTEX EXTENSION`, ensure
[SKILL.md](SKILL.md) § **Cortex Extension — user-facing one-liner** has
been shown once during this run.

## Intent Routing for This Step

Step 2 runs for every share intent (`share-first-time`,
`share-resync`, `share-resync-and-update-share-options`) but the
substeps differ:

| Substep | first-time | re-share* |
| -------------------------------- | :--------: | :-------: |
| 2A.Discover (find ladder rung) | ✅ | ❌ |
| 2A.Provision (CREATE SCHEMA) | ✅ | ❌ |
| 2A.Self-heal (GRANT USAGE; skip if verified) | ✅ | ✅* |
| 2B.Derive `EXTENSION_NAME` + `<skill_basename>` (skill only) | ✅ (name only) | ✅ (`skill_basename` only for skill) |
| 2B.Compose description (ask user) | ✅ | ✅ |
| 2B.MANDATORY STOPPING POINT | ✅ | ✅ |
| 2B.CREATE EXTENSION | ✅ | ❌ |
| 2B.Set COMMENT (`CREATE … COMMENT =` first-time / `ALTER … SET COMMENT` re-share) | ✅ if user gave one | ✅ if user opted to update |
| 2B.ADD LIVE VERSION | ✅ | ✅ |
| 2B.Upload files (see § Upload) | ✅ | ✅ |
| 2B.REMOVE (drop stale files) | ❌ | ✅ |
| 2B.COMMIT / ABORT | ✅ | ✅ |

\* "re-share" = `share-resync` or
`share-resync-and-update-share-options`. Both reuse `<DB>`,
`<SCHEMA>`, and `<EXTENSION_NAME>` from step 1's `DESCRIBE` — never
re-derive them — **unless** step 1 pivoted to `share-first-time` because
manifest `name` ≠ catalog FQN (then follow the first-time column). Self-heal
on re-share runs only when `SHOW GRANTS` shows `USAGE` to `ROLE PUBLIC` is
missing on the personal DB and/or the step-1 schema; see § Self-heal.

**First action in step 2 for any share intent:** if step 1 already set
`share-first-time` after a rename pivot, skip § **Re-share: `name` changed vs
catalog** and run the **first-time** row in the routing table — do **not**
target `<superseded_extension_name>` or the old FQN.

## 2A. Schema Ladder

**Applies to:** `share-first-time` for Discover and Provision. Re-share
skips Discover/Provision; use `<SCHEMA>` from step 1 as `<candidate>` and
run the grant check in § **Self-heal** (skip grants when already confirmed).

### User-facing heads-up *(once per run, before any `CREATE SCHEMA` / `GRANT USAGE` on the personal DB)*

The first time this run is about to either create a `SKILL_SHARING…`
schema in the user's personal DB **or** issue `GRANT USAGE` on the
personal DB or that schema (i.e. the first statement in § Provision or
§ Self-heal), surface this short note to the user — verbatim, once:

> Heads up: I'm setting up a dedicated `SKILL_SHARING…` schema in your
> personal database for shared `<artifact_noun>`s, and granting `USAGE` on the
> database and that schema to `PUBLIC` so the `<artifact_noun>` is reachable.
> This only touches that one schema — your other objects in the personal
> database are not affected.

Do **not** repeat the note before each subsequent `CREATE SCHEMA` or
`GRANT` statement in the same run, and do **not** show it when both
grants are already verified (Discover hit / re-share with grants present)
so no provisioning or grant work is happening.

From `<personal_db>` (e.g. `USER$ALICE`): **rung 1** `SKILL_SHARING`;
**rung 2** `SKILL_SHARING_<X>` (`X` = first 8 hex of
`sha256(lower(<personal_db>))` uppercased); then up to **5** rung-3
attempts `SKILL_SHARING_<X>_<YYYY>` (`YYYY` = 4 random uppercase
letters). Marker comment: `Skill catalog schema auto-created by
system`.

### Discover *(first-time only)*

**Skip this query** if step 1's ambiguous-intent probe already ran it and
passed `<schema_discovery_result>` forward — use that result directly.
Otherwise run:

```sql
SHOW SCHEMAS LIKE 'SKILL_SHARING%' IN DATABASE "<personal_db>";
```

Keep a row only if `name` matches a ladder shape. For each kept row:

```sql
SHOW GRANTS ON DATABASE "<personal_db>";
SHOW GRANTS ON SCHEMA "<personal_db>"."<candidate>";
```

On **both** result sets, a row with `privilege=USAGE`, `granted_to=ROLE`,
`grantee_name=PUBLIC` → **fully provisioned**; reuse `<candidate>` and
**skip § Self-heal** — continue to § 2B. If the schema grant is missing →
**half-provisioned**; do NOT adopt non-interactively, go to § Provision.
If the database grant is missing but the schema grant is present, treat as
**not** fully provisioned (run Self-heal after you have a `<candidate>`).

### Provision *(first-time only)*

Per ladder rung in order (skip half-provisioned). For each
`<candidate>`:

1. `SHOW SCHEMAS LIKE '<candidate>' IN DATABASE "<personal_db>";` —
   row exists → user-owned, skip rung and try the next one.
2. ```sql
   CREATE SCHEMA IF NOT EXISTS "<personal_db>"."<candidate>"
     COMMENT = $$Skill catalog schema auto-created by system$$
   ```
3. Re-DESCRIBE to confirm the schema is created.

4. Run § Self-heal (new schemas need grants).

### Self-heal *(GRANT USAGE; skip when grants already verified)*

**Skip this entire section** when you have already confirmed **both** grants
exist on the personal DB and the target schema:

| Grant target | Check |
| ------------ | ----- |
| `"<personal_db>"` | `SHOW GRANTS ON DATABASE "<personal_db>";` — `USAGE` to `ROLE PUBLIC` |
| `"<personal_db>"."<candidate>"` | `SHOW GRANTS ON SCHEMA "<personal_db>"."<candidate>";` — `USAGE` to `ROLE PUBLIC` |

- **First-time, Discover:** skip when the rung was **fully provisioned** (both
  checks passed during Discover).
- **First-time, Provision:** always run the `GRANT` statements below (new schema).
- **Re-share:** `<candidate>` = `<SCHEMA>` from step 1. Run both `SHOW GRANTS`
  above first; skip this section if both are present, otherwise issue grants.

When not skipping, for first-time `<candidate>` is the rung you provisioned;
for re-share it is the schema from step 1.

```sql
GRANT USAGE ON DATABASE "<personal_db>" TO ROLE PUBLIC;
GRANT USAGE ON SCHEMA "<personal_db>"."<candidate>" TO ROLE PUBLIC;
```

If `GRANT USAGE ON SCHEMA` fails AND the schema was just created
*(first-time only)*: `DROP SCHEMA IF EXISTS "<personal_db>"."<candidate>";`
then propagate the original error. You should not keep creating schemas and
leave them in the personal database. For re-share, never DROP a
pre-existing schema — surface the GRANT error directly.

## 2B. Share (package + commit)

### Derive names from manifest `name`

All share uploads use the same source string. Parse step 1 first.

1. Let `<artifactname>` =
   - **Skill:** trimmed `name` from `SKILL.md` frontmatter.
   - **Plugin:** trimmed `name` from `plugin.json`.
2. If `name` is missing, fall back to the folder name: `basename(<artifact_dir>)`.

From `<artifactname>` derive identifiers (do not use the raw folder name
for stage paths when `name` is present):

#### Cortex Extension object name — `<EXTENSION_NAME>` *(first-time only)*

Re-share intents skip this sub-block — they already have `<id>` and `<fqn>`
from step 1's `DESCRIBE`.

| Step | Rule |
| ---- | ---- |
| 1 | Uppercase the entire string |
| 2 | Replace every `-` with `_` |
| 3 | Replace every whitespace character (spaces, tabs, etc.) with `_` |

```
<EXTENSION_NAME> = trim(<artifactname>)
  .toUpperCase()
  .replace(/-/g, "_")
  .replace(/\s/g, "_")
```

Examples: `sql-patterns` → `SQL_PATTERNS`; `code-review` → `CODE_REVIEW`;
`my skill` → `MY_SKILL`; `my plugin` → `MY_PLUGIN`.

Let `<id> = "<DB>"."<SCHEMA>"."<EXTENSION_NAME>"` and `<fqn> =
<DB>.<SCHEMA>.<EXTENSION_NAME>` (unquoted; for stage URIs).

#### Stage folder under `skills/` — `<skill_basename>` *(skill only, all share intents)*

When `<artifact_type> = skill` only. Path segment (do not use
`<EXTENSION_NAME>` here):
`snow://cortex_extension/<fqn>/versions/live/skills/<skill_basename>/…`
It is **not** the SQL object name and **not** the host folder name unless
`name` was missing above.

| Step | Rule |
| ---- | ---- |
| 1 | Lowercase the entire string (kebab-case) |
| 2 | Replace every `_` with `-` |
| 3 | Replace every whitespace character with `-` |

```
<skill_basename> = trim(<artifactname>)
  .toLowerCase()
  .replace(/_/g, "-")
  .replace(/\s/g, "-")
```

Examples: `sql-patterns` → `sql-patterns`; `SQL_PATTERNS` in frontmatter →
`sql-patterns`; `my skill` → `my-skill`; `my_skill` → `my-skill`.

Re-share still uses this layout when uploading files — derive from the current
`SKILL.md` `name`, not from the extension object name (`SQL_PATTERNS` ≠
`sql-patterns` on disk).

### Re-share: `name` changed vs catalog *(⚠️ MANDATORY GATE — before anything else)*

**Skip** if `<intent>` is already `share-first-time` (step 1 pivoted after a
rename).

For `share-resync` / `share-resync-and-update-share-options` only: resolve
`<artifactname>` the same way as § Derive names (trimmed `name` when present;
otherwise folder fallback from `<artifact_dir>`). Compute
`<name_implied_extension>` with the § Cortex Extension object name transform.
Compare case-insensitively to `<EXTENSION_NAME>` from step 1's catalog FQN.

If they **differ**, this is a **hard stop** on the old extension:

- **Do not** `ALTER`, `ADD LIVE VERSION`, upload, `LIST`/`REMOVE`, or `COMMIT`
  on the old `<id>`.
- **Do not** ask the user whether to "update the existing share anyway" — user
  phrasing and an old FQN in the message **never** override this gate.
- Tell the user (same message as step 1 § **Re-share: renamed artifact?**).
- Set `<intent>` = `share-first-time`, re-derive `<EXTENSION_NAME>`, `<id>`, and
  `<fqn>` from `name`, then **restart step 2 on the first-time path** (schema
  ladder + `CREATE CORTEX EXTENSION` for the new name).

If they match, continue below (including § Remove Stale Files when applicable).

### Compose Description *(all share intents)*

Decide the catalog **COMMENT** via a plain-text prompt. Do **not** copy
TUI affordances (`[Ctrl+T]`, "Press Enter to save", "Press Escape to go
back") into the chat — the agent's UX is text, not a TUI.

Let `<current_description>` come from:

| Intent | Source |
| ------ | ------ |
| `share-first-time` | `<artifact_description>` from step 1 (manifest; may be empty) |
| `share-resync` / `share-resync-and-update-share-options` | `<existing_comment>` from step 1 `DESCRIBE` (may be empty) |

Show the current description in chat (use `[none]` if empty), then call
`ask_user_question` per
[share_interactive_prompts.md](../references/share_interactive_prompts.md)
§ **Catalog description**. If the user picks **Replace** or **Add**, ask
once in chat for the new or append text. **Do not** present keep / replace /
add / skip as a markdown bullet list.

**Compose `<comment>` from the picker** (and any follow-up chat text):

| Choice | `<comment>` |
| ------ | ----------- |
| Keep current description | `<current_description>` |
| Replace with new text | user-supplied text |
| Add to current description | `<current_description>` + `\n\n` + text when non-empty; else just text |
| Skip — don't set catalog description | (unset — leave `<comment>` empty) |

Apply the 1024-char truncation rule to the composed string; overflow gets
suffix `…`.

**`<comment_action>` by intent**

| Intent | Non-empty `<comment>` (`keep` / `replace` / `add`) | `skip` reply |
| ------ | -------------------------------------------------- | ------------ |
| `share-first-time` | `set-on-create` | `skip-comment` |
| `share-resync` / `share-resync-and-update-share-options` | `update` | `skip` |

For re-share, when `<comment_action> = skip`, preserve the existing catalog
COMMENT. When the composed string equals `<existing_comment>`, you may
still set `update` (idempotent) or `skip` if nothing changed.

### ⚠️ MANDATORY STOPPING POINT *(all share intents)*

Show `<id>`, `<fqn>`, the composed `<comment>` (or "[none]"), and
`<comment_action>` (one of `set-on-create` / `skip-comment` /
`update` / `skip`) in chat. Also note first-time create vs re-share update.
Call `ask_user_question` per
[share_interactive_prompts.md](../references/share_interactive_prompts.md)
§ **Publish confirm** before any CREATE / ALTER / file upload. If the user
chooses **Edit description first**, revise `<comment>` and re-run this stop;
if they choose **Cancel**, stop without creating, altering, or uploading.

### CREATE or ALTER the Extension

> **Only two statements are valid for the COMMENT on a Cortex Extension.**
> Do **not** emit `COMMENT ON CORTEX EXTENSION <id> IS $$…$$;` — that
> syntax does not exist for Cortex Extensions and will raise a parse
> error. Use the inline `COMMENT =` clause on `CREATE` for first-time, or
> `ALTER CORTEX EXTENSION <id> SET COMMENT = $$…$$` for re-share.

Branch by intent and `<artifact_type>`:

- **`share-first-time`** — set the COMMENT **inline on `CREATE`** in a
  single statement so the user-confirmed description is bound to the
  initial object. **Must include explicit `TYPE`:**

  **Skill** (`<artifact_type> = skill`):
  - When `<comment_action> = set-on-create`:
    ```sql
    CREATE CORTEX EXTENSION <id> TYPE = 'SKILL'
      COMMENT = $$<comment>$$;
    ```
  - When `<comment_action> = skip-comment`:
    ```sql
    CREATE CORTEX EXTENSION <id> TYPE = 'SKILL';
    ```

  **Plugin** (`<artifact_type> = plugin`):
  - When `<comment_action> = set-on-create`:
    ```sql
    CREATE CORTEX EXTENSION <id> TYPE = 'PLUGIN'
      COMMENT = $$<comment>$$;
    ```
  - When `<comment_action> = skip-comment`:
    ```sql
    CREATE CORTEX EXTENSION <id> TYPE = 'PLUGIN';
    ```

  Do **not** issue a follow-up `ALTER … SET COMMENT` on first-time —
  the inline `COMMENT =` is the only write needed.

  > **Feature gate (first-time path only):** This `CREATE` is the first
  > `CORTEX EXTENSION` statement on a first-time share. If it fails with
  > a parse-level error — `syntax error` near `CORTEX`/`EXTENSION`,
  > `unsupported feature` referencing `CORTEX EXTENSION`, or
  > `object type 'cortex extension' is not supported` — the feature is
  > **not enabled** on this account. **Stop** and follow
  > [SKILL.md](SKILL.md) § **Cortex Extensions feature not enabled on
  > this account**. Do not retry, do not `ADD LIVE VERSION`, do not
  > upload. The provisioned `SKILL_SHARING…` schema may be left in place.

  > **Object already exists (first-time path only):** If `CREATE` fails
  > with an error whose message (case-insensitive) contains
  > `already exists` or `object already exists`, a Cortex Extension with
  > this name was shared previously. Derive the URI as
  > `snow://skill_catalog/<DB>.<SCHEMA>.<EXTENSION_NAME>/`, show it in
  > chat, and call `ask_user_question` per
  > [share_interactive_prompts.md](../references/share_interactive_prompts.md)
  > § **Reshare combined stop** (use `<artifact_noun>` wording). Ask for role
  > names in chat if the **To a specific ROLE…** label is picked.
  >
  > **Do not** retry `CREATE`, `ADD LIVE VERSION`, upload, or `COMMIT`.
  > Map picker labels per step 1 §3 ambiguous reshare (store
  > `<share_choice>` / `<share_roles>` / `<discoverable_value>` for options
  > 1–3). Before pivoting on any of the four reshare-content labels (the
  > three audience labels or **Keep current share options…**), run
  > `DESCRIBE CORTEX EXTENSION <id>;` to capture `<existing_comment>` and
  > `discoverable`, and verify `type` matches `<artifact_type>`. If `type`
  > does not match, stop with the type-mismatch error from step 1 § SQL.
  > Then set `<DB>`, `<SCHEMA>`, `<EXTENSION_NAME>` from `<id>` and
  > **restart step 2 on the re-share path** (skip schema ladder
  > Discover/Provision; run Self-heal, then continue from § **2B. Share**).
  > Step 3 runs only when intent is `share-resync-and-update-share-options`.
  > **Different skill/plugin…** picker → DROP-or-rename message from step 1 §3;
  > **Done — do not proceed.**

- **`share-resync` / `share-resync-and-update-share-options`** —
  only when `<comment_action> = update`:
  ```sql
  ALTER CORTEX EXTENSION <id> SET COMMENT = $$<comment>$$;
  ```
  When `<comment_action> = skip`, do **not** touch the COMMENT —
  preserve whatever is already in the catalog.

`$$…$$` dollar quoting (or single quotes when the string contains
none) avoids escaping issues for descriptions with `'`, `"`, or
newlines.

### Open Live Version *(all share intents)*

Pick a fresh `<live_alias> = SYNC_<unix_ms>` (unquoted, unique per retry).
Get the current timestamp via SQL:

```sql
SELECT DATE_PART('epoch_millisecond', CURRENT_TIMESTAMP());
```

```sql
ALTER CORTEX EXTENSION <id> ADD LIVE VERSION <live_alias> FROM LAST;
```

### Upload Files *(all share intents)*

Upload layout **forks on `<artifact_type>`**. Load the appropriate sub-file and
follow it entirely before returning here for § Remove Stale Files:

- **`<artifact_type> = skill`** → load and follow
  [step_2_upload_skill.md](step_2_upload_skill.md)
- **`<artifact_type> = plugin`** → load and follow
  [step_2_upload_plugin.md](step_2_upload_plugin.md)

Use `PUT file://<local_path> INTO <stage_uri>` via the active Snowflake
connection. If `PUT` fails (with a non-limit error), follow
§ **Fallback — COPY FILES from workspace** below.

### Fallback — COPY FILES from workspace

Use **only after** `PUT file://…` fails with a non-limit error. Do not use
when the failure is a **stage limit error** per
[SKILL.md](SKILL.md) § **Stage file size and count limits** —
stop and surface the error instead.

1. Ask the user to upload their skill/plugin directory to their personal
   workspace. Resolve the workspace path:
   ```sql
   DESCRIBE WORKSPACE USER$<CURRENT_USER()>.PUBLIC."DEFAULT$";
   ```
   The workspace stage URI will be in the result. Skill files should be placed
   under `versions/live/.snowflake/cortex/skills/<folder>/` or
   `versions/live/.snowflake/si/skills/<folder>/`.

2. Once the user confirms the files are in their workspace, use `COPY FILES`
   to copy each file from the workspace stage to the extension stage:

   **Skill** — copy per file:
   ```sql
   COPY FILES
     INTO $$snow://cortex_extension/<fqn>/versions/live/skills/<skill_basename>/<relative_dir>/$$
     FROM $$<workspace_stage_uri>/versions/live/.snowflake/cortex/skills/<folder>/<relative_dir>/$$;
   ```

   **Plugin** — copy flat under `versions/live/`:
   ```sql
   COPY FILES
     INTO $$snow://cortex_extension/<fqn>/versions/live/<relative_dir>/$$
     FROM $$<workspace_stage_uri>/versions/live/<relative_dir>/$$;
   ```

3. After all files are copied, proceed to § Remove Stale Files (if applicable)
   then § Commit or Abort.

### Remove Stale Files *(re-share only)*

`share-first-time` has no prior sync state — skip this block.

**Skill** — list under the skill prefix:

```sql
LIST $$snow://cortex_extension/<fqn>/versions/live/skills/<skill_basename>/$$;
```

Issue one `REMOVE` per remote file not present in the new skill tree
(discovered by enumerating `<artifact_dir>` on disk):

```sql
REMOVE $$snow://cortex_extension/<fqn>/versions/live/skills/<skill_basename>/<previous_rel_path>$$;
```

**Plugin** — list at the live root:

```sql
LIST $$snow://cortex_extension/<fqn>/versions/live/$$;
```

Issue one `REMOVE` per remote file not present in the new plugin tree:

```sql
REMOVE $$snow://cortex_extension/<fqn>/versions/live/<previous_rel_path>$$;
```

Recurse into subprefixes if needed.

If remote listing is unavailable, skip REMOVE rather than guess.

If § **Re-share: `name` changed vs catalog** already pivoted to first-time share,
skip this section.

### Commit or Abort *(all share intents)*

```sql
ALTER CORTEX EXTENSION <id> COMMIT;
```

If ANY of `ADD LIVE VERSION` / upload (`PUT` or `COPY FILES`)
/ `REMOVE` / `COMMIT` fails:

- **Stage limit error** — follow [SKILL.md](SKILL.md) § **Stage file size and
  count limits**. This **still requires** `ALTER CORTEX EXTENSION <id> ABORT;`
  (per that section's step 5, since `ADD LIVE VERSION` already succeeded here) to
  avoid leaking the open `SYNC_<ts>` version — only the user-facing message
  differs. Then go to [step 5](step_5_report_result.md).
- **Any other error** — `ALTER CORTEX EXTENSION <id> ABORT;` (ignore failure;
  original error wins). Without ABORT, every failed retry leaks a `SYNC_<ts>`
  open version.

## Next

| Condition | Next step |
| --------- | --------- |
| `<intent> = share-resync` | [step 5](step_5_report_result.md) — content-only; no grant or DISCOVERABLE changes |
| `share-first-time` or `share-resync-and-update-share-options` | [step 3](step_3_apply_share_options.md) — apply share options via SQL |

When step 3 runs, it **skips its audience question** if step 1 already set
`<share_choice>` / `<share_roles>` / `<discoverable_value>`.
