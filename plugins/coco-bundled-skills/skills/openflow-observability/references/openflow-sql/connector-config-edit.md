---
name: openflow-observability-connector-config-edit
description: SQL-only connector config edit templates for STRING_LITERAL properties and ASSET_REFERENCE driver wiring via the stage-promote path (ADD VERSION FROM stage). Tier 2 -- load only when an allowlisted connector config-edit action candidate exists.
---

<a id="openflow-sql-connector-config-edit-actions"></a>
# Openflow SQL Connector Config-Edit Actions

> Customer-facing name: **Openflow SQL connector config edit**.

Templates for the connector config-edit actions in the MVP allowlist:

- `connector.config_set_property` -- regex-targeted edit of a single STRING_LITERAL property in `config.json`
- `connector.config_set_asset` -- set `ASSET_REFERENCE.assetIds` to reference a customer-staged JAR

These are the highest-risk actions in the MVP. They mutate the connector's `config.json` and create a new default version. Every template here assumes [action-guidelines.md](action-guidelines.md) is already loaded and all five hard gates from [SKILL.md](../../SKILL.md#openflow-sql-action-mode) will be enforced before the proposed SQL is executed.

> **STOP — what these actions actually do (BLOCKING).** `config_set_property` and `config_set_asset` are NOT "promote a new version" actions. They REWRITE the connector's `config.json` (via `REGEXP_REPLACE` against the snapshot in the working stage) and THEN promote the rewrite. If the agent skips the rewrite steps and goes straight from `COPY FILES` to `ALTER OPENFLOW CONNECTOR ... ADD VERSION FROM`, it promotes an unchanged `config.json` as a "new" version. The version count in `SHOW VERSIONS` increments, the customer thinks the edit landed, and silently nothing changed. The customer's NEW VALUE (or new `assetIds`) MUST appear as a SQL string literal in at least one executed SQL statement before `ADD VERSION FROM` runs — if it does not, the action is broken.

> **Hard precondition for `ADD VERSION FROM` (BLOCKING).** Before issuing `ALTER OPENFLOW CONNECTOR {fqn} ADD VERSION FROM '@stage'`, the agent MUST be able to point at three executed SQL statements in this turn that include, in order:
> 1. A `REGEXP_COUNT` against the snapshotted `config.json` returning `1` (uniqueness gate).
> 2. A `REGEXP_REPLACE` rewrite that writes back to the working stage's `config.json` and whose SQL text contains the customer's new value as a string literal.
> 3. A post-edit validation query that confirms `json_ok = TRUE`, `post_edit_match_count = 1`, and the observed value matches the new value.
>
> If any of those three is missing, do not issue `ADD VERSION FROM`. Surface the missing step and stop. The Mandatory Step Checklist (refusal rule) below restates this precondition per action.

For lifecycle actions (`START`, `STOP`, `COMMIT`, `ABORT`) see [connector-actions.md](connector-actions.md). For diagnostics see [connector-diagnostics.md](connector-diagnostics.md).

## Scope

- **Stage-promote path only**: `ALTER OPENFLOW CONNECTOR ... ADD VERSION FROM '@stage'`. No COMMIT step. Auto-promotes to default. Connector lands in `STOPPED`.
- Out of scope: SECRET_REFERENCE writes (refuse and direct to UI -- the wizard's `providerId` UUID minting is not validated via SQL), full-config replacement (customers with prepared configs run their own SQL), connector recreation, schema-changing edits to `configFormatVersion`.

The agent commits to one workflow. Customers who want explicit `ABORT`-before-apply control should use the Openflow UI wizard.

Do not run the working-stage `CREATE` statements until [Shared Preflight](#shared-preflight-all-config-edit-actions) step 0 has passed. Unsupported connector definitions fail before any mutating SQL, including stage setup. The working-stage `CREATE`, `REMOVE`, `COPY FILES`, and `COPY INTO @stage/config.json` statements are scratch-stage preflight writes governed by [Scratch-Stage Preflight Exception](action-guidelines.md#scratch-stage-preflight-exception); they do not authorize the final `ALTER OPENFLOW CONNECTOR ... ADD VERSION FROM`.

> **Per-connector property catalogs.** When proposing a property edit, look up the valid `value` form in the connector-definition's property catalog before generating the diff. The connector validator accepts only the form the catalog specifies -- in practice this is **either** the Java enum constant name (e.g. `CASE_INSENSITIVE`) **or** a display-label string with spaces (e.g. `"Set Null"`), depending on whether the underlying enum class declares a 3-arg constructor that overrides its serialized value. Mixing the two produces `Value is not one of the allowable values` validation errors that land the connector in `UPDATE_FAILED`. Never guess; always look up. Catalogs:
> - PostgreSQL CDC (SQL-managed, `OPENFLOW_POSTGRES_CDC`): [postgresql-sql-managed.md](../connectors/postgresql-sql-managed.md)
> - MySQL CDC (SQL-managed, `OPENFLOW_MYSQL_CDC`, PrPr): [mysql-sql-managed.md](../connectors/mysql-sql-managed.md)
> - Other connector definitions: catalog not yet documented; defer the property edit and direct the customer to the Openflow UI wizard.

---

## Stage Bootstrap (After Support Gate Passes)

Two stage classes are involved:

1. **Working stage** (agent-managed, one per session). Used inside the edit templates as the staging area. The agent creates it if it does not exist.
2. **Customer-named stage** (customer-managed, persistent). Used to hold driver JARs for `connector.config_set_asset`. The agent treats this stage as **read-only input** and never writes to it.

### Working stage setup

```sql
-- Regular stage required for ADD VERSION FROM (the stage-promote path). TEMPORARY stages
-- fail with 'Failed to decrypt input stream' when used as the source.
-- Per-session suffix prevents cross-session collisions when two agents edit
-- in parallel: {session_suffix} is a random 8-char hex token generated at
-- action entry, never reused across sessions.
CREATE STAGE IF NOT EXISTS {db}.{schema}.OPENFLOW_CONFIG_WORK_{session_suffix}
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');

CREATE FILE FORMAT IF NOT EXISTS {db}.{schema}.JSON_FF_RAW
  TYPE = JSON STRIP_OUTER_ARRAY = FALSE;
```

`{db}.{schema}` should match the connector's database and schema so the working stage shares the same RBAC scope.

`{session_suffix}` MUST be a fresh random token generated when the agent enters the action lane. Examples that are NOT acceptable: hard-coded constants, the connector name, the customer's user name, the deployment id. Examples that are acceptable: 8 hex chars from a random source, a UUID4 fragment, a millisecond timestamp combined with a counter. The point is per-session uniqueness.

### Driver JAR sourcing (for `connector.config_set_asset`)

The agent CANNOT conjure binary content. The customer must have already placed the driver JAR on a Snowflake-resident stage via one of:

- `PUT file://driver.jar @CUSTOMER_STAGE` from SnowSQL/CLI (one-time, requires filesystem)
- `COPY FILES INTO @CUSTOMER_STAGE FROM @EXTERNAL_S3_STAGE FILES = ('driver.jar')` (storage integration)
- `COPY FILES INTO @CUSTOMER_STAGE FROM @GIT_REPO_STAGE FILES = ('drivers/driver.jar')` (Git integration)

The preflight for `connector.config_set_asset` confirms the JAR is present via `LIST '@{customer_stage}'`. If absent, **fail closed**. Do not direct the customer to `PUT` mid-flow; the bootstrap is the customer's responsibility before triggering the action.

---

## Shared Preflight (All Config-Edit Actions)

Run before any of the per-action templates below. The output of these queries is what fills the **Current state** field and the **before/after diff** in the [Confirmation Preview Format](action-guidelines.md#confirmation-preview-format).

### 0. Connector-Definition Support Gate (BLOCKING)

Run the canonical [Connector-Definition Support Gate](action-guidelines.md#connector-definition-support-gate-sub-check-of-hard-gate-2) before any other step in this file, including stage setup, `REMOVE`, and the `config.json` snapshot. The gate has two parts:

1. **Pre-gate (no SQL):** match `connector_type` from input or page context (e.g. `postgresql`) against the matrix's `connector_type alias` column. Today `postgresql` (`GA`) and `mysql` (`PrPr`) enter the lane; everything else fails closed before any SQL fires.
2. **Live check (1 SQL):** match the SQL result's `CONNECTOR_DEFINITION` (e.g. `OPENFLOW_POSTGRES_CDC`) against the matrix's `Connector definition` column for the same row.

If either check fails, stop entirely and route to the Openflow UI -- stage operations against an unsupported or legacy (non-SQL-managed) connector definition are pointless and would still consume RBAC and storage budget. The pre-gate alone does NOT prove Openflow SQL action support for postgres (legacy UI-only postgres connectors report the same `connector_type`); the live check is what actually proves SQL-managed status. The gate's live check captures the connector identity and current state used below.

After step 0 passes, run [Stage Bootstrap](#stage-bootstrap-after-support-gate-passes) exactly once for this action before cleaning or copying files.

### 1. Clean the working stage (BLOCKING -- both `config_set_property` AND `config_set_asset`)

```sql
REMOVE @{db}.{schema}.OPENFLOW_CONFIG_WORK_{session_suffix};
```

The per-session stage suffix prevents cross-session collisions, but the same session may have run a prior action that left files behind. `REMOVE` ensures the stage holds only what this action puts there. Running `REMOVE` against an empty stage is a no-op; against a populated one it clears every file. Skipping this step is the documented cause of the "stale JAR leaks into a property edit" failure mode.

### 2. Resolve connector FQN and parent runtime

Step 0's 1-SQL live check already returned the connector's STATUS, RUNTIME, CONNECTOR_DEFINITION, DEFAULT_VERSION_NAME, and (when the `DESCRIBE` form was used) LIVE_VERSION_LOCATION_URI / DEFAULT_VERSION_LOCATION_URI. If step 0 used `SHOW`, run `DESCRIBE OPENFLOW CONNECTOR {connector_fqn}` now to capture the live-version columns the snapshot needs. Then run `DESCRIBE OPENFLOW RUNTIME {runtime_fqn}` for parent state (NODE_TYPE, EXTERNAL_ACCESS_INTEGRATIONS, DEPLOYMENT). Capture `RUNTIME`, `CONNECTOR_DEFINITION`, `STATUS`, `DEFAULT_VERSION_NAME`, `DEFAULT_VERSION_LOCATION_URI`, `LIVE_VERSION_LOCATION_URI`.

### 3. Require STOPPED or DRAFT

Per the Openflow SQL Action Guide, `STATUS` may be one of `DRAFT | STOPPED | STARTING | RUNNING | STOPPING | DELETING | DELETED | UPDATING`. Config-edit actions allow STATUS in `{STOPPED, DRAFT}`:

- STATUS = `STOPPED` -- normal post-commit state. Editing creates a new live version that auto-promotes via the stage-promote path.
- STATUS = `DRAFT` -- post-create, pre-first-commit state where `DEFAULT_VERSION_NAME IS NULL` and `LIVE_VERSION_LOCATION_URI` is non-NULL. Editing the DRAFT's live `config.json` is the canonical way to fill in a fresh connector before its first COMMIT.

If STATUS is `RUNNING`, propose `connector.stop` as a separate, freshly previewed action first. Do NOT chain.

Refuse on any other STATUS (`STARTING`, `STOPPING`, `UPDATING`, `DELETING`, `DELETED`).

### 4. Snapshot the current `config.json`

Pull from the version stage that holds the active configuration:

- If `DEFAULT_VERSION_NAME` is non-NULL: pull from `DEFAULT_VERSION_LOCATION_URI`.
- If `DEFAULT_VERSION_NAME` is NULL (DRAFT): pull from `LIVE_VERSION_LOCATION_URI`.

```sql
COPY FILES INTO @{db}.{schema}.OPENFLOW_CONFIG_WORK_{session_suffix}
  FROM '{source_version_uri}'
  FILES = ('config.json');

SELECT $1::STRING AS config_text
FROM @{db}.{schema}.OPENFLOW_CONFIG_WORK_{session_suffix}/config.json
  (FILE_FORMAT => '{db}.{schema}.JSON_FF_RAW');
```

Capture the full text and the parsed VARIANT for diff rendering.

### 5. Apply the CDC retention banner if needed

If `CONNECTOR_DEFINITION` has `Family = CDC` in the [Openflow SQL Connector Support Matrix](connector-support-matrix.md#connector-capability-matrix), include the [CDC Retention Warning](action-guidelines.md#cdc-retention-warning-cross-cutting) in the preview's Expected impact. Config-edit actions are minutes-scale pauses; use the **Standard** tier by default.

### 6. Scan for credential patterns before rendering the diff

Both the `Current value` (snapshotted from the existing `config.json`) and the `Proposed value` (the customer-supplied new value) MUST pass the [Secret Leak Prevention](action-guidelines.md#secret-leak-prevention) denylist scan before being rendered into the preview. If either side matches the denylist, fail closed with the customer-facing wording from that section. Do NOT render the diff; do NOT execute the action. Customers misuse STRING_LITERAL fields for secrets often enough (connection URLs with embedded passwords, query-string apikeys) that this scan is mandatory.

### 7. Capture the rollback target (NEW)

```sql
SHOW VERSIONS IN OPENFLOW CONNECTOR {connector_fqn};
```

Capture the `LOCATION_URI` of the row currently marked `IS_DEFAULT = TRUE` (or the most recent `IS_LAST = TRUE` row if the connector is DRAFT and has never had a default). Call this `{pre_action_default_uri}`. **This is the version the connector will roll back TO if the action goes wrong** -- specifically, the version that is the default at preflight time, which the action is about to displace. It is NOT the oldest available version; older versions are visible in `SHOW VERSIONS` but are not the canonical undo target for this action.

Substitute `{pre_action_default_uri}` into the `Rollback:` line of the Confirmation Preview's Expected impact (see [Confirmation Preview Format](action-guidelines.md#confirmation-preview-format)). The customer sees the escape hatch BEFORE approving:

```
Customer-run rollback: ALTER OPENFLOW CONNECTOR {connector_fqn} ADD VERSION FROM '{pre_action_default_uri}';
```

This gives the customer a concrete rollback target before approval. The agent does not execute rollback `ADD VERSION FROM` itself; rollback remains customer-run guidance because arbitrary previous-version promotion is outside the agent allowlist.

---

## SECRET_REFERENCE: Not Supported

SECRET_REFERENCE properties (e.g. `Source.Source Database Password`) are **not editable** via either action in this file in MVP. The wizard sets a `providerId` UUID minted by the Openflow Control Plane that the agent has not validated as settable from SQL alone. If the customer asks to edit a secret reference, refuse the action and direct them to set the secret in the Openflow UI.

---

## connector.config_set_property -- Regex-targeted property edit

Set a single STRING_LITERAL property in `config.json` to a new value. Used for fields like Source Database User / URL / Publication Name, Snowflake Destination Database, Warehouse, Tuning fields, Migration fields.

For SECRET_REFERENCE see [SECRET_REFERENCE: Not Supported](#secret_reference-not-supported). For ASSET_REFERENCE use `connector.config_set_asset`.

### Mandatory step checklist (refusal rule)

Every `connector.config_set_property` action MUST execute this exact ordered sequence before issuing `ALTER OPENFLOW CONNECTOR ... ADD VERSION FROM '@stage'`. Skipping any step is a refusal-class bug, not an optimization.

1. Shared Preflight steps 0 - 7 (support gate, working stage clean, FQN resolution, STATUS gate, **`config.json` snapshot via `COPY FILES`**, CDC banner, secret-leak scan, rollback target capture).
2. **Per-action Preflight step 4: `REGEXP_COUNT` uniqueness gate** -- one SQL statement against the snapshotted text. Outcome `1` is the only proceed signal.
3. **Edit step: `REGEXP_REPLACE` rewrite** -- one `COPY INTO @stage/config.json FROM (SELECT REGEXP_REPLACE(...))` statement. The customer-supplied `new_value` MUST appear as a SQL string literal inside this statement.
4. **Post-edit validation gate: `TRY_PARSE_JSON` + `REGEXP_COUNT` + `REGEXP_SUBSTR`** -- one SQL statement that confirms `json_ok`, `post_edit_match_count = 1`, and `observed_new_value = new_value`.
5. `LIST '@working_stage'` -- exactly one row (`config.json`).
6. The gated `ALTER OPENFLOW CONNECTOR ... ADD VERSION FROM '@working_stage'` mutation, after the customer's confirmation reply.
7. Verification (`DESCRIBE OPENFLOW CONNECTOR`, `SHOW VERSIONS`, Post-Action Error Scan).

**Refusal rule (BLOCKING).** If steps 2 (`REGEXP_COUNT` against the snapshot) AND 3 (`REGEXP_REPLACE` writing back to the working stage) AND 4 (post-edit validation) have not all executed and returned the expected outcomes in this turn, the agent MUST NOT issue `ALTER OPENFLOW CONNECTOR ... ADD VERSION FROM '@stage'`. Promoting an unmodified `config.json` as a "new" version silently no-ops the customer's request and produces a deceptive SHOW VERSIONS row. The post-edit gate is also where regex roundtrip corruption is caught; bypassing it can corrupt production config. This refusal is enforced at the edit-template level for both `config_set_property` and `config_set_asset`.

If any of steps 2 - 4 is genuinely impossible in the current environment (e.g., the eval container reports the working-stage `COPY FILES` unsupported and the snapshot is empty), surface the failure verbatim and stop. Do not fall back to "promote the version stage as-is" -- that is the silent-no-op the refusal rule exists to prevent.

### Inputs

- `connector_fqn` (required)
- `property_path` (required) -- the full path inside `configuration[].properties`, e.g. `Source.Source Database User` or `Destination details.Snowflake Destination Database`. The path matches the JSON keys, including any spaces.
- `new_value` (required) -- string value to set. The agent quotes/escapes appropriately for embedding in JSON.

### Preflight

1. Run all of [Shared Preflight](#shared-preflight-all-config-edit-actions) (steps 0 through 7) before any per-action work below.
2. Validate the property exists in the snapshotted `config.json` and its `valueType` is `STRING_LITERAL`. If `valueType` is `ASSET_REFERENCE` or `SECRET_REFERENCE`, **stop** and route to the correct action (`connector.config_set_asset`, or surface SECRET limitation).
3. **Define the edit predicate (once, reused below).** The uniqueness gate, edit step, and post-edit gate MUST use the same regex literal so a `count = 1` outcome cannot pair with a `0` or `>1` rewrite.

   ```
   {edit_predicate} = '("<property-name>":\\{[^}]*"value":)("[^"]*"|null)'
   ```

   `<property-name>` is the customer-supplied property leaf name with each `\` and `"` escaped for the regex (Snowflake regex is RE2-style, so `.\[](){}|*+?^$` need backslash-escaping). The `\\{` is required because `{` is a regex metacharacter.

4. **Uniqueness gate.** Count occurrences of the edit predicate in the snapshotted text:

   ```sql
   SELECT REGEXP_COUNT($1::STRING, {edit_predicate}) AS occurrence_count
   FROM @{db}.{schema}.OPENFLOW_CONFIG_WORK_{session_suffix}/config.json
     (FILE_FORMAT => '{db}.{schema}.JSON_FF_RAW');
   ```

   `configuration[]` is an array of step blocks and the same property name CAN appear in multiple steps (different scopes within the same connector configuration). The regex used in the edit step is global -- it would silently rewrite every occurrence.

   - `0` -> **fail closed**. Property is not present in the current config (or the wizard's key ordering does not put `value` immediately after the property block opener). Surface this and stop.
   - `1` -> proceed.
   - `>1` -> **fail closed**. Multiple steps in `configuration[]` use the same property name. The agent does not have a safe way to disambiguate from SQL alone (would require step-block path resolution that is not part of MVP). Surface the count and the step-block names from the snapshot, and direct the customer to the Openflow UI wizard for this edit.
5. Compute the replacement: `\\1"<json-escaped-new-value>"` (use `null` literal if the customer requested clearing). Single quotes inside `<new-value>` must be doubled for the SQL string literal; double quotes and backslashes must be JSON-escaped before the doubling.
6. Compute the **before/after diff** of the target value for the preview. Render only the property path plus scalar `Current value` and `Proposed value` lines. Do not render the full `properties.<key>` object; sibling fields can contain plaintext secrets.

### Edit step

```sql
COPY INTO @{db}.{schema}.OPENFLOW_CONFIG_WORK_{session_suffix}/config.json
FROM (
  SELECT REGEXP_REPLACE(
    $1::STRING,
    {edit_predicate},
    '\\1"{json_escaped_new_value}"'
  )
  FROM @{db}.{schema}.OPENFLOW_CONFIG_WORK_{session_suffix}/config.json
    (FILE_FORMAT => '{db}.{schema}.JSON_FF_RAW')
)
FILE_FORMAT = (TYPE = CSV COMPRESSION = NONE RECORD_DELIMITER = NONE FIELD_DELIMITER = NONE FIELD_OPTIONALLY_ENCLOSED_BY = NONE)
OVERWRITE = TRUE
SINGLE = TRUE;
```

`FIELD_OPTIONALLY_ENCLOSED_BY = NONE` is mandatory; otherwise the unload may quote double quotes inside the JSON and corrupt the file.

`{edit_predicate}` is the regex literal defined in Preflight step 3 -- reuse it verbatim. Do NOT rewrite a near-miss variant in the edit step; the count and the rewrite must use the same predicate.

### Post-edit validation gate (BLOCKING -- run before any `ADD VERSION FROM`)

The regex roundtrip can corrupt the rewritten file when the property value contains `}`, escaped `\"`, or non-compact whitespace. Refuse to promote unless ALL three checks pass against the rewritten file in the working stage:

```sql
SELECT
  TRY_PARSE_JSON($1::STRING) IS NOT NULL                              AS json_ok,
  REGEXP_COUNT($1::STRING, {edit_predicate})                          AS post_edit_match_count,
  REGEXP_SUBSTR(
    $1::STRING,
    '"<property-name>":\\{[^}]*"value":"([^"]*)"',
    1, 1, 'e', 1
  )                                                                   AS observed_new_value
FROM @{db}.{schema}.OPENFLOW_CONFIG_WORK_{session_suffix}/config.json
  (FILE_FORMAT => '{db}.{schema}.JSON_FF_RAW');
```

- `json_ok = FALSE` -> **fail closed**. The rewrite produced syntactically invalid JSON. Do NOT issue `ADD VERSION FROM`. Surface the failure verbatim to the customer and explain that the working stage's `config.json` is left intact for inspection.
- `post_edit_match_count != 1` -> **fail closed**. The regex matched zero or multiple times after the edit; semantics drifted from the gate. Do NOT promote.
- `observed_new_value != {expected_new_value}` -> **fail closed**. The rewrite landed but did not contain the requested value. Do NOT promote.

If the customer requested clearing (`null` literal replacement), assert `observed_new_value IS NULL OR observed_new_value = ''` instead of equality with a string.

This gate exists because the regex `[^}]*` and `[^"]*` character classes break on:
- JSON values containing `}` (e.g., JDBC URLs with `?options={a=1}`).
- JSON-escaped quotes (`\"`) inside string values.
- Pretty-printed `config.json` where keys appear before `value` (e.g., the wizard orders `valueType` first for ASSET_REFERENCE).
- CSV-roundtrip whitespace normalization that does not preserve byte-identical input.

When the gate trips, the working stage is left intact (do NOT auto-promote, do NOT auto-rollback). The customer can inspect the working stage's `config.json` via `LIST '@<stage>'` + `SELECT $1::STRING FROM @<stage>/config.json (FILE_FORMAT => '{db}.{schema}.JSON_FF_RAW')` and decide to retry, fix manually, or use the Openflow UI wizard.

> **Roadmap.** This gate is a mitigation, not a fix; the regex still has known failure modes. The follow-up to replace this pipeline with a Snowflake VARIANT-native edit (`PARSE_JSON` + `LATERAL FLATTEN` + `OBJECT_INSERT` + `TO_JSON`) is staged in `.claude_workspace/openflow-config-edit-variant-design.md`. Until validated, the gate is the safety contract.

### Verify the edit landed in the working stage (read-only, advisory)

This is a separate, customer-facing read used to populate the **Proposed value** line of the preview. It does NOT replace the post-edit gate above -- both run.

```sql
SELECT REGEXP_SUBSTR(
  $1::STRING,
  '"<property-name>":\\{[^}]*"value":"([^"]*)"',
  1, 1, 'e', 1
) AS property_value_after
FROM @{db}.{schema}.OPENFLOW_CONFIG_WORK_{session_suffix}/config.json
  (FILE_FORMAT => '{db}.{schema}.JSON_FF_RAW');
```

Echo only `property_value_after` in the preview as the **Proposed value** line. If it does not match what was intended, stop and surface the mismatch without printing the surrounding JSON object.

### Verify stage contents (BLOCKING -- run before `ADD VERSION FROM`)

```sql
LIST '@{db}.{schema}.OPENFLOW_CONFIG_WORK_{session_suffix}';
```

The result MUST contain exactly one row: `config.json`. If any other file is present (e.g., a stale JAR from a prior `connector.config_set_asset` run in the same session), **fail closed**. Do NOT proceed to `ADD VERSION FROM`. Surface the unexpected files verbatim and tell the customer to re-enter the action so the working stage starts clean.

### Proposed SQL (the gated mutation)

```sql
ALTER OPENFLOW CONNECTOR {connector_fqn}
  ADD VERSION FROM '@{db}.{schema}.OPENFLOW_CONFIG_WORK_{session_suffix}';
```

### Expected impact

- A new connector version is created from the working stage's contents (`config.json` only). It auto-promotes to default; previous default is preserved as a non-default version (visible via `SHOW VERSIONS`).
- Connector transitions `STOPPED -> UPDATING -> STOPPED`.
- For CDC connectors: include the [CDC Retention Warning](action-guidelines.md#cdc-retention-warning-cross-cutting).
- Reversible: yes, see [Rollback (Customer-Run)](#rollback-customer-run) below for the templated procedure. The agent does NOT auto-stage the previous version; rollback is customer-run guidance.

### Verification

```sql
DESCRIBE OPENFLOW CONNECTOR {connector_fqn};
SHOW VERSIONS IN OPENFLOW CONNECTOR {connector_fqn};
```

Confirm:
- `STATUS = 'STOPPED'`
- `LIVE_VERSION_LOCATION_URI` is now NULL
- `DEFAULT_VERSION_NAME` advanced and points to the working stage as `SOURCE_LOCATION_URI`

Then run the [Post-Action Error Scan](connector-diagnostics.md#post-action-error-scan) for the runtime namespace bounded to the last 2 minutes. If any `ERROR` rows return, surface them verbatim and provide the customer-run rollback guidance from [Rollback (Customer-Run)](#rollback-customer-run), populated with the rollback target captured in Shared Preflight step 7. Do not execute rollback SQL from the agent. Zero rows = the action succeeded; the agent MAY propose `connector.start` as a fresh, separately-confirmed next step.

---

## connector.config_set_asset -- Set ASSET_REFERENCE assetIds

Wire a customer-staged driver JAR into the connector's config. The JAR must already exist on a customer-named stage; the agent does not upload binaries.

### Mandatory step checklist (refusal rule)

Same shape as `connector.config_set_property`. Every `connector.config_set_asset` action MUST execute this exact ordered sequence before issuing `ALTER OPENFLOW CONNECTOR ... ADD VERSION FROM '@stage'`:

1. Shared Preflight steps 0 - 7.
2. Per-action Preflight step 4: `REGEXP_COUNT` uniqueness gate against the snapshotted `config.json`.
3. Per-action Preflight step 5: `LIST '@customer_stage'` JAR existence + exact-basename match.
4. Stage assemble step 1 - 3: seed working stage with `config.json`, copy the JAR, then `REGEXP_REPLACE` to set `assetIds`. The customer-supplied `jar_filename` MUST appear as a SQL string literal inside the `REGEXP_REPLACE`.
5. Post-edit validation gate: `TRY_PARSE_JSON` + `REGEXP_COUNT = 1` + `observed_asset_ids = '["{jar_filename}"]'`.
6. Stage assemble step 4: `LIST '@working_stage'` -- exactly two rows (`config.json` and the JAR).
7. The gated `ALTER OPENFLOW CONNECTOR ... ADD VERSION FROM '@working_stage'` mutation, after the customer's confirmation reply.
8. Verification (`DESCRIBE`, `SHOW VERSIONS`, `LIST` new version stage, Post-Action Error Scan).

**Refusal rule (BLOCKING).** Same as `connector.config_set_property`: if steps 2 (uniqueness `REGEXP_COUNT`) AND 4 (`REGEXP_REPLACE` writing back) AND 5 (post-edit validation) have not all executed and returned the expected outcomes in this turn, the agent MUST NOT issue `ADD VERSION FROM`.

### Inputs

- `connector_fqn` (required)
- `property_path` (required) -- the ASSET_REFERENCE property, typically `Source.Source Database Driver` for CDC connectors.
- `customer_stage` (required) -- fully qualified stage name where the JAR lives, e.g. `@CUSTOMER.SHARED.DRIVERS`.
- `jar_filename` (required) -- the basename of the JAR in `customer_stage`, e.g. `postgresql-42.7.10.jar`. This becomes the value placed in `assetIds`. **Customer-supplied; the agent does NOT infer the filename from the connector definition or from the matrix's `Driver ASSET_REFERENCE property` column.** Customers often have multiple JAR variants on the same stage (e.g. `postgresql-42.7.10.jar`, `postgresql-42.7.10-source.jar`, `postgresql-42.7.10-javadoc.jar`); only the runtime JAR is correct, and only the customer can identify it by exact basename.

### Preflight

1. Run all of [Shared Preflight](#shared-preflight-all-config-edit-actions) (steps 0 through 7) before any per-action work below.
2. Confirm the property's `valueType` is `ASSET_REFERENCE`. If it is `STRING_LITERAL` or `SECRET_REFERENCE`, route to the correct action.
3. **Define the edit predicate (once, reused below).** The uniqueness gate, edit step, and post-edit gate MUST use the same regex literal so a `count = 1` outcome cannot pair with a `0` or `>1` rewrite. The predicate matches both the `null` case (driver missing) and the existing-array case (driver already wired):

   ```
   {edit_predicate} = '("<asset-property-name>":\\{[^}]*"assetIds":)(null|\\[[^\\]]*\\])'
   ```

   `<asset-property-name>` is the customer-supplied property leaf name with regex metacharacters escaped. The trailing alternation `(null|\\[[^\\]]*\\])` covers both states the field can be in; the replacement always normalizes to a single-element array.

4. **Uniqueness gate.** Count occurrences of the edit predicate in the snapshotted text:

   ```sql
   SELECT REGEXP_COUNT($1::STRING, {edit_predicate}) AS occurrence_count
   FROM @{db}.{schema}.OPENFLOW_CONFIG_WORK_{session_suffix}/config.json
     (FILE_FORMAT => '{db}.{schema}.JSON_FF_RAW');
   ```

   Same rationale as `connector.config_set_property`: the regex used in the edit step rewrites every occurrence; multiple matches must be disambiguated outside SQL.

   - `0` -> **fail closed**. Property is not present.
   - `1` -> proceed.
   - `>1` -> **fail closed**. Surface the step-block names from the snapshot and direct the customer to the Openflow UI wizard for this edit.
5. Confirm the JAR exists on the customer stage with **exact basename match**:

   ```sql
   LIST '@{customer_stage}';
   ```

   `LIST` returns rows whose `name` column includes the stage prefix and any subdirectories. Sample output for a stage that holds the driver plus an unrelated file in a subfolder:

   | name | size | md5 | last_modified |
   |---|---|---|---|
   | `customer_drivers/postgresql-42.7.10.jar` | 1137016 | ... | ... |
   | `customer_drivers/old/postgresql-42.6.0.jar` | 1098240 | ... | ... |

   For each row, take the basename (split the `name` column on `/`, last component -- e.g. `customer_drivers/postgresql-42.7.10.jar` -> `postgresql-42.7.10.jar`). Compare case-sensitively against `{jar_filename}`.

   - **Exactly one row whose basename equals `{jar_filename}`** -> proceed.
   - **Zero exact-match rows** -> **fail closed**. Tell the customer the JAR is not on the stage and stop. Do not propose the action. Do not fall back to substring/prefix matching.
   - **Multiple rows whose basename CONTAINS `{jar_filename}` as a substring or prefix** (e.g., `postgresql-42.7.10.jar`, `postgresql-42.7.10-source.jar`, `postgresql-42.7.10-javadoc.jar`) -> **fail closed**. Quote the matching rows verbatim and ask the customer which exact basename to wire. Only the runtime JAR works; `-source` and `-javadoc` archives will load but the connector will fail at startup with `ClassNotFoundException`.
   - **The exact-match row's basename is in a subdirectory** (e.g., `customer_drivers/old/postgresql-42.7.10.jar`) -> the basename matches but the subsequent `COPY FILES INTO @working_stage FROM @{customer_stage} FILES = ('{jar_filename}')` matches by filename within the source root and will not find a JAR nested in a subfolder. **Fail closed** and ask the customer to either move the JAR to the customer stage's root or supply a different stage path that already roots the JAR.

   Do NOT proceed on a partial / fuzzy match. The agent's only safe match is the customer-supplied exact basename at the customer stage's root.
6. Build the before/after diff of the `assetIds` field for the preview. Render only the property path plus `Current assetIds` and `Proposed assetIds`; do not render the full property object.

### Stage assemble step

The new connector version stage will hold both `config.json` AND the JAR. Step 0 of Shared Preflight already cleared the working stage, so this section starts from a known-empty state.

```sql
-- 1. seed working stage with current config (Shared Preflight step 3 may have done this;
--    re-run only if the working stage was cleared between then and now)
COPY FILES INTO @{db}.{schema}.OPENFLOW_CONFIG_WORK_{session_suffix}
  FROM '{source_version_uri}'
  FILES = ('config.json');

-- 2. copy the JAR alongside config.json
COPY FILES INTO @{db}.{schema}.OPENFLOW_CONFIG_WORK_{session_suffix}
  FROM @{customer_stage}
  FILES = ('{jar_filename}');

-- 3. edit config.json to set assetIds (works whether prior value was null or an existing array)
COPY INTO @{db}.{schema}.OPENFLOW_CONFIG_WORK_{session_suffix}/config.json
FROM (
  SELECT REGEXP_REPLACE(
    $1::STRING,
    {edit_predicate},
    '\\1["{jar_filename}"]'
  )
  FROM @{db}.{schema}.OPENFLOW_CONFIG_WORK_{session_suffix}/config.json
    (FILE_FORMAT => '{db}.{schema}.JSON_FF_RAW')
)
FILE_FORMAT = (TYPE = CSV COMPRESSION = NONE RECORD_DELIMITER = NONE FIELD_DELIMITER = NONE FIELD_OPTIONALLY_ENCLOSED_BY = NONE)
OVERWRITE = TRUE
SINGLE = TRUE;

-- 4. confirm exactly the expected files are present (no leftovers)
LIST '@{db}.{schema}.OPENFLOW_CONFIG_WORK_{session_suffix}';
-- The result MUST contain exactly two rows: `config.json` and `{jar_filename}`.
-- If any other file is present, fail closed -- do not proceed to ADD VERSION FROM.
```

`{edit_predicate}` is the regex literal defined in Preflight step 3 -- reuse it verbatim. The same predicate covers both the `null`-replacement and the array-replacement cases, so there is no separate variant pattern.

### Post-edit validation gate (BLOCKING -- run before any `ADD VERSION FROM`)

The regex roundtrip can corrupt the rewritten file when the property block has unexpected key ordering or the surrounding JSON contains pathological characters. Refuse to promote unless ALL three checks pass against the rewritten file in the working stage:

```sql
SELECT
  TRY_PARSE_JSON($1::STRING) IS NOT NULL                              AS json_ok,
  REGEXP_COUNT($1::STRING, {edit_predicate})                          AS post_edit_match_count,
  REGEXP_SUBSTR(
    $1::STRING,
    '"<asset-property-name>":\\{[^}]*"assetIds":(\\[[^\\]]*\\])',
    1, 1, 'e', 1
  )                                                                   AS observed_asset_ids
FROM @{db}.{schema}.OPENFLOW_CONFIG_WORK_{session_suffix}/config.json
  (FILE_FORMAT => '{db}.{schema}.JSON_FF_RAW');
```

- `json_ok = FALSE` -> **fail closed**. Do NOT issue `ADD VERSION FROM`. Surface the failure verbatim.
- `post_edit_match_count != 1` -> **fail closed**. The predicate no longer matches exactly once after the edit.
- `observed_asset_ids != '["{jar_filename}"]'` -> **fail closed**. The rewrite landed but did not contain the expected single-element array.

When the gate trips, the working stage is left intact for inspection (do NOT auto-promote, do NOT auto-rollback, do NOT auto-retry). See the equivalent gate description under `connector.config_set_property` for the customer-facing failure path.

### Proposed SQL (the gated mutation)

```sql
ALTER OPENFLOW CONNECTOR {connector_fqn}
  ADD VERSION FROM '@{db}.{schema}.OPENFLOW_CONFIG_WORK_{session_suffix}';
```

### Expected impact

- A new connector version is created from the working stage. The new version stage will contain both `config.json` AND `{jar_filename}` at its root.
- `config.json` references `{jar_filename}` via `assetIds`.
- Connector transitions `STOPPED -> UPDATING -> STOPPED`.
- For CDC connectors: include the [CDC Retention Warning](action-guidelines.md#cdc-retention-warning-cross-cutting).
- Reversible: yes, see [Rollback (Customer-Run)](#rollback-customer-run) below for the templated procedure.

### Verification

```sql
DESCRIBE OPENFLOW CONNECTOR {connector_fqn};
SHOW VERSIONS IN OPENFLOW CONNECTOR {connector_fqn};
LIST '{new_default_version_location_uri}';
```

`LIST` MUST show the JAR at the expected basename in the new default version stage. Then run the [Post-Action Error Scan](connector-diagnostics.md#post-action-error-scan) for the runtime namespace bounded to the last 2 minutes. If any `ERROR` rows return (e.g., `ClassNotFoundException` because the JAR is the wrong variant), surface them verbatim and provide the customer-run rollback guidance from [Rollback (Customer-Run)](#rollback-customer-run), populated with the rollback target captured in Shared Preflight step 7. Do not execute rollback SQL from the agent. Zero rows = success; the agent MAY propose `connector.start` as a fresh action.

---

## Rollback (Customer-Run)

If the [Post-Action Error Scan](connector-diagnostics.md#post-action-error-scan) returns `ERROR` rows after a `connector.config_set_property` or `connector.config_set_asset` action, the new default version is broken but already promoted; the agent does NOT auto-rollback in MVP. The customer can roll back to the previous version with these three customer-run steps. Surface them verbatim with the customer's actual values substituted; do NOT execute them from the agent (the rollback `ADD VERSION FROM` targets a customer-named stage, which is denylisted as an agent action).

```sql
-- 1. Find the version to roll back to (the prior default before the failed change).
SHOW VERSIONS IN OPENFLOW CONNECTOR {connector_fqn};
-- Identify the row whose CREATED_ON is just before the failed action's timestamp.
-- That row's IS_DEFAULT was TRUE at the time. Capture its LOCATION_URI as
-- {prior_version_location_uri}.

-- 2. Seed a fresh customer-managed stage with the prior version's contents.
CREATE STAGE IF NOT EXISTS {db}.{schema}.OPENFLOW_CONFIG_ROLLBACK
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');
COPY FILES INTO @{db}.{schema}.OPENFLOW_CONFIG_ROLLBACK
  FROM '{prior_version_location_uri}'
  FILES = ('config.json');

-- If the prior version had ASSET_REFERENCE files (e.g., a JAR), enumerate and
-- copy them too. Otherwise the rollback ships a config.json that references a
-- JAR that does not exist in the new version stage and the connector will fail
-- to start with ClassNotFoundException.
LIST '{prior_version_location_uri}';
-- For each non-config.json file FOO.jar:
COPY FILES INTO @{db}.{schema}.OPENFLOW_CONFIG_ROLLBACK
  FROM '{prior_version_location_uri}'
  FILES = ('FOO.jar');

-- 3. Promote the rollback stage as the new default.
ALTER OPENFLOW CONNECTOR {connector_fqn}
  ADD VERSION FROM '@{db}.{schema}.OPENFLOW_CONFIG_ROLLBACK';
```

After step 3, run the [Post-Action Error Scan](connector-diagnostics.md#post-action-error-scan) again to confirm the rolled-back default does not produce new errors. If the connector should be running, the customer (not the agent) issues `ALTER OPENFLOW CONNECTOR ... START`.

Tell the customer this is a rollback only; if they want to retry the original change, they re-do the action from a clean working stage rather than re-running this rollback procedure in reverse.

---

## After Any Successful Action

- Report the before/after values from `SHOW VERSIONS` (new version name, source location URI, `IS_DEFAULT`).
- Run the [Post-Action Error Scan](connector-diagnostics.md#post-action-error-scan). If no errors appear, the agent MAY propose `connector.start` as a fresh, separately-confirmed action. If errors appear, surface them and provide customer-run rollback guidance from Shared Preflight step 7.
- Drop back to diagnostic mode for any further work. Never chain a second config-edit mutation in the same response without a fresh user request and a fresh preview.
- After the verification step succeeds, the agent MAY drop the working stage with `DROP STAGE IF EXISTS {db}.{schema}.OPENFLOW_CONFIG_WORK_{session_suffix};`. The stage is per-session and never reused, so leaving it on best-effort cleanup is acceptable but explicit drop is preferred when the action lane ends cleanly. Do NOT reuse the stage across sessions; the next agent session generates a fresh `{session_suffix}`.
