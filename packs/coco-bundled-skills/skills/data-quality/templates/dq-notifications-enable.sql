-- Data Quality Notifications (native)
-- Docs: https://docs.snowflake.com/en/user-guide/data-quality-notifications
--
-- Prefer this over CREATE ALERT health-% polling (see schema-sla-alert.sql).
-- Notifications fire on expectation violation OR anomaly detection.
--
-- WRITE statements below are examples for the agent to customize AFTER explicit
-- user approval. The status-check query at the bottom is READ-only and runnable.
--
-- Placeholders:
--   <database>           Target database (notifications are DB-scoped)
--   <schema>             Schema of an object to verify / opt out
--   <table_or_view>      Object name for status check / opt-out
--   <email>              Verified recipient email
--   <integration_name>   Notification integration name
--   <role>               Database owner role receiving grants
--   <cooldown_hours>     Min hours between notifications (e.g. 4)
--   <metric_fqn>         e.g. SNOWFLAKE.CORE.NULL_COUNT
--   <column>             Column argument for column-level DMFs
--   <webhook_secret_fqn> Fully-qualified secret for WEBHOOK integrations
--   <slack_secret_string> Slack webhook path secret string

-- =============================================================================
-- 1) Optional: CREATE NOTIFICATION INTEGRATION (EMAIL)
-- =============================================================================
-- CREATE NOTIFICATION INTEGRATION <integration_name>
--   TYPE = EMAIL
--   ENABLED = TRUE
--   ALLOWED_RECIPIENTS = ('<email>');

-- =============================================================================
-- 1b) Optional: CREATE WEBHOOK integration (e.g. Slack)
-- =============================================================================
-- CREATE OR REPLACE SECRET <webhook_secret_fqn>
--   TYPE = GENERIC_STRING
--   SECRET_STRING = '<slack_secret_string>';
--
-- CREATE OR REPLACE NOTIFICATION INTEGRATION <integration_name>
--   TYPE = WEBHOOK
--   ENABLED = TRUE
--   WEBHOOK_URL = 'https://hooks.slack.com/services/SNOWFLAKE_WEBHOOK_SECRET'
--   WEBHOOK_SECRET = <webhook_secret_fqn>
--   WEBHOOK_BODY_TEMPLATE = '{"text": "SNOWFLAKE_WEBHOOK_MESSAGE"}'
--   WEBHOOK_HEADERS = ('Content-Type'='application/json');

-- =============================================================================
-- 2) Grants (database owner must have these)
-- =============================================================================
-- GRANT MANAGE DATA QUALITY ON ACCOUNT TO ROLE <role>;
-- GRANT USAGE ON INTEGRATION <integration_name> TO ROLE <role>;

-- =============================================================================
-- 3) Enable notifications on the database (YAML via dollar-quoted string)
-- =============================================================================
-- Email recipients only (no integration):
-- ALTER DATABASE <database> SET DATA_QUALITY_MONITORING_SETTINGS =
--   $$
--   notification:
--     enabled: TRUE
--     email_recipients: [ '<email>' ]
--     cooldown_hours: <cooldown_hours>
--     metadata_included: TRUE
--   $$;
--
-- Integration + optional email recipients:
-- ALTER DATABASE <database> SET DATA_QUALITY_MONITORING_SETTINGS =
--   $$
--   notification:
--     enabled: TRUE
--     email_recipients: [ '<email>' ]
--     integrations:
--       - <integration_name>
--     cooldown_hours: <cooldown_hours>
--     metadata_included: TRUE
--   $$;

-- =============================================================================
-- 4) Optional: opt out a specific object ↔ DMF association
-- =============================================================================
-- ALTER TABLE <database>.<schema>.<table_or_view>
--   MODIFY DATA METRIC FUNCTION <metric_fqn> ON (<column>)
--     SET DATA_QUALITY_NOTIFICATION = FALSE;
--
-- ALTER VIEW <database>.<schema>.<table_or_view>
--   MODIFY DATA METRIC FUNCTION SNOWFLAKE.CORE.BLANK_COUNT ON (<column>)
--     SET DATA_QUALITY_NOTIFICATION = FALSE;

-- =============================================================================
-- 5) Status check (READ-only — safe to run)
-- =============================================================================
-- data_quality_notification_status indicates whether notifications are on
-- for each association after database-level enable / per-association opt-out.
SELECT
  REF_ENTITY_NAME,
  METRIC_DATABASE,
  METRIC_SCHEMA,
  METRIC_NAME,
  DATA_QUALITY_NOTIFICATION_STATUS
FROM TABLE(<database>.INFORMATION_SCHEMA.DATA_METRIC_FUNCTION_REFERENCES(
  REF_ENTITY_NAME => '<database>.<schema>.<table_or_view>',
  REF_ENTITY_DOMAIN => 'TABLE'
));
