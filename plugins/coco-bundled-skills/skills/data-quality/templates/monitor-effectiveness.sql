-- Monitor Effectiveness Analysis
-- Identifies noisy monitors (firing constantly), silent monitors (never firing),
-- and suspended DMFs. Used for DQ operations meta-observability.
--
-- Replace <database> and <schema> with target database and schema names.
--
-- Primary data source for violations: SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_EXPECTATION_STATUS (view)
-- Use expectation_violated for canonical pass/fail; view has measurement_time for time-window aggregation.
-- See: https://docs.snowflake.com/en/sql-reference/local/data_quality_monitoring_expectation_status
-- Credits/execution counts: SNOWFLAKE.ACCOUNT_USAGE.DATA_QUALITY_MONITORING_USAGE_HISTORY (45min-3hr latency).

-- Step 1: Violation and run counts from expectation status view (last 30 days)
WITH expectation_history AS (
    SELECT
        table_name,
        metric_name,
        COUNT(*) AS total_runs_30d,
        SUM(CASE WHEN expectation_violated = TRUE THEN 1 ELSE 0 END) AS violation_runs_30d,
        ROUND(
            SUM(CASE WHEN expectation_violated = TRUE THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0),
            1
        ) AS violation_rate_pct,
        MIN(measurement_time) AS first_run,
        MAX(measurement_time) AS last_run
    FROM SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_EXPECTATION_STATUS
    WHERE table_database = '<database>'
      AND table_schema = '<schema>'
      AND measurement_time >= DATEADD('day', -30, CURRENT_TIMESTAMP())
    GROUP BY table_name, metric_name
),

-- Step 2: Credits from ACCOUNT_USAGE (optional; has latency)
usage_credits AS (
    SELECT
        SPLIT_PART(REF_ENTITY_NAME, '.', 3) AS table_name,
        METRIC_NAME AS metric_name,
        SUM(CREDITS_USED) AS total_credits_30d
    FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_QUALITY_MONITORING_USAGE_HISTORY
    WHERE MEASUREMENT_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
      AND REF_ENTITY_NAME ILIKE '<database>.<schema>.%'
    GROUP BY 1, 2
),

-- Step 3: Current schedule status from INFORMATION_SCHEMA
schedule_status AS (
    SELECT DISTINCT
        t.TABLE_NAME,
        r.METRIC_NAME,
        r.SCHEDULE,
        r.SCHEDULE_STATUS
    FROM <database>.INFORMATION_SCHEMA.TABLES t,
    LATERAL (
        SELECT *
        FROM TABLE(INFORMATION_SCHEMA.DATA_METRIC_FUNCTION_REFERENCES(
            REF_ENTITY_NAME => '<database>.<schema>.' || t.TABLE_NAME,
            REF_ENTITY_DOMAIN => 'TABLE'
        ))
    ) r
    WHERE t.TABLE_SCHEMA = '<schema>'
      AND t.TABLE_TYPE = 'BASE TABLE'
)

-- Final: Effectiveness classification using expectation status view for violations
SELECT
    COALESCE(h.table_name, s.TABLE_NAME) AS table_name,
    COALESCE(h.metric_name, s.METRIC_NAME) AS metric_name,
    s.SCHEDULE,
    s.SCHEDULE_STATUS,
    COALESCE(h.total_runs_30d, 0) AS executions_30d,
    COALESCE(h.violation_runs_30d, 0) AS violations_30d,
    COALESCE(h.violation_rate_pct, 0) AS violation_rate_pct,
    ROUND(COALESCE(u.total_credits_30d, 0), 6) AS credits_30d,
    h.last_run,
    -- Effectiveness classification (based on expectation_violated from view)
    CASE
        WHEN s.SCHEDULE_STATUS = 'SUSPENDED'
            THEN 'SUSPENDED — DMF is attached but not running'
        WHEN COALESCE(h.total_runs_30d, 0) = 0
            THEN 'NO_HISTORY — no expectation runs in last 30 days (or view empty for this schema)'
        WHEN h.violation_rate_pct > 80
            THEN 'NOISY — firing > 80% of runs; threshold may be too strict or data has a chronic issue'
        WHEN h.violation_runs_30d = 0 AND h.total_runs_30d >= 5
            THEN 'SILENT — 0 violations in last 30 days; data may be clean or threshold too loose'
        WHEN h.violation_rate_pct BETWEEN 5 AND 80
            THEN 'HEALTHY — occasional violations within normal range'
        WHEN h.violation_rate_pct <= 5
            THEN 'CLEAN — very few violations; monitor is effective'
        ELSE 'UNKNOWN'
    END AS effectiveness_status,
    -- Recommendation
    CASE
        WHEN s.SCHEDULE_STATUS = 'SUSPENDED'
            THEN 'Resume: ALTER TABLE <database>.<schema>.<table> SET DATA_METRIC_SCHEDULE = ''TRIGGER_ON_CHANGES'''
        WHEN h.violation_rate_pct > 80
            THEN 'Tune threshold (expectations-management) or investigate chronic issue (root-cause-analysis)'
        WHEN h.violation_runs_30d = 0 AND h.total_runs_30d >= 10
            THEN 'Verify threshold is meaningful; consider if this monitor adds value'
        ELSE 'No action needed'
    END AS recommendation
FROM schedule_status s
LEFT JOIN expectation_history h
    ON UPPER(s.TABLE_NAME) = UPPER(h.table_name)
    AND s.METRIC_NAME = h.metric_name
LEFT JOIN usage_credits u
    ON UPPER(s.TABLE_NAME) = UPPER(u.table_name)
    AND s.METRIC_NAME = u.metric_name
ORDER BY
    CASE
        WHEN s.SCHEDULE_STATUS = 'SUSPENDED' THEN 1
        WHEN COALESCE(h.violation_rate_pct, 0) > 80 THEN 2
        WHEN h.violation_runs_30d = 0 AND COALESCE(h.total_runs_30d, 0) >= 5 THEN 3
        ELSE 4
    END,
    COALESCE(u.total_credits_30d, 0) DESC;

/*
Columns returned:
  TABLE_NAME             — table name
  METRIC_NAME            — DMF metric name
  SCHEDULE               — DMF schedule expression
  SCHEDULE_STATUS        — STARTED | SUSPENDED
  EXECUTIONS_30D         — expectation runs in last 30 days (from expectation status view)
  VIOLATIONS_30D         — runs where expectation_violated = TRUE
  VIOLATION_RATE_PCT     — percentage of runs that produced a violation
  CREDITS_30D            — credits consumed (from ACCOUNT_USAGE; has latency)
  LAST_RUN               — timestamp of last expectation run
  EFFECTIVENESS_STATUS   — SUSPENDED | NOISY | SILENT | HEALTHY | CLEAN | NO_HISTORY
  RECOMMENDATION         — actionable next step

Note: Violation counts and rates are derived from DATA_QUALITY_MONITORING_EXPECTATION_STATUS
(expectation_violated). Credits come from DATA_QUALITY_MONITORING_USAGE_HISTORY (45min-3hr latency).
*/
