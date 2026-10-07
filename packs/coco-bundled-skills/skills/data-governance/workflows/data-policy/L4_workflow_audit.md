# Guided Workflow: Audit Existing Policies

Use this file when the user needs to audit existing policies, generate an inventory, evaluate policy health, or consolidate scattered policies.

---

## Step 1: Gather Scope

**Ask user:**
```
To audit your data policies (masking, row access, projection), let's start with a focused scope:

1. **Database**: Which database to start with? (or "all")
2. **Data Type**: Which data type to focus on? (STRING, NUMBER, TIMESTAMP, VARIANT, or "all")
3. **Specific Policy**: Any specific policy name to review? (or "all")
```

**Recommended approach:**
- Start narrow: one database + one data type
- Review findings, then expand

**⚠️ STOP**: Confirm audit scope before proceeding.

---

## Step 2: Discover Policies

Based on confirmed scope, run discovery queries. **Run these ONCE and reuse the results** — don't repeat SHOW commands.

```sql
-- List masking policies (run ONCE, save results)
SHOW MASKING POLICIES IN DATABASE <db>;
-- Or for account-wide: SHOW MASKING POLICIES IN ACCOUNT;

-- List row access policies (run ONCE)
SHOW ROW ACCESS POLICIES IN DATABASE <db>;

-- Check policy assignments on a specific table
SELECT 
  POLICY_NAME,
  POLICY_KIND,
  REF_COLUMN_NAME AS COLUMN_NAME
FROM TABLE(<db>.INFORMATION_SCHEMA.POLICY_REFERENCES(
  REF_ENTITY_NAME => '<db>.<schema>.<table>',
  REF_ENTITY_DOMAIN => 'TABLE'
));
```

> 💡 **Efficiency**: Run `SHOW` commands once per scope. Don't repeat them — the results don't change during an audit session.

---

## Step 3: Evaluate Policies

### Efficiency Tips
- **Batch GET_DDL calls**: Fetch multiple policy definitions in one query (up to 5-10 per call)
- **Sample first**: For large accounts with many policies, analyze a representative sample (10-15 policies) before expanding
- **Cache SHOW results**: Run SHOW commands once and reuse the results

### Batch GET_DDL Pattern
```sql
-- Fetch multiple policy definitions in one query (more efficient)
SELECT 
  GET_DDL('POLICY', 'db1.schema1.policy1') as policy1_ddl,
  GET_DDL('POLICY', 'db1.schema1.policy2') as policy2_ddl,
  GET_DDL('POLICY', 'db2.schema2.policy3') as policy3_ddl;
```

### Individual GET_DDL (for single policy inspection)
```sql
SELECT GET_DDL('POLICY', '<db>.<schema>.<policy_name>');
```

### Check if Functions are Memoizable
If the policy calls a function, check if that function is memoizable:
```sql
-- List user functions and check is_memoizable column
SHOW USER FUNCTIONS IN SCHEMA <db>.<schema>;
```

### Evaluation Checklist

Severity is contextual: judge by how much real risk or maintenance cost the pattern creates in this account, not by the pattern alone. Do not over-escalate issues that are deterministic by Snowflake's semantics — for example, a CASE with no ELSE returns NULL in Snowflake, which is not a data leak.

| Check | Typical Severity | Issue | Recommendation |
|-------|------------------|-------|----------------|
| `CURRENT_ROLE()` comparison in an account with role hierarchy or secondary roles | **HIGH** — users inheriting the authorized role are wrongly denied access | Role inheritance / `USE SECONDARY ROLES ALL` is not respected | Replace with `IS_ROLE_IN_SESSION()` |
| Same unmask logic duplicated across multiple policies | **MEDIUM** | Drift between policies, harder to audit and evolve | Extract to a shared memoizable function (split pattern) |
| Long hardcoded role list repeated across policies | **MEDIUM** | Same role changes must be made in many places | Externalize to a function or mapping table |
| Inline `IN (SELECT …)` against a mapping table — large table, or view-backed, or repeated across policies | **MEDIUM** | Duplicated logic; recomputed work when the subquery is non-trivial | Wrap in a memoizable function |
| Inline `IN (SELECT …)` against a small, stable table used by a single policy | **LOW** | Mostly a reuse / consistency concern; not a performance emergency | Migrate to memoizable function when you have a second caller |
| `CURRENT_ROLE()` in an account with a strictly flat role model and no secondary roles | **LOW** | Functionally correct today but becomes a bug the moment hierarchy is introduced | Migrate to `IS_ROLE_IN_SESSION()` proactively |
| Implicit `ELSE` in CASE | **LOW** — readability / reviewability finding, **not** a security bug. See the worked example below. Do **not** classify this as CRITICAL / data-leak / silent-corruption / silent-data-loss — those framings are objectively wrong. | Add explicit `ELSE <masked_value>` or `ELSE NULL` so the fail-closed path is visible to reviewers |
| No `COMMENT` on policy | **LOW** | Ownership, purpose, and classification are not discoverable during audit | Add `COMMENT = '<Purpose>. Owner: <Team>. Protected: <Classification>'` |
| Policies scattered across team schemas at enterprise scale | **LOW–MEDIUM** (depends on scale) | Harder to audit, version, govern once there are many policies and owners | Centralize in a governance database |

### Worked example: what missing `ELSE` actually does in Snowflake

This is the single most frequently misdiagnosed audit finding. Before classifying any missing-`ELSE` policy, confirm what it actually returns. In Snowflake (and standard SQL), `CASE` with no matching `WHEN` and no `ELSE` returns `NULL` — deterministic, documented, not a leak.

```sql
-- A masking policy with no ELSE clause. Unauthorized users get NULL — fail-closed.
CREATE OR REPLACE MASKING POLICY demo_no_else
AS (val STRING) RETURNS STRING ->
  CASE WHEN IS_ROLE_IN_SESSION('HR_ADMIN') THEN val END;

-- Applied to a column:
ALTER TABLE employees MODIFY COLUMN ssn SET MASKING POLICY demo_no_else;

-- As a non-HR_ADMIN role:
SELECT ssn FROM employees LIMIT 1;
-- ssn: NULL     (not the real SSN; not a random value; not an error)
```

The correct audit finding is therefore: "add an explicit `ELSE` clause so reviewers can see the fail-closed path", not "unauthorized users can see real data" and not "silent data corruption".

### Spotting Problems in Policy Code

**Inline subquery — reuse/consistency issue, sometimes performance**
```sql
CREATE MASKING POLICY mask_v1 AS (val STRING) RETURNS STRING ->
  CASE
    WHEN CURRENT_ROLE() IN (SELECT role FROM mapping_table) THEN val
    ELSE '***MASKED***'
  END;
```
This is typically fine in isolation against a small stable table — Snowflake will materialize the subquery once per statement. Flag it when the same lookup is duplicated across policies, when the mapping table is large or view-backed, or when you need a single source of truth for authorization.

**Preferred: memoizable function**
```sql
CREATE MASKING POLICY fast_mask AS (val STRING) RETURNS STRING ->
  CASE
    WHEN is_authorized_role() THEN val  -- Cached, reusable across policies
    ELSE '***MASKED***'
  END;
```

---

**Long hardcoded role list duplicated across policies**
```sql
WHEN CURRENT_ROLE() IN ('ADMIN', 'MANAGER', 'ANALYST', 'USER1', 'USER2', 
                        'USER3', 'USER4', 'USER5', 'USER6', 'USER7') THEN val
```
A handful of stable roles in one policy is acceptable. Flag it when the same list appears in multiple policies or changes often.

**Preferred: externalize to a function or mapping table**
```sql
WHEN is_authorized_role() THEN val
```

---

**`CURRENT_ROLE()` comparison — real bug under role hierarchy or secondary roles**
```sql
WHEN CURRENT_ROLE() = 'ANALYST' THEN val  -- Fails for users who inherit ANALYST
```

**Preferred: `IS_ROLE_IN_SESSION()`**
```sql
WHEN IS_ROLE_IN_SESSION('ANALYST') THEN val  -- Works with inheritance and secondary roles
```

---

**🔴 BAD: Policy scattered in data schema**
```sql
CREATE MASKING POLICY SALES_DB.DATA.email_mask ...  -- Mixed with data
```

**✅ GOOD: Centralized in governance database**
```sql
CREATE MASKING POLICY GOVERNANCE_DB.POLICIES.email_mask ...  -- Easy to find/audit
```

---

## Step 4: Generate Health Report

Present findings in this format:

```
## Masking Policy Health Report

### Scope
- Database: <database or "all">
- Data Type: <data_type or "all">

### Policy Inventory
| POLICY_DATABASE | POLICY_SCHEMA | POLICY_NAME | DATA_TYPE | COLUMNS_PROTECTED |
|-----------------|---------------|-------------|-----------|-------------------|
| ...             | ...           | ...         | ...       | ...               |

### Summary by Data Type
| DATA_TYPE | POLICY_COUNT |
|-----------|--------------|
| STRING    | X            |
| NUMBER    | Y            |

### Issues Found
1. [SEVERITY] Issue description
   - Policy: <POLICY_DATABASE>.<POLICY_SCHEMA>.<POLICY_NAME>
   - Recommendation: <fix>

### Recommendations
- [ ] Action item 1
- [ ] Action item 2
```

**⚠️ STOP**: Present report and ask if user wants to apply fixes.

---

## Step 5: Apply Fixes (if approved)

Execute remediation SQL for each approved fix.

---

## Step 6: Migrate Policies Safely

When consolidating scattered policies to a governance database:

### Migration Principles
1. **Never break production** — Always test before applying
2. **One column at a time** — Don't bulk migrate
3. **Have a rollback plan** — Know how to undo changes
4. **Verify after each step** — Test that masking still works

### Safe Migration Steps (Zero Downtime)

```sql
-- ===========================================
-- STEP 1: Create improved policy in GOVERNANCE_DB
-- ===========================================
CREATE OR REPLACE MASKING POLICY GOVERNANCE_DB.POLICIES.email_mask 
AS (val STRING) RETURNS STRING ->
  CASE
    WHEN IS_ROLE_IN_SESSION('PII_VIEWER') THEN val
    ELSE '***MASKED***'
  END
  COMMENT = 'Generic email masking policy. Migrated from SALES_DB.DATA.email_mask_v1';

-- ===========================================
-- STEP 2: Test new policy in non-production (if available)
-- ===========================================
-- Apply to a test table first
ALTER TABLE TEST_DB.TEST_SCHEMA.test_table 
  MODIFY COLUMN email SET MASKING POLICY GOVERNANCE_DB.POLICIES.email_mask;

-- Verify it works
USE ROLE <authorized_role>;
SELECT email FROM TEST_DB.TEST_SCHEMA.test_table LIMIT 5;  -- Should see real data

USE ROLE <unauthorized_role>;
SELECT email FROM TEST_DB.TEST_SCHEMA.test_table LIMIT 5;  -- Should see masked data

-- ===========================================
-- STEP 3: Migrate production columns (one at a time)
-- ===========================================
-- First, remove old policy
ALTER TABLE SALES_DB.DATA.customers 
  MODIFY COLUMN email UNSET MASKING POLICY;

-- Then, apply new policy
ALTER TABLE SALES_DB.DATA.customers 
  MODIFY COLUMN email SET MASKING POLICY GOVERNANCE_DB.POLICIES.email_mask;

-- ===========================================
-- STEP 4: Verify immediately after each migration
-- ===========================================
-- Check policy is applied (qualify INFORMATION_SCHEMA with database)
SELECT * FROM TABLE(SALES_DB.INFORMATION_SCHEMA.POLICY_REFERENCES(
  REF_ENTITY_NAME => 'SALES_DB.DATA.CUSTOMERS',
  REF_ENTITY_DOMAIN => 'TABLE'
)) WHERE POLICY_KIND = 'MASKING_POLICY';

-- Test with different roles
USE ROLE <authorized_role>;
SELECT email FROM SALES_DB.DATA.customers LIMIT 3;

USE ROLE <unauthorized_role>;
SELECT email FROM SALES_DB.DATA.customers LIMIT 3;

-- ===========================================
-- STEP 5: Drop old policy ONLY after all columns migrated
-- ===========================================
-- First, verify no columns still use old policy
-- Check each table that might have used it:
SELECT POLICY_NAME, REF_COLUMN_NAME 
FROM TABLE(SALES_DB.INFORMATION_SCHEMA.POLICY_REFERENCES(
  REF_ENTITY_NAME => 'SALES_DB.DATA.CUSTOMERS',
  REF_ENTITY_DOMAIN => 'TABLE'
)) WHERE POLICY_NAME = 'EMAIL_MASK_V1';

-- If empty, safe to drop
DROP MASKING POLICY SALES_DB.DATA.email_mask_v1;
```

### Rollback Pattern (if something goes wrong)

```sql
-- Undo the migration immediately
ALTER TABLE SALES_DB.DATA.customers 
  MODIFY COLUMN email UNSET MASKING POLICY;

-- Re-apply old policy
ALTER TABLE SALES_DB.DATA.customers 
  MODIFY COLUMN email SET MASKING POLICY SALES_DB.DATA.email_mask_v1;

-- Verify rollback worked
SELECT email FROM SALES_DB.DATA.customers LIMIT 3;
```

---

## Step 7: Expand Scope (optional)

**Ask user:**
```
Current scope completed: <database> / <data_type>

Would you like to expand the audit?
1. All databases for <data_type> policies
2. All data types in <database>
3. Full account scan
4. Done for now
```

If user chooses to expand, return to Step 2 with new scope.

---

## Stopping Points

- ✋ Step 1: Scope confirmed
- ✋ Step 4: Health report reviewed
- ✋ Step 6: Migration plan approved before executing
- ✋ Step 7: Expansion decision made
