# Workflow 2: Root Cause Analysis (Upstream)

*"Why is this number wrong?"*

## User Intent
When I discover incorrect, missing, or unexpected data in an output, I want to trace the data back through its transformations to its source to identify where the issue originated.

## Trigger Phrases
- "Why is this number wrong?"
- "Where does this data come from?"
- "Root cause analysis for [table]"
- "Trace upstream for [table]"
- "Debug [table] data issue"
- "What feeds [table]?"
- "Source of [table]?"

## When to Use
- Data discrepancies discovered in reports
- Unexpected nulls or values in output tables
- Debugging transformation pipelines
- Validating data flow after changes

## Templates to Use

**Primary:** `root-cause-analysis.sql`
- Multi-level upstream lineage
- Shows full source-to-target path

**Change Detection:** `change-detection.sql`
- Recent schema changes in upstream objects
- Recent data modifications
- Identifies likely cause of issues

**Column-Level:** `root-cause-column.sql`
- Trace specific column through transformations
- Use when issue is isolated to specific field

## Execution Steps

1. **Extract Database, Schema, and Table**
   - From user query: "ANALYTICS_DB.REPORTING.REVENUE" → database='ANALYTICS_DB', schema='REPORTING', table='REVENUE'
   - DO NOT ask for confirmation if already provided

2. **Execute Upstream Lineage Query**
   - Read: `templates/root-cause-analysis.sql`
   - Replace placeholders
   - Execute immediately

3. **Execute Change Detection Query**
   - Read: `templates/change-detection.sql`
   - Look for recent changes in upstream objects
   - Correlate timing with when issue was noticed

4. **Identify Divergence Points**
   - Compare expected vs actual data patterns
   - Flag objects with recent modifications
   - Highlight schema changes

5. **Present Results**
   ```
   Root Cause Analysis: DATABASE.SCHEMA.TABLE

   ═══════════════════════════════════════════════════════════════
   UPSTREAM LINEAGE (N levels)
   ═══════════════════════════════════════════════════════════════
   Level 1: [Direct sources]
   Level 2: [Sources of sources]
   Level 3: [Origin tables/stages]

   ═══════════════════════════════════════════════════════════════
   RECENT CHANGES DETECTED
   ═══════════════════════════════════════════════════════════════
   ⚠️  OBJECT_NAME - Change type and timestamp
       Details of what changed
       Changed by: USER_NAME

   ═══════════════════════════════════════════════════════════════
   ANALYSIS
   ═══════════════════════════════════════════════════════════════
   Most Likely Cause: [Identified root cause]
   Recommendation: [Action to investigate/fix]
   ```

6. **Next Steps**
   - If schema change detected: "Verify downstream transforms handle new schema"
   - If data modification detected: "Check the query that modified data"
   - If no changes found: "Issue may be in source system. Check external data."

## Output Format
- Upstream lineage organized by level (closest to furthest)
- Recent changes highlighted with timestamps and users
- Clear "Most Likely Cause" conclusion
- Actionable recommendations
- **External rows**: when the result includes rows where `SOURCE_OBJECT_DATABASE IS NULL` and `SOURCE_OBJECT_DOMAIN = 'EXTERNAL'` (only on accounts meeting one of the two external-lineage gates — see [`../reference/external-row-output.md`](../reference/external-row-output.md)), present them under a separate "External Sources" header, identified by their `SOURCE_DATASET_TYPE` and `SOURCE_OBJECT_NAME`. Note that recent-change detection (schema changes, query history) does not extend to external entities. See [`../reference/external-row-output.md`](../reference/external-row-output.md).

## Snowflake APIs Used

```sql
-- Primary: Upstream lineage (object + data movement; VIEW LINEAGE, no account admin)
-- Domain 'TABLE' covers tables, views, materialized views, and dynamic tables.
-- For output column names and the DOWNSTREAM_*/UPSTREAM_* pitfall, see ../reference/snowflake-apis.md.
SNOWFLAKE.CORE.GET_LINEAGE('<db>.<schema>.<table>', 'TABLE', 'UPSTREAM', 5)
-- Use in root-cause-analysis.sql, change-detection.sql; fall back to OBJECT_DEPENDENCIES if empty or privilege error

-- Fallback: Upstream object dependencies (requires account admin)
SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES
-- Templates: root-cause-analysis-object-deps-fallback.sql, change-detection-object-deps-fallback.sql

-- Schema change detection
SNOWFLAKE.ACCOUNT_USAGE.TABLES
-- Fields: created, last_altered, table_owner

SNOWFLAKE.ACCOUNT_USAGE.COLUMNS  
-- Fields: created, last_altered (for column-level changes)

-- Data modification detection
SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY
-- Filter: objects_modified contains upstream objects

-- Query details for attribution
SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
-- Fields: query_text, user_name, start_time
```

## Change Detection Logic

```sql
-- Schema changes: Tables modified in last 7 days
WHERE last_altered > DATEADD(day, -7, CURRENT_TIMESTAMP())

-- Data changes: Objects modified by DML in last 7 days  
WHERE objects_modified IS NOT NULL
  AND query_start_time > DATEADD(day, -7, CURRENT_TIMESTAMP())

-- Prioritize by recency and proximity to target
ORDER BY 
  CASE WHEN level = 1 THEN 1 ELSE 2 END,  -- Direct sources first
  last_change_time DESC                     -- Most recent first
```

## Divergence Detection

The workflow identifies divergence by:
1. **Schema Divergence:** Column type changes, new/dropped columns
2. **Data Divergence:** Unexpected NULL rates, row count changes
3. **Timing Divergence:** Data freshness mismatches between related tables

## Error Handling
- Run primary template (GET_LINEAGE) first. If no rows or privilege error, run root-cause-analysis-object-deps-fallback.sql (and change-detection-object-deps-fallback.sql for change detection).
- If no upstream dependencies → "This appears to be a source table. Check external data source."
- If no recent changes → "No recent changes detected. Issue may be historical or in source system."
- If ACCESS_HISTORY unavailable → Show lineage only, note "Change detection requires ACCESS_HISTORY"

## Notes
- This workflow is for TROUBLESHOOTING, not routine monitoring
- Start with the failing output and work backwards
- Recent changes are the most likely culprits
- Consider time zones when correlating change timestamps
