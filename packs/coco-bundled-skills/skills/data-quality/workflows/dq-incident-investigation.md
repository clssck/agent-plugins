---
parent_skill: data-quality
---

# Workflow: DQ Incident Investigation

Multi-dimensional root-cause analysis for a data quality incident. Starts from a known or suspected DMF violation, then orchestrates investigation across the data-quality, lineage, and data-governance skills to produce a unified root-cause report with a chronological timeline and actionable remediation steps.

**Closes gaps:** G1 (Agentic Troubleshooting), G6 (Natural Language DQ Investigation), TA-01 to TA-03.

## Trigger Phrases
- "Why did freshness drop on TABLE_X?"
- "Investigate the quality incident on SCHEMA.TABLE"
- "Root cause for DMF violation on TABLE"
- "Why did my row count drop?"
- "Why are there suddenly nulls in TABLE?"
- "Correlate the quality violation with upstream changes"
- "DQ incident root cause"
- "What caused the quality failure?"

## When to Load
- User describes a data quality incident (freshness drop, row count anomaly, sudden nulls/duplicates)
- User wants multi-dimensional investigation beyond just "what metrics failed"
- Use `root-cause-analysis.md` for a simpler "show me what's failing" check; use this workflow when the user wants to understand **why** it happened

---

## Execution Steps

### Step 1: Identify the Incident

Extract from user message:
- **Affected object**: `DATABASE.SCHEMA.TABLE` (ask if not provided)
- **Metric type** (if mentioned): FRESHNESS, NULL_COUNT, ROW_COUNT, DUPLICATE_COUNT, or unknown
- **Time of incident** (if mentioned): "yesterday", "this morning", "around 3pm" — convert to approximate timestamp window

If the object is not clearly provided, ask:
> "Which table or schema experienced the quality issue? Please provide `DATABASE.SCHEMA.TABLE` (or just `DATABASE.SCHEMA` to investigate the whole schema)."

---

### Step 2: Check DMF Violations (DQ Skill — Primary Investigation)

Load and run the existing `root-cause-analysis.md` workflow against the affected object (including Steps 2b–2d: expectation status, trust stored measurement, system vs custom / GET_DDL).

This step answers: **What metrics are failing, with what values, and since when?**

- Execute `templates/schema-root-cause-realtime.sql` (or `schema-root-cause.sql` as fallback)
- For expectation-backed dashboard incidents, also query `DATA_QUALITY_MONITORING_EXPECTATION_STATUS` (`expectation_violated`, `value`, `expectation_expression`)
- Extract: failing metric names, **authoritative** violation values (`VALUE` / expectation `value`), `MEASUREMENT_TIME`, `METRIC_DATABASE` (SYSTEM vs CUSTOM)
- For CUSTOM DMFs: `GET_DDL('FUNCTION', …)` before any explanation or sample — never paraphrase the rule
- Optional examples: follow `templates/reproduce-dmf-violation.sql`; label as examples of N total — **never** report a `LIMIT` size as the violation count
- Note the violation timestamp — this anchors the cross-skill correlation in Steps 3 and 4

If no DMF violations are found:
> "No active DMF violations found for `<table>`. The issue may be resolved, the DMF may not be attached, or the DMF hasn't run since the incident. Would you like to run an ad-hoc one-time quality check instead?"

---

### Step 3: Trace Upstream Lineage (Delegate to Lineage Skill)

**Say to the user:** "I found quality issues. Now I'll trace the upstream data lineage to identify where the bad data entered the pipeline."

Load the `lineage` skill and run its root-cause-analysis workflow:
- Entry point: `data-governance/lineage/workflows/root-cause-analysis.md`
- Pass the failing table as the starting object
- Run both `templates/root-cause-analysis.sql` (upstream lineage) and `templates/change-detection.sql` (recent schema changes in upstream objects)

From this step, extract:
- **Upstream objects**: tables, views, or stages feeding the affected table
- **Recent changes**: any DDL modifications to upstream objects near the violation timestamp
- **Change timing**: did any upstream schema change precede the violation?

---

### Step 4: Check Query and Task History (Delegate to Data-Governance Skill)

**Say to the user:** "Now checking query and task history for failures that may have caused the issue."

Load the `data-governance` skill and use its `horizon-catalog` workflow to investigate:
- Entry point: `data-governance/data-governance/workflows/horizon-catalog.md`

Ask the data-governance skill to run:

1. **Failed queries on upstream objects** — queries that errored or were cancelled in the window surrounding the violation timestamp:
```sql
-- Provide to data-governance skill as context:
-- Find failed/errored queries touching <upstream_table> in last 48h
-- NOTE: LIMIT here caps HISTORY rows only — it is NOT a DMF violation count.
SELECT QUERY_TEXT, USER_NAME, ROLE_NAME, ERROR_MESSAGE, START_TIME, END_TIME
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME >= DATEADD('hour', -48, '<violation_timestamp>')
  AND ERROR_CODE IS NOT NULL
  AND (QUERY_TEXT ILIKE '%<upstream_table>%' OR QUERY_TEXT ILIKE '%<schema>%')
ORDER BY START_TIME DESC
LIMIT 20;
```

2. **Failed task runs** — TASK_HISTORY for tasks that write to upstream objects:
```sql
-- Find failed tasks in the window
-- NOTE: LIMIT here caps HISTORY rows only — it is NOT a DMF violation count.
SELECT NAME, DATABASE_NAME, SCHEMA_NAME, STATE, ERROR_MESSAGE,
       SCHEDULED_TIME, COMPLETED_TIME
FROM SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY
WHERE SCHEDULED_TIME >= DATEADD('hour', -48, '<violation_timestamp>')
  AND STATE = 'FAILED'
ORDER BY SCHEDULED_TIME DESC
LIMIT 20;
```

From this step, extract:
- **Failed queries**: any errors on upstream tables before the violation
- **Failed tasks**: any pipeline tasks that failed near the violation time

---

### Step 5: Synthesize Root-Cause Report

Combine findings from Steps 2, 3, and 4 into a unified incident report:

```
## DQ Incident Report: <DATABASE.SCHEMA.TABLE>

### Incident Summary
- Affected metric: <METRIC_DATABASE>.<METRIC_SCHEMA>.<METRIC_NAME> (SYSTEM|CUSTOM)
- Violation detected: <MEASUREMENT_TIME>
- Violation count (from DMF measurement): <VALUE>   ← authoritative; never replace with a sample size
- Expectation (if any): <expectation_expression> — VIOLATED|PASS (from EXPECTATION_STATUS)

### Root Cause (Primary)
<The most likely cause based on correlated evidence — e.g., "An upstream schema change to
STAGING.ORDERS removed the updated_at column at 14:32, causing FRESHNESS DMF to fail at 15:00.">

### Contributing Factors
- <Factor 1: e.g., failed LOAD_ORDERS task at 13:58>
- <Factor 2: e.g., DDL ALTER TABLE on STAGING.CUSTOMERS at 14:00>
- <Factor 3: if any>

### Chronological Timeline
| Time | Event | Source |
|------|-------|--------|
| <time> | <event> | DMF violation |
| <time> | <event> | TASK_HISTORY |
| <time> | <event> | Lineage change-detection |

### Affected Downstream Objects
<List from lineage impact analysis — objects that consume the affected table>

### Recommended Remediation Steps
1. <Specific, executable step — e.g., "Restore the updated_at column: ALTER TABLE STAGING.ORDERS ADD COLUMN updated_at TIMESTAMP_NTZ;">
2. <Step 2>
3. <Step 3 — e.g., "After fix: manually trigger DMF re-run and verify FRESHNESS returns to passing">
```

If evidence is sparse, state the most probable hypothesis and what additional investigation would confirm it.

---

### Step 6: Next Steps (skill-backed only)

After presenting the report, use `ask_user_question` and offer **only** options that load an existing workflow. Do **not** offer freeform “fix the data.”

Present options as **user-facing click labels** (action-oriented, plain language). **Copy the click labels below verbatim** for the default top 6 — do not paraphrase, reorder, or replace any item (e.g. do **not** substitute “trace upstream lineage” for #6; lineage belongs earlier in the investigation, not as a post-report swap-in). Offer in **this priority order**. Default ask shows the **top 6** + “No thanks”; reveal 7–11 only if the user asks “what else?” or the case clearly fits.

| Priority | Click label (show to user) | Load | When |
|----------|----------------------------|------|------|
| 1 | **Set up notifications on this association to get alerts when it fails** | `workflows/dq-notifications.md` | Default |
| 2 | **Set up a circuit breaker to auto-pause downstream pipelines when this fails again** | `workflows/circuit-breaker.md` | Default |
| 3 | **Adjust the pass/fail threshold for this check** | `workflows/expectations-management.md` | Default |
| 4 | **See whether this just broke or has been failing for a while** | `workflows/regression-detection.md` | Default |
| 5 | **Show how this metric has changed over time** | `workflows/trend-analysis.md` | Default |
| 6 | **Recommend or attach better monitors on these tables** | `workflows/monitor-recommendations.md` | Default |
| 7 | **Create a custom quality rule (or ACCEPTED_VALUES allow-list)** | `workflows/custom-dmf-patterns.md` | “What else?” / rule gap |
| 8 | **Check overall schema health score** | `workflows/health-scoring.md` | “What else?” / posture |
| 9 | **Find unmonitored tables or noisy monitors** | `workflows/coverage-gaps.md` | “What else?” / hygiene |
| 10 | **Compare two tables (e.g. staging vs prod)** | `workflows/compare-tables.md` | “What else?” / parity |
| 11 | **Break this metric down by a column (e.g. per region)** | `workflows/within-group-dmf.md` | “What else?” / segments |
| — | **No thanks — I’m done for now** | — | Exit |

Example default prompt (top 6):

> What would you like to do next?
> 1. Set up notifications on this association to get alerts when it fails  
> 2. Set up a circuit breaker to auto-pause downstream pipelines when this fails again  
> 3. Adjust the pass/fail threshold for this check  
> 4. See whether this just broke or has been failing for a while  
> 5. Show how this metric has changed over time  
> 6. Recommend or attach better monitors on these tables  
> Or **No thanks**. (Say **“what else?”** for more options.)

Load the matching workflow from the table. Prefer `dq-notifications` over `sla-alerting` unless the user asks for a custom health-% ALERT.

Do not invent follow-ups that lack a workflow file.

---

## Output Format
- Incident summary (metric FQN, **measurement** violation count, expectation status if any, detection time)
- For custom DMFs: rule explanation grounded in GET_DDL (not paraphrased)
- Optional example rows clearly labeled as a sample of the measurement total
- Primary root cause with supporting evidence
- Contributing factors
- Chronological event timeline
- Downstream blast radius
- Actionable remediation steps

## Stopping Points
- ✋ **Step 1**: If affected table is not provided — ask before proceeding
- ✋ **Step 5**: After presenting the full report — offer skill-backed next steps from the Step 6 table and await user response

## Error Handling
| Issue | Resolution |
|-------|-----------|
| No DMF violations found | Offer ad-hoc check; violation may be resolved or DMF not attached |
| Lineage skill returns no upstream objects | Report the table as a source (no upstream lineage); skip Step 4 |
| ACCOUNT_USAGE latency (data not yet available) | Note that query/task history has 45min–3hr latency; provide best available evidence |
| Multiple simultaneous violations | Investigate the most critical metric first (FRESHNESS > NULL_COUNT > DUPLICATE > ROW_COUNT) |

## Notes
- This workflow **orchestrates** other skills — it does not duplicate their SQL logic
- QUERY_HISTORY and TASK_HISTORY analysis belongs to the `data-governance` skill
- Upstream lineage and DDL change detection belongs to the `lineage` skill
- Always anchor the cross-skill investigation to the violation timestamp from Step 2
- DMF violation count always comes from stored measurement / EXPECTATION_STATUS — never from history `LIMIT`s or example-row previews
- Presentation contract refinement: see SNOW-3854076; AD-specific path: see SNOW-3854078
