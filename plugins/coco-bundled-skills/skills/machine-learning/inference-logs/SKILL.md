---
name: inference-logs
description: "View and analyze captured inference data from model services with Auto-Capture enabled. Use when: querying INFERENCE_TABLE, viewing inference logs, analyzing request/response data, debugging inference history, checking captured predictions. Triggers: inference logs, inference table, captured inference, autocapture data, view inference history, inference requests, inference responses."
parent_skill: machine-learning
---

# Inference Logs (Auto-Capture Data)

Query and analyze captured inference data from model services that have Auto-Capture enabled.

## Prerequisites

- A model service with `autocapture=True` enabled during creation
- OWNERSHIP privilege on the model (to read inference table data)
- USAGE privilege on the service and gateway (if filtering by those)

**Note:** Auto-Capture is not supported for vLLM or HuggingFace inference engines.

---

## Step 1: Identify the Model

**Ask user:**
```
Which model would you like to view inference logs for?

Please provide:
- Model name
- Database and schema where the model is registered
```

**⚠️ STOP**: Wait for user response.

---

## Step 2: Check Auto-Capture Status

Verify the model has services with autocapture enabled:

```python
from snowflake.ml.registry import Registry

session = <SESSION_SETUP>  # Per environment guide
reg = Registry(session=session, database_name="<DATABASE>", schema_name="<SCHEMA>")
mv = reg.get_model("<MODEL_NAME>").version("<VERSION>")

services_df = mv.list_services()
print(services_df[['name', 'status', 'autocapture_enabled']])
```

If no services have `autocapture_enabled=True`:
```
None of the services for this model have Auto-Capture enabled.

Auto-Capture must be enabled when creating the service (it cannot be added later).
To enable it, you would need to recreate the service with autocapture=True.

Would you like help creating a new service with Auto-Capture enabled?
```

If yes, load `../spcs-inference/SKILL.md`.

---

## Step 3: Collect Filter Options

**Ask user:**
```
You can filter the inference logs. All filters are optional — press Enter to skip any:

- Model version (e.g., V1):
- Service name (e.g., MY_SERVICE):
- Gateway name (if using a gateway):
- Time range: How far back? (e.g., "1 hour", "24 hours", "7 days")
```

**⚠️ STOP**: Wait for user response.

---

## Step 4: Query Inference Data

### Basic Query (All Logs)

```sql
SELECT *
FROM TABLE(INFERENCE_TABLE('<MODEL_NAME>'));
```

### Filtered Query

Include only the filters the user provided:

```sql
SELECT *
FROM TABLE(
    INFERENCE_TABLE(
        '<MODEL_NAME>',
        MODEL_VERSION => '<VERSION>',
        SERVICE => '<SERVICE_NAME>',
        GATEWAY => '<GATEWAY_NAME>'
    )
)
WHERE TIMESTAMP > DATEADD('<unit>', -<N>, CURRENT_TIMESTAMP());
```

### Filter by Function Name

```sql
SELECT *
FROM TABLE(INFERENCE_TABLE('<MODEL_NAME>'))
WHERE RECORD_ATTRIBUTES:"snow.model_serving.function.name" = '<function_name>';
```

### Sample Recent Logs

```sql
SELECT *
FROM TABLE(INFERENCE_TABLE('<MODEL_NAME>'))
WHERE TIMESTAMP > DATEADD('hour', -1, CURRENT_TIMESTAMP())
ORDER BY TIMESTAMP DESC
LIMIT 100;
```

---

## Step 5: Present Results and Offer Analysis

After running the query, present the results and ask:

```
I found <N> inference records. What would you like to do?

1. View the raw data
2. Summarize request/response patterns
3. Analyze input feature distributions
4. Done
```

**⚠️ STOP**: Wait for user response.

### Request Volume Over Time

```sql
SELECT
    DATE_TRUNC('hour', TIMESTAMP) as hour,
    COUNT(*) as request_count
FROM TABLE(INFERENCE_TABLE('<MODEL_NAME>'))
WHERE TIMESTAMP > DATEADD('day', -1, CURRENT_TIMESTAMP())
GROUP BY 1
ORDER BY 1;
```

---

## Inference Table Data Schema

| Field | Description |
|-------|-------------|
| `RECORD_ATTRIBUTES:"snow.model_serving.request.data.<column>"` | Input features sent to the model |
| `RECORD_ATTRIBUTES:"snow.model_serving.response.data.<column>"` | Inference output returned by the model |
| `RECORD_ATTRIBUTES:"snow.model_serving.request.timestamp"` | When the request hit the inference service |
| `RECORD_ATTRIBUTES:"snow.model_serving.response.code"` | HTTP status code |
| `RECORD_ATTRIBUTES:"snow.model_serving.truncation_policy"` | `NONE` or `TRUNCATED_DEFAULT` if data exceeded 1MB limit |
| `RECORD_ATTRIBUTES:"snow.model_serving.last_hop_id"` | Last gateway ID the request passed through |
| `RECORD_ATTRIBUTES:"snow.model_serving.hop_ids"` | List of gateway IDs showing request path |
| `TIMESTAMP` | Event timestamp (use for time-range filtering) |

---

## Important Notes

- **Only successful requests are captured.** Failed requests are not logged.
- **Filter arguments must reference existing entities.** If you recreated a service with the same name, queries only return data from the current service.
- **Data is retained after deletion.** Inference data persists even after deleting a service or version, as long as the model still exists.
- **Deleting the model permanently deletes all inference data.**
- **1MB limit per event.** Data exceeding this is progressively truncated (strings shortened, then payload dropped).
- **Performance tip:** Always filter by `TIMESTAMP` for large inference tables.

---

## Querying Historical Data for Deleted Entities

Even after deleting a service, version, or gateway, you can still query the historical data:

```sql
-- All logs for model (includes deleted services)
SELECT * FROM TABLE(INFERENCE_TABLE('<MODEL_NAME>'));

-- Filter by deleted version
SELECT * FROM TABLE(INFERENCE_TABLE('<MODEL_NAME>', MODEL_VERSION => '<VERSION>'));

-- Filter by deleted service
SELECT * FROM TABLE(INFERENCE_TABLE('<MODEL_NAME>', MODEL_VERSION => '<VERSION>', SERVICE => '<SERVICE>'));
```

---

## Common Use Cases

### Debugging Unexpected Predictions

```sql
SELECT
    RECORD_ATTRIBUTES:"snow.model_serving.request.data" as input,
    RECORD_ATTRIBUTES:"snow.model_serving.response.data" as output,
    TIMESTAMP
FROM TABLE(INFERENCE_TABLE('<MODEL_NAME>'))
WHERE TIMESTAMP > DATEADD('hour', -1, CURRENT_TIMESTAMP())
ORDER BY TIMESTAMP DESC
LIMIT 10;
```

### Building a Retraining Dataset

```sql
CREATE TABLE training_data_from_prod AS
SELECT
    RECORD_ATTRIBUTES:"snow.model_serving.request.data.feature1"::FLOAT as feature1,
    RECORD_ATTRIBUTES:"snow.model_serving.request.data.feature2"::FLOAT as feature2,
    RECORD_ATTRIBUTES:"snow.model_serving.response.data.prediction"::FLOAT as prediction,
    TIMESTAMP
FROM TABLE(INFERENCE_TABLE('<MODEL_NAME>'))
WHERE TIMESTAMP > DATEADD('day', -30, CURRENT_TIMESTAMP());
```

### Comparing Model Versions (A/B Testing)

```sql
SELECT
    RECORD_ATTRIBUTES:"snow.model_serving.version" as version,
    AVG(RECORD_ATTRIBUTES:"snow.model_serving.response.data.score"::FLOAT) as avg_score,
    COUNT(*) as request_count
FROM TABLE(INFERENCE_TABLE('<MODEL_NAME>'))
WHERE TIMESTAMP > DATEADD('day', -7, CURRENT_TIMESTAMP())
GROUP BY 1;
```
