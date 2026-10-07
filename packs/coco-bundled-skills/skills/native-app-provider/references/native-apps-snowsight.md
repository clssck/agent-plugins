# Native Apps in Snowsight — Environment Reference

Load when your system prompt mentions Snowsight. Governs all env-specific decisions for native-app work: when to push the user to a different environment, how to read package files, and what to refuse.

## Detecting Where You Are

Look for these markers in your system prompt, in order:

- Contains `"You are in a Workspace"` → **Snowsight Workspaces**. `write` / `read` / `edit` available.
- Contains `"You are NOT in a Workspace"` → **Snowsight Non-Workspaces** (Snowflake Intelligence). File tools are clunky for writes; reads work via the stage method.
- Mentions Snowsight but neither phrase above → default to **Snowsight Non-Workspaces** (the more restrictive option — safer to push the user to a better env than to assume `write`/`edit` exist).
- No Snowsight mention at all → **Cortex CLI**. Full file access plus local filesystem. (You shouldn't have loaded this reference; skip it.)

## Decision Flow

Classify the user's request into one of three shapes, then apply the rule for your environment. When in doubt, assume the task will modify files and follow shape 1.

### Shape 1 — Task modifies package files

Examples: edit `manifest.yml`, change the setup script, add/modify a service spec, edit Streamlit files, add a container, add an EAI block, change privileges, etc.

#### In Workspaces

1. If the task touches **3+ files** (e.g., manifest + setup script + streamlit + environment.yml):

   **⚠️ MANDATORY STOPPING POINT**: Stop immediately. Do not run any more tools or read any more sub-skills. Present this message to the user:
   > "This involves changes to multiple files. [Cortex CLI](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-cli) is significantly better for multi-file native app workflows — it has a real local filesystem, faster iteration, and avoids the stage-upload complexity that causes errors in Workspaces. Would you like to switch to CLI for this?"

   Do NOT proceed until the user responds. If they say yes, stop. If they say no or ask to continue here, proceed.
2. For 1-2 file changes, proceed without comment.

#### In Non-Workspaces

1. **First turn, always**: strongly recommend **[Cortex CLI](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-cli)**. The CLI is the only environment with a real iteration loop for native-app file edits — anything else is a tax on the user. Frame it as the recommended path, not an alternative. **Then stop and wait for the user to respond.** Do not start executing SQL against the package on the same turn.
2. If the user explicitly refuses CLI (says something like "I can't use the CLI" or "I want to stay in Snowsight"): recommend **Workspaces** (has `write` / `edit` / `read` and avoids the stage-write loop). Stop and wait again.
3. **Only** if the user has explicitly refused **both** CLI and Workspaces in the current conversation: you may attempt the stage-write loop below — with hard limits:
   - **One file, one targeted change.** If the request touches `manifest.yml` plus a setup script plus anything else, refuse — that is a refactor by definition, push CLI again.
   - **Brand-new / empty packages are always refactors.** A package with zero files uploaded needs manifest + setup script at minimum to be usable; that is multi-file. Refuse and push CLI, do not bootstrap a package via stage-writes.
   - **Phrases like "don't stop", "just do it", "walk me through", or "tell me the next step" are NOT refusals.** They mean push CLI harder and re-explain the cost, not skip ahead.
   - Warn explicitly, every time you do attempt a stage-write: *"This is best-effort in non-Workspaces. CLI or Workspaces is strongly recommended for anything beyond a single targeted change."*

### Shape 2 — Task reads package files but does not modify them

Examples: walk a manifest, inspect a setup script, debug a failed version, look up what's deployed.

- **Workspaces**: proceed normally — use the Workspaces snippet under "Reading a File From a Package".
- **Non-Workspaces**: proceed using the stage-method read snippet. Mention Workspaces as smoother if you expect to chain several file reads.

### Shape 3 — SQL only, no file I/O

Examples: privilege checks, telemetry queries, `SHOW` / `DESCRIBE` introspection, configuration changes via `ALTER`.

- Proceed normally in any environment.

## Reading a File From a Package

> **Note:** This reference is for traditional native app packages (TYPE = NATIVE). Declarative packages (TYPE = DATA) use the `snow://package` URL scheme and are handled by the `declarative-sharing` skill — do not mix the two.

Native app packages store files on a named stage inside the package (created during the deploy-test workflow). Use standard stage commands.

First, discover the stage:

```sql
SHOW STAGES IN APPLICATION PACKAGE <PKG>;
```

Then list files:

```sql
LIST @<PKG>.<schema>.<stage>/<path>/;
```

### Workspaces

```sql
-- Copy from stage to workspace for editing
COPY FILES INTO 'snow://workspace/USER$.PUBLIC.DEFAULT$/app_files/'
  FROM @<PKG>.<schema>.<stage>/<path>/
  FILES = ('manifest.yml');
```

Then `read` / `edit` the file in the workspace.

### Non-Workspaces

```sql
CREATE OR REPLACE STAGE download_stage;
COPY FILES INTO @download_stage/
  FROM @<PKG>.<schema>.<stage>/<path>/
  FILES = ('manifest.yml');

CREATE OR REPLACE FILE FORMAT raw_text_fmt
  TYPE = CSV FIELD_DELIMITER = NONE RECORD_DELIMITER = NONE
  COMPRESSION = NONE ESCAPE = NONE ESCAPE_UNENCLOSED_FIELD = NONE;

SELECT $1 AS content FROM @download_stage/manifest.yml (FILE_FORMAT => 'raw_text_fmt');
```

All five `NONE` params are required — dropping any of them corrupts the YAML/SQL with compression, escaping, or quoting. Repeat the `COPY FILES` + `SELECT` for each additional file (e.g., `scripts/setup.sql`).

### CLI

```sql
GET @<PKG>.<schema>.<stage>/<path>/manifest.yml file:///tmp/;
```

Default to `/tmp/`; ask first before downloading elsewhere.

## Uploading Files From Workspace to Package Stage

In Workspaces, `PUT` does not work (it only accepts `file://` local paths, which don't exist in Snowsight). Use `COPY FILES` to transfer files from the workspace to the package stage.

`COPY FILES` automatically overwrites existing files with the same name — no need to REMOVE first.

### Discover the workspace path first

The workspace URL varies by user. Before copying, run LIST to confirm the exact path:

```sql
LIST 'snow://workspace/<workspace_name>/versions/live/';
```

Common workspace name patterns:
- `USER$.PUBLIC.DEFAULT$` (CLI context)
- `USER$<USERNAME>.PUBLIC.DEFAULT$` (Snowsight with specific user)

If unsure, try `USER$.PUBLIC.DEFAULT$` first. If it errors, check the workspace name in the Snowsight sidebar.

### Copy syntax

The FROM path must include the full directory path to the file. FILES contains **only the filename** — never a subdirectory path. Always include a trailing `/` on both the INTO and FROM paths.

```sql
-- Root-level files (manifest.yml, README.md):
COPY FILES INTO @<PKG>.<schema>.<stage>/
  FROM 'snow://workspace/<workspace_name>/versions/live/<app_dir>/'
  FILES = ('manifest.yml');

-- Subdirectory files (scripts/setup.sql):
COPY FILES INTO @<PKG>.<schema>.<stage>/scripts/
  FROM 'snow://workspace/<workspace_name>/versions/live/<app_dir>/scripts/'
  FILES = ('setup.sql');
```

**Common mistakes:**

```sql
-- ❌ WRONG: subdir in FILES → file lands at scripts/scripts/setup.sql
COPY FILES INTO @PKG.STAGE_CONTENT.APP_STAGE/scripts/
  FROM 'snow://workspace/.../versions/live/myapp/'
  FILES = ('scripts/setup.sql');

-- ❌ WRONG: missing trailing slash on INTO → file lands at "scriptssetup.sql"
COPY FILES INTO @PKG.STAGE_CONTENT.APP_STAGE/scripts
  FROM 'snow://workspace/.../versions/live/myapp/scripts/'
  FILES = ('setup.sql');

-- ✅ RIGHT: trailing slash on INTO, subdir in FROM, only filename in FILES
COPY FILES INTO @PKG.STAGE_CONTENT.APP_STAGE/scripts/
  FROM 'snow://workspace/.../versions/live/myapp/scripts/'
  FILES = ('setup.sql');
```

Do NOT use `PUT` in Workspaces — it will fail with `invalid source URL scheme`.

## Inspect a Package Without Editing

When the user wants to know "what's wrong with my package" or "walk my manifest" without making changes:

1. `SHOW APPLICATION PACKAGES LIKE '<PKG>';` and `SHOW VERSIONS IN APPLICATION PACKAGE <PKG>;` — flag `INITIALIZING` / `FAILED` versions on their own.
2. Check for uploaded files: `SHOW STAGES IN APPLICATION PACKAGE <PKG>;` then `LIST @<PKG>.<schema>.<stage>/` — if 0 rows, artifacts were never uploaded; route to [`../deploy-test/SKILL.md`](../deploy-test/SKILL.md).
3. Read `manifest.yml` and the setup script using the env-specific snippet above.
4. Cross-reference findings against [`troubleshooting.md`](troubleshooting.md) and [`manifest-reference.md`](manifest-reference.md). Quote the matching rows; don't paraphrase. Don't invent new diagnostic rules — if it's not in those catalogs, surface the observation and stop.

## Introspecting a Consumer-Installed App

You can't `LIST` or `COPY FILES` from an installed `APPLICATION` — only from its source `APPLICATION PACKAGE`, which the consumer doesn't own. Introspect via SQL:

```sql
SHOW SCHEMAS IN APPLICATION <app_name>;
SHOW VIEWS IN APPLICATION <app_name>;
SHOW TABLES IN APPLICATION <app_name>;
SHOW USER PROCEDURES IN APPLICATION <app_name>;
SHOW USER FUNCTIONS IN APPLICATION <app_name>;
SHOW TASKS IN APPLICATION <app_name>;
SHOW STREAMLITS IN APPLICATION <app_name>;
```

For provider-side dev installs needing deeper visibility (query history, redaction-disabled view), load [`../debug-app/SKILL.md`](../debug-app/SKILL.md).
