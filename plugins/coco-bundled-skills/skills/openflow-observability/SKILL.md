---
name: openflow-observability
description: "Troubleshoot Openflow connector / runtime / deployment issues via Snowsight SQL diagnostics, and run a narrow set of confirmation-gated SQL actions on SQL-managed runtimes. Use when: connector is unhealthy, table FAILED, runtime stuck or OOM, EAI / network issues, restart / resume / suspend runtime, attach EAI to runtime. Triggers: openflow, connector, runtime, deployment, EAI, table FAILED, openflow troubleshoot, openflow runtime."
skill_version: "2026-07-16"
---

# Openflow Observability

Customer-facing skill for Snowflake Openflow connector issues in Snowsight. The default mode is read-only diagnosis: use Snowsight-accessible SQL to identify root cause, then tell the customer what they can check or change in their own Openflow UI, Openflow runtime, Snowflake account, source system, or cloud environment.

When the target runtime is verified SQL-managed and the customer either explicitly asks for an action ("please add EAI X to my runtime") or accepts an action proposal coming out of diagnosis, the skill MAY execute a narrow allowlist of Openflow SQL actions after an explicit confirmation gate. See [Openflow SQL Action Mode](#openflow-sql-action-mode).

**Keep all customer-facing responses concise** - No filler, lead with findings and next steps.

**Customer-Facing Naming (always).** When speaking to the customer, always use:

- "Openflow SQL actions" or "SQL action" (the lane / mechanism)
- "SQL-managed runtime" (a runtime that supports these actions)
- "Openflow UI" or "Openflow CLI" (the alternative)

---

## Intent Router (Run First)

Pick the lane based on the user request before any other work. The lane decides which startup bundle to load and which gates apply.

| Intent | Examples | Lane |
| --- | --- | --- |
| Troubleshoot a connector / runtime / deployment | "this connector is unhealthy", "diagnose <error>", "why is my runtime stuck" | **Troubleshoot lane** -> [Startup Sequence](#startup-sequence-run-first) below. |
| Explicit Openflow SQL action request (runtime / deployment / connector lifecycle / connector config) | "add EAI X to runtime Y", "resume runtime Y", "restart runtime Y", "stop / start / commit / abort connector Z", "set the publication name on connector Z", "the driver is missing on connector Z", "apply this config.json to connector Z" | **SQL action lane** -> [Openflow SQL Action Mode](#openflow-sql-action-mode). |
| Mixed | "this is failing because of a missing EAI, can you fix it?", "the connector is in DRAFT because the driver was never uploaded -- can you wire it up?" | Run **Troubleshoot lane** first to confirm root cause, then propose an Openflow SQL action only if it falls inside the allowlist. |
| Scale / resize a runtime | "make runtime X bigger", "resize to a larger node", "give it more memory" | **Troubleshoot lane** (capacity diagnosis). Node size (`NODE_TYPE`) is fixed at create time and changeable by neither SQL nor the UI, so this is not an Openflow SQL action -- do not enter the action lane. See [troubleshoot-runtime.md](references/troubleshoot-runtime.md) OOM / Memory branch. |

**Default to the Troubleshoot lane when intent is ambiguous.** Never jump straight into the SQL action lane based on a user-provided runtime name alone -- diagnose or preflight first.

---

## Startup Sequence (Run First)

**BLOCKING:** Complete steps 1-4 before routed diagnostics. The only SQL allowed before the full family bundle is loaded is the connector-type bootstrap in step 3 when `connector_type` is missing.

This Startup Sequence applies to the **Troubleshoot lane** selected by the [Intent Router](#intent-router-run-first). When the Intent Router selects the **SQL action lane** instead, skip ahead to [Openflow SQL Action Mode](#openflow-sql-action-mode) and load `references/openflow-sql/action-guidelines.md` before any further work; you do not need the connector family bundle for explicit runtime/EAI tasks. The SQL action lane still requires an active warehouse for `SHOW OPENFLOW ...` preflight queries; see the warehouse prerequisite in [core-guidelines.md](references/core-guidelines.md#diagnostic-mode-sql-constraint).

1. **Read core files now.**
   - Read `references/core-guidelines.md`.
   - Read `references/core-queries.md`.
   - **In parallel with these reads, call `get_page_context` when the tool is available.** See [Page Context (When Available)](#page-context-when-available) for what to merge. When the tool is unavailable or returns an empty payload, proceed unchanged.

2. **Parse inputs.**
   - Read `connector_type` from the input. Accept both structured field names and common prompt labels. Treat `connector_type` and `Connector:` as the same startup input. Normalize common aliases before routing: `postgres` -> `postgresql`, `mssql` or `sqlserver` -> `sql_server`.
   - Track `{event_table}`, `{deployment_id}`, `{runtime_name}`, and `deployment_type` immediately if present.
   - Only infer `connector_type` when it is truly missing from the input.

3. **Resolve `connector_type`, then read the full startup bundle.**
   - If `connector_type` is known, load the matching family bundle below.
   - If `connector_type` is missing, first read `references/core-queries-resource.md` and run Namespace Validation, Recent Error Logs, Error Pattern Summary, and Active Connectors to infer it. Once known, return here and load the matching family bundle.
   - After `connector_type` is known or inferred, read every file in the matching bundle in order. Do not cherry-pick. The bundle is a minimum baseline. Load additional reference files whenever the investigation calls for them. If the known `connector_type` maps to a dedicated per-connector file in the routed connector router, that per-connector file is part of the startup bundle and must be read now.

   **3a. Always first:** Read `references/connectors/connector-shared-generic.md`. Every family depends on it.

   **3b. Family-specific reads (in listed order):**

   **Per-connector file resolution.** Do NOT derive the per-connector file name from `connector_type`. Suffixes like `_unstructured`, `_bulk_api`, etc. do not always map 1:1 to a file (e.g. `sharepoint_unstructured` → `sharepoint.md`, `salesforce_bulk_api` → `salesforce.md`). Resolve the file via the routing table at the top of `references/connectors/connector-router-non-cdc.md` (Non-CDC and SaaS/API) or `references/connectors/connector-router-cdc.md` (CDC). For CDC, the basename happens to match `connector_type`, but still go through the router so the rule stays consistent. If the router has no dedicated file for the `connector_type`, do not invent one — fall back as described below.

   **CDC** (`postgresql`, `mysql`, `sql_server`, `oracle`):
   1. Read `references/connectors/connector-shared-cdc.md`
   2. Read `references/connectors/connector-router-cdc.md`
   3. Read the per-connector file resolved from the CDC router table (`references/connectors/connector-router-cdc.md`). For CDC every supported `connector_type` has a dedicated file.
   4. Read `references/core-queries-resource.md`

   **Non-CDC** (`kafka`, `kinesis`, `mongodb`, `snowflake_to_kafka`):
   1. Read `references/connectors/connector-router-non-cdc.md`
   2. Look up `connector_type` in that router's mapping table and read the resolved per-connector file. If `connector_type` has no dedicated file in the table, continue with the shared files already loaded (`connector-shared-generic.md`).

   **SaaS/API** (see the routing table in `references/connectors/connector-router-non-cdc.md` for the authoritative list — currently includes `salesforce_bulk_api`, `microsoft_dataverse`, `sharepoint_unstructured`, `google_drive_unstructured`, `box_unstructured`, ads connectors, and SaaS connectors such as `google_drive`, `sharepoint`, `box`, `jira`, `hubspot`, `workday`, `confluence`, `slack`, `google_sheets`):
   1. Read `references/connectors/connector-router-non-cdc.md`
   2. Read `references/connectors/saas-connectors.md`
   3. Look up `connector_type` in the router's mapping table and read the resolved per-connector file. If `connector_type` has no dedicated file in the table, continue with `references/connectors/saas-connectors.md` plus `references/connectors/connector-shared-generic.md`.

   All referenced files live under `references/connectors/` except `core-queries-resource.md` which lives under `references/`.

4. **Only now begin routed SQL diagnostics.** Namespace Validation is the first routed query when step 3 did not require the bootstrap path. If step 3 used the bootstrap path, do not continue into routing or recovery guidance until the resolved family bundle has been loaded.

### Why This Order Matters

Per-connector files (e.g. `oracle.md`) contain source-specific diagnostics but defer all recovery procedures to `connector-shared-cdc.md`. If the shared files are not loaded, the agent will improvise recovery steps from incomplete context, give wrong guidance, or skip canonical procedures like Restart Table Replication. The bundle is not background reading; it is required context for correct diagnosis. See [Context Retention](#context-retention) for guidance when bundle files are evicted in long sessions.

### Context Retention
- **If any bundle file read was truncated or evicted, re-read it before writing any guidance that references its content.** Do not rely on partial memory of file contents. Re-read once; if re-reading causes further eviction, proceed with available context and note the uncertainty to the customer.
- **Before writing recovery guidance for a FAILED table, re-read the [Restart Table Replication](#restart-table-replication) section in this file and the safety preamble in `references/connectors/connector-shared-cdc.md`.** This is the most commonly misquoted procedure.
- **The CDC critical rules in [CDC Guardrails](#cdc-guardrails-apply-early) survive context eviction.** Even if the full bundle files are evicted, those rules remain in SKILL.md and must be followed.

### Cross-Category References

These are not part of the startup bundle but can be loaded whenever the investigation points to a different failure domain (see [Cross-Category Investigation](references/core-guidelines.md#cross-category-investigation)).

| Trigger | Reference |
|---------|-----------|
| Network errors (UnknownHostException, EAI, connection refused, timeout) | `references/troubleshoot-network.md` |
| Runtime errors (OOM, crash loop, upgrade failure, pod issues) | `references/troubleshoot-runtime.md` |

### Context Tracking

Track startup files internally. Only mention them if startup is incomplete or context was lost. At session start or after context loss, confirm the required inputs (`{event_table}`, `{deployment_id}`, and the routed runtime or connector context) are tracked before continuing.

When summarizing tracked context to the customer, use human labels and omit unknowns. Never show curly-brace placeholders like `{namespace}` in customer-facing text.

```
Tracked context:
- Event table: <event_table>
- Deployment ID: <deployment_id>
- Runtime: <runtime_name>
- Namespace: <namespace>
- Connector type: <connector_type> (<CDC | Non-CDC | SaaS/API>)
- Time window: <time_window>  OR  last <hours_back> hours
- Deployment type: Snowflake SPCS  OR  BYOC <cloud>
```

---

## Structured Input

The Snowsight UI provides structured fields when triggering this skill. Extract and track these throughout the session.

### Input Fields

| Field | Required | Example | Notes |
| --- | --- | --- | --- |
| `event_table` | Yes | `OPENFLOW.OPENFLOW.EVENTS` | Fully qualified three-part name |
| `deployment_id` | Yes | `5fac6f12-...` | UUID from the Openflow UI |
| `runtime_name` | Situational | `My PostgreSQL` | Expected for all connector issues |
| `connector_type` | Situational | `postgresql` | Required for connector issues; routes via the CDC or non-CDC connector router |
| `connector_name` | No | `PostgreSQL CDC` | Display-only. Used in escalation. Cross-reference with Active Connectors if needed |
| `error_message` | No | `Table FAILED...` | Raw error text from UI; used for triage routing |
| `health_status` | No | `UNHEALTHY` | Connector health from UI; confirms connector is in a failure state |
| `deployment_type` | No | `snowflake` | `snowflake` = SPCS; any other value (e.g., `byoc_aws`, `byoc_*`) = BYOC. Use this to branch SPCS vs BYOC in runtime and network fallback paths. |
| `time_window` | No | `2024-01-01T00:00:00.000Z to 2024-01-08T00:00:00.000Z` | Dashboard date range filter. When present, use it for incident-scoped event-log diagnostics instead of `{hours_back}`. Resource/state queries may still use a rolling window when their section says so. Format: ISO 8601 start, optionally ` to ` ISO 8601 end. If queries return results outside the expected window, verify `{start_time}` parses correctly with `TRY_TO_TIMESTAMP_TZ` in Snowflake; malformed timestamps silently fall back to the rolling `{hours_back}` window. |
| `total_errors` | No | `3` | Error count from the dashboard. Informational only; helps gauge severity but does not change diagnostic routing. |

### Derived Variables

Computed from input fields. Track these throughout the session:

| Variable | Derivation | Default |
| --- | --- | --- |
| `{event_table}` | Direct from `event_table` input | -- (required) |
| `{deployment_id}` | Direct from `deployment_id` input | -- (required) |
| `{namespace}` | `runtime-<key>`. Prefer page context, else read the `key` from `DESCRIBE OPENFLOW RUNTIME`. The name-sanitization heuristic (lowercase `runtime_name`, spaces -> hyphens, prepend `runtime-`; e.g. `My PostgreSQL` -> `runtime-my-postgresql`) is a **gen1 fallback** and misses the `-NNN` suffix that SQL-managed (gen2) runtimes always carry -- see [Namespace Derivation](references/core-guidelines.md#namespace-derivation) | -- (derive then validate per [Namespace Validation](#namespace-validation)) |
| `{hours_back}` | Start at `2`. **Only used when `time_window` is not provided.** See [Time Filtering](references/core-guidelines.md#time-filtering) for expansion rules. | `2` (see [Time Filtering](references/core-guidelines.md#time-filtering) for expansion rules) |
| `{start_time}` | Start timestamp from `time_window` input | Falls back to `DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP())` |
| `{end_time}` | End timestamp from `time_window` input | `CURRENT_TIMESTAMP()` when `time_window` has no end, or omitted entirely when using `{hours_back}` fallback |
| `{connector_name}` | Direct from `connector_name` input | -- (optional) |
| `{error_timestamp}` | UTC timestamp from query results or customer report | Use `{hours_back}` rolling window when unavailable |
| `{runtime_name}` | Direct from `runtime_name` input | -- (required for runtime and connector paths) |
| `{field_pattern}` | Set by the **Namespace + Shape Probe** (`references/core-queries.md`). Values: `record_attributes` or `parsed_json` (standard queries self-adapt via COALESCE; no branching needed), or `raw_text` (both NULL; skip standard filtered queries, use Generic Raw Log Fallback). | `record_attributes` |
| `{probe_run}` | Set by the Discovery Sequence primary parallel batch. Values: `ran` (probe executed) or `skipped` (page-context fast path; namespace validity and `{field_pattern}` inferred from catalog without a SQL round-trip). Track across the session so later turns do not re-derive the probe state from scratch. Reset to `ran` and run the probe on the next batch whenever the agent narrows `{start_time}`/`{end_time}` off the page-context snapshot window or switches `{namespace}` to a value not supplied by page context. | `ran` |

**`{namespace}` precedence (page context).** When `get_page_context` returns a `namespace` field, use it directly and skip the derivation above. Namespace is load-bearing: a wrong value scopes every subsequent query to the wrong runtime. [Namespace Validation](#namespace-validation) still runs against the chosen namespace unchanged, so a stale or bad page-context payload fails closed there.

### Investigation-Only Variables

Most deployment and runtime metadata should already be present in the provided context. Only discover additional values when a routed troubleshooting path actually needs them:

| Variable | How It Becomes Known | Used In |
| --- | --- | --- |
| `{eai_name}` | Discovered from `SHOW EXTERNAL ACCESS INTEGRATIONS` or deployment metadata when troubleshooting network/EAI issues | `DESCRIBE EXTERNAL ACCESS INTEGRATION`, customer-run EAI updates if needed |
| `{network_rule_name}` | `DESCRIBE EXTERNAL ACCESS INTEGRATION {eai_name}` output | `DESCRIBE NETWORK RULE`, customer-run network rule updates if needed |
| `{destination_database}` | Error logs (table failure messages name the table) or customer | Identifies affected destination table |
| `{failed_schema}`, `{failed_table}` | Error logs (`Replication state for table ... changed ... to FAILED`) | Identifies failed replication target |
| `{source_host}` | Connection error logs (`UnknownHostException`, `Connection refused`) | Network rule VALUE_LIST, domain allowlist verification |
| `{aws_region}` | Error logs (`dynamodb.{aws_region}.amazonaws.com`) or customer | Kinesis/Kafka/SaaS domain allowlists, network rule VALUE_LIST |
| `{runtime_role}` | Customer-provided or discovered from `SHOW GRANTS TO ROLE` during permission troubleshooting | Identifies the runtime's granted role |
| `{integration_name}` | `name` column from `SHOW OPENFLOW DATA PLANE INTEGRATIONS` filtered by `{deployment_id}` | `DESCRIBE OPENFLOW DATA PLANE INTEGRATION`, deployment state verification |

### When Fields Are Missing

- **`event_table` missing:** Ask the customer to provide it from the Snowsight skill context or deployment details. Do not run account-level discovery by default.
- **`deployment_id` missing:** Ask the customer to provide it from the Snowsight skill context or deployment details. Do not run account-level discovery by default.
- **`runtime_name` missing for a runtime or connector issue:** Ask the customer to provide it from the Snowsight skill context or runtime details. Do not query event-table namespaces as a fallback.
- **`connector_type` missing:** Infer from error context when the logger or error text is distinctive:
  - `SALESFORCE_BULK_API` in LogMessage -> `salesforce_bulk_api`
  - SharePoint/Graph API loggers, `CaptureSharepointChanges` -> `sharepoint_unstructured`
  - `CaptureGoogleDriveChanges` or Google Drive API loggers -> `google_drive_unstructured`
  - Kafka/Kinesis client loggers (`org.apache.kafka.*`, `software.amazon.kinesis.*`) -> `kafka` or `kinesis`
  - `com.snowflake.openflow.runtime.processors.dataverse` -> `microsoft_dataverse`
  - For all other logger prefixes, or when the prompt gives no distinctive signal, use the [Startup Sequence](#startup-sequence-run-first) bootstrap in step 3: Namespace Validation -> Recent Error Logs -> Error Pattern Summary -> Active Connectors. Do not guess the family bundle before running that bootstrap.
- **`health_status` provided but `error_message` and `connector_type` absent:** Use the [Startup Sequence](#startup-sequence-run-first) bootstrap in step 3. Start with Namespace Validation, then Recent Error Logs, then Error Pattern Summary. If the error pattern is still ambiguous, run Active Connectors before choosing a bundle.
- **`time_window` missing:** Fall back to `{hours_back}` rolling window (default 2h, expanding per [Time Filtering](references/core-guidelines.md#time-filtering) rules). This is the normal path for the ConnectorsTable entry point and any sessions where the dashboard date range was not captured.
- **`connector_type` present but `error_message` absent (high-level troubleshoot):** The startup bundle is already loaded from [Startup Sequence](#startup-sequence-run-first) step 3. Follow the Discovery Sequence below.

---

## Page Context (When Available)

When `get_page_context` is available, call it in parallel with the [Startup Sequence](#startup-sequence-run-first) file reads. The payload is a snapshot of the dashboard at the moment the customer clicked Troubleshoot, not a live source of truth. See [Trust Boundary](#trust-boundary) below for verification rules.

### Metadata Merge

Fields map 1:1 to the tracked variables already defined in [Input Fields](#input-fields) and [Derived Variables](#derived-variables): `eventTable`, `deploymentId`, `connectorType`, `connectorName`, `timeWindowStart`/`timeWindowEnd` -> `{start_time}`/`{end_time}`. The `namespace` field is pre-derived as `runtime-<runtimeKey>` -- use directly, skip the derivation step.

### SOM / SQL-managed metadata (SOM connectors only)

When the connector carries a gen2 (SQL-managed, internally "SOM") identity, page context adds the fields below; track each as the session variable shown. **Trust semantics live in `references/openflow-sql/action-guidelines.md` and win on any discrepancy** -- the invariant to hold inline: **none of these authorizes a mutation; live `SHOW`/`DESCRIBE` is the sole positive gate** ([Openflow SQL Action Support Detection](references/openflow-sql/action-guidelines.md#openflow-sql-action-support-detection)).

- `isSom` -> `{is_som}` (hint): `'false'` routes to the gen1/legacy read-only path; `'true'` is a SOM candidate that live SQL must still confirm.
- `openflowSqlActionsEnabled` -> `{sql_actions_enabled}` (negative gate only): present-and-`'false'` -> read-only, route to UI, run zero Openflow SQL ([session feature-flag pre-filter](references/openflow-sql/action-guidelines.md#session-feature-flag-pre-filter-no-sql-negative-only)); `'true'` or absent is **not** authorization.
- Identity/lookup hints (never capability signals, always confirmed by the live reads that gate every action): `openflowConnectorId` -> `{openflow_connector_id}`, an integer id used only to resolve the FQN ([ID Resolution](references/openflow-sql/action-guidelines.md#id-resolution-and-namespace-mapping)); `connectorDefinition` -> `{connector_definition_hint}`, the matrix pre-gate lookup key (live `CONNECTOR_DEFINITION` wins on disagreement); `deploymentName`/`runtimeName` -> `{deployment_name}`/`{runtime_name}`, seeds for the live deployment/runtime reads. Mutating SQL always uses the live SQL `NAME`, never a page-context value.

If `get_page_context` returns none of these fields, proceed exactly as today -- the live SQL gates decide SQL-managed status and the action lane stays available (normal for CLI usage and older hosts). Field emission is host-gated by the `_DP_AI_ENABLE_OPENFLOW_OBSERVABILITY_SQL_ACTIONS` rollout, so absence is expected pre-rollout and is **never** treated as `'false'`. On disagreement between snapshot sources (page context vs prompt fields, both hints), prefer the page-context value -- it reflects what the customer is looking at; this ordering is between snapshots only, and live `SHOW`/`DESCRIBE` outranks both. Namespace is load-bearing: see the precedence note under [Derived Variables](#derived-variables). [Namespace Validation](#namespace-validation) still runs against the chosen namespace unchanged, so a stale or bad page-context payload fails closed there.

### Active Content Catalog

`activeContent`, when non-empty, is a deduped error catalog whose initial grouping matches the **Error Pattern Summary** query in `references/core-queries.md` (grouped by `logger_name` + `error_message`). The catalog then adds post-processing (top-20 truncation, stack-trace compaction, cadence labels); see [Trust Boundary](#trust-boundary) below for exclusions.

Payload shape:

- `Summary:` rollup line containing total pattern count, total occurrence count, and the snapshot window.
- Top 20 patterns formatted as `- [<count>x | <duration> | <pattern>] <title> -- last <iso>`, where:
  - `<pattern>` = the grouped key (logger name plus normalized error-message signature; matches the Error Pattern Summary `GROUP BY 1, 2` tuple).
  - `<title>` = the representative first line of the error message for that group.
- Summarized stack traces for the top 10 patterns.
- Cadence labels on each pattern: `burst` (>=80% of occurrences in two 10% time buckets), `escalating` (>=60% in the trailing 30%, back-loaded), `decaying` (>=60% in the leading 30%, front-loaded).

### Trust Boundary

Page context is a snapshot bounded by `{start_time}` / `{end_time}`, not a live source of truth.

**What the catalog excludes** (absence in the catalog is not proof of absence in the event table):

- Tail patterns below the top-20 cutoff
- Sample causes for groups 11+ (count and cadence only)
- Stack frames in: `java.util.concurrent.*`, `java.lang.reflect.*`, `java.lang.Thread*`, `jdk.internal.*`, `sun.reflect.*`, `org.apache.nifi.engine.*`, `org.apache.nifi.controller.service.StandardControllerServiceNode`, `org.apache.nifi.util.ReflectionUtils`
- Frames beyond the top 5 per throwable; cause text beyond 500 bytes
- Anything that arrived after the snapshot was taken

#### Tiered Confirmatory-Query Rule

| Output type | Confirmatory event-table query? |
| --- | --- |
| Restating what the catalog shows | MAY skip |
| Routing to a connector-specific reference for follow-up reading | MAY skip |
| Re-running Recent Error Logs or Error Pattern Summary purely to confirm the catalog, when `activeContent` is non-empty and its window matches `{start_time}`/`{end_time}` | MAY skip |
| **Writing recovery guidance** (restart, reconfigure, escalate) | **MUST run** |
| **Asserting a root cause** | **MUST run** |
| **Forward-looking claim** ("ongoing", "resolved", "escalating right now") | **MUST run** |
| **Any CDC FAILED-state recovery** | **MUST run** the CDC Table Replication State query regardless of catalog |

The confirmatory query MUST filter for the routed pattern (logger family, message ILIKE, processor name, or connector PG ID) within `{start_time}` / `{end_time}`. Re-fetching the same Error Pattern Summary view does not satisfy this rule.

**Pattern label caveat.** `burst` / `escalating` / `decaying` describe the snapshot window only. Do not write "the issue is escalating" without a confirmatory query showing recent timestamps still fall in an active window. Acceptable without verification: "over the dashboard window, errors were back-loaded".

**Disagreement rule.** If the confirmatory query and catalog disagree, trust the query and note the discrepancy ("dashboard view may be cached -- the live query shows X").

---

### Discovery Sequence (High-Level Troubleshoot)

After the [Startup Sequence](#startup-sequence-run-first) is complete, when the customer triggers troubleshooting without a specific error (connector is unhealthy but no error was selected), fire the primary parallel batch first; fall back to validation queries only on zero-row outcomes. All queries are in `references/core-queries.md` unless noted.

1. **Primary parallel batch.** Fire these in **one parallel batch**. Do not serialize -- COALESCE-based schema handling in each query removes the need for a blocking shape check.

   - **Namespace + Shape Probe.** Answers both "does `{namespace}` have recent logs?" and the field-access pattern in one round-trip. Its validity is implicitly proven once any other query in the batch returns rows. **MAY be skipped** when the page-context fast path applies (see skip conditions below). When skipped, set `{field_pattern}` = `record_attributes`, `{probe_run}` = `skipped`, and proceed as if the probe returned rows.
   - **Recent Error Logs.** **MAY be skipped** when the page-context fast path applies (see skip conditions below). When skipped, route from the catalog (same `logger_name` + `error_message` dedup grouping as Error Pattern Summary). Confirmatory rules in [Tiered Confirmatory-Query Rule](#tiered-confirmatory-query-rule) still gate recovery guidance, root-cause claims, and forward-looking statements.
   - **Error Pattern Summary.** **MAY be skipped** when the page-context fast path applies (see skip conditions below). `activeContent` is already deduped by the same `logger_name` + `error_message` grouping. Run it when the catalog is empty, the window has shifted, or counts for patterns ranked 21+ are needed.
   - **CDC Table Replication State** (`references/core-queries-resource.md`). **Always run for CDC connectors** (`postgresql`, `mysql`, `sql_server`, `oracle`) regardless of the primary error signal. A FAILED table from a prior incident can coexist with an unrelated current error -- fire it in this batch, not as a follow-up. Never skipped by the fast path: CDC table state is not represented in `activeContent`.

   **Page-context fast path skip conditions (all must be true).** Apply equally to the Namespace + Shape Probe, Recent Error Logs, and Error Pattern Summary bullets above; any one of them MAY be skipped only when every condition below holds:

   1. `get_page_context` returned a payload.
   2. `activeContent` is non-empty.
   3. `{start_time}` / `{end_time}` equal the snapshot window at the moment of the skip decision -- i.e., still the values set from `timeWindowStart` / `timeWindowEnd` on page-context load. If the agent has narrowed (or otherwise changed) the window mid-session to drill into a sub-incident, the fast path no longer applies and the queries must be run.
   4. `{namespace}` came from page context (not derived locally from `runtime_name`).

   If any condition is false, run the corresponding query as normal. The fast path fails closed: zero-row outcomes from later queries still trigger the broadening [Namespace Validation](#namespace-validation) query.

2. **Branch on results.**

   | Primary batch outcome | Next action |
   | --- | --- |
   | Recent Error Logs returns rows | Proceed to step 3. Namespace validity is implicitly proven; `{field_pattern}` is informational. |
   | Probe skipped via page-context fast path | Treat as "probe returned rows with `record_attributes`". Namespace validity is satisfied by non-empty `activeContent`. Proceed to step 3. |
   | Recent Error Logs also skipped via page-context fast path | Treat `activeContent` as the error data for routing and triage (same `logger_name` + `error_message` grouping). Proceed to step 3. Before any recovery guidance, root-cause claim, or forward-looking statement, satisfy the [Tiered Confirmatory-Query Rule](#tiered-confirmatory-query-rule) with a scoped query on the routed pattern. |
   | Recent Error Logs returns zero rows AND Namespace + Shape Probe returns rows | Namespace is valid; runtime may be healthy in the window or errors only exist in raw `value`. Run **Generic Raw Log Fallback**. If still zero, run **Event Time Bounds Check**, then broaden per [Time Filtering](references/core-guidelines.md#time-filtering). |
   | Namespace + Shape Probe returns zero rows | Run the broadening query in [Namespace Validation](#namespace-validation) (`LIKE 'runtime-%'`). Do not proceed with any further diagnostic queries until the namespace is confirmed. |
   | Probe returns rows but both `record_attributes` and `TRY_PARSE_JSON(value)` fields are NULL (`raw_text`) | Skip standard filtered queries. Use **Generic Raw Log Fallback** for the session. |

3. **Cause-chain drill-down (optional).** When multiple logger families need throwable / cause-chain context, **Load** `references/core-queries-fallbacks.md` and run **Throwable Cause Chain (Top Loggers)** once instead of firing one cause-chain query per logger.

4. **Zero-error fallbacks.** If the primary batch returned zero rows despite confirmed symptoms:
   - **Runtime Workflow Failures** (in `references/troubleshoot-runtime.md`) for runtime creation/upgrade failures.
   - **Stuck FlowFiles** (`references/core-queries-resource.md`) for backpressure without error logs.
   - **DPS Heartbeat Check** (in `references/core-queries-resource.md`) if the deployment appears Inactive or Not Reporting.

5. **Categorize findings.** Scan logger names and error messages against the [Triage Router](#triage-router). Rank by significance.

6. **Present findings overview.** Before writing CDC recovery guidance, apply [CDC Guardrails](#cdc-guardrails-apply-early). Before drilling into any single category, summarize all discovered error categories with counts and most recent timestamp. If only one category is present, proceed directly to step 7. If multiple, identify the most impactful and propose investigating it first.

7. **Route and load reference.** Based on the dominant error pattern, route via the [Triage Router](#triage-router) or [Connector Type Routing](#connector-type-routing). Load and read the routed reference file before writing diagnostic output. If no errors and no resource issues found, verify the event table is receiving data (run Deployment Info from `references/core-queries-resource.md`) and confirm with the customer whether the issue is still occurring.

> **Trust Boundary.** Before writing recovery guidance, asserting a root cause, or making a forward-looking claim, run a scoped confirmatory query filtered on the routed logger family / message / processor / connector PG ID within `{start_time}`/`{end_time}`. See [Tiered Confirmatory-Query Rule](#tiered-confirmatory-query-rule). Re-running Error Pattern Summary does not satisfy this rule.

### CDC Guardrails (Apply Early)

For CDC connectors (`postgresql`, `mysql`, `sql_server`, `oracle`), apply these rules before writing conclusions:

- **The CDC startup bundle must already be loaded from the [Startup Sequence](#startup-sequence-run-first).** If you reach this section and any file from the CDC bundle is missing, stop and go back to step 3 of the Startup Sequence. Do not write recovery guidance until the full CDC startup bundle is loaded.
- **FAILED is terminal.** A table in `FAILED` will not recover automatically. Do not tell the customer to wait for retries.
- **Recovery steps come from the [Restart Table Replication](#restart-table-replication) procedure below.** The safety preamble (Before Recommending a Restart, When to Escalate Instead) lives in `references/connectors/connector-shared-cdc.md`; re-read it before recommending a restart. Do not summarize, improvise, or guess restart steps from memory or from per-connector files alone.
- **Fix source/destination root cause first, then decide whether table restart is needed.** Correcting the source problem alone does not revive a table that is already in `FAILED`.
- **Run CDC Table Replication State for every CDC investigation.** Even if the primary error is obvious, confirm whether any tables are already in `FAILED`, `NEW`, or stuck in `SNAPSHOT_REPLICATION`. Fire it in the [Discovery Sequence](#discovery-sequence-high-level-troubleshoot) primary parallel batch alongside Recent Error Logs; do not serialize it behind the error scan or the CDC Error Log Scan.
- **Keep the investigation scoped to the target connector.** In multi-connector runtimes, do not generalize CDC findings from unrelated logger families or unrelated tables. Only act on CDC table-state rows that tie back to the reported connector via the affected table name or matching CDC error-log evidence.
- **No restart button exists in the Openflow UI.** Recovery is the customer-run [Restart Table Replication](#restart-table-replication) procedure below. Do not invent a UI shortcut.
- **FAILED tables do not self-heal.** Do not tell the customer to "wait for retries" or "restart the connector" for a FAILED table. The only recovery is the [Restart Table Replication](#restart-table-replication) procedure. A connector restart or runtime restart does not clear FAILED state.

### Restart Table Replication

> **CDC connectors only.** This procedure applies exclusively to CDC connectors (`postgresql`, `mysql`, `sql_server`, `oracle`). Do not use it for non-CDC connectors; those do not have per-table replication state and have no equivalent recovery path.

> **USE THIS SECTION VERBATIM**
> Canonical restart procedure. All per-connector files and `connector-shared-cdc.md` defer to this section. Do not improvise, shorten, or paraphrase these steps. Present them to the customer exactly as written, substituting only the table-specific values.

**This is a last resort for the affected table only.** Restarting table replication drops the destination table and re-snapshots from source. For production tables this can mean hours or days of re-ingestion depending on data volume. Exhaust all less destructive options first. Do not generalize into a connector-wide reset.

**Step 3 is irreversible.** Dropping the destination table removes all its data. Time Travel `UNDROP TABLE` may recover it within the retention window (default 1 day) but is not a safety net -- confirm the correct table name and customer acceptance before step 3.

Present the warnings above together with the steps below in a single response so the customer sees the impact and the procedure at the same time. Do not withhold the steps pending a confirmation turn. Point the customer to the relevant connector maintenance documentation when available.

Only provide these steps after the root cause is fixed and the table is confirmed still in FAILED (see Before Recommending a Restart in `references/connectors/connector-shared-cdc.md`):

1. In the Openflow UI, update `Included Table Names` and `Included Table Regex` so the affected table is excluded from replication.
2. Verify the table state has been removed in the Openflow UI: right-click the connector canvas > Controller Services > `Table State Store` > **View State**. Do not continue until the affected table no longer appears there.
3. Drop the destination table in Snowflake for that table only (all existing data in that table is lost). The connector will NOT overwrite an existing destination table, so skipping this step causes immediate re-failure.
4. Update `Included Table Names` and `Included Table Regex` again so the affected table is included in replication.
5. Verify the table reappears in `Table State Store` and progresses through `NEW`, then `SNAPSHOT_REPLICATION`, and finally `INCREMENTAL_REPLICATION`.

### Variable Substitution Rule

Before presenting any SQL to the customer, substitute **all** known variables. Never show raw `{placeholder}` values when the value is known. Never echo passwords, private keys, API keys, or other secrets.

**Multiple candidates:** If a SHOW/DESCRIBE returns multiple values for a variable, present candidates to the customer and ask them to confirm.

### Runtime Scoping Rule

For runtime and connector investigations, scope event-table queries to the routed runtime and the affected connector context when known. In multi-connector runtimes, do not treat all CDC errors in the namespace as belonging to the same connector until the logger family, message, or table state evidence ties them to the reported connector. Apply the namespace filter:

```sql
AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
```

When a single runtime hosts multiple connectors and namespace scoping is too broad, narrow to one connector's process-group subtree using [Per-Connector Scoping (Multi-Connector Runtimes)](references/core-queries.md#per-connector-scoping-multi-connector-runtimes) -- discover the connector's `processGroupNamePath` from the data, then filter by prefix. It fails soft to logger-family / message scoping when the field is absent.

### Connector Type Routing

**Normalize common aliases before routing:** `postgres` -> `postgresql`, `mssql` or `sqlserver` -> `sql_server`.

When `connector_type` is present or inferred, the startup bundle is already loaded from [Startup Sequence](#startup-sequence-run-first) step 3. Use the matching router for routing decisions inside that already-loaded bundle: database CDC connectors (`postgresql`, `mysql`, `sql_server`, `oracle`) use `references/connectors/connector-router-cdc.md`; all other connector types use `references/connectors/connector-router-non-cdc.md` after loading the matching Non-CDC or SaaS/API bundle.

**Bundle rule:** Use the startup bundle from [Startup Sequence](#startup-sequence-run-first). Direct error-signal routing can change which query or section you use first, but it does not change which bundle must already be loaded.

**Discovery-first gate:** When `error_message` is absent entirely (high-level troubleshoot, no specific error selected), do NOT route to a connector-specific file immediately. First run Recent Error Logs and Error Pattern Summary to discover errors, then use the results to route via the Triage Router or connector type routing. This prevents loading a narrow connector-specific diagnostic when the root cause may be runtime-level, network, or shared destination.

**Routing gate:** Do not route via the Triage Router until `connector_type` is known. If `connector_type` is missing from the input, use the [Startup Sequence](#startup-sequence-run-first) step 3 bootstrap first, then load the required bundle before continuing. If inference fails, use the Ambiguous or Unknown Errors path.

**CDC fast path:** If `connector_type` is already known and an error signal is clearly source-CDC origin (for example binlog/WAL issues, replication slot/stream failures), proceed directly to the relevant section in the already-loaded `references/connectors/connector-router-cdc.md`. Fast path changes the first query or section, not the loading rule from [Startup Sequence](#startup-sequence-run-first) step 3. Do not fast-path on table FAILED alone (that state can arise from Snowflake-side causes). If `error_message` is absent, apply the Discovery-first gate regardless of `connector_type`.

### Namespace Validation

See [Namespace Validation](references/core-guidelines.md#namespace-validation) in `core-guidelines.md` for the validation and broadening queries. The **Namespace + Shape Probe** in `references/core-queries.md` satisfies this check implicitly when it returns rows; fall back to the broadening query there only on zero-row outcomes.

When the probe is skipped via the page-context fast path (see [Page-context fast path skip conditions](#discovery-sequence-high-level-troubleshoot) in Discovery Sequence step 1), namespace validation is satisfied by the non-empty `activeContent` -- data was returned for that namespace at snapshot time. The broadening query still applies if a later query unexpectedly returns zero rows.

---

## Triage Router

Route connector issues to the appropriate diagnostic file. Use the first match.

**Prerequisite:** `connector_type` must be known before using this table. If it is missing from the input, infer it first, then load the required bundle. See [Connector Type Routing](#connector-type-routing) for the routing gate.

**Schema prerequisite:** The **Namespace + Shape Probe** from `references/core-queries.md` (fired in the [Discovery Sequence](#discovery-sequence-high-level-troubleshoot) primary parallel batch) satisfies this check. If you arrived here without running the probe or Discovery Sequence, run it now.

| Error Signals | Route To | Notes |
| --- | --- | --- |
| `SnowflakeConnectionService` INVALID, `PutSnowpipeStreaming` auth/role/warehouse errors, `PutSnowpipeStreaming` channel invalidation/INHERITED state, `No active warehouse selected`, destination SQL compilation errors, `does not exist or not authorized`, `ClassNotFoundException` (JDBC driver), `Failed to invoke @OnEnabled`, controller service INVALID/ENABLING, `PrivateKeyService` INVALID/ERROR, `insufficient privileges`, shared Snowflake-side processor failures | `references/connectors/connector-shared-generic.md` | Shared destination-side and controller service failures across connector types |
| Connector stuck in DRAFT, "Edits not applied", `LIVE_VERSION_LOCATION_URI` non-NULL with no default, missing-driver `assetIds:null`, missing publication name, wrong connection URL after a known good baseline | `references/openflow-sql/connector-diagnostics.md` | Routes through the [DRAFT Connector Fast-Path](references/openflow-sql/connector-diagnostics.md#draft-connector-fast-path), [Stuck-Driver Fast-Path](references/openflow-sql/connector-diagnostics.md#stuck-driver-fast-path-assetids-is-null), and [Connector Config Snapshot](references/openflow-sql/connector-diagnostics.md#connector-config-snapshot-read-only). After diagnosis, propose the corresponding allowlisted connector action only via the [Openflow SQL Action Mode](#openflow-sql-action-mode) gates. |
| Table FAILED, replication stuck, binlog/WAL lag, CDC errors, snapshot failures, CDC engine errors, INCREMENTAL_REPLICATION stopped | `references/connectors/connector-router-cdc.md` | CDC connectors; router directs to per-connector file. The full CDC bundle is already loaded from [Startup Sequence](#startup-sequence-run-first) step 3. |
| Non-CDC connector errors, processor failures, config errors, SaaS auth, Kafka consumer, Kinesis KCL, Salesforce bulk, rate limiting | `references/connectors/connector-router-non-cdc.md` | Non-CDC connectors; router directs to per-connector file |
| UnknownHostException, EAI, network rule, connection refused, timeout to external host, SocketTimeoutException, SSLHandshakeException, DNS resolution | `references/troubleshoot-network.md` | Network issues blocking connector operation |
| Create failed, WaitForRuntime*, OOM, heap exhausted, stuck Upgrading, SSL/TLS error, pod crash, runtime restart, UPGRADE_FAILED, CREATING stuck | `references/troubleshoot-runtime.md` | Runtime-level issues surfacing as connector symptoms |
| No clear match from the above rows | See **Ambiguous or Unknown Errors** section below | Run Recent Error Logs first |

**Precedence:** Error-signal routing in the Triage Router takes precedence over `connector_type` routing. After the signal-matched file is loaded, carry `connector_type` context for any sub-routing within that file.

---

## Ambiguous or Unknown Errors

When the error signals do not clearly match a route in the [Triage Router](#triage-router), follow the [Discovery Sequence](#discovery-sequence-high-level-troubleshoot) -- the primary parallel batch plus its zero-row branches already cover this case. Specifics that apply when the first pass returns zero rows:

- **Scheduled connectors or incidents with a known `{error_timestamp}`:** use a bounded incident window around that timestamp, or extend to cover one full schedule cycle. Do not broaden with `{hours_back}` expansion when a specific timestamp exists.
- **Other connectors:** expand per [Time Filtering](references/core-guidelines.md#time-filtering) (2h -> 6h -> 24h).
- **Event table has data but no errors:** the issue may have self-resolved or be runtime-level. Verify with the customer before closing.
- **Errors span multiple categories:** follow step 6 of the Discovery Sequence -- summarize each category with counts and most recent timestamp, then investigate the most impactful first.
- **Still unclear after the above:** only escalate if the pattern indicates a Snowflake-internal failure with no customer action.

---

<a id="openflow-sql-action-mode"></a>
## Openflow SQL Action Mode (Narrow Allowlist)

> Customer-facing name: **Openflow SQL Action Mode**.

This mode is the only path that lets the skill execute mutating SQL on the customer's account. It is OFF by default. It activates only when the [Intent Router](#intent-router-run-first) selects the SQL action lane or a Troubleshoot finding produces an allowlisted action candidate.

**Hard gates before any mutating SQL.** Load `references/openflow-sql/action-guidelines.md` and apply its five gates in order: intent, live SQL action support, allowlist, exact confirmation, and list-property preservation. Stop and revert to read-only guidance if any gate fails. Page-context hints can route the check but cannot authorize mutation. When `openflowSqlActionsEnabled` is present-and-`'false'`, the support gate short-circuits to read-only before any SQL -- see [Session feature-flag pre-filter](references/openflow-sql/action-guidelines.md#session-feature-flag-pre-filter-no-sql-negative-only).

**Allowlist index only.** The canonical table is `references/openflow-sql/action-guidelines.md > ## Action Allowlist (MVP)` and wins on any discrepancy. Current action families:

- Runtime / deployment metadata and lifecycle: `references/openflow-sql/runtime-actions.md`, `references/openflow-sql/deployment-actions.md`
- Connector lifecycle (`START`, `STOP`, `COMMIT`, `ABORT`): `references/openflow-sql/connector-actions.md`
- Connector config-content edits (single STRING_LITERAL property; ASSET_REFERENCE `assetIds` for a customer-staged JAR): `references/openflow-sql/connector-config-edit.md`

Everything not in the canonical table is guide-only or UI/admin-owned, including `EXECUTE_AS_ROLE`, `CREATE`, `TERMINATE`, `DROP`, `UPGRADE`, connector metadata SET/UNSET, full-config replacement, SECRET_REFERENCE writes, `[RECOVERY]` modifiers, and admin DDL (`GRANT`, `CREATE NETWORK RULE`, `CREATE EXTERNAL ACCESS INTEGRATION`).

**During execution.** Run only the previewed SQL. Do not chain additional mutating statements that were not previewed. Always preserve list properties (`EXTERNAL_ACCESS_INTEGRATIONS`) by reading the current list first and unioning the new value. Each response renders at most ONE Confirmation Preview -- multi-step plans become multiple sequential responses, each with its own confirmation. See [One preview per response](references/openflow-sql/action-guidelines.md#confirmation-preview-format).

**After execution.** Run the verification query (typically `DESCRIBE OPENFLOW RUNTIME`, with optional event-table follow-up scoped to `{namespace}` for state-change confirmation) and report the before/after state.

**Admin DDL Assist (Deferred).** `GRANT`, `CREATE NETWORK RULE`, and `CREATE EXTERNAL ACCESS INTEGRATION` remain Snowflake admin operations and are NOT part of the MVP allowlist. When diagnostics point to one of these, load `references/openflow-sql/admin-ddl-assist.md` and propose the exact SQL as customer-run guidance instead.

To enter this mode, **Load** `references/openflow-sql/action-guidelines.md` and the matching action template file:

- `references/openflow-sql/runtime-actions.md` for runtime / EAI actions
- `references/openflow-sql/deployment-actions.md` for deployment metadata actions
- `references/openflow-sql/connector-actions.md` for connector lifecycle actions (start, stop, commit, abort)
- `references/openflow-sql/connector-config-edit.md` for connector config-content edits (STRING_LITERAL property, ASSET_REFERENCE assetIds)

All of these are Tier 2 -- only load when an action candidate exists.

---

## Alert Skill Handoff (Optional)

When the customer asks to set up OpenFlow monitoring alerts, or to troubleshoot existing OpenFlow monitoring alerts, during or after troubleshooting, do not improvise alert SQL in this skill.

**Load** `references/alert-skill-handoff.md` and follow it end-to-end.

---

## Reference Index

Every file listed below is classified as **Tier 1 (always loaded at startup)** or **Tier 2 (load on demand)**. Do not load Tier 2 files during startup or Discovery Sequence unless the specific trigger below applies.

### Tier 1: Always Loaded (Startup Bundle)

Loaded unconditionally during Startup Protocol step 3:

| Reference | Purpose |
| --- | --- |
| `references/core-guidelines.md` | Diagnostic-mode rules (read-only SQL only), SPCS/BYOC differences, output patterns, time filtering, query mechanics, and the diagnostic / Openflow SQL action mode split |
| `references/core-queries.md` | Core triage queries: Namespace + Shape Probe, Recent Error Logs, Error Pattern Summary, Active Connectors |

The routed family bundle (see [Discovery Sequence](#discovery-sequence-high-level-troubleshoot) step 3) is also Tier 1 once `connector_type` is known. `references/core-queries-resource.md` is Tier 1 for CDC connectors (required for CDC Table Replication State) and Tier 2 otherwise.

### Tier 2: Load On Demand

Do not load during startup. Load only when the trigger in the right column is hit:

| Reference | Load when |
| --- | --- |
| `references/core-queries-fallbacks.md` | Drill-down after the primary parallel batch: Normalized Error Pattern Summary (rank 21+), Throwable Cause Chain (Top Loggers) |
| `references/core-queries-resource.md` | Non-CDC investigations needing DPS Heartbeat Check, Deployment Info, Resource Utilization, or Active Connectors details |
| `references/troubleshoot-runtime.md` | Runtime OOM, stuck upgrading, SSL errors, crash loops (fallback from connector investigation) |
| `references/troubleshoot-network.md` | EAI, network rules, connectivity failures |
| `references/escalation.md` | Drafting an escalation to Snowflake support (template + philosophy) |
| `references/public-docs.md` | Citing Snowflake documentation in a customer-facing response |
| `references/alert-skill-handoff.md` | Relay from Openflow troubleshooting into Alert skill setup or alert troubleshooting, with carryover context |
| `references/openflow-sql/action-guidelines.md` | Openflow SQL Action Mode: trust boundaries, support detection, allowlist/denylist, confirmation protocol |
| `references/openflow-sql/admin-ddl-assist.md` | Customer-run admin DDL guidance for proven missing grants, network rules, or external access integrations. Load only when diagnostics prove one of these gaps. |
| `references/openflow-sql/runtime-actions.md` | Openflow SQL action templates for runtime / EAI: attach EAI, restart, suspend, resume, update or clear runtime metadata |
| `references/openflow-sql/deployment-actions.md` | Openflow SQL action templates for deployment metadata: `deployment.set_display_name`, `deployment.set_comment`. Requires deployment `OWNERSHIP`. Load when an explicit user request targets a deployment-level metadata change. |
| `references/openflow-sql/connector-actions.md` | Openflow SQL action templates for connector lifecycle: start, stop, commit, abort. Load when the user explicitly requests a connector lifecycle change, or when diagnosis points to a stuck connector that needs commit/abort. |
| `references/openflow-sql/connector-config-edit.md` | Openflow SQL action templates for connector config-content edits via the stage-promote path (`ADD VERSION FROM '@stage'`): set a STRING_LITERAL property, set ASSET_REFERENCE `assetIds` for a driver JAR. Load when the user asks to fix a config field or wire up a missing driver. |
| `references/connectors/postgresql-sql-managed.md` | Validating SQL-managed Postgres CDC (`OPENFLOW_POSTGRES_CDC`) property values before a config edit; diagnosing `Value is not one of the allowable values` validation errors after a config edit; secret-reference (`SECRET_REFERENCE`) diagnostics and grant checks; `UPDATE_FAILED` lifecycle pitfalls and `CREATE FROM '@<stage>'` parameter-context binding. |
| `references/connectors/mysql-sql-managed.md` | Validating SQL-managed MySQL CDC (`OPENFLOW_MYSQL_CDC`, PrPr) property values before a config edit; diagnosing `Value is not one of the allowable values` validation errors after a config edit; MariaDB driver / `jdbc:mariadb://` URL forms, `Starting Binlog Position` / `Re-read Tables in State`, `Destination Schema Strategy` values; `SECRET_REFERENCE` diagnostics and `UPDATE_FAILED` lifecycle pitfalls. |
| `references/openflow-sql/connector-diagnostics.md` | Read-only Openflow SQL diagnostics: `SHOW OPENFLOW CONNECTOR DEFINITIONS`, `SHOW VERSIONS`, `SHOW GRANTS ON OPENFLOW RUNTIME`, DRAFT-connector fast-path (with stuck-driver routing), config-snapshot helper, post-action error scan. Load when a controller service is INVALID/ENABLING, a connector appears stuck in DRAFT or "Edits not applied", privilege-error evidence is needed, `config.json` content needs to be inspected for cause-chain analysis, or a gated SQL action needs post-action validation. |
| `references/openflow-sql/connector-support-matrix.md` | Single source of truth for which connector definitions are SQL-managed today, their minimum parent `NODE_TYPE`, their family (CDC vs non-CDC), their driver `ASSET_REFERENCE` property name, and their common `STRING_LITERAL` fix-candidates. Consulted by `references/openflow-sql/action-guidelines.md`, `references/openflow-sql/connector-actions.md`, `references/openflow-sql/connector-config-edit.md`, and `references/connectors/connector-shared-cdc.md`. Load whenever the active action template needs to evaluate a connector-definition-specific gate (node-size, CDC family, available fix-candidates). |
| `references/openflow-sql/account-usage.md` | Historical context for SQL-managed runtimes/deployments via `ACCOUNT_USAGE.OPENFLOW_*` views (last resumed, last altered, recently deleted). Load when "when did this last change?" or recently-deleted-orphan questions arise. |

### Connector Routing (Loaded via Startup Bundle)

Loaded as part of the family bundle once `connector_type` is known. Not independently Tier 2; they arrive via the startup path.

| Reference | Purpose |
| --- | --- |
| `references/connectors/connector-router-cdc.md` | CDC connector triage entry point, routing table, and error-log scan |
| `references/connectors/connector-router-non-cdc.md` | Non-CDC connector triage entry point, routing table, and initial runtime-scoped checks |
| `references/connectors/connector-shared-cdc.md` | Shared CDC decision tree, state machine, recovery impact guidance, error aggregation |
| `references/connectors/connector-shared-generic.md` | Generic patterns: validation, bulletins, backpressure, dashboard, escalation |
| Per-connector files (under `references/connectors/`) | Per-connector troubleshooting, allowlists, source setup. Resolved via the router's mapping table; current files: `postgresql.md`, `mysql.md`, `sql-server.md`, `oracle.md`, `kafka.md`, `kinesis.md`, `salesforce.md`, `saas-connectors.md`, `sharepoint.md`, `google-drive.md`, `box.md`, `microsoft-dataverse.md`, `ads-connectors.md`. Names also listed in the CDC and non-CDC router files |
