---
name: openflow-observability-connector-actions
description: Connector lifecycle Openflow SQL action templates and preflight checks (start, stop, commit, abort). Tier 2 -- load only when the Openflow SQL Action Mode has been entered and an allowlisted connector lifecycle action candidate exists.
---

<a id="openflow-sql-connector-lifecycle-actions"></a>
# Openflow SQL Connector Lifecycle Actions

> Customer-facing name for actions in this file: **Openflow SQL actions for connectors**. Use "SQL-managed connector" / "Openflow SQL action" when speaking to the customer.

Templates and preflight for the connector lifecycle actions in the MVP allowlist. Every template here assumes [action-guidelines.md](action-guidelines.md) is already loaded and all five hard gates from [SKILL.md](../../SKILL.md#openflow-sql-action-mode) will be enforced before the proposed SQL is executed.

This file is the lifecycle counterpart to [runtime-actions.md](runtime-actions.md). For config-content edits (changing properties inside `config.json`, attaching driver JARs), see [connector-config-edit.md](connector-config-edit.md).

## Scope

- Preflight queries shared by all connector actions
- Per-action templates: `connector.start`, `connector.stop`, `connector.commit`, `connector.abort`
- Out of scope: connector metadata SET/UNSET (cosmetic; customers do this via the UI), `connector.terminate`, `connector.drop`, anything that mutates `config.json` content (see [connector-config-edit.md](connector-config-edit.md))

---

## Shared Preflight

Run before any of the per-action templates below. The output of these queries is what fills the **Current state** field in the [Confirmation Preview Format](action-guidelines.md#confirmation-preview-format).

### 0. Connector-Definition Support Gate (BLOCKING)

Run the canonical [Connector-Definition Support Gate](action-guidelines.md#connector-definition-support-gate-sub-check-of-hard-gate-2) before any other step:

1. **Pre-gate (no SQL):** the agent has `connector_type` from input or page context (e.g. `postgresql`). Match it against the matrix's `connector_type alias` column. Today `postgresql` (`GA`) and `mysql` (`PrPr`) enter the lane; everything else fails closed before any SQL fires.
2. **Live check (1 SQL):** the agent reads `CONNECTOR_DEFINITION` from the SQL result (e.g. `OPENFLOW_POSTGRES_CDC`). Match it against the matrix's `Connector definition` column for the same row that passed the pre-gate.

If either check fails, stop entirely: no per-action preflight, no parent runtime describe, no preview. Note that the pre-gate alone CANNOT distinguish a SQL-managed postgres connector from a legacy (UI-only) one -- both report `connector_type = postgresql`. The live check is the load-bearing Openflow SQL action support signal; legacy postgres connectors fall out as zero-row / not-authorized.

The gate's live check also resolves the connector FQN and captures most of the columns used below, so it doubles as Step 1.

### 1. Resolve connector FQN AND confirm Openflow SQL action support (1 SQL)

This single query satisfies both the FQN-resolution need AND the gate-2 live Openflow SQL action support check above. Choose the form based on what the customer provided:

```sql
-- When the customer gave only a short connector name:
SHOW OPENFLOW CONNECTORS LIKE '{connector_name}' IN ACCOUNT;

-- When the customer gave the FQN (or the runtime is already known and we want
-- the full state set in one round-trip):
DESCRIBE OPENFLOW CONNECTOR {connector_fqn};
```

Per the Openflow SQL Action Guide, `SHOW OPENFLOW CONNECTORS`'s `IN` clause accepts `ACCOUNT | DATABASE | DATABASE <name> | SCHEMA | SCHEMA <name>`. `IN ACCOUNT` is the broadest scope and is the right choice when the customer hasn't specified a database/schema. To narrow to a single runtime's connectors, run `SHOW OPENFLOW CONNECTORS IN ACCOUNT` and filter the result rows where the `runtime` column matches the runtime name (the `IN OPENFLOW RUNTIME ...` form is not a valid `SHOW` scope on Snowflake).

Validate per the support gate. On success, capture FQN (`<DATABASE_NAME>.<SCHEMA_NAME>.<NAME>`), STATUS, CONNECTOR_DEFINITION, RUNTIME, DEFAULT_VERSION_NAME. From `DESCRIBE` (only) also capture LIVE_VERSION_LOCATION_URI, DEFAULT_VERSION_SOURCE_LOCATION_URI, DISPLAY_NAME, OWNER.

### 2. Describe the connector (only when step 1 used `SHOW`, and the action needs the live-version columns)

The fields needed for action eligibility differ by action:

| Action | Needs `LIVE_VERSION_LOCATION_URI` from DESCRIBE? |
|---|---|
| `connector.start`, `connector.stop` | No -- STATUS + DEFAULT_VERSION_NAME from step 1 are sufficient. Skip this step. |
| `connector.commit`, `connector.abort` | Yes -- run `DESCRIBE OPENFLOW CONNECTOR {connector_fqn}` to capture LIVE_VERSION_LOCATION_URI. |
| `connector.config_set_property`, `connector.config_set_asset` | Yes -- the config-edit shared preflight (`connector-config-edit.md`) needs LIVE_VERSION_LOCATION_URI and DEFAULT_VERSION_LOCATION_URI for the snapshot. |

When this step does run:

```sql
DESCRIBE OPENFLOW CONNECTOR {connector_fqn};
```

Capture: `STATUS`, `RUNTIME`, `CONNECTOR_DEFINITION`, `DEFAULT_VERSION_NAME`, `LIVE_VERSION_LOCATION_URI`, `DEFAULT_VERSION_SOURCE_LOCATION_URI`, `DISPLAY_NAME`, `OWNER`.

Validate `STATUS` against the action eligibility table below. Stop if the action is not allowed for the current state.

### 3. Resolve and describe the parent runtime

The connector's parent runtime gates many CDC-retention warnings and the node-size requirement for `connector.start`.

```sql
DESCRIBE OPENFLOW RUNTIME {runtime_fqn};
-- runtime_fqn comes from the RUNTIME column captured in step 1 (or step 2),
-- combined with the same DATABASE_NAME / SCHEMA_NAME (connector and runtime share scope)
```

Capture parent `STATUS`, `NODE_TYPE`, `EXTERNAL_ACCESS_INTEGRATIONS`, `DEPLOYMENT`. `NODE_TYPE` is needed for the [`connector.start` connector-definition node-size gate](#connectorstart----start-a-stopped-connector).

### 4. Connector status eligibility

Per the Openflow SQL Action Guide, `DESCRIBE OPENFLOW CONNECTOR` returns `STATUS` as one of: `DRAFT | STOPPED | STARTING | RUNNING | STOPPING | DELETING | DELETED | UPDATING | START_FAILED | STOP_FAILED`. `DRAFT` is a real STATUS column value (the post-create, pre-first-commit state where `DEFAULT_VERSION_NAME IS NULL`); it is NOT a derived label. The `DEFAULT_VERSION_NAME` and `LIVE_VERSION_LOCATION_URI` columns are independent of STATUS and gate the live-version actions.

| Action | Required STATUS | Required `LIVE_VERSION_LOCATION_URI` | Required `DEFAULT_VERSION_NAME` | Notes |
|---|---|---|---|---|
| `connector.start` | `STOPPED` | (any) | non-NULL | If STATUS is `DRAFT`, refuse and route to the [DRAFT Connector Fast-Path](connector-diagnostics.md#draft-connector-fast-path) -- a DRAFT connector has no default version to start. The `DEFAULT_VERSION_NAME non-NULL` belt-and-suspenders check catches the rare case of a STOPPED connector with no default. |
| `connector.stop` | `RUNNING` OR `UPDATE_FAILED` | (any) | (any) | Refuse on every other STATUS. `UPDATE_FAILED` is permitted because STOP is the documented recovery from that state -- see the explanatory note below the table. |
| `connector.commit` | `STOPPED` OR `DRAFT` | non-NULL | (any) | DRAFT-commit is the canonical recovery for a fresh DRAFT connector: COMMIT promotes the live version to default and transitions STATUS to STOPPED. STOPPED-commit applies staged edits on a previously-committed connector. Refuse if `LIVE_VERSION_LOCATION_URI IS NULL` ("no edits to apply"). |
| `connector.abort` | non-terminal | non-NULL | non-NULL | Refuse if `DEFAULT_VERSION_NAME IS NULL` (DRAFT connectors cannot ABORT -- aborting the only live version would leave them unrunnable). Use `connector.config_set_*` to fix DRAFT, then COMMIT. |

**Fail-closed STATUS values (refuse every action above).** If `DESCRIBE OPENFLOW CONNECTOR` returns any of: `CREATING`, `CREATE_FAILED`, `DELETING`, `DELETED`, `UPDATING`, `START_FAILED`, `STOP_FAILED`, treat as a transient or terminal state. Stop, tell the customer the connector is not in an actionable state, and fall back to read-only guidance. For `START_FAILED` / `STOP_FAILED` specifically, run the [Post-Action Error Scan](connector-diagnostics.md#post-action-error-scan) bounded to the runtime namespace so the customer sees the underlying cause (typically missing EAI / network access / source DB unreachable for `START_FAILED`).

**`UPDATE_FAILED` is a special case: only `connector.stop` is permitted.** All other actions (`connector.start`, `connector.commit`, `connector.abort`, `connector.config_set_*`) refuse on `UPDATE_FAILED`. Run the [Post-Action Error Scan](connector-diagnostics.md#post-action-error-scan) to surface the validation failure that produced the `UPDATE_FAILED` state, then propose `connector.stop` as the recovery path. After `STOP` lands the connector in `STOPPED`, the customer can re-attempt the corrected config edit (a fresh `connector.config_set_*` or stage-promote cycle) followed by `connector.start`. See the explanatory note below.

`STARTING` and `STOPPING` are transient. Stop and ask the customer to wait for the connector to settle, then re-preflight.

> **`UPDATE_FAILED` recovery via `connector.stop`.** A connector in `UPDATE_FAILED` cannot be moved forward by another `START` or by a fresh `ADD VERSION FROM` promote -- both are rejected or land back in `UPDATE_FAILED`. The recovery is `connector.stop`, which transitions the connector to `STOPPED`. After it reaches `STOPPED`, the customer can re-attempt the corrected config edit followed by `connector.start`. The diagnostic flow is: investigate the underlying validation failure first (usually visible in the canvas bulletin board if the event table is silent), fix the offending property, then `STOP -> corrected edit -> START`. If multiple stage-promote cycles do not clear the validation despite the corrected `config.json`, the connector's validation cache may be stuck on an earlier bad version; this requires recreating the connector through the Openflow UI wizard (DROP / TERMINATE / CREATE OPENFLOW CONNECTOR are not in the SQL action allowlist; do not author a SQL sequence performing them).

---

## CDC Retention Warning

When the connector's `CONNECTOR_DEFINITION` has `Family = CDC` in the [Openflow SQL Connector Support Matrix](connector-support-matrix.md#connector-capability-matrix), include the canonical [CDC Retention Warning](action-guidelines.md#cdc-retention-warning-cross-cutting) in the Confirmation Preview's **Expected impact** field for any action that pauses the connector (`connector.stop`, `connector.commit`).

Tier selection:

- `connector.stop`: ask the mandatory duration prompt from [CDC Retention Warning](action-guidelines.md#cdc-retention-warning-cross-cutting) and use the tier selected by the customer's `(a)/(b)/(c)` reply.
- `connector.commit`: use **Standard** (the pause is the brief UPDATING window).

Anchor name kept here for backward compatibility with cross-file references; the canonical source is in `action-guidelines.md`.

---

## connector.start -- Start a STOPPED connector

### Inputs

- `connector_fqn` (required)

### Preflight

1. Run [Shared Preflight](#shared-preflight) steps 0 through 3. Step 2 is skipped for start/stop and required for commit/abort.
2. Require `STATUS = 'STOPPED'`.
3. Require `DEFAULT_VERSION_NAME` is non-NULL. If NULL the connector is in DRAFT and starting will fail; route to the [DRAFT Connector Fast-Path](connector-diagnostics.md#draft-connector-fast-path).
4. Confirm parent runtime `STATUS = 'ACTIVE'`. A connector cannot start on a SUSPENDED runtime.
5. **Connector-definition node-size gate.** Some connector definitions require a minimum parent runtime `NODE_TYPE`. Look up the connector's row in the [Openflow SQL Connector Support Matrix](connector-support-matrix.md#connector-capability-matrix) and read the `Min parent NODE_TYPE` column. Compare against step 3's parent runtime `NODE_TYPE`.

   If the connector definition is not listed in the matrix, the agent has no node-size data and must NOT proceed with `connector.start` -- fall back to customer-run UI guidance.

   If the parent runtime `NODE_TYPE` is below the minimum, **fail closed**. `node_type` is immutable after runtime creation, so the customer must rebuild the runtime at the larger size; surface that explicitly and stop. Do not propose `connector.start`.
6. **Capture the rollback target.** Run `SHOW VERSIONS IN OPENFLOW CONNECTOR {connector_fqn}` and capture the `LOCATION_URI` of the row currently marked `IS_DEFAULT = TRUE`. Call this `{pre_action_default_uri}`. **This is the version the connector will roll back TO if the action goes wrong** -- specifically, the version that is the default at preflight time. Substitute it into the `Rollback:` line of the Confirmation Preview's Expected impact (see [Confirmation Preview Format](action-guidelines.md#confirmation-preview-format)). The rollback for `connector.start` is `connector.stop` (no version change), but the line is required by format consistency -- render `Rollback: ALTER OPENFLOW CONNECTOR {connector_fqn} STOP` for this action.

### Proposed SQL

```sql
ALTER OPENFLOW CONNECTOR {connector_fqn} START;
```

### Expected impact

- Connector transitions `STOPPED -> STARTING -> RUNNING`.
- For CDC connectors: replication resumes from the last committed offset. No data loss in steady state.
- Cost impact: the parent runtime is already running, so the marginal cost of starting a connector is the runtime time it takes to ingest and merge data.
- Reversible: yes, via `connector.stop`.

### Verification

```sql
DESCRIBE OPENFLOW CONNECTOR {connector_fqn};
```

Watch `STATUS` move through `STARTING` to `RUNNING` via a single `DESCRIBE` snapshot. Then run the [Post-Action Error Scan](connector-diagnostics.md#post-action-error-scan) for the runtime namespace bounded to the last 2 minutes. If the connector lands in `STOPPED` again immediately or the scan returns `ERROR` rows, surface them verbatim and propose `connector.stop` (followed by config repair via [connector-config-edit.md](connector-config-edit.md) if the errors point at config) as a fresh action.

---

## connector.stop -- Stop a RUNNING or UPDATE_FAILED connector

### Inputs

- `connector_fqn` (required)
- `reason` (required free text used in the preview, e.g. "stop before editing config", "pause during source maintenance")

### Preflight

1. Run [Shared Preflight](#shared-preflight) steps 0 through 3. Step 2 is skipped for start/stop and required for commit/abort.
2. Require `STATUS IN ('RUNNING', 'UPDATE_FAILED')`.
3. If `CONNECTOR_DEFINITION` is a CDC type, ask the mandatory duration prompt from [CDC Retention Warning](action-guidelines.md#cdc-retention-warning-cross-cutting) unless the customer already answered with `(a)`, `(b)`, or `(c)`. Prepare the warning using that exact bucket, not prose from `reason`.

### Proposed SQL

```sql
ALTER OPENFLOW CONNECTOR {connector_fqn} STOP;
```

### Expected impact

- Connector transitions `RUNNING -> STOPPING -> STOPPED`, or `UPDATE_FAILED -> STOPPED` for update-failure recovery. In-flight flowfiles drain to a stable point before the stop completes.
- For CDC connectors: see [CDC Retention Warning](action-guidelines.md#cdc-retention-warning-cross-cutting). No data loss in steady state.
- Cost impact: the connector stops processing; the parent runtime continues to incur cost.
- Reversible: yes, via `connector.start`.

### Verification

```sql
DESCRIBE OPENFLOW CONNECTOR {connector_fqn};
```

Watch `STATUS` transition through `STOPPING` to `STOPPED`. If `STOPPING` persists for more than a few minutes, surface that to the customer and stop -- do not retry from the agent.

---

## connector.commit -- Apply staged config edits

Apply a previously-prepared live version (created via the Openflow UI wizard's editing flow, or by a separate customer-run `ADD LIVE VERSION` + content edits) to become the new default version. After commit the connector lands in `STOPPED`; `connector.start` is required to run.

This action is the **apply** step at the end of the live-version edit roundtrip. Note that the agent's own config-edit actions in [connector-config-edit.md](connector-config-edit.md) use the stage-promote path (`ADD VERSION FROM '@stage'`) which auto-promotes and does not require a separate COMMIT. `connector.commit` exists primarily for the case where the customer staged edits via the Openflow UI and then asks the agent to apply them.

### Inputs

- `connector_fqn` (required)

### Preflight

1. Run [Shared Preflight](#shared-preflight) steps 0 through 3. Step 2 is skipped for start/stop and required for commit/abort.
2. Require `STATUS IN ('STOPPED', 'DRAFT')`. If `RUNNING`, propose `connector.stop` first as a separate gated action -- do not chain.
3. Require `LIVE_VERSION_LOCATION_URI` is non-NULL (a live version exists to apply).
4. **Capture the rollback target.** Run `SHOW VERSIONS IN OPENFLOW CONNECTOR {connector_fqn}` and capture the `LOCATION_URI` of the row currently marked `IS_DEFAULT = TRUE`. For a `DRAFT` connector with no default version, there is no rollback target; render `Rollback: none -- this is the first default version` in the preview. Otherwise, call the captured URI `{pre_action_default_uri}`. **This is the version the customer can roll back TO if the action goes wrong** -- specifically, the version that is the default at preflight time, which the COMMIT is about to displace. It is NOT the oldest available version. Substitute it into the `Rollback:` line of the Confirmation Preview's Expected impact as customer-run guidance:

   ```
   Customer-run rollback: ALTER OPENFLOW CONNECTOR {connector_fqn} ADD VERSION FROM '{pre_action_default_uri}';
   ```
5. Surface the live version's stage URI and remind the customer that `COMMIT` is irreversible by `ABORT` after this point (revert is only possible via a customer-run `ADD VERSION FROM '@stage'` of a previous version, which the rollback line above gives them when a previous default exists).

### Proposed SQL

```sql
ALTER OPENFLOW CONNECTOR {connector_fqn} COMMIT;
```

### Expected impact

- Live version is promoted to default. Previous default version is preserved as a non-default version (visible via `SHOW VERSIONS`).
- Connector transitions `STOPPED -> UPDATING -> STOPPED`. **Always lands in STOPPED**; `connector.start` is required separately to run.
- For CDC connectors: see [CDC Retention Warning](action-guidelines.md#cdc-retention-warning-cross-cutting) -- the connector is paused for the duration of UPDATING.
- Reversible: only by creating a new version from a previous version (`ADD VERSION FROM` -- not in this MVP allowlist for arbitrary previous versions) or by another full edit cycle.

### Verification

```sql
DESCRIBE OPENFLOW CONNECTOR {connector_fqn};
SHOW VERSIONS IN OPENFLOW CONNECTOR {connector_fqn};
```

Confirm:
- `STATUS = 'STOPPED'`
- `LIVE_VERSION_LOCATION_URI` is now NULL
- `DEFAULT_VERSION_NAME` advanced (e.g. from `version$1` to `version$2`)

Then run the [Post-Action Error Scan](connector-diagnostics.md#post-action-error-scan) for the runtime namespace bounded to the last 2 minutes. If `ERROR` rows return, the new default has a config problem -- surface verbatim and provide the customer-run rollback guidance captured in Preflight step 4. Do not execute rollback SQL from the agent. Zero rows = success; the agent MAY propose `connector.start` as a fresh, separately-confirmed next step.

---

## connector.abort -- Discard staged config edits

Discard a live version without applying it. The connector returns to its prior default version content; nothing else changes.

### Inputs

- `connector_fqn` (required)

### Preflight

1. Run [Shared Preflight](#shared-preflight) steps 0 through 3. Step 2 is skipped for start/stop and required for commit/abort.
2. Require `LIVE_VERSION_LOCATION_URI` is non-NULL (something to abort).
3. Require `DEFAULT_VERSION_NAME` is non-NULL. If NULL the connector is in DRAFT and `ABORT` would leave it unrunnable -- refuse and route to the [DRAFT Connector Fast-Path](connector-diagnostics.md#draft-connector-fast-path) for guidance.
4. Status may be `STOPPED` or `RUNNING`; abort does not require a stop because it does not change the running configuration.

### Proposed SQL

```sql
ALTER OPENFLOW CONNECTOR {connector_fqn} ABORT;
```

### Expected impact

- Live version is permanently deleted. Any uploaded driver JARs or modified `config.json` in the live stage are lost.
- Default version is unchanged; the connector continues to run with its current configuration.
- Reversible: no. Customer must re-do their edits if they want to retry.

### Verification

```sql
DESCRIBE OPENFLOW CONNECTOR {connector_fqn};
```

Confirm `LIVE_VERSION_LOCATION_URI` is NULL.

---

## After Any Successful Action

- Report the before/after values from the verification query in plain language.
- For `connector.start`, `connector.stop`, `connector.commit`: run the [Post-Action Error Scan](connector-diagnostics.md#post-action-error-scan) for the runtime namespace bounded to the last 2 minutes. If `ERROR` rows return, surface them verbatim and provide customer-run recovery or rollback guidance; do not execute rollback SQL from the agent. Zero rows = success.
- Drop back to diagnostic mode for any further work. Do not chain a second mutation in the same response without a fresh user request and a fresh preview. The one explicit chain the agent MAY propose (as a separate, freshly previewed action) is `connector.start` after `connector.commit`, because COMMIT always lands in STOPPED and the customer almost always wants to run the connector afterward.
