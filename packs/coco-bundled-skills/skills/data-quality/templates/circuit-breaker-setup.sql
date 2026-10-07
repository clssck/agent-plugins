-- Circuit Breaker Setup
-- Creates a Snowflake ALERT that monitors expectation status for an upstream table
-- and suspends a downstream TASK or DYNAMIC TABLE when any expectation is violated.
-- Trigger is based on expectations set on the table (expectation_violated), not ad-hoc thresholds.
--
-- Placeholders to replace:
--   <database>          — database containing upstream table and downstream object
--   <schema>            — schema for the ALERT and protected objects
--   <upstream_table>    — table with DMFs + expectations attached (the quality gate)
--   <downstream_object> — TASK or DYNAMIC TABLE name to suspend on violation
--   <object_type>       — TASK or DYNAMIC TABLE
--   <alert_name>        — name for the ALERT (suggestion: <table>_CIRCUIT_BREAKER)
--   <warehouse>         — warehouse for the ALERT to use
--   <frequency_minutes> — how often the alert checks (e.g., 15, 60)
--
-- Optional: add "AND metric_name ILIKE '%<metric_name>%'" in the WHERE clause to watch only specific DMF(s).

-- Create the circuit breaker ALERT (trigger: any expectation violated on upstream table)
CREATE OR REPLACE ALERT <database>.<schema>.<alert_name>
  WAREHOUSE = <warehouse>
  SCHEDULE = 'USING CRON */<frequency_minutes> * * * * UTC'
  IF (
    EXISTS (
      SELECT 1
      FROM TABLE(SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_EXPECTATION_STATUS(
          REF_ENTITY_NAME => '<database>.<schema>.<upstream_table>',
          REF_ENTITY_DOMAIN => 'TABLE'
      ))
      WHERE expectation_violated = TRUE
        AND measurement_time >= DATEADD('minute', -<frequency_minutes>, CURRENT_TIMESTAMP())
    )
  )
  THEN
    -- Action: Suspend the downstream object
    CALL SYSTEM$EXECUTE_IMMEDIATE('
      ALTER <object_type> <database>.<schema>.<downstream_object> SUSPEND
    ');

-- Activate the alert immediately after creation
ALTER ALERT <database>.<schema>.<alert_name> RESUME;

/*
After creation, verify the alert is active:
  SHOW ALERTS LIKE '<alert_name>' IN SCHEMA <database>.<schema>;

To check alert execution history:
  SELECT *
  FROM TABLE(INFORMATION_SCHEMA.ALERT_HISTORY(
      SCHEDULED_TIME_RANGE_START => DATEADD('day', -7, CURRENT_TIMESTAMP())
  ))
  WHERE name = '<alert_name>'
  ORDER BY SCHEDULED_TIME DESC
  LIMIT 20;

To resume the downstream object after fixing the upstream quality issue:
  ALTER <object_type> <database>.<schema>.<downstream_object> RESUME;

To remove the circuit breaker:
  DROP ALERT <database>.<schema>.<alert_name>;

Notes:
  - The ALERT fires if any expectation on <upstream_table> has expectation_violated = TRUE
    in the last <frequency_minutes> minutes. Expectations must be set on the table (ADD EXPECTATION
    on the DMF association). No ad-hoc threshold — use expectations as the source of truth.
  - Requires EXECUTE ALERT privilege on the warehouse.
  - Requires OPERATE privilege on the downstream TASK or DYNAMIC TABLE.
  - The SYSTEM$EXECUTE_IMMEDIATE call runs the ALTER in a separate context;
    ensure the ALERT's owner role has OPERATE on the downstream object.
  - For multiple downstream objects, add additional CALL SYSTEM$EXECUTE_IMMEDIATE
    statements in the THEN block.

Limitation (async):
  This circuit breaker is asynchronous: the ALERT runs on a schedule, so the downstream
  TASK or DYNAMIC TABLE may run one more time before the suspend takes effect. For synchronous
  blocking of dynamic table refreshes, Snowflake does not currently offer a native "block
  refresh until expectations pass" option; alternatives include running quality checks inside
  the pipeline (e.g. in a task step before refresh) or using manual gates.
*/
