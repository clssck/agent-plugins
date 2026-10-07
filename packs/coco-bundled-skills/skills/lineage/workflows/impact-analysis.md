# Workflow 1: Impact Analysis (Downstream)

*"If I change this, what breaks?"*

## User Intent
When a data asset changes or an issue is detected, I want to quickly understand which downstream datasets, dashboards, and business processes are affected to assess risk and communicate confidently.

## Trigger Phrases
- "What depends on this table?"
- "Impact analysis for [table]"
- "What will break if I change [table]?"
- "Who uses this table?"
- "Downstream dependencies"
- "If I modify [table], what's affected?"

## When to Use
- Before making schema changes
- Before deprecating a table
- When planning data migrations
- When an upstream issue is detected and you need to assess blast radius

## Templates to Use

**Primary:** `impact-analysis.sql`
- Single-level downstream dependencies with risk scoring
- Fast execution, suitable for quick checks

**Extended:** `impact-analysis-multi-level.sql`
- Multi-level traversal (2-3 levels deep)
- Shows cascade effects
- Use for comprehensive impact assessment

**User Attribution:** `impact-analysis-users.sql`
- Identifies affected users/roles
- Use when stakeholder communication is needed

## Execution Steps

1. **Extract Database, Schema, and Table**
   - From user query: "RAW_DB.SALES.ORDERS" → database='RAW_DB', schema='SALES', table='ORDERS'
   - DO NOT ask for confirmation if already provided

2. **Execute Primary Template**
   - Read: `templates/impact-analysis.sql`
   - Replace placeholders: `<database>`, `<schema>`, `<table>`
   - Execute immediately (NO permission prompt)

3. **Risk Tiering** (automatic based on query results)
   - **CRITICAL:** High query frequency (>50/day) OR has downstream dependents OR domain is finance/revenue
   - **MODERATE:** Medium query frequency (10-50/day) OR updated frequently
   - **LOW:** Low query frequency (<10/day) AND no downstream dependents

4. **Present Results**
   ```
   Impact Analysis: DATABASE.SCHEMA.TABLE

   ═══════════════════════════════════════════════════════════════
   CRITICAL RISK (N objects)
   ═══════════════════════════════════════════════════════════════
   1. DEPENDENT_DB.SCHEMA.OBJECT (Type)
      Risk: CRITICAL | Queries: X/day | Users: Y in last 7 days
      → Additional context (feeds dashboards, used for reporting, etc.)

   ═══════════════════════════════════════════════════════════════
   MODERATE RISK (N objects)
   ═══════════════════════════════════════════════════════════════
   ...

   ═══════════════════════════════════════════════════════════════
   LOW RISK (N objects)
   ═══════════════════════════════════════════════════════════════
   ...

   Summary: X downstream dependencies | Y CRITICAL | Z MODERATE | W LOW
   Affected Users: N unique users in last 7 days
   ```

5. **Next Steps**
   - If CRITICAL dependencies: "Consider notifying owners before changes."
   - If many dependencies: "Would you like the full cascade analysis?"
   - Offer to identify specific affected users if needed

## Output Format
- Grouped by risk tier (CRITICAL → MODERATE → LOW)
- Each object shows: name, type, risk level, usage stats
- Summary with total counts and affected users
- Actionable recommendations based on risk
- **External rows**: when the result includes rows where `TARGET_OBJECT_DATABASE IS NULL` and `TARGET_OBJECT_DOMAIN = 'EXTERNAL'` (only on accounts meeting one of the two external-lineage gates — see [`../reference/external-row-output.md`](../reference/external-row-output.md)), present them under a separate "External Dependencies" header, identified by their `TARGET_DATASET_TYPE` and `TARGET_OBJECT_NAME`. Don't apply Snowflake risk/trust scoring to them. See [`../reference/external-row-output.md`](../reference/external-row-output.md).

## Snowflake APIs Used

```sql
-- Primary: Object + data-movement lineage (no account admin; VIEW LINEAGE)
-- Domain 'TABLE' covers tables, views, materialized views, and dynamic tables — do not pass 'VIEW'.
-- For output column names and the DOWNSTREAM_*/UPSTREAM_* pitfall, see ../reference/snowflake-apis.md.
SNOWFLAKE.CORE.GET_LINEAGE('<db>.<schema>.<table>', 'TABLE', 'DOWNSTREAM', 5)
-- Use for downstream list; fall back to OBJECT_DEPENDENCIES if empty or privilege error

-- Fallback: Object dependency only (requires account admin)
SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES
-- Templates: impact-analysis-object-deps-fallback.sql, impact-analysis-multi-level-object-deps-fallback.sql, impact-analysis-users-object-deps-fallback.sql

-- Usage patterns for risk scoring
SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY
-- Fields: query_id, base_objects_accessed, objects_modified, user_name

-- User attribution
SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
-- Fields: query_id, user_name, role_name, query_type
```

## Risk Scoring Logic

```
RISK = CRITICAL if:
  - query_count_7d > 50 OR
  - downstream_dependent_count > 0 OR
  - schema_name IN ('FINANCE', 'REVENUE', 'REPORTING') OR
  - object_type = 'DYNAMIC TABLE'

RISK = MODERATE if:
  - query_count_7d BETWEEN 10 AND 50 OR
  - last_modified < 7 days ago

RISK = LOW otherwise
```

## Error Handling
- Run primary template (GET_LINEAGE) first. If it returns no rows or a privilege error, run the OBJECT_DEPENDENCIES fallback template for this workflow.
- If both return empty → "No downstream dependencies found. Safe to modify." Optionally try impact-analysis-fallback.sql (DDL/INFORMATION_SCHEMA).
- If ACCESS_HISTORY unavailable → Use lineage only (primary or fallback), note "Usage stats unavailable".
- If object not found → "Object not found. Check spelling: DATABASE.SCHEMA.TABLE"

### ⚠️ Stop conditions for the "affected users" arm (impact-analysis-users.sql)

If the user asks "who would be affected" / "which users use this":

1. Run `GET_LINEAGE` to enumerate downstream objects (one query).
2. Run `ACCESS_HISTORY` (using `LATERAL FLATTEN` on `base_objects_accessed`) **once** with a 7-day or 30-day lookback, filtered to the downstream objects from step 1.
3. **If step 2 returns 0 rows → STOP.** Report: "No recorded user activity for the downstream objects in the last N days. ACCESS_HISTORY does not retain data beyond 365 days and may have 45min–3h ingestion latency for new objects."
4. **Do NOT** then run `OBJECT_DEPENDENCIES`, `GRANTS_TO_ROLES`, `GRANTS_TO_USERS`, `SHOW GRANTS`, or `QUERY_HISTORY` looking for user lists. Those views do **not** answer "who would be affected" — they answer "who is granted access" or "who has run anything ever". The answer for "affected users" is whatever `ACCESS_HISTORY` shows, full stop.

## Notes
- This workflow is CRITICAL for change management
- Always run before schema modifications in production
- Risk tiers help prioritize communication efforts
- Consider running during low-traffic periods for accurate usage stats
