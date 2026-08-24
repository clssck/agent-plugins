---
name: iceberg
description: >-
  REQUIRED entry point for ALL Iceberg table work in Snowflake: creating and altering Iceberg
  tables (Snowflake-managed storage by default), catalog integrations, catalog-linked databases
  (CLD, auto-discover/sync tables), external volumes, auto-refresh problems (stale data, refresh
  stuck, delta direct), Horizon IRC setup and diagnostics (PAT authentication), Snowflake
  Intelligence, and converting externally managed tables to Snowflake-managed (take ownership). Do
  NOT work with Iceberg manually — invoke this skill first. Triggers: iceberg, apache iceberg,
  REST catalog, AWS Glue and glue IRC, S3 Tables, Lake Formation, Unity Catalog, Databricks,
  Polaris/Open Catalog, OneLake, Microsoft Fabric lakehouse, BigLake/BigQuery metastore, workload
  identity federation, token-exchange or bearer-token catalog integration, SAP BDC, Delta Sharing,
  external volume, storage access on S3/Azure Blob/GCS, ALLOW_WRITES.
---

# Iceberg

## When to Use

When a user wants to work with Iceberg tables in Snowflake. This includes:
- Creating Iceberg tables (defaults to Snowflake-managed storage — no external volume needed)
- Setting up catalog integrations (AWS Glue, Amazon S3 Tables, Unity Catalog, OpenCatalog/Polaris, OneLake/Microsoft Fabric, Google Cloud BigLake Metastore, SAP BDC, Delta Sharing)
- Creating catalog-linked databases for automatic table discovery
- Configuring external volumes for storage access
- Debugging auto-refresh issues
- Surfacing CLD Iceberg data in Snowflake Intelligence
- Converting an externally managed Iceberg table to Snowflake-managed (unlocks zero-copy clone, replication, and native table optimization)

This is the entry point for all Iceberg workflows.

---

## Session Prerequisites

Before routing to any operation, confirm the user's goal to avoid unnecessary work.

**Confirmation checkpoint** (use before starting any workflow):

> "It sounds like you want to [detected intent]. Is that right, or were you looking for something else?"

> **Exception — Default table creation**: A plain request to create an Iceberg table (with no external catalog/volume/storage qualifier) routes straight to `snowflake-managed-storage/SKILL.md`. Do **not** run the routing-confirmation checkpoint for this path — load that subskill. It defaults storage/catalog to Snowflake-managed, then presents the SQL and runs it through the normal execution approval (it does not auto-execute DDL).

---

## Routing Principles

1. **Confirm before routing** - State detected intent, ask user for confirmation. **Exception**: a plain create-table request routes to `snowflake-managed-storage/SKILL.md` without the routing-confirmation checkpoint (the SQL still runs through the standard execution approval).
2. **Primary wins ties** - If ambiguous between intents, choose the more common operation
3. **Follow dependencies** - Some workflows depend on others (e.g., CLD requires catalog integration first)
4. **Sub-skills handle details** - This skill routes; sub-skills execute

---

## Intent Detection

When user makes a request, detect their intent and route to the appropriate sub-skill:

### Primary Operations

These are the most common operations users perform. Route here confidently.

**CREATE_TABLE Intent** - User wants to create a new Iceberg table (no external catalog/volume named):

- Trigger phrases: "create an iceberg table", "create a new iceberg table", "make an iceberg table", "set up an iceberg table", "I need an iceberg table", "create iceberg table with columns ...", "save this query as an iceberg table", "load this data into an iceberg table", "materialize as iceberg", "create iceberg table as select", "CTAS iceberg"
- **→ Load** `snowflake-managed-storage/SKILL.md` (Snowflake-managed storage, no routing confirmation, no external volume). This is the highest-priority path — check it before the other intents. CTAS requests (query materialization) also route here — columns derive from the query.

**CATALOG_INTEGRATION Intent** - User wants to connect Snowflake to an external catalog:

- Trigger phrases: "catalog integration", "connect to glue", "connect to s3 tables", "amazon s3 tables", "s3 tables", "connect to databricks", "connect to unity catalog", "connect to polaris", "connect to opencatalog", "connect to onelake", "connect to fabric", "onelake", "microsoft fabric", "fabric lakehouse", "connect to biglake", "biglake", "biglake metastore", "bigquery metastore", "connect to google cloud", "google cloud iceberg", "gcp iceberg", "connect to SAP", "SAP BDC", "SAP Business Data Cloud", "sap data products", "sap invitation link", "delta sharing", "connect to delta sharing", "delta share", "query delta sharing tables", "bearer token catalog integration", "connect to delta sharing server", "setup iceberg REST", "configure catalog"
- **→ Route to** [Catalog Integration Routing](#catalog-integration-routing)

**AWS_GLUE_SETUP Intent** - User wants to set up AWS-side Glue infrastructure (S3, crawler, Iceberg conversion):

- Trigger phrases: "aws glue setup", "glue crawler", "athena CTAS", "parquet to iceberg", "S3 to iceberg", "glue database", "convert to iceberg", "aws iceberg setup"
- **→ Load** `catalog-integration/glueirc-catalog-integration-setup/aws-setup/SKILL.md`

**CATALOG_LINKED_DATABASE Intent** - User wants to auto-discover tables from a catalog:

- Trigger phrases: "catalog-linked database", "CLD", "auto-discover tables", "sync tables from catalog", "CREATE DATABASE LINKED_CATALOG", "import iceberg tables"
- **→ Load** `catalog-linked-database/SKILL.md`

**EXTERNAL_VOLUME Intent** - User wants to configure storage in their **own** cloud bucket (data residency, CMK, existing data lake) or debug an existing volume:

- Trigger phrases: "external volume", "storage access", "S3 access", "Azure storage", "GCS storage", "S3-compatible / S3Compat storage", "Access Denied", "403 error", "cannot write", "ALLOW_WRITES", "trust policy", "IAM role", "my bucket", "my storage", "BYO storage"
- **→ Load** `external-volume/SKILL.md`
- **Note**: if the user just wants to create an Iceberg table (no own-bucket requirement), they do NOT need an external volume — route to `snowflake-managed-storage/SKILL.md` instead. The external-volume skill has its own setup-intent guard that will catch this and redirect.

**AUTO_REFRESH Intent** - User has stale data or refresh issues:

- Trigger phrases: "auto-refresh", "stale data", "refresh not working", "refresh stuck", "STALLED", "STOPPED", "delta direct", "not syncing", "data not updating"
- **→ Load** `auto-refresh/SKILL.md`

**HORIZON_IRC Intent** - User wants to test, verify, or debug Horizon IRC (Snowflake's native Polaris-based Iceberg REST Catalog):

- Trigger phrases: "horizon IRC", "horizon IRC setup", "horizon IRC not working", "test horizon IRC", "diagnose horizon IRC", "debug horizon IRC", "horizon IRC connection", "horizon IRC endpoint", "horizon IRC 401", "horizon IRC 403", "horizon IRC 404", "PAT authentication horizon", "table not visible horizon IRC", "horizon REST catalog"
- **→ Load** `horizon-irc-diagnose/SKILL.md`

**CONVERT_TO_MANAGED Intent** - User wants to convert an externally managed Iceberg table to Snowflake-managed (unlocks zero-copy clone, replication, and native table optimization):

- Trigger phrases: "convert iceberg table", "convert to managed", "ALTER ICEBERG TABLE CONVERT TO MANAGED", "take ownership of iceberg table", "snowflake managed iceberg", "externally managed to managed", "switch iceberg catalog to snowflake"
- **→ Load** `convert-to-managed/SKILL.md`

### Secondary Operations

Route here when user language indicates more advanced or combined workflows.

**SNOWFLAKE_INTELLIGENCE Intent** - User wants to query CLD Iceberg tables with natural language:

- Trigger phrases: "snowflake intelligence", "natural language", "text-to-SQL", "query CLD with AI", "create agent for CLD", "semantic view for CLD", "query iceberg naturally"
- **→ Load** `cld-snowflake-intelligence/SKILL.md`

---

## Catalog Integration Routing

When user wants to connect to an external catalog, identify which catalog type:

**Ask the user**:
```
Which external catalog are you connecting to?

A: AWS Glue Data Catalog or Amazon S3 Tables
   → Iceberg tables managed in AWS Glue IRC
   → Amazon S3 Tables direct path (bypasses Glue)

B: Databricks Unity Catalog
   → Iceberg tables managed in Databricks

C: OpenCatalog / Polaris
   → Snowflake's open Iceberg catalog

D: Microsoft OneLake (Fabric)
   → Iceberg tables in Microsoft Fabric via OneLake REST

E: Google Cloud BigLake Metastore
   → Iceberg tables in Google Cloud via workload identity federation

F: SAP Business Data Cloud (SAP BDC)
   → Delta tables shared from SAP via zero-copy integration

G: Delta Sharing
   → Consuming Delta tables shared by an external provider (e.g., Databricks Unity Catalog)
   → You have a credential file or bearer token issued by the provider

H: I'm not sure / I need help choosing
```

**Route based on response**:
- **A (Glue / S3 Tables)** → **Load** `catalog-integration/glueirc-catalog-integration-setup/SKILL.md`
- **B (Unity Catalog)** → **Load** `catalog-integration/unitycatalog-catalog-integration-setup/SKILL.md`
- **C (OpenCatalog/Polaris)** → **Load** `catalog-integration/opencatalog-catalog-integration-setup/SKILL.md`
- **D (OneLake/Fabric)** → **Load** `catalog-integration/onelake-catalog-integration-setup/SKILL.md`
- **E (BigLake)** → **Load** `catalog-integration/biglake-catalog-integration-setup/SKILL.md`
- **F (SAP BDC)** → **Load** `catalog-integration/sapbdc-catalog-integration-setup/SKILL.md`
- **G (Delta Sharing)** → **Load** `catalog-integration/deltasharing-catalog-integration-setup/SKILL.md`
- **H (Not sure)** → Help user identify their catalog (see [Catalog Selection Guide](#catalog-selection-guide))

---

## Catalog Selection Guide

Help users identify their catalog type:

| If user mentions... | Catalog Type | Route to |
|---------------------|--------------|----------|
| AWS, Glue, Lake Formation, S3 with Iceberg, Amazon S3 Tables, S3 Tables | AWS Glue IRC / S3 Tables | `glueirc-catalog-integration-setup` |
| Databricks, Unity, Delta Lake (converted to Iceberg) | Unity Catalog | `unitycatalog-catalog-integration-setup` |
| Polaris, OpenCatalog, Snowflake Open Catalog | OpenCatalog | `opencatalog-catalog-integration-setup` |
| OneLake, Microsoft Fabric, Fabric lakehouse, OneLake REST | OneLake (Fabric) | `onelake-catalog-integration-setup` |
| BigLake, BigLake metastore, BigQuery metastore, Google Cloud, GCP, Lakehouse Iceberg REST | Google Cloud BigLake | `biglake-catalog-integration-setup` |
| SAP, SAP BDC, SAP Business Data Cloud | SAP BDC | `sapbdc-catalog-integration-setup` |
| Delta Sharing, delta share, consuming a Databricks share, bearer token from provider, credential file from provider | Delta Sharing | `deltasharing-catalog-integration-setup` |

---

## Workflow Decision Tree

```
Start Session
    ↓
Detect User Intent
    ↓
    ├─→ CREATE_TABLE (plain "create an iceberg table", no external storage/catalog)
    │   └─→ Load `snowflake-managed-storage/SKILL.md` → CATALOG='SNOWFLAKE', EXTERNAL_VOLUME='SNOWFLAKE_MANAGED'
    │
    ├─→ CATALOG_INTEGRATION → Identify catalog type
    │   ├─→ AWS Glue → Load `glueirc-catalog-integration-setup`
    │   ├─→ Unity Catalog → Load `unitycatalog-catalog-integration-setup`
    │   ├─→ OpenCatalog/Polaris → Load `opencatalog-catalog-integration-setup`
    │   ├─→ OneLake/Fabric → Load `onelake-catalog-integration-setup`
    │   ├─→ Google Cloud BigLake → Load `biglake-catalog-integration-setup`
    │   ├─→ SAP BDC → Load `sapbdc-catalog-integration-setup`
    │   ├─→ Delta Sharing → Load `deltasharing-catalog-integration-setup`
    │   └─→ Not sure → Catalog Selection Guide
    │
    ├─→ AWS_GLUE_SETUP → Load `glueirc-catalog-integration-setup/aws-setup/SKILL.md`
    │
    ├─→ CATALOG_LINKED_DATABASE → Load `catalog-linked-database/SKILL.md`
    │
    ├─→ EXTERNAL_VOLUME → Load `external-volume/SKILL.md`
    │
    ├─→ AUTO_REFRESH → Load `auto-refresh/SKILL.md`
    │
    ├─→ HORIZON_IRC → Load `horizon-irc-diagnose/SKILL.md`
    │
    ├─→ CONVERT_TO_MANAGED → Load `convert-to-managed/SKILL.md`
    │
    └─→ SNOWFLAKE_INTELLIGENCE → Load `cld-snowflake-intelligence/SKILL.md`
```

---

## Typical User Journeys

### Journey 0: Create a Table (Default, Zero-Setup)
```
CREATE_TABLE → Load `snowflake-managed-storage/SKILL.md` (Snowflake-managed storage)
```
Example: "Create an Iceberg table" / "Make an iceberg table ORDERS with id and amount" / "Save this query as an Iceberg table" — built with `CATALOG='SNOWFLAKE'` + `EXTERNAL_VOLUME='SNOWFLAKE_MANAGED'`, no external volume and no storage/catalog questions. The only prompt is for a table name when the user didn't give one. CTAS (query materialization) follows the same path — columns derive from the query.

### Journey 1: New Iceberg Setup (End-to-End)
```
CATALOG_INTEGRATION → EXTERNAL_VOLUME (if needed) → CATALOG_LINKED_DATABASE → SNOWFLAKE_INTELLIGENCE
```
Example: "I want to set up Iceberg from scratch and query with natural language"

### Journey 1b: AWS-Side Setup + Snowflake Integration (End-to-End)
```
AWS_GLUE_SETUP → CATALOG_INTEGRATION → CATALOG_LINKED_DATABASE
```
Example: "I have parquet data in S3 and want to query it as Iceberg in Snowflake"

### Journey 2: Connect External Catalog
```
CATALOG_INTEGRATION → CATALOG_LINKED_DATABASE
```
Example: "I want to query my Glue Iceberg tables from Snowflake"

### Journey 3: Storage Access Issues
```
EXTERNAL_VOLUME (diagnose) → fix IAM/trust policy → EXTERNAL_VOLUME (verify)
```
Example: "I'm getting Access Denied when creating an Iceberg table"

### Journey 4: Data Freshness Problems
```
AUTO_REFRESH (diagnose) → apply fix → AUTO_REFRESH (verify)
```
Example: "My Iceberg table data is stale"

### Journey 5: Add Natural Language to Existing CLD
```
CATALOG_LINKED_DATABASE (verify) → SNOWFLAKE_INTELLIGENCE
```
Example: "I have a CLD and want to query it with natural language"

### Journey 5b: Take Ownership of an Externally Managed Table
```
CONVERT_TO_MANAGED (verify external volume → convert → verify)
```
Example: "I have an unmanaged Iceberg table created against my Glue/Polaris catalog (outside any CLD) and want Snowflake to own it so I get zero-copy clone, replication, and native table optimization."

> Tables that live inside a catalog-linked database do **not** support `CONVERT TO MANAGED` — only externally managed Iceberg tables created outside a CLD are eligible.

### Journey 6: Catalog Integration Troubleshooting
```
CATALOG_INTEGRATION → Troubleshoot Workflow
```
Example: "My Unity Catalog integration isn't working"

### Journey 7: CLD Not Syncing Tables
```
CATALOG_LINKED_DATABASE (troubleshoot) → AUTO_REFRESH (if refresh issues)
```
Example: "Tables aren't appearing in my catalog-linked database"

### Journey 8: Create a Table Inside an Existing CLD
```
CATALOG_LINKED_DATABASE → create-table/SKILL.md
```
Example: "I have a CLD and want to create a new Iceberg table in it"

---

## Compound Requests

If the user describes multiple operations:

1. Create a task list capturing all requested operations
2. Ask the user to confirm the order:
   > "I've identified these tasks: [list]. What order would you like me to tackle them?"
3. Execute in confirmed order, completing each before moving to the next
4. Note: Natural dependencies exist:
   - Catalog Integration → before → CLD
   - External Volume → before → CLD (if not using vended credentials)
   - CLD → before → Snowflake Intelligence

---

## Sub-Skill Reference Index

### Table Creation (Snowflake-managed storage)

| Sub-Skill | Purpose |
|-----------|---------|
| `snowflake-managed-storage/SKILL.md` | Default table creation fast-path (no routing confirmation, no external volume) |
| `snowflake-managed-storage/references/snowflake-managed-storage.md` | CREATE templates, defaults at account/db/schema, permanent vs. transient, type guidance, cloud support, GCP/gov fallback |

### Catalog Integrations

| Sub-Skill | Purpose |
|-----------|---------|
| `catalog-integration/glueirc-catalog-integration-setup/SKILL.md` | AWS Glue Data Catalog (Glue IRC) integration |
| `catalog-integration/glueirc-catalog-integration-setup/aws-setup/SKILL.md` | AWS-side Glue infrastructure (S3, crawler, Athena CTAS) |
| `catalog-integration/unitycatalog-catalog-integration-setup/SKILL.md` | Databricks Unity Catalog integration |
| `catalog-integration/opencatalog-catalog-integration-setup/SKILL.md` | OpenCatalog/Polaris integration |
| `catalog-integration/onelake-catalog-integration-setup/SKILL.md` | Microsoft OneLake (Fabric) integration via Iceberg REST |
| `catalog-integration/biglake-catalog-integration-setup/SKILL.md` | Google Cloud BigLake Metastore integration via workload identity federation |
| `catalog-integration/biglake-catalog-integration-setup/gcp-setup/SKILL.md` | GCP-side BigLake setup (gcloud: bucket, catalog, workload identity, IAM; Spark table snippet) |
| `catalog-integration/sapbdc-catalog-integration-setup/SKILL.md` | SAP Business Data Cloud (SAP BDC) integration |
| `catalog-integration/deltasharing-catalog-integration-setup/SKILL.md` | Delta Sharing integration (bearer token, vended credentials) |
| `catalog-integration/shared/next-steps/SKILL.md` | Post-integration options (CLD or individual tables) |
| `catalog-integration/shared/verify/SKILL.md` | Shared verification workflow |

### Catalog-Linked Databases

| Sub-Skill | Purpose |
|-----------|---------|
| `catalog-linked-database/SKILL.md` | CLD creation, verification, troubleshooting router |
| `catalog-linked-database/setup/SKILL.md` | CLD configuration collection |
| `catalog-linked-database/create/SKILL.md` | CLD creation workflow |
| `catalog-linked-database/verify/SKILL.md` | CLD verification workflow |
| `catalog-linked-database/create-table/SKILL.md` | Create an Iceberg table inside an existing CLD (unmanaged writes) |
| `catalog-linked-database/references/troubleshooting.md` | CLD error patterns and solutions |

### External Volumes

| Sub-Skill | Purpose |
|-----------|---------|
| `external-volume/SKILL.md` | External volume debugging for AWS S3, Azure, GCS |
| `external-volume/examples/examples.md` | Example configurations |
| `external-volume/examples/known-issues.md` | Known issues and workarounds |

### Auto-Refresh

| Sub-Skill | Purpose |
|-----------|---------|
| `auto-refresh/SKILL.md` | Auto-refresh debugging for Iceberg and Delta Direct |
| `auto-refresh/delta-direct.md` | Delta Direct specific debugging |
| `auto-refresh/monitoring.md` | Auto-refresh monitoring and alerting setup |

### Snowflake Intelligence (CLD)

| Sub-Skill | Purpose |
|-----------|---------|
| `cld-snowflake-intelligence/SKILL.md` | Query CLD Iceberg tables via Snowflake Intelligence |
| `cld-snowflake-intelligence/references/semantic-view-sql.md` | Semantic view syntax for CLD tables |

### Horizon IRC

| Sub-Skill | Purpose |
|-----------|---------|
| `horizon-irc-diagnose/SKILL.md` | Test, verify, and debug Horizon IRC (Snowflake Polaris) connectivity |

---

## Stopping Points

- **Intent Detection**: Confirm detected intent before routing
- **Catalog Type Selection**: Wait for user to identify their catalog
- **Sub-skill handoff**: Each sub-skill has its own stopping points

**Resume rule**: Upon user approval ("yes", "looks good", "proceed"), route to the appropriate sub-skill without re-asking.

---

## Scope

**In scope**:
- Creating Iceberg tables by default with Snowflake-managed storage (routed to the `snowflake-managed-storage` subskill)
- Routing to appropriate Iceberg sub-skills
- Initial diagnosis to identify the right workflow

**Out of scope** (handled by sub-skills):
- Detailed catalog integration setup → specific catalog integration skills
- CLD configuration details → `catalog-linked-database/SKILL.md`
- External volume IAM/permission details → `external-volume/SKILL.md`
- Auto-refresh debugging details → `auto-refresh/SKILL.md`

---

## Output

- User routed to the correct Iceberg sub-skill based on their intent
- For a plain create request: a Snowflake-managed Iceberg table (no external volume, no storage/catalog questions); the agent asks for a table name only if the user didn't provide one
- Sub-skill completes the requested operation (setup, verification, or troubleshooting)

---

## Documentation

- [Snowflake Iceberg Tables](https://docs.snowflake.com/user-guide/tables-iceberg)
- [Storage for Apache Iceberg Tables (overview)](https://docs.snowflake.com/en/user-guide/tables-iceberg-storage)
- [Snowflake storage for Apache Iceberg Tables](https://docs.snowflake.com/en/user-guide/tables-iceberg-internal-storage)
- [Configure Catalog Integration](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration)
- [Configure Catalog Integration for OneLake REST](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-rest-onelake)
- [Catalog-Linked Databases](https://docs.snowflake.com/en/user-guide/tables-iceberg-catalog-linked-database)
- [External Volumes](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-external-volume)
- [Auto-Refresh Iceberg Tables](https://docs.snowflake.com/en/user-guide/tables-iceberg-auto-refresh)
