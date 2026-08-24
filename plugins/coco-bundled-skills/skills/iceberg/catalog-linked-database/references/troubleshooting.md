---
name: cld-troubleshooting
description: "Diagnose and fix catalog-linked database issues"
parent_skill: catalog-linked-database
---

# Troubleshooting Catalog-Linked Databases

Diagnose and fix issues with catalog-linked databases.

## When to Load

- Database creation failed
- Sync status shows ERROR
- Tables not discovered
- Auto-refresh issues
- Query failures

---

## Diagnostic Commands

```sql
-- Check catalog link status
SELECT SYSTEM$CATALOG_LINK_STATUS('<database_name>');

-- Get full CLD configuration (shows all settings including catalog integration, external volume, namespace filters, etc.)
SELECT SYSTEM$GET_CATALOG_LINKED_DATABASE_CONFIG('<database_name>');

-- List schemas
SHOW SCHEMAS IN DATABASE <database_name>;

-- List tables with auto-refresh status
SHOW ICEBERG TABLES IN DATABASE <database_name>;

-- Check specific table auto-refresh
SELECT SYSTEM$AUTO_REFRESH_STATUS('<db>.<schema>.<table>');

-- Check underlying catalog integration
DESC CATALOG INTEGRATION <integration_name>;
SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<integration_name>');
```

---

## Common Issues

### 1. Wrong Catalog Source

**Symptom**: Database creation fails or no tables sync

**Cause**: Catalog integration uses `CATALOG_SOURCE = GLUE` (legacy) instead of `ICEBERG_REST`

**Check**:
```sql
DESC CATALOG INTEGRATION <integration_name>;
-- Look for CATALOG_SOURCE value
```

**Solution**: CLD requires `CATALOG_SOURCE = POLARIS` or `ICEBERG_REST`. Recreate catalog integration with Glue IRC or appropriate REST catalog type.

---

### 2. Catalog Integration Verification Fails

**Symptom**: `SYSTEM$CATALOG_LINK_STATUS` returns `failureDetails` array with authentication/connection issues

**Cause**: Underlying catalog integration has issues

**Debug**:
```sql
SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<integration_name>');
```

**Solution**: Fix catalog integration first using the appropriate catalog integration skill (glueirc, unitycatalog, opencatalog).

---

### 3. Namespaces Not Discovered

**Symptom**: `SHOW SCHEMAS` returns empty or missing expected namespaces

**Causes & Solutions**:

| Cause | Check | Solution |
|-------|-------|----------|
| ALLOWED_NAMESPACES too restrictive | `SYSTEM$GET_CATALOG_LINKED_DATABASE_CONFIG('<db>')` | Add missing namespaces or remove filter |
| BLOCKED_NAMESPACES blocking | `SYSTEM$GET_CATALOG_LINKED_DATABASE_CONFIG('<db>')` | Remove from blocked list |
| Case sensitivity mismatch | Compare catalog vs Snowflake names | Use correct CATALOG_CASE_SENSITIVITY |
| Nested namespaces ignored | NAMESPACE_MODE setting | Set FLATTEN_NESTED_NAMESPACE if needed |
| Permissions in remote catalog | Check remote catalog grants | Grant access to service principal/role |

> **Note**: If you specify both ALLOWED_NAMESPACES and BLOCKED_NAMESPACES, the BLOCKED_NAMESPACES list takes precedence. A namespace in both lists will be blocked. You must remove the namespace from BLOCKED_NAMESPACES to allow it to sync.

**Case Sensitivity Details**:

For `CASE_INSENSITIVE` catalogs (Glue, Unity):
- Remote namespace `MyNamespace` appears as `mynamespace` in Snowflake
- All identifiers normalized to lowercase

For `CASE_SENSITIVE` catalogs (OpenCatalog):
- Must match exactly: `"MyNamespace"` (with quotes)

---

### 4. Tables Not Discovered

**Symptom**: Namespace exists but tables missing

**Causes & Solutions**:

| Cause | Solution |
|-------|----------|
| Tables not Iceberg format | CLD only discovers Iceberg tables |
| Permissions in remote catalog | Grant SELECT on tables to service principal |
| Namespace filtering | Check ALLOWED/BLOCKED_NAMESPACES includes the namespace |
| Sync still in progress | Wait for SYNC_INTERVAL_SECONDS, check status again |

---

### 5. Table Not Initialized

**Symptom**: `auto_refresh_status` shows `ICEBERG_TABLE_NOT_INITIALIZED`

**Cause**: Table was discovered but Snowflake couldn't read its metadata

**Common reasons**:
- Corrupted metadata file in remote catalog
- Invalid Iceberg table format
- Storage access issues
- Catalog connection failure
- Catalog authentication failure

**Debug**:
```sql
SELECT SYSTEM$AUTO_REFRESH_STATUS('<db>.<schema>.<table>');
```

**Solutions**:
1. Fix the table in the remote catalog
2. Verify storage permissions (external volume or vended credentials)
3. After fixing, enable auto-refresh:
```sql
ALTER ICEBERG TABLE <db>.<schema>.<table> SET AUTO_REFRESH = TRUE;
```

---

### 6. Auto-Refresh Stalled or Failing

> **Note**: For CLD auto-discovered tables, auto-refresh is enabled by default. The refresh frequency is controlled by `REFRESH_INTERVAL_SECONDS` on the **catalog integration**, not the CLD.

**Execution States** (see [SYSTEM$AUTO_REFRESH_STATUS](https://docs.snowflake.com/en/sql-reference/functions/system_auto_refresh_status)):
| State | Meaning | Action |
|-------|---------|--------|
| `RUNNING` | Healthy, automated refresh running as expected | None |
| `STALLED` | Temporary issue, attempting to recover | Wait; check if persists |
| `STOPPED` | Unrecoverable error, requires action | Investigate and fix |
| `ICEBERG_TABLE_NOT_INITIALIZED` | Error occurred during table creation | Resolve error, then enable auto-refresh |

**Debug**:
```sql
SELECT SYSTEM$AUTO_REFRESH_STATUS('<db>.<schema>.<table>');
```

**Quick Fix - Toggle Auto-Refresh**:
```sql
-- Disable (stop polling)
ALTER ICEBERG TABLE <db>.<schema>.<table> SET AUTO_REFRESH = FALSE;

-- Re-enable
ALTER ICEBERG TABLE <db>.<schema>.<table> SET AUTO_REFRESH = TRUE;
```

**Monitor via Event Table** (if configured):
```sql
SELECT *
FROM <event_table>
WHERE record:'name' = 'iceberg_auto_refresh_snapshot_lifecycle'
  AND resource_attributes:'snow.table.name' = '<table_name>'
ORDER BY timestamp DESC
LIMIT 10;
```

**For persistent or complex auto-refresh issues**:

First, check the catalog integration's refresh interval:
```sql
DESC CATALOG INTEGRATION <integration_name>;
-- Look for REFRESH_INTERVAL_SECONDS
```

If the issue persists after toggling, or you need:
- In-depth debugging with event logs
- Monitoring and alerting setup
- Cost investigation
- Refresh interval tuning

→ **Invoke** the `auto-refresh` skill for comprehensive auto-refresh debugging.

---

### 7. Write Operations Failing

**Symptom**: DROP TABLE or CREATE TABLE fails

**Cause**: `ALLOWED_WRITE_OPERATIONS = NONE`

**Check**:
```sql
SELECT SYSTEM$GET_CATALOG_LINKED_DATABASE_CONFIG('<database_name>');
-- Parse JSON response: check "allowed_write_operations" field
```

**Solution**: If writes needed, alter database:
```sql
ALTER DATABASE <database_name> UPDATE LINKED_CATALOG SET ALLOWED_WRITE_OPERATIONS = ALL;
```

**WARNING**: With write enabled, `DROP TABLE` in Snowflake propagates to remote catalog and **deletes data**.

---

### 8. table-uuid Mismatch

**Symptom**: Table disappears from CLD unexpectedly

**Cause**: The table-uuid in Snowflake doesn't match the remote catalog (e.g., table was recreated externally)

**Behavior**: Snowflake drops the local table during sync. The remote table is NOT affected.

**Solution**: Table will be re-discovered on next sync if it still exists in remote catalog.

---

### 9. Remote Table Renamed

**Symptom**: Old table name disappears, new table name appears

**Cause**: Table was renamed in remote catalog

**Behavior**: Snowflake drops the old table and creates a new one with the new name. This is expected behavior.

---

### 10. Sync Latency

**Symptom**: Changes in remote catalog take too long to appear

**Causes**:
- Large number of namespaces (7,500+ namespaces ≈ 1 hour)
- Large number of tables (500,000+ tables ≈ 1 hour for refresh)
- SYNC_INTERVAL_SECONDS set too high

**Solutions**:
- Reduce scope with ALLOWED_NAMESPACES
- Create separate CLDs for different latency requirements
- Adjust SYNC_INTERVAL_SECONDS:
```sql
ALTER DATABASE <database_name> UPDATE LINKED_CATALOG SET SYNC_INTERVAL_SECONDS = 30;
```

---

## ALTER DATABASE Limitations

For full syntax details, see: [ALTER DATABASE (catalog-linked)](https://docs.snowflake.com/en/sql-reference/sql/alter-database-catalog-linked)

**What CAN be changed** (examples):
```sql
-- Modify namespace filtering
ALTER DATABASE <db> UPDATE LINKED_CATALOG ADD ('ns1', 'ns2') TO ALLOWED_NAMESPACES;
ALTER DATABASE <db> UPDATE LINKED_CATALOG REMOVE ('ns1') FROM BLOCKED_NAMESPACES;

-- Change write mode or sync interval
ALTER DATABASE <db> UPDATE LINKED_CATALOG SET ALLOWED_WRITE_OPERATIONS = ALL;
ALTER DATABASE <db> UPDATE LINKED_CATALOG SET SYNC_INTERVAL_SECONDS = 60;
```

**What CANNOT be changed**:
- CATALOG (catalog integration)
- EXTERNAL_VOLUME
- CATALOG_CASE_SENSITIVITY
- NAMESPACE_MODE / NAMESPACE_FLATTEN_DELIMITER

To change these, you must **recreate the database**.

---

## Health Dashboard

For comprehensive monitoring across all CLDs, see `references/health-dashboard.sql`.

---

## After Troubleshooting

After applying fixes:
→ **Return** to `verify/SKILL.md` Step V2 to re-verify the catalog-linked database status.
