# Best Practices

Use this file when the user asks about policy design guidelines, anti-patterns, or practical constraints.

## Quick Reference

| # | Best Practice | Priority | When to Apply |
|---|--------------|----------|---------------|
| 1 | Check similar tables first | **CRITICAL** | Before creating any new policy |
| 2 | Use `IS_ROLE_IN_SESSION()` for role checks | **HIGH** in accounts with role hierarchy or secondary roles; LOW otherwise | Role-based authorization |
| 3 | Use generic, reusable policies | HIGH | Always when creating new policies |
| 4 | Centralize in a governance database | HIGH at scale; YAGNI for a handful of policies | Account-wide policy management |
| 5 | Use memoizable functions for lookups | HIGH when the same lookup is shared across policies or the mapping is non-trivial | Policy uses a mapping/lookup table |
| 6 | Explicit `ELSE` in CASE bodies | LOW (readability/audit, not correctness) | Any CASE-based policy body |
| 7 | `COMMENT` every policy | LOW (operability) | Always when creating policies |

---

## 1. Check Similar Tables First

**Problem:** Creating a new policy without checking existing ones leads to inconsistent protection and policy sprawl.

**Solution:** Before protecting any column, check what policies already protect similar columns or tables with the same tags.

**Why this matters:**
- Ensures **consistency** — similar data gets similar protection
- Promotes **reuse** — one policy protects many columns
- Avoids **sprawl** — prevents dozens of near-identical policies
- Reveals **gaps** — find unprotected tables that should have policies

> For discovery SQL queries, see the **conversational create workflow**, Step 2.

**Decision flow:**
1. Found policy on similar table? → **Reuse it**
2. Found multiple different policies? → **Consolidate to one**
3. Found unprotected similar tables? → **Protect them too**
4. No similar tables exist? → **Create new generic policy**

---

## 2. Use Generic, Reusable Policies

**Problem:** Creating separate masking policies for every table or column leads to policy sprawl and maintenance burden.

**Solution:** Define generic policies that can be reused across datasets.

**Good:**
```sql
-- One policy for all PII string columns
CREATE MASKING POLICY pii_string_mask AS (val STRING) RETURNS STRING ->
  CASE
    WHEN IS_ROLE_IN_SESSION('PII_VIEWER') THEN val
    ELSE '***MASKED***'
  END;
```

**Anti-pattern:**
```sql
-- DON'T: Create table-specific policies
CREATE MASKING POLICY customers_email_mask ...
CREATE MASKING POLICY orders_email_mask ...
CREATE MASKING POLICY users_email_mask ...
```

---

## 3. Centralize in a Governance Database

**Problem:** Policies, tags, and mapping tables scattered across schemas make governance difficult to manage and audit.

**Solution:** Create a dedicated governance database to centralize all policy-related objects.

**Recommended structure:**
```
GOVERNANCE_DB
├── POLICIES (schema)
│   └── masking policies, row access policies, projection policies
├── TAGS (schema)
│   └── tag definitions
└── ACCESS_CONTROL (schema)
    ├── role_mapping tables
    └── entitlement tables
```

**Setup:**
```sql
CREATE DATABASE GOVERNANCE_DB;
CREATE SCHEMA GOVERNANCE_DB.POLICIES;
CREATE SCHEMA GOVERNANCE_DB.TAGS;
CREATE SCHEMA GOVERNANCE_DB.ACCESS_CONTROL;

-- Restrict access to governance role
GRANT USAGE ON DATABASE GOVERNANCE_DB TO ROLE GOVERNOR;
GRANT ALL ON SCHEMA GOVERNANCE_DB.POLICIES TO ROLE GOVERNOR;
```

---

## 4. Use Memoizable Functions for Lookups

**Problem:** Inline subqueries make policy logic harder to reuse and audit across policies. For large mapping tables, view-backed lookups, or lookups called with varying arguments, they can also become a per-evaluation cost rather than a one-time cost.

**Solution:** Wrap the authorization lookup in a memoizable scalar SQL UDF. The cache keys on the (constant) arguments and persists across SQL statements in a session while the data is unchanged, which gives you a single source of truth for "who is authorized" and removes repeated work when the same arguments (e.g. `CURRENT_ROLE()`) recur.

> **Note on performance:** For a simple `IN (SELECT … FROM small_table)` against a stable mapping table, Snowflake's optimizer typically materializes the subquery once per statement, so raw row-level overhead is small. The primary wins from this pattern are **reuse, auditability, and consistency across policies**, with performance as a secondary benefit for large or view-backed lookups.

**Good:**
```sql
CREATE OR REPLACE FUNCTION is_authorized_role()
RETURNS BOOLEAN
MEMOIZABLE
AS
$$
  EXISTS (
    SELECT 1 FROM governance_db.access_control.authorized_roles 
    WHERE role_name = CURRENT_ROLE()
  )
$$;

CREATE MASKING POLICY secure_mask AS (val STRING) RETURNS STRING ->
  CASE
    WHEN is_authorized_role() THEN val
    ELSE '***MASKED***'
  END;
```

**Less preferred (inline lookup):**
```sql
-- Functionally correct, but duplicates the authorization logic in the policy body
-- and cannot be shared across policies.
CREATE MASKING POLICY inline_mask AS (val STRING) RETURNS STRING ->
  CASE
    WHEN CURRENT_ROLE() IN (SELECT role_name FROM mapping_table) THEN val
    ELSE '***MASKED***'
  END;
```

**When you cannot use a memoizable function:**
- The policy needs to pass per-row column values into the lookup (memoizable requires constant arguments).
- The function would have to call non-deterministic or non-SQL functions (not allowed inside memoizable).
- Return type would be OBJECT or VARIANT (not cached).
- You need the authorization change to be visible immediately even while a session is in flight (memoization can keep the previous result until context changes).

---

## 5. Prefer IS_ROLE_IN_SESSION() for Role Checks

**Problem:** `CURRENT_ROLE()` returns only the primary active role. It does not consider role hierarchy or secondary roles. In any account that uses role hierarchies or secondary roles (`USE SECONDARY ROLES ALL`), a user who inherits the authorized role will be wrongly masked.

**Solution:** Use `IS_ROLE_IN_SESSION('<role>')` for authorization checks — it returns TRUE when the role is in the active primary or secondary role hierarchy.

**Recommended:**
```sql
-- Hierarchy-aware: works if the user has the role directly or inherits it
WHEN IS_ROLE_IN_SESSION('ANALYST') THEN val
```

**Acceptable only with flat role models:**
```sql
-- OK if the account has no role hierarchy and no secondary roles,
-- and you are sure the primary role will always be the exact role name.
WHEN CURRENT_ROLE() = 'ANALYST' THEN val
```

> Snowflake documentation explicitly recommends `IS_ROLE_IN_SESSION` when role hierarchy matters in policy conditions.

---

## Common Anti-Patterns Summary

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| Table-specific policies when the rule is reusable | Sprawl, inconsistent protection | Use one generic policy per data type; attach via tags when many tables share the rule |
| Unmask logic duplicated in multiple policy bodies | Drift between policies, harder to audit | **Apply split pattern** — extract the shared check to a memoizable function |
| Long hardcoded role lists repeated across policies | Adding or revoking access requires editing multiple policies | **Externalize** the list to a function or mapping table so it lives in one place |
| Inline `IN (SELECT …)` against a mapping table used in many policies | Duplicated logic; on large or view-backed lookups, also recomputed work | Wrap the lookup in a memoizable function |
| `CURRENT_ROLE()` comparisons in accounts with role hierarchy or secondary roles | Inherited roles are wrongly denied access | Use `IS_ROLE_IN_SESSION()` |
| Policies scattered across many team schemas in large orgs | Hard to audit, version, and govern | Centralize in a governance database once you outgrow a handful of policies |
| Implicit `ELSE` in CASE | Not a correctness issue (Snowflake returns NULL deterministically) but hurts readability and review | Add an explicit `ELSE <masked_value>` or `ELSE NULL` so the fail-closed path is visible |
| No `COMMENT` | Hard to understand ownership / purpose / classification during audit | Add `COMMENT` with purpose, owner, and protected classification |

> 💡 **Split pattern:** Extract unmask logic from policy bodies into a shared memoizable function. All policies call this function instead of having their own logic. See the **proven patterns reference** → Pattern 2.

---

## 6. Make the Fail-Closed Path Explicit

**Problem:** A CASE expression with no `ELSE` returns `NULL` when no `WHEN` matches (Snowflake follows ANSI SQL here — this is deterministic, not a security bug). The issue is **readability and review**: an auditor reading the policy cannot tell at a glance what unauthorized users see.

**Solution:** Always write an explicit `ELSE` clause so the masked-path value is visible in the policy body. Use `ELSE NULL` when you want unauthorized users to see nothing, or an explicit masked value when the business wants a recognizable placeholder.

**Good:**
```sql
CREATE MASKING POLICY mask_ssn AS (val STRING) RETURNS STRING ->
  CASE
    WHEN IS_ROLE_IN_SESSION('HR_ADMIN') THEN val
    WHEN IS_ROLE_IN_SESSION('FINANCE_ADMIN') THEN val
    ELSE NULL  -- Secure default: unauthorized roles see nothing
  END
COMMENT = 'Masks SSN for non-privileged roles. Owner: Security Team';
```

**Harder to review:**
```sql
-- Functionally returns NULL for unauthorized roles, but the reader has to
-- reason about implicit CASE behavior instead of seeing the fail-closed path.
CREATE MASKING POLICY mask_ssn AS (val STRING) RETURNS STRING ->
  CASE
    WHEN CURRENT_ROLE() = 'HR_ADMIN' THEN val
    WHEN CURRENT_ROLE() = 'FINANCE_ADMIN' THEN val
  END;
```

---

## 7. Document Every Policy with COMMENT

**Problem:** Policies without documentation become orphaned—no one knows who owns them, what they protect, or whether they can be modified.

**Solution:** Add a COMMENT to every policy specifying owner, purpose, and protected data.

**Good:**
```sql
CREATE MASKING POLICY mask_email AS (val STRING) RETURNS STRING ->
  CASE
    WHEN IS_ROLE_IN_SESSION('MARKETING_ADMIN') THEN val
    ELSE '***@***'
  END
COMMENT = 'Masks email addresses. Owner: Data Governance Team. Protected: PII-EMAIL';
```

**Recommended COMMENT format:**
```
'<Purpose>. Owner: <Team/Person>. Protected: <Data Classification>'
```

**Anti-pattern:**
```sql
-- DON'T: No comment
CREATE MASKING POLICY mask_email AS (val STRING) RETURNS STRING -> ...;
```

---

## Before/After Transformations

### Transform 1: Scattered → Centralized

**Before (scattered):**
```
SALES_DB.DATA.email_mask
SALES_DB.POLICIES.phone_mask
HR_DB.EMPLOYEE_DATA.ssn_mask
FINANCE_DB.TRANSACTIONS.card_mask
```

**After (centralized):**
```
GOVERNANCE_DB.POLICIES.pii_string_mask    -- Reusable for email, phone
GOVERNANCE_DB.POLICIES.ssn_mask           -- Specific for SSN format
GOVERNANCE_DB.POLICIES.card_mask          -- Specific for card numbers
```

### Transform 2: Hardcoded → Dynamic

**Before (hardcoded roles):**
```sql
CREATE MASKING POLICY old_mask AS (val STRING) RETURNS STRING ->
  CASE
    WHEN CURRENT_ROLE() IN ('ADMIN', 'MANAGER', 'ANALYST', 'SUPPORT',
                            'VIEWER_US', 'VIEWER_EU', 'VIEWER_APAC') THEN val
    ELSE '***MASKED***'
  END;
```

**After (dynamic with mapping table):**
```sql
-- Step 1: Create mapping table
CREATE TABLE GOVERNANCE_DB.ACCESS_CONTROL.authorized_roles (
    role_name STRING,
    can_view_pii BOOLEAN
);

-- Step 2: Create memoizable function
CREATE FUNCTION can_view_pii()
RETURNS BOOLEAN
MEMOIZABLE
AS $$ 
  EXISTS (SELECT 1 FROM GOVERNANCE_DB.ACCESS_CONTROL.authorized_roles 
          WHERE role_name = CURRENT_ROLE() AND can_view_pii = TRUE)
$$;

-- Step 3: Create simple policy
CREATE MASKING POLICY new_mask AS (val STRING) RETURNS STRING ->
  CASE WHEN can_view_pii() THEN val ELSE '***MASKED***' END
  COMMENT = 'Generic PII mask. Access controlled via authorized_roles table.';
```

### Transform 3: Slow → Fast

**Before (slow - subquery per row):**
```sql
CREATE MASKING POLICY slow_mask AS (val STRING) RETURNS STRING ->
  CASE
    WHEN EXISTS (
      SELECT 1 FROM auth_table 
      WHERE role = CURRENT_ROLE() AND access_level = 'FULL'
    ) THEN val
    ELSE '***MASKED***'
  END;
```

**After (reusable, cached):**
```sql
-- Memoizable function: the result is cached keyed on the (constant) arguments.
-- The same CURRENT_ROLE() lookup is evaluated once and reused across statements
-- in the session while the auth_table and context are unchanged.
CREATE FUNCTION has_full_access()
RETURNS BOOLEAN
MEMOIZABLE
AS $$
  EXISTS (SELECT 1 FROM auth_table 
          WHERE role = CURRENT_ROLE() AND access_level = 'FULL')
$$;

CREATE MASKING POLICY fast_mask AS (val STRING) RETURNS STRING ->
  CASE WHEN has_full_access() THEN val ELSE '***MASKED***' END;
```
