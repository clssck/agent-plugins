---
name: openflow-observability-action-guidelines
description: Openflow SQL Action Mode trust boundaries, support detection, allowlist, denylist, confirmation protocol, and verification. Tier 2 only; load when an allowlisted Openflow SQL action candidate exists.
---

# Openflow SQL Action Mode: Guidelines

> Customer-facing name for this mode: **Openflow SQL Action Mode** (or just "Openflow SQL actions"). Use "SQL-managed runtime" when describing a runtime that supports these actions.
> - Never expose internal gate numbering (`Gate 1`, `Gate 2`, ..., `Gate 5`, "gate failed", "intent gate", "support gate", etc.) to the customer. The five-gate structure is internal scaffolding. Customer-facing refusal text MUST describe the cause in product terms (e.g., "this runtime is not visible to Openflow SQL commands" instead of "Gate 2 failed", "the proposed action is outside the supported set" instead of "denylist gate failed").

This file governs every Openflow object mutation and non-scratch mutating SQL the skill runs against the customer's account. It is loaded only when the Openflow SQL Action Mode is entered (see [Openflow SQL Action Mode in SKILL.md](../../SKILL.md#openflow-sql-action-mode)). If this file is not loaded, no Openflow-object `ALTER` / `CREATE` / `DROP` / `GRANT` SQL may be executed. Session-scoped diagnostic scratch SQL is documented separately in [connector-diagnostics.md](connector-diagnostics.md#connector-config-snapshot-read-only).

## Scope

- Openflow SQL action support detection (account, deployment, runtime, connector)
- Trust boundary and confirmation protocol
- Action allowlist (MVP)
- Action denylist (MVP)
- ID resolution and namespace mapping
- Verification after execution

---

## Hard Gates Recap

Every Openflow object mutation and every non-scratch mutating call MUST pass all five gates from [SKILL.md](../../SKILL.md#openflow-sql-action-mode) in order. The only exception is the limited [Scratch-Stage Preflight Exception](#scratch-stage-preflight-exception), which can prepare and validate connector config content before the final Openflow mutation is previewed.

1. **Intent gate** -- explicit user request or explicit acceptance of a proposed action.
2. **SQL action support gate** -- proven by live `SHOW`/`DESCRIBE` (see [Openflow SQL Action Support Detection](#openflow-sql-action-support-detection)). For connector-targeted actions, this includes the [Connector-Definition Support Gate](#connector-definition-support-gate-sub-check-of-hard-gate-2): a no-SQL pre-gate matching `connector_type` (e.g. `postgresql`) against the matrix `connector_type alias` column, followed by exactly 1 SQL whose returned `CONNECTOR_DEFINITION` (e.g. `OPENFLOW_POSTGRES_CDC`) must match the matrix `Connector definition` column for the same row. Today the `postgresql` -> `OPENFLOW_POSTGRES_CDC` row is `GA` and the `mysql` -> `OPENFLOW_MYSQL_CDC` row is `PrPr`; both enter the action lane.
3. **Action allowlist gate** -- the proposed SQL is in the [Action Allowlist (MVP)](#action-allowlist-mvp) and not in the [Action Denylist (MVP)](#action-denylist-mvp).
4. **Confirmation gate** -- the final Openflow-object SQL, target FQN, current state, expected impact, and verification query were shown, and the user replied with explicit approval that matches the [Confirmation Matching Rule](#confirmation-matching-rule). Anything not matching fails closed; do not interpret synonyms or qualified replies.
5. **List-property preservation gate** (only when the action mutates a list-valued property; today only `runtime.attach_eai`).
   - The Confirmation Preview MUST include `Current X list:` populated from a fresh `DESCRIBE` run within the same response, AND a `Proposed X list:` line, AND a `Removed: [...]` line (empty list `[]` is acceptable when nothing is being removed).
   - If `Removed` is non-empty AND the customer's request did not enumerate removals, **fail closed**. Do not silently drop list entries.
   - Without all three lines populated from live SQL, the preview is invalid -- refuse to execute even on a "yes".

If a gate fails, fall back to read-only guidance and stop. Do not retry without re-running the gate that failed.

---

## Scratch-Stage Preflight Exception

`connector.config_set_property`, `connector.config_set_asset`, and the diagnostic config snapshot need SQL that writes scratch files or scratch objects before the final Openflow mutation is previewed. These statements do not mutate an Openflow object, but they still write to the customer's account, so they are allowed only under this narrow exception.

Allowed scratch preflight writes:

- `CREATE STAGE IF NOT EXISTS {db}.{schema}.OPENFLOW_CONFIG_WORK_{session_suffix}` for the per-session config-edit working stage.
- `CREATE TEMPORARY STAGE OPENFLOW_CONFIG_INSPECT` for the diagnostic config snapshot.
- `CREATE FILE FORMAT IF NOT EXISTS {db}.{schema}.JSON_FF_RAW` for config-edit staging, or `CREATE TEMPORARY FILE FORMAT JSON_FF_RAW` for diagnostic snapshots.
- `REMOVE @{db}.{schema}.OPENFLOW_CONFIG_WORK_{session_suffix}` to clear the per-session working stage.
- `COPY FILES INTO @{working_stage}` from a connector version stage, and from a customer-named stage only for the single validated driver JAR.
- `COPY INTO @{working_stage}/config.json FROM (SELECT REGEXP_REPLACE(...))` after the uniqueness and secret-leak gates pass.
- `DROP STAGE IF EXISTS {db}.{schema}.OPENFLOW_CONFIG_WORK_{session_suffix}` as best-effort cleanup after successful verification.

Constraints:

- The connector-definition support gate and live SQL-managed support check MUST pass before any scratch write. Unsupported or legacy connectors get 0 scratch writes.
- Scratch stages use a fresh per-session suffix and are never reused across sessions.
- Customer-named stages are read-only inputs. The agent may `LIST` and `COPY FILES FROM` them, but must never `REMOVE`, `PUT`, `COPY INTO`, or `DROP` them.
- Scratch writes do not satisfy the confirmation gate. The final `ALTER OPENFLOW CONNECTOR ... ADD VERSION FROM '@working_stage'` still requires the full preview and an exact confirmation reply.
- If any scratch step fails, stop. Do not promote, retry with a different target, or clean up by dropping customer-owned stages.

---

<a id="openflow-sql-action-support-detection"></a>
## Openflow SQL Action Support Detection

> Customer-facing name: "checking whether the runtime is SQL-managed". Do not surface the section heading verbatim.

Page-context fields like `isSom`, `objectModel`, or `runtime.kind` are **hints only**. They cannot authorize mutation because the dashboard snapshot can be stale and some accounts have these SQL features disabled while objects remain visible. Always confirm with live SQL before any mutation.

Hints may still *route* work, in the fail-closed direction only:

- `isSom = 'false'` -> treat the connector/runtime as gen1/legacy. Gen1 objects are not SQL-managed, so skip SOM-only work and stay read-only; route any requested change to the Openflow UI. (Narrows scope; never grants an action.)
- `isSom = 'true'` -> the object is a SOM *candidate*. This is the entry condition for considering an action, not proof of one. Every downstream live check (`SHOW OPENFLOW DEPLOYMENTS`, `DESCRIBE OPENFLOW DEPLOYMENT`, `SHOW OPENFLOW RUNTIMES` / `DESCRIBE OPENFLOW RUNTIME`, and the connector live check) still runs and still has to pass.
- `isSom` absent -> **no SOM routing signal** (page context unavailable, e.g. CLI usage, or an older host). Do **not** assume gen1/read-only. Fall through to the normal flow and let the live SQL gates determine SQL-managed status, exactly as when there is no page context -- the action lane stays available and is decided by the live checks.

The rule is asymmetric on purpose: a hint may only ever *withhold* the action lane (`isSom='false'` -> read-only) or *act as the entry condition for* the live checks (`isSom='true'` -> proceed to the live checks, which still decide the outcome). A hint never substitutes for the live positive gate.

### Session feature-flag pre-filter (no SQL, negative only)

If page context carried `openflowSqlActionsEnabled` and its value is `'false'`, the host has already determined that mutating Openflow SQL actions are unavailable in this account/session. **Fail closed immediately:** stay in read-only diagnostic mode, run **zero Openflow SQL of any kind** -- no support-detection `SHOW`/`DESCRIBE`, and no `SYSTEM$OPENFLOW_*` id-resolution helpers -- and route the customer to the Openflow UI (or customer-run SQL) for the requested change. Use product-terms refusal wording, e.g. "Openflow SQL actions aren't enabled for this session, so I can't run that change directly -- here's how to do it in the Openflow UI."

This is a cheap negative filter that saves the account/deployment/runtime round-trips below when the answer is already known to be "no". It is **not** the positive gate, and it is directional:

- `openflowSqlActionsEnabled = 'false'` (present-and-false) -> fail closed here, before the account-level live SQL below.
- `openflowSqlActionsEnabled = 'true'` -> **not** authorization. Fall through to the live account/deployment/runtime checks below unchanged; they remain the sole positive gate.
- Field absent -> fall through unchanged (older host, or the skill flag is off). Absence is never treated as `'false'`.

A stale `'false'` can only ever cause an over-conservative refusal (routing the customer to the UI), which is the safe direction. A stale or spoofed `'true'` grants nothing, because the live checks below still have to pass.

### Account-level support

Run once per session before the first Openflow SQL action.

```sql
SHOW OPENFLOW DEPLOYMENTS;
```

- Zero rows AND the user has `MONITOR`/`USAGE` on at least one deployment -> **fail closed**: account does not surface SQL-managed deployments to this role. Fall back to UI guidance.
- The query errors with "unsupported" / "feature disabled" / "syntax error near OPENFLOW" -> Openflow SQL commands are not enabled in this account. Fall back to UI guidance and explain that Openflow SQL actions are not available.
- Returns rows -> Openflow SQL commands are enabled at the account level for at least one deployment. Continue to deployment-level checks.

### Deployment-level support

When the action is scoped to a specific deployment, or when the runtime preflight needs to confirm the parent deployment.

```sql
DESCRIBE OPENFLOW DEPLOYMENT "{deployment_name}";
```

- Returns one row with `STATUS = 'ACTIVE'` -> proceed.
- `STATUS` is one of `CREATING`, `CREATE_FAILED`, `INACTIVE`, `NOT_REPORTING`, `NOT_HEALTHY`, `DELETING`, `DELETE_FAILED`, `DELETED`, `DEACTIVATION_REQUIRED`, `UPGRADING`, `UPGRADE_FAILED` -> **fail closed**. Tell the customer the deployment is not in an actionable state and link them to the deployment status in the Openflow UI.
- Errors with `does not exist or not authorized` -> the user does not have privileges or the deployment is legacy-only. Fall back to UI guidance.

**Deployment-level metadata actions (`deployment.set_display_name`, `deployment.set_comment`)** require the parent deployment in `STATUS = 'ACTIVE'` AND the customer's role to hold `OWNERSHIP` on the deployment (per the Openflow privilege model -- `SET` is an `OWNERSHIP`-gated operation). If the role lacks `OWNERSHIP`, fail closed and direct the customer to the deployment owner; do not silently fall back to runtime metadata.

### Runtime-level support

Required for every runtime/EAI action. Use the fully qualified runtime name (`<db>.<schema>.<runtime>`).

```sql
SHOW OPENFLOW RUNTIMES LIKE '{runtime_name}';
```

- Clean zero rows (query ran, no match) -> **fail closed**: runtime is not SQL-managed or not visible to this role. The runtime may exist as a legacy entity. Direct the customer to the Openflow UI.
- Multiple rows -> **stop and ask**. Quote the matching `NAME`, `DEPLOYMENT`, `DATABASE_NAME`, `SCHEMA_NAME` for each row and ask the customer to specify the FQN.
- Exactly one row -> capture the runtime FQN, then run the `DESCRIBE` below.
- **Errors** (`unsupported` / `syntax error near OPENFLOW` / `feature ... disabled` / `does not exist or not authorized`) are not a clean zero-row result -- they signal the account may not be Openflow-SQL-enabled. Do not fail closed on the `SHOW` alone: build the best-known FQN from the inputs and still run the `DESCRIBE` below so the customer sees the verbatim result of the actual read.

`DESCRIBE OPENFLOW RUNTIME` is the canonical runtime read and is **mandatory for every runtime / EAI action** -- always execute it, never skip or substitute it with `SHOW`. It is the only query that returns the live `EXTERNAL_ACCESS_INTEGRATIONS` list. Run it even when the `SHOW` above errored or you expect the account to reject Openflow SQL; surface any error verbatim, then proceed to the Confirmation Preview.

```sql
DESCRIBE OPENFLOW RUNTIME {runtime_fqn};
```

State machine for action eligibility:


| Action                                                        | Required STATUS       | Notes                                                          |
| ------------------------------------------------------------- | --------------------- | -------------------------------------------------------------- |
| Attach EAI (`ALTER ... SET EXTERNAL_ACCESS_INTEGRATIONS`)     | `ACTIVE`, `SUSPENDED` | The Openflow SQL action surface only blocks `ALTER` in `CREATING`, `CREATE_FAILED`, `DELETING`, `DELETED`. The narrower `ACTIVE` / `SUSPENDED` window is agent-level conservatism so the `ALTER` lands on a steady-state runtime, not mid-transition. |
| Restart (`ALTER ... RESTART`)                                 | `ACTIVE`              | Refuse if `RESTARTING`, `UPGRADING`, `SUSPENDING`, `DELETING`. |
| Resume (`ALTER ... RESUME`)                                   | `SUSPENDED`           | Refuse if any other state.                                     |
| Suspend (`ALTER ... SUSPEND`)                                 | `ACTIVE`              | Refuse if any other state.                                     |
| Update display name (`ALTER ... SET DISPLAY_NAME`)            | `ACTIVE`              | `DISPLAY_NAME` change requires the runtime to be ACTIVE.       |
| Update comment (`ALTER ... SET COMMENT`)                      | `ACTIVE`, `SUSPENDED` | Metadata-only; no runtime-state restriction beyond the fail-closed list below. |
| Clear display name (`ALTER ... UNSET DISPLAY_NAME`)           | `ACTIVE`              | Same constraint as the SET form. Reverts to the SQL `NAME`.    |
| Clear comment (`ALTER ... UNSET COMMENT`)                     | `ACTIVE`, `SUSPENDED` | Metadata-only.                                                 |


**Fail-closed STATUS values (refuse every action above).** If `DESCRIBE OPENFLOW RUNTIME` returns any of the following, stop immediately, tell the customer the runtime is not in an actionable state, and fall back to read-only guidance. Do not attempt to transition the runtime into a permitted state as part of a proposed action.

`CREATING`, `CREATE_FAILED`, `DELETING`, `DELETE_FAILED`, `DELETED`, `UPGRADING`, `UPGRADE_FAILED`, `SUSPENDING`, `ACTIVATING`, `UPDATING`, `RESTARTING`, `SUSPEND_FAILED`, `ACTIVATE_FAILED`, `RESTART_FAILED`, `UPDATE_FAILED`, `CANCEL_REQUESTED`, `GENERATING_DIAGNOSTIC_BUNDLE`

The status set above is the canonical Openflow runtime STATUS set minus `ACTIVE` and `SUSPENDED` (the only two states the allowlist accepts for any action). Deployment-only STATUS values (`INACTIVE`, `NOT_REPORTING`, `NOT_HEALTHY`, `DEACTIVATION_REQUIRED`) are intentionally not listed -- they cannot appear on a runtime row. If `DESCRIBE OPENFLOW RUNTIME` returns one of those, treat it as schema drift and fail closed.

Anything outside the table and not listed above: fail closed, ask the customer to confirm current state from the Openflow UI, and do not guess.

### Raw `EXTERNAL_ACCESS_INTEGRATIONS` format

`DESCRIBE OPENFLOW RUNTIME` returns `EXTERNAL_ACCESS_INTEGRATIONS` as a single string column. Worked examples (verified against the eval verifier `_parse_eai_list` in `evals/data-engineering/openflow-observability/shared/verifier/verifier_lib.py`):

| Runtime state | Raw column value | Parsed list |
|---|---|---|
| No EAIs attached | `[]` (or empty string in some clients) | `[]` |
| One EAI | `[OPENFLOW_POSTGRES_EAI]` | `["OPENFLOW_POSTGRES_EAI"]` |
| Multiple, including a quoted identifier | `[OPENFLOW_POSTGRES_EAI, "My EAI"]` | `["OPENFLOW_POSTGRES_EAI", "My EAI"]` |
| Multiple, JSON-encoded (current GS surface) | `["EAI_A","EAI_B"]` (escaped as `"[\"EAI_A\",\"EAI_B\"]"` in some clients) | `["EAI_A", "EAI_B"]` |

**Canonical parser (use this verbatim before applying gate 5).** Preserve both raw SQL tokens and comparison keys:

1. Trim outer `[`/`]` (or `(`/`)` if the client renders parentheses).
2. Split on `,`. If a token itself contains a comma or unbalanced quotes, fail closed rather than guessing.
3. For each part: trim whitespace and store the resulting `raw_token` exactly as Snowflake returned it, including surrounding quotes.
4. Derive a comparison key only for deduplication:
   - quoted identifiers compare by the quoted inner text exactly;
   - unquoted identifiers compare by uppercased text.
5. Drop empty entries.

Render existing entries back into `Current EAI list:`, `Proposed EAI list:`, and the final SQL using their preserved `raw_token` values. Do NOT strip quotes, re-quote, re-order, or case-fold existing entries. For the newly attached EAI, use the exact name returned by `SHOW EXTERNAL ACCESS INTEGRATIONS`; quote it with double quotes only when Snowflake returned or requires a quoted identifier, and escape any embedded double quote by doubling it.

### Connector-level support

Connector lifecycle actions (`START`, `STOP`, `COMMIT`, `ABORT`) and connector config-content edits (`config_set_property`, `config_set_asset`) are in the MVP allowlist ONLY for connector definitions whose `Openflow SQL support` column in the [Openflow SQL Connector Support Matrix](connector-support-matrix.md#connector-capability-matrix) is `GA`, `MVP`, or `PrPr` (all treated identically for the action lane; a `PrPr` connector may optionally include a preview note in the Confirmation Preview). Today that is `OPENFLOW_POSTGRES_CDC` (`GA`) and `OPENFLOW_MYSQL_CDC` (`PrPr`); every other connector definition (SQL Server, Oracle, MongoDB, BigQuery, Kafka, Kinesis, SaaS) is `Coming next` or `Not yet` and refuses to enter Openflow SQL Action Mode at all.

Connector `TERMINATE` and `DROP` remain denylisted (see [Action Denylist (MVP)](#action-denylist-mvp)).

#### Connector-Definition Support Gate (sub-check of Hard Gate 2)

Two ordered checks. Both MUST pass before any per-action preflight runs. The two checks compare different values from different sources -- the pre-gate compares pre-SQL inputs, the live check compares post-SQL fields:

| Check | What value | Source | Compares against |
|---|---|---|---|
| 1. Pre-gate | `connector_type` (e.g. `postgresql`) | Page context / user input (pre-SQL) | Matrix `connector_type alias` column |
| 2. Live check | `CONNECTOR_DEFINITION` (e.g. `OPENFLOW_POSTGRES_CDC`) | `SHOW`/`DESCRIBE` result (post-SQL) | Matrix `Connector definition` column |

**Important.** The pre-gate is a **negative filter**, not a positive support confirmation. `connector_type = postgresql` from page context is the same string for both SQL-managed and legacy (UI-only, pre-Openflow-SQL) postgres connectors -- the event-table metadata that drives `connector_type` does not carry SQL-managed-vs-legacy provenance. The pre-gate's job is to refuse non-postgres aliases before any SQL fires; Openflow SQL action support for postgres connectors is proven only by the live check below.

**1. Connector-type pre-gate (no SQL).** Read `connector_type` from input or page context. Normalize aliases (`postgres` -> `postgresql`, `mssql` / `sqlserver` -> `sql_server`). Look up the matching `connector_type alias` row in the matrix.

- If the matched row's `Openflow SQL support` column is **`GA`**, **`MVP`**, or **`PrPr`**, proceed to the live check below. Today `postgresql` (`OPENFLOW_POSTGRES_CDC`, `GA`) and `mysql` (`OPENFLOW_MYSQL_CDC`, `PrPr`) qualify. For a `PrPr` connector, you may optionally include a preview note in the Confirmation Preview (see the matrix legend).
- If `Openflow SQL support` is **`Coming next`** or **`Not yet`**, **fail closed immediately** -- route the customer to the Openflow UI for any lifecycle or config edit on this connector definition. Do NOT run any Openflow SQL action (no `SHOW OPENFLOW CONNECTORS`, no `DESCRIBE`). Diagnostic reads from the troubleshoot lane are still allowed (they're not mutating).
- If `connector_type` is missing from input, **ask the customer** for it. Do NOT run a discovery `SHOW OPENFLOW CONNECTORS` to infer it -- that would be an Openflow SQL action call against a possibly-unsupported definition.
- If `connector_type` does not match any `connector_type alias` row in the matrix (typo, third-party, future), **fail closed**. The matrix is the single source of truth for what the agent supports.

**Using `connectorDefinition` from page context (SOM only).** When page context carried `connectorDefinition` (e.g. `OPENFLOW_POSTGRES_CDC`), use it directly as the pre-gate lookup key against the matrix `Connector definition` column, instead of guessing the definition from the `connector_type` alias. This is a more precise pre-SQL negative filter -- it avoids the alias-to-definition ambiguity for connectors that share an alias family. Rules:

- Look up the row whose `Connector definition` equals `{connector_definition_hint}`. Apply the same status semantics as the alias path: `GA`/`MVP`/`PrPr` -> proceed to the live check; `Coming next`/`Not yet` -> fail closed with 0 SQL; no matching row -> fail closed.
- `{connector_definition_hint}` and the normalized `connector_type` alias MUST resolve to the **same matrix row**. If they disagree (e.g. alias `postgresql` but definition `OPENFLOW_MYSQL_CDC`), treat it as page-context drift and **fail closed** -- do not run the live check against a guess. This is a deliberate pre-SQL over-refusal (two disagreeing snapshots are no basis to pick a row); a self-consistent page context still proceeds to the live check.
- This remains a **pre-SQL hint**. The definition string in page context is a snapshot; the positive gate is still step 2's live `CONNECTOR_DEFINITION` from `SHOW`/`DESCRIBE`, which must match the same matrix row and **wins on any discrepancy**.
- When `connectorDefinition` is absent (gen1, or older host), fall back to the alias-based pre-gate exactly as written above.

**2. Openflow SQL action support live check (exactly 1 SQL).** Once the pre-gate passes, run ONE of the following queries -- not both -- to confirm SQL-managed status against live state:

```sql
-- When only a short connector name is known:
SHOW OPENFLOW CONNECTORS LIKE '{connector_name}' IN ACCOUNT;

-- When the FQN is already known:
DESCRIBE OPENFLOW CONNECTOR {connector_fqn};
```

**FQN resolution preference.** When `{openflow_connector_id}` is an integer, resolve `{connector_fqn}` via [ID Resolution](#id-resolution-and-namespace-mapping) first, then run the `DESCRIBE` form (avoids the `SHOW ... LIKE` multi-row branch). The id->FQN `SELECT` is a separate read-only round-trip *before* the support check, so the support budget is still exactly one live query (the `DESCRIBE`). Fall back to `SHOW` when the id is absent, non-integer, or unresolvable.

Validate the result against the matrix's `Connector definition` column for the same row that passed the pre-gate. For a `postgresql` pre-gate that means `CONNECTOR_DEFINITION = 'OPENFLOW_POSTGRES_CDC'`:

- Zero rows / `Unknown command` / `feature disabled` / `does not exist or not authorized` -> **fail closed**. The connector is legacy (created via the Openflow UI before Openflow SQL actions were available, so not visible to the SQL surfaces), the role lacks visibility, or the Openflow SQL action surface is disabled at the account level. Route to UI -- this is the path that catches "postgres alias passed the pre-gate, but the connector itself isn't SQL-managed".
- `SHOW` returns multiple rows -> **stop and ask** the customer to disambiguate. Do not run `DESCRIBE` against a guess.
- One row whose `CONNECTOR_DEFINITION` does not equal the matrix's `Connector definition` value for the alias (e.g., pre-gate said `postgresql` but live returned `OPENFLOW_MYSQL_CDC`) -> **fail closed**. Page context disagrees with live state; treat as drift and route to UI.
- Exactly one row with the expected `CONNECTOR_DEFINITION` -> the gate passes. Capture FQN, STATUS, CONNECTOR_DEFINITION, DEFAULT_VERSION_NAME, and (from `DESCRIBE` only) LIVE_VERSION_LOCATION_URI / DEFAULT_VERSION_LOCATION_URI. Per-action preflight may need additional queries (`DESCRIBE OPENFLOW RUNTIME` for parent state, `SHOW VERSIONS` for the rollback target) -- those are action-specific calls that fire AFTER the gate, not part of the support check.

This single live query replaces the prior two-step `SHOW` + `DESCRIBE` flow for Openflow SQL action support detection. The `DESCRIBE` form is preferred when the FQN is already known because it returns the full state set in one round-trip; the `SHOW` form is the fallback when the agent only has a short name.

**Net call counts:**
- Unsupported `connector_type` (`Coming next` / `Not yet` / not in matrix) -> 0 SQL (pre-gate refuses on alias).
- Supported connector (`GA` / `MVP` / `PrPr`), SQL-managed -> exactly 1 SQL (live check passes).
- Supported connector, legacy / UI-only -> exactly 1 SQL (live check returns 0 rows or error, fail closed, route to UI).
- Integer `{openflow_connector_id}` present -> one extra read-only `SELECT SYSTEM$OPENFLOW_GET_CONNECTOR_NAMES_BY_IDS(...)` precedes the support query (a resolution helper, not a support call; suppressed entirely when `openflowSqlActionsEnabled='false'`).

When a new connector definition is enabled for Openflow SQL actions, flip the matrix row's `Openflow SQL support` to `GA`/`MVP`/`PrPr`. No template edits, no gate-text edits required.

---

## ID Resolution and Namespace Mapping

- **Runtime FQN (preferred)**: `<database>.<schema>.<runtime>`. If the user gives only a short name, use `SHOW OPENFLOW RUNTIMES LIKE '{name}'` to disambiguate. Stop on multiple matches.
- **Connector FQN (SOM connectors)**: When `openflowConnectorId` is present as an **integer** id (not a UUID or name), resolve the FQN from it instead of matching a possibly-ambiguous short name. The argument is a **JSON array of integers** and must be a **literal constant** (it cannot wrap another function call):

  ```sql
  SELECT SYSTEM$OPENFLOW_GET_CONNECTOR_NAMES_BY_IDS('[{openflow_connector_id}]');
  ```

  Returns a **JSON array of objects** (`[{"id":..,"fully_qualified_name":"DB.SCHEMA.NAME"}]`); use `[0].fully_qualified_name` as `{connector_fqn}`, never the raw JSON. Unknown ids are dropped, so `[]` means "not found".

  This resolves **identity only, not authorization**: the FQN still feeds the same live `DESCRIBE OPENFLOW CONNECTOR` gate, whose `CONNECTOR_DEFINITION`-vs-matrix match (step 2) is a **type** check -- it does not prove the object is the one the customer is looking at (two connectors sharing a definition both pass). What bounds a wrong/spoofed id: resolution and every read/mutation run under the **customer's role** (an id the role cannot see returns `[]` / `does not exist or not authorized` -> fail closed, no escalation), and the Confirmation Preview must show the resolved `{connector_fqn}` so the customer confirms identity.

  **Fallback** to `SHOW OPENFLOW CONNECTORS LIKE '{connector_name}' IN ACCOUNT` (with its multi-row "stop and ask") when the id is absent/non-integer, the call errors (`Unknown function`, `unsupported`, `insufficient privileges`, `idsJson must be a valid JSON array`, `Each ID ... must be an integer`), or the result is `[]` / NULL / unparseable / multi-object. Do not fail the action on the resolution attempt alone. The reverse `SYSTEM$OPENFLOW_GET_CONNECTOR_ID_BY_NAME('<name>')` (name -> id; needs a current schema) is available for verification, not required.

  > `openflowConnectorId` is a `BIGINT` carried as a decimal string (snapps `.../openflowobservability/connector_names.go`); guard on all-digits. The UUID-looking `connector_url` is that integer hex-encoded, not this id.
- **Display name vs SQL name**: `DESCRIBE OPENFLOW RUNTIME` returns both. Always use the SQL `NAME`, never the `DISPLAY_NAME`, in the mutating SQL.
- **Event-table namespace** (used for verification log scans): `runtime-<key>` -- do not invent the namespace, and do not derive it by sanitizing the runtime name (SOM runtimes carry a `-NNN` key suffix that name-sanitization misses). Read the `key` field back from `DESCRIBE OPENFLOW RUNTIME`, or take the namespace from a recent log row in the event table.
- **EAI names**: must match `SHOW EXTERNAL ACCESS INTEGRATIONS` exactly (case-sensitive identifiers if quoted). When the EAI itself is missing or not granted to the runtime role, do NOT silently create or grant it -- load `admin-ddl-assist.md` for customer-run admin guidance.

---

## SQL Rendering and Input Safety

All mutating SQL templates MUST follow these rendering rules:

- Prefer identifiers and FQNs discovered from live `SHOW` / `DESCRIBE` results. Do not substitute a display name, UI label, or user prose when a SQL `NAME`, `DATABASE_NAME`, or `SCHEMA_NAME` is available.
- Reject user-provided identifiers, stage names, stage paths, property names, and filenames that contain semicolons, SQL comments (`--`, `/*`, `*/`), newlines, carriage returns, NUL bytes, or other control characters.
- SQL string literals are single-quoted, with single quotes escaped by doubling (`'` -> `''`). Do not use backslash escaping for SQL strings.
- FQNs are rendered part-by-part. Preserve quoting from live SQL results; when constructing a quoted identifier, wrap the part in double quotes and escape embedded double quotes by doubling them.
- Stage references must be shape-checked before use. Customer-provided stages for driver JARs must be a stage reference rooted at a Snowflake stage (for example `@DB.SCHEMA.STAGE` or `@DB.SCHEMA.STAGE/path`), not an arbitrary URI, and the JAR filename must be an exact basename match with no path separators.
- EAI list rendering follows [Raw `EXTERNAL_ACCESS_INTEGRATIONS` format](#raw-external_access_integrations-format): preserve existing raw tokens and append only the validated new token.

If any required value cannot be rendered safely, fail closed and route the customer to the Openflow UI or customer-run SQL.

---

## Action Allowlist (MVP)

> **Canonical source.** This table is the authoritative MVP allowlist. SKILL.md surfaces action families as a routing index only; on any discrepancy, this table wins. When adding or removing an entry, update this table -- SKILL.md does not enumerate templates.

The skill MAY execute exactly these statements after every gate passes. Templates and preflight live in the action-family files under `references/openflow-sql/` (`runtime-actions.md`, `deployment-actions.md`, `connector-actions.md`, and `connector-config-edit.md`).


| ID                         | Statement template                                                                         | Use when                                                                                                                                     |
| -------------------------- | ------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `runtime.attach_eai`       | `ALTER OPENFLOW RUNTIME {runtime_fqn} SET EXTERNAL_ACCESS_INTEGRATIONS = ({eai_list_csv})` | An existing EAI (and matching network rule) needs to be attached to a SQL-managed runtime.                                                   |
| `runtime.restart`          | `ALTER OPENFLOW RUNTIME {runtime_fqn} RESTART`                                             | Customer-safe restart cases (e.g. stale TLS certs on otherwise-stable SPCS runtime). Agent does not propose `RESTART RECOVERY` in MVP (the Openflow SQL action surface supports it, reserved for customer break-glass).         |
| `runtime.resume`           | `ALTER OPENFLOW RUNTIME {runtime_fqn} RESUME`                                              | Runtime is `SUSPENDED` and user explicitly asked to resume. Agent does not propose `RESUME RECOVERY` in MVP (the Openflow SQL action surface supports it, reserved for customer break-glass).                                  |
| `runtime.suspend`          | `ALTER OPENFLOW RUNTIME {runtime_fqn} SUSPEND`                                             | User explicitly asked to suspend (cost / pause). Confirm cost impact.                                                                        |
| `runtime.set_display_name` | `ALTER OPENFLOW RUNTIME {runtime_fqn} SET DISPLAY_NAME = {quoted_string}`                  | Low-risk explicit user request. Runtime must be `ACTIVE`.                                                                                    |
| `runtime.set_comment`      | `ALTER OPENFLOW RUNTIME {runtime_fqn} SET COMMENT = {quoted_string}`                       | Low-risk explicit user request. Runtime must be `ACTIVE` or `SUSPENDED`.                                                                     |
| `runtime.unset_display_name` | `ALTER OPENFLOW RUNTIME {runtime_fqn} UNSET DISPLAY_NAME`                                | Low-risk explicit user request to clear a display name. Runtime must be `ACTIVE`. UI reverts to showing the SQL `NAME`.                       |
| `runtime.unset_comment`    | `ALTER OPENFLOW RUNTIME {runtime_fqn} UNSET COMMENT`                                       | Low-risk explicit user request to clear a comment. Runtime must be `ACTIVE` or `SUSPENDED`.                                                  |
| `deployment.set_display_name` | `ALTER OPENFLOW DEPLOYMENT "{deployment_name}" SET DISPLAY_NAME = {quoted_string}`         | Low-risk explicit user request to update the deployment display label. Requires deployment `OWNERSHIP`. Deployment must be `ACTIVE`.        |
| `deployment.set_comment`   | `ALTER OPENFLOW DEPLOYMENT "{deployment_name}" SET COMMENT = {quoted_string}`                | Low-risk explicit user request to set a deployment comment. Requires deployment `OWNERSHIP`. Deployment must be `ACTIVE`.                    |
| `connector.start`           | `ALTER OPENFLOW CONNECTOR {connector_fqn} START`                                          | Connector is `STOPPED` with a non-NULL default version, parent runtime is `ACTIVE`, and parent runtime `NODE_TYPE` meets the connector-definition minimum (CDC connectors require `MEDIUM`+). Post-action validation is via the [Post-Action Error Scan](connector-diagnostics.md#post-action-error-scan). |
| `connector.stop`            | `ALTER OPENFLOW CONNECTOR {connector_fqn} STOP`                                           | Connector is `RUNNING` or `UPDATE_FAILED`. CDC connectors get the retention banner in the preview.                           |
| `connector.commit`          | `ALTER OPENFLOW CONNECTOR {connector_fqn} COMMIT`                                         | Connector is `STOPPED` or `DRAFT` with a non-NULL `LIVE_VERSION_LOCATION_URI`. Post-action validation is via the [Post-Action Error Scan](connector-diagnostics.md#post-action-error-scan). |
| `connector.abort`           | `ALTER OPENFLOW CONNECTOR {connector_fqn} ABORT`                                          | Live version exists AND a default version exists (DRAFT connectors cannot ABORT).                                            |
| `connector.config_set_property` | Stage-promote path: stage roundtrip + `ALTER ... ADD VERSION FROM '@stage'`         | Property edit on a STRING_LITERAL field in `config.json`. Connector must be `STOPPED` or `DRAFT`. Before/after value diff required in preview. See [connector-config-edit.md](connector-config-edit.md). |
| `connector.config_set_asset` | Stage-promote path: stage assemble (config + JAR) + `ALTER ... ADD VERSION FROM '@stage'` | Sets `ASSET_REFERENCE` `assetIds`. Driver JAR MUST already be on a customer-named stage; the agent does not upload binaries. See [connector-config-edit.md](connector-config-edit.md). |


**List-property preservation.** For `runtime.attach_eai`, the agent MUST first read the existing list from `DESCRIBE OPENFLOW RUNTIME` (`EXTERNAL_ACCESS_INTEGRATIONS` column), union it with the new value, deduplicate, then preview the full final list. Never replace the list with just the new EAI.

**Connector config-edit preview extension.** For `connector.config_set_property` and `connector.config_set_asset`, the preview MUST include a JSON-level **before/after diff** for the affected property, not just the SQL. Render only the scalar `Current value` / `Proposed value` (or `assetIds`) lines for the property's full path within `configuration[].properties`; never render the surrounding property object in full.

**Auto-stop is NOT chained.** Connector config-edit actions require the connector to be `STOPPED` or `DRAFT`, and `connector.commit` requires `STOPPED` or `DRAFT`. The agent does NOT chain `connector.stop` automatically into `connector.commit` or `connector.config_*`. If the connector is `RUNNING`, propose `connector.stop` as a separate, freshly previewed and confirmed action; once that lands in `STOPPED`, propose the next action with a fresh preview.

**Auto-start IS proposed (with fresh confirmation).** After `connector.commit` or any `connector.config_*` action lands the connector in `STOPPED`, the agent MAY propose `connector.start` as the next action. The customer must approve it with a fresh confirmation; do not execute it as part of the same response.

> **Why this is the agent's job, not Snowflake's.** `ALTER OPENFLOW RUNTIME ... SET EXTERNAL_ACCESS_INTEGRATIONS = (X)` is a **REPLACE**, not an append. A customer who runs the bare statement themselves will silently lose every EAI not named in the new list -- and the only signal is `DESCRIBE OPENFLOW RUNTIME` afterwards (no warning, no error). The read-union-write protocol in this skill is the one and only protection against that footgun. If a future allowlist entry sets any other multi-value runtime property (e.g. a future `LABELS`, `TAGS`, or similar collection), it MUST follow the same read-union-write pattern and surface the same `Current X list` / `Proposed X list` lines in the preview. Never trust the user-supplied value as the full final list.

---

## Action Denylist (MVP)

These are explicitly OUT of the MVP. Do not preview, do not execute, do not pretend to. If the user asks, explain that the agent does not perform this action and direct them to the Openflow UI or customer-run SQL.

- `DROP OPENFLOW RUNTIME`, `DROP OPENFLOW CONNECTOR`, `DROP OPENFLOW DEPLOYMENT` (any variant including `CASCADE`)
- `ALTER OPENFLOW * TERMINATE` (any variant including `TERMINATE CASCADE`)
- `CREATE OPENFLOW RUNTIME`, `CREATE OPENFLOW DEPLOYMENT`, `CREATE OPENFLOW CONNECTOR`
- `ALTER OPENFLOW RUNTIME ... UPGRADE`, `ALTER OPENFLOW DEPLOYMENT ... UPGRADE`
- `ALTER OPENFLOW RUNTIME ... RESTART RECOVERY`, `ALTER OPENFLOW RUNTIME ... RESUME RECOVERY` (the Openflow SQL action surface supports the `[RECOVERY]` modifier, but the agent does not propose it in MVP -- it brings the runtime back up with all processors stopped and is reserved for break-glass investigation by the customer in the Openflow UI)
- `ALTER OPENFLOW RUNTIME ... SET EXECUTE_AS_ROLE`, `ALTER OPENFLOW RUNTIME ... UNSET EXECUTE_AS_ROLE` (privileged and easy to mis-set; defer)
- Runtime node-size change ("SET NODE_TYPE"). NODE_TYPE (Small / Medium / Large) is fixed at create time and cannot be changed by any path -- not SQL, not the Openflow UI -- so there is no mutation to propose. For "make it bigger" / "more memory per node", explain it is create-time-only and the only path is a new larger runtime in the UI. Node count (`MIN_NODES` / `MAX_NODES`) is also not allowlisted; offer it only as customer-run guidance. See [troubleshoot-runtime.md](../troubleshoot-runtime.md) (OOM / Memory branch).
- `ALTER OPENFLOW RUNTIME ... RENAME TO`, `ALTER OPENFLOW DEPLOYMENT ... RENAME TO` (requires `CREATE` privilege; defer)
- Connector mutations not in MVP: `ALTER OPENFLOW CONNECTOR ... TERMINATE` (any variant including `TERMINATE CASCADE`), `DROP OPENFLOW CONNECTOR`, `ALTER OPENFLOW CONNECTOR ... SET DISPLAY_NAME / COMMENT` (and their UNSET forms; cosmetic-only, customers do this in the UI)
- Connector ownership transfer: `GRANT OWNERSHIP ON OPENFLOW CONNECTOR ...`
- Connector recreate or whole-config replace via `CREATE OPENFLOW CONNECTOR` / `ADD VERSION FROM '@<customer-prepared-stage>'` (the agent applies new config to existing connectors only via the stage-promote path targeting its own working stage and only via the two allowlisted property/asset actions)
- SECRET_REFERENCE writes (the wizard's `providerId` UUID minting is not validated via SQL; refuse and direct to the Openflow UI)
- CDC restart-table-replication, destination table `DROP` / `TRUNCATE`, manual stream/sequence resets
- Any `GRANT`, `CREATE NETWORK RULE`, or `CREATE EXTERNAL ACCESS INTEGRATION` (load `admin-ddl-assist.md` for customer-run guidance)

---

## CDC Retention Warning (Cross-Cutting)

Several allowlisted actions pause CDC connectors -- either by stopping the connector itself (`connector.stop`, `connector.commit`, `connector.config_set_property`, `connector.config_set_asset`), or by taking down the parent runtime (`runtime.suspend`, `runtime.restart`). Every one of these actions MUST surface a CDC retention banner in the Confirmation Preview's **Expected impact** field when any in-scope connector has `Family = CDC` in the [Openflow SQL Connector Support Matrix](connector-support-matrix.md#connector-capability-matrix). Consult the matrix rather than hardcoding the CDC connector list -- when new CDC connectors are added, the matrix is the single source of truth.

### Canonical banner

> **CDC retention risk:** pausing a CDC connector for longer than the source database's WAL, binlog, or logical-replication-slot retention window will age out the log positions the connector needs. On resume the connector cannot rewind past the retention cutoff and a per-table reseed (see Restart Table Replication in SKILL.md) may be required. Source-side knobs to check by family:
>
> - **Postgres**: `wal_keep_size` (or legacy `wal_keep_segments`), `max_slot_wal_keep_size`, plus the replication-slot's `confirmed_flush_lsn` lag.
> - **MySQL**: `expire_logs_days` / `binlog_expire_logs_seconds`, `binlog_row_image`, `binlog_format`.
> - **SQL Server**: transaction log backup cadence (ensures the log can grow), CDC capture-job retention, `sys.dm_repl_logreader_status` lag.
> - **Oracle**: archive log retention (`db_recovery_file_dest_size`, RMAN backup cadence), supplemental logging, LogMiner staging.

### Duration prompt (mandatory before tier selection)

Before previewing any CDC-pausing action where duration is customer-stated (`connector.stop`, `runtime.suspend`), ask the customer once, verbatim:

> How long do you expect the pause? Reply with one of:
> (a) under 1 hour
> (b) 1-24 hours
> (c) over 24 hours

Do NOT infer duration from prose in the customer's request (e.g., "over the weekend", "during long maintenance"). Prose hints are unreliable -- the duration prompt's three buckets are the single source of truth. If the customer answers anything other than (a)/(b)/(c), re-prompt with the same three options.

Tier mapping:

| Reply | Tier |
|---|---|
| (a) under 1 hour | **Standard** |
| (b) 1-24 hours | **Strong** |
| (c) over 24 hours | **Escalate** |

Skip the prompt only when the action's intrinsic duration is bounded:

- `runtime.restart` -- minutes-scale, always **Standard**.
- `connector.commit`, `connector.config_set_property`, `connector.config_set_asset` -- the UPDATING window is minutes-scale, always **Standard**.

### Tier wording in the preview

| Tier | Wording in the preview |
|---|---|
| **Standard** | Include the canonical banner verbatim plus "verify your source retention covers the pause duration". |
| **Strong** | Canonical banner + "Postgres WAL slots typically age out within 24-48h depending on `max_slot_wal_keep_size`; verify before approving." |
| **Escalate** | Canonical banner + "**very high risk** of WAL / binlog / archive-log positions aging out; on resume the connector may require a full table reseed". Recommend the customer take a manual snapshot or coordinate with a maintenance window before approving. |

### Action-specific variants

| Action | Tier source |
|---|---|
| `runtime.restart` | Always **Standard** (minutes-scale). |
| `runtime.suspend` | From the duration prompt above. |
| `connector.stop` | From the duration prompt above. |
| `connector.commit`, `connector.config_set_property`, `connector.config_set_asset` | Always **Standard** (UPDATING window is minutes-scale). |

The action template files (`runtime-actions.md`, `connector-actions.md`, `connector-config-edit.md`) reference this section rather than restating the banner -- update this section if the source-side knob list or the tier wording changes.

---

## Confirmation Preview Format

> **One preview per response.** Each agent response renders at most ONE Confirmation Preview block. Multi-step plans (e.g., stop -> commit -> start) are presented one preview at a time. The customer's affirmative reply applies only to the most recent single preview. If a previous response had multiple previews, the agent MUST refuse to execute on the customer's reply, apologize for the rendering error, and re-render exactly one preview. Stacked previews encourage a single combined "yes" that bypasses the per-action confirmation gate.

When the SQL action support gate and the allowlist gate have both passed, the agent presents a single preview block to the user. The preview MUST include all six fields below. If any field is unknown, stop and gather it before previewing -- do not guess. The header text is customer-visible -- use exactly "Openflow SQL action proposal".

```
Openflow SQL action proposal
  Action:        <plain-language description, e.g. "attach EAI to runtime">
  Target:        <runtime_fqn>   (display name: <display_name_or_none>)
  Current state: <relevant fields from DESCRIBE OPENFLOW RUNTIME>
  Proposed SQL:  <exact SQL that will be executed, single statement>
  Expected impact:
    - downtime / cost / data implications, written plainly
    - irreversibility note if any
  Verification:  <SHOW or DESCRIBE statement that will be run after>
Reply `"yes"`, `"proceed"`, `"approved"`, or `"do it"` to execute; anything else cancels.
```

**List-property extension for `runtime.attach_eai`.** When the action is `runtime.attach_eai`, the preview MUST add two extra lines after `Current state` so the customer sees the full before/after of the `EXTERNAL_ACCESS_INTEGRATIONS` list. List preservation is the easiest invariant to break silently.

```
  Current EAI list:  [EAI_A, EAI_B]
  Proposed EAI list: [EAI_A, EAI_B, EAI_C_NEW]
  Removed:           []
```

Render both lists in the exact spelling returned by `DESCRIBE OPENFLOW RUNTIME` (case-sensitive identifiers if quoted). Do not abbreviate or re-order existing entries.

The `Action` field is plain language for the customer ("attach EAI to runtime", "restart runtime", "stop connector"). Do NOT print the internal action ID like `runtime.attach_eai` to the customer.

### Confirmation Matching Rule

The agent MUST wait for an exact-match affirmative before issuing the proposed SQL. Apply the rule mechanically:

1. Take the customer's reply.
2. Trim whitespace.
3. Strip leading and trailing punctuation (`.`, `!`, `?`, `,`, `;`, `:`).
4. Lowercase.

The normalized result MUST equal exactly one of these four tokens:

- `yes`
- `proceed`
- `approved`
- `do it`

Anything else fails closed. This includes (non-exhaustive):

- Synonyms: `yeah`, `yep`, `go`, `go ahead`, `run it`, `execute`, `confirmed`, `ok`, `sure`, `sounds good`, `ship it`, `i guess`, `fine`.
- Modified affirmatives: `yes please`, `approved with the smaller node count`, `do it carefully`, `do it once you've checked X first`, `proceed but only after Y`. Any modifier voids the affirmative -- restart the preflight from scratch and present a fresh preview.
- Conditionals: `if it's safe, yes`, `proceed if X`.

When the reply does not match, cancel the action using [Cancellation and Denial Handling](#cancellation-and-denial-handling). Do not re-prompt with the same preview.

If the customer asks to modify the proposal (e.g. a different EAI, different node counts), re-run the preflight from scratch and present a new preview. Do not piecewise-edit a previously-approved plan.

---

## Cancellation and Denial Handling

The Confirmation gate fails closed on any reply that does not match the [Confirmation Matching Rule](#confirmation-matching-rule). When that happens:

1. **Stop the action.** Do not execute the previewed SQL. Do not re-prompt with the same preview.
2. **Customer-facing reply (use this wording):** "Action canceled. I won't run that SQL."
3. **Reentry.** Return to diagnostic mode. If the customer's reply suggests an alternative ("can we do X instead?"), treat it as a fresh diagnostic question, NOT a modification of the canceled preview. If the alternative names a different allowlisted action, re-run preflight from scratch for that action and present a new preview (subject to all five hard gates again).
4. **No re-propose without a fresh customer ask.** The agent MUST NOT re-render the canceled preview in the same session unless the customer explicitly asks to retry the action by name.

The cancellation path applies equally whether the customer said "no", said something ambiguous, or asked a clarifying question instead of approving. Treating any non-affirmative as a cancellation is the safe default; the customer can always re-request the action explicitly.

### Worked Example: `runtime.attach_eai`

Use this as the literal template for EAI attach proposals. Swap in the customer's values.

```
Openflow SQL action proposal
  Action:        attach EAI to runtime
  Target:        PROD_OPENFLOW.OPENFLOW_DB.SALES_RUNTIME   (display name: Sales CDC)
  Current state: STATUS = ACTIVE, MIN_NODES = 1, MAX_NODES = 3, DEPLOYMENT = TEST_DEPLOYMENT (parent DEPLOYMENT_TYPE = SNOWFLAKE per DESCRIBE OPENFLOW DEPLOYMENT)
  Current EAI list:  [OPENFLOW_POSTGRES_EAI]
  Proposed EAI list: [OPENFLOW_POSTGRES_EAI, OPENFLOW_SALESFORCE_EAI]
  Removed:           []
  Proposed SQL:  ALTER OPENFLOW RUNTIME PROD_OPENFLOW.OPENFLOW_DB.SALES_RUNTIME
                   SET EXTERNAL_ACCESS_INTEGRATIONS = (OPENFLOW_POSTGRES_EAI, OPENFLOW_SALESFORCE_EAI);
  Expected impact:
    - STATUS stays ACTIVE throughout. The runtime does NOT restart and does NOT pass through RESTARTING / UPDATING. The new EAI is in effect on the next processor scheduling tick. CDC connectors are not paused.
    - No data loss.
    - Cost impact: none.
    - Reversible by another ALTER ... SET EXTERNAL_ACCESS_INTEGRATIONS = (...) that omits OPENFLOW_SALESFORCE_EAI.
  Verification:  DESCRIBE OPENFLOW RUNTIME PROD_OPENFLOW.OPENFLOW_DB.SALES_RUNTIME;
Reply "yes", "proceed", "approved", or "do it" to execute; anything else cancels.
```

---

## Secret Leak Prevention

When rendering `Current state` / `Current value` / before-after diffs in any preview, show ONLY the named property's `value` field (or `assetIds` for ASSET_REFERENCE). Never render the surrounding `properties.<key>` block in full -- a sibling property may contain plaintext credentials, even though customers SHOULD use SECRET_REFERENCE for those.

Before rendering, scan the value against this credential-pattern denylist. If any pattern matches, **fail closed** -- do not render the preview, do not execute the action, and surface a customer-facing message: "I detected a credential pattern in the property block I would render. I cannot show this in a preview; please review the property in the Openflow UI."

| Pattern | Regex | Why |
|---|---|---|
| Basic auth in URL | `://[^:/@]+:[^@]+@` | E.g. `jdbc:postgresql://user:pass@host` -- plaintext password in connection URL. |
| Password assignment | `(?i)password\s*=` | Common in connection-string properties or query-string options. |
| API key assignment | `(?i)api[_-]?key\s*=` | Catches both `apikey=` and `api_key=`. |
| Bearer token | `Bearer\s+[A-Za-z0-9._\-]+` | OAuth bearer in headers or strings. |
| PEM private key | `-----BEGIN .* PRIVATE KEY-----` | Snowflake / SSL key-pair material. |

The scan applies to BOTH `Current value` and `Proposed value`. If the customer's proposed new value matches a denylist pattern, treat it the same way: refuse and direct to the UI's secret-management flow.

---

## Verification After Execution

Run the previewed verification query and report before/after. Default verification:


| Action                                                 | Verification                                                                                                                                                                  |
| ------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `runtime.attach_eai`                                   | `DESCRIBE OPENFLOW RUNTIME {runtime_fqn};` and confirm `EXTERNAL_ACCESS_INTEGRATIONS` includes the new entry plus all prior entries.                                          |
| `runtime.restart`, `runtime.resume`, `runtime.suspend` | `DESCRIBE OPENFLOW RUNTIME {runtime_fqn};` -- watch `STATUS` transition. Optional follow-up: scoped Recent Error Logs query bounded to the post-action window.                |
| `runtime.set_display_name`, `runtime.set_comment`      | `DESCRIBE OPENFLOW RUNTIME {runtime_fqn};` -- confirm new value.                                                                                                              |
| `connector.start`, `connector.stop`                    | `DESCRIBE OPENFLOW CONNECTOR {connector_fqn};` -- watch `STATUS` settle via a single snapshot. Then run the [Post-Action Error Scan](connector-diagnostics.md#post-action-error-scan) for the runtime namespace bounded to the last 2 minutes. If `ERROR` rows return, surface verbatim and provide customer-run recovery guidance; do not execute rollback SQL. |
| `connector.commit`, `connector.abort`                  | `DESCRIBE OPENFLOW CONNECTOR {connector_fqn};` and `SHOW VERSIONS IN OPENFLOW CONNECTOR {connector_fqn};` -- confirm `LIVE_VERSION_LOCATION_URI` cleared and `DEFAULT_VERSION_NAME` advanced (commit) or unchanged (abort). Then run the [Post-Action Error Scan](connector-diagnostics.md#post-action-error-scan). |
| `connector.config_set_property`, `connector.config_set_asset` (stage-promote path) | `DESCRIBE OPENFLOW CONNECTOR {connector_fqn};` then `SHOW VERSIONS IN OPENFLOW CONNECTOR {connector_fqn};` then the [Post-Action Error Scan](connector-diagnostics.md#post-action-error-scan). If `ERROR` rows return, surface verbatim and provide the customer-run rollback guidance from the config-edit template; do not execute the rollback `ADD VERSION FROM` from the agent. |


If verification shows the property did not change, do NOT retry. Tell the customer the action did not take effect and pivot to diagnosis.

---

## Failure Handling

- **Snowflake error during execution**: stop. Surface the error verbatim to the user. Do not chain a follow-up `ALTER`, `CREATE`, or `DROP`.
- **Privilege error** (`Insufficient privileges to operate on ...`): tell the customer which privilege is missing per the Openflow SQL security model (`OPERATE` for restart/resume/suspend/upgrade, `OWNERSHIP` for SET / RENAME / TERMINATE / DROP, `MONITOR` for SHOW/DESCRIBE). Recommend the customer run `SHOW GRANTS ON OPENFLOW RUNTIME {runtime_fqn}` (documented in [`connector-diagnostics.md`](connector-diagnostics.md#show-grants-on-openflow-runtime)) to enumerate which roles already have which privileges -- that is the concrete evidence-gathering step before any `GRANT` request goes to an admin. Do NOT silently `GRANT` from the agent.
- **State error** (`ALTER is not permitted on a runtime in CREATING/...`): tell the customer the current state and what state is required. Do not attempt a fix-by-suspend-then-resume sequence in the MVP.
- **Async work**: Openflow SQL tasks are queued (FIFO, 2 concurrent). If the system reports the task is queued, tell the customer and stop. Do not poll-and-retry from inside the same response. **Issue at most one `ALTER OPENFLOW` per response** -- a queued or in-flight result is a STOP, never a cue to issue a second `ALTER` or "try the next step". See the [Pending Action Tracker](#pending-action-tracker) below for the cross-action queue rule.

---

## Pending Action Tracker

When the agent issues an Openflow SQL action in the current session, track three fields per mutation: action ID (e.g. `runtime.suspend`), target FQN, and timestamp. Before previewing a NEW mutation in the same session, check the tracker:

| Tracker state | Behavior |
|---|---|
| Empty | Proceed with normal preview. |
| Prior mutation reported as `queued` by Snowflake (FIFO 2-concurrent backend) | Refuse to preview the new mutation. Tell the customer the prior task is still queued and ask them to wait, then restart the request when the queue drains. |
| Prior mutation executed but not yet observed in a settled STATUS (e.g., target is still in `UPDATING` / `RESTARTING` / `ACTIVATING` / `SUSPENDING` per `DESCRIBE`) | Refuse to preview the new mutation. Re-run the prior verification first; only proceed if the target reaches a settled STATUS. |
| Prior mutation verified settled | Proceed. |

Reset the tracker only after a successful verification (settled STATUS observed) or when the customer cancels via the [Cancellation and Denial Handling](#cancellation-and-denial-handling) protocol. Do NOT reset the tracker just because a new turn started; tracking is session-scoped, not turn-scoped.

This rule is independent of the [One preview per response](#confirmation-preview-format) rule: the latter prevents stacked previews in a single response, the tracker prevents back-to-back previews across responses while a prior mutation is in-flight.

---
