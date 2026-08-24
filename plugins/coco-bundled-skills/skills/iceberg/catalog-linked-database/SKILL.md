---
name: catalog-linked-database
description: "Setup, verify, and troubleshoot catalog-linked databases (CLD) for REST-based Iceberg catalogs. Triggers: create catalog linked database, setup CLD, CREATE DATABASE LINKED_CATALOG, auto-discover iceberg tables, catalog sync status, auto refresh iceberg, table not initialized, troubleshoot CLD, CLD health, sync iceberg tables, create iceberg table in CLD, CREATE ICEBERG TABLE in catalog-linked database, add table to CLD, create table in linked database, unmanaged writes CLD."
---

# Catalog-Linked Database Setup

## Setup

**Load** the following references (used across all sub-workflows):
- `references/troubleshooting.md`: Common issues, diagnostic commands, and troubleshooting patterns
- `references/health-dashboard.sql`: SQL queries for CLD health monitoring and status checks

Setup, verify, or troubleshoot a Snowflake catalog-linked database for automatic Iceberg table discovery.

## Supported Catalogs

**Supported**: Catalog integrations with `CATALOG_SOURCE = POLARIS` or `ICEBERG_REST`
- OpenCatalog/Polaris
- Glue Iceberg REST (IRC)
- Unity Catalog Iceberg REST
- Microsoft OneLake IRC
- Horizon REST

**Not Supported**:
- `CATALOG_SOURCE = GLUE` (legacy Glue)
- Non-Iceberg / object-store catalogs

---

## Intent Routing (FIRST)

**Ask the user**:
```
What would you like to do?

A: Create a new catalog-linked database
   → Auto-discover tables from an existing catalog integration

B: Verify an existing catalog-linked database
   → Check sync status and table health

C: Troubleshoot a catalog-linked database
   → Diagnose sync failures, auto-refresh issues

D: Create an Iceberg table inside an existing catalog-linked database
   → Use CREATE ICEBERG TABLE to add a new table to an existing CLD
```

**Route based on response**:
- **A (Create)** → Continue to [Create Workflow](#create-workflow)
- **B (Verify)** → **Load** `verify/SKILL.md` then follow [Verify Workflow](#verify-workflow)
- **C (Troubleshoot)** → **Load** `references/troubleshooting.md` then follow [Troubleshoot Workflow](#troubleshoot-workflow)
- **D (Create Table)** → **Load** `create-table/SKILL.md` then follow its workflow

---

## Create Workflow

### Step 1: Prerequisite Checks

Before creating a CLD, verify the required components are in place.

#### Step 1.1: Check Catalog Integration

**Ask**:
```
Do you already have a catalog integration set up for your external catalog?

A: Yes, I have a working catalog integration
B: No, I need to create one
C: I'm not sure
```

**If B or C** → Help identify or create:

```sql
-- List existing catalog integrations
SHOW CATALOG INTEGRATIONS;
```

**If no integration exists or user selects B**:

**Ask**:
```
Which external catalog are you connecting to?

1: AWS Glue Data Catalog (Glue IRC)
2: Databricks Unity Catalog
3: OpenCatalog / Polaris
4: Other REST-based Iceberg catalog
```

**Route to catalog integration skill**:
- **1 (Glue)** → "Please set up your catalog integration first. **Invoke** the `glueirc-catalog-integration-setup` skill."
- **2 (Unity)** → "Please set up your catalog integration first. **Invoke** the `unitycatalog-catalog-integration-setup` skill."
- **3 (OpenCatalog)** → "Please set up your catalog integration first. **Invoke** the `opencatalog-catalog-integration-setup` skill."
- **4 (Other)** → Provide generic guidance for REST catalog setup

**⚠️ STOP**: Do not proceed until catalog integration is created and verified. Return here after catalog integration setup is complete.

**If A (has integration)** → Continue to Step 1.2

---

#### Step 1.2: Verify Catalog Integration

**Ask**: 
```
What is the name of your catalog integration?

If you're not sure, would you like me to run SHOW CATALOG INTEGRATIONS to list all available integrations?
```

**If user wants to list integrations**:
```sql
SHOW CATALOG INTEGRATIONS;
```

**Once integration name is provided, execute**:
```sql
DESC CATALOG INTEGRATION <integration_name>;
```

**Check CATALOG_SOURCE**:
- `POLARIS` or `ICEBERG_REST` → Continue
- `GLUE` (legacy) or other → **STOP**: Not supported for CLD. Must recreate with REST-based integration.

**Verify it works**:
```sql
SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<integration_name>');
```

**If verification fails** → Route to appropriate catalog integration troubleshooting skill.

**If verification succeeds** → Continue to Step 1.3

---

#### Step 1.3: Check Credential Mode & External Volume

**Ask**:
```
Does your catalog integration use vended credentials (storage access provided by the catalog)?

A: Yes, vended credentials (catalog provides storage access)
   
B: No, I need to use external volume credentials
   → Snowflake accesses storage directly via external volume
   
C: I'm not sure
```

**If C (not sure)** → Check the integration:
```sql
DESC CATALOG INTEGRATION <integration_name>;
-- Look for ACCESS_DELEGATION_MODE:
-- VENDED_CREDENTIALS = catalog provides access
-- EXTERNAL_VOLUME_CREDENTIALS = need external volume
```

**If B or ACCESS_DELEGATION_MODE = EXTERNAL_VOLUME_CREDENTIALS**:

**Ask**: "Do you already have an external volume configured for this storage location?"

```sql
-- List existing external volumes
SHOW EXTERNAL VOLUMES;
```

**If no external volume exists**:
```
You need an external volume to access your Iceberg data.
**Invoke** the `iceberg-external-volume` skill to create one.

⚠️ STOP: Return here after external volume is created.
```

**If external volume exists** → **Record**: External volume name for later use

**If A (vended credentials)** → **Record**: No external volume needed

---

#### Step 1.4: Prerequisites Confirmed

**Present summary**:
```
Prerequisites Verified:
═══════════════════════════════════════════════════════════
✓ Catalog Integration: <integration_name>
  └─ Type: <POLARIS|ICEBERG_REST>
  └─ Status: Verified
  └─ Credential Mode: <Vended|External Volume>

✓ External Volume: <volume_name|Not required (vended credentials)>
═══════════════════════════════════════════════════════════
```

→ Continue to Step 2

---

### Step 2: Gather CLD Configuration

> **Load** `setup/SKILL.md` and follow its workflow to collect configuration options.

Collects:
- Database name
- Namespace filtering (ALLOWED/BLOCKED)
- Case sensitivity setting
- Nested namespace handling
- Write mode
- Sync interval

**⚠️ STOP**: setup/SKILL.md ends with configuration summary approval. Wait for user confirmation before proceeding.

### Step 3: Create Database

> **Load** `create/SKILL.md` and follow its workflow.
1. Generate CREATE DATABASE SQL
2. **⚠️ STOP**: Review SQL with user
3. Execute creation upon approval

### Step 4: Verify

→ Continue to [Verify Workflow](#verify-workflow)

---

## Verify Workflow

> **Load** `verify/SKILL.md` and follow its workflow.

---

## Troubleshoot Workflow

> **Load** `references/troubleshooting.md` for error patterns.

**For auto-refresh specific issues** (stalled, failing, cost, monitoring):
→ **Load** `../auto-refresh/SKILL.md` for in-depth debugging

After troubleshooting:
→ **Return** to Verify Workflow to confirm fixes

---

## Important Behaviors

**CLD creates externally managed (unmanaged) Iceberg tables.**

| Remote Catalog Action | Snowflake Behavior |
|-----------------------|-------------------|
| Table renamed | Drops old table, creates new |
| Table dropped | Drops from CLD (async) |
| table-uuid mismatch | Drops local table |
| **Write enabled + DROP in Snowflake** | **Propagates to remote (removes data!)** |

---

## Case Sensitivity: Query Construction Rules

After the user selects their case sensitivity mode in Step 2.3, you MUST construct all subsequent SQL queries according to these rules. Track the chosen mode throughout the session.

**When `CATALOG_CASE_SENSITIVITY = CASE_INSENSITIVE` (default)**:
- Identifiers can be used without quotes in SELECT/DML queries
- Snowflake treats `mytable`, `MYTABLE`, and `MyTable` as equivalent
- For DDL commands (CREATE ICEBERG TABLE/SCHEMA, ALTER), use double-quoted identifiers

**When `CATALOG_CASE_SENSITIVITY = CASE_SENSITIVE`**:
- You MUST use double quotes around schema and table names to preserve exact case
- Without quotes, Snowflake auto-converts identifiers to UPPERCASE, which may not match the catalog

**Rule**: When case-sensitive mode is active and you're constructing any query against the CLD, default to using double-quoted identifiers for schema and table names unless you've confirmed the identifiers are uppercase in the catalog.

---

## Understanding Sync vs Auto-Refresh

| Parameter | Level | Purpose |
|-----------|-------|---------|
| `SYNC_INTERVAL_SECONDS` | CLD | How often Snowflake discovers **new/dropped tables and namespaces** from the remote catalog |
| `REFRESH_INTERVAL_SECONDS` | Catalog Integration | How often Snowflake polls for **data changes** (new Iceberg snapshots) on individual tables |
| `AUTO_REFRESH` | Table | Whether a table participates in auto-refresh. **Enabled by default** for CLD auto-discovered tables |

> **Note**: To tune data refresh frequency, adjust `REFRESH_INTERVAL_SECONDS` on the catalog integration, not `SYNC_INTERVAL_SECONDS` on the CLD.

---

## Quick Reference

**Create CLD (vended credentials)**:
```sql
CREATE DATABASE <db_name>
  LINKED_CATALOG = (
    CATALOG = '<catalog_integration>'
  );
```

**Create CLD (with external volume)**:
```sql
CREATE DATABASE <db_name>
  LINKED_CATALOG = (
    CATALOG = '<catalog_integration>'
  )
  EXTERNAL_VOLUME = '<external_volume>';
```

**Create CLD (with options)**:
```sql
CREATE DATABASE <db_name>
  LINKED_CATALOG = (
    CATALOG = '<catalog_integration>',
    ALLOWED_NAMESPACES = ('ns1', 'ns2'),
    ALLOWED_WRITE_OPERATIONS = NONE,
    SYNC_INTERVAL_SECONDS = 60
  )
  CATALOG_CASE_SENSITIVITY = CASE_INSENSITIVE;
```

**Diagnostic Commands**:
```sql
SELECT SYSTEM$CATALOG_LINK_STATUS('<db_name>');
SHOW SCHEMAS IN DATABASE <db_name>;
SHOW ICEBERG TABLES IN DATABASE <db_name>;
SELECT SYSTEM$AUTO_REFRESH_STATUS('<db>.<schema>.<table>');
SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('<catalog_integration>');
SELECT SYSTEM$LIST_ICEBERG_TABLES_FROM_CATALOG('<catalog_integration>', '<namespace>');
```

---

## Scope

**In scope**:
- Creating catalog-linked databases
- Configuring namespace filtering, case sensitivity, write mode
- Verifying sync status
- Troubleshooting sync and auto-refresh issues

**Out of scope**:
- Creating catalog integrations → Use catalog integration skills
- Creating external volumes → Use external volume skill

---

## Stopping Points

- ✋ Intent routing: Wait for user selection (A/B/C/D)
- ✋ Step 1.1: Catalog integration check - wait for user response
- ✋ Step 1.3: Credential mode check - wait for user response
- ✋ Step 2 (setup/SKILL.md): Configuration summary approval
- ✋ Step 3 (create/SKILL.md): SQL review and approval before execution

**Resume rule:** Upon user approval ("yes", "looks good", "proceed"), continue to next step without re-asking.

---

## Output

- Successfully created and verified catalog-linked database
- Verification report with sync status, namespace count, table health
- Troubleshooting recommendations if issues detected

---

## Documentation

- [Use a catalog-linked database](https://docs.snowflake.com/en/user-guide/tables-iceberg-catalog-linked-database)
- [CREATE DATABASE (catalog-linked)](https://docs.snowflake.com/en/sql-reference/sql/create-database-catalog-linked)
- [Automatically refresh Iceberg tables](https://docs.snowflake.com/en/user-guide/tables-iceberg-auto-refresh)
