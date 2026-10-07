---
parent_skill: data-quality
---

# Workflow: DQ Coverage & Meta-Observability

Meta-observability — analyze the health and effectiveness of the data quality monitoring practice itself, not just the data. Answers: "Am I monitoring the right things? Are my monitors working? Are they noisy or silent? Am I spending credits efficiently?"

**Closes gaps:** G3 (Operations/Meta-Observability Agent), OA-01 (Monitoring Coverage Dashboard), OA-02 (Alert Effectiveness), OA-03 (Incident Trend Analysis), OA-05 (DQ Cost Optimization).

## Trigger Phrases
- "What % of my tables are monitored?"
- "Show me my DQ coverage gaps"
- "Which tables have no monitors?"
- "Are any of my monitors noisy?"
- "Which monitors never fire?"
- "DQ monitoring health"
- "Coverage report"
- "Which DMFs are costing the most?"
- "Are my monitors working?"
- "DQ operations report"

## When to Load
- User wants an operational view of their DQ monitoring practice
- User wants to find unmonitored critical tables
- User wants to tune or decommission underperforming monitors

**Scope to critical assets:** When identifying coverage gaps, prioritize contract boundaries (gold/shared tables, data products), business keys, PII/financial fields, and SLA-sensitive pipelines; avoid treating every transient staging table as equally critical by default.

---

## Execution Steps

### Step 1: Establish Scope

Extract target scope from user message:
- **Preferred**: `DATABASE.SCHEMA`
- **Also accepted**: database name only (will analyze all schemas)

If not provided, ask:
> "Which database or schema would you like the coverage report for? Please provide `DATABASE.SCHEMA` or just the database name."

Determine user's primary focus (ask if ambiguous):
1. **Coverage report** — what % is monitored, what's missing
2. **Monitor effectiveness** — which monitors are noisy, silent, or potentially broken
3. **Cost optimization** — which DMFs cost the most vs. the value they provide
4. **All of the above** — full operational report

---

### Step 2: Compute Coverage Metrics

Read and execute `templates/coverage-gaps-summary.sql` with `<database>` and `<schema>` replaced.

This produces:
- Total table count in scope
- Tables with ≥1 DMF attached
- Coverage % overall
- Tables with zero DMFs + their access frequency (critical unmonitored candidates)
- Per-metric coverage (how many tables have NULL_COUNT vs FRESHNESS vs DUPLICATE_COUNT)

---

### Step 3: Identify Critical Unmonitored Tables

From the coverage query results, flag tables that are:
- **Zero DMF coverage** AND
- High access frequency (>50 queries in last 90 days from ACCESS_HISTORY) **OR**
- Have downstream dependents (from OBJECT_DEPENDENCIES if available)

Present these as the highest-priority gaps:

```
### Critical Unmonitored Tables (monitor these first)
| Table | Queries/90d | Downstream Objects | Risk |
|-------|------------|-------------------|------|
| TABLE_X | 1,245 | 8 | CRITICAL |
| TABLE_Y | 892 | 3 | HIGH |
```

After presenting, offer:
> "Would you like me to generate DMF recommendations for these unmonitored tables?"

If yes → Load `workflows/monitor-recommendations.md` with these tables as the scope.

---

### Step 4: Analyze Monitor Effectiveness

**You must use the template:** Read and execute `templates/monitor-effectiveness.sql` with `<database>` and `<schema>` replaced. Do not substitute a different query for violation counts — the template uses **SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_EXPECTATION_STATUS** for violation rates and effectiveness (noisy/silent/healthy). Credits come from `SNOWFLAKE.ACCOUNT_USAGE.DATA_QUALITY_MONITORING_USAGE_HISTORY`.

The template identifies:

**Noisy monitors** (violation rate > 80% of executions in last 30 days):
- These are potentially misconfigured, have thresholds that are too strict, or reflect a chronic data issue that has never been remediated
- Flag for: threshold tuning (load `expectations-management.md`) OR investigation (load `root-cause-analysis.md`)

**Silent monitors** (0 violations AND 0 results in last 30 days):
- These may be suspended, misconfigured, or pointing at tables that never change
- Flag for: review schedule status and verify DMF is actually running

**Stale monitors** (schedule = SUSPENDED):
- DMF is attached but not running
- Flag for: `ALTER TABLE ... SET DATA_METRIC_SCHEDULE = 'TRIGGER_ON_CHANGES'` to resume

Present effectiveness summary:

```
### Monitor Effectiveness Report (Last 30 Days)

#### Noisy Monitors (firing > 80% of runs — review thresholds)
| Table | Metric | Violation Rate | Recommendation |
|-------|--------|---------------|----------------|
| ORDERS | NULL_COUNT(email) | 95% | Relax threshold or fix upstream data |

#### Silent Monitors (0 results — may be broken)
| Table | Metric | Last Run | Status |
|-------|--------|----------|--------|
| PRODUCTS | FRESHNESS | Never | SUSPENDED |

#### Healthy Monitors (within normal range)
X monitors operating normally
```

---

### Step 5: Cost Optimization Analysis

Query `SNOWFLAKE.ACCOUNT_USAGE.DATA_QUALITY_MONITORING_USAGE_HISTORY` for credit consumption per DMF:

```sql
SELECT
    REF_ENTITY_NAME AS table_name,
    METRIC_NAME,
    SUM(CREDITS_USED) AS total_credits_30d,
    COUNT(*) AS executions_30d,
    ROUND(SUM(CREDITS_USED) / NULLIF(COUNT(*), 0), 6) AS credits_per_execution
FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_QUALITY_MONITORING_USAGE_HISTORY
WHERE MEASUREMENT_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
  AND REF_ENTITY_NAME ILIKE '<database>.<schema>.%'
GROUP BY 1, 2
ORDER BY total_credits_30d DESC;
```

Cross-reference with table access frequency: **expensive DMFs on rarely-queried tables** = optimization candidates.

Present:
```
### Cost Optimization Opportunities

#### Expensive DMFs on Low-Value Tables (consider reducing schedule or removing)
| Table | Metric | Credits/30d | Queries/30d | Action |
|-------|--------|------------|------------|--------|
| ARCHIVE_DATA | NULL_COUNT | 0.42 | 0 | Suspend or remove |

#### High-Value DMFs (expensive but justified by high downstream impact)
| Table | Metric | Credits/30d | Downstream | Keep |
|-------|--------|------------|-----------|------|
| ORDERS_FACT | FRESHNESS | 0.15 | 12 | Yes |

Total monthly DMF spend: X credits (~$Y at current pricing)
```

---

### Step 6: Present Operational Summary and Next Steps

```
## DQ Operations Report: <DATABASE.SCHEMA>

### Coverage Snapshot
- Total tables: X
- Monitored tables: Y (Z%)
- Critical unmonitored: N tables

### Monitor Health
- Healthy monitors: A
- Noisy monitors: B (need threshold tuning)
- Silent/suspended monitors: C (need investigation)

### Cost
- Monthly DMF spend: X credits
- Optimization savings available: ~Y credits/month

### Top Recommendations
1. Monitor [TABLE_X, TABLE_Y] — critical unmonitored, high traffic
2. Tune threshold for [ORDERS.NULL_COUNT(email)] — firing 95% of runs
3. Investigate [PRODUCTS.FRESHNESS] — suspended, never ran
4. Suspend DMF on [ARCHIVE_DATA] — 0 queries, wasting credits
```

Always offer:
> "Would you like me to:
> 1. Generate DMF recommendations for unmonitored tables?
> 2. Tune thresholds on noisy monitors?
> 3. Show the full cost breakdown?"

---

## Output Format
- Coverage % summary (total tables, monitored %, per-metric breakdown)
- Critical unmonitored table list with access frequency + downstream count
- Monitor effectiveness: noisy, silent, and suspended monitor lists
- Cost optimization: expensive DMFs on low-value tables
- Prioritized operational recommendations

## Stopping Points
- ✋ **Step 1**: Scope not provided — ask before proceeding
- ✋ **Step 3**: After critical unmonitored table list — offer to generate recommendations, await response
- ✋ **Step 6**: After full report — offer follow-up actions, await user response

## Error Handling
| Issue | Resolution |
|-------|-----------|
| DATA_QUALITY_MONITORING_USAGE_HISTORY empty | Either no DMFs are attached, or history is within 45-min latency window — note this and skip cost section |
| OBJECT_DEPENDENCIES unavailable | Skip downstream count; base criticality on access frequency only |
| ACCESS_HISTORY unavailable | Skip access frequency; base criticality on table row count and column types only |
| No DMFs at all | Redirect to `monitor-recommendations.md` — coverage is 0% |

## Notes
- This workflow is read-only except for the optional "suspend DMF" optimization action
- Skip Step 5 if the user only wants the coverage report (check user intent in Step 1)
- Cross-skill: for detailed query/task history behind a specific monitor failure, delegate to `data-governance` skill
