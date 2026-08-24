---
name: agent-studio-agent-monitor
description: "Monitor and inspect Cortex Agent evaluation run results. Use when user wants to check eval status, view eval scores, see how an eval run performed, inspect per-metric results, or explore eval trace attributes. Triggers: check eval status, monitor eval, eval results, eval scores, how did my eval do, show eval run, what were my eval results, eval run status, view evaluation results, check evaluation, evaluation metrics, eval summary."
parent_skill: agent-studio-agent
---

# Monitor Eval Run

Inspect and explore Cortex Agent evaluation run results using AI Observability events.

> Tool usage: see parent `agent/SKILL.md`. This skill uses `snowflake_sql_execute` exclusively for all queries.

## When to Load

Parent `agent/SKILL.md` routes here when the user wants to check the status or results of an evaluation run — NOT when they want to launch a new evaluation (that's `eval/SKILL.md`).

## Key Functions

| Function | Purpose |
|----------|---------|
| `SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS` | eval_root spans with per-metric scores and run status |
| `SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_LOGS` | Diagnostic log messages (errors, warnings) |

## Workflow

### Step 1: Gather Parameters

**Goal:** Get the agent FQN and run name.

> If `get_page_context` is available, call it silently first. If `metadata.agentName`, `metadata.database`, and `metadata.schema` are present, construct `<AGENT_FQN>` and skip asking.

1. Ask the user for the agent's fully qualified name (`DATABASE.SCHEMA.AGENT_NAME`). If only the name is given:
   ```sql
   SHOW AGENTS LIKE '%<AGENT_NAME>%' IN ACCOUNT;
   ```

2. Confirm `<DATABASE>`, `<SCHEMA>`, `<AGENT_NAME>` with the user.

3. Ask the user for the **run name** they want to inspect. If they don't know it, list recent runs:

   ```sql
   SELECT
       record_attributes:"snow.ai.observability.run.name"::string AS run_name,
       COUNT(*) AS records_evaluated,
       MIN(TIMESTAMP) AS started_at,
       MAX(TIMESTAMP) AS finished_at
   FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
       '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
   ))
   WHERE record_attributes:"ai.observability.span_type"::string = 'eval_root'
   GROUP BY run_name
   ORDER BY finished_at DESC
   LIMIT 10;
   ```

   If the query returns no rows, inform the user that no evaluation runs were found for this agent and stop.

   Present the results and ask the user to pick one. Record as `<RUN_NAME>`.

---

### Step 2: Show Run Status

**Goal:** Give the user an immediate overview of the run's health.

Run this query verbatim:

```sql
SELECT
    COUNT(DISTINCT record_attributes:"ai.observability.eval.target_record_id"::string) AS records_evaluated,
    COUNT(DISTINCT record_attributes:"ai.observability.eval.metric_name"::string) AS metrics_computed,
    MIN(TIMESTAMP) AS first_score_at,
    MAX(TIMESTAMP) AS last_score_at,
    COUNT_IF(record_attributes:"ai.observability.eval_root.status.code"::int != 200) AS failed_scores
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
))
WHERE record_attributes:"ai.observability.span_type"::string = 'eval_root'
  AND record_attributes:"snow.ai.observability.run.name"::string = '<RUN_NAME>';
```

Present to the user:

```
Run Status: <RUN_NAME>
─────────────────────────────────
Records evaluated:  <records_evaluated>
Metrics computed:   <metrics_computed>
First score at:     <first_score_at>
Last score at:      <last_score_at>
Failed scores:      <failed_scores>
```

Also attempt to check the eval task's lifecycle status (retains 7 days only; requires MONITOR EXECUTION ON ACCOUNT or OWNERSHIP/MONITOR on the task):

```sql
SELECT NAME, STATE, ERROR_CODE, ERROR_MESSAGE, SCHEDULED_TIME, COMPLETED_TIME
FROM TABLE(SNOWFLAKE.INFORMATION_SCHEMA.TASK_HISTORY())
WHERE NAME LIKE 'AI_EVALS_%'
  AND QUERY_TEXT ILIKE '%<RUN_NAME>%'
ORDER BY SCHEDULED_TIME DESC
LIMIT 10;
```

> If this query returns an insufficient privileges error, **skip it silently** and proceed with the inference logic below using only `records_evaluated`.

**Determine run state:**

| records_evaluated | task_history result | Inferred state | Action |
|-------------------|---------------------|----------------|--------|
| > 0 | Any, none, or skipped | **SUCCEEDED** | Continue to Step 3 |
| 0 | Has rows with STATE | Use STATE from task_history (EXECUTING, FAILED, etc.) | If FAILED → check logs below. If EXECUTING → tell user it's still running. Stop. |
| 0 | No rows found or skipped (privilege error) | **FAILED** (assumed) | Check logs below |

If task_history returned results, append to the status output:

```
Task state:         <STATE>
Scheduled at:       <SCHEDULED_TIME or "—">
Completed at:       <COMPLETED_TIME or "—">
Error:              <ERROR_MESSAGE or "—">
```

**If state is FAILED or `failed_scores` > 0**, check diagnostic logs:

```sql
SELECT
    TIMESTAMP,
    record:"severity_text"::string AS severity,
    VALUE AS message
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_LOGS(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
))
WHERE record_attributes:"snow.ai.observability.run.name"::string = '<RUN_NAME>'
  AND record:"severity_text"::string IN ('ERROR', 'WARN')
ORDER BY TIMESTAMP ASC
LIMIT 50;
```

- If logs show errors: present the errors to the user — the run likely failed before scoring started (common causes: dataset permissions, missing grants, invalid config). Stop here.
- If no logs found and `records_evaluated` is 0: inform the user the run failed but no diagnostic logs are available (logs may have aged out past 7 days). Stop here.
- If `failed_scores` > 0 but `records_evaluated` > 0: Present the earliest warnings/errors for EACH METRIC alongside the status so the user sees what went wrong on specific records. Then continue to Step 3.

---

### Step 3: Show Eval Summary

**Goal:** Show per-metric aggregate scores.

Run this query verbatim:

```sql
SELECT
    record_attributes:"ai.observability.eval.metric_name"::string AS metric_name,
    record_attributes:"ai.observability.eval.metric_type"::string AS metric_type,
    COUNT(*) AS records_scored,
    ROUND(AVG(record_attributes:"ai.observability.eval_root.score"::float), 4) AS avg_score,
    ROUND(MIN(record_attributes:"ai.observability.eval_root.score"::float), 4) AS min_score,
    ROUND(MAX(record_attributes:"ai.observability.eval_root.score"::float), 4) AS max_score,
    ANY_VALUE(record_attributes:"ai.observability.eval.llm_judge_name"::string) AS judge_model
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
))
WHERE record_attributes:"ai.observability.span_type"::string = 'eval_root'
  AND record_attributes:"snow.ai.observability.run.name"::string = '<RUN_NAME>'
GROUP BY metric_name, metric_type
ORDER BY metric_name;
```

Present:

```
Eval Summary: <RUN_NAME>
Agent: <DATABASE>.<SCHEMA>.<AGENT_NAME>
Judge Model: <judge_model>

| Metric | Type | Records | Avg Score | Min | Max |
|--------|------|---------|-----------|-----|-----|
| ...    | ...  | ...     | ...       | ... | ... |
```

---

### Step 4: Explore Attributes

After presenting the summary, ask the user:

```
Would you like to explore specific attributes from the eval_root spans, or shall I show all available attributes?
```

**If the user wants to see all attributes**, run:

```sql
SELECT DISTINCT f.key, TYPEOF(f.value) AS value_type, ANY_VALUE(f.value::string) AS sample_value
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
)) t,
LATERAL FLATTEN(input => t.RECORD_ATTRIBUTES) f
WHERE t.RECORD_ATTRIBUTES:"ai.observability.span_type"::string = 'eval_root'
  AND t.RECORD_ATTRIBUTES:"snow.ai.observability.run.name"::string = '<RUN_NAME>'
GROUP BY f.key, value_type
ORDER BY f.key;
```

Present all keys with their types and a sample value.

**If the user asks for a specific attribute** (by key name or by describing what they want), map their request to the appropriate `record_attributes` key and run:

```sql
SELECT
    record_attributes:"ai.observability.eval.target_record_id"::string AS record_id,
    record_attributes:"ai.observability.eval.metric_name"::string AS metric_name,
    record_attributes:"<USER_CHOSEN_KEY>"::string AS value
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
))
WHERE record_attributes:"ai.observability.span_type"::string = 'eval_root'
  AND record_attributes:"snow.ai.observability.run.name"::string = '<RUN_NAME>'
ORDER BY record_id, metric_name;
```

If the user's request doesn't map to a known key, show all attributes first (query above) and ask them to pick from the list.

---

## Iteration

After showing attributes, ask if the user wants to:
- Explore another attribute
- Inspect a different run (return to Step 1.3)
- Done

---

## Integration

- **`eval/SKILL.md`** — launches evaluations; after deploying, users come here to monitor results.
- **`dataset/SKILL.md`** — if the user wants to improve scores, they may need to re-author their dataset.
