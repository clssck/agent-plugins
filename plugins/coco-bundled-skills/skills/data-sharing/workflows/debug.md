# Debug Share

Troubleshoot and diagnose issues with Snowflake shares: grant failures, consumer access problems, and permission errors.

## When to Load

Load this sub-skill when user reports:
- Share not working or consumer can't access data
- Grant failures or permission errors
- "Share does not currently have a database" error
- Consumer can see share but not data
- Any share-related error messages

## Workflow

```
Start → Step 1: Identify Issue → Step 2: Diagnose → Step 3: Fix → Step 4: Verify → Done
             ↑                        ↑               ↑
       ⚠️ STOP                  ⚠️ STOP         ⚠️ STOP
```

### Step 1: Identify the Issue

**Goal:** Understand what's not working.

**Actions:**

1. **Ask** the user:
   ```
   To help debug your share issue, please provide:
   
   1. **Share name**: What is the share called?
   2. **Error message** (if any): What error are you seeing?
   3. **Who's affected**: Provider side or consumer side?
   4. **What's not working**: 
      - Grant failing?
      - Consumer can't see the share?
      - Consumer can see share but not data?
      - Something else?
   ```

2. **Run initial diagnostics**:
   ```sql
   -- Check if share exists
   SHOW SHARES LIKE '<share_name>';
   
   -- Check share contents
   DESCRIBE SHARE <share_name>;
   
   -- Check grants to share
   SHOW GRANTS TO SHARE <share_name>;
   
   -- Check consumer access
   SHOW GRANTS OF SHARE <share_name>;
   ```

**⚠️ MANDATORY STOPPING POINT**: Confirm the issue before proceeding to diagnosis.

---

### Step 2: Diagnose the Problem

**Goal:** Identify the root cause based on symptoms.

Route to the appropriate diagnosis based on the error/symptom:

---

#### Issue: "Share does not currently have a database"

**Cause:** Grants were applied in wrong order.

**Diagnosis:**
```sql
-- Check what's currently granted
SHOW GRANTS TO SHARE <share_name>;
```

**Root cause:** Must grant DATABASE → SCHEMA → OBJECTS in order.

**→ Go to Step 3: Fix Grant Order**

---

#### Issue: "Non-secure object can only be granted to shares"

**Cause:** Trying to share a non-secure view or UDF.

**Diagnosis:**
```sql
-- View: check if secure
SHOW VIEWS LIKE '<view_name>' IN SCHEMA <db>.<schema>;
-- Look at "is_secure" column

-- UDF: list matching functions and check secure flag in output
SHOW FUNCTIONS LIKE '<fn_name>' IN SCHEMA <db>.<schema>;
```

**→ Go to Step 3: Fix Non-Secure Object**

---

#### Issue: "Insufficient privileges"

**Cause:** Missing required privileges to create or modify share.

**Diagnosis:**
```sql
-- Check current role
SELECT CURRENT_ROLE();

-- Check grants to your role
SHOW GRANTS TO ROLE <your_role>;

-- Check if role has CREATE SHARE
-- Look for: CREATE SHARE on ACCOUNT
```

**Required privileges:**
- `CREATE SHARE` on ACCOUNT
- `USAGE` on database
- `USAGE` on schema
- `SELECT` on objects to share

**→ Go to Step 3: Fix Privileges**

---

#### Issue: "Account does not exist" or invalid account

**Cause:** Consumer account identifier is incorrect.

**Diagnosis:**
```sql
-- Check current consumers on share
SHOW GRANTS OF SHARE <share_name>;
```

**Common format issues:**
- Missing organization: Use `ORG_NAME.ACCOUNT_NAME`
- Using locator vs name: Try both formats
- Typo in account name

**→ Go to Step 3: Fix Account Identifier**

---

#### Issue: Consumer can see share but can't query data

**Cause:** Consumer hasn't created database from share, or objects not properly granted.

**Diagnosis (Provider side):**
```sql
-- Verify objects are in share
DESCRIBE SHARE <share_name>;

-- Verify grants are correct
SHOW GRANTS TO SHARE <share_name>;
```

**Consumer must run:**
```sql
-- Create database from share
CREATE DATABASE <local_db_name> FROM SHARE <provider_account>.<share_name>;

-- Then query
SELECT * FROM <local_db_name>.<schema>.<table>;
```

**→ Go to Step 3: Guide Consumer**

---

#### Issue: Consumer can't see the share at all

**Cause:** Account not added to share, or wrong account identifier.

**Diagnosis:**
```sql
-- Check which accounts have access
SHOW GRANTS OF SHARE <share_name>;
```

**→ Go to Step 3: Add Consumer Account**

---

#### Issue: Share exists but is empty

**Cause:** Grants were revoked or never applied.

**Diagnosis:**
```sql
-- Check share contents
DESCRIBE SHARE <share_name>;

-- Check grant history
SHOW GRANTS TO SHARE <share_name>;
```

**→ Go to Step 3: Re-grant Objects**

---

#### Issue: View with cross-database references fails or consumer gets errors

**Cause:** View references tables, views, or policies from a **different database** than the one granted with USAGE. Missing `REFERENCE_USAGE` grant. This includes **nested views** that reference other databases.

**Symptoms:**
- Grant succeeds but consumer queries fail
- Error mentions "object does not exist" for referenced objects
- View works for provider but not consumer
- Nested view chain breaks at some level

**Diagnosis - Recursive Dependency Analysis:**
```sql
-- 1. Get ALL recursive dependencies (includes nested views, tables, functions)
SELECT 
  REFERENCED_DATABASE,
  REFERENCED_SCHEMA,
  REFERENCED_OBJECT_NAME,
  REFERENCED_OBJECT_DOMAIN
FROM TABLE(
  SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES(
    '<database>.<schema>.<view_name>',
    'VIEW'
  )
)
ORDER BY REFERENCED_DATABASE, REFERENCED_SCHEMA;

-- 2. Find all unique databases that need REFERENCE_USAGE
SELECT DISTINCT REFERENCED_DATABASE
FROM TABLE(
  SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES(
    '<database>.<schema>.<view_name>',
    'VIEW'
  )
)
WHERE REFERENCED_DATABASE != '<primary_share_database>';

-- 3. Check what's currently granted to the share
SHOW GRANTS TO SHARE <share_name>;
-- Compare: Are all referenced databases covered with REFERENCE_USAGE?

-- 4. Alternative: Get direct references only (one level)
SELECT * FROM TABLE(GET_OBJECT_REFERENCES(
  DATABASE_NAME => '<database>',
  SCHEMA_NAME => '<schema>',
  OBJECT_NAME => '<view_name>'
));
```

**Root cause:** When a view references objects in another database (tables, views, policies) - including through nested views - you must grant `REFERENCE_USAGE` on ALL databases in the dependency chain.

**→ Go to Step 3: Fix Cross-Database References**

---

#### Issue: Masking policy or row access policy from another database

**Cause:** Object has a policy (masking or row access) defined in a different database.

**Diagnosis:**
```sql
-- Check for masking policies on the table
SELECT * FROM TABLE(INFORMATION_SCHEMA.POLICY_REFERENCES(
  REF_ENTITY_NAME => '<database>.<schema>.<table>',
  REF_ENTITY_DOMAIN => 'TABLE'
));

-- Check if policy database differs from object database
-- If POLICY_DB != object's database, need REFERENCE_USAGE
```

**→ Go to Step 3: Fix Cross-Database References**

---

### Step 3: Apply Fix

**⚠️ MANDATORY STOPPING POINT**: Present the fix to user for approval before executing.

#### Fix: Grant Order

**Problem:** Grants applied in wrong order.

**Solution:** Revoke and re-grant in correct order.

```sql
-- 1. Revoke existing grants (in reverse order)
REVOKE SELECT ON ALL TABLES IN SCHEMA <db>.<schema> FROM SHARE <share_name>;
REVOKE USAGE ON SCHEMA <db>.<schema> FROM SHARE <share_name>;
REVOKE USAGE ON DATABASE <db> FROM SHARE <share_name>;

-- 2. Re-grant in correct order
-- FIRST: Database
GRANT USAGE ON DATABASE <db> TO SHARE <share_name>;

-- SECOND: Schema
GRANT USAGE ON SCHEMA <db>.<schema> TO SHARE <share_name>;

-- LAST: Objects
GRANT SELECT ON TABLE <db>.<schema>.<table> TO SHARE <share_name>;
```

---

#### Fix: Non-Secure Object

**Problem:** View or UDF is not secure.

**Option A:** Convert to secure (recommended)

```sql
-- View
ALTER VIEW <db>.<schema>.<view> SET SECURE;
-- Then retry the grant
GRANT SELECT ON VIEW <db>.<schema>.<view> TO SHARE <share_name>;

-- UDF (SQL/JavaScript — include full argument signature)
ALTER FUNCTION <db>.<schema>.<fn>(<arg_types>) SET SECURE;
-- Then retry the grant
GRANT USAGE ON FUNCTION <db>.<schema>.<fn>(<arg_types>) TO SHARE <share_name>;
```

**Option B:** Allow non-secure objects (⚠️ cannot be undone)

```sql
ALTER SHARE <share_name> SET SECURE_OBJECTS_ONLY = FALSE;
-- Then retry the grant(s) — same ALTER applies to both views and UDFs on this share

-- View
GRANT SELECT ON VIEW <db>.<schema>.<view> TO SHARE <share_name>;

-- UDF (include full argument signature)
GRANT USAGE ON FUNCTION <db>.<schema>.<fn>(<arg_types>) TO SHARE <share_name>;
```

Do not run `ALTER VIEW` / `ALTER FUNCTION ... SET SECURE` unless the user explicitly approves changing the object.

Docs: [Use secure objects to control data access](https://docs.snowflake.com/en/user-guide/data-sharing-secure-views) · [Share data in non-secured views](https://docs.snowflake.com/en/user-guide/data-sharing-views)

---

#### Fix: Privileges

**Problem:** Missing required privileges.

**Solution:** Request grants from admin.

```sql
-- Admin needs to run:
GRANT CREATE SHARE ON ACCOUNT TO ROLE <your_role>;
GRANT USAGE ON DATABASE <db> TO ROLE <your_role>;
GRANT USAGE ON SCHEMA <db>.<schema> TO ROLE <your_role>;
GRANT SELECT ON TABLE <db>.<schema>.<table> TO ROLE <your_role>;
```

---

#### Fix: Account Identifier

**Problem:** Wrong consumer account format.

**Solution:** Use correct format.

```sql
-- Try organization.account format
ALTER SHARE <share_name> ADD ACCOUNTS = ORG_NAME.ACCOUNT_NAME;

-- Or try account locator
ALTER SHARE <share_name> ADD ACCOUNTS = ABC12345;

-- For accounts in different regions
ALTER SHARE <share_name> ADD ACCOUNTS = ABC12345.us-west-2.aws;
```

---

#### Fix: Add Consumer Account

**Problem:** Consumer not added to share.

```sql
ALTER SHARE <share_name> ADD ACCOUNTS = <consumer_account>;

-- Verify
SHOW GRANTS OF SHARE <share_name>;
```

---

#### Fix: Re-grant Objects

**Problem:** Share is empty or missing objects.

```sql
-- Check what database the share should use
-- Then grant in order:
GRANT USAGE ON DATABASE <db> TO SHARE <share_name>;
GRANT USAGE ON SCHEMA <db>.<schema> TO SHARE <share_name>;
GRANT SELECT ON TABLE <db>.<schema>.<table> TO SHARE <share_name>;

-- Verify
DESCRIBE SHARE <share_name>;
```

---

#### Fix: Cross-Database References (REFERENCE_USAGE)

**Problem:** View references objects (tables, views, policies) from another database - including through nested views.

**Solution:** Recursively identify ALL referenced databases and grant `REFERENCE_USAGE` on each.

```sql
-- 1. Get ALL databases in the dependency chain (recursive)
SELECT DISTINCT REFERENCED_DATABASE
FROM TABLE(
  SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES(
    '<database>.<schema>.<view_name>',
    'VIEW'
  )
)
WHERE REFERENCED_DATABASE != '<primary_share_database>';

-- 2. For EACH database returned, grant REFERENCE_USAGE
GRANT REFERENCE_USAGE ON DATABASE <db1> TO SHARE <share_name>;
GRANT REFERENCE_USAGE ON DATABASE <db2> TO SHARE <share_name>;
-- ... repeat for all databases in the dependency chain
```

**For policies from another database:**
```sql
-- Check for policies on any objects in the dependency chain
SELECT DISTINCT POLICY_DB
FROM SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES
WHERE REF_DATABASE_NAME IN (<list_of_referenced_databases>)
  AND POLICY_DB != '<primary_share_database>';

-- Grant REFERENCE_USAGE on each policy database
GRANT REFERENCE_USAGE ON DATABASE <policy_db> TO SHARE <share_name>;
```

**Example: Nested view chain**
```
DB_A.VIEW_1 → DB_B.VIEW_2 → DB_C.BASE_TABLE (has policy from DB_D)
```

```sql
-- Primary share grants
GRANT USAGE ON DATABASE DB_A TO SHARE my_share;
GRANT USAGE ON SCHEMA DB_A.SCHEMA TO SHARE my_share;
GRANT SELECT ON VIEW DB_A.SCHEMA.VIEW_1 TO SHARE my_share;

-- REFERENCE_USAGE for entire dependency chain
GRANT REFERENCE_USAGE ON DATABASE DB_B TO SHARE my_share;
GRANT REFERENCE_USAGE ON DATABASE DB_C TO SHARE my_share;
GRANT REFERENCE_USAGE ON DATABASE DB_D TO SHARE my_share;  -- policy db
```

**Verify all dependencies are covered:**
```sql
-- Check grants on share
SHOW GRANTS TO SHARE <share_name>;

-- Verify no missing databases
-- Compare REFERENCE_USAGE grants against dependency list
```

**⚠️ Important:** `REFERENCE_USAGE` allows the share to reference objects but does NOT expose them directly to consumers. Only objects with explicit SELECT/USAGE grants are visible.

---

### Step 4: Verify Fix

**Goal:** Confirm the issue is resolved.

**Actions:**

1. **Provider-side verification:**
   ```sql
   -- Check share contents
   DESCRIBE SHARE <share_name>;
   
   -- Check grants
   SHOW GRANTS TO SHARE <share_name>;
   
   -- Check consumer access
   SHOW GRANTS OF SHARE <share_name>;
   ```

2. **Consumer-side verification** (ask consumer to run):
   ```sql
   -- List available shares
   SHOW SHARES;
   
   -- Create/refresh database from share
   CREATE OR REPLACE DATABASE <db_name> FROM SHARE <provider>.<share_name>;
   
   -- Test query
   SELECT * FROM <db_name>.<schema>.<table> LIMIT 10;
   ```

3. **Report to user:**
   ```
   ✅ Share issue resolved!
   
   **Issue:** <description of what was wrong>
   **Fix applied:** <what was done>
   
   **Verification:**
   - Share contains: <list of objects>
   - Consumer accounts: <list of accounts>
   
   **Consumer next steps:**
   CREATE DATABASE <name> FROM SHARE <provider>.<share_name>;
   ```

---

## Common Errors Quick Reference

| Error | Likely Cause | Quick Fix |
|-------|--------------|-----------|
| "Share does not currently have a database" | Wrong grant order | Grant DATABASE first, then SCHEMA, then objects |
| "Non-secure object can only be granted..." | Sharing non-secure view/UDF | **Option A:** `ALTER VIEW` / `ALTER FUNCTION ... SET SECURE` (recommended), then grant — **Option B:** `ALTER SHARE ... SET SECURE_OBJECTS_ONLY=FALSE`, then grant |
| "Account does not exist" | Wrong account format | Use `ORG.ACCOUNT` format or account locator |
| "Insufficient privileges" | Missing CREATE SHARE | Request `CREATE SHARE ON ACCOUNT` from admin |
| "Object does not exist" | Wrong object name/path | Verify object exists with `SHOW TABLES/VIEWS` |
| "Cannot grant to share" | Object type not supported | Check [supported types](https://docs.snowflake.com/en/user-guide/data-sharing-intro) |
| "Share restrictions" error | Business Critical → non-BC | Use `SHARE_RESTRICTIONS=FALSE` |
| Consumer can't see share | Account not added | `ALTER SHARE ADD ACCOUNTS` |
| Consumer can't query | Database not created | Consumer runs `CREATE DATABASE FROM SHARE` |
| "Database already exists" | Consumer DB name conflict | Use different database name |
| View works for provider but not consumer | Missing REFERENCE_USAGE | `GRANT REFERENCE_USAGE ON DATABASE <other_db> TO SHARE` |
| Consumer query fails on view with cross-db refs | View references other database | Grant `REFERENCE_USAGE` on referenced database |
| Policy error on shared object | Policy in different database | `GRANT REFERENCE_USAGE ON DATABASE <policy_db> TO SHARE` |

**Reference:** [Snowflake Data Sharing Docs](https://docs.snowflake.com/en/user-guide/data-sharing-intro)

---

## Stopping Points

- ✋ **Step 1**: After identifying the issue (confirm understanding)
- ✋ **Step 2**: After diagnosis (present findings before fixing)
- ✋ **Step 3**: Before applying fix (get approval for changes)

**Resume rule:** Upon user approval, proceed directly to next step.

## Output

- Diagnosed root cause of share issue
- Applied fix (with user approval)
- Verified share is working correctly
