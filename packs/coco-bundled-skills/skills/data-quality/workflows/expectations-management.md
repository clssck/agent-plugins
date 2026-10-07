---
parent_skill: data-quality
---

# Workflow: DMF Expectations Management

View, set, and tune DMF expectation thresholds — the pass/fail criteria that determine whether a DMF result triggers a violation. Without expectations, DMF measurements are informational only; with expectations, they produce actionable pass/fail outcomes.

**Closes gaps:** G2/MA-03 (Auto-Threshold Calculation), OA-02 (Alert Effectiveness Analysis — threshold tuning).

## Trigger Phrases
- "Set a threshold for my DMF"
- "Configure DMF expectations"
- "Review DMF expectations"
- "Show me which expectations are passing and failing"
- "Tune my monitor thresholds"
- "My monitor fires too often — reduce the threshold"
- "Set NULL_COUNT must equal zero"
- "Add an expectation to my DMF"
- "What are my current DQ thresholds?"

## When to Load
- User wants to define pass/fail criteria for DMF measurements
- User's monitors are too noisy (threshold too strict) and want to relax them
- User wants to review current expectations and their status

---

## Execution Steps

### Step 1: Establish Scope and Intent

Extract from user message:
- **Scope**: `DATABASE.SCHEMA` or `DATABASE.SCHEMA.TABLE`
- **Intent**:
  - **Review**: show current expectations and their pass/fail status
  - **Set**: add a new expectation to an existing DMF
  - **Tune**: modify an existing expectation threshold
  - **Remove**: drop an expectation

If scope not provided, ask:
> "Which schema or table would you like to manage DMF expectations for? Please provide `DATABASE.SCHEMA` or `DATABASE.SCHEMA.TABLE`."

---

### Step 2: Review Current Expectations

**You must use the template:** Read and execute `templates/expectations-review.sql` with `<database>` and `<schema>` replaced. Do not substitute a different query or derive pass/fail by joining DATA_QUALITY_MONITORING_RESULTS with DATA_METRIC_FUNCTION_EXPECTATIONS — the template is the source of truth.

The template uses **SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_EXPECTATION_STATUS** (view or table function) for pass/fail via the `expectation_violated` column. It shows:
- Expectation name and expression
- Current metric value
- Pass/Fail status (from expectation_violated: TRUE = FAIL, FALSE = PASS)
- Last measurement time

Present:

```
## DMF Expectations Review: <DATABASE.SCHEMA>

| Table | Metric | Expectation | Current Value | Status | Last Run |
|-------|--------|------------|--------------|--------|----------|
| CUSTOMERS | NULL_COUNT(email) | value = 0 | 3 | ❌ FAIL | 2026-03-01 14:22 |
| ORDERS | FRESHNESS | value < 86400 | 72000 | ✅ PASS | 2026-03-01 15:00 |
| PRODUCTS | DUPLICATE_COUNT(sku) | value = 0 | 0 | ✅ PASS | 2026-03-01 14:58 |
| ORDERS | NULL_COUNT(customer_id) | (none) | 5 | — NO EXPECTATION | 2026-03-01 15:00 |

Tables with no expectations: X of Y monitored tables
```

Tables/metrics with no expectation have measurements but no pass/fail definition — offer to set one.

---

### Step 3: Set or Modify an Expectation

For setting a new expectation, or modifying an existing one, use the Snowflake expectation DDL syntax.

First, show the user what the threshold will do — then ask for confirmation if modifying an existing expectation (which replaces it).

**Setting a new expectation (NULL_COUNT must equal 0):**
```sql
ALTER DATA METRIC FUNCTION SNOWFLAKE.CORE.NULL_COUNT
  ON <database>.<schema>.<table>(<column>)
  SET EXPECTATION (
    EXPRESSION => 'value = 0',
    NAME => 'no_nulls_in_<column>'
  );
```

**Common expectation patterns:**

| Use Case | Expression | Example |
|---|---|---|
| No nulls allowed | `value = 0` | Critical ID or required field |
| No duplicates | `value = 0` | Primary key or unique column |
| Maximum null tolerance | `value < <N>` | `value < 10` for non-critical column |
| Freshness SLA (seconds) | `value < <seconds>` | `value < 3600` for hourly data |
| Row count minimum | `value > <N>` | `value > 1000` for active tables |
| Row count range | `value BETWEEN <min> AND <max>` | Expected data volume band |
| Custom DMF passes | `value = 0` | Format validation, referential integrity |

**Modifying an existing expectation (relax to allow up to 5 nulls):**
```sql
ALTER DATA METRIC FUNCTION SNOWFLAKE.CORE.NULL_COUNT
  ON <database>.<schema>.<table>(<column>)
  SET EXPECTATION (
    EXPRESSION => 'value < 5',
    NAME => 'max_5_nulls_in_<column>'
  );
```

**⚠️ STOPPING POINT**: For new expectations, execute immediately (it is a configuration change, not a data change). For **modifying** existing expectations, first confirm:

> "I'll change the expectation on `<table>.<metric>` from `<old_expression>` to `<new_expression>`. This will change the pass/fail status for this monitor. Proceed? (Yes / No)"

---

### Step 4: Threshold Tuning Guidance

If the user mentions a monitor fires too often (noisy) or never fires (silent), provide intelligent tuning guidance:

**For noisy monitors** (violation rate > 80%):
- If `NULL_COUNT > 0` fires on every run: check if the column legitimately has nulls → relax to `value < N` where N is the 10th percentile of historical values
- If `FRESHNESS > <threshold>`: check actual refresh cadence → set threshold to 1.5x the normal refresh interval
- Suggest: "Based on recent history, the value has been around X. Setting threshold to `value < X * 1.5` would reduce noise while still catching real issues."

**For silent monitors** (never fires a violation):
- The threshold may be too loose or the data is actually clean
- Check: is the DMF actually running? (`SHOW` the schedule status)
- If data is always clean → the monitor is healthy, not broken
- If the threshold is `value < 1000` for a NULL_COUNT that is always 0 → the expectation is too loose to be meaningful; suggest tightening

**For setting auto-suggested thresholds** (MA-03):
Query historical DMF results to suggest a data-driven threshold:
```sql
-- Suggest threshold based on historical distribution (p90 value)
SELECT
    METRIC_NAME,
    COUNT(*) AS measurements,
    MIN(VALUE) AS min_val,
    MAX(VALUE) AS max_val,
    ROUND(AVG(VALUE), 2) AS avg_val,
    ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY VALUE), 2) AS p90_val,
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY VALUE), 2) AS p95_val
FROM TABLE(SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS(
    REF_ENTITY_NAME => '<database>.<schema>.<table>',
    REF_ENTITY_DOMAIN => 'TABLE'
))
WHERE METRIC_NAME = '<metric_name>'
  AND MEASUREMENT_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP BY METRIC_NAME;
```

Present: "Based on 30 days of history, the P90 value for `<metric>` is X. I recommend setting the expectation to `value < X * 1.2` to allow for normal variance while catching genuine anomalies."

---

### Step 5: Remove an Expectation (Optional)

If the user wants to remove an expectation entirely:

```sql
ALTER DATA METRIC FUNCTION SNOWFLAKE.CORE.NULL_COUNT
  ON <database>.<schema>.<table>(<column>)
  UNSET EXPECTATION 'no_nulls_in_<column>';
```

Always confirm before removing.

---

## Output Format
- Current expectations table: metric, expression, current value, pass/fail status
- New/modified expectation DDL (shown before execution)
- Tuning suggestions with historical data context
- Post-change confirmation

## Stopping Points
- ✋ **Step 1**: Scope not provided — ask before proceeding
- ✋ **Step 3**: Before modifying an existing expectation — confirm the change
- ✋ **Step 5**: Before removing an expectation — confirm

## Error Handling
| Issue | Resolution |
|-------|-----------|
| `DATA_METRIC_FUNCTION_EXPECTATIONS` view empty | No expectations set yet — this is normal for new DMF setups; proceed to set new ones |
| ACCOUNT_USAGE latency (expectations not yet visible) | Expectations show up with the standard 45min–3hr ACCOUNT_USAGE latency; newly set expectations are active immediately even if not yet visible in the view |
| No DMF results available | DMF may not have run yet; wait 1–2 minutes and retry |
| Table has no DMFs attached | Expectations require DMFs; redirect to `monitor-recommendations.md` first |
| Permission error on ALTER DATA METRIC FUNCTION | Requires ownership of the DMF or `MANAGE DATA METRIC FUNCTION` privilege on the table |

## Notes
- Expectations are stored in Snowflake and apply to every future DMF execution — they persist until explicitly removed or modified
- Setting an expectation does not immediately re-run the DMF; the next scheduled run or `TRIGGER_ON_CHANGES` event evaluates it
- Expectations are visible in `SNOWFLAKE.ACCOUNT_USAGE.DATA_METRIC_FUNCTION_EXPECTATIONS` with standard ACCOUNT_USAGE latency
- For bulk expectation management across a schema, consider scripting via a loop over `INFORMATION_SCHEMA.DATA_METRIC_FUNCTION_REFERENCES`
- **Tiered expectations (warn vs critical):** Snowflake supports multiple expectations per DMF (e.g. two on FRESHNESS: `value < 300` for warning, `value < 1800` for critical), each with a distinct expectation name — useful for escalation and dashboards
- **Test before enabling alerts:** Use `SYSTEM$EVALUATE_DATA_QUALITY_EXPECTATIONS` on the target table/view to validate expressions and current violations before enabling alerts or circuit breakers; use in CI or one-off checks
