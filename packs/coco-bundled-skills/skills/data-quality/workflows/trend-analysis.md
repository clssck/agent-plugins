---
parent_skill: data-quality
---

# Workflow 4: Trend Analysis

## Trigger Phrases
- "Show quality trends"
- "Is quality improving?"
- "Quality over time"
- "Historical quality trends"
- "Track quality changes"

## When to Load
Data-quality Step 2: trend/history intent.

## Template to Use
**Primary:** `schema-quality-trends.sql`
- Shows time-series data of health scores
- Identifies persistent issues vs transient failures
- Tracks improvement or degradation over time

## Execution Steps

### Step 1: Extract Database and Schema
- From user query: "DEMO_DQ_DB.SALES" → database='DEMO_DQ_DB', schema='SALES'
- If not already provided, ask which DATABASE.SCHEMA to analyze

### Step 2: Read and Execute Template
- Read: `templates/schema-quality-trends.sql`
- Replace: `<database>` → actual database name
- Replace: `<schema>` → actual schema name
- Execute via `snowflake_sql_execute`

### Step 3: Present Results
```
Quality Trends: DATABASE.SCHEMA (Last 30 Days)

Health Trend:
Week 1: 95%
Week 2: 92% (-3%)
Week 3: 88% (-4%)
Week 4: 90% (+2%)

Persistent Issues (failing > 7 days):
1. CUSTOMERS.email - NULL_COUNT (failing 14 days)
2. ORDERS.order_date - DATE_RANGE (failing 21 days)

Transient Issues (resolved < 3 days):
1. PRODUCTS.price - POSITIVE_VALUE (failed 1 day, now resolved)

Overall Trend: Degrading (-5% over 30 days)
```

### Step 4: Next Steps
- If degrading: "Address persistent issues to improve trend."
- If improving: "Quality trending up. Monitor to sustain."
- If stable: "Quality stable. Set alerts to catch future issues."

## Output Format
- Time-series health scores (daily, weekly, or monthly)
- Trend direction (improving, degrading, stable)
- Persistent issues (long-standing failures)
- Transient issues (short-lived failures)
- Overall trend summary with percentage change

## Analysis to Provide
- **Trend Direction:** Up, down, or flat
- **Persistent Issues:** Failures lasting > 7 days (need urgent attention)
- **Transient Issues:** Short-lived failures (may be data pipeline issues)
- **Seasonality:** Weekly/monthly patterns if detected

## Error Handling
- If insufficient data → "Need at least 7 days of history for trend analysis."
- If no trends detected → "Quality stable with no significant trends."
- If template fails → Run `preflight-check.sql` to diagnose

## Notes
- This is a READ-ONLY workflow (no approval required)
- Uses SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS() table function
- Best with 30+ days of measurements
- Helps identify chronic vs acute issues
- Use for executive reporting and KPI tracking

## Halting States
- **Success**: Trend report presented with direction
- **Insufficient data**: "Need at least 7 days of history for trend analysis."
- **No trends**: "Quality stable with no significant trends."
