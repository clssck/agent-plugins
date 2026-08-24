---
name: openflow-observability-connector-diagnostics
description: Read-only Openflow SQL diagnostics for connectors and runtimes -- SHOW OPENFLOW CONNECTOR DEFINITIONS, SHOW VERSIONS, SHOW GRANTS ON OPENFLOW RUNTIME, DRAFT-connector fast-path, config snapshot, post-action error scan. Tier 2 only; load when a connector or runtime SQL diagnostic is needed.
---

# Openflow SQL Diagnostics (Read-Only)

> Customer-facing name: **Openflow SQL diagnostics**.

This file contains diagnostics that do not mutate Openflow runtime or connector objects. Most commands are read-only. The Connector Config Snapshot uses session-scoped scratch SQL (`CREATE TEMPORARY STAGE`, `CREATE TEMPORARY FILE FORMAT`, `COPY FILES INTO @temp_stage`) to inspect `config.json`; those writes are governed by the [Scratch-Stage Preflight Exception](action-guidelines.md#scratch-stage-preflight-exception). All Openflow object mutations are governed by [action-guidelines.md](action-guidelines.md) and the action templates.

Load this file when:

- A controller service is `INVALID` or `ENABLING` and the connector won't start.
- A connector appears stuck in `DRAFT` or `Edits not applied`.
- A privilege error from a SQL action needs evidence-gathering before loading `admin-ddl-assist.md`.
- The customer asks "is this connector definition available in my account?" or "what version of this connector is live?"
- Post-action validation is needed after a gated SQL action lands.
- Historical context is needed (last resumed, last altered, recently deleted) -- pair with [account-usage.md](account-usage.md).

---

## Post-Action Error Scan

After a gated SQL action lands (`connector.start`, `connector.stop`, `connector.commit`, `connector.abort`, `connector.config_set_property`, `connector.config_set_asset`), the agent MUST run this scan to confirm no new errors appeared in the runtime namespace within the post-action 2-minute window. If any rows return, surface them verbatim and provide customer-run recovery or rollback guidance. Do not execute rollback SQL from the agent. Zero rows = action succeeded.

```sql
SELECT timestamp, severity_text,
       record_attributes:"logger_name"::STRING AS logger,
       record_attributes:"error.message"::STRING AS error_message
FROM {event_table}
WHERE resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND timestamp >= DATEADD(second, -120, CURRENT_TIMESTAMP())
  AND severity_text = 'ERROR'
ORDER BY timestamp DESC
LIMIT 50;
```

The 2-minute window is intentional: longer than typical `UPDATING` / `STARTING` transitions (~10-30 seconds) but short enough that pre-existing errors from before the action don't pollute the result. If the customer's session captured a different `{event_table}` or `{namespace}`, substitute their values; do not invent.

This scan is the canonical post-action validator for every gated SQL action in the skill. It is also the diagnostic that named-error-pattern recovery guidance branches off of (see Triage Router in `SKILL.md`).

---

## SHOW OPENFLOW CONNECTOR DEFINITIONS

Lists the connector definitions installed in the account. Read-only.

### Syntax

```sql
SHOW OPENFLOW CONNECTOR DEFINITIONS [ LIKE '%{name_pattern}%' ];
```

### Output columns

| Column        | Type    | Notes                                                                  |
| ------------- | ------- | ---------------------------------------------------------------------- |
| `NAME`        | VARCHAR | Definition name (e.g. `POSTGRES_CDC`, `SALESFORCE_BULK_API`).          |
| `PROVIDER`    | VARCHAR | Provider of the connector (`Snowflake`, `Adobe`, etc.).                |
| `VERSION`     | VARCHAR | Definition version.                                                    |
| `DESCRIPTION` | VARCHAR | Short description.                                                     |

### Use cases

- **"Why can't I create a connector of type X?"** -- if `SHOW OPENFLOW CONNECTOR DEFINITIONS LIKE '%X%'` returns zero rows, the definition isn't installed for this account/role. Direct the customer to the Openflow UI's connector catalog or to Snowflake support.
- **Confirming definition naming** before previewing any future `CREATE OPENFLOW CONNECTOR ... FROM DEFINITION ...` guidance (note: `CREATE OPENFLOW CONNECTOR` is denylisted as an agent action -- this is customer-run guidance only).

---

## SHOW VERSIONS IN OPENFLOW CONNECTOR

Lists the version history of a connector's configuration. Read-only.

### Syntax

```sql
SHOW VERSIONS IN OPENFLOW CONNECTOR {connector_fqn};
```

### Output columns (relevant subset)

| Column                  | Type      | Notes                                                                                                                |
| ----------------------- | --------- | -------------------------------------------------------------------------------------------------------------------- |
| `CREATED_ON`            | TIMESTAMP | When the version was created.                                                                                        |
| `NAME`                  | VARCHAR   | Auto-generated version name (e.g. `version$2`).                                                                      |
| `ALIAS`                 | VARCHAR   | Optional user-provided alias.                                                                                        |
| `LOCATION_URI`          | VARCHAR   | Stage URI for the version's files.                                                                                   |
| `IS_DEFAULT`            | BOOLEAN   | Whether this is the current default (committed) version.                                                             |
| `IS_LIVE`               | BOOLEAN   | Whether this is the current live (editable, uncommitted) version.                                                    |
| `IS_FIRST` / `IS_LAST`  | BOOLEAN   | Position markers.                                                                                                    |
| `OWNER`                 | VARCHAR   | Role that owns the version.                                                                                          |
| `COMMENT`               | VARCHAR   | Optional comment.                                                                                                    |
| `SOURCE_LOCATION_URI`   | VARCHAR   | If created `FROM '<location>'`, the source.                                                                          |
| `GIT_COMMIT_HASH`       | VARCHAR   | Git commit, if pulled from a git stage.                                                                              |

### Diagnostic patterns

| Row pattern                                       | What it means                                                                                                                                                                                              |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Exactly one row, `IS_DEFAULT = TRUE`, no live row | Steady state: a default version is committed, no in-flight edits.                                                                                                                                          |
| One row `IS_LIVE = TRUE`, no `IS_DEFAULT = TRUE` | Connector is in `DRAFT` -- no default version has ever been committed. See [DRAFT Connector Fast-Path](#draft-connector-fast-path).                                                                          |
| One row `IS_DEFAULT = TRUE` AND one row `IS_LIVE = TRUE` | "Edits not applied" -- a live version was created from the default but not yet committed or aborted. The customer must `ALTER ... COMMIT` (apply) or `ALTER ... ABORT` (discard) to clear the state. |

Both `ALTER ... COMMIT` and `ALTER ... ABORT` are now MVP-allowlisted as gated agent actions (`connector.commit`, `connector.abort` -- see [connector-actions.md](connector-actions.md)). If the user has explicitly asked for the apply or discard, route through the [Openflow SQL Action Mode](../../SKILL.md#openflow-sql-action-mode) gates rather than emitting customer-run guidance. If the user only asked to understand the state, stop at the diagnosis and surface the action as a candidate to confirm.

---

## SHOW GRANTS ON OPENFLOW RUNTIME

Privilege-gap evidence for runtime-scoped actions and for the `admin-ddl-assist.md` lane. Read-only.

### Syntax

```sql
SHOW GRANTS ON OPENFLOW RUNTIME {runtime_fqn};
```

Returns one row per grant, including the `privilege` (`OWNERSHIP`, `MONITOR`, `OPERATE`, `USAGE`), the `grantee_name`, and the `granted_by` role.

### Use cases

- **Privilege error from an Openflow SQL action** (`Insufficient privileges to operate on ...`): run this query to enumerate which roles already have which privileges on the target runtime. Pair with the Openflow privilege model -- `OPERATE` is required for `RESTART` / `RESUME` / `SUSPEND`, `OWNERSHIP` is required for `SET` / `RENAME` / `TERMINATE` / `DROP`, `MONITOR` is required for `SHOW` / `DESCRIBE`.
- **Customer-run `GRANT` guidance**: name the exact missing privilege and the role that should hold it; do not silently `GRANT` (admin DDL is out of MVP).

Surface the rows verbatim; do not summarize "no one has OPERATE" without showing which roles do hold privileges.

---

## DRAFT Connector Fast-Path

Use when a connector is `STOPPED` and the customer reports it "won't start" or "won't apply edits". Avoids generic startup investigation when the actual problem is missing default-version commit.

### Step 1: Describe the connector

```sql
DESCRIBE OPENFLOW CONNECTOR {connector_fqn};
```

### Step 2: Apply the fast-path rule

| `DEFAULT_VERSION_NAME` | `LIVE_VERSION_LOCATION_URI` | Diagnosis                                                                                                                                                                              |
| ---------------------- | --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| NULL                   | non-NULL                    | **DRAFT.** No default version has ever been committed. The customer must upload a valid `config.json` to the live stage and run `ALTER OPENFLOW CONNECTOR {connector_fqn} COMMIT`.     |
| non-NULL               | non-NULL                    | **Edits not applied.** A live version exists alongside a default. The customer must either `ALTER ... COMMIT` (apply edits) or `ALTER ... ABORT` (discard edits) to clear the state.   |
| non-NULL               | NULL                        | Steady state. DRAFT is not the issue -- continue with normal startup investigation in [connector-shared-generic.md](../connectors/connector-shared-generic.md).                            |

### Step 3: Confirm with `SHOW VERSIONS`

For both the **DRAFT** and **Edits not applied** rows above, **run `SHOW VERSIONS IN OPENFLOW CONNECTOR {connector_fqn}` and report the `IS_LIVE` / `IS_DEFAULT` row pattern in the diagnosis.** This is the durable, machine-checkable confirmation the `DESCRIBE` columns describe -- the customer's runbook expects to see the version-state evidence, not just the column-level inference.

```sql
SHOW VERSIONS IN OPENFLOW CONNECTOR {connector_fqn};
```

Apply the [SHOW VERSIONS diagnostic patterns](#show-versions-in-openflow-connector) above and surface the relevant row pattern in the diagnosis (e.g., "one row `IS_LIVE = TRUE`, no `IS_DEFAULT = TRUE` -> DRAFT").

Only the **Steady state** row (`DEFAULT_VERSION_NAME` non-NULL, `LIVE_VERSION_LOCATION_URI` NULL) skips this confirmation -- DRAFT is not the issue and the agent moves to generic startup investigation.

### Step 4: Scope errors before committing

Before suggesting `ALTER ... COMMIT`, run a Recent Error Logs scan scoped to the runtime namespace for the last hour and inspect the connector's snapshotted `config.json` via [Connector Config Snapshot](#connector-config-snapshot-read-only). If any errors name missing required properties, missing assets, or the connector's stage shows `"value": null` / `"assetIds": null` on a required field, surface those first -- the commit will land but the connector will not start until those are fixed.

### Stuck-Driver Fast-Path (assetIds is null)

A specific sub-case of Step 4: the [Connector Config Snapshot](#connector-config-snapshot-read-only) shows the `Source Database Driver` ASSET_REFERENCE has `"assetIds": null` AND/OR Recent Error Logs (scoped to the runtime namespace) report `ClassNotFoundException` referencing the JDBC driver class.

Trigger phrase to offer the customer (always present BOTH paths so they can pick): "Your connector is missing the JDBC driver. There are two ways to fix this:

1. **Upload the JAR to a Snowflake stage and let me wire it in.** Run `PUT file://driver.jar @<DB>.<SCHEMA>.<STAGE>` from SnowSQL, then tell me the fully-qualified stage name (`<DB>.<SCHEMA>.<STAGE>`) and the JAR's exact basename. I'll set `assetIds` and promote a new connector version with one `ALTER OPENFLOW CONNECTOR ... ADD VERSION FROM` after you confirm.
2. **Use the connector's guided install wizard in Snowsight.** This connector is SQL-managed, so the driver is uploaded directly inside the wizard (open the connector's configure page, follow the prompts, attach the JAR when asked). You do NOT need to touch a parameter context for SQL-managed connectors -- that path is for legacy non-SQL-managed connectors only.

Which would you like? If you confirm option 1 and give me the fully-qualified stage and JAR basename, I'll preview the before/after diff and the exact SQL before doing anything."

If the customer picks option 1 and confirms a fully-qualified stage path plus exact JAR basename, proceed through the [`connector.config_set_asset`](connector-config-edit.md#connectorconfig_set_asset----set-asset_reference-assetids) preflight as normal. If they pick option 2 or cannot identify which JAR to use, stop and direct them to the guided install wizard; do not preview the action.

- Action candidate: `connector.config_set_asset` ([connector-config-edit.md](connector-config-edit.md#connectorconfig_set_asset----set-asset_reference-assetids))
- Pre-stage requirement: the JAR must already exist on a customer-named stage. The agent does NOT upload binaries. If the customer has not staged the JAR yet, surface the prerequisite and stop -- direct them to `PUT file://driver.jar @<their_stage>` from SnowSQL/CLI, or to the Openflow UI wizard for the upload path.
- Do **not** offer when:
  - `SHOW OPENFLOW CONNECTORS` returns zero rows for the connector (legacy or invisible) -- guide via UI instead.
  - The connector is BYOC -- default to UI guidance for parameter-context asset uploads.
  - The customer cannot identify which JAR (version, vendor) is required -- consult [Required JDBC drivers by connector](../connectors/connector-shared-generic.md#missing-jdbc-driver--parameter-context-assets) first.
- After successful application: the connector lands in `STOPPED` with a new default version. Propose `connector.start` as a separately-confirmed next step (do not chain).

### Diagnosis vs gated action

This file does not mutate Openflow objects. The DRAFT and "Edits not applied" cases produce a finding plus a recommended next step; the next step itself is a separately-gated SQL action:

- Apply staged edits -> `connector.commit` ([connector-actions.md](connector-actions.md#connectorcommit----apply-staged-config-edits))
- Discard staged edits -> `connector.abort` ([connector-actions.md](connector-actions.md#connectorabort----discard-staged-config-edits))
- Fill out a DRAFT connector's `config.json` (driver, properties) -> `connector.config_set_property` / `connector.config_set_asset` ([connector-config-edit.md](connector-config-edit.md))

The diagnostic job ends when the cause is named and the next-step action candidate is identified. The hand-off into the [Openflow SQL Action Mode](../../SKILL.md#openflow-sql-action-mode) is what produces the preview + confirmation; do not call the mutation from inside diagnostics.

---

## Connector Configure Deep Link (Not Yet Available)

Not currently scriptable from SQL. When the customer asks for a configure URL, ask them to navigate from the Openflow UI runtime page. (Implementation note: a future SQL surface exposing the connector `gsId` will enable a one-line URL builder; until then, do not invent a `gsId` source. The detailed URL format and the pinned future builder live in `openflow-core/.../ConnectorIdConverter.java` and the design notes alongside it.)

---

## Connector Config Snapshot (Read-Only)

Pull the connector's current `config.json` into a session-scoped stage and read it as JSON. Used for cause-chain analysis when a property looks misconfigured but the customer has not described it explicitly. Does not mutate the connector.

> **Permissions caveat.** The `COPY FILES INTO ... FROM 'snow://openflow_connector/...'` and `LIST 'snow://openflow_connector/...'` operations require READ on the connector's hidden version stage. The connector's owning role (typically `OPENFLOW_ADMIN`) usually has access, but customer-facing roles or scoped diagnostic roles may not. If the COPY FILES or LIST returns `Access Denied` / `does not exist or not authorized`, **fall back to event-table-only diagnostics**: the processor-level ERROR/WARN logs from the runtime namespace are usually sufficient to identify wrong / missing config values via the SQL text in the failed processor's bulletin (e.g., a 2-part `"schema"."table"` name in a `CREATE TABLE` reveals a missing destination-database property; `SQL access control error: Insufficient privileges to operate on <object>` or `Object 'X' does not exist or not authorized` reveals a wrong `Snowflake Role` or missing grants). Do not block the diagnostic on stage access -- treat it as enrichment, not a prerequisite.

### Setup (once per session)

```sql
CREATE OR REPLACE TEMPORARY STAGE OPENFLOW_CONFIG_INSPECT
  COMMENT = 'Read-only scratch for connector config diagnostics; auto-drops at session end';

CREATE TEMPORARY FILE FORMAT JSON_FF_RAW
  TYPE = JSON STRIP_OUTER_ARRAY = FALSE;
```

The TEMPORARY stage and TEMPORARY file format avoid cleanup work and persistent permission concerns.

### Pull and inspect the default version

```sql
-- 1. resolve the version path
DESCRIBE OPENFLOW CONNECTOR {connector_fqn};
-- capture default_version_location_uri, e.g.
-- snow://openflow_connector/{db}.{schema}.{connector}/versions/version$N/

-- 2. pull config.json into the temp stage
COPY FILES INTO @OPENFLOW_CONFIG_INSPECT
  FROM '{default_version_location_uri}'
  FILES = ('config.json');

-- 3. read as text
SELECT $1::STRING AS config_text
FROM @OPENFLOW_CONFIG_INSPECT/config.json
  (FILE_FORMAT => 'JSON_FF_RAW');
```

Direct `SELECT ... FROM 'snow://openflow_connector/...'` does NOT work (`Domain 'OPENFLOW CONNECTOR' is not supported by SnowURL in infer_schema`). The stage roundtrip is required.

### List all files in the version stage

```sql
LIST '{default_version_location_uri}';
```

Useful when an `ASSET_REFERENCE` field is set: confirm the named file (e.g. `postgresql-42.7.10.jar`) actually lives at the expected stage-relative path.

### Common patterns to grep for in the JSON

| Symptom | Pattern |
|---|---|
| Driver not uploaded | `"assetIds":null` on a property whose `valueType` is `ASSET_REFERENCE` |
| Required string left blank | `"value":null` on a property whose `valueType` is `STRING_LITERAL` |
| Secret never wired | `"fullyQualifiedSecretName":null` on a `SECRET_REFERENCE` |
| Wrong publication name | `"Source Database Publication Name":{"value":"..."}` does not match what `pg_publication_tables` reports on the source |

Pair the snapshot with Recent Error Logs scoped to the runtime namespace -- the snapshot tells you what the connector THINKS it should connect to; the error logs tell you what actually broke when it tried.

Per-action verification stays as a single `DESCRIBE OPENFLOW *` snapshot; report the observed `STATUS` and stop. If the target is mid-transition (`UPDATING`, `RESTARTING`, `ACTIVATING`, `STARTING`, `STOPPING`, `SUSPENDING`), surface that state and stop -- do not poll, do not wait, do not retry. Confirmation of the steady state comes from the [Post-Action Error Scan](#post-action-error-scan) above, not from polling object status.
