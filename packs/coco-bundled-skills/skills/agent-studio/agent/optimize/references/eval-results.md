# Eval Results (Optimize)

Used after every `eval-deploy` in the optimize loop. Substitute `<DATABASE>`, `<SCHEMA>`, `<AGENT_NAME>`, `<RUN_NAME>`, `<BASE_NAME>`, `<SOURCE_TABLE>`.

Do not load `monitor/SKILL.md` from optimize — it stops for exploratory prompts.

## Poll until COMPLETED

```sql
USE DATABASE <DATABASE>;
USE SCHEMA <SCHEMA>;

CALL EXECUTE_AI_EVALUATION(
  'STATUS',
  OBJECT_CONSTRUCT('run_name', '<RUN_NAME>'),
  '@<DATABASE>.<SCHEMA>.EVAL_CONFIG_STAGE/cortex_project/<BASE_NAME>.resolved.yaml'
);
```

| Status | Action |
|--------|--------|
| `INVOCATION_IN_PROGRESS` / `COMPUTATION_IN_PROGRESS` | Wait 30–60s and poll again |
| `COMPLETED` | Continue to scores |
| `FAILED` | Read `STATUS_DETAILS`. Privilege language → `../../permission/SKILL.md`. Otherwise present the error and stop |

`<BASE_NAME>` is the `eval-write --base-name` used for that run. If unknown, list recent runs:

```sql
SELECT
    record_attributes:"snow.ai.observability.run.name"::string AS run_name,
    COUNT(*) AS records_evaluated,
    MAX(TIMESTAMP) AS finished_at
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
))
WHERE record_attributes:"ai.observability.span_type"::string = 'eval_root'
GROUP BY run_name
ORDER BY finished_at DESC
LIMIT 10;
```

A run is ready to score when `records_evaluated > 0` for that `run_name`.

## Aggregate scores

```sql
SELECT
    record_attributes:"ai.observability.eval.metric_name"::string AS metric_name,
    COUNT(*) AS records_scored,
    ROUND(AVG(record_attributes:"ai.observability.eval_root.score"::float), 4) AS avg_score,
    COUNT_IF(record_attributes:"ai.observability.eval_root.score"::float >= 0.80) AS pass_n,
    COUNT_IF(record_attributes:"ai.observability.eval_root.score"::float >= 0.40
         AND record_attributes:"ai.observability.eval_root.score"::float < 0.80) AS partial_n,
    COUNT_IF(record_attributes:"ai.observability.eval_root.score"::float < 0.40) AS fail_n
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
))
WHERE record_attributes:"ai.observability.span_type"::string = 'eval_root'
  AND record_attributes:"snow.ai.observability.run.name"::string = '<RUN_NAME>'
GROUP BY metric_name
ORDER BY metric_name;
```

Present mean `answer_correctness` as the headline accuracy, with Pass / Partial / Fail counts from that metric.

## Per-record scores

```sql
SELECT
    record_attributes:"ai.observability.eval.target_record_id"::string AS record_id,
    record_attributes:"ai.observability.eval.metric_name"::string AS metric_name,
    record_attributes:"ai.observability.eval_root.score"::float AS score
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
))
WHERE record_attributes:"ai.observability.span_type"::string = 'eval_root'
  AND record_attributes:"snow.ai.observability.run.name"::string = '<RUN_NAME>'
ORDER BY record_id, metric_name;
```

Join to the dataset source table for the question and expected answer (column names may vary; `INPUT_QUERY` + `GROUND_TRUTH` are the native shape):

```sql
SELECT
    INPUT_QUERY,
    GROUND_TRUTH:ground_truth_output::string AS expected_answer,
    GROUND_TRUTH:ground_truth_invocations AS expected_tools
FROM <SOURCE_TABLE>;
```

Match rows by question text when `record_id` does not line up with a table key. If the source table is unknown, list questions from `SHOW DATASETS` / the registered dataset and reason over both result sets.

## Comparison table

```
Evaluation comparison

                Mean AC   Pass / Partial / Fail
Baseline        0.31      4 / 2 / 7
After update    0.77      10 / 1 / 2
Generalized     0.84      12 / 1 / 0

Improvements: Q1, Q4, Q5, Q7, Q9, Q10
Regressions:  none
Still failing: Q2, Q8
```

A **regression** is a question that was Pass (`>= 0.80`) on an earlier run and is Fail (`< 0.40`) on the later run. Call those out explicitly.

## Snowsight URL

```sql
SELECT LOWER(CURRENT_ORGANIZATION_NAME()), LOWER(CURRENT_ACCOUNT_NAME());
```

```
https://app.snowflake.com/<org>/<account>/#/agents/database/<DATABASE>/schema/<SCHEMA>/agent/<AGENT_NAME>/evaluations/<RUN_NAME>/records
```

Use an underscore in the account segment (`sfdevrel_enterprise`, not `sfdevrel-enterprise`).
