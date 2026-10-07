---
name: openflow-observability-core-queries-resource
description: Resource and operational SQL queries for Openflow event table diagnostics. Required for CDC startup and connector-type bootstrap; otherwise load on demand.
---

# Resource & Operational Queries

SQL templates for resource checks, processor status, FlowFile analysis, and connector inventory. This file is required during CDC startup and connector-type bootstrap because it contains Active Connectors and CDC table-state queries. Outside those paths, load it on demand for resource utilization, backpressure, crash loops, or connector versioning.

These queries assume a routed runtime investigation. If you are intentionally comparing multiple runtimes, replace the exact namespace filter with a broader runtime filter.

For core triage queries, see `references/core-queries.md` (always loaded).

---

## CPU Utilization by Pod

**Purpose:** Check CPU utilization as a percentage. Identifies resource-constrained runtimes.

**When to use:** Slow data flows, timeouts, suspected resource issues.


```sql
SELECT
  cu.timestamp,
  cu.pod_name AS runtime_pod,
  cu.cpu_used AS cpu_used_raw,
  lc.cores_available AS cores_available,
  ROUND((cu.cpu_used / lc.cores_available) * 100, 2) AS cpu_usage_percentage
FROM (
  SELECT
    timestamp,
    resource_attributes:"k8s.pod.name"::STRING AS pod_name,
    value AS cpu_used
  FROM {event_table}
  WHERE timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
    AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
    AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
    AND resource_attributes:"k8s.container.name"::STRING LIKE '%-server'
    AND record_type = 'METRIC'
    AND record:"metric":"name"::STRING = 'container.cpu.usage'
) cu
ASOF JOIN (
  SELECT
    timestamp,
    resource_attributes:"k8s.pod.name"::STRING AS pod_name,
    value AS cores_available
  FROM {event_table}
  WHERE timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
    AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
    AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
    AND record_type = 'METRIC'
    AND record:"metric":"name"::STRING = 'cores.available'
) lc
MATCH_CONDITION(cu.timestamp >= lc.timestamp)
ON cu.pod_name = lc.pod_name
WHERE lc.cores_available IS NOT NULL
ORDER BY cu.timestamp DESC;
```

**Thresholds:**
- < 60%: Normal
- 60-80%: Elevated -- monitor
- \> 80% sustained: High -- recommend resizing runtime to a larger instance family
- Cores available: 1 = Small, 4 = Medium, 8 = Large

**BYOC Note:** The `cores.available` metric may not be present in BYOC event tables. If this query returns zero rows, use the raw `container.cpu.usage` values and compare against known instance CPU counts: Small = 1 vCPU, Medium = 4 vCPU, Large = 8 vCPU.

**Zero rows:** If this query returns zero rows for all metrics, do not assume the runtime is healthy. Metrics may be unavailable because the runtime is down, the event table is not receiving metric records, or the `{hours_back}` window does not cover the period of interest. Verify the runtime is running by checking for recent LOG records in the namespace before concluding resource utilization is normal.

---

## Memory Utilization by Pod

**Purpose:** Check memory utilization percentage. Identifies OOM risk.

**When to use:** OOM errors, Java heap errors, slow performance.


```sql
WITH memory_metrics AS (
  SELECT
    timestamp,
    resource_attributes:"k8s.pod.name"::STRING AS runtime_pod,
    record:"metric":"name"::STRING AS metric_name,
    value
  FROM {event_table}
  WHERE timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
    AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
    AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
    AND resource_attributes:"k8s.container.name"::STRING LIKE '%-server'
    AND record_type = 'METRIC'
    AND record:"metric":"name"::STRING IN ('container.memory.usage', 'container.memory.available')
)
SELECT
  timestamp,
  runtime_pod,
  MAX(CASE WHEN metric_name = 'container.memory.usage' THEN value END) AS memory_usage,
  MAX(CASE WHEN metric_name = 'container.memory.available' THEN value END) AS memory_available,
  ROUND(
    (MAX(CASE WHEN metric_name = 'container.memory.usage' THEN value END) /
     (MAX(CASE WHEN metric_name = 'container.memory.usage' THEN value END) +
      MAX(CASE WHEN metric_name = 'container.memory.available' THEN value END))) * 100,
    2
  ) AS memory_usage_percentage
FROM memory_metrics
GROUP BY timestamp, runtime_pod
ORDER BY timestamp DESC, runtime_pod;
```

**Thresholds:**
- < 70%: Normal (idle runtimes often sit at ~50%)
- 70-85%: Elevated -- monitor closely
- \> 85%: High OOM risk -- recommend resizing runtime
- Sudden jumps to 95%+ followed by pod restart = OOM kill

---

## Disk Space per Runtime

**Purpose:** Check free disk space for runtime storage repositories.

**When to use:** Suspected disk full, FlowFile content issues, provenance buildup.


```sql
SELECT
  timestamp,
  resource_attributes:"openflow.dataplane.id"::STRING AS deployment_id,
  resource_attributes:"k8s.pod.name"::STRING AS runtime_pod,
  record_attributes:"storage.type"::STRING AS storage_type,
  ROUND(value / 1024 / 1024 / 1024, 2) AS gb_free
FROM {event_table}
WHERE timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND record_type = 'METRIC'
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND scope:"name"::STRING = 'runtime'
  AND record:"metric":"name"::STRING = 'storage.free'
ORDER BY timestamp DESC;
```

**Thresholds:**
- \> 5 GB: Normal
- 1-5 GB: Low -- investigate what's consuming storage
- < 1 GB: Critical -- data flow will fail; content repository or provenance buildup

**Storage types:** `flowfile` (FlowFile metadata), `content` (actual data), `provenance` (data lineage records)

---

## Processor Run Status

**Purpose:** Check which processors are running vs stopped.

**When to use:** Connector not processing data, partial data flow.


```sql
SELECT
  timestamp,
  record_attributes:"component"::STRING AS processor,
  record_attributes:"id"::STRING AS processor_id,
  value AS running
FROM {event_table}
WHERE record_type = 'METRIC'
  AND record:"metric":"name"::STRING = 'processor.run.status.running'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
ORDER BY timestamp DESC;
```

**Interpretation:**
- `running` = 1: Processor is active
- `running` = 0: Processor is stopped
- All processors stopped = connector is stopped or has validation errors
- Some stopped = may be intentional (some connectors have processors that don't run in all configs)

---

## Stuck FlowFiles

**Purpose:** Find connections where data has been queued for too long.

**When to use:** Data not flowing, suspected backpressure or stuck processing.


```sql
SELECT
  timestamp,
  record_attributes:"name"::STRING AS connection_name,
  record_attributes:"source.name"::STRING AS source_processor,
  record_attributes:"destination.name"::STRING AS dest_processor,
  record_attributes:"id"::STRING AS connection_id,
  value AS max_queued_duration_ms,
  ROUND(value / 1000 / 60, 1) AS queued_minutes
FROM {event_table}
WHERE record_type = 'METRIC'
  AND record:"metric":"name"::STRING = 'connection.queued.duration.total'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND value > 0
ORDER BY value DESC
LIMIT 50;
```

**Thresholds:**
- < 5 minutes: Normal processing time
- 5-30 minutes: Elevated -- check destination processor status
- \> 30 minutes: Concern -- investigate processor failures or backpressure

---

## Active Connectors

**Purpose:** List all connectors that have been active in the runtime.

**When to use:** Inventory check, identify which connectors are deployed.


```sql
SELECT DISTINCT
  record_attributes:"flow.identifier"::STRING AS connector_id,
  SPLIT_PART(record_attributes:"processGroupIdPath"::STRING, '/', 3) AS connector_pg_id,
  SPLIT_PART(record_attributes:"processGroupNamePath"::STRING, '/', 3) AS connector_name
FROM {event_table}
WHERE record_type = 'METRIC'
  AND record:"metric":"name"::STRING = 'processgroup.bytes.sent'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
LIMIT 100;
```

---

## Connector Versions

**Purpose:** Check which connector versions are running.

**When to use:** Version mismatch investigation, pre-upgrade check.


```sql
SELECT
  resource_attributes:"openflow.dataplane.id"::STRING AS deployment_id,
  resource_attributes:"k8s.namespace.name"::STRING AS runtime_key,
  record_attributes:"flow.identifier"::STRING AS connector_id,
  record_attributes:"flow.version"::STRING AS connector_version,
  record_attributes:"name"::STRING AS connector_name
FROM {event_table}
WHERE timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND record_type = 'METRIC'
  AND record_attributes:"type"::STRING = 'process-group'
  AND record_attributes:"flow.identifier"::STRING != ''
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
GROUP BY ALL;
```

**Interpretation:**
- Compare `flow.version` across connectors. Mismatched versions after an upgrade may indicate a failed flow update.
- Check if the version matches the expected version from the Connector Flow Registry (accessible in the Openflow UI).
- Different connectors on the same runtime may legitimately have different versions if they were installed at different times.

---

## Container Restart Count

**Purpose:** Check if runtime containers have been restarting.

**When to use:** Suspected crash loops, intermittent failures.


```sql
SELECT
  timestamp,
  resource_attributes:"k8s.pod.name"::STRING AS pod_name,
  resource_attributes:"k8s.container.name"::STRING AS container_name,
  resource_attributes:"k8s.container.restart_count"::STRING AS restart_count
FROM {event_table}
WHERE record_type = 'LOG'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND resource_attributes:"k8s.container.name"::STRING LIKE '%-server'
ORDER BY timestamp DESC
LIMIT 10;
```

**Interpretation:**
- `restart_count` = 0: No restarts (normal)
- `restart_count` >= 1: Container has restarted -- investigate why
- Increasing restart count over time = crash loop

**Restart trend query (hourly buckets):**

```sql
SELECT
  TIME_SLICE(timestamp, 1, 'HOUR') AS hour_bucket,
  resource_attributes:"k8s.pod.name"::STRING AS pod,
  MAX(resource_attributes:"k8s.container.restart_count"::NUMBER) AS restart_count
FROM {event_table}
WHERE record_type = 'LOG'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND resource_attributes:"k8s.container.name"::STRING LIKE '%-server'
GROUP BY 1, 2
ORDER BY 1 DESC;
```

Use this to identify whether restarts are clustered at specific times or steadily increasing.

---

## CDC Table Replication State

**Purpose:** Derive the latest known replication state per table from event logs. CDC connectors only.

**When to use:** Table FAILED errors, replication stuck, proactive CDC health check, or high-level troubleshoot of CDC connectors.


**Shared-runtime scoping:** If the affected table is already known from the CDC Error Log Scan or the customer report, add `AND value ILIKE '%state for table%<schema>.<table>%'` inside the `state_transitions` and `stored_states` CTE `WHERE` clauses (not the `combined` CTE) before interpreting results. In shared runtimes, do not use runtime-wide rows from this query as restart evidence for a different connector.

```sql
WITH state_transitions AS (
  SELECT
    timestamp,
    REGEXP_SUBSTR(TRY_PARSE_JSON(value):"formattedMessage"::STRING,
      'Replication state for table (\\S+)', 1, 1, 'e') AS table_name,
    REGEXP_SUBSTR(TRY_PARSE_JSON(value):"formattedMessage"::STRING,
      'changed from (\\w+)', 1, 1, 'e') AS from_state,
    REGEXP_SUBSTR(TRY_PARSE_JSON(value):"formattedMessage"::STRING,
      'to (\\w+)', 1, 1, 'e') AS to_state
  FROM {event_table}
  WHERE record_type = 'LOG'
    AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
    AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
    AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
    AND value ILIKE '%Replication state for table%changed from%'
),
stored_states AS (
  SELECT
    timestamp,
    REGEXP_SUBSTR(TRY_PARSE_JSON(value):"formattedMessage"::STRING,
      'Stored state for table ([^:]+)', 1, 1, 'e') AS table_name,
    NULL AS from_state,
    REGEXP_SUBSTR(TRY_PARSE_JSON(value):"formattedMessage"::STRING,
      'status=(\\w+)', 1, 1, 'e') AS to_state
  FROM {event_table}
  WHERE record_type = 'LOG'
    AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
    AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
    AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
    AND value ILIKE '%Stored state for table%status=FAILED%'
),
combined AS (
  SELECT *, 0 AS source_rank FROM state_transitions
  UNION ALL
  SELECT *, 1 AS source_rank FROM stored_states
)
SELECT table_name, to_state AS current_state, from_state AS previous_state, timestamp AS last_transition_at
FROM combined
QUALIFY ROW_NUMBER() OVER (PARTITION BY table_name ORDER BY timestamp DESC, source_rank ASC) = 1
ORDER BY
  CASE current_state WHEN 'FAILED' THEN 0 WHEN 'SNAPSHOT_REPLICATION' THEN 1
    WHEN 'NEW' THEN 2 WHEN 'INCREMENTAL_REPLICATION' THEN 3 ELSE 4 END,
  table_name;
```

**To show only FAILED tables:** Add `AND value ILIKE '%to FAILED%'` to the `state_transitions` CTE WHERE clause. The `stored_states` CTE already filters to FAILED only.

**Interpretation:**
- FAILED tables sort first -- these need immediate attention
- `previous_state` shows where the table was before it failed
- Rows with NULL `previous_state` and a `current_state` of FAILED were sourced from `Stored state` messages (periodic state snapshots from StandardTableStateService), not from transition logs. These indicate the table was already in FAILED state when the log was written. If the failure phase matters (snapshot vs incremental), check the CDC Error Log Scan results for the table name to identify the transition.
- In multi-connector runtimes, only act on rows that tie back to the reported connector via the affected table name or matching CDC error-log evidence
- Only reflects tables with state changes or stored-state snapshots inside the selected incident window or `{hours_back}` fallback. If zero rows are returned, do not conclude there are no FAILED tables -- the transitions may have aged out. Use the Table State Store UI for current state.
- For definitive current state, guide the customer to the Table State Store in the Openflow UI (right-click connector canvas > Controller Services > Table State Store > View State)
- **Do not write recovery guidance from this query's results alone.** FAILED table recovery requires the procedure in `references/connectors/connector-shared-cdc.md`, which must already be loaded before this query runs (see [Discovery Sequence](../SKILL.md#discovery-sequence-high-level-troubleshoot) step 1, primary parallel batch, in SKILL.md).

---

## DPS Heartbeat Check

**Purpose:** Verify the Data Plane Service is sending heartbeats to the control plane.

**When to use:** Deployment shows as Inactive or Not Reporting.


**SPCS:**
```sql
SELECT
  timestamp,
  resource_attributes:"openflow.dataplane.id"::STRING AS deployment_id,
  value AS log_message
FROM {event_table}
WHERE record_type = 'LOG'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.pod.name"::STRING LIKE 'dataplane-service%'
ORDER BY timestamp DESC
LIMIT 50;
```

**BYOC:**
```sql
SELECT
  timestamp,
  resource_attributes:"openflow.dataplane.id"::STRING AS deployment_id,
  value AS log_message
FROM {event_table}
WHERE record_type = 'LOG'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = 'openflow-runtime-infra'
  AND resource_attributes:"k8s.pod.name"::STRING LIKE 'dataplane-service%'
ORDER BY timestamp DESC
LIMIT 50;
```

**Healthy indicators (look for these messages):**
- "Publishing heartbeat to Control Plane"
- "Polling Control Plane for tasking"
- "Received 0 runtime tasks from Control Plane" (normal when no pending tasks)

**Unhealthy indicators:**
- No results = DPS is not running or not logging
- Repeated errors about OAuth tokens = authentication issue
- Errors about connectivity = network issue between DPS and control plane

---

## Deployment Info

**Purpose:** Get deployment state and configuration from account-level SQL.

**When to use:** Verify deployment exists and is in expected state.

```sql
SHOW OPENFLOW DATA PLANE INTEGRATIONS;
```

Then for details on a specific deployment:

```sql
DESCRIBE OPENFLOW DATA PLANE INTEGRATION {integration_name};
```

**Key columns from SHOW:**
- `state`: ACTIVE, INACTIVE, CREATING, etc.
- `event_table`: Configured event table
- `created_on`: Creation timestamp

**Metadata reliability:** Do not treat empty `SHOW OPENFLOW DATA PLANE INTEGRATIONS` or `DESCRIBE ... does not exist or not authorized` as proof the integration was deleted; these are affected by privilege scope or name mismatches.

**BYOC OAuth failures:** For BYOC deployments showing DPS heartbeat failures plus OAuth `403` / token endpoint errors, prioritize the event-table evidence and follow `references/troubleshoot-network.md`. Those signals indicate a deployment-level control-plane connectivity or allowlist problem unless stronger evidence proves otherwise.
