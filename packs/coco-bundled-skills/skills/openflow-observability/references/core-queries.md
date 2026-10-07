---
name: openflow-observability-core-queries
description: Core triage SQL queries for Openflow event table diagnostics. Always loaded.
---

# Core Queries

Essential SQL queries for triage and investigation. For resource and operational queries (CPU, memory, disk, processor status, FlowFiles, connectors, restarts), **Load** `references/core-queries-resource.md`.

## Parameter Substitution

Before running any query, substitute all variables with actual values. See `SKILL.md` Structured Input for the variable inventory and substitution rule. See `references/core-guidelines.md` for namespace derivation and time filtering patterns.

---
## Namespace + Shape Probe (Primary)

**Purpose:** Single round-trip that answers **both** "does this namespace have recent logs?" and "which field-access pattern does this event table use?"

**When to use:** First query of any routed investigation. Fire it in parallel with Recent Error Logs (and, for CDC connectors, CDC Table Replication State). Replaces separate Namespace Validation and schema-probe calls on the common path. Fall back to the [Namespace Validation](../SKILL.md#namespace-validation) broadening query only when this probe returns zero rows despite a valid `{namespace}` input.

**MAY be skipped** when the page-context fast path applies. In that case namespace validity and `{field_pattern}` = `record_attributes` are inferred from the catalog without a SQL round-trip (non-empty `activeContent` proves the dashboard parsed structured fields, so the table is not in `raw_text` mode). The broadening query in [Namespace Validation](../SKILL.md#namespace-validation) still applies if a subsequent query unexpectedly returns zero rows. See the full [page-context fast path skip conditions](../SKILL.md#discovery-sequence-high-level-troubleshoot) in `SKILL.md` Discovery Sequence step 1 for the authoritative criteria (payload present, `activeContent` non-empty, window unchanged from page-context load, `{namespace}` from page context).

```sql
SELECT
  timestamp,
  record_attributes:"severity_text"::STRING       AS ra_severity,
  record_attributes:"LogLevel"::STRING            AS ra_log_level,
  TRY_PARSE_JSON(value):"level"::STRING           AS pj_severity,
  record_attributes:"LoggerName"::STRING          AS ra_logger,
  TRY_PARSE_JSON(value):"loggerName"::STRING      AS pj_logger,
  LEFT(value, 250)                                AS value_sample
FROM {event_table}
WHERE record_type = 'LOG'
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
ORDER BY timestamp DESC
LIMIT 20;
```

**Interpretation:**

| Result | `{namespace}` valid? | `{field_pattern}` |
| --- | --- | --- |
| Zero rows | **Unknown** -- run the [Namespace Validation](../SKILL.md#namespace-validation) broadening query (`LIKE 'runtime-%'`). Do not proceed with other diagnostic queries until namespace is confirmed. | n/a |
| Rows present; `ra_severity` / `ra_logger` populated | Yes | `record_attributes` |
| Rows present; only `pj_severity` / `pj_logger` populated | Yes | `parsed_json` |
| Rows present; both NULL (only `value_sample` populated) | Yes | `raw_text` -- skip standard filtered queries, use [Generic Raw Log Fallback](#generic-raw-log-fallback) |

Downstream queries use COALESCE over both patterns, so `{field_pattern}` is informational for the agent (log in session state) rather than load-bearing for the standard queries.

---
## Event Time Bounds Check

**Purpose:** Find the actual min/max timestamps for recent data before broadening the search window.

**When to use:** Parsed queries return very few rows or zero rows and you need to know whether logs are outside the initial 2-hour window.

```sql
-- When time_window is provided:
SELECT
  MIN(timestamp) AS first_log_at,
  MAX(timestamp) AS last_log_at,
  COUNT(*) AS log_row_count
FROM {event_table}
WHERE record_type = 'LOG'
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND timestamp BETWEEN '{start_time}' AND '{end_time}';

-- When time_window is not provided (hours_back fallback, 2-day broad window):
SELECT
  MIN(timestamp) AS first_log_at,
  MAX(timestamp) AS last_log_at,
  COUNT(*) AS log_row_count
FROM {event_table}
WHERE record_type = 'LOG'
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND timestamp >= DATEADD(day, -2, CURRENT_TIMESTAMP());
```

**Interpretation:**
- If `last_log_at` is recent but error queries returned zero rows, the issue is query shape/schema, not data freshness.
- If `last_log_at` is older than expected, tell the customer the incident may have aged out of the current window before expanding repeated query scans.
- If `log_row_count` is zero, do not expand the time window. Verify the namespace with [Namespace Validation](../SKILL.md#namespace-validation) and run Deployment Info (in `references/core-queries-resource.md`) to confirm the event table is configured for this runtime.
- If a specific `time_window` was provided, compare `last_log_at` to that window, not to `CURRENT_TIMESTAMP`.
- Use this before broadening 2h -> 6h -> 24h in general runtime investigations.

---

## Recent Error Logs

**Purpose:** First-pass triage. Shows recent ERROR and WARN logs from the routed runtime, excluding noisy loggers.

**When to use:** Start of any investigation, or when error signals are ambiguous. Fire in parallel with the [Namespace + Shape Probe](#namespace--shape-probe-primary) in the primary batch -- COALESCE over both field patterns means this query does not need to wait for a shape decision.

**Page-context skip:** When the page-context fast path applies, you MAY skip this query and route from the catalog (same `logger_name` + `error_message` dedup grouping). The [Tiered Confirmatory-Query Rule](../SKILL.md#tiered-confirmatory-query-rule) still gates recovery guidance, root-cause claims, and forward-looking statements. See the full [page-context fast path skip conditions](../SKILL.md#discovery-sequence-high-level-troubleshoot) in `SKILL.md` Discovery Sequence step 1 for the authoritative criteria.

**Scope rule:** Assumes a routed runtime or connector investigation. For deployment-wide or unknown-runtime discovery, replace the exact namespace filter with `LIKE 'runtime-%'`.

**Zero-row interpretation:** Do not assume the runtime is healthy -- run [Generic Raw Log Fallback](#generic-raw-log-fallback).

```sql
WITH openflow_parsed_logs AS (
  SELECT *, TRY_PARSE_JSON(value) AS parsed_log
  FROM {event_table}
  WHERE record_type = 'LOG'
    AND resource_attributes:"k8s.container.name"::STRING NOT ILIKE '%-gateway'
    AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
    AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
    AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
)
SELECT
  timestamp,
  COALESCE(
    parsed_log:"throwable":"message"::STRING,
    parsed_log:"message"::STRING
  ) AS error_message,
  COALESCE(
    record_attributes:"LoggerName"::STRING,
    parsed_log:"loggerName"::STRING
  ) AS logger,
  COALESCE(
    record_attributes:"severity_text"::STRING,
    record_attributes:"LogLevel"::STRING,
    parsed_log:"level"::STRING
  ) AS log_level,
  COALESCE(
    parsed_log:"formattedMessage"::STRING,
    parsed_log:"message"::STRING,
    LEFT(value, 500)
  ) AS message
FROM openflow_parsed_logs
WHERE COALESCE(
    record_attributes:"LoggerName"::STRING,
    parsed_log:"loggerName"::STRING,
    ''
  ) NOT ILIKE 'org.apache.nifi.web.security.%'
  AND COALESCE(
    record_attributes:"LoggerName"::STRING,
    parsed_log:"loggerName"::STRING,
    ''
  ) NOT ILIKE 'org.apache.nifi.web.server.%'
  AND COALESCE(
    record_attributes:"LoggerName"::STRING,
    parsed_log:"loggerName"::STRING,
    ''
  ) NOT ILIKE 'org.apache.nifi.cluster.%'
  AND COALESCE(
    record_attributes:"LoggerName"::STRING,
    parsed_log:"loggerName"::STRING,
    ''
  ) NOT ILIKE 'org.apache.nifi.controller.scheduling.%'
  AND COALESCE(
    record_attributes:"LoggerName"::STRING,
    parsed_log:"loggerName"::STRING,
    ''
  ) NOT ILIKE 'org.apache.nifi.controller.repository.%'
  AND COALESCE(
    record_attributes:"LoggerName"::STRING,
    parsed_log:"loggerName"::STRING,
    ''
  ) NOT ILIKE 'org.apache.nifi.controller.leader.%'
  AND COALESCE(
    record_attributes:"LoggerName"::STRING,
    parsed_log:"loggerName"::STRING,
    ''
  ) NOT ILIKE 'org.apache.nifi.controller.tasks.%'
  AND COALESCE(
    record_attributes:"severity_text"::STRING,
    record_attributes:"LogLevel"::STRING,
    parsed_log:"level"::STRING
  ) IN ('WARN', 'ERROR')
ORDER BY timestamp DESC
LIMIT 100;
```

**Interpretation:**
- Focus on `error_message` and `message` columns for root cause
- `logger` identifies which component produced the error
- Loggers starting with `com.snowflake.openflow.runtime.processors` are connector-specific
- Rows where logger cannot be determined from either `record_attributes` or parsed `value` will pass all logger exclusion filters and appear in results with a NULL `logger` column. Review `logger` for NULL before drawing conclusions about the error source.

## Per-Connector Scoping (Multi-Connector Runtimes)

**Purpose:** Isolate one connector's errors when several connectors share a single runtime (namespace). Namespace scoping alone (`k8s.namespace.name`) returns every connector on the runtime; this narrows to one connector's process-group subtree.

**When to use:** A multi-connector runtime where Recent Error Logs returns errors from more than one connector and you need to attribute them to the reported connector. For single-connector runtimes, skip this -- the namespace filter is already connector-scoped.

**Mechanism:** Logs carry the connector's process-group path. On LOG records it is in the parsed `value` MDC (`parsed_log:"mdc":"processGroupNamePath"`); on METRIC records it is a record attribute (`record_attributes:"processGroupNamePath"`). COALESCE over both, exactly as the logger fields are handled. Do **not** assume a fixed path depth or `SPLIT_PART` index -- the connector's nesting depth differs between deployment generations. Discover the actual path from the data, then filter by prefix.

**Step 1 -- Discover the connector paths present in the namespace:**

```sql
SELECT DISTINCT
  COALESCE(
    TRY_PARSE_JSON(value):"mdc":"processGroupNamePath"::STRING,
    record_attributes:"processGroupNamePath"::STRING
  ) AS process_group_name_path
FROM {event_table}
WHERE record_type = 'LOG'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND COALESCE(
    TRY_PARSE_JSON(value):"mdc":"processGroupNamePath"::STRING,
    record_attributes:"processGroupNamePath"::STRING
  ) IS NOT NULL
ORDER BY 1;
```

**Step 2 -- Pick the target connector's path.** Match the reported `{connector_name}` (or `connector_type`) against the returned paths. If the mapping is ambiguous, present the distinct paths and ask the customer which one is the affected connector. Set `{connector_path}` to the chosen value (or a stable prefix of it).

**Step 3 -- Re-run the scoped query.** Add this predicate to [Recent Error Logs](#recent-error-logs) (inside the CTE) or [Error Pattern Summary](#error-pattern-summary):

```sql
  AND COALESCE(
    TRY_PARSE_JSON(value):"mdc":"processGroupNamePath"::STRING,
    record_attributes:"processGroupNamePath"::STRING,
    ''
  ) ILIKE '{connector_path}%'
```

**Fail-soft:** If Step 1 returns no rows (the field is absent for this deployment), this scoping is unavailable -- fall back to the logger-family / message / connector PG ID scoping described in the [Runtime Scoping Rule](../SKILL.md#runtime-scoping-rule). Never invent a `{connector_path}`; only filter on a value returned by Step 1.

## Generic Raw Log Fallback

**Purpose:** Inspect raw `value` directly when parsed fields are sparse, malformed, or unavailable.

**When to use:** Namespace + Shape Probe shows parsed fields are mostly NULL (`raw_text` pattern), first-pass discovery queries return zero rows despite clear symptoms, or you need raw event text before choosing a connector-specific fallback.

**Scope rule:** Apply the routed runtime namespace filter unless you have not yet identified the target runtime namespace (omit the namespace filter or use `LIKE 'runtime-%'` in that case).


```sql
SELECT
  timestamp,
  COALESCE(
    record_attributes:"LoggerName"::STRING,
    TRY_PARSE_JSON(value):"loggerName"::STRING,
    REGEXP_SUBSTR(value, '"loggerName":"([^"]+)"', 1, 1, 'e', 1)
  ) AS logger,
  LEFT(value, 1200) AS raw_log
FROM {event_table}
WHERE record_type = 'LOG'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND resource_attributes:"k8s.container.name"::STRING NOT ILIKE '%-gateway'
ORDER BY timestamp DESC
LIMIT 100;
```

**Interpretation:**
- Use `raw_log` to recover the exact error text, processor, component, or external system signal that parsed queries missed.
- If the result set is noisy, re-run the same incident window with routed logger or error-text predicates instead of assuming the runtime is healthy.
- Use this before concluding that CDC, network, Kafka/Kinesis, or SaaS source investigations have no raw-log evidence.

## Destination Raw Log Fallback

Moved to `references/connectors/connector-shared-generic.md` (always loaded as part of every family bundle). Use it when parsed queries return `NULL` fields for destination-side warnings (`PutSnowpipeStreaming`, `destination write errors`, `insufficient privileges`).

---

## Error Pattern Summary

**Purpose:** Aggregate error patterns with counts. Shows what's failing most frequently on the routed runtime.

**When to use:** When Recent Error Logs returns too many results, or to identify the dominant issue. **MAY be omitted** from the primary parallel batch when the page-context fast path applies -- the catalog is already deduped by the same `logger_name` + `error_message` grouping as this query. Run it when the catalog is empty, when the time window has shifted, or when you need counts for patterns ranked 21+ (below the catalog's top-20 cutoff). See the full [page-context fast path skip conditions](../SKILL.md#discovery-sequence-high-level-troubleshoot) in `SKILL.md` Discovery Sequence step 1 for the authoritative criteria.

**Scope rule:** This query assumes a routed runtime or connector investigation. For deployment-wide discovery or unknown-runtime discovery, replace the exact namespace filter with `LIKE 'runtime-%'`.


```sql
SELECT
  COALESCE(
    record_attributes:"LoggerName"::STRING,
    TRY_PARSE_JSON(value):"loggerName"::STRING
  ) AS logger_name,
  COALESCE(
    TRY_PARSE_JSON(value):"throwable":"message"::STRING,
    TRY_PARSE_JSON(value):"formattedMessage"::STRING,
    TRY_PARSE_JSON(value):"message"::STRING
  ) AS error_message,
  COUNT(*) AS occurrence_count,
  MIN(timestamp) AS first_seen,
  MAX(timestamp) AS last_seen
FROM {event_table}
WHERE record_type = 'LOG'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND COALESCE(
    RECORD_ATTRIBUTES:"severity_text"::STRING,
    RECORD_ATTRIBUTES:"LogLevel"::STRING,
    TRY_PARSE_JSON(value):"level"::STRING
  ) IN ('WARN', 'ERROR')
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
GROUP BY 1, 2
ORDER BY occurrence_count DESC
LIMIT 50;
```

**Interpretation:**
- Use `occurrence_count`, `first_seen`, and `last_seen` to gauge severity and whether the issue is ongoing. See [Frequency Interpretation](core-guidelines.md#frequency-interpretation) for count-based interpretation rules.
- Many critical signals (CDC state transitions, Snowpipe Streaming channel invalidation, Kafka connectivity, backpressure throttling, processor validation failures) are logged at WARN, not ERROR. Do not treat zero ERROR rows as "no issues found" when the connector is UNHEALTHY.
- If this query returns zero rows despite confirmed symptoms, run [Generic Raw Log Fallback](#generic-raw-log-fallback) before concluding no errors exist.

> **Drill-downs.** For normalized grouping (when many rows share a message prefix but embed unique IDs) or a top-N throwable cause chain, **Load** `references/core-queries-fallbacks.md`. Both queries are load-on-demand, not part of startup.

---

## DPS Heartbeat Check

Moved to `references/core-queries-resource.md`. Use it when the deployment appears Inactive or Not Reporting.

---

## Deployment Info

Moved to `references/core-queries-resource.md`. Use it to verify deployment existence, state, and configured event table.

---

## Runtime Workflow Failures

Moved to `references/troubleshoot-runtime.md` (Step 2 of runtime troubleshooting). Use it when the runtime is stuck in CREATING, UPGRADING, or showing FAILED state.

## Query Best Practices

See [Time Filtering](core-guidelines.md#time-filtering) and [Query Mechanics](core-guidelines.md#query-mechanics) in `references/core-guidelines.md` for the canonical rules covering time bounds, namespace scoping, `ILIKE`, and `TRY_PARSE_JSON` fallback patterns. All queries in this file follow those rules.
