---
name: catalog-integration-verify
description: "Verify catalog integration is working correctly (universal for all catalog types). Use when: verify catalog integration, test catalog integration connection, check catalog integration status, validate catalog integration setup."
---

# Catalog Integration Verification

Validate that your catalog integration is properly configured and can connect to the external catalog.

## When to Use

Use this verification process after creating any catalog integration (OpenCatalog, Glue IRC, Unity Catalog, OneLake, Delta Sharing, etc.) to ensure it's operational.

## Prerequisites

- Catalog integration successfully created
- Integration name known

## Verification Workflow

### Step 1: Check Integration Exists

Verify the integration was created with correct configuration.

**Execute**:
```sql
SHOW CATALOG INTEGRATIONS LIKE '<integration_name>';
DESC CATALOG INTEGRATION <integration_name>;
```

**Expected Output**: Integration details with `ENABLED = TRUE`

**Key Fields to Verify**:
- `name`: Matches your integration name
- `enabled`: TRUE
- `catalog_source`: Appropriate value (POLARIS, ICEBERG_REST, GLUE, DELTA_SHARING, etc.)
- `catalog_uri`: Matches your catalog endpoint URL (for REST catalogs)
- `catalog_name`: Matches your catalog identifier

**Present to user**:
```
Integration Configuration:
─────────────────────────────
Name: <integration_name>
Enabled: <TRUE|FALSE>
Catalog Source: <catalog_source>
Catalog URI: <url>
Catalog Name: <catalog_name>
─────────────────────────────
```

**If ENABLED = FALSE**: Integration exists but is disabled - this is unusual for new creation.

**⚠️ STOPPING POINT**: If configuration looks incorrect, pause and ask user if values should be different.

### Step 2: Test Connection

Use `SYSTEM$VERIFY_CATALOG_INTEGRATION()` to test connection to the catalog.

**Execute**:
```sql
SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<integration_name>');
```

**Expected Success Response**:
```json
{
  "success": true
}
```

**Present to user**: "✅ Connection test passed! Integration can authenticate with the catalog."

**If Failure Response**:
```json
{
  "success": false,
  "errorCode": "004155",
  "errorMessage": "Failed to perform OAuth client credential flow..." // Or other error
}
```

**If Failed**:
- Present error message to user
- **⚠️ MANDATORY STOPPING POINT**: Authentication or connectivity issue detected
- Load catalog-specific troubleshooting guide for diagnosis
- Wait for user direction before attempting fixes

### Step 3: List Namespaces

**Ask**: "Would you like to list namespaces from the catalog to verify discovery works?"

> **Note**: When verification is called as part of the **create workflow** (post-creation), skip this prompt and automatically list namespaces and tables to provide a complete verification report without extra friction.

**If Yes** (or auto-run from create workflow) → Execute the following:
```sql
SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('<integration_name>');
```

**If No** → Skip to Step 4

**Expected Output**: JSON array of namespaces
```json
[
  "my_namespace",
  "another_namespace"
]
```

**Present to user**:
```
Discovered Namespaces:
─────────────────────────────
- <namespace_1>
- <namespace_2>
- <namespace_3>
─────────────────────────────
```

**Ask**: "Do you see your expected namespace(s) in this list?"

**If Empty Array**:
- May indicate no namespaces exist in catalog
- Or service principal/role lacks proper privileges
- **⚠️ STOPPING POINT**: Ask user if they expect to see namespaces

**If Unexpected Results**:
- **⚠️ STOPPING POINT**: Load troubleshooting guide

### Step 4: List Tables

**Ask**: "Would you like to list tables from a specific namespace? If yes, which namespace?"

**If Yes** → Ask user for namespace name, then execute the following
**If No** → Skip to Step 5

**Execute**:
```sql
SELECT SYSTEM$LIST_ICEBERG_TABLES_FROM_CATALOG(
  '<integration_name>',
  '<namespace>'
);
```

**Expected Output**: JSON array of tables
```json
[
  "customer_data",
  "transaction_history",
  "product_catalog"
]
```

**Present to user**:
```
Tables in namespace '<namespace>':
─────────────────────────────
- <table_1>
- <table_2>
- <table_3>
─────────────────────────────
```

**Ask**: "Are these the tables you want to query from Snowflake?"

**If Empty Array**:
- No tables found in namespace
- Check namespace spelling (case-sensitive in some catalogs)
- Verify tables exist in the external catalog
- **⚠️ STOPPING POINT**: Ask user to confirm namespace and table existence

**If Tables Missing**:
- Some expected tables not visible
- May indicate service principal/role lacks table-level privileges
- **⚠️ STOPPING POINT**: Load troubleshooting guide

### Step 5: Verification Summary

**Present complete verification results**:

```
Verification Results:
═══════════════════════════════════════════════════════════
✅ Integration exists and is enabled
✅ Connection test: PASSED
✅ Namespaces discovered: <count> namespace(s)
✅ Tables visible: <count> table(s) in '<namespace>'
═══════════════════════════════════════════════════════════

Your catalog integration is fully configured and operational!
```

**If all checks passed**:
- Congratulate user
- Return to main skill
- Proceed to next steps (table creation)

**If any checks failed**:
- Summarize which checks failed
- **⚠️ MANDATORY STOPPING POINT**: Do not proceed to next steps
- Load catalog-specific troubleshooting guide
- Wait for user direction on fixing issues

## Verification Checklist

Track verification status:

- [ ] Integration exists with correct configuration
- [ ] ENABLED = TRUE
- [ ] `SYSTEM$VERIFY_CATALOG_INTEGRATION()` returns success
- [ ] Namespaces are discoverable
- [ ] Tables are visible in expected namespace

## Output

Verification status report indicating whether catalog integration is operational or requires troubleshooting.

### Step 6: Next Steps (On Success)

**If all verification checks passed**:

**Load** `shared/next-steps/SKILL.md` (path: `../shared/next-steps/SKILL.md`)

Present options to the user for accessing catalog tables:
- Option A: Create individual Iceberg tables
- Option B: Create catalog-linked database (recommended)

DO NOT skip this step. After successful verification, users need guidance on how to actually use the catalog integration.

---

## Catalog-Specific Notes

This is a universal verification process. However, different catalog types may have:
- **Different authentication methods**: OAuth, Bearer token, SigV4
- **Different error messages**: Refer to catalog-specific troubleshooting guides
- **Different privilege models**: OpenCatalog roles vs AWS IAM vs Unity Catalog grants

For catalog-specific troubleshooting, refer back to the parent skill's troubleshooting documentation.
