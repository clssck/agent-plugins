---
parent_skill: data-quality
---

# Workflow 2: Row-Level Diff

## Trigger Phrases
- "Show me the actual differences"
- "What rows were added?"
- "What rows were removed?"
- "Drill down into differences"
- "Show me the changed rows"

## When to Load
Data-diff Step 2: User wants to see actual row-level details.

## Tool to Use
**Primary:** `data_diff` tool
- Efficient row-level comparison
- Shows actual row values with + and -

**Fallback SQL templates:**
- `added-rows.sql` - Rows in target but not source
- `removed-rows.sql` - Rows in source but not target
- `modified-rows.sql` - Rows with changed values

## Execution Steps

### Step 1: Extract Parameters
- Source table: DATABASE.SCHEMA.TABLE
- Target table: DATABASE.SCHEMA.TABLE  
- Primary key column(s)
- Filter condition (optional)

If not provided, ask:
```
Please provide:
1. Source table (baseline): ?
2. Target table (new version): ?
3. Primary key column: ?
4. Filter (optional, e.g., "created_at > '2024-01-01'"): ?
```

### Step 2: Check Table Sizes
- Query row counts for both tables
- If > 1M rows, suggest filtering:
```
Tables have X million rows. Consider adding a filter:
a) Last 7 days: -w "updated_at > CURRENT_DATE - 7"
b) Last month: -w "updated_at > CURRENT_DATE - 30"  
c) Proceed with full comparison
```

### Step 3: Execute data_diff Tool

**For same-database comparison:**
```
"snowflake://<connection>/DATABASE/SCHEMA" source_table target_table -k key_column -c %
```

**For cross-database comparison:**
```
"snowflake://<connection>/SOURCE_DB/SCHEMA" source_table "snowflake://<connection>/TARGET_DB/SCHEMA" target_table -k key_column -c %
```

**With filter:**
```
"snowflake://<connection>/DATABASE/SCHEMA" source_table target_table -k key_column -c % -w "filter_condition"
```

### Step 4: Present Results

**If no differences:**
```
Row-Level Diff: SOURCE_TABLE vs TARGET_TABLE

Result: ✅ No row-level differences found.
Tables are identical at the row level.
```

**If differences found:**
```
Row-Level Diff: SOURCE_TABLE vs TARGET_TABLE

Added Rows (in target, not source):
+ | key_val | col1_val | col2_val |
+ | key_val | col1_val | col2_val |

Removed Rows (in source, not target):
- | key_val | col1_val | col2_val |
- | key_val | col1_val | col2_val |

Summary:
- Rows added: N
- Rows removed: N
```

### Step 5: Next Steps
- "Would you like to export these differences to a table for audit?"
- "Would you like to analyze distribution changes?"
- "Would you like to filter to specific columns?"

## Output Format
- Actual row values with +/- indicators
- Summary counts
- Suggestion for next steps

## Error Handling
- If connection fails: Verify connection name
- If key column not found: Ask for correct column
- If timeout: Suggest smaller filter or `-s` for summary only

## Notes
- Uses data_diff tool for efficient comparison
- Shows actual data values (be mindful of sensitive data)
- Can be slow for very large tables without filters

## Halting States
- **Success**: Differences shown — suggest export or further analysis
- **No differences**: Report tables identical
- **Error**: Report error and suggest alternatives
