---
name: openflow-observability-core-guidelines
description: Core context for Openflow diagnostics. Always load. Read-only diagnostic SQL is the default; mutating SQL is only allowed via the separate Openflow SQL Action Mode reference.
---

# Core Guidelines

This file establishes the rules all other diagnostic files follow.

> **Customer-Facing Naming.** When speaking to the customer, always use "Openflow SQL actions" (the lane / mechanism) and "SQL-managed runtime" (a runtime that supports them).

## Scope

- Diagnostic-mode SQL constraints (read-only)
- Boundary with the Openflow SQL Action Mode (mutating SQL)
- SPCS vs BYOC telemetry differences
- Event table parameterization
- Output pattern for customer communication
- Permission boundaries
- Escalation pattern

---

## Mode Boundary

The skill operates in one of two modes at a time:

| Mode | Purpose | SQL allowed |
| --- | --- | --- |
| **Diagnostic mode (default)** | Identify root causes; tell the customer what to check or change | Read-only SQL (`SELECT`, `SHOW`, `DESCRIBE`) and non-destructive session context (`USE ROLE`, `USE WAREHOUSE`, `USE DATABASE`, `USE SCHEMA`) |
| **Openflow SQL Action Mode** | Execute a narrow allowlist of Openflow runtime, deployment, connector lifecycle, and connector config-edit statements after explicit user confirmation | The allowlist defined in `references/openflow-sql/action-guidelines.md` only, after every gate in [Openflow SQL Action Mode in SKILL.md](../SKILL.md#openflow-sql-action-mode) passes |

This file (and every other diagnostic-side reference) governs **diagnostic mode**. The Openflow SQL Action Mode is OFF unless `references/openflow-sql/action-guidelines.md` has been loaded and all five hard gates have passed.

---

## Diagnostic Mode SQL Constraint

This is a customer-facing troubleshooting skill. The agent identifies root causes through Snowsight-accessible diagnostics and then tells the customer what they can check or change on their side. In diagnostic mode the agent does NOT execute mutating SQL or runtime actions itself.

**Can do:**
- Execute read-only SQL (SELECT, SHOW, DESCRIBE) against the event table and account objects
- Execute non-destructive session context statements when required for diagnostics (for example `USE ROLE`, `USE WAREHOUSE`, `USE DATABASE`, `USE SCHEMA`)
- Interpret query results and identify root causes
- Explain customer-run remediation when the action is customer-controlled and publicly documented
- Propose an Openflow SQL action candidate (for example "attach EAI X to runtime Y") that, if the customer accepts, hands off to the Openflow SQL Action Mode under its own gates
- Escalate to Snowflake support only when the issue requires Snowflake-internal access or engineering intervention (see [Escalation](#escalation))

**Run Snowsight-accessible diagnostics yourself.** Do not ask the customer to run queries that you can run in Snowsight. If verification must happen outside Snowsight, such as on the customer's source database, cloud network, or Openflow UI, explicitly label it as a customer-run check.

**Warehouse prerequisite:** Before running diagnostic queries, ensure an active warehouse is set on the session. If queries fail with "No active warehouse selected", use an already-approved warehouse in the session or ask the customer which warehouse should be used. Do not assume a warehouse named `OPENFLOW` exists.

**Stage-listing canonical form:** the agent always emits `LIST '@<stage>'`, never the SnowSQL alias `LS`. `LIST` parses identically across SnowSQL, Snowsight, JDBC, ODBC, and REST; `LS` may parse-error in some surfaces.

**Cannot do in diagnostic mode:**
- Execute or "preview-then-run" mutating SQL (`ALTER`, `CREATE`, `DROP`, `GRANT`, `TRUNCATE`, `TERMINATE`, `UPGRADE`, `RESTART`, `RESUME`, `SUSPEND`, connector `COMMIT`/`ABORT`). Mutations live exclusively in the Openflow SQL Action Mode and only for the allowlist there.
- Access the NiFi REST API (no nipyapi, no curl to runtime)
- Modify runtime state directly (no start/stop processors)
- Restart pods or containers
- Access internal Snowflake systems (Snowhouse, eng_cloud)
- View the Openflow UI on behalf of the customer
- Execute shell commands, scripts, or file system operations on any host

When the root cause requires remediation, separate customer-owned actions from Snowflake-owned actions:
- Customer-owned: explain what the customer should change and include a public doc link when possible
- Allowlisted Openflow SQL action on a SQL-managed runtime: propose the action and let the Openflow SQL Action Mode handle it; do not execute from diagnostic mode
- Snowflake-owned or internal-only: explain why support is required and include the diagnostic evidence

---

## Agent-Run Versus Customer-Run Work

Use this split consistently in every response:

- **Agent-run:** Snowsight SQL against the event table and account objects, interpretation, triage, evidence gathering
- **Customer-run:** Openflow UI inspection and changes, source database checks and configuration, firewall and network changes, cloud-specific validation, Snowflake admin DDL in the customer's account

If a step is customer-run, say so plainly. Do not imply the agent can perform it.

## SPCS vs BYOC Telemetry Differences

Both deployment types write to the customer's event table, but the data available differs.

| Aspect | SPCS | BYOC |
|--------|------|------|
| Event table location | Customer-configured (typically `<db>.<schema>.EVENTS`) | Customer-configured (same) |
| Runtime namespace pattern | `runtime-<runtime-key>` | `runtime-<runtime-key>` |
| DPS pod name | `dataplane-service%` in namespace `dataplane-service` | `dataplane-service%` in namespace `openflow-runtime-infra` |
| Container metrics | Full (CPU, memory, disk, restart count) | Full (same) |
| Ingress / gateway logs | Not applicable -- SPCS uses openflow ingress | `%-gateway` container |
| Server logs | `%-server` container | `%-server` container |
| EAI/Network rules | Queryable via SQL (SHOW INTEGRATIONS, SHOW NETWORK RULES) | Not applicable -- direct network access |
| Deployment agent | `data-plane-agent` namespace in SPCS logs | Deployment agent runs outside K8s cluster |
| Cert manager | `trust-manager` in `cert-manager` namespace | Full cert-manager stack in `cert-manager` or `kube-system` namespace |

### Key BYOC Limitations for SQL Diagnostics

- Cannot verify cloud networking (security groups, NAT gateways, VPC peering) via SQL
- Deployment agent logs may not appear in the event table
- Cannot check EAI or network rules (they don't exist for BYOC)
- When network issues are suspected in BYOC, guide the customer to verify: (1) security group outbound rules allow the port/protocol, (2) NAT/internet gateway is configured, (3) VPC routing includes a route to the destination, (4) DNS resolves within the VPC. Adapt terminology for AWS/Azure/GCP.

---

## Event Table Parameterization

All query templates use `{placeholder}` variables. Variable substitution rules (input fields, derived variables, investigation-only variables, and the substitution rule itself) are defined in SKILL.md under [Variable Substitution Rule](../SKILL.md#variable-substitution-rule) -- apply them to all queries in this file and all reference files.

### Namespace Derivation

The runtime namespace is always `runtime-<key>`, where `<key>` is the runtime's internal key. Resolve `<key>` in this order:

1. **Page context** (preferred). When `get_page_context` returns a `namespace` field, use it directly -- it is already `runtime-<key>`.
2. **`DESCRIBE OPENFLOW RUNTIME <fqn>`** -- read the `key` field. This is the authoritative source whenever a warehouse is available.
3. **SOM identity fields (page context)** -- when page context indicates a SQL-managed connector (`isSom = 'true'`, or an `openflowConnectorId` is present -- gen1 connectors never carry one) but no pre-derived `namespace` was supplied, do **not** fall through to the name-sanitization heuristic below; it will silently miss the mandatory `-NNN` suffix. Resolve the authoritative `key` via `DESCRIBE OPENFLOW RUNTIME <fqn>` (step 2). If the runtime FQN is not yet known, resolve the connector FQN from the integer `openflowConnectorId` first (see [ID Resolution](openflow-sql/action-guidelines.md#id-resolution-and-namespace-mapping)), read its parent `RUNTIME`, then `DESCRIBE OPENFLOW RUNTIME` that.
4. **Name-sanitization heuristic** (gen1 fallback only) -- lowercase the runtime name, replace spaces with hyphens, prepend `runtime-`. Example: "My PostgreSQL" -> `runtime-my-postgresql`.

**The heuristic does not match SQL-managed (gen2, internally "SOM") runtimes.** SQL-managed runtime keys carry a numeric suffix (today allocated in the `-100`+ range; treat the exact range as illustrative, not a gen1-vs-SOM discriminator) assigned at creation (e.g. runtime "My PostgreSQL" -> key `my-postgresql-100` -> namespace `runtime-my-postgresql-100`). The suffix is allocated by scanning for the first free key in the account, so it is **not derivable from the runtime name** -- the heuristic will silently miss it. Gen1 runtimes carry a suffix only on a name collision. For any SQL-managed runtime, treat the heuristic output only as a seed for [Namespace Validation](#namespace-validation) and resolve the real key from page context or `DESCRIBE OPENFLOW RUNTIME`. When page context supplies `isSom='true'` or an `openflowConnectorId` but no pre-derived `namespace` (i.e. step 1 did not apply), prefer the authoritative resolution above (steps 2-3) and skip the heuristic (step 4) entirely.

**Multi-runtime deployments:** A deployment can have multiple runtimes. When the customer reports an issue, determine which runtime is affected. If unclear, query for all namespaces under the deployment and ask the customer to identify which runtime is exhibiting the issue.

### Namespace Validation

The **Namespace + Shape Probe** from `references/core-queries.md` satisfies this check implicitly whenever it returns rows. Use the dedicated queries below only when the probe returns zero rows, or when running outside the Discovery Sequence primary batch and no probe result is available.

Apply the [Time Filtering](#time-filtering) rules: use `{start_time}`/`{end_time}` when `time_window` is provided, otherwise fall back to `{hours_back}`.

```sql
-- When time_window is provided:
SELECT DISTINCT resource_attributes:"k8s.namespace.name"::STRING AS ns
FROM {event_table}
WHERE TIMESTAMP BETWEEN '{start_time}' AND '{end_time}'
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
LIMIT 5;

-- When time_window is not provided (hours_back fallback):
SELECT DISTINCT resource_attributes:"k8s.namespace.name"::STRING AS ns
FROM {event_table}
WHERE TIMESTAMP >= DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
LIMIT 5;
```

**If zero rows:** STOP. Do not proceed with any diagnostic queries. The most common cause is a SQL-managed runtime whose namespace carries a `-NNN` suffix the name-sanitization heuristic missed (see [Namespace Derivation](#namespace-derivation)).

- **If a warehouse is available, resolve the authoritative key first:** run `DESCRIBE OPENFLOW RUNTIME <fqn>` and read the `key` field, then retry the validation query with `{namespace}` = `runtime-<key>`. This is the precise fix and avoids guessing.
- **If no warehouse is available** (or the FQN is unknown), confirm the runtime name with the customer, then run the broadening query (using the same time filter pattern) and match the suffixed namespace:

```sql
-- When time_window is provided:
SELECT DISTINCT resource_attributes:"k8s.namespace.name"::STRING AS ns
FROM {event_table}
WHERE TIMESTAMP BETWEEN '{start_time}' AND '{end_time}'
  AND resource_attributes:"k8s.namespace.name"::STRING LIKE 'runtime-%'
ORDER BY ns
LIMIT 20;

-- When time_window is not provided (hours_back fallback):
SELECT DISTINCT resource_attributes:"k8s.namespace.name"::STRING AS ns
FROM {event_table}
WHERE TIMESTAMP >= DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING LIKE 'runtime-%'
ORDER BY ns
LIMIT 20;
```

Present results and ask the customer to identify which namespace corresponds to the affected runtime in the Openflow UI.

### Time Filtering

All queries in this skill use COALESCE to auto-select `{start_time}/{end_time}` when present and fall back to `{hours_back}` otherwise. Do not rewrite this pattern in ad-hoc queries.

Always include time bounds in queries. Default pattern:

```sql
AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
```

**Time window takes precedence** over `{hours_back}`. Do not apply the 2h -> 6h -> 24h expansion. If zero results within the window, tell the customer no errors were found in that date range and suggest widening it in the dashboard. For follow-up queries needing a different scope, use the incident-window pattern below.

For investigating specific incidents, use the error timestamp from the UI:

```sql
AND timestamp BETWEEN DATEADD(minute, -30, '{error_timestamp}') AND DATEADD(minute, 5, '{error_timestamp}')
```

For scheduled connectors or incidents older than 24 hours:
- Prefer a bounded incident window around `{error_timestamp}` over a broad 48h+ scan
- If no exact timestamp is available, extend only enough to cover one full schedule cycle for the routed connector
- Do not keep widening general runtime scans indefinitely; explain the time-window limitation if the incident has already aged out

**`{hours_back}` expansion (only when `time_window` is absent).** Start at 2h. Before broadening to 6h or 24h, run the **Event Time Bounds Check** in `references/core-queries.md` to confirm whether logs exist outside the current window. Do not expand beyond 24h in general runtime scans; switch to an incident window instead.

### Query Mechanics

- **Use `ILIKE`** for any text match -- event logs have mixed casing.
- **Parse JSON with `TRY_PARSE_JSON(value)`**. Unparseable rows return NULL silently -- they become invisible to any predicate built on parsed fields.
- **When parsed queries return fewer rows than expected or no root cause despite clear symptoms**, fall back to `value ILIKE '%error_text%'` on the raw column to catch unparseable rows. The **Generic Raw Log Fallback** in `references/core-queries.md` is the canonical pattern.

### Frequency Interpretation

- High count + recent `last_seen` = ongoing issue
- High count + regular cadence = retry loop; the processor is failing on schedule and will not self-resolve
- High count + old `last_seen` = may have self-resolved; report that the cause may be undetermined from current event-table data
- Single occurrence is not automatically transient. If the message explicitly names a missing object, invalid privilege, invalid credential, or invalid configuration, treat it as actionable even with `occurrence_count = 1`
- If counts look artificially low because each message embeds a connection ID, request ID, or UUID, use a normalized grouping query before concluding the error is isolated

### Multi-Connector Runtimes

When one runtime hosts multiple connectors or mixes source and destination failures in the same log stream:

1. Start with **Error Pattern Summary** scoped to `{namespace}` so unrelated runtimes do not pollute the result set.
2. Group issues by logger family before routing:
   - `com.snowflake.openflow.runtime.processors.database.*`, `ExecuteSQL` + `STREAM_HAS_DATA` -> CDC
   - `org.apache.nifi.processors.standard.LogMessage` with `SALESFORCE_BULK_API` -> Salesforce
   - `PutSnowpipeStreaming`, `SnowflakeConnectionService`, `SnowflakeDetectDuplicate`, `UpdateSnowflakeDatabase`, `ExecuteSQL` against destination tables -> shared Snowflake-side destination path
3. Separate shared Snowflake-side failures from source-specific failures before routing to connector pages. If one shared destination failure explains multiple connector symptoms, guide that fix first.
4. Route connector-specific issues separately only after isolating the shared runtime-wide failures.

---

## Output Pattern

**Be concise.** Customers are technical - don't over-explain, no filler, no preamble. Lead with the finding, not the reasoning.

Each diagnostic step produces:

1. **Finding** -- 1-2 sentences: what the query showed
2. **Next step** -- SQL to run, action to take, or escalation

Only add a "what it means" explanation when the finding is non-obvious or counterintuitive. Don't explain routine results.

### Output Formatting

- Run all diagnostic queries yourself -- don't ask the customer to run them
- No results = usually good news; say so in one line
- Many results = summarize the pattern, not individual rows
- If the error has already stopped recurring, say that plainly and label it as self-resolved or aged out when the root cause can no longer be proven from current logs
- Don't repeat information the customer already provided
- Don't narrate what you're about to do -- just do it

### Session Close

When resolved or escalated, summarize: (1) symptom, (2) root cause (or "undetermined"), (3) action taken/recommended, (4) verification result or next steps.

If the investigation is still in progress or inconclusive, clearly label the summary as **"Investigation in progress"** and list: (1) findings so far, (2) next diagnostic step pending, (3) what the customer can do while waiting (if anything).

**Always end with a final customer-facing summary.** Even on long workflows that fire many tool calls, the agent MUST conclude with a single user-visible message containing the summary above. Do NOT end the session on an internal tool call, a partial diagnosis, or a stage operation. Run-out-of-budget mid-investigation is a signal to write the summary now (with what's known so far, labeled "Investigation in progress") rather than to keep firing more diagnostic queries. The final summary is what the customer reads — without it, the session is incomplete regardless of how many SQL queries ran.

---

### Event Table Permission Recovery

If an event table query fails with access control errors:
1. Switch to the role with SELECT on the event table (typically the monitoring role from setup)
2. If unknown, run `SHOW GRANTS ON TABLE {event_table}` with ACCOUNTADMIN
3. Reference [Set up and access Openflow](https://docs.snowflake.com/en/user-guide/data-integration/openflow/setup-openflow-roles-login)

---

## Escalation

**Load** `references/escalation.md` when the investigation is about to hand off to Snowflake support. The file covers the escalation philosophy (when to escalate vs. when to guide customer-run fixes) and the escalation template with the diagnostic context to include.

---

## Cross-Category Investigation

When investigation in one diagnostic file reveals a root cause in a different category:

- Network errors found during runtime troubleshooting -> **Load** `references/troubleshoot-network.md`
- Resource exhaustion found during connector troubleshooting -> **Load** `references/troubleshoot-runtime.md`
- Network issues found during connector troubleshooting -> **Load** `references/troubleshoot-network.md`
- Source database issues found during CDC troubleshooting -> **Load** the per-connector file under `references/connectors/` for source setup instructions
- Deployment appears unhealthy (DPS heartbeat missing, deployment not reporting) -> This is a Snowflake-internal issue. Escalate to Snowflake support with deployment ID and diagnostic findings. Deployment-level issues are outside the scope of connector troubleshooting.

For any other cross-category finding, load the specific section of the diagnostic file for the root-cause category, then return to report the finding in the context of the original investigation. Do not abandon the original diagnostic thread -- synthesize both findings for the customer.

Explain to the customer how the root cause relates to their original symptom.

---

## Diagnostic Workflow Pattern

Every diagnostic path follows CHECK-INVESTIGATE-GUIDE:

1. **CHECK** -- Run initial queries yourself based on error context. Ensure a warehouse is active before running any query. If queries fail with "No active warehouse selected", ask the customer which warehouse to use (see the warehouse prerequisite in [Diagnostic Mode SQL Constraint](#diagnostic-mode-sql-constraint)).
2. **INVESTIGATE** -- Interpret results, narrow root cause, run follow-up queries yourself.
3. **GUIDE** -- Report findings and root cause to the customer. If the issue is customer-actionable, explain what the customer needs to change and link to public documentation when helpful. Escalate to Snowflake support only when the issue requires Snowflake-internal access or engineering intervention (see [Escalation](#escalation)).

In diagnostic mode, this is a troubleshooting-focused skill. The agent does not execute mutating SQL or non-SQL runtime actions itself. The agent may recommend customer-run remediation when the action is customer-controlled and supported in public docs or the Openflow UI. Do not provide internal-only actions, support-only tooling, or Snowflake-owned remediation steps.
