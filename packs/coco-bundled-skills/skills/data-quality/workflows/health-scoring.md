---
parent_skill: data-quality
---

# Workflow 1: Schema Health Scoring

## Trigger Phrases
- "Can I trust my schema?"
- "Schema health check"
- "Schema quality score"
- "How healthy is [DATABASE.SCHEMA]?"

## When to Load
Data-quality Step 2: health/trust/score intent.

## Template to Use
**Primary:** `schema-health-snapshot-realtime.sql`
- Provides immediate, real-time health score via dynamic table discovery
- Use for demos and ad-hoc checks

**Fallback (if real-time fails):** `schema-health-snapshot.sql`
- Also uses `SNOWFLAKE.LOCAL` but with a different query structure
- Use when the primary template has issues

## Execution Steps

### Step 0: Preflight Check
- Run `templates/preflight-check.sql` first (as specified in SKILL.md Step 0)
- If preflight fails, stop and report the issue
- If preflight passes, proceed to Step 1

### Step 1: Extract Database and Schema
- From user query: "DEMO_DQ_DB.SALES" → database='DEMO_DQ_DB', schema='SALES'
- If not already provided, ask which DATABASE.SCHEMA to check

### Step 2: Execute Template
- Read: `templates/schema-health-snapshot-realtime.sql`
- This template dynamically discovers tables via `INFORMATION_SCHEMA.TABLES` — no hardcoded table names
- Uses `SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS()` table function (correct column: `VALUE`, not `metric_value`)
- Replace: `<database>` → actual database name, `<schema>` → actual schema name
- Execute via `snowflake_sql_execute` (NO permission prompt)

### Step 3: Present Results
```
Schema Health Report: DATABASE.SCHEMA

Overall Health: XX.X%
Metrics: X passing, Y failing
Tables Monitored: Z tables
Issues Found: N tables with problems
```

### Step 4: Next Steps
- If health = 100%: "All metrics passing. No action needed."
- If health < 100%: Use `ask_user_question` to offer:

  > "Your schema health is X%. Would you like me to dig into what's failing and why?"

  | Option | Description |
  |--------|-------------|
  | **Show me what's failing** | Run root cause analysis to list the specific DMF failures (null counts, duplicates, etc.). From there, you can also trace the upstream data lineage to find where the bad data originates. |
  | **No, just show the summary** | Stop here with the health score overview. |

- Do NOT auto-run root cause — wait for user selection
- Note: the full investigation chain is **health score → root cause analysis → upstream lineage** — each step is offered as a follow-up, not auto-chained

## Output Format
- Overall health percentage
- Count of passing vs failing metrics
- Number of tables monitored
- Number of tables with issues

## Error Handling
- If real-time template fails → Try fallback template (`schema-health-snapshot.sql`)
- If both fail → Check DMF attachment: `check-dmf-status.sql`
- If no DMFs → "No DMFs found. Set up monitoring first."

## Notes
- This is a READ-ONLY workflow (no approval required)
- Does not drill into specific failures (use root-cause-analysis.md for that)
- Fast execution (< 5 seconds for schemas with < 20 tables)

## Halting States
- **Success**: Health report presented — suggest next steps based on score
- **No DMFs**: Inform user that monitoring needs to be set up first
