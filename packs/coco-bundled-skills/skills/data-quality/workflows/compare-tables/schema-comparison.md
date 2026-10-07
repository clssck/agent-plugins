---
parent_skill: data-quality
---

# Workflow 3: Schema Comparison

## Trigger Phrases
- "Compare table schemas"
- "Did columns change?"
- "What schema differences are there?"
- "Check if structure is the same"

## When to Load
Data-diff Step 2: User wants to compare table structures before or instead of data.

## Template to Use
**Primary:** `schema-comparison.sql`
- Compares column names, types, nullability
- Shows added, removed, and changed columns

## Execution Steps

### Step 1: Extract Parameters
- Source table: DATABASE.SCHEMA.TABLE
- Target table: DATABASE.SCHEMA.TABLE

Parse into components:
- `<source_database>`, `<source_schema>`, `<source_table>`
- `<target_database>`, `<target_schema>`, `<target_table>`

### Step 2: Execute Schema Comparison
- Read: `templates/compare-tables/schema-comparison.sql`
- Replace all placeholders
- Execute via `snowflake_sql_execute`

### Step 3: Present Results

**If schemas identical:**
```
Schema Comparison: SOURCE_TABLE vs TARGET_TABLE

Result: ✅ Schemas are identical.

| Column Count | Source | Target |
|--------------|--------|--------|
| Total Columns | N | N |
```

**If schemas differ:**
```
Schema Comparison: SOURCE_TABLE vs TARGET_TABLE

| Column | Status | Source Type | Target Type |
|--------|--------|-------------|-------------|
| new_col | ADDED | - | VARCHAR |
| old_col | REMOVED | NUMBER | - |
| changed_col | TYPE_CHANGED | VARCHAR(50) | VARCHAR(100) |
| same_col | UNCHANGED | NUMBER | NUMBER |

Summary:
- Columns Added: N
- Columns Removed: N
- Columns Changed: N
- Columns Unchanged: N
```

### Step 4: Implications
If schema differences found, explain implications:

**Added columns:**
```
New columns in target: col1, col2
- Data diff will ignore these columns (they don't exist in source)
- Use -c to specify columns if needed
```

**Removed columns:**
```
Columns removed from target: col1, col2
- Data diff will fail if comparing these columns
- Use -c to specify only common columns
```

**Type changes:**
```
Column type changed: col1 (VARCHAR -> NUMBER)
- Hash comparison may show false differences
- Consider comparing specific columns
```

### Step 5: Next Steps
- If identical: "Proceed with data comparison?"
- If differences: "Would you like to proceed with data diff using common columns only?"

## Output Format
- Schema change summary table
- Counts by change type
- Implications for data comparison
- Suggested next steps

## Error Handling
- If table not found: Verify table name and permissions
- If INFORMATION_SCHEMA access denied: Check role privileges

## Notes
- This is a READ-ONLY workflow
- Helps understand structure before data comparison
- May identify why data diff fails

## Halting States
- **Schemas identical**: Suggest proceeding to data diff
- **Schemas differ**: Present changes and ask how to proceed
- **Error**: Report error and stop
