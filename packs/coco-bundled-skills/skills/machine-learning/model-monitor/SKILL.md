---
name: model-monitor
description: "Set up and manage model version monitors for ML Observability on Snowflake Model Registry models. Track drift and performance for one model version from a source table. Use when: model version monitor, track drift, model performance, monitor predictions, ML observability, add monitoring, enable monitoring. NOT for gateway model monitors — route those to gateway-ab-testing."
parent_skill: machine-learning
---

# Model Version Monitor Operations

## Intent Detection

Route based on user intent.

**⚠️ Gateway check (run first):** If the user mentions a **gateway**, **traffic split**, **champion-challenger**, **gateway model monitor**, or **comparing inference services**, route to `../gateway-ab-testing/SKILL.md` instead of the workflows below.

| User Says | Route To |
|-----------|----------|
| "create monitor", "set up monitoring", "track model", "monitor my model", "add monitoring", "enable monitoring", "start monitoring" | [Workflow A: Create Model Version Monitor](#workflow-a-create-model-version-monitor) |
| "check drift", "view metrics", "model performance", "query metrics" | [Workflow B: Query Monitor Metrics](#workflow-b-query-monitor-metrics) |
| "suspend monitor", "resume monitor", "add segment", "set baseline" | [Workflow C: Manage Monitor](#workflow-c-manage-monitor) |
| "monitor not working", "suspended", "refresh failing" | [Workflow D: Troubleshoot Monitor](#workflow-d-troubleshoot-monitor) |

---

## ⚠️ CRITICAL: Environment Guide Check

**Before proceeding, check if you already have the environment guide (from `machine-learning/SKILL.md` → Step 0) in memory.** If you do NOT have it or are unsure, go back and load it now. The guide contains essential surface-specific instructions for session setup, code execution, and package management that you must follow.

---

## Prerequisites

Before using model version monitors:
- Model must be registered in Snowflake Model Registry
- Model task must be `tabular_binary_classification`, `tabular_regression`, or `tabular_multi_classification`
- Source table with predictions and timestamps must exist
- `snowflake-ml-python >= 1.7.1` required

---

## Workflow A: Create Model Version Monitor

### Step 0: Check for Recent Model Context

**⚠️ IMPORTANT:** Before asking questions, check if you have context from a recent session:

**Context sources:**
- **From model-registry:** Model name, version, database, schema, framework
- **From spcs-inference:** Model name, version, database, schema, service name

**Context to look for:**
- Model name and version
- Database and schema
- Source table (if predictions are being logged)
- Inference service name (if coming from SPCS)

**If context exists:**
- Use known model name/version - don't ask again
- Skip to Step 1, pre-filling the checklist with known values
- Only ask for missing required parameters (source table, warehouse, timestamp column, etc.)

**If no context:** Proceed to Step 1 and Step 2 normally.

### Step 1: Parse Intent and Build Parameter Checklist

Analyze the user's request to determine which parameters to collect:

**Feature Detection Table:**

| If user mentions... | Add to collection |
|---------------------|-------------------|
| "baseline", "drift", "PSI" | BASELINE |
| "segment", "subgroup", "slice" | SEGMENT_COLUMNS |
| "accuracy", "performance", "ground truth", "actual" | ACTUAL columns |
| "id column", "unique identifier", "row id" | ID_COLUMNS |

**Build checklist:**
- [ ] Mandatory: monitor name, model, version, function, source, warehouse, refresh interval, aggregation window, timestamp, prediction columns
- [ ] BASELINE (if drift/baseline mentioned)
- [ ] SEGMENT_COLUMNS (if segment/subgroup mentioned)
- [ ] ACTUAL columns (if performance/accuracy mentioned)
- [ ] ID_COLUMNS (if unique identifier mentioned)

### Step 2: Collect Mandatory Parameters

**If recent context exists**, only ask for parameters not already known:
```
I see you just registered model <MODEL_NAME> version <VERSION>. To set up a model version monitor, I need:

1. Monitor name: [identifier for the monitor]
2. Function name: [e.g., 'predict']
3. Source table: [table with predictions, fully qualified]
4. Warehouse: [for monitor compute]
5. Refresh interval: [e.g., '1 day', '6 hours', min: '60 seconds']
6. Aggregation window: [days only, e.g., '1 day', '7 days']
7. Timestamp column: [column name, must be TIMESTAMP_NTZ]
8. Prediction column(s): [score or class columns]
```

**If no context**, ask for all parameters:
```
To create your model version monitor, I need the following information:

1. Monitor name: [identifier for the monitor]
2. Model name: [must be in Model Registry]
3. Model version: [version to monitor]
4. Function name: [e.g., 'predict']
5. Source table: [fully qualified: DATABASE.SCHEMA.TABLE]
6. Warehouse: [for monitor compute]
7. Refresh interval: [e.g., '1 day', '6 hours', min: '60 seconds']
8. Aggregation window: [days only, e.g., '1 day', '7 days']
9. Timestamp column: [column name, must be TIMESTAMP_NTZ]
10. Prediction column(s): [score or class columns]
```

**⚠️ STOP**: Wait for user response.

### Step 3: Collect Feature-Specific Parameters

Based on Step 1 analysis, ask for additional parameters:

**If BASELINE needed:**
```
For drift detection, I also need:
- Baseline table: [fully qualified: DATABASE.SCHEMA.TABLE]
```

**If SEGMENT_COLUMNS needed:**
```
For segmentation, I also need:
- Segment column(s): [column names, must be STRING type, max 5, <25 unique values recommended, no special characters in values]
```

**If ACTUAL columns needed:**
```
For performance metrics, I also need:
- Actual/ground truth column(s): [score or class columns]
```

**⚠️ STOP**: Wait for user response (only if additional parameters needed).

### Step 4: Validate Prerequisites

```sql
-- Verify model and version exist
SHOW MODELS LIKE '<MODEL_NAME>' IN SCHEMA <DATABASE>.<SCHEMA>;
```

**If model doesn't exist (empty result):** Direct user to register model first using `../model-registry/SKILL.md`.

**If model exists:** Confirm the expected version appears in the results before proceeding.

```sql
-- Check source table columns
DESCRIBE TABLE <SOURCE_TABLE>;
```

Verify:
- Timestamp column exists (must be `TIMESTAMP_NTZ`)
- Prediction columns exist:
  - Binary classification/regression: `NUMBER` type
  - Multi-class classification: `STRING` type
- Actual columns (if provided): same type rules as prediction columns
- Segment columns (if provided): must be `STRING` type

### Step 5: Generate and Execute SQL

Build **model version monitor** CREATE MODEL MONITOR statement with collected parameters:

```sql
CREATE MODEL MONITOR <MONITOR_NAME> WITH
    MODEL = <MODEL_NAME>
    VERSION = '<VERSION_NAME>'
    FUNCTION = '<FUNCTION_NAME>'
    SOURCE = <SOURCE_TABLE>
    WAREHOUSE = <WAREHOUSE_NAME>
    REFRESH_INTERVAL = '<REFRESH_INTERVAL>'
    AGGREGATION_WINDOW = '<AGGREGATION_WINDOW>'
    TIMESTAMP_COLUMN = <TIMESTAMP_COL>
    PREDICTION_SCORE_COLUMNS = ('<PRED_COL>')
    -- Include if ACTUAL columns collected:
    ACTUAL_SCORE_COLUMNS = ('<ACTUAL_COL>')
    -- Include if BASELINE collected:
    BASELINE = <BASELINE_TABLE>
    -- Include if SEGMENT_COLUMNS collected:
    SEGMENT_COLUMNS = ('<SEGMENT_COL_1>', '<SEGMENT_COL_2>');
```

**⚠️ MANDATORY:** Present the generated SQL (with only the relevant clauses) to user and wait for approval before executing.

### Step 6: Verify Monitor Created

```sql
-- List all monitors in schema
SHOW MODEL MONITORS IN SCHEMA <DATABASE>.<SCHEMA>;

-- Filter by name pattern
SHOW MODEL MONITORS LIKE '%<PATTERN>%' IN SCHEMA <DATABASE>.<SCHEMA>;

-- Check specific monitor details
DESC MODEL MONITOR <MONITOR_NAME>;
```

Verify `monitor_state` is `ACTIVE` (not SUSPENDED, PARTIALLY_SUSPENDED, or UNKNOWN).

**⚠️ STOP**: Confirm monitor is running before proceeding.

### Suggested Next Actions

Present context-aware options based on what was configured:

**If baseline was NOT configured:**
```
Your model version monitor is active! To enable drift detection:
  - "Set a baseline for drift detection"
```

**If actual columns were NOT configured:**
```
To track model accuracy, you can add ground truth data later:
  - "Add actual columns to my monitor" (requires recreating monitor)
```

**Always show:**
```
View your monitor: Snowsight → AI&ML → Models → Select Model → Monitors
Query metrics: "Show me metrics for my monitor"
```

---

## Workflow B: Query Monitor Metrics

### Step 1: Identify Monitor and Metric Type

**Ask user:**
```
What metrics would you like to view?

1. Drift metrics (PSI, distribution shifts)
2. Performance metrics (accuracy, precision, recall, F1, MAE, RMSE)
3. Statistical metrics (counts, nulls, distributions)
```

**⚠️ STOP**: Wait for user response.

### Step 2: Query Metrics

**Drift Metrics:**

```sql
SELECT * 
FROM TABLE(MODEL_MONITOR_DRIFT_METRIC(
    '<MONITOR_NAME>',
    '<METRIC_NAME>',        -- e.g., 'POPULATION_STABILITY_INDEX', 'JENSEN_SHANNON', 'DIFFERENCE_OF_MEANS', 'WASSERSTEIN'
    '<COLUMN_NAME>',        -- feature column to check drift
    'DAY',                  -- granularity
    '<START_TIME>'::TIMESTAMP_NTZ,
    '<END_TIME>'::TIMESTAMP_NTZ
));
```

**Performance Metrics:**

```sql
SELECT * 
FROM TABLE(MODEL_MONITOR_PERFORMANCE_METRIC(
    '<MONITOR_NAME>',
    '<METRIC_NAME>',        -- e.g., 'ROC_AUC', 'CLASSIFICATION_ACCURACY', 'PRECISION', 'RECALL', 'F1_SCORE', 'RMSE', 'MAE'
    'DAY',
    '<START_TIME>'::TIMESTAMP_NTZ,
    '<END_TIME>'::TIMESTAMP_NTZ
));
```

**Statistical Metrics:**

```sql
SELECT * 
FROM TABLE(MODEL_MONITOR_STAT_METRIC(
    '<MONITOR_NAME>',
    '<METRIC_NAME>',        -- e.g., 'COUNT', 'COUNT_NULL', 'MIN', 'MAX', 'AVG', 'SUM'
    '<COLUMN_NAME>',
    'DAY',
    '<START_TIME>'::TIMESTAMP_NTZ,
    '<END_TIME>'::TIMESTAMP_NTZ
));
```

**Query Metrics for Specific Segment:**

```sql
SELECT * 
FROM TABLE(MODEL_MONITOR_DRIFT_METRIC(
    '<MONITOR_NAME>',
    '<METRIC_NAME>',
    '<COLUMN_NAME>',
    'DAY',
    '<START_TIME>'::TIMESTAMP_NTZ,
    '<END_TIME>'::TIMESTAMP_NTZ,
    '{"SEGMENTS": [{"column": "<SEGMENT_COL>", "value": "<SEGMENT_VALUE>"}]}'
));
```

### Step 3: Present Results

Format results clearly showing:
- Time period analyzed
- Metric values and trends
- Any concerning drift or performance degradation

**Suggest next actions** based on results:
- High drift → Investigate data pipeline, consider retraining
- Low performance → Review model, check for concept drift
- Missing data → Check source table updates

---

## Workflow C: Manage Monitor

Present the chosen `ALTER MODEL MONITOR` statement to the user and wait for approval before executing.

### Suspend/Resume Monitor

```sql
-- Suspend monitoring
ALTER MODEL MONITOR <MONITOR_NAME> SUSPEND;

-- Resume monitoring
ALTER MODEL MONITOR <MONITOR_NAME> RESUME;
```

### Set Monitor Properties

Set one or more properties in a single statement (each is optional):

```sql
ALTER MODEL MONITOR <MONITOR_NAME> SET
    BASELINE = '<BASELINE_TABLE_NAME>'
    REFRESH_INTERVAL = '<REFRESH_INTERVAL>'
    WAREHOUSE = <WAREHOUSE_NAME>;
```

**Examples:**

```sql
-- Set baseline only
ALTER MODEL MONITOR <MONITOR_NAME> SET BASELINE = '<BASELINE_TABLE>';

-- Set refresh interval only
ALTER MODEL MONITOR <MONITOR_NAME> SET REFRESH_INTERVAL = '6 hours';

-- Set warehouse only
ALTER MODEL MONITOR <MONITOR_NAME> SET WAREHOUSE = <NEW_WAREHOUSE>;

-- Set multiple properties at once
ALTER MODEL MONITOR <MONITOR_NAME> SET
    REFRESH_INTERVAL = '6 hours'
    WAREHOUSE = <NEW_WAREHOUSE>;
```

### Add/Remove Segment Columns

```sql
-- Add segment (max 5 segments, must be STRING type)
ALTER MODEL MONITOR <MONITOR_NAME> ADD SEGMENT_COLUMN = '<COLUMN_NAME>';

-- Remove segment
ALTER MODEL MONITOR <MONITOR_NAME> DROP SEGMENT_COLUMN = '<COLUMN_NAME>';
```

---

## Drop Model Version Monitor

**⚠️ MANDATORY:** Before dropping, confirm with user:
```
Are you sure you want to delete monitor <MONITOR_NAME>?

This cannot be undone. All monitor history and metrics will be lost.

Type "yes" to confirm:
```

**⚠️ STOP**: Wait for explicit confirmation before proceeding.

**If confirmed:**

```sql
DROP MODEL MONITOR <MONITOR_NAME>;
```

---

## Workflow D: Troubleshoot Monitor

### Step 1: Check Monitor Status

```sql
DESC MODEL MONITOR <MONITOR_NAME>;
```

Check `monitor_state`:
- `ACTIVE` - Operating correctly
- `SUSPENDED` - Monitoring paused (manual or after 5 failures)
- `PARTIALLY_SUSPENDED` - One underlying table stopped refreshing
- `UNKNOWN` - State cannot be identified

**Additional fields for debugging:**
- `aggregation_status` - Current aggregation state
- `aggregation_last_error` - Error details if suspended

### Step 2: Common Issues and Solutions

| Issue | Cause | Solution |
|-------|-------|----------|
| SUSPENDED | Manual suspend or 5 consecutive refresh failures | Fix root cause, then `ALTER MODEL MONITOR ... RESUME` |
| PARTIALLY_SUSPENDED | One underlying table stopped refreshing | Check DESC for `aggregation_last_error`, fix issue, then RESUME |
| UNKNOWN | State cannot be determined | Check DESC for errors, may need to recreate monitor |
| No drift metrics | No baseline set | Set baseline with `ALTER MODEL MONITOR ... SET BASELINE` |
| Missing performance metrics | No actual columns | Re-create monitor with `ACTUAL_SCORE_COLUMNS` |
| Segment query fails | Invalid segment value | Check segment column has expected values, case sensitive |
| Invalid data errors | NULLs, NaNs, or out-of-range values | Clean source data, remove invalid rows |

### Step 3: Resume After Fixing

```sql
-- After fixing root cause
ALTER MODEL MONITOR <MONITOR_NAME> RESUME;

-- Verify it's running
DESC MODEL MONITOR <MONITOR_NAME>;
```

---

## CREATE MODEL MONITOR Parameters

### Mandatory Parameters (Always Required)

| Parameter | Type | Description |
|-----------|------|-------------|
| `MONITOR_NAME` | identifier | Name for the monitor |
| `MODEL` | identifier | Model name (same schema as monitor) |
| `VERSION` | string | Model version name |
| `FUNCTION` | string | Function name (e.g., 'predict') |
| `SOURCE` | identifier | Table/view with predictions (fully qualified) |
| `WAREHOUSE` | identifier | Warehouse for compute |
| `REFRESH_INTERVAL` | string | How often to refresh (min: '60 seconds', e.g., '1 day') |
| `AGGREGATION_WINDOW` | string | Aggregation period (days only, e.g., '1 day') |
| `TIMESTAMP_COLUMN` | identifier | Timestamp column (must be TIMESTAMP_NTZ) |
| `PREDICTION_*_COLUMNS` | string list | At least one of: PREDICTION_CLASS_COLUMNS or PREDICTION_SCORE_COLUMNS |

### Feature-Triggered Parameters (Ask When User Mentions Feature)

| Parameter | Trigger Keywords | Type | Description |
|-----------|------------------|------|-------------|
| `BASELINE` | "baseline", "drift", "PSI" | identifier | Baseline table for drift detection |
| `SEGMENT_COLUMNS` | "segment", "subgroup", "slice" | string list | Columns for segmentation (max 5, STRING type, <25 unique values recommended) |
| `ACTUAL_CLASS_COLUMNS` | "accuracy", "performance", "ground truth", "actual" | string list | Ground truth class columns |
| `ACTUAL_SCORE_COLUMNS` | "accuracy", "performance", "ground truth", "actual" | string list | Ground truth score columns |

### Optional Parameters (Only If User Explicitly Requests)

| Parameter | Type | Description |
|-----------|------|-------------|
| `ID_COLUMNS` | string list | Columns that uniquely identify each row in source data |
| `CUSTOM_METRIC_COLUMNS` | string list | Additional numeric columns to track |

---

## Usage Notes

- **Column uniqueness:** Each column can only be used in one parameter (e.g., an ID column cannot also be a prediction column), except for segment columns which can overlap with other columns as long as they are STRING type
- **Single output only:** Multiple-output models not supported; prediction/actual column arrays must have exactly one element
- **Segment values:** Case sensitive, special characters not supported in segment queries

---

## Monitor Status Commands

### List Monitors

```sql
-- All monitors in current schema
SHOW MODEL MONITORS;

-- Filter by pattern
SHOW MODEL MONITORS LIKE '%mymodel%';

-- Specific scope
SHOW MODEL MONITORS IN SCHEMA <DATABASE>.<SCHEMA>;
SHOW MODEL MONITORS IN DATABASE <DATABASE>;
SHOW MODEL MONITORS IN ACCOUNT;
```

**Key output column:** `monitor_state` (ACTIVE, SUSPENDED, PARTIALLY_SUSPENDED, UNKNOWN)

### Describe Monitor

```sql
DESC MODEL MONITOR <MONITOR_NAME>;
```

**Key output columns for debugging:**
- `monitor_state` - Current state
- `aggregation_status` - Aggregation state details
- `aggregation_last_error` - Error message if suspended
- `columns` - JSON with all configured columns

---

## Supported Metrics

**Drift Metrics:**
- `JENSEN_SHANNON`, `DIFFERENCE_OF_MEANS`, `WASSERSTEIN`, `POPULATION_STABILITY_INDEX`

**Performance Metrics (Binary Classification):**
- `ROC_AUC`, `CLASSIFICATION_ACCURACY`, `PRECISION`, `RECALL`, `F1_SCORE`

**Performance Metrics (Multi-class Classification):**
- `CLASSIFICATION_ACCURACY`, `MACRO_AVERAGE_PRECISION`, `MACRO_AVERAGE_RECALL`, `MICRO_AVERAGE_PRECISION`, `MICRO_AVERAGE_RECALL`

**Performance Metrics (Regression):**
- `RMSE`, `MAE`, `MAPE`, `MSE`

**Statistical Metrics:**
- `COUNT`, `COUNT_NULL`, `MIN`, `MAX`, `AVG`, `SUM`

---

## Limitations

- Max 250 monitors per account
- Max 500 features monitored per monitor
- Max 5 segment columns per monitor
- Segment columns must be STRING type, <25 unique values recommended
- Segment values are case sensitive, no special characters supported
- Multiple-output models not supported (arrays must have one element)
- Supports regression, binary classification, and multi-class classification
- Monitor must be in same schema as model
- Cannot change model/source after creation (must drop and recreate)

---

## Output

- Model version monitor created and tracking predictions from the source table
- Metrics available via SQL functions or Snowsight UI
- Alerts can be configured using Snowflake alerting features
