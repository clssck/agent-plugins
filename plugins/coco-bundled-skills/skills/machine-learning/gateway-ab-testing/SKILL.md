---
name: gateway-ab-testing
description: "Set up Snowflake Gateway A/B tests with gateway model monitors for drift and performance on real-time inference. Use when: gateway model monitor, gateway A/B testing, online inference experiment, champion challenger, model upgrade, shadow testing, traffic split, canary deployment, route traffic between models, compare inference services, evaluate A/B test, service-as-baseline drift metrics. NOT for model version monitors — route those to model-monitor."
parent_skill: machine-learning
---

# Gateway Monitoring & A/B Testing

Monitor inference services behind a Snowflake Gateway and compare baseline vs challenger during live A/B or shadow tests. Uses **gateway model monitors** and **auto-captured inference logs**.

**Preview feature.** Supported model tasks: binary classification, regression, multi-class classification.

## Intent Detection

Trigger strings match `machine-learning/SKILL.md` Inference routing. Route within this skill based on user intent.

**Model version monitor check (run first):** If the user mentions a **source table**, **model version only**, **batch/offline monitoring**, or `VERSION = ...` / `SOURCE = ...` with **no gateway** → route to `../model-monitor/SKILL.md` instead of the workflows below.

| User Says | Route To |
|-----------|----------|
| "gateway A/B testing", "online inference experiment", "champion challenger", "model upgrade", "shadow testing", "compare inference services", "A/B test", "traffic split", "canary deployment", "route traffic between models" | [Workflow A: End-to-End A/B Test](#workflow-a-end-to-end-ab-test) |
| "gateway model monitor", "create gateway monitor", "monitor gateway" | [Workflow B: Create Gateway Model Monitor](#workflow-b-create-gateway-model-monitor) |
| "query drift", "compare challenger", "A/B metrics", "performance by service" | [Workflow C: Query A/B Metrics](#workflow-c-query-ab-metrics) |
| "view in Snowsight", "monitor dashboard", "edit traffic split", "evaluate A/B test" | [Workflow D: Evaluate in Snowsight](#workflow-d-evaluate-in-snowsight) |
| "deploy services" (no monitor yet) | `../spcs-inference/SKILL.md` → [A/B Testing section](../spcs-inference/SKILL.md#ab-testing-creating-a-gateway-for-traffic-splitting) |

---

## Environment Guide Check

**Before proceeding, check if you already have the environment guide (from `machine-learning/SKILL.md` → Step 0) in memory.** If you do not have it, load it now before continuing.

---

## Prerequisites

Before gateway A/B testing:

- Two or more **inference services** deployed from the Model Registry (or one service for shadow-only setups)
- **Auto Capture enabled** on every service you want to monitor (immutable at service creation — see `../spcs-inference/SKILL.md` Step 5b)
- A **traffic_split** or shadow gateway routing traffic (see `../spcs-inference/SKILL.md` A/B Testing section)
- Model task: `tabular_binary_classification`, `tabular_regression`, or `tabular_multi_classification`
- At least one active inference service on the gateway that backs the monitored model
- All services behind the gateway must expose the **same function name** (e.g. `predict`) and **same output feature name** for the monitored function

**Optional for performance metrics:** Ground truth table + `ID_COLUMNS` matching `extra_columns` in inference requests.

---

## Workflow A: End-to-End A/B Test

Copy this checklist and track progress:

```
Task Progress:
- [ ] Step 1: Deploy services with Auto Capture
- [ ] Step 2: Create traffic-split gateway
- [ ] Step 3: (Optional) Prepare ground truth
- [ ] Step 4: Create gateway model monitor
- [ ] Step 5: Evaluate (Snowsight or SQL)
- [ ] Step 6: Adjust traffic split or promote winner
```

### Step 1: Deploy Services with Auto Capture

Load `../spcs-inference/SKILL.md` and deploy each inference service with **`autocapture=True`**.

Auto Capture is required for gateway model monitors. It cannot be enabled on an existing service — recreate the service if needed.

For inference request IDs that join to ground truth later, include matching fields in **`extra_columns`** on each request (see Stable Endpoints API reference in prod docs).

Confirm services are running and Auto Capture is enabled before creating the gateway.

### Step 2: Create Traffic-Split Gateway

Do **not** duplicate gateway DDL here. Follow `../spcs-inference/SKILL.md` → **A/B Testing: Creating a Gateway for Traffic Splitting**:

1. `SHOW ENDPOINTS IN SERVICE` for each service
2. Check privileges (`CREATE GATEWAY`, `BIND SERVICE ENDPOINT`, service roles)
3. `CREATE OR REPLACE GATEWAY` with `type: traffic_split` and weights summing to 100
4. Get gateway URL and smoke-test with PAT auth

For **shadow tests**, use a shadow-traffic gateway spec (challenger receives mirrored requests; baseline handles production responses). See Stable Endpoints & API Reference in prod docs.

Confirm the gateway is created and smoke-tested before creating the monitor.

### Step 3: (Optional) Prepare Ground Truth

Labels often arrive after predictions. You can create the monitor with an empty or partially populated ground truth table and load labels over time.

Requirements:

- Ground truth table with columns for actuals and ID fields
- `ID_COLUMNS` on the monitor must match `extra_columns` field names sent in inference requests
- Omit `GROUND_TRUTH` and `ID_COLUMNS` for **drift-only** monitoring (add performance later requires dropping and recreating the monitor)

### Step 4: Create Gateway Model Monitor

Continue to [Workflow B](#workflow-b-create-gateway-model-monitor).

### Step 5: Evaluate

- **Snowsight:** [Workflow D](#workflow-d-evaluate-in-snowsight)
- **SQL dashboards:** [Workflow C](#workflow-c-query-ab-metrics)

### Step 6: Adjust or Promote

- Change split: `CREATE OR REPLACE GATEWAY` with updated weights (`../spcs-inference/SKILL.md`)
- Promote winner: update gateway to 100% challenger, or route production to winning service
- Suspend test: `ALTER MODEL MONITOR ... SUSPEND` (monitoring pauses; gateway keeps routing)

---

## Workflow B: Create Gateway Model Monitor

### Step 0: Check for Recent Context

**Context sources:**

- **From spcs-inference:** Model name, database, schema, service names, gateway name
- **From model-registry:** Model name, database, schema

If context exists, pre-fill the checklist and only ask for missing values.

### Step 1: Collect Parameters

```
To create a gateway model monitor, I need:

1. Monitor name: [identifier in the schema]
2. Model name: [Model Registry model — must match services on the gateway]
3. Gateway name: [fully qualified: DB.SCHEMA.GATEWAY_NAME]
4. Function name: [e.g. 'predict' — must match all services behind the gateway]
5. Warehouse: [for monitor refresh compute]
6. Refresh interval: [min '60 seconds'; e.g. '1 minute' for online inference]
7. Aggregation window: [hours or days, min 1 hour; e.g. '1 hour']
8. (Optional) Ground truth table: [fully qualified table]
9. (Optional) ID columns: [array matching extra_columns in inference requests]
10. (Optional) Prediction columns: [`PREDICTION_CLASS_COLUMNS` or `PREDICTION_SCORE_COLUMNS` — class labels vs numeric scores; omit for single-output; required for multi-output]
11. (Optional) Actual columns: [`ACTUAL_CLASS_COLUMNS` or `ACTUAL_SCORE_COLUMNS` — match ground-truth type; omit when inferred; required for multi-output with performance metrics]
```

Wait for the user's response before continuing.

### Step 2: Validate Prerequisites

```sql
-- Model exists
SHOW MODELS LIKE '<MODEL_NAME>' IN SCHEMA <DATABASE>.<SCHEMA>;

-- Gateway exists
SHOW GATEWAYS IN SCHEMA <DATABASE>.<SCHEMA>;
DESCRIBE GATEWAY <DB>.<SCHEMA>.<GATEWAY_NAME>;

-- Services on gateway have autocapture (Python)
-- See ../inference-logs/SKILL.md Step 2
```

Verify privileges before proceeding:

| Requirement | Privilege |
|-------------|-----------|
| Create monitor | `CREATE MODEL MONITOR` on schema |
| Model | `OWNERSHIP` on model |
| Gateway | `USAGE` on gateway |
| Ground truth (if used) | `SELECT` on ground truth table |
| Compute | `USAGE` on database, schema, warehouse |

Do not execute GRANT statements. If a privilege is missing, tell the user which grant they need to run manually.

### Step 3: Generate CREATE MODEL MONITOR SQL

Drift-only (no ground truth):

```sql
CREATE MODEL MONITOR <MONITOR_NAME> WITH
    MODEL = <MODEL_NAME>
    GATEWAY = <GATEWAY_NAME>
    FUNCTION = '<FUNCTION_NAME>'
    WAREHOUSE = <WAREHOUSE_NAME>
    REFRESH_INTERVAL = '<REFRESH_INTERVAL>'
    AGGREGATION_WINDOW = '<AGGREGATION_WINDOW>';
```

With performance metrics (ground truth + IDs):

```sql
CREATE MODEL MONITOR <MONITOR_NAME> WITH
    MODEL = <MODEL_NAME>
    GATEWAY = <GATEWAY_NAME>
    FUNCTION = '<FUNCTION_NAME>'
    WAREHOUSE = <WAREHOUSE_NAME>
    REFRESH_INTERVAL = '<REFRESH_INTERVAL>'
    AGGREGATION_WINDOW = '<AGGREGATION_WINDOW>'
    GROUND_TRUTH = <GROUND_TRUTH_TABLE>
    ID_COLUMNS = ('<ID_COL_1>', '<ID_COL_2>');
```

Multi-output or explicit column mapping:

Use `PREDICTION_CLASS_COLUMNS` / `ACTUAL_CLASS_COLUMNS` for class labels. Use `PREDICTION_SCORE_COLUMNS` / `ACTUAL_SCORE_COLUMNS` for numeric scores (regression outputs or classification probabilities). Pick the parameter that matches the column type.

```sql
CREATE MODEL MONITOR <MONITOR_NAME> WITH
    MODEL = <MODEL_NAME>
    GATEWAY = <GATEWAY_NAME>
    FUNCTION = '<FUNCTION_NAME>'
    WAREHOUSE = <WAREHOUSE_NAME>
    REFRESH_INTERVAL = '<REFRESH_INTERVAL>'
    AGGREGATION_WINDOW = '<AGGREGATION_WINDOW>'
    GROUND_TRUTH = <GROUND_TRUTH_TABLE>
    ID_COLUMNS = ('<ID_COL_1>')
    PREDICTION_SCORE_COLUMNS = ('<PRED_COL>')   -- or PREDICTION_CLASS_COLUMNS
    ACTUAL_SCORE_COLUMNS = ('<ACTUAL_COL>');    -- or ACTUAL_CLASS_COLUMNS
```

**Single-output models:** Omit prediction and actual column parameters — Snowflake infers them from model task, auto-captured logs, and ground truth schema.

**Multi-output models:** User must specify explicitly — at least one `PREDICTION_*` parameter (and matching `ACTUAL_*` when using ground truth).

At creation, Snowflake picks a representative gateway service to infer model task. Data from up to **2 weeks** before creation can be included.

**⚠️ MANDATORY:** Present SQL to the user and wait for approval before executing.

### Step 4: Verify Monitor

```sql
SHOW MODEL MONITORS IN SCHEMA <DATABASE>.<SCHEMA>;
DESC MODEL MONITOR <MONITOR_NAME>;
```

Verify `type = 'GATEWAY_MODEL_MONITOR'`, `monitor_state` is `ACTIVE`, and check `aggregation_status` in DESC output. Five consecutive refresh failures auto-suspend the monitor.

### Step 5: Set Baseline Service (Drift)

In Snowsight, open the monitor dashboard and use **Set as baseline** on the control service. For SQL drift queries, pass `BASE_SERVICE` explicitly (Workflow C).

---

## Workflow C: Query A/B Metrics

Gateway monitors expose **drift** (distribution shift vs baseline service) and **performance** (when ground truth is configured).

### Drift: Compare Challenger vs Baseline

`BASE_SERVICE` is **required** for gateway drift metrics:

```sql
SELECT *
FROM TABLE(MODEL_MONITOR_DRIFT_METRIC(
    '<MONITOR_NAME>',
    '<METRIC_NAME>',
    '<PREDICTION_COLUMN>',
    '1 HOUR',
    DATEADD('day', -7, CURRENT_TIMESTAMP()),
    CURRENT_TIMESTAMP(),
    SERVICE => '<CHALLENGER_SERVICE>',
    BASE_SERVICE => '<BASELINE_SERVICE>'
));
```

Drift metric names: `'JENSEN_SHANNON'`, `'DIFFERENCE_OF_MEANS'`, `'WASSERSTEIN'`, `'POPULATION_STABILITY_INDEX'`.

Gateway monitors support hourly granularity (`'<num> HOUR'`). Segment queries (`extra_args`) are **not** supported for gateway monitors.

### Performance: Per-Service Accuracy

```sql
SELECT *
FROM TABLE(MODEL_MONITOR_PERFORMANCE_METRIC(
    '<MONITOR_NAME>',
    '<METRIC_NAME>',
    '1 HOUR',
    DATEADD('day', -7, CURRENT_TIMESTAMP()),
    CURRENT_TIMESTAMP(),
    SERVICE => '<CHALLENGER_SERVICE>'
));
```

Performance metrics by task:

| Task | Metrics |
|------|---------|
| Binary classification | `ROC_AUC`, `CLASSIFICATION_ACCURACY`, `PRECISION`, `RECALL`, `F1_SCORE` |
| Multi-class | `CLASSIFICATION_ACCURACY`, `MACRO_AVERAGE_PRECISION`, `MACRO_AVERAGE_RECALL`, `MICRO_AVERAGE_PRECISION`, `MICRO_AVERAGE_RECALL` |
| Regression | `RMSE`, `MAE`, `MAPE`, `MSE` |

Compare both services by running the query twice with different `SERVICE` values.

---

## Workflow D: Evaluate in Snowsight

1. Open **AI & ML** → **Models** → **Gateways** tab
2. **Monitoring** column shows monitor count per gateway — select the gateway
3. **Overview** — review services and traffic percentages; **Edit Gateway** to change split during the test
4. **Gateway monitoring** — select a monitor to open its dashboard
5. **Metrics overview** — latest drift and performance per service; **Set as baseline** for drift comparisons
6. **Charts** — filter by metrics, services, and time range
7. **Monitor details** — ground truth, refresh interval, aggregation window, columns; suspend/resume/drop from here

Gateway model monitors appear on the **gateway** details page, not on a model's **Monitoring** tab (that tab is for model version monitors).

---

## Manage Monitor Lifecycle

Suspend, resume, or update refresh settings for a gateway model monitor.

Present the chosen `ALTER MODEL MONITOR` statement to the user and wait for approval before executing.

```sql
ALTER MODEL MONITOR <MONITOR_NAME> SUSPEND;
ALTER MODEL MONITOR <MONITOR_NAME> RESUME;
ALTER MODEL MONITOR <MONITOR_NAME> SET
    REFRESH_INTERVAL = '<REFRESH_INTERVAL>'
    WAREHOUSE = <WAREHOUSE_NAME>;
```

---

## Drop Gateway Model Monitor

**⚠️ MANDATORY:** Before dropping, confirm with the user and wait for explicit confirmation (`yes`) before executing:

```
Are you sure you want to delete monitor <MONITOR_NAME>?

This cannot be undone. All monitor history and metrics will be lost.

Type "yes" to confirm:
```

**If confirmed:**

```sql
DROP MODEL MONITOR <MONITOR_NAME>;
```

---

## Troubleshoot Gateway Model Monitor

### Check monitor status

```sql
DESC MODEL MONITOR <MONITOR_NAME>;
```

Check `monitor_state` and `aggregation_status`. After five consecutive refresh failures, the monitor auto-suspends.

### Common issues

| Issue | Cause | Solution |
|-------|-------|----------|
| SUSPENDED | Manual suspend or 5 consecutive refresh failures | Check `aggregation_last_error` in DESC, fix root cause, then `ALTER MODEL MONITOR ... RESUME` |
| No drift metrics | Baseline service not set | Set baseline in Snowsight, or pass `BASE_SERVICE` in drift queries (Workflow C) |
| Missing performance metrics | No `GROUND_TRUTH` + `ID_COLUMNS` at creation | Create new monitor with ground truth configured |
| Missing autocapture data | Auto Capture not enabled on service | Recreate service with `autocapture=True` (`../spcs-inference/SKILL.md`) |
| Invalid data errors | NULLs, NaNs, or out-of-range scores in logs | Clean data at source; check auto-captured inference logs (`../inference-logs/SKILL.md`) |

After fixing the root cause:

```sql
ALTER MODEL MONITOR <MONITOR_NAME> RESUME;
DESC MODEL MONITOR <MONITOR_NAME>;
```
