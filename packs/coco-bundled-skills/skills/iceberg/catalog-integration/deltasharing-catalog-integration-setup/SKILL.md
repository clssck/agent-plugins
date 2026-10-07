---
name: deltasharing-catalog-integration-setup
description: "Setup and verify catalog integration for Delta Sharing. Triggers: create delta sharing catalog integration, connect snowflake to delta sharing, setup delta sharing, configure delta sharing catalog, delta sharing bearer token, query delta sharing tables from snowflake, delta sharing rest catalog, troubleshoot delta sharing integration, verify delta sharing catalog integration, delta sharing credential vending, fix delta sharing connection, debug delta sharing, delta sharing open protocol, databricks delta sharing snowflake."
---

# Delta Sharing Catalog Integration

Setup, verify, or troubleshoot a Snowflake catalog integration for Delta Sharing.

## Intent Routing (FIRST)

**Ask the user**:
```
What would you like to do?

A: Create a new catalog integration for Delta Sharing
   → Setup Snowflake to connect to a Delta Sharing server

B: Verify an existing catalog integration
   → Test connection and list shares/schemas/tables

C: Troubleshoot a catalog integration
   → Diagnose and fix connection issues
```

**Route based on response**:
- **A (Create)** → **Load** `setup/SKILL.md` then follow [Create Workflow](#create-workflow)
- **B (Verify)** → **Load** `verify/SKILL.md` then follow [Verify Workflow](#verify-workflow)
- **C (Troubleshoot)** → **Load** `references/troubleshooting.md` then follow [Troubleshoot Workflow](#troubleshoot-workflow)

---

## Create Workflow

> **⚠️ REQUIRED**: Load `setup/SKILL.md` FIRST before proceeding with this workflow.

Create a new catalog integration to connect Snowflake to a Delta Sharing server.

### Step 1: Prerequisites

Follow `setup/SKILL.md` to collect:

Collect one-by-one:
1. Delta Sharing endpoint URL (from the provider's credential file)
2. Bearer token (from the provider's credential file)
3. Share name (`CATALOG_NAME`) — the Delta Sharing share to connect to
4. Access delegation mode (vended credentials or external volume)
5. Integration name

**⚠️ STOP**: Confirm prerequisites before proceeding

### Step 2: Create Integration

**Load** `create/SKILL.md` and follow its workflow:

1. Generate CREATE CATALOG INTEGRATION SQL
2. **⚠️ STOP**: Review SQL with user
3. Execute creation
4. Confirm integration is created, enabled, and verified

### Step 3: Verify

→ Continue to [Verify Workflow](#verify-workflow)

---

## Verify Workflow

> **⚠️ REQUIRED**: Load `verify/SKILL.md` FIRST before proceeding with this workflow.

Verify an existing catalog integration is working correctly.

### Step V1: Get Integration Name

**Ask**: "What is the name of your catalog integration?"

If user doesn't know:
```sql
SHOW CATALOG INTEGRATIONS;
```

### Step V2: Check Integration Status

Follow `verify/SKILL.md` which loads the shared verification workflow.

Run verification checks:
```sql
-- Check integration exists and is enabled
SHOW CATALOG INTEGRATIONS LIKE '<integration_name>';

-- Verify connection
SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<integration_name>');

-- List schemas in the configured share
SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('<integration_name>');

-- List tables in a schema
SELECT SYSTEM$LIST_ICEBERG_TABLES_FROM_CATALOG('<integration_name>', '<schema>');
```

### Step V3: Report Results

**If all checks pass**:
```
Integration verified successfully
- Status: ENABLED
- Connection: Working
- Schemas: <count> discovered
- Tables: Accessible
```

**If any check fails** → Continue to [Troubleshoot Workflow](#troubleshoot-workflow)

### Step V4: Next Steps

**If verification succeeded**:

**Load** `shared/next-steps/SKILL.md` (path: `../shared/next-steps/SKILL.md`)

Guide user through options for accessing catalog tables:
- Option A: Create individual Iceberg tables
- Option B: Create catalog-linked database (recommended)

---

## Troubleshoot Workflow

> **⚠️ REQUIRED**: Load `references/troubleshooting.md` to have error patterns and solutions available.

Diagnose and fix issues with an existing catalog integration.

### Step T1: Get Integration Name

**Ask**: "What is the name of your catalog integration?"

### Step T2: Gather Error Information

**Ask**: "What error or issue are you experiencing?"

Common symptoms:
- Integration creation failed
- Verification returns error
- Cannot list schemas
- Cannot see tables
- Authentication / token errors

### Step T3: Diagnose

Use error patterns from `references/troubleshooting.md` to diagnose.

Run diagnostics:
```sql
-- Check integration details
DESC CATALOG INTEGRATION <integration_name>;

-- Test connection
SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<integration_name>');

-- List schemas
SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('<integration_name>');
```

### Step T4: Match Error Pattern

Common issues and solutions in `references/troubleshooting.md`:
1. Invalid or expired bearer token
2. Insufficient privileges
3. Schema/table discovery issues
4. Access delegation mode error
5. Invalid CATALOG_URI
6. Feature not enabled

**⚠️ STOP**: Present diagnosis and wait for user direction before applying fixes.

---

## Scope

This skill focuses on **Snowflake-side setup**:
- Creating catalog integrations for Delta Sharing
- Verification
- Troubleshooting

**Key characteristics of Delta Sharing integration**:
- Uses `CATALOG_SOURCE = DELTA_SHARING`
- Uses `TABLE_FORMAT = DELTA`
- Authentication via **bearer token** from the Delta Sharing provider's credential file
- `CATALOG_NAME` specifies the share to connect to (e.g., `'my_share'` or `'shares/my_share'`)
- Supports both `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` and `EXTERNAL_VOLUME_CREDENTIALS`
- Only supports **public connectivity** (no PrivateLink support)
- Compatible with any Delta Sharing-compliant server (Databricks Unity Catalog, etc.)

**Delta Sharing hierarchy**:
- **Share** → configured via `CATALOG_NAME` in the integration
- **Schema** → namespace within a share; returned by `SYSTEM$LIST_NAMESPACES_FROM_CATALOG`
- **Table** → individual table within a schema; returned by `SYSTEM$LIST_ICEBERG_TABLES_FROM_CATALOG`

**Out of scope** (separate resources):
- Delta Sharing server setup on the provider side
- Generating or managing bearer tokens on the provider side
- External volume creation

---

## Quick Reference

**Catalog Integration SQL**:
```sql
CREATE OR REPLACE CATALOG INTEGRATION <name>
  CATALOG_SOURCE = DELTA_SHARING
  TABLE_FORMAT = DELTA
  REST_CONFIG = (
    CATALOG_URI = '<delta_sharing_endpoint>'
    CATALOG_NAME = '<share_name>'              -- e.g. 'my_share' or 'shares/my_share'
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS  -- optional; omit to use EXTERNAL_VOLUME_CREDENTIALS
  )
  REST_AUTHENTICATION = (
    TYPE = BEARER
    BEARER_TOKEN = '<bearer_token>'
  )
  ENABLED = TRUE;
```

**Diagnostic Commands**:
```sql
SHOW CATALOG INTEGRATIONS LIKE '<name>';
DESC CATALOG INTEGRATION <name>;
SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<name>');
SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('<name>');
SELECT SYSTEM$LIST_ICEBERG_TABLES_FROM_CATALOG('<name>', '<schema>');
```

---

## Success Criteria

- Integration shows `ENABLED = TRUE`
- `SYSTEM$VERIFY_CATALOG_INTEGRATION()` returns success
- Schemas (namespaces) discoverable within the configured share
- Tables visible within schemas

---

## Documentation

- [Snowflake Iceberg Tables](https://docs.snowflake.com/user-guide/tables-iceberg)
