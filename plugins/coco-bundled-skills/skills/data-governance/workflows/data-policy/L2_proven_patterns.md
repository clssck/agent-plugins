# Proven Solution Patterns

Use this file when the user wants reusable patterns or examples of how to implement policies at scale.

## Pattern 1: Attribute-Based Access Control (ABAC)
Use user tags plus attribute mapping tables to drive masking or row filtering without duplicating policies.

**Why it's good**
- Centralizes authorization in a single mapping table; no policy duplication across tables.
- Scales with tags: add attributes or roles without rewriting policies.
- Keeps policy logic stable while access rules change in data.

**When to use**
- You have many columns/rows to protect and want one policy per data type or per tag.
- Access decisions depend on user attributes (role, department, clearance).
- You need to update access quickly without changing policy code.

**Context / tradeoffs**
- Requires governance discipline for tags and mapping table ownership.
- Per-row/tag lookups can add overhead; consider memoizable functions if needed.
- Best for consistent, organization-wide access rules rather than ad‑hoc exceptions.

### Column-Level Masking (Policy Uses Tags for Attributes)
```sql
-- Step 1: Setup
CREATE OR REPLACE DATABASE DEMO_DB;
USE DEMO_DB;

-- Step 2: Create access mapping table
CREATE OR REPLACE TABLE access_allowed (
  user_role_tag STRING,
  attribute STRING
);

-- HR can access HR_DATA; IT can access IT_DATA
INSERT INTO access_allowed VALUES
  ('HR', 'HR_DATA'),
  ('IT', 'IT_DATA');

-- Step 3: Create tags
CREATE OR REPLACE TAG user_attribute;
CREATE OR REPLACE TAG column_attribute;

-- Step 4: Create masking policy using column/user tags
CREATE OR REPLACE MASKING POLICY attribute_based_masking_policy
AS (val STRING)
RETURNS STRING ->
  CASE
  WHEN EXISTS (
      SELECT 1
      FROM access_allowed
      WHERE attribute = SYSTEM$GET_TAG_ON_CURRENT_COLUMN('column_attribute')
        AND user_role_tag = SYSTEM$GET_TAG('user_attribute', CURRENT_USER(), 'USER')
  )
  THEN val
  ELSE '***masked***'
  END;

-- Step 5: Attach masking policy to column tag
ALTER TAG column_attribute SET MASKING POLICY attribute_based_masking_policy;

-- Step 6: Create table with column tags
CREATE OR REPLACE TABLE employee_info (
  name STRING,
  ssn STRING WITH TAG (column_attribute = 'HR_DATA'),
  ip STRING WITH TAG (column_attribute = 'IT_DATA')
);

-- Step 7: Insert sample data
INSERT INTO employee_info VALUES
  ('Alice', '123-45-6789', '192.168.0.1'),
  ('Bob', '987-65-4321', '10.0.0.1');

-- Step 8a: Query as HR
ALTER USER ADMIN SET TAG user_attribute = 'HR';
-- ✅ HR sees SSN
-- ❌ HR sees IP as masked
SELECT '--- HR VIEW ---' AS view_context, * FROM employee_info;

-- Step 8b: Switch to IT role
ALTER USER ADMIN SET TAG user_attribute = 'IT';
-- ✅ IT sees IP
-- ❌ IT sees SSN as masked
SELECT '--- IT VIEW ---' AS view_context, * FROM employee_info;
```

### Row-Level Access (Policy Uses Tags for Attributes)
```sql
-- Step 1: Setup
CREATE OR REPLACE DATABASE DEMO_DB;
USE DEMO_DB;

-- Step 2: Create access mapping table
CREATE OR REPLACE TABLE access_allowed (
  user_role_tag STRING,
  row_attribute STRING
);

-- HR_MANAGER can access HR_DEPARTMENT; IT_MANAGER can access IT_DEPARTMENT
INSERT INTO access_allowed VALUES
  ('HR_MANAGER', 'HR_DEPARTMENT'),
  ('IT_MANAGER', 'IT_DEPARTMENT');

-- Step 3: Create user_attribute tag (only one tag needed)
CREATE OR REPLACE TAG user_attribute;

-- Step 4: Create row access policy using row_attribute column and user tag
CREATE OR REPLACE ROW ACCESS POLICY attribute_based_raw_access_policy
AS (row_attribute STRING)
RETURNS BOOLEAN ->
  EXISTS (
  SELECT 1
  FROM access_allowed
  WHERE row_attribute = access_allowed.row_attribute
    AND user_role_tag = SYSTEM$GET_TAG('user_attribute', CURRENT_USER(), 'USER')
  );

-- Step 5: Create employee_info table with a row_attribute column
CREATE OR REPLACE TABLE employee_info (
  name STRING,
  ssn STRING,
  ip STRING,
  department STRING  -- This is the row_attribute: HR_DEPARTMENT, IT_DEPARTMENT
);

-- Step 6: Apply row access policy to department column
ALTER TABLE employee_info ADD ROW ACCESS POLICY attribute_based_raw_access_policy ON (department);

-- Step 7: Insert sample data
INSERT INTO employee_info VALUES
  ('Alice', '123-45-6789', '192.168.0.1', 'HR_DEPARTMENT'),
  ('Bob', '987-65-4321', '10.0.0.1', 'IT_DEPARTMENT');

-- Step 8a: Query as HR manager
ALTER USER ADMIN SET TAG user_attribute = 'HR_MANAGER';
-- ✅ HR_MANAGER sees only HR_DEPARTMENT rows
SELECT  '--- HR_MANAGER VIEW ---'AS view_context, * FROM employee_info;

-- Step 8b: Switch to IT manager
ALTER USER ADMIN SET TAG user_attribute = 'IT_MANAGER';
-- ✅ IT_MANAGER sees only IT_DEPARTMENT rows
SELECT '--- IT_MANAGER VIEW ---' AS view_context, * FROM employee_info;
```

## Pattern 2: Split Pattern (Unmask Condition + Memoizable Function)

**The core idea: SPLIT unmask logic from masking logic.**

Instead of embedding role checks directly in each policy body, extract ("split") them into a single memoizable function. All policies then call this shared function.

```
❌ BEFORE (not split):              ✅ AFTER (split):
┌─────────────────────────┐        ┌─────────────────────────┐
│ MASK_STRING_PII         │        │ unmask_condition()      │  ← Single source of truth
│ ├─ CASE WHEN ROLE IN... │        │ └─ ROLE IN ('A','B')    │
│ └─ THEN val ELSE mask   │        └─────────────────────────┘
├─────────────────────────┤                    ▲
│ MASK_TIMESTAMP_PII      │                    │ calls
│ ├─ CASE WHEN ROLE IN... │  ──────────────────┼───────────────
│ └─ THEN val ELSE mask   │        ┌───────────┴───────────┐
└─────────────────────────┘        │                       │
 (duplicated logic)          ┌─────▼─────┐         ┌───────▼───────┐
                             │STRING_PII │         │TIMESTAMP_PII  │
                             │WHEN func()│         │WHEN func()    │
                             └───────────┘         └───────────────┘
```

**Why it's good**
- Single source of truth for "who can see cleartext"
- Adding a new role = update ONE function (all policies inherit the change)
- Faster evaluation when the same condition is used across many policies
- Cleaner policy definitions and easier audits

**When to use**
- Multiple masking policies share the same access rule
- You want consistent behavior across string/number/time/timestamp columns
- **Extending an existing policy to a new data type**
- You see hardcoded roles in an existing policy (refactor to split pattern)

**Context / tradeoffs**
- Function logic should be small and deterministic; avoid heavy queries.
- Memoization means changes to the condition require redeploying the function.
- Ensure return types match masking policy outputs (especially for time/date/timestamp).

### Core Pattern: Memoizable Unmask Function

> To check whether an existing policy is already split, see the **conversational create workflow**, Step 2.3.
```sql
-- Step 1: Create the shared unmask condition function
CREATE OR REPLACE FUNCTION GOVERNANCE.unmask_condition()
RETURNS BOOLEAN
MEMOIZABLE
AS
$$
  IS_ROLE_IN_SESSION('ACCOUNTADMIN')
  OR IS_ROLE_IN_SESSION('SECURITYADMIN')
  OR IS_ROLE_IN_SESSION('DATA_OWNER')
$$;
```

### Policy Templates by Data Type

Use these templates when extending protection to new data types:

```sql
-- STRING (VARCHAR) - for text PII like SSN, email, names
CREATE OR REPLACE MASKING POLICY GOVERNANCE.MASK_STRING_PII AS (val VARCHAR)
    RETURNS VARCHAR ->
    CASE
        WHEN GOVERNANCE.unmask_condition() THEN val
        ELSE '***MASKED***'
    END
COMMENT = 'Masks STRING PII. Authorized roles see cleartext.';

-- NUMBER - for numeric PII like salary, account numbers
CREATE OR REPLACE MASKING POLICY GOVERNANCE.MASK_NUMBER_PII AS (val NUMBER)
    RETURNS NUMBER ->
    CASE
        WHEN GOVERNANCE.unmask_condition() THEN val
        ELSE -1
    END
COMMENT = 'Masks NUMBER PII. Authorized roles see actual value.';

-- TIMESTAMP - for temporal PII like created_at, birth_datetime
CREATE OR REPLACE MASKING POLICY GOVERNANCE.MASK_TIMESTAMP_PII AS (val TIMESTAMP)
    RETURNS TIMESTAMP ->
    CASE
        WHEN GOVERNANCE.unmask_condition() THEN val
        ELSE '1900-01-01 00:00:00'::TIMESTAMP
    END
COMMENT = 'Masks TIMESTAMP PII. Authorized roles see actual timestamp.';

-- DATE - for date PII like birth_date, hire_date  
CREATE OR REPLACE MASKING POLICY GOVERNANCE.MASK_DATE_PII AS (val DATE)
    RETURNS DATE ->
    CASE
        WHEN GOVERNANCE.unmask_condition() THEN val
        ELSE '1900-01-01'::DATE
    END
COMMENT = 'Masks DATE PII. Authorized roles see actual date.';

-- TIME - for time PII like appointment_time
CREATE OR REPLACE MASKING POLICY GOVERNANCE.MASK_TIME_PII AS (val TIME)
    RETURNS TIME ->
    CASE
        WHEN GOVERNANCE.unmask_condition() THEN val
        ELSE '00:00:00'::TIME
    END
COMMENT = 'Masks TIME PII. Authorized roles see actual time.';
```

### Extending to a New Data Type

When adding protection for a new data type (e.g., customer has STRING policy, needs TIMESTAMP):

1. **Check if unmask function exists**: `SHOW USER FUNCTIONS IN SCHEMA GOVERNANCE;`
2. **If function doesn't exist**: Create it FIRST (see "Core Pattern" above)
3. **Create new policy using the function**: Copy template above, adjust return type and masked value
4. **Apply to columns**: `ALTER TABLE ... MODIFY COLUMN ... SET MASKING POLICY ...;`
5. **Verify consistency**: Test with same roles to confirm matching behavior

> ⚠️ **Order matters:** The function must exist BEFORE you create policies that reference it.

---

## Pattern 3: Entitlement Table Pattern

**The core idea: Externalize access decisions to a data table.**

Instead of hardcoding role lists in policies, store access rules in an entitlement table. Policies query this table to make dynamic access decisions.

**Why it's good**
- Access changes are DATA changes, not CODE changes
- Adding/removing roles = INSERT/DELETE, no policy redeploy
- Auditability: entitlement table shows all access grants
- Supports complex access levels (FULL, MASKED, NONE)

**When to use**
- Many roles need different access levels
- Access rules change frequently
- You need audit trails of who can access what
- Multi-tenant or data-source-specific access control

### Entitlement Table Structure
```sql
-- Create policies schema (if it doesn't exist for this domain)
CREATE SCHEMA IF NOT EXISTS IT_SECURITY.POLICIES
COMMENT = 'Data governance policies for IT Security data';

-- Create entitlement table
CREATE OR REPLACE TABLE IT_SECURITY.POLICIES.DATA_ACCESS_CONTROL (
    ROLE_NAME VARCHAR,
    DATA_SOURCE VARCHAR,      -- 'ALL' or specific source
    ACCESS_LEVEL VARCHAR,     -- 'FULL', 'MASKED', or 'NONE'
    CONSTRAINT pk_access PRIMARY KEY (ROLE_NAME, DATA_SOURCE)
);

-- Populate with access rules
INSERT INTO IT_SECURITY.POLICIES.DATA_ACCESS_CONTROL VALUES
    ('IT_SECURITY_ADMIN_RL', 'ALL', 'FULL'),
    ('IT_SECURITY_ANALYST_RL', 'ALL', 'MASKED'),
    ('SECURITYADMIN', 'ALL', 'FULL'),
    ('DATA_SCIENTIST_RL', 'INTERNAL', 'MASKED'),
    ('DATA_SCIENTIST_RL', 'EXTERNAL', 'NONE');
```

### Masking Policy Using Entitlement Table
```sql
CREATE OR REPLACE MASKING POLICY IT_SECURITY.POLICIES.mask_pii_variant 
AS (val VARIANT, data_source VARCHAR) RETURNS VARIANT ->
  CASE
    -- Admin bypass
    WHEN IS_ROLE_IN_SESSION('IT_SECURITY_ADMIN_RL') THEN val
    -- Full access check
    WHEN EXISTS (
      SELECT 1 FROM IT_SECURITY.POLICIES.DATA_ACCESS_CONTROL
      WHERE IS_ROLE_IN_SESSION(ROLE_NAME)
      AND (DATA_SOURCE = data_source OR DATA_SOURCE = 'ALL')
      AND ACCESS_LEVEL = 'FULL'
    ) THEN val
    -- Masked access - remove sensitive fields
    WHEN EXISTS (
      SELECT 1 FROM IT_SECURITY.POLICIES.DATA_ACCESS_CONTROL
      WHERE IS_ROLE_IN_SESSION(ROLE_NAME)
      AND (DATA_SOURCE = data_source OR DATA_SOURCE = 'ALL')
      AND ACCESS_LEVEL = 'MASKED'
    ) THEN OBJECT_DELETE(OBJECT_DELETE(OBJECT_DELETE(val, 'email'), 'password'), 'ip_address')
    ELSE NULL  -- Secure default
  END
COMMENT = 'Masks PII in VARIANT data based on entitlement table. Owner: IT Security Team';
```

### Row Access Policy Using Entitlement Table
```sql
CREATE OR REPLACE ROW ACCESS POLICY IT_SECURITY.POLICIES.rap_data_access
AS (data_source VARCHAR) RETURNS BOOLEAN ->
  IS_ROLE_IN_SESSION('IT_SECURITY_ADMIN_RL')
  OR EXISTS (
    SELECT 1 FROM IT_SECURITY.POLICIES.DATA_ACCESS_CONTROL
    WHERE IS_ROLE_IN_SESSION(ROLE_NAME)
    AND (DATA_SOURCE = data_source OR DATA_SOURCE = 'ALL')
    AND ACCESS_LEVEL IN ('FULL', 'MASKED')
  )
COMMENT = 'Controls row-level access by data source. Owner: IT Security Team';
```

---

## Pattern 4: Tag-Based Policies at Scale (all six policy kinds)

Bind a data protection policy to a **tag** once, then set the tag on a database, schema, table, view, or column. Tag inheritance applies the policy everywhere the tag is set — including objects created later. Snowflake supports tag-based attach for **all six** policy kinds: masking, tokenization, row access, projection, aggregation, and join.

> This differs from Pattern 1 (ABAC), where the policy is attached *directly* and merely *reads* user/column tags. Here the policy itself is **bound to the tag** via `ALTER TAG ... SET <KIND> POLICY`, so setting the tag is what applies the policy.

**Why it's good**
- Write the policy once, bind it once, protect many objects — new objects under a tagged scope are protected automatically.
- Classification-driven: a tag set by auto-classification can carry the policy.

**When to use**
- Many objects share one classification and need the same protection.
- You want protection to follow a tag rather than be applied object-by-object.

**Rules to respect** (Snowflake enforces these)
- A tag carries **one** row-access / projection / aggregation / join policy, or **≤1 masking policy per data type**; a tag holds *either* masking policies *or* one of the other kinds — never a mix.
- A directly-attached policy takes precedence over the tag-based one of the same kind (aggregation: only when the `ENTITY KEY` set matches; otherwise both are enforced).
- Level by kind: row access / aggregation / join protect whole tables/views (tag at table/view/schema/database); masking / tokenization / projection protect columns (tag at column, or inherited).

### Bind syntax by kind

```sql
-- Column-protecting kinds (no attach clause):
ALTER TAG <db>.<schema>.<tag> SET MASKING POLICY      <db>.<schema>.<policy>;
ALTER TAG <db>.<schema>.<tag> SET TOKENIZATION POLICY <db>.<schema>.<policy>;
ALTER TAG <db>.<schema>.<tag> SET PROJECTION POLICY   <db>.<schema>.<policy>;

-- Table-protecting kinds (optional per-kind attach clause):
ALTER TAG <db>.<schema>.<tag> SET AGGREGATION POLICY <db>.<schema>.<policy> [ENTITY KEY (<col> [, ...])];
ALTER TAG <db>.<schema>.<tag> SET ROW ACCESS POLICY  <db>.<schema>.<policy> [ON (<arg> <type> [, ...])];
ALTER TAG <db>.<schema>.<tag> SET JOIN POLICY        <db>.<schema>.<policy> [ALLOWED JOIN KEYS (<col> [, ...])];
```

Then set the tag on the target (and query to verify):

```sql
-- Table / view / schema / database level (row access, aggregation, join, and inherited masking/tokenization/projection):
ALTER TABLE <db>.<schema>.<table> SET TAG <db>.<schema>.<tag> = '<value>';
-- Column level (masking, tokenization, projection):
ALTER TABLE <db>.<schema>.<table> MODIFY COLUMN <col> SET TAG <db>.<schema>.<tag> = '<value>';
```

Replace a bound policy atomically with `FORCE` (`ALTER TAG <tag> SET <KIND> POLICY <new> FORCE`) to avoid an unprotected gap between `UNSET` and `SET`.

### Two strategies for the policy body

The body can key off the **user's role** (strategy A — like a regular policy) or the **tag's string value** (strategy B — one policy that behaves differently per tag value). Strategy B reads the tag with `SYSTEM$GET_TAG(...)` for table-level kinds or `SYSTEM$GET_TAG_ON_CURRENT_COLUMN(...)` for projection; the tag name must be fully qualified.

```sql
-- Strategy A: role-driven aggregation policy, applied via a tag
CREATE OR REPLACE AGGREGATION POLICY governance.policies.employee_agg
AS () RETURNS AGGREGATION_CONSTRAINT ->
  CASE
    WHEN IS_ROLE_IN_SESSION('DATA_ADMIN') THEN NO_AGGREGATION_CONSTRAINT()
    ELSE AGGREGATION_CONSTRAINT(MIN_GROUP_SIZE => 5)
  END;
ALTER TAG governance.tags.pii_tier SET AGGREGATION POLICY governance.policies.employee_agg;
ALTER SCHEMA analytics.events SET TAG governance.tags.pii_tier = 'CONFIDENTIAL';

-- Strategy B: tag-string-value-driven (same policy, behavior varies by the tag value on the object)
CREATE OR REPLACE AGGREGATION POLICY governance.policies.sensitivity_agg
AS () RETURNS AGGREGATION_CONSTRAINT ->
  CASE
    WHEN SYSTEM$GET_TAG('governance.tags.sensitivity_level',
                        CURRENT_DATABASE() || '.' || CURRENT_SCHEMA() || '.SALARIES',
                        'TABLE') = 'public' THEN NO_AGGREGATION_CONSTRAINT()
    ELSE AGGREGATION_CONSTRAINT(MIN_GROUP_SIZE => 5)
  END;
```

The other new kinds follow the same shape, differing only in the constraint they return:

```sql
-- Row access: filter rows (returns BOOLEAN)
CREATE OR REPLACE ROW ACCESS POLICY governance.policies.tenant_filter
AS (tenant_id NUMBER) RETURNS BOOLEAN ->
  IS_ROLE_IN_SESSION('DATA_ADMIN') OR tenant_id = SYSTEM$GET_TAG(/* ... */);
ALTER TAG governance.tags.tenant_tag SET ROW ACCESS POLICY governance.policies.tenant_filter;

-- Projection: allow/deny projecting a column (returns PROJECTION_CONSTRAINT)
CREATE OR REPLACE PROJECTION POLICY governance.policies.hide_from_partners
AS () RETURNS PROJECTION_CONSTRAINT ->
  CASE WHEN IS_ROLE_IN_SESSION('CLEAN_ROOM_ADMIN') THEN PROJECTION_CONSTRAINT(ALLOW => TRUE)
       ELSE PROJECTION_CONSTRAINT(ALLOW => FALSE) END;
ALTER TAG governance.tags.no_project SET PROJECTION POLICY governance.policies.hide_from_partners;

-- Join: require a join (returns JOIN_CONSTRAINT)
CREATE OR REPLACE JOIN POLICY governance.policies.require_join
AS () RETURNS JOIN_CONSTRAINT ->
  CASE WHEN IS_ROLE_IN_SESSION('CLEAN_ROOM_ADMIN') THEN JOIN_CONSTRAINT(JOIN_REQUIRED => FALSE)
       ELSE JOIN_CONSTRAINT(JOIN_REQUIRED => TRUE) END;
ALTER TAG governance.tags.shared_data SET JOIN POLICY governance.policies.require_join;
```
