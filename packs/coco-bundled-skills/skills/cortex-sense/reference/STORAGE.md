# Storage

Single home for everything Cortex Sense persistence — how manifests are written and read, how a use case is registered, and what `doctor` reports.

This doc is **agent-facing**. All SQL patterns below are run directly by CoCo via `snow sql`; there is no Python wrapper for the storage calls themselves. `scripts/persist_state.py` handles only YAML validation, formatting, dedup, and doctor pre-flight.

## Persistence

```
SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER
  create-context    → registers the use case
  put-stage-file    → writes scope.yaml to internal stage (plain YAML, JSON-escaped)
  get-stage-file    → reads scope.yaml back
```

If storage is unavailable, surface a plain-English error and stop.

---

## SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER

### Action set

| Action | Status | Purpose |
|---|---|---|
| `help` | available | List actions and schemas |
| `create-context` | available | Register a use case |
| `list-contexts` | available | List all contexts in account |
| `get-context` | available | Get one context by name |
| `put-stage-file` | available | Write a file (e.g. `scope.yaml`) to the internal stage |
| `get-stage-file` | available | Read a file back from the internal stage |
| `list-files` | not yet available | List files in the internal stage |
| `delete-context` | available | Delete a context and its associated files; returns `{"deleted": true, "id": "...", "name": "...", "schema_name": "...", "database_name": "..."}` |
| `force-reprocess` | available | Reset a context's `last_processed_at` to the epoch, triggering a reprocess on the next refreshd poll tick (on-demand build trigger) |
| `record-feedback` | available | Append one correction to `feedback.json`. Durable and readable back; **nothing consumes it yet**. Separate from the manifest — see `FEEDBACK_RECORD.md` |
| `list-feedback` | available | Per-record summary of a context's feedback. Not used by this skill — `get-stage-file` on `feedback.json` is the read this family already uses everywhere else (`FEEDBACK_RECORD.md` "Reading it back") |
| `update-feedback` | available | Edit a recorded feedback record. Not used by this skill; rejects any change to `absorbable` or its gating fields (`FEEDBACK_RECORD.md`) |

> **`deployment` field.** Do **not** include `deployment` (or `account_url`) in any `SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER` call — they are server-resolved and will be deprecated. Omit them from all payloads: `create-context`, `put-stage-file`, `get-stage-file`, `list-contexts`, etc. The same applies to `SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT` (context lookup) — it also resolves account/deployment server-side, so omit both there too (see `CONTEXT_LOOKUP.md`).

### Pre-flight: ensure the target schema exists

Before the first `create-context` call in a session, ensure `<DB>.<SCHEMA>` exists. This is idempotent — safe to run every session:

```bash
uv run --project <SKILL_DIR>/.. snow sql -q "
  CREATE DATABASE IF NOT EXISTS <DB>;
  CREATE SCHEMA IF NOT EXISTS <DB>.<SCHEMA>;
"
```

`<DB>` and `<SCHEMA>` come from the doctor output's `database` / `schema` fields (defaults: `TEMP` / `CORTEX_SENSE`). If either `CREATE` fails with a permission error, fall through to the doctor's `needs_database_schema` recovery path — ask the builder for an alternate location, set `CORTEX_SENSE_DB` / `CORTEX_SENSE_SCHEMA`, and re-run doctor.

---

### Saving — two calls in sequence

**Call 1: Register the use case** (create-context)

```bash
# Runs in CoCo bash sandbox (Linux) — safe on any host OS
uv run --project <SKILL_DIR>/.. snow sql --format json -q "
  SELECT TRY_PARSE_JSON(
    SYSTEM\$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER(
      '{\"action\":\"create-context\",\"parameters\":{\"name\":\"<domain>\",\"database_name\":\"<DB>\",\"schema_name\":\"<SCHEMA>\"}}'
    )
  ) AS result;
"
```

> **Note on the `parameters` wrapper.** Fields go inside a nested `parameters` object — a flat payload (no `parameters` key) causes `INVALID_ARGUMENT: missing required parameter(s)`.

`<domain>` is the use case name. `<DB>` and `<SCHEMA>` come from the doctor output's `database` / `schema` fields (same values used in the pre-flight `CREATE` above).

`create-context` field table:

| Field | Value |
|---|---|
| `name` | the use case's `domain` (== `business_domain`) verbatim |
| `database_name` / `schema_name` | from doctor `database` / `schema` fields (default: `TEMP` / `CORTEX_SENSE`) |
| `target_lag_seconds` | omit — server applies its own default |

**Reading the response** (create-context):

`TRY_PARSE_JSON` returns either a JSON object or `NULL`. Parse `[{"RESULT": ...}]`:

- **`response_structured.cortex_context` is present and there's no `error`** → registration succeeded. Continue silently.
- **`error.message` matches "already exists" / "duplicate"** (case-insensitive) → another save into the same domain landed first. Treat as success; continue silently.
- **`INVALID_ARGUMENT` — missing parameters** → the payload is missing the `parameters` wrapper; fix the call and retry once.
- **`NotFound`** → the schema likely does not exist. Run `CREATE DATABASE IF NOT EXISTS <DB>; CREATE SCHEMA IF NOT EXISTS <DB>.<SCHEMA>;` and retry `create-context` once. If it still fails, surface the error and stop.
- **Transient error** — `error.type` / `error.message` matches `INTERNAL`, `CreateCortexContext failed`, `timeout`, or `unavailable` (case-insensitive) → **retry once silently** (no builder-facing narration). If the retry also fails, treat as "Any other error" below.
- **Any other `error`** (e.g. permission denied) → render the one-line warning (see below) and stop. Do **not** silently swallow the error.
- **`RESULT` is `null`** → treat like "Any other error".
- **`snow sql` non-zero, stderr matches "already exists"** → treat as success.
- **`snow sql` non-zero, other** → render the one-line warning and stop.

Warning copy: *"(Cortex Sense couldn't save your scope — `<message>`. Fix the issue above and try again.)"*

> **The argument must be a constant string literal.** `SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER` rejects non-constant arguments (`OBJECT_CONSTRUCT(...)::STRING` fails with "argument 0 needs to be constant"). This is safe because `domain` is `[A-Za-z0-9_-]` and database/schema match `[A-Za-z_][A-Za-z0-9_]*` — neither can contain a quote.

---

**Call 2: Write the manifest file** (put-stage-file)

After `create-context` succeeds (or returns "already exists"), write the manifest YAML to the internal stage.

**Encoding:** JSON-encode the YAML string directly — do **not** base64-encode it. The `content` field value is the raw YAML string with JSON-standard escaping (`"` → `\"`, newline → `\n`, backslash → `\\`, tab → `\t`).

**Quoting:** Use **dollar quoting** (`$$...$$`) for the SQL string literal — **not** single quotes. Manifest YAML routinely contains single quotes (YAML timestamp strings, user-authored text) and backslash sequences (JSON `\n` newlines). Single-quote literals require `''` doubling and `\\` escaping that corrupts the JSON payload the function receives. Dollar quoting passes the JSON verbatim with no SQL-layer escaping.

**Recommended approach:** Build the full JSON payload in Python/script, write it to a temp `.sql` file with `$$` quoting, then execute via `snow sql -f`:

```python
# Runs in CoCo bash sandbox (Linux) — safe on any host OS
import json, tempfile, os

# `manifest_yaml` is the merged YAML string from persist_state.py
payload = json.dumps({
    "action": "put-stage-file",
    "parameters": {
        "name": "<domain>",
        "database_name": "<DB>",
        "schema_name": "<SCHEMA>",
        "path": "scope.yaml",
        "content": manifest_yaml,
        "overwrite": True
    }
})

sql = f"SELECT SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER($${payload}$$) AS result"

fd, sql_path = tempfile.mkstemp(suffix=".sql")
with os.fdopen(fd, "w") as f:
    f.write(sql)
```

```bash
# Runs in CoCo bash sandbox (Linux) — safe on any host OS
uv run --project <SKILL_DIR>/.. snow sql --format json -f "$SQL_PATH" -c <connection>
```

Alternatively, inline with `-q` (for short manifests):

```bash
uv run --project <SKILL_DIR>/.. snow sql --format json -q "
  SELECT SYSTEM\$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER(
    \$\$<JSON payload with content field>\$\$
  ) AS result;
"
```

> **Why not single quotes?** The YAML `content` field contains timestamps like `'2026-07-10T05:43:09Z'` and user text with apostrophes. Inside a SQL `'...'` literal these require `''` doubling — but the function parses the *received* string as JSON, and `''` is not valid JSON. Dollar quoting avoids the mismatch entirely.

`<DB>` and `<SCHEMA>` are the same values used in `create-context`. On a **transient** failure (`INTERNAL`, `CreateCortexContext failed`, `timeout`, or `unavailable`), **retry once silently** before surfacing anything. On any other failure — or if the retry also fails — render the one-line warning and stop; do not silently continue without saving.

### Versioned scope snapshot

Immediately after `put-stage-file path: scope.yaml` succeeds, write a second copy at the versioned path. Use the same payload construction pattern as Call 2, substituting `"path": "scope_<version_id>.yaml"` and `"overwrite": false`:

- **Path**: `scope_<version_id>.yaml` where `<version_id>` is the `version_id` field from the manifest YAML that was just saved (e.g. `scope_v-20260610-200000-abc123.yaml`).
- **Content**: identical to what was written as `scope.yaml`.
- **`overwrite`: false** — snapshot files are immutable. If the response indicates the file already exists, treat as success (a prior retry already wrote it) and continue silently.

Snapshot files accumulate in the stage and are never deleted by this skill. They allow eval runs to be linked to the exact scope that was active at run time via `scope_version_id` — see `reference/EVAL_FORMAT.md` "Results schema (`eval_results.yaml`)" for that field.

### Loading — one call

Extract the `content` field from the response. New files contain plain YAML; legacy files written before this change are base64-encoded. The loading SQL handles both:

```bash
uv run --project <SKILL_DIR>/.. snow sql --format json -q "
  WITH raw AS (
    SELECT TRY_PARSE_JSON(
      SYSTEM\$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER(
        '{\"action\":\"get-stage-file\",\"parameters\":{\"name\":\"<domain>\",
          \"database_name\":\"<DB>\",\"schema_name\":\"<SCHEMA>\",
          \"path\":\"scope.yaml\"}}'
      )
    ):response_structured:content::STRING AS content_str
  )
  SELECT
    CASE
      WHEN content_str REGEXP '^[A-Za-z0-9+/\\n]+=*$'
        THEN BASE64_DECODE_STRING(content_str)
      ELSE content_str
    END AS scope_yaml
  FROM raw;
"
```

`<DB>` and `<SCHEMA>` are the same values used in `create-context` / `put-stage-file`.

**Reading the response** (get-stage-file):

- **`scope_yaml` is a non-null string** → parse as YAML and use as the manifest. Continue.
- **`scope_yaml` is `null`** → file not found or not yet written. Surface a plain-English message and stop.
- **`snow sql` non-zero or `TRY_PARSE_JSON` returns `null`** → treat as "file not found" and surface the error.

### Listing contexts

```bash
uv run --project <SKILL_DIR>/.. snow sql --format json -q "
  SELECT SYSTEM\$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER(
    '{\"action\":\"list-contexts\"}'
  ) AS result;
"
```

Use this to audit which contexts exist in the account. For `NotFound` errors on `create-context`, run the pre-flight `CREATE DATABASE / CREATE SCHEMA` step instead of searching for an alternate schema here.

### Deleting a context

**⚠️ MANDATORY CHECKPOINT**: Deleting a context and its internal stage is irreversible. Before executing `delete-context`, confirm with the builder using explicit language:

> Are you sure you want to permanently delete the `<domain>` context and all its stored data? This cannot be undone.

Only proceed if the builder explicitly confirms (e.g. "yes", "delete it", "go ahead"). If they hesitate or ask what it means, explain and wait. Do not run the SQL below without affirmative approval.

```bash
uv run --project <SKILL_DIR>/.. snow sql --format json -q "
  SELECT SYSTEM\$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER(
    '{\"action\":\"delete-context\",\"parameters\":{\"name\":\"<domain>\",
      \"database_name\":\"<DB>\",\"schema_name\":\"<SCHEMA>\"}}'
  ) AS result;
"
```

`<domain>`, `<DB>`, and `<SCHEMA>` are the same values used in `create-context`.

**Reading the response** (delete-context):

- **`response_structured.deleted` is `true`** → deletion succeeded. Echo: *"Domain `<domain>` deleted."*
- **`response_structured.deleted` is `false`** → surface to the builder as a failed delete and stop. Do not treat as success.
- **`error.message` matches "not found" / "does not exist"** (case-insensitive) → the context was already absent. Treat as success; continue silently.
- **Any other `error`** → surface the error message to the builder and stop. Do not silently ignore a failed delete.
- **`RESULT` is `null`** → treat like "Any other error".

---

### Force-reprocessing a context

Call immediately after every successful save (`put-stage-file scope.yaml` + versioned snapshot) to reset the context's `last_processed_at` to the epoch. This makes the context immediately due for reprocessing on the next refreshd poll tick, triggering an on-demand build rather than waiting for the normal refresh cycle.

```bash
uv run --project <SKILL_DIR>/.. snow sql --format json -q "
  SELECT TRY_PARSE_JSON(
    SYSTEM\$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER(
      '{\"action\":\"force-reprocess\",\"parameters\":{\"name\":\"<domain>\",
        \"database_name\":\"<DB>\",\"schema_name\":\"<SCHEMA>\"}}'
    )
  ) AS result;
"
```

`<domain>`, `<DB>`, and `<SCHEMA>` are the same values used in `create-context`.

**Reading the response** (force-reprocess):

- **`response_structured.force_reprocess_queued` is `true`** → reprocess queued. Continue silently.
- **`error.message` matches "not found" / "does not exist"** (case-insensitive) → the context registration hasn't propagated yet. Log internally; continue — the manifest is already saved.
- **Any other `error`** or **`RESULT` is `null`** → **non-blocking**: log the error internally but do not surface it to the builder and do not stop. The manifest is already persisted; the build will be picked up on the next normal refresh cycle.

> **Non-blocking by design.** `force-reprocess` is a best-effort acceleration — the save is already durable. A `force-reprocess` failure must never prevent the confirm block from rendering.

> **Do not translate internal cadence to the builder.** "refreshd poll tick" and "refresh cycle" are internal mechanics — never tell the builder the build runs "every hour" or on any fixed schedule, and never quote a specific ETA. Builder-facing timing stays vague ("a few hours" / "minutes or hours depending on scope").

---

### Setting the COMMENT (description)

The full contract — generation rules, confirm block, SQL pattern, drift tracking via `description_synced_version`, and no-read-back implications — lives in `reference/DESCRIPTION.md`. Consult it for all description-related work; notes here cover what is specific to this file's surface.

**Timing:** the description is confirmed *before* the save (see `DESCRIPTION.md` "When this runs"), so `description_synced_version` rides in the single `put-stage-file` call. `ALTER CORTEX SENSE` runs after `force-reprocess`, non-blocking.

**DDL, not `_BUILDER`.** `ALTER CORTEX SENSE` is plain Snowflake DDL — it is not routed through `SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER`, so the constant-literal restriction on `_BUILDER` calls does not apply. However, DDL resolves unquoted identifiers to uppercase, so the domain name **must** be double-quoted; build the SQL in Python and write it to a temp file (`snow sql -f`). See `DESCRIPTION.md` "Identifier quoting" and "Applying it" for the exact pattern.

**Privilege required.** `ALTER CORTEX SENSE … SET COMMENT` requires `MODIFY` or `OWNERSHIP` on the context object — a different grant from everything else in this file, which goes through `_BUILDER`. For the exact error-matching criteria and advisory copy, see `DESCRIPTION.md` "Response handling".

---

### Recording feedback

Appends one correction to `feedback.json` in the context's stage. The record contract — every field, how to derive it, and the caps this call does not enforce — is `FEEDBACK_RECORD.md`. Validate with `feedback_record.py draft` before building the payload.

**Quoting:** use **dollar quoting** (`$$...$$`) for the same reason as `put-stage-file` — see that section. The argument must also be a constant literal, so a bind parameter is not an option.

`draft` rejects `$$` in any free-text field before you get here. Dollar quoting has no escape sequence, so there is nothing to escape to.

```python
# Runs in CoCo bash sandbox (Linux) — safe on any host OS
import json, tempfile, os

# `record` is the `record` object from `feedback_record.py draft`
payload = json.dumps({"action": "record-feedback", "parameters": record}, sort_keys=True)

sql = f"SELECT SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER($${payload}$$) AS result"

fd, sql_path = tempfile.mkstemp(suffix=".sql")
with os.fdopen(fd, "w") as f:
    f.write(sql)
```

```bash
# Runs in CoCo bash sandbox (Linux) — safe on any host OS
uv run --project <SKILL_DIR>/.. snow sql --format json -f "$SQL_PATH" [-c <connection>]
```

`sort_keys=True` keeps the emitted bytes stable for a given record, so re-drafting the same record produces the same statement and a test can assert on it. It is **not** there to make a retry safe — a retry is never safe here, because each attempt mints a new `feedback_id` and creates a second correction rather than repairing the first (see `Unknown`, below).

No `TRY_PARSE_JSON` here. The response is five flat keys, two of them a bool and an int — exactly what `TRY_PARSE_JSON` returns in scientific-notation float form — and it yields `NULL` on input it cannot parse, which would turn a server error into an empty result. Read the keys out of the returned string instead.

**Response:** `feedback_id`, `lifecycle_state`, `envelope_version`, `indexed_text`, `indexed` — five keys, all internal; none reaches the builder. What each one means is in `FEEDBACK_RECORD.md` "### Response".

**Errors:** arrives as a failed SQL statement, not an error field in the envelope, per `FEEDBACK_RECORD.md` "## Errors" — read the failure text, not `response_structured`. Covers `InvalidArgument`, `NotFound`, `Unauthenticated`, `ResourceExhausted`, `DataLoss`, `FailedPrecondition`, `Unknown`, `Internal`, and a `snow sql` failure with no status code (treat as `Unknown`); what each means and what to say is there too.

> **Blocking.** Unlike `force-reprocess`, this call is the whole point of the flow. If it fails, say so — never report a correction as recorded on an ambiguous outcome.

Read `feedback.json` back with `get-stage-file` (see **Loading — one call**, substituting the path). A `NOT_FOUND` there means either no correction has been recorded yet or the context does not exist; disambiguate with `get-context` before telling the builder anything.

---

## Doctor pre-flight

Every sub-skill (`setup`, `refine`, `test`) runs `doctor` once before any other `persist_state.py` call:

```bash
uv run --project <SKILL_DIR>/.. python <SKILL_DIR>/../scripts/persist_state.py doctor
```

`doctor` always exits 0 and never raises — it prints a JSON report. Three branches the skill must handle:

| Field | Skill behavior |
|---|---|
| `snow_cli == "missing"` | Render the install line (link to <https://docs.snowflake.com/developer-guide/snowflake-cli/installation/installation>) and stop the flow. No retry. |
| `needs_database_schema: true` | Ask **once**, in plain English, for a database and schema the builder can write to. **Validate the `<DB>.<SCHEMA>` shape; if it's wrong, ask once more with a corrected example, and after two failures stop and tell the builder plainly.** Set them as `CORTEX_SENSE_DB` / `CORTEX_SENSE_SCHEMA` env vars for the rest of the session, **then re-run `doctor`** so the new location is provisioned. **Never** mention the env-var names to the builder. |
| Otherwise (`storage_ready: true`) | Continue silently. |

### Doctor JSON shape

| Key | Type | Notes |
|---|---|---|
| `snow_cli` | `"ok"` \| `"missing"` | `which("snow")` result |
| `database` / `schema` | string | resolved values |
| `database_source` / `schema_source` | `"env"` \| `"default"` | how each was resolved |
| `storage_location` | string \| null | context-builder context path once provisioned |
| `storage_ready` | bool | true after provisioning succeeds |
| `needs_database_schema` | bool | reserved — not emitted by current `cortex_context_builder` backend; present only in `"local"` backend when provisioning fails |
| `error` | string | reserved — only present alongside `needs_database_schema: true` in the `"local"` backend |
| `lookup_sql_available` | bool | true whenever the Snowflake connection works (`snow_cli == "ok"`); the `SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT` SQL fallback resolves account/deployment server-side and needs no env vars |
| `storage_backend` | `"cortex_context_builder"` (or `"local"` when `CORTEX_SENSE_LOCAL_ROOT` is set for testing) | identifies the storage mechanism |

## Schema ownership and permissions

Cortex Sense stores each domain's manifest (`scope.yaml`) and source files in a **stage** inside a schema (e.g. `TEMP.CORTEX_SENSE`). Different domains can live in different schemas if the builder chooses.

**Schema creation:** If the schema does not yet exist, Cortex Sense creates it automatically during setup (see "Pre-flight: ensure the target schema exists" above). The schema is owned by the role that was active when it was created — which is also the role that becomes the build role for contexts in that schema.

**Key caveat:** Only the owning role (and roles it has been granted to) can read the objects inside the schema. This is the most common source of permission errors when a different role or teammate tries to resume a Cortex Sense session.

**Granting access to another role:**
```sql
GRANT USAGE ON DATABASE <DB> TO ROLE <OTHER_ROLE>;
GRANT USAGE ON SCHEMA <DB>.<SCHEMA> TO ROLE <OTHER_ROLE>;
GRANT READ ON STAGE <DB>.<SCHEMA>.SENSE_SOURCES TO ROLE <OTHER_ROLE>;
```

Do **not** recommend dropping or modifying objects inside the schema manually — that can corrupt the manifest or the internal stage.

When surfacing permission errors to the builder, use plain English: name the schema and the owning role, and suggest the grant commands above.

## Resolution order (database + schema for create-context)

1. `CORTEX_SENSE_DB` / `CORTEX_SENSE_SCHEMA` env vars — explicit override.
2. Built-in default `TEMP.CORTEX_SENSE` — used whenever env vars are not set.

`CURRENT_DATABASE()` / `CURRENT_SCHEMA()` is **not** used as a fallback. Personal session schemas are not appropriate storage locations.

## Backend abstraction (persist_state.py)

`scripts/persist_state.py` scope: YAML validation, formatting, in-process instruction dedup, doctor pre-flight, and `LocalFileBackend` for tests.

| Backend | When used | Notes |
|---|---|---|
| `LocalFileBackend` | `CORTEX_SENSE_LOCAL_ROOT` is set | Tests only; never surfaced to builders. |

## Backfill

Existing manifests get re-saved on the next builder edit. No bulk backfill needed.

## Pointers

- `scripts/persist_state.py` — validation, formatting, dedup, doctor.
- `reference/SCOPE_MANIFEST.md` — manifest schema (what's *inside* the YAML files).
- `reference/NOT_YET_IMPLEMENTED.md` — remaining work: `list-files`, native use-case object.
- `reference/CONTEXT_LOOKUP.md` — context lookup contract (`SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT`).
