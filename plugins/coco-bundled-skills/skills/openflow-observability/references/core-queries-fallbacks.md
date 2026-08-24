---
name: openflow-observability-core-queries-fallbacks
description: Drill-down and fallback SQL queries for Openflow event table diagnostics. Load on demand after the primary batch in core-queries.md identifies failing loggers or fragmented error groupings.
---

# Core Queries -- Fallbacks & Drill-downs

Secondary queries used only after the primary batch in `references/core-queries.md` has identified something to drill into. Load this file on demand; it is **not** part of startup.

**When to load:**
- **Error Pattern Summary returned many single-occurrence rows sharing a prefix** -> use *Normalized Error Pattern Summary*.
- **Multiple failing loggers surfaced and recovery guidance is about to be written** -> use *Throwable Cause Chain (Top Loggers)*.

## Normalized Error Pattern Summary

**Purpose:** Re-group errors when the raw message embeds unique identifiers such as `ClientConnectionId`, request IDs, or UUIDs.

**When to use:** Error Pattern Summary returns many single-occurrence rows that clearly share the same logger and message prefix.


```sql
WITH normalized_errors AS (
  SELECT
    COALESCE(
      record_attributes:"LoggerName"::STRING,
      TRY_PARSE_JSON(value):"loggerName"::STRING
    ) AS logger_name,
    REGEXP_REPLACE(
      REGEXP_REPLACE(
        COALESCE(
          TRY_PARSE_JSON(value):"throwable":"message"::STRING,
          TRY_PARSE_JSON(value):"formattedMessage"::STRING,
          TRY_PARSE_JSON(value):"message"::STRING,
          ''
        ),
        'ClientConnectionId:[^, )]+',
        'ClientConnectionId:<id>'
      ),
      '[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,36}',
      '<id>'
    ) AS normalized_error,
    timestamp
  FROM {event_table}
  WHERE record_type = 'LOG'
    AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
    AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
    AND COALESCE(RECORD_ATTRIBUTES:"severity_text"::STRING, RECORD_ATTRIBUTES:"LogLevel"::STRING, TRY_PARSE_JSON(value):"level"::STRING) IN ('WARN', 'ERROR')
    AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
)
SELECT
  logger_name,
  normalized_error,
  COUNT(*) AS occurrence_count,
  MIN(timestamp) AS first_seen,
  MAX(timestamp) AS last_seen
FROM normalized_errors
GROUP BY 1, 2
ORDER BY occurrence_count DESC
LIMIT 50;
```

Use this query only when the raw grouping is obviously fragmented by embedded identifiers.

## Throwable Cause Chain (Top Loggers)

**Purpose:** Drill into the `throwable` -> `cause` -> `cause.cause` chain for the top N failing loggers in one query. Replaces the pattern of running one cause-chain query per failing logger (for example, a separate drill-down for `CaptureChangePostgreSQL` and another for `ListTableNames` when both share a root PSQLException).

**When to use:** After the primary parallel batch identifies multiple failing loggers and you need the full root-cause chain before writing guidance. Do **not** run this in the primary parallel batch -- it adds no signal when no errors have been identified yet.

```sql
WITH top_loggers AS (
  SELECT
    COALESCE(record_attributes:"LoggerName"::STRING, TRY_PARSE_JSON(value):"loggerName"::STRING) AS logger
  FROM {event_table}
  WHERE record_type = 'LOG'
    AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
    AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
    AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
    AND COALESCE(
      record_attributes:"severity_text"::STRING,
      record_attributes:"LogLevel"::STRING,
      TRY_PARSE_JSON(value):"level"::STRING
    ) IN ('WARN', 'ERROR')
  GROUP BY 1
  ORDER BY COUNT(*) DESC
  LIMIT 5
)
SELECT
  timestamp,
  COALESCE(record_attributes:"LoggerName"::STRING, TRY_PARSE_JSON(value):"loggerName"::STRING)         AS logger,
  TRY_PARSE_JSON(value):"throwable":"message"::STRING                                                  AS throwable_message,
  TRY_PARSE_JSON(value):"throwable":"cause":"message"::STRING                                          AS cause_message,
  TRY_PARSE_JSON(value):"throwable":"cause":"cause":"message"::STRING                                  AS root_cause_message,
  TRY_PARSE_JSON(value):"formattedMessage"::STRING                                                     AS formatted_message
FROM {event_table}
WHERE record_type = 'LOG'
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND COALESCE(record_attributes:"LoggerName"::STRING, TRY_PARSE_JSON(value):"loggerName"::STRING)
      IN (SELECT logger FROM top_loggers)
  AND COALESCE(
    record_attributes:"severity_text"::STRING,
    record_attributes:"LogLevel"::STRING,
    TRY_PARSE_JSON(value):"level"::STRING
  ) IN ('WARN', 'ERROR')
QUALIFY ROW_NUMBER() OVER (PARTITION BY logger ORDER BY timestamp DESC) <= 3
ORDER BY logger, timestamp DESC;
```

**Interpretation:**
- Read `root_cause_message` first -- it names the underlying failure when the top-level message is generic (for example top-level `Failed to start replication stream`, root cause `FATAL: database "hammerdb_load" does not exist`).
- Sibling loggers that share a `root_cause_message` indicate a single upstream fault manifesting in multiple processors. Do not treat them as independent issues.
- If `root_cause_message` is NULL but `cause_message` is set, the exception chain is only one level deep.
- If all three message columns are NULL, the error is not carrying a throwable -- fall back to `formatted_message` or run **Generic Raw Log Fallback** in `references/core-queries.md` on the affected logger.
- Tune the `LIMIT 5` on `top_loggers` if the primary batch surfaced more than 5 distinct failing loggers worth investigating.
