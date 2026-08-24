---
parent_skill: data-quality
---

# Workflow: Custom DMF Patterns

Create custom Data Metric Functions (DMFs) for validation rules that system DMFs don't cover: format validation (email, phone, UUID), value range checks, and cross-column business rules.

**Recommend system DMFs first:** For format, categorical, or simple range checks (e.g. email-like, status IN (...), column > 0), recommend **SNOWFLAKE.CORE.ACCEPTED_VALUES** before suggesting a custom DMF. For referential integrity / FK checks, recommend **SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT** (system DMF) before suggesting a custom DMF. Use custom DMFs only when system DMFs cannot express the rule (complex regex, cross-column, multi-table joins beyond simple FK). See `templates/custom-dmf-create.sql` intro, [ACCEPTED_VALUES](https://docs.snowflake.com/en/sql-reference/functions/dmf_accepted_values), and [REFERENTIAL_INTEGRITY_COUNT](https://docs.snowflake.com/en/sql-reference/functions/dmf_referential_integrity_count). Keep expectation expressions simple (VALUE + Boolean only); complex logic belongs in the DMF or upstream.

**Closes gaps:** G8 (Anomaly Detection Breadth — format and value range), MA-02 (Column-Level Pattern Detection).

## Trigger Phrases
- "Create a custom DMF for email format validation"
- "Custom DMF for value range check"
- "Validate that price is always positive"
- "Check referential integrity with a DMF" (→ prefer system DMF REFERENTIAL_INTEGRITY_COUNT)
- "Create a DMF to check phone number format"
- "Format validation DMF"
- "Cross-column validation DMF"
- "Check that start_date is before end_date"
- "Custom quality rule DMF"

## When to Load
- System DMFs (NULL_COUNT, FRESHNESS, DUPLICATE_COUNT, etc.) don't cover the user's quality rule
- User needs format validation, range checks, or business-rule validation as a continuous DMF

---

## Execution Steps

### Step 1: Prefer System DMFs When Applicable

If the user's rule is format validation, categorical (value in set), or simple numeric range (e.g. column > 0), suggest **ACCEPTED_VALUES** with an expectation first.

If the user's rule is referential integrity / FK validation (e.g. "customer_id must exist in CUSTOMERS"), suggest **SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT** with `TABLE(...)` syntax. This system DMF handles single-column and compound key FK checks natively — no custom DMF needed.

Only proceed to custom DMF when system DMFs cannot express the rule (e.g. complex regex, cross-column comparisons, multi-table joins beyond simple FK, conditional FK logic).

### Step 2: Identify the Pattern Type

Ask the user (or infer from their message) which type of custom DMF is needed:

| Pattern Type | Example | Recommended Template |
|---|---|---|
| **Format validation** | Email, phone, UUID, zip code | Regex pattern match |
| **Value range** | `price > 0`, `age BETWEEN 0 AND 120` | Range predicate |
| **Referential integrity** | `customer_id` exists in `CUSTOMERS` | **Prefer system DMF** `REFERENTIAL_INTEGRITY_COUNT`; custom only for complex joins |
| **Cross-column** | `start_date < end_date` | Multi-column predicate |
| **Statistical outlier** | Values outside 3 standard deviations | STDDEV-based check |
| **Null ratio** | Custom null threshold (e.g., < 5% nulls) | Percentage computation |

If ambiguous, present the list and ask which type the user needs.

---

### Step 3: Gather Parameters

For each pattern type, collect required parameters:

**Format validation:**
- Column name and table to validate
- Pattern type (email / phone / UUID / custom regex)
- Target schema where the DMF will be created

**Value range:**
- Column name, data type, and constraint (e.g., `> 0`, `BETWEEN 18 AND 99`)

**Referential integrity:**
- Child column + child table
- Parent column + parent table (the referenced table)

**Cross-column:**
- First column + second column + comparison operator

**Statistical outlier:**
- Column name (must be numeric)
- Threshold (default: 3 standard deviations)

---

### Step 4: Generate DMF DDL

Read `templates/custom-dmf-create.sql` for the boilerplate structure, then generate the specific DDL:

**Email format validation:**
```sql
CREATE OR REPLACE DATA METRIC FUNCTION <schema>.valid_email_count()
RETURNS NUMBER
AS
$$
  SELECT COUNT_IF(NOT (email RLIKE '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'))
  FROM TABLE(UPSTREAM_TABLES())
$$;
```
*Returns: count of rows with invalid email format (0 = all valid)*

**Phone format validation (US E.164):**
```sql
CREATE OR REPLACE DATA METRIC FUNCTION <schema>.invalid_phone_count()
RETURNS NUMBER
AS
$$
  SELECT COUNT_IF(NOT (phone RLIKE '^\\+?1?[2-9][0-9]{9}$'))
  FROM TABLE(UPSTREAM_TABLES())
$$;
```

**UUID format validation:**
```sql
CREATE OR REPLACE DATA METRIC FUNCTION <schema>.invalid_uuid_count()
RETURNS NUMBER
AS
$$
  SELECT COUNT_IF(NOT (id RLIKE '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'))
  FROM TABLE(UPSTREAM_TABLES())
$$;
```

**Value range (price > 0):**
```sql
CREATE OR REPLACE DATA METRIC FUNCTION <schema>.negative_price_count()
RETURNS NUMBER
AS
$$
  SELECT COUNT_IF(price <= 0)
  FROM TABLE(UPSTREAM_TABLES())
$$;
```

**Referential integrity (FK check):**

> **Prefer system DMF:** For simple FK validation, use `SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT` instead of a custom DMF:
> ```sql
> ALTER TABLE <schema>.<child_table>
>   ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT
>   ON (<child_fk_column>, TABLE(<parent_database>.<parent_schema>.<parent_table>(<parent_pk_column>)));
> ```
> Only use the custom DMF below for complex scenarios (conditional FK logic, multi-table joins, or business rules beyond simple FK):

```sql
CREATE OR REPLACE DATA METRIC FUNCTION <schema>.orphan_order_count()
RETURNS NUMBER
AS
$$
  SELECT COUNT(*)
  FROM TABLE(UPSTREAM_TABLES()) o
  LEFT JOIN <parent_database>.<parent_schema>.<parent_table> p
    ON o.<child_fk_column> = p.<parent_pk_column>
  WHERE p.<parent_pk_column> IS NULL
    AND o.<child_fk_column> IS NOT NULL
$$;
```

**Cross-column validation (start before end):**
```sql
CREATE OR REPLACE DATA METRIC FUNCTION <schema>.invalid_date_range_count()
RETURNS NUMBER
AS
$$
  SELECT COUNT_IF(start_date >= end_date)
  FROM TABLE(UPSTREAM_TABLES())
$$;
```

**Statistical outlier (values > 3 STDDEV from mean):**
```sql
CREATE OR REPLACE DATA METRIC FUNCTION <schema>.outlier_count()
RETURNS NUMBER
AS
$$
  SELECT COUNT_IF(ABS(<column> - stats.mean_val) > 3 * stats.stddev_val)
  FROM TABLE(UPSTREAM_TABLES()),
  (SELECT AVG(<column>) AS mean_val, STDDEV(<column>) AS stddev_val
   FROM TABLE(UPSTREAM_TABLES())) stats
$$;
```

---

### Step 5: Present DDL for Approval

**⚠️ MANDATORY STOPPING POINT**: Present the generated DDL and ask:


> "Here is the custom DMF I'll create:
>
> ```sql
> <generated DDL>
> ```
>
> After creation, I'll attach it to `<table>` with:
>
> ```sql
> ALTER TABLE <database>.<schema>.<table>
>   ADD DATA METRIC FUNCTION <schema>.<dmf_name> ON (<column>);
> ```
>
> Shall I proceed? (Yes / No / Modify)"

**NEVER execute without explicit approval** (unless pre-approval was given in the request).

---

### Step 6: Execute (On Approval)

Execute in order:
1. `CREATE DATA METRIC FUNCTION` DDL
2. `ALTER TABLE ... ADD DATA METRIC FUNCTION` to attach it

After execution:

```
Custom DMF Created: <schema>.<dmf_name>
Attached to: <database>.<schema>.<table> on column (<column>)

The first measurement will appear within 1–2 minutes (TRIGGER_ON_CHANGES)
or on the next scheduled run.

To view results:
SELECT * FROM TABLE(SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS(
  REF_ENTITY_NAME => '<database>.<schema>.<table>',
  REF_ENTITY_DOMAIN => 'TABLE'
))
ORDER BY MEASUREMENT_TIME DESC
LIMIT 10;
```

---

### Step 7: Set Expectation Threshold (Optional)

After creating the DMF, offer:

> "Would you like to set an **expectation threshold** so this check has a defined pass/fail criterion?
> (e.g., 'invalid_email_count must equal 0 to pass')"

If yes → Load `workflows/expectations-management.md`.

---

## Output Format
- Custom DMF DDL (generated per pattern type)
- Attachment `ALTER TABLE` DDL
- Post-execution confirmation with result query
- Optional: link to expectations-management workflow

## Stopping Points
- ✋ **Step 2**: Parameters not provided — ask before generating DDL
- ✋ **Step 4**: Before creating the DMF — show DDL and await explicit approval

## Error Handling
| Issue | Resolution |
|-------|-----------|
| `UPSTREAM_TABLES()` not supported | Snowflake DMFs use `TABLE(UPSTREAM_TABLES())` — ensure Snowflake version supports custom DMFs (generally available) |
| Referential integrity DMF fails at runtime | The parent table must be accessible from the DMF's owner role |
| Regex syntax error | Test regex in isolation first: `SELECT 'test@example.com' RLIKE '<pattern>'` |
| Schema for DMF creation not specified | Ask user where to CREATE the DMF; recommend keeping custom DMFs in a dedicated `<schema>_QUALITY` schema |
| DMF name conflict | Append `_v2` or use `CREATE OR REPLACE` (already included in templates) |

## Notes
- Custom DMFs must be created in a schema the user has `CREATE DATA METRIC FUNCTION` privilege on
- The DMF owner role must have SELECT access to all tables referenced in the body (including parent tables for FK checks)
- All custom DMF templates return a count of **violations** (0 = all valid), consistent with system DMF conventions
- For monitoring coverage reports including custom DMFs, see `workflows/coverage-gaps.md`
