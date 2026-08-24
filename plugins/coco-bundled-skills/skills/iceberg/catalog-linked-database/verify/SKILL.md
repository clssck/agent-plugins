---
name: cld-verify
description: "Verify catalog-linked database sync status and table health"
parent_skill: catalog-linked-database
---

# Catalog-Linked Database Verification

Verify sync status, namespace discovery, and table health for a catalog-linked database.

## When to Load

- From main skill Step 3: After database creation
- From main skill Verify Workflow: Direct verification request

## Prerequisites

- Catalog-linked database exists
- Database name known

---

## Workflow

### Step V1: Get Database Name

If not already known:

**Ask**: "What is the name of your catalog-linked database?"

**If unknown**, list databases:
```sql
SHOW DATABASES;
-- Catalog-linked databases have a link icon in UI
```

---

### Step V2: Check Catalog Link Status

**Execute**:
```sql
SELECT SYSTEM$CATALOG_LINK_STATUS('<database_name>');
```

**Parse response** (JSON):
- `executionState`: `RUNNING` (next sync scheduled/executing) or `FAILED` (error occurred)
- `lastLinkAttemptStartTime`: Timestamp when Snowflake last started discovery/sync
- `failedExecutionStateReason`: Error message (only appears if `FAILED`)
- `failedExecutionStateErrorCode`: Error code (only appears if `FAILED`)
- `failureDetails`: Array of entity sync failures - **empty array means healthy, non-empty indicates issues**
  - Each entry contains: `qualifiedEntityName`, `entityDomain`, `operation`, `errorCode`, `errorMessage`

**Interpret results**:
- `executionState` is `RUNNING` and `failureDetails` is empty `[]` → Sync is healthy
- `executionState` is `FAILED` → Linking operation failed, check `failedExecutionStateReason`
- `failureDetails` has entries → Specific entities failed to sync

**Present**:
```
Catalog Link Status:
═══════════════════════════════════════════════════════════
Database: <database_name>
Execution State: <RUNNING|FAILED>
Last Link Attempt: <timestamp>
Failure Details: <None|List of failures>
═══════════════════════════════════════════════════════════
```

**If FAILED or failureDetails exist** → Note failures, continue to gather more info, then troubleshoot. See [SYSTEM$CATALOG_LINK_STATUS docs](https://docs.snowflake.com/en/sql-reference/functions/system_catalog_link_status) for details.

---

### Step V3: List Schemas (Namespaces)

**Execute**:
```sql
SHOW SCHEMAS IN DATABASE <database_name>;
```

**Present**:
```
Discovered Namespaces:
─────────────────────────────
- <schema_1>
- <schema_2>
- <schema_3>
─────────────────────────────
Total: <count> namespace(s)
```

**Ask**: "Do you see your expected namespaces?"

**If empty or missing namespaces** → Note for troubleshooting (check ALLOWED/BLOCKED_NAMESPACES, case sensitivity)

---

### Step V4: List Tables and Auto-Refresh Status

**Execute**:
```sql
SHOW ICEBERG TABLES IN DATABASE <database_name>;
```

**Key columns**:
- `name`: Table name
- `schema_name`: Namespace
- `auto_refresh_status`: Refresh health (JSON, may be empty for healthy tables)

**Present summary**:
```
Discovered Tables:
─────────────────────────────
Schema: <schema_1>
  - table_a (auto_refresh: RUNNING)
  - table_b (auto_refresh: RUNNING)

Schema: <schema_2>
  - table_c (auto_refresh: STALLED)
─────────────────────────────
Total: <count> table(s)
```

**Interpret auto_refresh_status**:
- Empty/null: Normal for auto-discovered CLD tables (refresh controlled by catalog integration's `REFRESH_INTERVAL_SECONDS`)
- `RUNNING`: Healthy
- `STALLED`: Temporary issue, attempting to recover
- `STOPPED`: Unrecoverable error, requires action
- `ICEBERG_TABLE_NOT_INITIALIZED`: Table created but couldn't refresh

**If issues detected** (STALLED, STOPPED, NOT_INITIALIZED):
→ Note for Step V6. For persistent issues, **Invoke** the `auto-refresh` skill.

---

### Step V5: Check Specific Table (Optional)

**If issues found or user wants details**:

**Ask**: "Would you like to check the auto-refresh status for a specific table?"

**If yes**, get table name and execute:
```sql
SELECT SYSTEM$AUTO_REFRESH_STATUS('<database>.<schema>.<table>');
```

**Response includes**:
- `executionState`: RUNNING, STALLED, STOPPED, etc.
- `pendingSnapshotCount`: Snapshots waiting to process
- `lastRefreshTimestamp`: When last refreshed

---

### Step V6: Verification Summary

**Present complete results**:

```
Verification Results:
═══════════════════════════════════════════════════════════
Database: <database_name>
─────────────────────────────────────────────────────────────
Execution State: <RUNNING|FAILED>
Last Link Attempt: <timestamp>
Failure Details: <None|List of failures>

Namespaces Discovered: <count>
Tables Discovered: <count>

Auto-Refresh: Enabled by default for auto-discovered tables
              (Refresh interval controlled by catalog integration)

Table Health:
  Healthy (empty/RUNNING): <count>
  STALLED: <count>
  STOPPED: <count>
  NOT_INITIALIZED: <count>
═══════════════════════════════════════════════════════════
```

**If all healthy**:
```
✅ Catalog-linked database is fully operational!

Your tables are syncing from the remote catalog.
Query them directly: SELECT * FROM <database>.<schema>.<table>;
```

**If issues found**:
```
⚠️ Issues detected:

<list specific issues>

Recommendation: Load troubleshooting guide for diagnosis.
```

→ **Load** `references/troubleshooting.md`
→ After fixing, **return** to Step V2 to re-verify

**For auto-refresh specific issues** (persistent STALLED/STOPPED, monitoring needs):
→ **Invoke** the `auto-refresh` skill for in-depth debugging and monitoring setup.

---

### Step V7: Health Dashboard (Optional)

**For ongoing monitoring**, recommend the health dashboard recipe:

**Ask**: "Would you like to see a comprehensive health check query for all your catalog-linked databases?"

**If yes** → Load `references/health-dashboard.sql`

> Note: The health dashboard SQL is a template. Replace `<DATABASE_NAME>` placeholders with your actual CLD names before running.

---

## Output

Verification status report with:
- Sync status
- Namespace count
- Table count and health breakdown
- Specific issues identified

## Next Steps

**If verification succeeded**:
- User can query tables directly: `SELECT * FROM <database>.<schema>.<table>;`
- Recommend monitoring with health dashboard

**Want to create a new Iceberg table inside this CLD?**
→ **Load** `create-table/SKILL.md` to create a table using unmanaged writes.

**Want to query your data with natural language?**
→ **Invoke** the `cld-snowflake-intelligence` skill to surface your CLD tables in Snowflake Intelligence. This creates a semantic view and agent that lets you and your users ask questions in plain English.

**If issues found**:
→ **Load** `references/troubleshooting.md`
→ Diagnose specific failures
→ After fixing, **return** to Step V2 to re-verify
