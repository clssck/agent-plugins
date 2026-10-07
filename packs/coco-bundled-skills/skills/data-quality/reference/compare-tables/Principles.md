---
parent_skill: data-quality
---

## Core Principles

### Principle 1: Source of Truth Clarity

Always establish which table is the source (baseline) and which is the target (being validated):

- **Source**: The reference/trusted/before version
- **Target**: The new/changed/after version

**Ask if unclear:**
```
Which table should we treat as the baseline (source)?

a) TABLE_A is source (baseline), TABLE_B is target (new version)
b) TABLE_B is source (baseline), TABLE_A is target (new version)
```

This clarity prevents confusion about what "added" vs "removed" means.

### Principle 2: Summary Before Detail

Always provide summary counts before detailed row-level output:

1. **First**: Show high-level metrics (row counts, difference counts)
2. **Then**: Offer to drill down into specifics
3. **Finally**: Show actual rows only when requested

**Example - good approach:**
```
Summary: 1,250 rows added, 45 rows removed, 0 rows modified

Would you like to:
a) See sample of added rows
b) See sample of removed rows  
c) Export full diff to a table
```

This prevents overwhelming users with thousands of rows when they just want an overview.

### Principle 3: Key Column Validation

Before running any comparison, verify the primary key:

1. **Check it exists** in both tables
2. **Check it's unique** (no duplicates)
3. **Ask if ambiguous** - never assume

**Example - key validation:**
```sql
-- Verify key uniqueness before diff
SELECT COUNT(*) AS total, COUNT(DISTINCT key_col) AS unique_keys
FROM table_name;
-- If total != unique_keys, the key is not unique
```

**If key has duplicates:**
```
The column 'order_id' has duplicate values (10,500 rows but only 10,200 unique).

Options:
a) Use compound key (e.g., order_id + line_item_id)
b) Proceed anyway (may cause incorrect diff results)
c) Specify a different key column
```

### Principle 4: Progressive Filtering

For large tables, always suggest filtering to reduce scope:

1. **Time-based**: `WHERE created_at > '2024-01-01'`
2. **Status-based**: `WHERE status = 'active'`
3. **Partition-based**: `WHERE region = 'US'`

**Example - suggesting filters:**
```
Tables have 50M+ rows each. Full comparison may timeout.

Suggested filters:
a) Last 7 days: -w "updated_at > CURRENT_DATE - 7"
b) Last month: -w "updated_at > CURRENT_DATE - 30"
c) Specific partition: -w "region = 'US'"
d) Proceed with full comparison (may take 10+ minutes)
```

### Principle 5: Actionable Results

Don't just report differences - provide context and next steps:

**Bad:**
```
Found 150 added rows.
```

**Good:**
```
Found 150 added rows in target table.

Analysis:
- All 150 rows have created_at > '2024-01-15'
- This matches the expected data load from the new pipeline

Recommendations:
a) Review sample of added rows to verify correctness
b) Accept differences as expected (new data)
c) Investigate if additions were unexpected
```

### Principle 6: Cross-Environment Awareness

When comparing across environments (dev/staging/prod), be explicit:

1. **State environments clearly** in output
2. **Warn about expected differences** (timestamps, auto-generated IDs)
3. **Suggest column exclusions** for known differences

**Example:**
```
Cross-environment comparison: STAGING.orders vs PROD.orders

Note: These columns typically differ between environments:
- created_at (timestamp differs)
- audit_user (environment-specific)
- row_id (auto-generated)

Would you like to exclude these from comparison?
a) Yes, compare only business columns
b) No, compare all columns
```

### Principle 7: Preserve Evidence

When differences matter for audit or compliance:

1. **Offer to materialize results** to a Snowflake table
2. **Include metadata** (comparison timestamp, user, parameters)
3. **Suggest naming conventions** for audit tables

**Example:**
```
Diff complete. Would you like to save results for audit?

a) Save to: AUDIT.DATA_DIFF_ORDERS_20240115 (recommended)
b) Save with custom name
c) Skip (results not persisted)
```

### Principle 8: Fail Fast, Fail Clear

When something goes wrong, report clearly and stop:

**Check before running:**
- Tables exist
- Key columns exist
- User has SELECT access
- Connection is valid

**On error:**
```
Cannot proceed: Key column 'user_id' not found in target table.

Available columns in STAGING.USERS:
- id, name, email, status, created_at

Did you mean one of these?
a) Use 'id' as key column
b) Specify a different column
```

### Principle 9: Respect Scale

Adapt behavior based on table size:

| Table Size | Approach |
|------------|----------|
| < 10K rows | Full comparison, show all differences |
| 10K - 1M rows | Summary first, sample differences |
| > 1M rows | Mandatory filtering, summary only by default |

**Example for large tables:**
```
Source: 5.2M rows | Target: 5.3M rows

Recommended approach for large tables:
a) Summary statistics only (-s flag)
b) Compare last 7 days only
c) Compare specific columns only
d) Full comparison (estimated time: 15+ minutes)
```

### Principle 10: Verify Before Claiming Success

**NEVER report results without verifying execution succeeded.**

1. **Check for errors** in tool output
2. **Verify row counts make sense** (not all zeros)
3. **Confirm connection worked** before reporting

**Wrong behavior (never do this):**
```
[Tool returns error: Connection failed]
✅ Comparison complete! Tables are identical.  <-- WRONG!
```

**Correct behavior:**
```
[Tool returns error: Connection failed]
❌ Comparison failed: Could not connect to Snowflake.

Please verify:
1. Connection name is correct
2. You have network access to Snowflake
3. Credentials are valid
```

### Principle 11: Structured Output

Format all results for clarity:

**Use tables for comparisons:**
```
| Metric | Source | Target | Difference |
|--------|--------|--------|------------|
| Row Count | 10,500 | 10,650 | +150 |
| Unique Keys | 10,500 | 10,650 | +150 |
```

**Use clear status indicators:**
```
Validation Status: ⚠️ REVIEW REQUIRED

✅ Row counts within tolerance (+1.4%)
✅ No removed rows
⚠️ 150 added rows (expected from new pipeline)
❌ 3 rows with modified values (unexpected)
```

### Principle 12: Document Comparison Parameters

Always echo back the comparison parameters used:

```
Comparison Parameters:
- Source: PROD_DB.ANALYTICS.ORDERS
- Target: STAGING_DB.ANALYTICS.ORDERS  
- Key: order_id
- Columns: ALL (%)
- Filter: created_at > '2024-01-01'
- Connection: prod_snowflake
```

This ensures reproducibility and helps with debugging.
