---
name: dynamic-table-permissions-troubleshoot
description: "Troubleshoot dynamic table failures because of permissions/privilege issues. Use when: DT refresh fails with insufficient privileges, scheduled refresh stops working, manual refresh returns permission error. Triggers: dynamic table permissions, DT privilege error, refresh failed, insufficient privileges dynamic table."
parent_skill: dynamic-tables
---

# Dynamic Table Permissions Troubleshooting

## When to Load

Main skill routes here when user reports:
- Permission or privilege errors on DT refresh
- "Insufficient privileges" error messages
- Scheduled refresh stopped working after ownership changes
- Manual refresh fails with access denied
- Masking policy related DT failures

---

## Workflow

## Core Concept: Scheduled vs Manual Refresh

- **Scheduled Refresh**: Uses **DT Owner Role** privileges with assigned warehouse
- **Manual Refresh**: Manual refresh is triggered via ALTER DYNAMIC TABLE ... REFRESH. To alter a dynamic table, you must use a role that has either the OWNERSHIP or OPERATE privilege on that dynamic table.

### Step 1: Identify the Failure Type

**Ask user:**
```
What type of failure are you seeing?
1. Initial creation succeeded but refresh fails
2. Manual refresh (ALTER ... REFRESH) fails with "Insufficient privileges"
3. Scheduled refresh stopped working
4. Creation fails with privilege error
```

**⚠️ STOP**: Wait for user response before proceeding.

### Step 2: Gather Dynamic Table Information

***Prerequisite***
SHOW DYNAMIC TABLES, INFORMATION_SCHEMA.DYNAMIC_TABLE_GRAPH_HISTORY, and DYNAMIC_TABLE_REFRESH_HISTORY all require MONITOR on the dynamic table to see metadata.

**Run:**
```sql
SHOW DYNAMIC TABLES LIKE '<dt_name>';
```

**Extract from output:**
- `owner` → DT Owner Role
- `warehouse` → Assigned warehouse for refresh
- `scheduling_state` → Current state (ACTIVE, SUSPENDED)
- `suspend_reason_code` → If suspended, why

**Then run:**
```sql
SELECT * FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_GRAPH_HISTORY(NAME=>'<fully_qualified_dt_name>'))
ORDER BY REFRESH_START_TIME DESC
LIMIT 5;
```

### Step 3: Identify Roles and Flatten Hierarchy

| Scenario | Roles to Check |
|----------|----------------|
| Scheduled refresh fails | DT Owner Role + inherited parent roles |
| Manual refresh fails | User's current role (for OPERATE) + DT Owner Role hierarchy (for execution) |
| Creation with ownership transfer | Original creator role + new owner role hierarchy |

**Build Effective Owner Permissions by flattening role hierarchy:**

```sql
-- Step 3a: Get roles granted to the owner role
SHOW GRANTS TO ROLE <owner_role>;
```

Look for rows where `granted_on` = `ROLE` - these are parent roles.

```sql
-- Step 3b: Recursively check parent roles
SHOW GRANTS TO ROLE <parent_role_1>;
SHOW GRANTS TO ROLE <parent_role_2>;
-- Continue until no more parent roles
```

**Collect all roles in hierarchy** → These form the "Effective Owner Permissions" set.

**For manual refresh, also check user's role:**
```sql
SELECT CURRENT_ROLE();
SHOW GRANTS ON DYNAMIC TABLE <db>.<schema>.<dt_name>;
```

### Step 4: Verify Execution Privileges (DT Owner Role Hierarchy)

These are required for BOTH scheduled and manual refresh execution.
Check if ANY role in the flattened hierarchy (from Step 3) has these privileges.

#### 4a. Warehouse USAGE
```sql
SHOW GRANTS ON WAREHOUSE <assigned_warehouse>;
```
**Required:** DT Owner Role (or parent) must have `USAGE` on the warehouse assigned to the DT.

#### 4b. Source Object SELECT
```sql
SHOW GRANTS ON TABLE <source_table>;
SHOW GRANTS ON VIEW <source_view>;
SHOW GRANTS ON DYNAMIC TABLE <upstream_dt>;
```
**Required:** `SELECT` on ALL source tables directly referenced in the DT body, views, and upstream DTs (via owner or parent role). When creating a DT that depends on other DTs and doing a synchronous initial refresh (INITIALIZE = ON_CREATE, which is the default), the creator role must have OPERATE on all upstream dynamic tables, not just SELECT.
Note: SELECT on the objects directly referenced in the DT definition (tables, views, dynamic tables). They do not require direct SELECT on the base tables underneath a secure view. 

#### 4c. Target Schema/Database USAGE
```sql
SHOW GRANTS ON SCHEMA <target_schema>;
SHOW GRANTS ON DATABASE <target_database>;
```
**Required:** `USAGE` on schema and database containing the DT (via owner or parent role).

### Step 5: Verify Permissions for Manual Refresh 

**Check if user's role has OPERATE:**
```sql
SHOW GRANTS ON DYNAMIC TABLE <db>.<schema>.<dt_name>;
```
**Required:** User's role needs `OWNERSHIP` or `OPERATE` privilege on the dynamic table.

### Step 6: Check for Ownership Transfer Issues

If creation succeeded but refresh fails, ownership transfers via future grants may have broken privileges.

**More common issue: Base object ownership changed**

Future grants at schema/database level can transfer ownership of base tables, views, or upstream DTs to a different role, causing the DT owner to lose SELECT access:

```sql
-- Check future grants on schema/database that might affect base objects
SHOW FUTURE GRANTS IN SCHEMA <source_schema>;
SHOW FUTURE GRANTS IN DATABASE <source_database>;
```

Look for `OWNERSHIP` grants on TABLES, VIEWS, or DYNAMIC TABLES. If present, newly created or recreated source objects will be owned by a different role, and the DT owner may lose SELECT.

**Less common: DT itself transferred**

```sql
SHOW FUTURE GRANTS IN SCHEMA <dt_schema>;
```

If output shows `OWNERSHIP` on DYNAMIC TABLES, the DT was transferred to a different role after creation.

**Resolution:** Verify DT owner role still has SELECT on all source objects (Step 4b), and grant if missing.

### Step 7: Check Masking Policy References

If base tables have masking policies, they MUST use fully qualified names:

```sql
SHOW MASKING POLICIES IN SCHEMA <schema>;
DESC MASKING POLICY <policy_name>;
```

Moreover, policy owner must have required privileges on objects referenced by the policy.

**Check policy body references use:** `database.schema.object` format, not unqualified names.

### Step 8: Account Usage Investigation (Optional)

For comprehensive privilege check on DT Owner Role, or when investigating issues older than ~14 days (beyond INFORMATION_SCHEMA retention):

**For longer refresh history** (account usage view, requires `IMPORTED PRIVILEGES` on `SNOWFLAKE`): see [references/dt-refresh-analysis.md — Account-level refresh history (optional)](../references/dt-refresh-analysis.md#account-level-refresh-history-optional) and https://docs.snowflake.com/en/sql-reference/account-usage/dynamic_table_refresh_history

**For privilege analysis:**

```sql
SELECT *
FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
WHERE GRANTEE_NAME IN ('<owner_role>', '<inherited_roles>')
  AND DELETED_ON IS NULL
  AND (
    (GRANTED_ON IN ('TABLE','VIEW','DYNAMIC TABLE')
     AND NAME = '<source_object_name>'
     AND PRIVILEGE = 'SELECT')
    OR
    (GRANTED_ON = 'WAREHOUSE'
     AND NAME = '<assigned_warehouse>'
     AND PRIVILEGE = 'USAGE')
  );
```

## Privilege Requirements Summary

| Action | Role Checked | Object | Privilege |
|--------|--------------|--------|-----------|
| Create DT | Creator | Schema | CREATE DYNAMIC TABLE |
| Create DT | Creator | Source objects | SELECT |
| Create DT | Creator | Warehouse | USAGE |
| Create DT | Creator | Database/Schema | USAGE |
Create DT (with upstream DTs, INITIALIZE = ON_CREATE) |	Creator |	Upstream dynamic tables |	OPERATE |
| Scheduled Refresh | DT Owner (or parent) | Warehouse | USAGE |
| Scheduled Refresh | DT Owner (or parent) | Source objects | SELECT |
| Scheduled Refresh | DT Owner (or parent) | Target Schema/DB | USAGE |
| Manual Refresh | User Role | Dynamic Table | OWNERSHIP/OPERATE |


## Common Fixes

### Grant missing warehouse usage:
```sql
GRANT USAGE ON WAREHOUSE <wh> TO ROLE <owner_role>;
```

### Grant missing SELECT on source:
```sql
GRANT SELECT ON TABLE <source> TO ROLE <owner_role>;
```

### Grant OPERATE for manual refresh:
```sql
GRANT OPERATE ON DYNAMIC TABLE <dt> TO ROLE <user_role>;
```

### Transfer ownership properly:
```sql
GRANT OWNERSHIP ON DYNAMIC TABLE <dt> TO ROLE <new_owner>;
```
Then verify new owner has all execution privileges.

## Stopping Points

- ✋ Step 1: Wait for failure type
- ✋ After diagnosis: Present findings and recommended fixes

---

## Output

- Identified missing privileges
- SQL commands to grant required privileges
- Explanation of root cause
