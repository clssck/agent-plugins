# Adaptive Warehouse Tuning and Recommendations

## Tuning Parameters

Use the two parameters to tune performance headroom for your workload. These parameters control performance level and throughput capacity — they are not cost optimization levers. Adaptive delivers similar costs to Gen2 regardless of tuning.

| Workload | `MAX_QUERY_PERFORMANCE_LEVEL` | `QUERY_THROUGHPUT_MULTIPLIER` | Additional Controls |
|------|------------------------------|-------------------------------|---------------------|
| Latency-sensitive / critical queries | XLARGE or higher | Higher (e.g., 4–8) | Resource monitors |
| Mixed / general-purpose workloads | MEDIUM–LARGE | Medium (e.g., 2–4) | Budgets |
| Low-complexity / batch workloads | Lower (SMALL–MEDIUM) | Lower (e.g., 2–4) | Strict budgets |

**Modify parameters on an existing warehouse:**
```sql
ALTER WAREHOUSE {{warehouse_name}}
  SET MAX_QUERY_PERFORMANCE_LEVEL = {{level}}
      QUERY_THROUGHPUT_MULTIPLIER = {{multiplier}};
```

**View current settings:**
```sql
SHOW WAREHOUSES LIKE '{{warehouse_name}}';
```

**When to adjust `QUERY_THROUGHPUT_MULTIPLIER` post-conversion:**
- **Queries are queueing** → increase QTM (more concurrent throughput capacity needed)
- **Workload is lighter than expected** → decrease QTM (reduce headroom to match actual concurrency)

---

## Data-Driven Tuning Recommendations

When a user asks how to tune a specific adaptive warehouse, ask which symptom they're experiencing, then run the corresponding diagnostic query and generate the ALTER SQL.

### Symptom 1 — Too Much Queueing

**Trigger keywords:** "queries are queuing", "jobs waiting", "high queue time", "slow due to queueing", "QUERY_THROUGHPUT_MULTIPLIER too low"

**Step 1 — Diagnose with `WAREHOUSE_LOAD_HISTORY`:**

```sql
SELECT
    DATE_TRUNC('hour', start_time)          AS hour,
    AVG(avg_running)                        AS avg_running_jobs,
    AVG(avg_queued_load)                    AS avg_queued_load,
    AVG(avg_queued_provisioning)            AS avg_queued_provisioning,
    MAX(avg_queued_load)                    AS peak_queued_load
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_LOAD_HISTORY
WHERE warehouse_name = '{{warehouse_name}}'
  AND start_time >= DATEADD(day, -7, CURRENT_DATE())
GROUP BY 1
ORDER BY avg_queued_load DESC
LIMIT 48;
```

If `avg_queued_load` is consistently > 0 or `peak_queued_load` is high, queueing is a real problem.

**Step 2 — Get current QUERY_THROUGHPUT_MULTIPLIER:**

```sql
SHOW WAREHOUSES LIKE '{{warehouse_name}}';
```

Look for the `QUERY_THROUGHPUT_MULTIPLIER` column.

**Step 3 — Recommend the adjustment:**

| Approach | Formula | Notes |
|----------|---------|-------|
| Conservative | `CEIL(current * 1.2)` | ~20% increase; monitor for a week before tuning further |
| Aggressive | `current * 2` | Doubles throughput capacity; use when queueing is severe |

- Minimum value is `2`. If current is `0` (unlimited), no change needed — queueing is caused by something else.
- `0` (unlimited) is the ceiling — never recommend going above it.

**Step 4 — Present the ALTER SQL for approval:**

```sql
-- Conservative (~20% increase)
ALTER WAREHOUSE {{warehouse_name}}
  SET QUERY_THROUGHPUT_MULTIPLIER = {{ceil(current * 1.2)}};

-- Aggressive (double)
ALTER WAREHOUSE {{warehouse_name}}
  SET QUERY_THROUGHPUT_MULTIPLIER = {{current * 2}};
```

⚠️ **STOPPING POINT** — present both options and get explicit user approval before executing.

---

### Symptom 2 — Single Queries Running Slowly or Timing Out

**Trigger keywords:** "query is slow", "query timed out", "single job taking too long", "long-running query", "MAX_QUERY_PERFORMANCE_LEVEL too low"

**Step 1 — Diagnose with `QUERY_HISTORY`:**

```sql
SELECT
    query_id,
    query_text,
    start_time,
    ROUND(execution_time / 1000.0, 1)       AS execution_sec,
    ROUND(queued_overload_time / 1000.0, 1) AS queued_overload_sec,
    error_code,
    error_message
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE warehouse_name = '{{warehouse_name}}'
  AND start_time >= DATEADD(day, -7, CURRENT_DATE())
  AND (
      execution_time > 300000          -- longer than 5 minutes
      OR error_code IS NOT NULL        -- any error (catches timeouts)
  )
ORDER BY execution_time DESC
LIMIT 20;
```

If long execution times or timeout errors appear, `MAX_QUERY_PERFORMANCE_LEVEL` may be the lever.

**Step 2 — Get current MAX_QUERY_PERFORMANCE_LEVEL:**

```sql
SHOW WAREHOUSES LIKE '{{warehouse_name}}';
```

**Step 3 — Recommend the adjustment:**

Performance level ordering (lowest → highest): `XSMALL`, `SMALL`, `MEDIUM`, `LARGE`, `XLARGE`, `XXLARGE`, `XXXLARGE`, `X4LARGE`

| Approach | Change | Notes |
|----------|--------|-------|
| Conservative | +1 level | Incremental bump; re-evaluate after a few days |
| Aggressive | +2 levels | Faster relief; use when queries are timing out |

- **Hard cap: `X4LARGE`** — never recommend above this.
- If already at `X4LARGE`, tell the user this is the maximum and suggest reviewing query optimization instead.

**Step 4 — Present the ALTER SQL for approval:**

```sql
-- Conservative (+1 level, e.g. XLARGE → XXLARGE)
ALTER WAREHOUSE {{warehouse_name}}
  SET MAX_QUERY_PERFORMANCE_LEVEL = {{current + 1}};

-- Aggressive (+2 levels, e.g. XLARGE → XXXLARGE)
ALTER WAREHOUSE {{warehouse_name}}
  SET MAX_QUERY_PERFORMANCE_LEVEL = {{current + 2}};
```

⚠️ **STOPPING POINT** — present both options and get explicit user approval before executing.

---

### Symptom 3 — Costs Are Too High

**Trigger keywords:** "too expensive", "costs are high", "reduce spend", "lower credits", "warehouse is costing too much"

> **Framing reminder:** Adaptive is a performance feature, not a cost-reduction feature. Before diving into tuning, acknowledge this: reducing parameters will trade performance for lower cost — the user should be aware of that tradeoff.

**Step 1 — Diagnose with `QUERY_METERING_HISTORY`:**

```sql
SELECT
    DATE_TRUNC('day', query_start_time)     AS day,
    COUNT(DISTINCT query_id)                AS queries,
    SUM(credits_used)                       AS total_credits,
    ROUND(AVG(credits_used), 4)             AS avg_credits_per_query
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_METERING_HISTORY
WHERE warehouse_name = '{{warehouse_name}}'
  AND query_start_time >= DATEADD(day, -14, CURRENT_DATE())
GROUP BY 1
ORDER BY 1 DESC;
```

Use this to understand whether spend is driven by **volume** (many queries) or **per-query cost** (expensive individual queries).

**Step 2 — Get current settings:**

```sql
SHOW WAREHOUSES LIKE '{{warehouse_name}}';
```

**Step 3 — Recommend the adjustment:**

| Goal | Parameter | Change | Tradeoff |
|------|-----------|--------|----------|
| Reduce concurrent throughput capacity | `QUERY_THROUGHPUT_MULTIPLIER` | Reduce by ~20% (`FLOOR(current * 0.8)`, min 2) | More queueing at peak; jobs still run at full performance level |
| Reduce per-query compute | `MAX_QUERY_PERFORMANCE_LEVEL` | −1 level | Queries may run slower or time out |

- If spend is **volume-driven** → reducing `QUERY_THROUGHPUT_MULTIPLIER` is safer (limits parallel capacity).
- If spend is **per-query-driven** → reducing `MAX_QUERY_PERFORMANCE_LEVEL` targets the root cause but risks performance degradation.
- Minimum `QUERY_THROUGHPUT_MULTIPLIER` is `2`. If already at `2`, reducing further is not possible without setting to `0` (unlimited) — which would increase cost, not decrease it.
- Minimum `MAX_QUERY_PERFORMANCE_LEVEL` is `XSMALL` — never recommend below this.

**Step 4 — Present the ALTER SQL for approval:**

```sql
-- Option A: reduce throughput capacity by ~20%
ALTER WAREHOUSE {{warehouse_name}}
  SET QUERY_THROUGHPUT_MULTIPLIER = {{max(floor(current_qtm * 0.8), 2)}};

-- Option B: reduce per-query performance level by 1
ALTER WAREHOUSE {{warehouse_name}}
  SET MAX_QUERY_PERFORMANCE_LEVEL = {{current_mqpl - 1}};
```

⚠️ **STOPPING POINT** — explain the tradeoffs, present both options, and get explicit user approval before executing.

---

## Should I Use Adaptive?

**Adaptive works well for:**
- Mixed workloads where query sizes vary widely — Adaptive Compute right-sizes each query automatically
- Dashboard and high-concurrency workloads — `QUERY_THROUGHPUT_MULTIPLIER` controls parallel capacity
- Teams that struggle to pick the right warehouse size — adaptive removes that decision
- Any workload currently using QAS — QAS usage is included in compute credits (no separate QAS credit line)
- Analytical pipelines and transformation workloads — Adaptive handles these well

**Adaptive may not be ideal for:**
- Workloads requiring Snowpark-optimized memory configurations (not supported)
- Very large queries that need X5LARGE or X6LARGE (not supported)
- HTAP (key-value store access) workloads — Adaptive is not optimized for this query pattern; keep these warehouses on Standard
- Hybrid table queries — Adaptive is not optimized for hybrid table workloads; keep these warehouses on Standard
- SLA-sensitive workloads that require precise, predictable performance guarantees — a well-tuned standard warehouse with a fixed size may offer more explicit control and predictability in those cases

**IMPORTANT:** The above limitations are based on workload optimization and feature support. DO NOT invent technical explanations (e.g., memory reallocation, node reshuffling, resource conflicts) for why these workloads are not ideal. If a user asks for technical details beyond what's documented here, refer them to the [Adaptive Warehouse documentation](https://docs.snowflake.com/en/user-guide/warehouses-adaptive) or their Snowflake account team.

**Price and performance framing:**
- Adaptive warehouses deliver **generally better performance at similar costs to Gen2**
- Do **not** quote a specific performance percentage — use "generally better performance at similar costs" language
- Cost is controlled via `MAX_QUERY_PERFORMANCE_LEVEL` and `QUERY_THROUGHPUT_MULTIPLIER`, plus resource monitors and budgets
- The key simplification benefit is removing the need to right-size warehouses manually
- **Adaptive is not a cost-reduction feature.** If a user asks which warehouses to migrate in order to lower costs, correct the framing: adaptive delivers better performance at similar costs, not lower costs. The decision to migrate should be based on workload fit and operational simplicity, not cost savings.

## Which Warehouses to Migrate?

When a user asks which warehouses are good candidates for adaptive migration, frame the decision around **workload fit and performance**, not cost reduction.

**Good candidates (better performance fit):**
- Mixed workloads where query sizes vary widely — adaptive right-sizes each query automatically
- High-concurrency workloads currently using multi-cluster or QAS — adaptive handles concurrency via the shared pool
- Warehouses where teams struggle to pick the right size — adaptive removes that operational burden
- Workloads where operational simplicity matters more than explicit control
- Analytical pipelines and transformation workloads — adaptive works well for these

**Poor candidates (not a good fit):**
- Snowpark-optimized warehouses (not supported)
- Interactive warehouses (not supported)
- X5LARGE or X6LARGE warehouses (not supported)
- Hybrid table query workloads (Adaptive is not optimized for hybrid tables)
- SLA-sensitive workloads where precise, predictable performance is critical — a well-tuned standard warehouse may be a better fit

**DO NOT fabricate technical reasons** for why a workload is or isn't a good fit beyond what's documented above. If a user asks "why" and this document doesn't explain it in detail, say:

> "This skill doesn't provide technical implementation details on why [X] is not ideal for Adaptive. For architectural details, please refer to the [Adaptive Warehouse documentation](https://docs.snowflake.com/en/user-guide/warehouses-adaptive) or consult your Snowflake account team."