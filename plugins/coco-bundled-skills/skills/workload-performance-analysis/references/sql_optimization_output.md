# SQL Optimization Output Format Reference

Standardized formatting for presenting SQL optimization results to users.

## Comment Tags

| Tag | When to Use |
|-----|-------------|
| `[C<N>]` | Every comment line for a change (C1, C2, etc.) |
| `[QUERY_INSIGHT_*]` | From Query Insights (when available) |
| `[GENERAL SUGGESTION]` | Only when NO Query Insights exist (< 2 hours) |
| `[INFERRED]` | Column or value was inferred, not explicit |
| `[ACTION REQUIRED]` | User must confirm before execution |
| `[NOTE]` | Optional suggestion (e.g., view DDL update) |
| `[INFO]` | Positive insight — no changes needed |
| `[WARNING]` | Important issue requiring attention |

**Rules:**
- Every line for the same change uses same `[C<N>]` prefix
- Stack tags in order: Change ID → Insight Type → Details → Status
- DO NOT mix `[QUERY_INSIGHT_*]` and `[GENERAL SUGGESTION]` tags in the same output

## Disclaimer

**ALWAYS display FIRST, before showing any changes:**

```
[IMPORTANT] DISCLAIMER
================================================================
The suggestions below are POTENTIAL PERFORMANCE IMPROVEMENTS based on 
Snowflake Query Insights. Snowflake's optimizer already maximizes 
execution performance automatically.

These SQL modifications may produce DIFFERENT RESULTS than the original.
Please review each change and verify output before production use.
================================================================
```

## Full Output Structure

Present in this order:

1. **DISCLAIMER** (above)
2. **ORIGINAL QUERY** — the full query text
3. **UPDATED QUERY WITH SUGGESTED IMPROVEMENTS** — with summary block at top and inline comments at each change
4. **[VALIDATED]** — Syntax validated via `EXPLAIN` (no execution)
5. **SUGGESTED CHANGES** — numbered list of all changes with insight type and status
6. **MODIFICATION INSTRUCTIONS** — how user can accept, reject, or modify individual changes

## Summary Block

Place at the TOP of the updated SQL:

```sql
-- ============================================================
-- QUERY INSIGHT CHANGES SUMMARY
-- ============================================================
-- [WARNING] These changes may produce different results.
-- ============================================================
-- C1: [<INSIGHT_TYPE>] <Description> - <STATUS>
-- C2: [<INSIGHT_TYPE>] <Description> - <STATUS>
-- ============================================================
-- To modify: "C1 - <your change>" or "Accept all"
-- ============================================================
```

## Inline Comment Format

```sql
-- [C1] [QUERY_INSIGHT_NO_FILTER_ON_TOP_OF_TABLE_SCAN] Added filter
-- [C1] [INFERRED] Column 'sale_date' from clustering key (Confidence: 80/100)
-- [C1] [INFERRED] Value from existing filter on line 12 (Confidence: 95/100)
-- [C1] [ACTION REQUIRED] Confirm date range
WHERE sv.sale_date >= DATEADD('day', -30, CURRENT_DATE())
```

## EXPLAIN Validation

**Always validate generated SQL before presenting:**

```sql
EXPLAIN <updated_sql_query>
```

**IMPORTANT:** Snowflake's EXPLAIN only works with SELECT statements. If the original query is DML (INSERT, MERGE, CREATE TABLE AS, etc.), extract the SELECT portion for EXPLAIN validation. For example:
- `INSERT INTO t SELECT ...` → `EXPLAIN SELECT ...`
- `CREATE TABLE t AS SELECT ...` → `EXPLAIN SELECT ...`
- `MERGE INTO t USING (SELECT ...) ...` → `EXPLAIN SELECT ...` (validate the USING subquery)

- If EXPLAIN succeeds → show `[VALIDATED] Syntax validated via EXPLAIN (no execution)`
- If EXPLAIN fails → attempt auto-fix and retry (max 3 attempts)
- If still fails after 3 attempts → present SQL with `[WARNING] MANUAL REVIEW REQUIRED`

## User Confirmation

**[CRITICAL] Always ask before execution:**

```
Would you like me to execute this updated query?

Reply:
- "Yes" or "Execute" to run the updated query
- "No" to skip execution
- "C<N> - <modification>" to adjust a specific change
- "Accept all" to accept all changes as-is
```

**Never execute updated SQL without explicit user approval.**

## Special Formats

### Positive Insights (no changes needed)

```sql
-- [INFO] Query benefited from: <INSIGHT_DESCRIPTION>
--   Table: <TABLE_NAME>
--   This is working well - no changes needed.
```

### Spillage with Co-Located Root Cause

```
[WARNING] REMOTE SPILLAGE DETECTED - POTENTIAL ROOT CAUSE IDENTIFIED

Another insight was detected on the same logical node that may be the ROOT CAUSE:
  - [<OTHER_INSIGHT_TYPE>] on node [<NODE_ID>]: <MESSAGE>

RECOMMENDATION: 
1. FIRST - Address the <OTHER_INSIGHT_TYPE> issue (see suggested fix above)
2. Re-run the query after applying the fix
3. If spillage persists, THEN consider a larger warehouse
```

### Spillage without Co-Located Root Cause

```
[WARNING] REMOTE SPILLAGE DETECTED

This query spilled data to remote storage. No SQL-level root cause identified.

RECOMMENDATION: Use a larger warehouse size.
```

### Queuing (not a SQL issue)

```sql
-- [NOTE] QUEUING DETECTED: Query waited for warehouse resources (overload)
-- Suggestions:
--   - Use a dedicated or less-utilized warehouse
--   - Schedule execution during off-peak hours
--   - Consider multi-cluster warehouse for concurrency scaling
```

### View Expansion

```sql
FROM my_schema.orders_view ov  -- issue in underlying table: my_schema.raw_orders
-- [C1] [QUERY_INSIGHT_*] <fix description>
-- [C1] [NOTE] Consider updating view DDL if filter benefits all view users
```

## Post-Execution Comparison Format

After executing the optimized query, present a comparison:

```
### Performance Comparison

| Metric | Original | Optimized | Change |
|--------|----------|-----------|--------|
| Total elapsed | <X>s | <Y>s | <±Z%> |
| Execution time | <X>s | <Y>s | <±Z%> |
| Rows produced | <N> | <M> | <diff> |

[WARNING] These numbers may not be directly comparable due to:
- Warehouse caching (second run may benefit from cached data)
- Queue wait time differences (concurrency varies by time of day)
- Underlying data changes (table contents may have changed)

To get a fairer comparison, you can re-run the original query now.
```

### Operator-Level Comparison

Compare `GET_QUERY_OPERATOR_STATS` for operators targeted by insights:

```
### Operator Comparison (Insight-Targeted Nodes)

| Operator | Type | Original In→Out | Optimized In→Out | Change |
|----------|------|-----------------|------------------|--------|
| [<ID>] | <TYPE> | <in>→<out> | <in>→<out> | <note> |
```

**Rules:**
- Only compare operators that map to insight-targeted nodes (the ones changes were applied to)
- If the optimizer produces a different plan shape, note this — operator IDs may not align 1:1
- Use `OPERATOR_TYPE` + `OPERATOR_ATTRIBUTES` to match corresponding operators across plans when IDs differ
