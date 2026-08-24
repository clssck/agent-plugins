---
name: missing_relationships_detection
description: "Detect when relationship count is suspiciously low and check primary key prerequisites"
parent_skill: best_practices_audit
---

# Missing Relationships Detection

## When to Load

Best Practices Audit Phase 2d.

## When to Flag

**Only flag when relationships are suspiciously low:**

| Tables | Expected Min Relationships | Flag If          |
| ------ | -------------------------- | ---------------- |
| 2-3    | 1                          | 0 relationships  |
| 4-6    | 2                          | ≤1 relationship  |
| 7+     | 3                          | ≤2 relationships |

**AND** at least one of:
- Multiple tables share FK-like columns (e.g., `ACCOUNT_ID` in 3+ tables)
- Dimension table exists (table with `*_ID` as likely PK) but no relationships point to it

## Detection Steps

1. **Count existing relationships** vs table count
2. **If below threshold**: Identify potential relationship candidates
3. **For each candidate**: Check if at least one table has a primary key on join columns
4. **Report findings with PK status**

## Validating Primary Keys

To verify if a column is a valid primary key, use `snowflake_sql_execute`:

```sql
SELECT COUNT(*) AS total_rows,
       COUNT(DISTINCT {column}) AS distinct_values
FROM {database}.{schema}.{table};
```

If `total_rows = distinct_values`, the column is unique and can serve as a primary key.

## Output Format

```
### 🔗 MISSING RELATIONSHIPS ({count})

Relationship count ({current}) is low for {table_count} tables.

| Table A | Table B | Join Columns | PK Status |
|---------|---------|--------------|-----------|
| ORDERS | CUSTOMERS | CUSTOMER_ID → CUSTOMER_ID | ✅ CUSTOMERS has PK |
| LOGS | ACCOUNTS | ACCOUNT_ID → ... | ❌ Neither has PK |

### ⚠️ PRIMARY KEY ISSUES ({count})

At least one table must have a PK on the join columns:

| Table | Suggested PK Columns | Action |
|-------|---------------------|--------|
| ACCOUNTS | ACCOUNT_ID | Verify uniqueness with SQL above |

**Options for missing primary keys:**
1. Verify uniqueness with `snowflake_sql_execute` (SQL above)
2. User provides known primary key columns
```

## Next Steps

To fix: Route to **edit workflow** — **Load** `../../edit/SKILL.md`

Primary keys must be verified/added BEFORE relationships can be created.
