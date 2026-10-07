# Monitoring App Health (CPU / Memory / Lifecycle)

How to monitor the runtime health of a running Snowflake App service you own or operate: resource usage (CPU, memory), restarts, and lifecycle transitions. This complements the status and log checks in `operate/SKILL.md`; load this file when the user asks about **CPU, memory, resource limits, restarts, crash loops, capacity, or in-memory caching headroom**.

> Requires `MONITOR` privilege on the application service. The function queries the service's event table via the service's internal owner (hidden) role, so callers do not need direct access to the event table. Without `MONITOR` the call fails with `Insufficient privileges to operate on Application Service '<name>'. Your primary role <role> or one of your secondary roles must have MONITOR granted on APPLICATION SERVICE <fqn>`. If the role cannot resolve the object at all, the error is the generic "does not exist or not authorized" instead.

## The observability function

`SYSTEM$GET_APPLICATION_SERVICE_EVENT_TABLE_DATA` is a convenience wrapper over the service's event table — you don't need to know where the event table lives or query its raw OTEL-shaped columns. It exposes three streams, selected by `event_type`:

| `event_type` | Contains | Use for |
|--------------|----------|---------|
| `METRIC` | Per-container CPU/memory usage vs. requested/limit, container state, restart counts, network egress, volume usage | Resource health, capacity, cache headroom |
| `LOG` | Application stdout/stderr plus framework/platform startup output | Error hunting (see operate `View Logs`) |
| `EVENT` | Service/container lifecycle transitions (pending → ready, restarts, upgrades, failures) | Crash-loop and restart diagnosis |

```sql
SYSTEM$GET_APPLICATION_SERVICE_EVENT_TABLE_DATA(
    app_fqn      STRING,   -- 'DB.SCHEMA.APP'
    event_type   STRING,   -- 'LOG' | 'METRIC' | 'EVENT'
    [ start_time STRING,   -- TIMESTAMP literal, interpreted in the session time zone
      end_time   STRING ], -- TIMESTAMP literal, interpreted in the session time zone
    [ returnJobUUID STRING ] -- 'true' -> return a job UUID instead of inline data
);
```

- All streams are scoped to the requested window and sourced from the event table, so there is a **short ingestion delay** before the most recent samples appear.
- Metrics and lifecycle events **only** exist in the event table (always historical). Live-tail logs come from `SYSTEM$GET_APPLICATION_SERVICE_LOGS` instead (see operate `View Logs`).
- `returnJobUUID` is the **5th positional argument**, so you must also supply `start_time` and `end_time` to use it.

### Behavior worth knowing (verify against current docs if it changes)

- **Arguments must be constants.** `start_time` / `end_time` must be compile-time constants — either literal strings or **session variables**. Passing an expression like `CURRENT_TIMESTAMP()` or `TO_CHAR(DATEADD(...))` **directly** as an argument fails with "argument … needs to be constant". For a relative window, set session variables first (the queries below do this) and run the `SET` and the query in the same session/worksheet; alternatively hardcode literal timestamps.
- **Time zone & literal format.** Times are parsed in the **session time zone** and converted to UTC internally. Use `YYYY-MM-DD HH24:MI:SS` literals. A trailing zone offset must use a colon (`-07:00`) or `Z`; an offset without a colon (e.g. `-0700`) is rejected with "Invalid timestamp format". Building the window with `TO_CHAR(<ts>, 'YYYY-MM-DD HH24:MI:SS')` avoids the offset issue (a raw `TIMESTAMP_LTZ` cast renders `-0700`).
- **Row cap.** Results are ordered `timestamp DESC` and capped at `APPLICATION_SERVICE_EVENT_TABLE_MAX_ROWS` (**default 500**). Because the METRIC stream emits several rows per interval (usage + limit + requested, per container, per instance), 500 rows can cover only a few minutes. For anything wider, either **narrow the window** or use the **paged path** below.
- **Paged / unbounded path.** Passing `'true'` as the final argument runs the query with **no row limit** and returns a **query UUID**; retrieve the full result — as clean named columns, not JSON — with `RESULT_SCAN` in the same session (see [Preferred: paged path](#preferred-paged-path-for-wider-windows)).
- **Empty result.** An empty array (`[]`) means no data in range — but also occurs when the account's event table has **no ingested telemetry**, when **no event table is configured**, or when the query was throttled. It is not necessarily an error. Confirm an event table is set with `SHOW PARAMETERS LIKE 'EVENT_TABLE' IN ACCOUNT;`, and note telemetry can take a few minutes to appear after deploy. For a fast liveness check that does not depend on the event table, use `SYSTEM$GET_APPLICATION_SERVICE_LOGS` (see operate `View Logs`).

## Response shape

The function returns a VARCHAR containing a JSON array of positional tuples (array-of-arrays). For `METRIC`, each tuple is one sample; positions follow the METRIC column order documented in `operate/SKILL.md`:

| Position | Field | Notes |
|----------|-------|-------|
| `[0]` | `TIMESTAMP` | Sample time. Parse defensively — see the `sample_time` expression below. |
| `[1]` | `METRIC_NAME` | e.g. `container.cpu.usage`, `container.memory.limit` |
| `[2]` | `VALUE` | Numeric — cast with `::FLOAT` |
| `[3]` | `UNIT` | `cpu`, `byte`, etc. |
| `[4]` | `INSTANCE_ID` | Instance ordinal — **distinct instances report independently** (see multi-instance note) |
| `[5]` | `CONTAINER_NAME` | `runner` is the workload container |

> Filter to `CONTAINER_NAME = 'runner'` (the default app container) for the app's own CPU/memory. Other containers may also emit rows.

## Key metrics

| Metric name | Unit | Meaning |
|-------------|------|---------|
| `container.cpu.usage` | cpu (cores) | CPU cores currently in use |
| `container.cpu.limit` | cpu (cores) | CPU cores the container may use |
| `container.cpu.requested` | cpu (cores) | CPU cores reserved at schedule time |
| `container.memory.usage` | byte | Memory currently in use |
| `container.memory.limit` | byte | Hard memory ceiling (OOM-kill boundary) |
| `container.memory.requested` | byte | Memory reserved at schedule time |
| `container.restarts` | count | Container restart count — key crash-loop signal |
| `container.state.running` / `container.state.pending` / `container.state.started` / `container.state.finished` | state | Container lifecycle state gauges |
| `network.egress.transmitted.bytes` / `network.egress.received.bytes` | byte | Outbound-connection traffic |
| `network.egress.denied.packets` | count | Packets blocked by egress policy — EAI misconfiguration signal |
| `volume.usage` / `volume.capacity` | byte | Mounted-volume usage vs. capacity |

`usage` samples arrive frequently (roughly every 7–15 s for `runner`); `limit`/`requested` are steady configuration values re-emitted each interval. GPU equivalents (`container.gpu.*`) exist for GPU compute pools.

> **Multi-instance apps:** when a service runs more than one instance, each `INSTANCE_ID` reports its own `usage`/`limit` rows at the same timestamp. Join `usage` to `limit` on `(timestamp, container_name, instance_id)` — never on timestamp alone — or you will cross-pair samples across instances. The queries below group by instance for this reason.

## Reading memory usage

Memory usage and limit are reported directly in bytes — no derivation needed. This is the go-to check for **in-memory caching headroom** (room left below the limit before an OOM kill).

```sql
-- Time args must be constants, so set the window first (relative window here).
SET win_start = TO_CHAR(DATEADD('minute', -15, CURRENT_TIMESTAMP()), 'YYYY-MM-DD HH24:MI:SS');
SET win_end   = TO_CHAR(CURRENT_TIMESTAMP(), 'YYYY-MM-DD HH24:MI:SS');

WITH payload AS (
    SELECT SYSTEM$GET_APPLICATION_SERVICE_EVENT_TABLE_DATA(
        '<database>.<schema>.<app_name>', 'METRIC', $win_start, $win_end
    ) AS json
),
records AS (
    SELECT r.value AS rec
    FROM payload, LATERAL FLATTEN(input => PARSE_JSON(payload.json)) r
    WHERE rec[5]::STRING = 'runner'
      AND rec[1]::STRING IN ('container.memory.usage', 'container.memory.limit')
)
SELECT
    -- [0] may be epoch seconds or an ISO string depending on build; handle both.
    COALESCE(TRY_TO_TIMESTAMP(rec[0]::STRING),
             TO_TIMESTAMP(TRY_TO_DOUBLE(rec[0]::STRING)))                    AS sample_time,
    rec[4]::STRING                                                           AS instance_id,
    MAX(IFF(rec[1]::STRING = 'container.memory.usage', rec[2]::FLOAT, NULL)) AS used_bytes,
    MAX(IFF(rec[1]::STRING = 'container.memory.limit', rec[2]::FLOAT, NULL)) AS limit_bytes,
    ROUND(used_bytes / 1024 / 1024, 1)                                       AS used_mib,
    ROUND(100 * used_bytes / NULLIF(limit_bytes, 0), 1)                      AS pct_of_limit
FROM records
GROUP BY sample_time, instance_id
ORDER BY sample_time DESC;
```

## Reading CPU utilization

CPU utilization percent is **not** emitted directly — derive it from two co-sampled metrics that share the same timestamp for the same container and instance:

```
cpu_utilization_percent = (container.cpu.usage / container.cpu.limit) * 100
```

Join `usage` and `limit` on `(timestamp, container_name, instance_id)` and **drop samples where `cpu.limit` is 0** (no limit configured; the percentage is undefined). Because `usage` and `limit` are emitted per interval, pivoting with conditional aggregation on the grouping key pairs them without a self-join.

```sql
SET win_start = TO_CHAR(DATEADD('minute', -15, CURRENT_TIMESTAMP()), 'YYYY-MM-DD HH24:MI:SS');
SET win_end   = TO_CHAR(CURRENT_TIMESTAMP(), 'YYYY-MM-DD HH24:MI:SS');

WITH payload AS (
    SELECT SYSTEM$GET_APPLICATION_SERVICE_EVENT_TABLE_DATA(
        '<database>.<schema>.<app_name>', 'METRIC', $win_start, $win_end
    ) AS json
),
records AS (
    SELECT r.value AS rec
    FROM payload, LATERAL FLATTEN(input => PARSE_JSON(payload.json)) r
    WHERE rec[5]::STRING = 'runner'
      AND rec[1]::STRING IN ('container.cpu.usage', 'container.cpu.limit')
),
paired AS (
    SELECT
        COALESCE(TRY_TO_TIMESTAMP(rec[0]::STRING),
                 TO_TIMESTAMP(TRY_TO_DOUBLE(rec[0]::STRING)))                 AS sample_time,
        rec[4]::STRING                                                        AS instance_id,
        MAX(IFF(rec[1]::STRING = 'container.cpu.usage', rec[2]::FLOAT, NULL)) AS cpu_usage,
        MAX(IFF(rec[1]::STRING = 'container.cpu.limit', rec[2]::FLOAT, NULL)) AS cpu_limit
    FROM records
    GROUP BY sample_time, instance_id
)
SELECT
    sample_time,
    instance_id,
    cpu_usage,
    cpu_limit,
    ROUND(100 * cpu_usage / cpu_limit, 1) AS cpu_pct
FROM paired
WHERE cpu_limit > 0
ORDER BY sample_time DESC;
```

## Preferred: paged path for wider windows

Because inline results are capped at ~500 rows (newest first), a longer window silently truncates the METRIC stream. To analyze more than a few minutes, request a job UUID (unbounded) and read it back as **named columns** — no JSON parsing, no positional indexing:

```sql
-- Step 1: capture a UUID for the full (unlimited) result into a session variable
SET win_start = TO_CHAR(DATEADD('hour', -6, CURRENT_TIMESTAMP()), 'YYYY-MM-DD HH24:MI:SS');
SET win_end   = TO_CHAR(CURRENT_TIMESTAMP(), 'YYYY-MM-DD HH24:MI:SS');
SET job_uuid  = (SELECT SYSTEM$GET_APPLICATION_SERVICE_EVENT_TABLE_DATA(
    '<database>.<schema>.<app_name>', 'METRIC', $win_start, $win_end, 'true'
));

-- Step 2: read it back with real columns (same session); pivot for memory headroom
SELECT
    timestamp,
    instance_id,
    MAX(IFF(metric_name = 'container.memory.usage', value::FLOAT, NULL)) AS used_bytes,
    MAX(IFF(metric_name = 'container.memory.limit', value::FLOAT, NULL)) AS limit_bytes,
    ROUND(100 * used_bytes / NULLIF(limit_bytes, 0), 1)                  AS pct_of_limit
FROM TABLE(RESULT_SCAN($job_uuid))
WHERE container_name = 'runner'
  AND metric_name IN ('container.memory.usage', 'container.memory.limit')
GROUP BY timestamp, instance_id
ORDER BY timestamp DESC;
```

The same `RESULT_SCAN` columns (`timestamp, metric_name, value, unit, instance_id, container_name`) work for the CPU pivot — swap in the `container.cpu.*` metrics.

## Detecting restarts and crash loops

Two independent signals confirm a crash loop: a rising `container.restarts` in METRIC, plus recurring failure transitions in EVENT.

```sql
-- Lifecycle transitions over the last 6 hours
SET win_start = TO_CHAR(DATEADD('hour', -6, CURRENT_TIMESTAMP()), 'YYYY-MM-DD HH24:MI:SS');
SET win_end   = TO_CHAR(CURRENT_TIMESTAMP(), 'YYYY-MM-DD HH24:MI:SS');
SELECT SYSTEM$GET_APPLICATION_SERVICE_EVENT_TABLE_DATA(
    '<database>.<schema>.<app_name>', 'EVENT', $win_start, $win_end
);
```

`EVENT` tuples carry `SEVERITY`, `EVENT_NAME`, and `EVENT_DETAILS` (full column order in `operate/SKILL.md`); `EVENT_DETAILS` is an object with `message` and `status`. When restart count climbs alongside recurring failure events, correlate with the `LOG` stream around each restart timestamp to find the cause.

## Health triage flow

1. **Is it up?** `DESCRIBE APPLICATION SERVICE` → `status` should be `RUNNING`, `url` populated (see operate `Check App Status`).
2. **Is it resource-starved?** Query METRIC: memory `pct_of_limit` trending toward 100% risks OOM kills; sustained high `cpu_pct` means throttling.
3. **Is it restarting?** Check `container.restarts` (METRIC) and lifecycle churn (EVENT).
4. **Why?** Correlate with LOG around the affected timestamps (see operate `View Logs`).
