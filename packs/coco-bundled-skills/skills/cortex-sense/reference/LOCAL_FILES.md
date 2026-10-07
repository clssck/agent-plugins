# Local files → stage

The build reads content **from Snowflake internal/named stages**, never from the builder's local filesystem. So when a builder points at a local path — a checked-out dbt repo's `target/manifest.json`, a metrics spec PDF, a SQL workbook — CoCo must get that file onto a stage first, then record the resulting stage FQN in the manifest. Never silently ignore a local path, and never record a `file://` path in the manifest.

## When this applies

Detect a local reference when the builder gives a path that isn't a stage FQN — e.g. it starts with `/`, `./`, `~/`, a drive letter, or names a local directory/repo, and does **not** start with `@`. Common cases:

- **dbt**: a local repo with `target/manifest.json` (e.g. `~/repos/analytics/target/manifest.json`). Detect `target/manifest.json` under a named local directory.
- **Business docs / query patterns**: a local `.pdf`, `.md`, `.sql`, `.csv`.

## Default stage — `<DB>.<SCHEMA>.SENSE_SOURCES`

Cortex Sense already has a home database and schema — the doctor's `database` / `schema` (default `TEMP.CORTEX_SENSE`), where the context-builder stage lives. By default, uploaded local files land there in a stage named **`SENSE_SOURCES`** (`<DB>.<SCHEMA>.SENSE_SOURCES`). Surface this up front (see setup §5) so the builder knows where their additional/local content will be stored, and let them point at a different stage if they prefer.

## Flow

1. **Explain once, plainly:**

   ```
   The build reads from Snowflake stages, not your local device. I'll upload <file> to
   @<DB>.<SCHEMA>.SENSE_SOURCES (the stage I keep for your Cortex Sense source files)
   and include it — or tell me a different stage to use.
   Proceed? (yes / use a different stage: <name>)
   ```

   **Wait for the builder's answer before running any `CREATE STAGE` or `PUT`.** These write persistent state to a Snowflake stage, so do not upload until the builder confirms (or names a stage). If they name a stage, use it; if they decline, don't upload.

2. **Resolve the target stage.** Default to `<DB>.<SCHEMA>.SENSE_SOURCES` (DB/SCHEMA from the doctor output). If the builder named a stage, use theirs instead. Create it if it doesn't exist (idempotent):

   ```bash
   # Runs in CoCo bash sandbox (Linux) — safe on any host OS
   uv run --project <SKILL_DIR>/.. snow sql -q "CREATE STAGE IF NOT EXISTS <DB>.<SCHEMA>.SENSE_SOURCES;"
   ```

3. **PUT the file** onto the stage:

   ```bash
   # Runs in CoCo bash sandbox (Linux) — safe on any host OS
   uv run --project <SKILL_DIR>/.. snow sql -q "PUT file://<absolute-local-path> @<DB>.<SCHEMA>.<STAGE> AUTO_COMPRESS=FALSE OVERWRITE=TRUE;"
   ```

   Use `AUTO_COMPRESS=FALSE` so the staged filename matches what the file rule references (compression appends `.gz`).

4. **Record the resulting stage FQN** as the right source (see `SCOPE_MANIFEST.md`):
   - **dbt** → `dbt_projects`, `file` rule with `stage: <DB>.<SCHEMA>.<STAGE>` and `path` pointing at `target/manifest.json` (the `path` **must** end in `manifest.json` — enforced by the validator).
   - **doc / SQL / CSV** → `stage_files`, `file` rule with a non-empty `file_pattern` naming the uploaded file.

5. **Echo** what landed: *"Uploaded `<file>` to `@<DB>.<SCHEMA>.<STAGE>` and added it to scope."*

## Guardrails

- Never write a `file://` or local path into the manifest — only the resulting stage FQN.
- If `PUT` fails (permissions, missing stage), surface a single plain-English line and offer the batched-ask fallback (builder names an existing stage path). Never silently drop the file.
- Keep the dbt `path` pointed at `manifest.json`; the full path up to and including the file name is required.

## Workspace-backed Streamlit apps → stage

Same principle as local files: **everything the build reads must live on a stage.** A Streamlit app authored in a **Snowflake Workspace** does *not* live on a stage — its source is at a `snow://workspace/...` URI the offline build can't reach (the build runs server-side). So a workspace app must be **copied out to a regular stage** the builder's role owns before it can be included. Best-effort and ask — never silently skip.

### How to tell a workspace app from a stage app

This branch is reached from the Streamlit content-path rule in `INSTRUCTIONS.md`. Run `DESCRIBE STREAMLIT <DB.SCHEMA.APP>` and look at which location column is populated:

- **`root_location` present** (`@DB.SCHEMA.STAGE`) → stage-backed → use the existing stage recipe in `INSTRUCTIONS.md`. Done.
- **`source_location` = `snow://workspace/...`** (and no usable `root_location`) → **workspace-backed** → run the copy flow below.

Facts to rely on (validated):

- A workspace app shows up in `SHOW STREAMLITS IN ACCOUNT` as a **preview object** with a system name (`ST<hash>`) in `USER$<user>.PUBLIC`, `owner_role_type = USER`, and a `comment`/`title` that references the workspace source path.
- On a `snow://workspace/...` URI, `LIST` and `GET` work, but reading files in place does **not** — `SELECT $1 FROM '<snow://workspace...>' (FILE_FORMAT=>…)` fails with `Domain 'WORKSPACE' is not supported by SnowURL in infer_schema`. You must **copy the files out**, not read them in place.
- `cortex ws ls '<coords>:/<path>/'` ≡ `LIST 'snow://workspace/…/versions/head/<path>/'`; `cortex ws cp '<coords>:/…/file' <local>/` ≡ `GET 'snow://workspace/…/file' 'file://<local>/'`. The friendly `cortex ws` form is quoting-safe — prefer it for the read side.

### Resolve the workspace coordinates + app folder

The examples below use these placeholders — substitute the resolved values, never the literals:

- **`<SOURCE_LOCATION>`** = the verbatim `snow://workspace/...` URI from `DESCRIBE STREAMLIT`.
- **`<WORKSPACE_COORD>`** = `USER$<user>.PUBLIC.DEFAULT$` — from `SHOW WORKSPACES;` (`database_name` = `USER$<user>`, `schema_name` = `PUBLIC`, `name` = `DEFAULT$`).
- **`<APP_FOLDER>`** = the last path segment of `source_location` (e.g. `.../versions/head/sales_app` → `sales_app`).
- **`<TARGET_STAGE>`** = the 3-part `DB.SCHEMA.STAGE` the builder chose for the copy.
- **`<main_file>`** = from `DESCRIBE STREAMLIT` (e.g. `streamlit_app.py`).

### Ask / confirm (mirror the local-files ask)

Do not copy silently. Tell the builder plainly and get a target stage:

```
<app> is a Workspace app — the build can't read Workspace files directly. I can copy
its source into a stage you own so it's included. Which stage should I use?
(default @<DB>.<SCHEMA>.SENSE_SOURCES, or name another, e.g. @<TARGET_STAGE>)
```

Validate the stage is a full 3-part `DB.SCHEMA.STAGE` and writable by the current role (reuse the `ACCESS_PREFLIGHT.md` check). Create it if the builder asks and has rights (idempotent `CREATE STAGE IF NOT EXISTS`).

> **Offer the simpler alternative once:** the builder can instead **deploy** the Workspace app, which gives it a `root_location` stage — after that the plain stage recipe applies and no copy is needed.

### Copy procedure — one server-side `COPY FILES` (validated)

A single **`COPY FILES`** copies the app straight from the workspace URI to a regular stage — server-side, with **no local download and no `cortex ws` dependency**. Use the `source_location` from `DESCRIBE STREAMLIT` verbatim as the `FROM` (append a trailing `/`), and the target stage plus the `<app>` subfolder as the `INTO`:

```sql
COPY FILES INTO @<TARGET_STAGE>/<APP_FOLDER>/
FROM '<SOURCE_LOCATION>/';
```

Run it via `snow sql -f <tempfile>` (not inline `-q`) so the workspace URI's embedded double-quotes and `$` aren't mangled by the shell — the same temp-`.sql` pattern used in `STORAGE.md`. Then `LIST @<TARGET_STAGE>/<APP_FOLDER>/` to verify.

Validated end-to-end: `COPY FILES` copies the whole app folder (`streamlit_app.py`, `pyproject.toml`, `snowflake.yml`, `.streamlit/config.toml`) and does **not** compress, so staged filenames match the `file` rule.

**Fallback (only if `COPY FILES` is unavailable) — client-side download + upload:**

1. **Enumerate** the app's files:

   ```bash
   # Runs in CoCo bash sandbox (Linux) — safe on any host OS
   cortex ws ls '<WORKSPACE_COORD>:/<APP_FOLDER>/' --connection <conn>
   ```

2. **Download** the app folder to a temp local dir (repeat per file `ls` reports — e.g. `pyproject.toml`, `.streamlit/config.toml` — preserving relative paths):

   ```bash
   # Runs in CoCo bash sandbox (Linux) — safe on any host OS
   TMP="$(mktemp -d)"; mkdir -p "$TMP/<APP_FOLDER>"
   cortex ws cp '<WORKSPACE_COORD>:/<APP_FOLDER>/<main_file>' "$TMP/<APP_FOLDER>/" --connection <conn>
   ```

3. **Upload** to the target regular stage:

   ```bash
   # Runs in CoCo bash sandbox (Linux) — safe on any host OS
   uv run --project <SKILL_DIR>/.. snow sql --connection <conn> -q \
     "PUT 'file://$TMP/<APP_FOLDER>/*' '@<TARGET_STAGE>/<APP_FOLDER>/' AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
   ```

   Use `AUTO_COMPRESS=FALSE` so staged filenames match what the file rule references.

4. **Verify**:

   ```bash
   # Runs in CoCo bash sandbox (Linux) — safe on any host OS
   uv run --project <SKILL_DIR>/.. snow sql --connection <conn> -q \
     "LIST '@<TARGET_STAGE>/<APP_FOLDER>/'"
   ```

> The `COPY FILES` path above is the **primary, validated** method (server-side, one statement). Use the client-side download + upload only if `COPY FILES` is unavailable in the account.

### Record it as a normal stage-backed source

The copied app is stored as an ordinary `streamlit_apps` `file` rule so the build treats it like any other stage app — with `provenance` recording where it came from. See `SCOPE_MANIFEST.md` "The `file` rule" and "Provenance":

```yaml
sources:
  - name: streamlit_apps
    type: snowflake_content
    enabled: true
    rules:
      - type: file
        stage: <TARGET_STAGE>                        # e.g. MY_DB.CORTEX_SENSE.STREAMLIT_SRC
        file_pattern: <APP_FOLDER>/                  # or <APP_FOLDER>/<main_file> for just the entrypoint
        user_prompt: "include the <APP_FOLDER> workspace app"
        provenance:
          state: approved
          origin: inferred-shown-to-user
          sources:
            - type: source_code
              ref: "<SOURCE_LOCATION>"
```

Enforce pattern hygiene: full 3-part stage FQN, no database-level wildcards (see `SCOPE_MANIFEST.md` "Pattern hygiene").

### Workspace copy guardrails

- The copy is a **point-in-time snapshot.** If the builder edits the app in the Workspace later, re-copy on the next `refresh` / `deeper` / refine. Say so once.
- `LIST` / `GET` / `PUT` all run with the **current role** — same access rules as the preflight.
- **Never silently drop** a workspace app — copy it, ask for a stage, or offer the deploy alternative.
