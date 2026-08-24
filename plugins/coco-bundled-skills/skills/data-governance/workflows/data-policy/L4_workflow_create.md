# Guided Workflow: Create New Policies

Use this file when the user wants to create new policies, extend existing ones, or says "protect the data."

**Prerequisites:** The universal intake questions in the data-policy skill router (Step 1) should already be answered before entering this workflow. If not, ask them now.

---

## Step 1: Resolve Scope and Ask Policy-Type-Specific Follow-Ups

Start by making sure Cortex knows which tables or columns need protection, then ask **only** the follow-up questions for the selected policy type. Skip any question the user has already answered.

### 1.1 Resolve Target Scope

**If the user wants Cortex to discover sensitive columns automatically:**

1. Confirm the target database or schema to scan.
2. Check whether auto-classification is enabled on the target database:
   ```sql
   SHOW PARAMETERS LIKE 'CLASSIFICATION_PROFILE' IN DATABASE <database>;
   ```
3. If auto-classification is enabled, load the **sensitive-data classification workflow** to identify candidate sensitive columns, then return here once the target columns are confirmed.
4. If auto-classification is not enabled, ask whether the user wants to enable it first. If yes, load the **sensitive-data classification workflow**. If no, ask the user to provide the specific tables/columns to protect before continuing.

**If the user already knows which tables or columns need protection:**

- Confirm any missing database, schema, table, or column names before continuing.

### 1.2 Policy-Type-Specific Follow-Ups

### Masking Policy Follow-Ups

1. **What data type are the target columns?** — STRING (text like email, SSN, phone), NUMBER (salary, account numbers), TIMESTAMP/DATE/TIME, or VARIANT (JSON/semi-structured)?
2. **What should unauthorized users see?** — NULL (secure default, recommended), a fixed placeholder like `'***MASKED***'`, a partial mask (e.g., last 4 digits of SSN), or a hash (preserves uniqueness for joins)?
3. **Do multiple roles need different levels of access?** — For example: admins see full value, support sees partial mask, everyone else sees NULL. If yes, identify each tier and its mask format.

### Row Access Policy Follow-Ups

1. **Which column(s) should the policy evaluate to decide row visibility?** — For example, `region`, `department`, `tenant_id`.
2. **What logic determines row access?** — Direct role check (`IS_ROLE_IN_SESSION`), a mapping table that maps roles/users to allowed values, or a user attribute?
3. **Does the policy need a mapping table?** — If yes, what is the table name and which columns link the user's identity to the row filter value?

### Projection Policy Follow-Ups

1. **What should happen when projection is denied?** — Fail the query entirely (`ALLOW => FALSE`), or return NULLs while allowing the query to succeed (`ENFORCEMENT => 'NULLIFY'`)?
2. **Is this for a data clean room (unconditional block) or conditional by role?**

### Aggregation Policy Follow-Ups

1. **What minimum group size should queries be forced to aggregate to?** — Common values: 2, 5, 10, 100.
2. **Should the constraint apply to rows or to distinct entities?** — If entities, which column (e.g., `customer_id`, `user_id`)?
3. **Should any roles bypass the aggregation constraint?** — If yes, which roles?

---

## Step 2: Check for Existing Policies

Before creating a new policy, check what already exists. Run these discovery queries immediately (no confirmation needed for read-only SQL).

### 2.1 Find Policies on the Target Table

```sql
SELECT
  REF_COLUMN_NAME AS COLUMN_NAME,
  POLICY_NAME,
  POLICY_KIND
FROM TABLE(<db>.INFORMATION_SCHEMA.POLICY_REFERENCES(
  REF_ENTITY_NAME => '<db>.<schema>.<table>',
  REF_ENTITY_DOMAIN => 'TABLE'
))
ORDER BY REF_COLUMN_NAME;
```

### 2.2 Find Existing Policies of the Same Type

Run the command that matches the policy type you are creating:

```sql
-- Masking policy
SHOW MASKING POLICIES IN DATABASE <db>;

-- Row access policy
SHOW ROW ACCESS POLICIES IN DATABASE <db>;

-- Projection policy
SHOW PROJECTION POLICIES IN DATABASE <db>;

-- Aggregation policy
SHOW AGGREGATION POLICIES IN DATABASE <db>;
```

Then get the definition of any relevant policy:
```sql
SELECT GET_DDL('POLICY', '<db>.<schema>.<policy_name>');
```

### 2.3 Decide What to Reuse

If the current policy type is **masking** and you are reusing similar access rules, examine the policy body to determine the implementation pattern:

| What You See in Policy Body | Decision |
|-----------------------------|----------|
| Calls a shared function like `unmask_condition()` | **Already split** — create new policy using same function |
| Hardcoded roles in CASE statement | **Not split** — apply split pattern first (Step 3) |
| Direct subquery or complex logic | **Not split** — extract to function first (Step 3) |
| No suitable existing policy | **Create new** — use split pattern from the start (Step 4) |

**Masking split vs. not split:**
```
SPLIT (good):                       NOT SPLIT (anti-pattern):
CASE                                 CASE
  WHEN schema.unmask_condition()       WHEN CURRENT_ROLE() IN ('A', 'B')
  THEN val                             THEN val
  ELSE '***'                           ELSE '***'
END                                  END
     ^                                    ^
     Calls a shared function              Unmask logic embedded directly
```

For **row access, projection, or aggregation** policies, inspect the existing DDL for reusable role checks, mapping tables, enforcement modes, thresholds, or other access logic. Reuse those patterns where they match the requested behavior; otherwise continue to Step 4 with a new policy.

> **Split pattern principle:** Unmask logic should live in ONE place (a memoizable function), not duplicated across masking policies. See the **proven patterns reference**, Pattern 2, for full details.

---

## Step 3: Apply the Split Pattern (If Needed)

When extending a policy that has embedded unmask logic, split it out first.

> **Order matters:** Create the function FIRST, before creating or modifying any policies that reference it.

### 3.1 Create the Shared Unmask Function

```sql
CREATE OR REPLACE FUNCTION <schema>.unmask_condition()
RETURNS BOOLEAN
MEMOIZABLE
AS
$$
  IS_ROLE_IN_SESSION('AUTHORIZED_ROLE_1')
  OR IS_ROLE_IN_SESSION('AUTHORIZED_ROLE_2')
$$;
```

### 3.2 Refactor the Existing Policy

```sql
-- Unset from columns first
ALTER TABLE <table> MODIFY COLUMN <col> UNSET MASKING POLICY;

-- Recreate using the function
CREATE OR REPLACE MASKING POLICY <schema>.MASK_STRING_PII
AS (val STRING) RETURNS STRING ->
  CASE
    WHEN <schema>.unmask_condition() THEN val
    ELSE '***MASKED***'
  END
COMMENT = 'Masks STRING PII. Uses shared unmask_condition() for auth.';

-- Reapply
ALTER TABLE <table> MODIFY COLUMN <col> SET MASKING POLICY <schema>.MASK_STRING_PII;
```

> **Pre-write approval:** Before executing the above, summarize the changes, show the exact SQL, and wait for user confirmation.

---

## Step 4: Create the Policy

Use the split pattern from the start when creating new policies.

**Pre-write approval:** Before executing any `CREATE` or `ALTER` below, summarize what will be created and wait for user confirmation.

### Masking Policy

```sql
-- Step 1: Create shared function (if it doesn't exist)
CREATE OR REPLACE FUNCTION <schema>.unmask_condition()
RETURNS BOOLEAN
MEMOIZABLE
AS
$$
  IS_ROLE_IN_SESSION('ROLE_A')
  OR IS_ROLE_IN_SESSION('ROLE_B')
$$;

-- Step 2: Create policy using the function
CREATE OR REPLACE MASKING POLICY <schema>.MASK_<TYPE>_PII
AS (val <DATA_TYPE>) RETURNS <DATA_TYPE> ->
  CASE
    WHEN <schema>.unmask_condition() THEN val
    ELSE <masked_value>
  END
COMMENT = '<Purpose>. Owner: <Team>. Protected: <Classification>';

-- Step 3: Apply to column
ALTER TABLE <table> MODIFY COLUMN <col>
  SET MASKING POLICY <schema>.MASK_<TYPE>_PII;
```

> **Pre-write approval reminder:** Show the exact SQL you plan to run, summarize the intended changes, and wait for user confirmation before executing.

> See the **proven patterns reference**, Pattern 2, for templates covering STRING, NUMBER, TIMESTAMP, DATE, and TIME data types.

### Row Access Policy

```sql
CREATE OR REPLACE ROW ACCESS POLICY <schema>.FILTER_BY_<ATTRIBUTE>
AS (<filter_col> STRING) RETURNS BOOLEAN ->
  IS_ROLE_IN_SESSION('<authorized_role>')
  OR <filter_col> = <mapping_condition>
COMMENT = '<Purpose>. Owner: <Team>.';

ALTER TABLE <table>
  ADD ROW ACCESS POLICY <schema>.FILTER_BY_<ATTRIBUTE> ON (<filter_col>);
```

### Projection Policy

```sql
CREATE OR REPLACE PROJECTION POLICY <schema>.HIDE_<COLUMN_DESC>
AS () RETURNS PROJECTION_CONSTRAINT ->
  CASE
    WHEN IS_ROLE_IN_SESSION('<authorized_role>')
    THEN PROJECTION_CONSTRAINT(ALLOW => TRUE)
    ELSE PROJECTION_CONSTRAINT(ALLOW => FALSE)
  END
COMMENT = '<Purpose>. Owner: <Team>.';

ALTER TABLE <table> MODIFY COLUMN <col>
  SET PROJECTION POLICY <schema>.HIDE_<COLUMN_DESC>;
```

### Aggregation Policy

```sql
CREATE OR REPLACE AGGREGATION POLICY <schema>.AGG_<CONSTRAINT_DESC>
AS () RETURNS AGGREGATION_CONSTRAINT ->
  CASE
    WHEN IS_ROLE_IN_SESSION('<bypass_role>')
    THEN NO_AGGREGATION_CONSTRAINT()
    ELSE AGGREGATION_CONSTRAINT(MIN_GROUP_SIZE => <num>)
  END
COMMENT = '<Purpose>. Owner: <Team>.';

ALTER TABLE <table>
  ADD AGGREGATION POLICY <schema>.AGG_<CONSTRAINT_DESC>;
```

---

## Step 5: Verify

Test that the policy works as expected:

```sql
-- 1. Check policy is applied
SELECT * FROM TABLE(<db>.INFORMATION_SCHEMA.POLICY_REFERENCES(
  REF_ENTITY_NAME => '<db>.<schema>.<table>',
  REF_ENTITY_DOMAIN => 'TABLE'
));

-- 2. Test with authorized role
USE ROLE <authorized_role>;
SELECT <protected_column> FROM <table> LIMIT 5;
-- Expected: See real data

-- 3. Test with unauthorized role
USE ROLE <unauthorized_role>;
SELECT <protected_column> FROM <table> LIMIT 5;
-- Expected: See masked/filtered data
```

---

## Step 6: Recommend Scale Path

After the immediate problem is solved, mention future options if relevant:

- **Tag-based policies:** For protecting many objects that share a classification. Supported for masking, tokenization, row access, projection, aggregation, and join policies. See the **proven patterns reference**, Pattern 4 (tag-based policies at scale) for the bind syntax across all six kinds, and Pattern 1 (ABAC) for attribute-driven access.
- **Centralized governance schema:** Keep all policies in one place. See the **best-practices reference**.
- **Shared functions:** Already using split pattern = easy to extend to new data types.

---

## Decision Summary

| Scenario | Action |
|----------|--------|
| New policy, no existing | Create with split pattern from start (Step 4) |
| Extend existing policy (already split) | Create new policy using same function (Step 4) |
| Extend existing policy (not split) | Apply split pattern first (Step 3), then create new (Step 4) |
| Multiple tables need same protection | Consider tag-based policies (Step 6) |

---

## Stopping Points

- ✋ Step 1: Follow-up questions answered — confirm understanding
- ✋ Step 2: Existing policies evaluated — **split or not?**
- ✋ Before any `CREATE`, `ALTER`, `DROP`, or `APPLY` (pre-write approval rule)
- ✋ Step 5: Verification complete
