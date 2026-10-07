---
parent_skill: data-quality
---

# Workflow 4: Distribution Analysis

## Trigger Phrases
- "Compare value distributions"
- "Did the data distribution change?"
- "Statistical comparison"
- "Check for distribution shift"
- "Compare percentiles"

## When to Load
Data-diff Step 2: User wants statistical/distribution comparison rather than row-level.

## Templates to Use
**For categorical columns:** `distribution-categorical.sql`
- Compares value frequencies and percentages

**For numeric columns:** `distribution-numeric.sql`
- Compares percentiles, mean, stddev, min/max

## Execution Steps

### Step 1: Extract Parameters
- Source table: DATABASE.SCHEMA.TABLE
- Target table: DATABASE.SCHEMA.TABLE
- Column(s) to analyze (or ask which columns)

### Step 2: Identify Column Types
Query INFORMATION_SCHEMA to determine:
- Which columns are categorical (VARCHAR, BOOLEAN, etc.)
- Which columns are numeric (NUMBER, FLOAT, etc.)

### Step 3: Execute Distribution Analysis

**For categorical column:**
- Read: `templates/compare-tables/distribution-categorical.sql`
- Replace: `<source_table>`, `<target_table>`, `<column_name>`
- Execute via `snowflake_sql_execute`

**For numeric column:**
- Read: `templates/compare-tables/distribution-numeric.sql`
- Replace: `<source_table>`, `<target_table>`, `<numeric_column>`
- Execute via `snowflake_sql_execute`

### Step 4: Present Results

**Categorical Distribution:**
```
Distribution Comparison: COLUMN_NAME

| Value | Source Count | Target Count | Source % | Target % | Shift |
|-------|--------------|--------------|----------|----------|-------|
| A | 1000 | 1200 | 40% | 42% | +2% |
| B | 750 | 800 | 30% | 28% | -2% |
| C | 500 | 600 | 20% | 21% | +1% |
| NULL | 250 | 250 | 10% | 9% | -1% |

Largest shifts:
- Value 'A': +2% (1000 → 1200 rows)
- Value 'B': -2% (750 → 800 rows, but lower percentage)
```

**Numeric Distribution:**
```
Distribution Comparison: NUMERIC_COLUMN

| Metric | Source | Target | Change |
|--------|--------|--------|--------|
| Min | 0 | 0 | 0 |
| P25 | 10 | 12 | +2 |
| Median | 50 | 55 | +5 |
| P75 | 100 | 110 | +10 |
| Max | 500 | 600 | +100 |
| Mean | 65.2 | 72.3 | +7.1 |
| StdDev | 45.1 | 48.2 | +3.1 |
| Null Count | 50 | 45 | -5 |

Analysis:
- Distribution shifted upward (median +5, mean +7.1)
- Variance increased slightly (stddev +3.1)
- Max value increased significantly (+100)
```

### Step 5: Interpret Results
Provide interpretation based on findings:

**Stable distribution:**
```
✅ Distribution appears stable.
- No significant shifts in categorical values
- Numeric percentiles within expected range
```

**Distribution shift detected:**
```
⚠️ Distribution shift detected:
- Median increased by 10% (50 → 55)
- New high outliers (max 500 → 600)
- Consider investigating data source changes
```

### Step 6: Next Steps
- "Would you like to analyze another column?"
- "Would you like to see row-level differences for outliers?"
- "Would you like to compare aggregate metrics?"

## Output Format
- Distribution comparison tables
- Shift analysis
- Interpretation and recommendations

## Error Handling
- If column not found: List available columns
- If wrong type: Suggest appropriate analysis type
- If too many distinct values: Suggest top N or bucketing

## Notes
- Useful for detecting data drift
- Complements row-level diff with statistical view
- Can identify issues not visible in row counts

## Halting States
- **Stable distribution**: Report and suggest row-level diff if needed
- **Shift detected**: Highlight concerns and suggest investigation
- **Error**: Report error and stop
