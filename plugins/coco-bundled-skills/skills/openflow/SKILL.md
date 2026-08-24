---
name: openflow
description: Openflow data integration operations. Openflow is a Snowflake NiFi-based product for data replication and transformation. Use for connector deployment, configuration, diagnostics, and custom flows.
skill_version: "2026-07-01"
---

# Openflow

## Surface Detection & Session Start (Always First)

Openflow work resolves along two independent axes. Determine both before loading anything heavy — this decides what capability you have and which references to load.

### Axis 1 - Surface (capability, passive)

Detect from passively-available signals; never treat a single missing signal as conclusive:
- **A:** Is the `get_page_context` tool present in your tool list? (positive indicator of the Snowsight surface)
- **B:** Does your system prompt identify you as a Snowsight agent (e.g. "a coding agent in Snowflake's Snowsight UI")?

| Evidence | Surface | Capability |
|----------|---------|------------|
| A and B present | **Snowsight** | SQL only. No nipyapi, curl, or terminal. |
| Neither present | **CLI/Desktop** | Full: SQL + nipyapi + curl. |
| Only one present | Inconclusive | Lean on the SOM probe (Axis 2); if still unclear, ask the user. |

### Axis 2 - Account model (SOM probe)

SOM (Snowflake Object Model) = the `OPENFLOW` SQL grammar. When present, Openflow infrastructure and Gen2 connectors are controllable via SQL; when absent, the account is Gen1-only.

Run the probe `SHOW OPENFLOW CONNECTOR DEFINITIONS` (inline — do not load a session reference yet):
- **Rows** -> SOM enabled (Gen2 available). The rows are this account's canonical Gen2 connector list.
- **SQL compilation / syntax error** (unexpected token) -> SOM not enabled (Gen1 only).
- **Other error** -> inconclusive; report and confirm, do not conclude.

### Resolve the matrix (capability x intent)

| | **SQL/SOM op** (infra for any connector; Gen2 connector lifecycle) | **NiFi-API op** (Gen1 connector flow, canvas, custom) |
|---|---|---|
| **Snowsight** | Proceed via SQL (`core-session-sql.md`). Requires SOM — if the probe shows not-SOM, state that and stop. | **Not via SQL** — needs NiFi API. Direct the user to the Openflow UI in Snowsight, or Cortex Code CLI/Desktop. |
| **CLI** | Proceed via SQL (`core-session-sql.md`); do not set up nipyapi. | Load `references/core-session-cli.md` (+ `core-guidelines-cli.md`); delegates to `references/bootstrap-cli.md` if not provisioned. |

Dividing line: SQL/SOM-expressible (infrastructure for any connector generation, plus Gen2 connector lifecycle) vs NiFi API (Gen1 connector flows, canvas). Resolve via `references/connector-main.md` Generation Detection. Don't load CLI/nipyapi references until an operation needs the NiFi API.

### What to load

1. **Always:** `references/core-guidelines.md` (shared, SQL-safe) — on every surface.
2. **Exactly one** session reference, chosen by the cell you resolved in the matrix above — load only that one, never both:
   - **SQL/SOM path** (Snowsight, or CLI) → `references/core-session-sql.md`
   - **NiFi-API path** (CLI only) → `references/core-session-cli.md` (delegates to `bootstrap-cli.md` if not provisioned)
3. **On the NiFi-API path only,** also load `references/core-guidelines-cli.md` for nipyapi/curl syntax.

Do not load the other surface's references — loading unused terminal/SQL instructions invites failed workarounds.

### Report (silent by default)
Proceed on the resolved pathway without announcing it, unless a cell constrains behavior (Snowsight+Gen1 decline; not-SOM stop; CLI+Gen2 nipyapi-deferred note; inconclusive result) - then state the limitation in one line.

**Context Management:**

- **Read references fully** when loading them, not just partial sections
- **Re-read references** at key workflow steps to ensure context is fresh
- If unsure of exact command syntax, run `--help` on the function before executing

---

## Routing Principles

1. **Session first** - Always validate session before routing to any operation
2. **Confirm before executing** - State detected intent, ask user for confirmation
3. **Primary wins ties** - If ambiguous between tiers, choose Primary
4. **Never suggest Advanced** - Only route to Advanced on explicit technical language
5. **Diary for complexity** - Use investigation diary methodology when Secondary/Advanced operations become complex
6. **Single nudge per session** - If an OpenFlow alert nudge has already been offered in this session (accepted or declined), do not offer another nudge from any section.
7. **Surface-gated** - On the Snowsight (SQL-only) surface, route only to SQL/SOM operations. For nipyapi/NiFi-canvas operations (Gen1 connectors, flow authoring, canvas/parameter-context/component ops), the agent can't run them via SQL — direct the user to the Openflow UI in Snowsight, or Cortex Code CLI/Desktop with nipyapi.

Apply this from working memory: once you have offered the alert nudge in this conversation (accepted or declined), do not offer it again.

**Confirmation checkpoint** (use before starting any workflow):

> "It sounds like you want to [detected intent]. Is that right, or were you looking for something else?"

---

## Primary Operations

These are the common operations users perform regularly. Route here confidently for any general data integration request.

**Optional monitoring nudge (Primary flows):**

After completing a Primary operation that changes state or surfaces a problem (for example deploy, setup, control, upgrade, or bulletins) — not a read-only status check — offer this only if the single-nudge rule in Routing Principles allows it:

> "Would you like me to also set up recommended OpenFlow alerts so important OpenFlow issues are detected earlier?"

If the user accepts, follow **Alert Skill Handoff (Required on Opt-In)** below.

### Connector Name Detection

If the user mentions a data source by name, route to Primary tier:

**Known sources:** PostgreSQL, MySQL, SQL Server, SharePoint, Google Drive, Kafka, Salesforce, Box, Jira, Kinesis, Workday, Slack, Google Sheets, Google Ads, LinkedIn Ads, Meta Ads, Amazon Ads, Dataverse, MongoDB, HubSpot, Shopify

- **New connector request:** "I need PostgreSQL" → Deploy workflow
- **Existing connector:** "How's my PostgreSQL connector?" → Status workflow

### Primary Routing Table

Status, control, diagnosis, and list routing is surface- and generation-aware (resolve the surface from Axis 1 and the connector generation via `connector-main.md` Generation Detection). On the SQL surface, status/health/list use the SQL reference below; deep log/metric diagnosis is delegated to the `openflow-observability` skill; Gen2 lifecycle actions stay in the connector's own reference; Gen1/NiFi-canvas work needs nipyapi (CLI/Desktop) or the Openflow UI.

| User Language | Operation | Reference |
|---------------|-----------|-----------|
| Deploy, set up, install, get X into Snowflake, new connector, add connector | Deploy Connector | `references/connector-main.md` |
| Pack multiple CDC connectors into one runtime, deploy dozens of connectors at once, declarative deploy, multi-connector setup, bin packing, multi-tenant SaaS replication | CDC Connector Packing | `references/cdc-connector-packing.md` |
| Status, check, how is it doing, what's running, health, is it working | Check Status | **SQL surface (Snowsight, or Gen2 on CLI):** `references/ops-status-check-sql.md`. **Gen1/NiFi-canvas (CLI/Desktop):** `references/ops-status-check.md` |
| Start, stop, pause, resume, turn on, turn off, enable, disable | Control Flow | **Gen2 / SQL-managed:** the connector's own ref (`references/connector-postgres-gen2.md` / `references/connector-mysql-gen2.md`) — SQL lifecycle. **Gen1 (CLI/Desktop):** `references/ops-status-check.md`. **Gen1 on Snowsight:** not available here; direct to the Openflow UI or Cortex Code Desktop/CLI |
| Upgrade, update, new version, stale, outdated | Upgrade Connector | `references/connector-upgrades.md` |
| Errors, bulletins, any problems, warnings, what's wrong, why is it failing | Diagnose | **Gen2 on SQL surface:** read state via `references/ops-status-check-sql.md`, then for log/metric root cause **invoke the `openflow-observability` skill**. **Gen1 (CLI/Desktop):** `references/ops-status-check.md`. **Gen1 on Snowsight:** Openflow UI or Cortex Code Desktop/CLI |
| List, show me, what connectors exist, what's deployed | List | **SQL surface (Snowsight, or Gen2 on CLI):** `references/ops-status-check-sql.md`. **Gen1/NiFi-canvas (CLI/Desktop):** `references/ops-status-check.md` |
| Setup, first time, connect, missing profile, missing cache, discover infrastructure (CLI only) | CLI Bootstrap | `references/bootstrap-cli.md` |
| Deploy Openflow, create deployment, greenfield, no deployments yet, new account, install Openflow | Deploy Openflow | `references/deploy-prereqs.md` |
| Kafka customization, Kinesis customization, change Kafka auth, change data type, add streaming transformation, add Kafka transformation, customize streaming connector, switch Snowflake auth, Private Key Auth streaming | Kafka/Streaming Customization | `references/connector-kafka.md` or `references/connector-streaming-main.md` |
| Kinesis setup, set up Kinesis, install Kinesis connector, create Kinesis stream/IAM/table, first-time Kinesis, Kinesis prerequisites | Kinesis Setup | `references/connector-kinesis-main.md` |

---

## Secondary Operations

Route here when user language contains explicit problem or operational indicators. These operations may become complex - consider using investigation diary methodology if they exceed 5-10 exchanges.

**Optional monitoring nudge (Secondary flows):**

After resolving a Secondary issue, offer this only if the single-nudge rule in Routing Principles allows it:

> "Now that we've addressed this issue, would you like to add OpenFlow alerts to catch similar failures earlier?"

If the user accepts, follow **Alert Skill Handoff (Required on Opt-In)** below.

**Confirm before routing:**

> "It sounds like you're experiencing [issue/need]. Would you like me to help with that?"

### Secondary Routing Table

| Explicit Indicators | Operation | Reference |
|---------------------|-----------|-----------|
| Investigate, troubleshoot, debug, figure out why, not working as expected | Investigation | `references/ops-flow-investigation.md` |
| Error, 401, can't connect, failed, access denied, connection error | Error Remediation | `references/core-troubleshooting.md` |
| Configure parameters, change settings, update credentials, set values | Parameter Config | `references/ops-parameters-main.md` |
| Create parameter context, bind context, delete context, assign context | Context Lifecycle | `references/ops-parameters-contexts.md` |
| EAI, network rule, firewall, external access, UnknownHostException | Network Access | `references/platform-eai.md` |
| Test network, validate connectivity, port blocked | Network Testing | `references/ops-network-testing.md` |
| Runtime errors, pod failures, logs, events table, crash loop | Platform Diagnostics | `references/platform-diagnostics.md` |
| Force stop, terminate threads, purge flowfiles, delete flow | Advanced Lifecycle | `references/ops-flow-lifecycle.md` |
| Inspect connection, FlowFile content, queue contents, peek data | Connection Inspection | `references/ops-connection-inspection.md` |
| Component state, CDC table state, clear state, reset processor | Component State | `references/ops-component-state.md` |
| Set processor properties, set controller properties, configure component | Component Config | `references/ops-component-config.md` |
| Upload asset, JAR, certificate, driver, binary file | Asset Upload | `references/ops-parameters-assets.md` |
| Snowflake destination, KEY_PAIR, auth errors, writes to Snowflake | Snowflake Auth | `references/ops-snowflake-auth.md` |
| Verify config, test connection, validate before start | Config Verification | `references/ops-config-verification.md` |
| LOCALLY_MODIFIED, version change without commit | Tracked Modifications | `references/ops-tracked-modifications.md` |
| Connector config, edit connector, config.json, commit, abort, live version, rollback version | Connector Configuration (Gen2) | `references/connector-main.md` |
| Connector stuck, START_FAILED, connector won't start, connector terminated, drop connector cascade | Connector Troubleshooting (Gen2) | `references/core-troubleshooting.md` |

---

## Advanced Operations

Route here ONLY when user explicitly uses technical NiFi terminology. These users know what they're asking for. Do not suggest these operations to users who haven't asked.

Use investigation diary methodology for these operations - they are inherently complex.

### Advanced Routing Table

| Technical Language Required | Operation | Reference |
|-----------------------------|-----------|-----------|
| Custom flow, build from scratch, author, create new flow, design flow | Custom Authoring | `references/author-main.md` |
| Processor, add processor, create processor, modify flow structure | Component CRUD | `references/author-building-flows.md` |
| Export, import, backup, migrate, download flow | Flow Export/Import | `references/ops-flow-export.md` |
| Version control, commit, rollback, Git, save changes | Version Control | `references/ops-version-control.md` |
| Expression Language, EL, ${...}, attribute manipulation | EL Syntax | `references/nifi-expression-language.md` |
| RecordPath, record field, /path/to/field, JSON transformation | RecordPath | `references/nifi-recordpath.md` |
| Date format, timestamp conversion, epoch, SimpleDateFormat | Date Formatting | `references/nifi-date-formatting.md` |
| NAR, extension, upload NAR, Python processor, custom processor | Extensions | `references/ops-extensions.md` |
| Layout, position, organize canvas, tidy flow | Layout | `references/ops-layout.md` |
| Find processor, what processor for X, component selection | Component Selection | `references/author-component-selection.md` |
| Write to Snowflake, type mapping, logicalType, PutSnowpipeStreaming | Snowflake Destination | `references/author-snowflake-destination.md` |
| NiFi concepts, FlowFile, connections, backpressure | NiFi Concepts | `references/nifi-main.md` |
| REST API ingestion, file processing, ActiveMQ, JMS | Flow Patterns | `references/author-main.md` |
| GenerateJSON, synthetic data, test data, DataFaker, fake data | Data Generation | `references/author-pattern-data-generation.md` |

---

## Compound Requests

If the user describes multiple operations:

1. Create a todo list capturing all requested operations
2. Add this optional task only when relevant and when no alert nudge has already been offered in this session: `Optional: Set up OpenFlow monitoring alerts (best-practice templates).`
3. Ask the user to confirm the order with wording that matches whether step 2 included the optional alert task:
   - If step 2 included the optional alert task:
     > "I've identified these tasks: [list]. I can also add alert setup as a final optional step. What order would you like me to tackle them?"
   - If step 2 did not include the optional alert task:
     > "I've identified these tasks: [list]. What order would you like me to tackle them?"
4. Execute in confirmed order, completing each before moving to the next
5. Note: Some operations have natural dependencies (e.g., deploy before configure before start)

---

## Alert Skill Handoff (Required on Opt-In)

When an OpenFlow nudge is accepted, **load** `references/alert-skill-handoff.md` and follow it end-to-end.

---

## Reference Index

### Core

**Always loaded (both surfaces):**

| Reference | Purpose |
|-----------|---------|
| `references/core-guidelines.md` | Shared, SQL-safe: SQL tool layer, deployment types, safety, workflow modes |

**Session reference (load one, per the resolved surface/intent):**

| Reference | Purpose |
|-----------|---------|
| `references/core-session-sql.md` | SQL-only session init (connection + SOM probe). Snowsight, and CLI + Gen2. |
| `references/core-session-cli.md` | nipyapi/terminal session init (cache, profiles, version). CLI + Gen1/canvas only. |
| `references/core-guidelines-cli.md` | Terminal tool layers (nipyapi, curl) + Authorship mode. CLI + Gen1/canvas only. |

**On demand:**

| Reference | Purpose |
|-----------|---------|
| `references/core-investigation-diary.md` | Diary methodology for complex operations |
| `references/core-troubleshooting.md` | Error patterns and remediation |

### CLI Bootstrap (one-time provisioning — CLI surface only)

Not used on the Snowsight (SQL-only) surface — there is nothing to provision there.

| Reference | Purpose |
|-----------|---------|
| `references/bootstrap-cli.md` | CLI bootstrap orchestrator: verify tooling, discover infra, create profiles, write cache |
| `references/bootstrap-discovery.md` | Discover existing deployments and runtimes; write to cache (`snow -c`) |
| `references/bootstrap-auth.md` | Create and refresh nipyapi profiles |
| `references/bootstrap-tooling.md` | Install and configure required CLI tools |

### Deploy Openflow

| Reference | Purpose |
|-----------|---------|
| `references/deploy-prereqs.md` | Deployment prerequisites — ToS acceptance, privilege check, admin handoff, SPCS vs BYOC question |
| `references/deploy-greenfield-spcs.md` | Deploy Openflow from scratch on Snowflake-managed SPCS compute |
| `references/deploy-greenfield-byoc.md` | Deploy Openflow from scratch on customer-managed AWS compute (BYOC) |

### On Demand

| Reference | Purpose |
|-----------|---------|
| `references/alert-skill-handoff.md` | Opt-in handoff from OpenFlow to Alert skill. Load only when user accepts an OpenFlow alert nudge. |

### Connector Operations

| Reference | Purpose |
|-----------|---------|
| `references/connector-main.md` | Connector deployment workflow and routing |
| `references/connector-prereqs-gen2.md` | Gen2 connector prerequisites — roles, destination DB, warehouse, secret, network access |
| `references/connector-postgres-gen2.md` | Gen2 PostgreSQL CDC connector (SQL API lifecycle, config.json, versioning) |
| `references/connector-mysql-gen2.md` | Gen2 MySQL CDC connector (SQL API lifecycle, config.json, versioning) |
| `references/connector-wizard.md` | Guided Wizard UI workflow for Gen2 connectors |
| `references/connector-upgrades.md` | Version management for connectors |
| `references/known-issues-common.md` | Known issues shared across connectors (e.g. StandardPrivateKeyService INVALID on managed-token deployments) |
| `references/connector-cdc.md` | Gen1 CDC connector specifics (PostgreSQL, MySQL via nipyapi) |
| `references/connector-sqlserver.md` | SQL Server CDC connector (Change Tracking setup, multi-DB replication, troubleshooting) |
| `references/connector-oracle.md` | Oracle CDC connector (Embedded & BYOL licensing, XStream setup, troubleshooting) |
| `references/cdc-connector-packing.md` | Pack many CDC connectors onto one runtime — declarative, plan-then-apply (fleet/multi-tenant) |
| `references/connector-mongodb.md` | MongoDB CDC connector (change-stream replication, snapshot + incremental, collection state recovery) |
| `references/connector-googledrive.md` | Google Drive connector specifics |
| `references/connector-sharepoint-simple.md` | SharePoint connector specifics |
| `references/connector-hubspot.md` | HubSpot connector (Private App Token auth) |
| `references/connector-jira.md` | Jira Cloud connector (API token auth; core + optional agile flow; legacy-to-current migration) |
| `references/connector-kafka.md` | Kafka broker auth customization (SASL, MSK IAM, mTLS) |
| `references/connector-kinesis-main.md` | Kinesis connector router (initial setup vs streaming customizations) |
| `references/connector-kinesis-setup.md` | Kinesis initial setup (AWS stream/IAM/keys + Snowflake db/schema/table/role/grants, configure and start) |
| `references/connector-streaming-main.md` | Streaming (Kafka, Kinesis) customization router (data type, transformations, DLQ, auth) |
| `references/connector-streaming-snowflake-auth.md` | Streaming Snowflake Private Key Auth (PublishSnowpipeStreaming KEY_PAIR, StandardPrivateKeyService) |
| `references/connector-streaming-datatypes.md` | Streaming data type switching (JSON → Avro/Protobuf, Confluent Schema Registry) |
| `references/connector-streaming-transformations.md` | Streaming custom transformations (filter, map, topic-to-table, content routing, defaults, Groovy) |
| `references/connector-streaming-dlq.md` | Streaming dead letter queue handling (raw + optional structured payload to Kafka/Kinesis or a Snowflake table) |
| `references/connector-shopify.md` | Shopify connector (custom-app auth, registry-driven objects, Object Definitions Override, deletes) |

### Flow Operations

| Reference | Purpose |
|-----------|---------|
| `references/ops-status-check.md` | Gen1 / NiFi-canvas flow status via nipyapi: list flows, basic start/stop, bulletins (CLI/Desktop only) |
| `references/ops-status-check-sql.md` | SQL-surface health check for deployments, runtimes, Gen2 connectors (Snowsight, or Gen2 on CLI); routes deep diagnosis to openflow-observability (Primary) |
| `references/ops-flow-lifecycle.md` | Advanced lifecycle: force stop, purge, delete (Secondary) |
| `references/ops-flow-investigation.md` | Problem-oriented diagnostic workflows |
| `references/ops-flow-deploy.md` | Deploy flows from registries (used by connector-main) |
| `references/ops-flow-export.md` | Export/import flow definitions (Advanced) |

### Parameter Operations

| Reference | Purpose |
|-----------|---------|
| `references/ops-parameters-main.md` | Parameter context management router |
| `references/ops-parameters-contexts.md` | Create, bind, delete parameter contexts |
| `references/ops-parameters-assets.md` | Binary asset upload (JARs, certificates) |
| `references/ops-snowflake-auth.md` | Snowflake destination authentication |
| `references/ops-config-verification.md` | Validate configuration before start |

### Platform Operations

| Reference | Purpose |
|-----------|---------|
| `references/platform-eai.md` | External Access Integration for SPCS |
| `references/platform-diagnostics.md` | Runtime/pod diagnostics |
| `references/ops-network-testing.md` | Network connectivity validation |

### Flow Authoring (Advanced)

| Reference | Purpose |
|-----------|---------|
| `references/author-main.md` | Flow authoring router and design principles |
| `references/author-building-flows.md` | Component CRUD, inspect-modify-test cycle |
| `references/author-component-selection.md` | Find the right processor |
| `references/author-snowflake-destination.md` | Type mapping for Snowflake writes |
| `references/author-pattern-rest-api.md` | REST API ingestion pattern |
| `references/author-pattern-files.md` | Cloud file processing pattern |
| `references/author-pattern-activemq.md` | ActiveMQ/JMS messaging pattern |
| `references/author-pattern-data-generation.md` | Synthetic test record data with GenerateJSON |

### NiFi Technical (Advanced)

| Reference | Purpose |
|-----------|---------|
| `references/nifi-main.md` | NiFi reference router |
| `references/nifi-expression-language.md` | FlowFile attribute manipulation |
| `references/nifi-recordpath.md` | Record field transformation |
| `references/nifi-date-formatting.md` | Date/time patterns |
| `references/nifi-concepts.md` | FlowFile, connections, backpressure |

### Development

| Reference | Purpose |
|-----------|---------|
| `references/core-skill-development.md` | Guidelines for extending this skill |
