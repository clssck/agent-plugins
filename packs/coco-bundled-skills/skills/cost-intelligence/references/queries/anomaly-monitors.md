# Anomaly Monitors API

Reference for **Anomaly Monitors** (Tag-Based Anomaly Insights) — named, tag/service-type-scoped cost anomaly monitors on the `SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS` class. Each monitor has its own daily attribution, anomaly detection, and email alerting, scoped to Snowflake object tags and/or account-level service types.

**Semantic keywords:** anomaly monitor, monitor, tag-based anomaly, cost center anomaly, team anomaly, business unit anomaly, create monitor, monitor config, monitor notifications, recalculate anomalies, adhoc anomalies, sandbox anomalies

---

## Feature availability

Monitor procedures require the feature to be enabled for the account (`ENABLE_ANOMALY_MONITORS_API`, under master gate `FEATURE_ANOMALY_MONITORS`). If a monitor procedure errors as unknown/disabled, the feature is not enabled for that account — tell the user rather than retrying.

## Access control (RBAC)

The monitor procedures use the existing Cost Management application roles. No new roles are introduced.

| Procedure | `APP_USAGE_VIEWER` | `APP_USAGE_ADMIN` |
|-----------|:---:|:---:|
| `LIST_MONITORS` | ✅ | ✅ |
| `GET_MONITOR_CONFIG` | ✅ | ✅ |
| `GET_MONITOR_ANOMALIES` | ✅ | ✅ |
| `ADHOC_CALCULATE_ANOMALIES_FROM_CONFIG` | ✅ | ✅ |
| `RECALCULATE_ANOMALIES` | ✅ | ✅ |
| `CREATE_MONITOR` | | ✅ |
| `RENAME_MONITOR` | | ✅ |
| `UPDATE_MONITOR_CONFIG` | | ✅ |
| `DROP_MONITOR` | | ✅ |
| `SET_MONITOR_NOTIFICATION_EMAILS` | | ✅ |
| `GET_MONITOR_NOTIFICATION_EMAILS` | | ✅ |
| `GET_MONITOR_NOTIFICATION_LOG` | | ✅ |

Principle: read/compute is available to viewers; create/mutate/manage-notifications requires admin. Check access with the `SHOW GRANTS OF APPLICATION ROLE` queries in the parent router before running admin-only procedures.

## Limits

| Limit | Default | Enforced by |
|-------|---------|-------------|
| `MAX_NUM_ANOMALY_MONITORS` | 20 per account | `CREATE_MONITOR` (errors when exceeded) |
| `MAX_API_RESPONSE_WINDOW` | 366 days | `GET_MONITOR_ANOMALIES` (`end_date - start_date`) |

Defaults may be overridden by Snowflake operations via parameter change.

---

## The `config` object

`CREATE_MONITOR` and `UPDATE_MONITOR_CONFIG` take a `config` VARIANT built with `OBJECT_CONSTRUCT`. Keys:

| Key | Values | Notes |
|-----|--------|-------|
| `resource_tags` | object: `operator` + `tags` | `operator` is a set operator (e.g. `'UNION'`). `tags` is an array of `[tag_reference, tag_value]` pairs. |
| `service_types` | array of service-type strings | e.g. `'AI_SERVICES'`, `'AUTO_CLUSTERING'`, `'WAREHOUSE_METERING'`. Clear with `ARRAY_CONSTRUCT()`. |
| `credit_family` | `'CREDITS'` (default) or `'AI_CREDITS'` | Set at create time. `service_types` must belong to the declared family or the call errors (`INVALID_MONITOR_CONFIG`). |

Each tag in `tags` is a pair: the first element is a `SYSTEM$REFERENCE('TAG', '<db.schema.tag>', 'SESSION', 'APPLYBUDGET')` token; the second is the tag value string to match.

> **`ADHOC_CALCULATE_ANOMALIES_FROM_CONFIG` uses a different tag shape** — dict-shaped tags via `PARSE_JSON`, NOT `SYSTEM$REFERENCE` pairs. See its entry below.

> **System tags are not supported.** Tags in the `SNOWFLAKE` database (e.g. `SNOWFLAKE.CORE.PRIVACY_CATEGORY`) are rejected by the underlying ResourceGroup — use only user-defined tags (e.g. `MY_DB.MY_SCHEMA.COST_CENTER`).

> **`UPDATE_MONITOR_CONFIG` is a partial update.** Omitted keys preserve their current values. To clear service types, pass `'service_types', ARRAY_CONSTRUCT()` explicitly.

> **AI_CREDITS monitors:** when the monitor (or adhoc config) uses AI service types (e.g. `CORTEX_AGENTS`), you must set `'credit_family', 'AI_CREDITS'` in the config, or validation fails with a family mismatch.

**Example config for CREATE_MONITOR / UPDATE_MONITOR_CONFIG** (`OBJECT_CONSTRUCT`, `SYSTEM$REFERENCE` tag pairs):

```sql
OBJECT_CONSTRUCT(
    'credit_family', 'CREDITS',
    'resource_tags', OBJECT_CONSTRUCT(
        'operator', 'UNION',
        'tags', ARRAY_CONSTRUCT(
            ARRAY_CONSTRUCT(
                (SELECT SYSTEM$REFERENCE('TAG', 'MY_DB.MY_SCHEMA.COST_CENTER', 'SESSION', 'APPLYBUDGET')),
                'engineering'
            ),
            ARRAY_CONSTRUCT(
                (SELECT SYSTEM$REFERENCE('TAG', 'MY_DB.MY_SCHEMA.DEPT', 'SESSION', 'APPLYBUDGET')),
                'platform'
            )
        )
    ),
    'service_types', ARRAY_CONSTRUCT('AI_SERVICES', 'AUTO_CLUSTERING')
)
```

---

## Discovering eligible tags & service types

Use these when the user hasn't given an exact tag/value or service types — surface the valid options before building the `config`.

### Eligible tags & values

Lists user-defined tags applied to taggable objects, with their distinct values. Excludes `SNOWFLAKE.*` system tags (not supported by monitors). `TAG_REFERENCES` has up to ~2h latency.

```sql
SELECT TAG_DATABASE, TAG_SCHEMA, TAG_NAME,
       ARRAY_AGG(DISTINCT TAG_VALUE) WITHIN GROUP (ORDER BY TAG_VALUE) AS TAG_VALUES
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
WHERE domain IN ('WAREHOUSE','COMPUTE POOL','DATABASE','SCHEMA','TABLE','TASK','PIPE','REPLICATION GROUP','SNOWFLAKE INTELLIGENCE','CORTEX AGENT')
  AND OBJECT_DELETED IS NULL
  AND tag_database != 'SNOWFLAKE'
GROUP BY TAG_DATABASE, TAG_SCHEMA, TAG_NAME
ORDER BY TAG_NAME, TAG_DATABASE, TAG_SCHEMA;
```

### Eligible service types (by credit family)

A monitor's `service_types` must all belong to its `credit_family`. There is **no public view** for these yet, so the valid values are maintained here (move to a public source when one exists).

**CREDITS family:**
```
ADJ_CLOUD_SERVICES, AI_SERVICES, APPLICATION_UPGRADE, ARCHIVE_STORAGE_RETRIEVAL_FILE_PROCESSING,
ARCHIVE_STORAGE_WRITE, AUTOMATED_REFRESH_AND_DATA_REGISTRATION, AUTO_CLASSIFICATION_ASYNC_TASK,
AUTO_CLASSIFICATION_SCHEDULER_TASK, AUTO_CLUSTERING, BACKUP, BUDGET_TASK, CATALOG_LINKED_DATABASE,
CLOUD_SERVICES, COPY_FILES, DATA_QUALITY_MONITORING, FAILSAFE_RECOVERY, HYBRID_TABLE_REQUESTS,
INTERACTIVE_STREAMING, LOGGING, MATERIALIZED_VIEW, OBSERVE_USAGE, OPENFLOW_COMPUTE_BYOC,
OPENFLOW_COMPUTE_SNOWFLAKE, OPEN_CATALOG, ORGANIZATION_USAGE, PIPE, POSTGRES_COMPUTE,
POSTGRES_COMPUTE_HA, QUERY_ACCELERATION, REPLICATION, SEARCH_OPTIMIZATION,
SENSITIVE_DATA_CLASSIFICATION, SERVERLESS_ALERTS, SERVERLESS_EXPERIMENTS, SERVERLESS_TASK,
SERVERLESS_TASKS_FLEX, SNOWFLAKEDB_UPGRADE, SNOWFLAKE_APP_RUNTIME,
SNOWFLAKE_APP_RUNTIME_SERVERLESS, SNOWPARK_CONTAINER_SERVICES, SNOWPIPE_STREAMING,
STORAGE_LIFECYCLE_POLICY_EXECUTION, TABLE_OPTIMIZATION, TELEMETRY_DATA_INGEST, TRUST_CENTER,
WAREHOUSE_METERING
```

**AI_CREDITS family:**
```
AI_FUNCTIONS, AI_INFERENCE, AI_INFERENCE_TOOLS, AI_SENSITIVE_DATA_CLASSIFICATION,
BATCH_CORTEX_SEARCH, CORTEX_AGENTS, CORTEX_AI_GUARDRAILS, CORTEX_SEARCH, SNOWFLAKE_COCO,
SNOWFLAKE_COCO_CLI, SNOWFLAKE_COCO_DESKTOP, SNOWFLAKE_COCO_SNOWSIGHT, SNOWFLAKE_COWORK, SNOWWORK
```

> Pick `credit_family` first, then choose `service_types` only from that family's list — mixing families fails with `INVALID_MONITOR_CONFIG`.

---

## Procedures

### CREATE_MONITOR

**Triggered by:** "create a monitor", "set up anomaly monitoring for my cost center / team", "monitor tag X for anomalies"

**Access:** `APP_USAGE_ADMIN`. Fails if `alias` already exists, config is malformed, or the account already has `MAX_NUM_ANOMALY_MONITORS`.

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!CREATE_MONITOR('<alias>', <config>);
```

### RENAME_MONITOR

**Triggered by:** "rename monitor", "change monitor name"

**Access:** `APP_USAGE_ADMIN`.

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!RENAME_MONITOR('<alias>', '<new_alias>');
```

### LIST_MONITORS

**Triggered by:** "list monitors", "what monitors do I have", "show my anomaly monitors"

**Access:** `APP_USAGE_VIEWER` / `APP_USAGE_ADMIN`. Returns each monitor's `alias` and `config`.

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!LIST_MONITORS();
```

### DROP_MONITOR

**Triggered by:** "delete monitor", "drop monitor", "remove anomaly monitor"

**Access:** `APP_USAGE_ADMIN`. Permanently deletes the monitor and its state. Confirm before calling.

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!DROP_MONITOR('<alias>');
```

### UPDATE_MONITOR_CONFIG

**Triggered by:** "update monitor", "change monitor tags / service types", "edit monitor scope"

**Access:** `APP_USAGE_ADMIN`. Partial update — omitted keys are preserved.

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!UPDATE_MONITOR_CONFIG('<alias>', <config>);
```

### GET_MONITOR_CONFIG

**Triggered by:** "show monitor config", "what tags is this monitor watching", "monitor details"

**Access:** `APP_USAGE_VIEWER` / `APP_USAGE_ADMIN`. Returns the persisted `resource_tags` and `service_types`.

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!GET_MONITOR_CONFIG('<alias>');
```

### SET_MONITOR_NOTIFICATION_EMAILS

**Triggered by:** "add email to monitor alerts", "set monitor notifications", "who gets alerted for this monitor"

**Access:** `APP_USAGE_ADMIN`. **Overwrites the full list** — GET the current list, merge, then SET. Each address must be verified in Snowsight.

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!SET_MONITOR_NOTIFICATION_EMAILS('<alias>', '<email1>,<email2>');
```

### GET_MONITOR_NOTIFICATION_EMAILS

**Triggered by:** "show monitor notification emails", "current alert recipients"

**Access:** `APP_USAGE_ADMIN`.

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!GET_MONITOR_NOTIFICATION_EMAILS('<alias>');
```

### GET_MONITOR_ANOMALIES

**Triggered by:** "show anomalies for monitor X", "did the FINANCE monitor spike", "monitor anomaly history"

**Access:** `APP_USAGE_VIEWER` / `APP_USAGE_ADMIN`. Returns persisted daily results in the date range (`end_date - start_date` must be ≤ `MAX_API_RESPONSE_WINDOW`). Output columns: `USAGE_DATE, CONSUMPTION, FORECASTED_CONSUMPTION, CURRENCY_TYPE, LOWER_BOUND, UPPER_BOUND, IS_ANOMALY, ANOMALY_ID, LAST_REFRESHED_AT`. The unit is the monitor's **credit family** (`CREDITS` or `AI_CREDITS`), surfaced in the `CURRENCY_TYPE` column.

> **Surface anomaly days in SQL, not by eye.** This procedure returns one row **per day** (up to 366), and typically only a few have `IS_ANOMALY = TRUE`. Do not scan the raw output for anomalies — the one anomalous day is easily missed in a large/truncated result. Filter server-side with `RESULT_SCAN`:

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!GET_MONITOR_ANOMALIES('<alias>', '<start_date>', '<end_date>');
SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE IS_ANOMALY = TRUE
ORDER BY USAGE_DATE;
```

To also show the full daily series (e.g. the trend around a spike), read from the same `RESULT_SCAN(LAST_QUERY_ID())` without the `WHERE` filter.

> **No cause attribution for monitor spikes.** When asked "what drove/caused" a monitor anomaly, do NOT run account-level drill-downs (`METERING_HISTORY`, `GET_TOP_WAREHOUSES_ON_DATE`, etc.) and do NOT infer or fabricate a cause from the monitor's service types or tag. Per-resource cause attribution within a monitor's scope is not available today — say so, and offer the monitor's own trend, `GET_MONITOR_CONFIG`, or `RECALCULATE_ANOMALIES` instead.

### ADHOC_CALCULATE_ANOMALIES_FROM_CONFIG

**Triggered by:** "try this config before saving", "preview anomalies for these tags", "sandbox a monitor", "what would this monitor detect"

**Access:** `APP_USAGE_VIEWER` / `APP_USAGE_ADMIN`. Runs a one-off attribution + detection on a supplied `config` without persisting a monitor. Same output columns as `GET_MONITOR_ANOMALIES`. Include `credit_family` in the config when using AI service types.

> **Different tag format from CREATE/UPDATE.** ADHOC does NOT use `SYSTEM$REFERENCE` pairs. Its `resource_tags.tags` are fully-qualified **dicts** — `tagName`, `tagDatabase`, `tagSchema`, `tagValues` (array) — passed as a JSON string via `PARSE_JSON`. Passing the CREATE/UPDATE pair format calls `.get()` on a list and fails with a masked "Computation Error."

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!ADHOC_CALCULATE_ANOMALIES_FROM_CONFIG(
    PARSE_JSON('{
        "credit_family": "CREDITS",
        "resource_tags": {
            "operator": "UNION",
            "tags": [{"tagDatabase": "DEMO_DB", "tagSchema": "DEMO_SCHEMA", "tagName": "COST_CENTER", "tagValues": ["ml_team"]}]
        },
        "service_types": []
    }'),
    '<start_date>'::DATE,
    '<end_date>'::DATE
);
```

> **No cause attribution** (same as `GET_MONITOR_ANOMALIES`). An adhoc anomaly is tag-scoped — do NOT run account-level drill-downs (`METERING_HISTORY`, `GET_TOP_WAREHOUSES_ON_DATE`, etc.) or infer a cause from the config's tags/service types. Report the anomalous day(s) and offer to persist the config as a monitor.

### RECALCULATE_ANOMALIES

**Triggered by:** "recalculate monitor", "refresh monitor results", "my tag changed, rerun the monitor"

**Access:** `APP_USAGE_VIEWER` / `APP_USAGE_ADMIN`. Forces an immediate full recomputation for the monitor (the daily pipeline otherwise self-heals within 24h). Returns the refreshed results (same columns as `GET_MONITOR_ANOMALIES`).

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!RECALCULATE_ANOMALIES('<alias>');
```

### GET_MONITOR_NOTIFICATION_LOG

**Triggered by:** "was I notified", "monitor notification history", "which alerts fired for this monitor"

**Access:** `APP_USAGE_ADMIN`. Returns notifications sent for the monitor in the date window.

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!GET_MONITOR_NOTIFICATION_LOG('<alias>', '<start_date>', '<end_date>');
```
