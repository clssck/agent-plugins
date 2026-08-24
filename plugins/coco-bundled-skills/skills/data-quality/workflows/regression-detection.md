---
parent_skill: data-quality
---

# Workflow 3: Regression Detection

## Trigger Phrases
- "What changed since yesterday?"
- "Quality regression"
- "What broke recently?"
- "Show me new failures"
- "Did quality get worse?"

## When to Load
Data-quality Step 2: regression/change intent.

## Template to Use
**Primary:** `schema-regression-detection.sql`
- Compares two time periods (current vs previous)
- Shows delta: new failures, resolved issues, health change

## Execution Steps

### Step 1: Extract Database and Schema
- From user query: "DEMO_DQ_DB.SALES" → database='DEMO_DQ_DB', schema='SALES'
- If not already provided, ask which DATABASE.SCHEMA to compare

### Step 2: Read and Execute Template
- Read: `templates/schema-regression-detection.sql`
- Replace: `<database>` → actual database name
- Replace: `<schema>` → actual schema name
- Execute via `snowflake_sql_execute`

### Step 3: Present Results
```
Regression Detection: DATABASE.SCHEMA

Health Change: 95% -> 83% (-12%)

New Failures (2):
1. CUSTOMERS.email - NULL_COUNT now failing
2. ORDERS.order_date - DATE_RANGE now failing

Resolved Issues (1):
1. PRODUCTS.price - POSITIVE_VALUE now passing

Summary:
- 2 new issues detected
- 1 issue resolved
- Net change: -1 metric health
```

### Step 4: Next Steps
- If regressions found: "Investigate new failures with root cause analysis."
- If improvements: "Quality is improving. Keep monitoring."
- If no change: "Quality stable since last check."

## Output Format
- Health score delta (previous → current)
- List of NEW failures (what broke)
- List of RESOLVED issues (what got fixed)
- Net quality change summary

## What to Compare
- Default: Current vs 24 hours ago
- User can specify: "since last week", "since Monday", etc.
- Use most recent measurement from SNOWFLAKE.LOCAL for comparison

## Error Handling
- If insufficient historical data → "Not enough history. Need at least 2 measurements."
- If no changes detected → "Quality stable. No regressions or improvements."
- If template fails → Run `preflight-check.sql` to diagnose

## Notes
- This is a READ-ONLY workflow (no approval required)
- Uses SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS() table function
- Needs at least 2 measurements to compare
- Focuses on changes, not absolute state
- Use after deployments to catch regressions

## Halting States
- **Success**: Regression report presented with delta
- **Insufficient data**: "Need at least 2 measurements for comparison."
- **No changes**: "Quality stable. No regressions or improvements."
