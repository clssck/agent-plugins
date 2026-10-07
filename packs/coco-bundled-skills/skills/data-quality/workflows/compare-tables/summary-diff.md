---
parent_skill: data-quality
---

# Workflow 1: Summary Diff

## Trigger Phrases
- "Compare these tables"
- "How many differences?"
- "Quick diff check"
- "Are these tables the same?"

## When to Load
Data-diff Step 2: Quick summary or initial comparison request.

## Templates to Use
**Primary:** `summary-diff.sql`
- Provides counts of added, removed, modified, unchanged rows
- Fast execution, minimal output

**Fallback:** `row-count-comparison.sql`
- Simple row count comparison if summary fails

## Execution Steps

### Step 1: Extract Parameters
- Source table (baseline): DATABASE.SCHEMA.TABLE
- Target table (new version): DATABASE.SCHEMA.TABLE  
- Primary key column(s)

If not provided, ask:
```
Please provide:
1. Source table (baseline): ?
2. Target table (new version): ?
3. Primary key column: ?
```

### Step 2: Execute Quick Check
- Read: `templates/compare-tables/exact-match.sql`
- Replace: `<source_table>`, `<target_table>`
- Execute via `snowflake_sql_execute`

If IDENTICAL: Report "Tables are identical" and stop.
If DIFFERENT: Continue to summary.

### Step 3: Execute Summary
- Read: `templates/compare-tables/summary-diff.sql`
- Replace: `<source_table>`, `<target_table>`, `<key_column>`
- Execute via `snowflake_sql_execute`

### Step 4: Present Results
```
Summary Diff: SOURCE_TABLE vs TARGET_TABLE

| Change Type | Count |
|-------------|-------|
| Rows Added | N |
| Rows Removed | N |
| Rows Modified | N |
| Rows Unchanged | N |

Status: [IDENTICAL / ADDITIONS_ONLY / REMOVALS_ONLY / MODIFIED / CHANGED]
```

### Step 5: Next Steps
- If IDENTICAL: "Tables are identical. No further action needed."
- If differences found: "Would you like to drill down into specific differences?"
- Do NOT auto-run detailed diff (that's a separate workflow)

## Output Format
- Summary counts table
- Status indicator
- Suggestion for next steps

## Error Handling
- If tables don't exist: Report and stop
- If key column not found: Ask for correct column
- If query times out: Suggest using filter with `-w` option

## Notes
- This is a READ-ONLY workflow (no approval required)
- Does not show actual row values (use row-level-diff for that)
- Fast execution (< 10 seconds for most tables)

## Halting States
- **Success**: Summary presented — suggest drill-down if differences found
- **Tables identical**: Report and complete
- **Error**: Report error and stop
