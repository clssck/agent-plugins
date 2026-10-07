---
name: feature-store-monitor
description: "Monitor, audit, validate, and promote Snowflake Feature Store: health checks, refresh history, freshness, suspend/resume, cost, validation checklist, environment promotion."
parent_skill: feature-store
path: machine-learning/feature-store/monitor
---

# Feature Store Operations, Monitoring & Validation

## When to Load

Parent skill routes here for MONITOR intent: "feature freshness", "refresh history", "pipeline health", "list feature views", "suspend feature view", "resume feature view", "feature store cost", "audit", "validate", "check feature store", "promote features", "DEV to PROD".

## Prerequisites

- `../references/api-reference.md` loaded
- Feature store (`fs`) initialized

---

## Workflow

### Step 1: Inventory Check

**List all feature store objects:**

```python
print("=== Entities ===")
fs.list_entities().show()

print("=== Feature Views ===")
fs.list_feature_views().select(
    "NAME", "VERSION", "SCHEDULING_STATE", "DESC"
).show()
```

---

### Step 2: Health Check

**Check scheduling state for all feature views:**

```python
fv_status = fs.list_feature_views().select(
    "NAME", "VERSION", "SCHEDULING_STATE"
)
fv_status.show()
```

| State | Meaning | Action |
|-------|---------|--------|
| `ACTIVE` | Refreshing on schedule | Healthy |
| `SUSPENDED` | Paused, not refreshing | Resume if needed |
| `DRAFT` | Not yet registered | Register to activate |

> **Note:** `fv.status` returns a `FeatureViewStatus` enum, not a string. Use `str(fv.status)` or `"ACTIVE" in str(fv.status)` for comparisons.

**Check refresh history for a specific feature view:**

```python
fv = fs.get_feature_view("<FV_NAME>", "<VERSION>")
fs.get_refresh_history(fv).show()
```

**SQL-based health check (deeper diagnostics):**

```sql
SELECT name, scheduling_state, last_completed_refresh_state,
       target_lag_sec, target_lag_type, latest_data_timestamp
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
WHERE schema_name = '<FEATURE_STORE_SCHEMA>'
ORDER BY name;

SELECT name, state, state_message, refresh_action,
       refresh_start_time, refresh_end_time
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
    NAME_PREFIX => '<DATABASE>.<SCHEMA>', ERROR_ONLY => TRUE
))
ORDER BY refresh_start_time DESC
LIMIT 10;
```

For more diagnostic queries → Load `../references/troubleshooting.md`.

---

### Step 3: Suspend / Resume Feature Views

**Suspend (stop refreshing):**
```python
fs.suspend_feature_view("<FV_NAME>", "<VERSION>")
```

**Resume (restart refreshing):**
```python
fs.resume_feature_view("<FV_NAME>", "<VERSION>")
```

> **Note:** If `resume_feature_view()` doesn't take effect, use SQL directly:
> ```sql
> ALTER DYNAMIC TABLE <DATABASE>.<SCHEMA>."<FV_NAME>$<VERSION>" RESUME;
> ```

**⚠️ STOP**: Confirm with user before suspending production feature views.

---

### Step 4: Read Feature Values

**Read current feature values (offline store):**
```python
df = fs.read_feature_view("<FV_NAME>", "<VERSION>")
df.show()
```

**Read specific keys:**
```python
df = fs.read_feature_view(
    "<FV_NAME>", "<VERSION>",
    keys=[["key_1"], ["key_2"]],
    feature_names=["FEATURE_A", "FEATURE_B"],
)
df.show()
```

---

### Step 5: Cost Management

```sql
SELECT
    name,
    SUM(DATEDIFF('second', refresh_start_time, refresh_end_time)) / 3600.0 AS approx_compute_hours,
    COUNT(*) AS refresh_count
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY())
WHERE schema_name = '<FEATURE_STORE_SCHEMA>'
GROUP BY name
ORDER BY approx_compute_hours DESC;
```

**Cost optimization strategies:**
- Increase `refresh_freq` for less time-sensitive features
- Use smaller warehouses for simple feature pipelines
- Dedicate warehouses per pipeline criticality tier
- Suspend unused or deprecated feature views
- Use `DOWNSTREAM` target lag for intermediate stages

---

### Step 6: Validate Against Best Practices

After registration or as a standalone audit, validate entity and feature view against this checklist. Report each item as **Pass**, **Warn**, or **Fail** with actionable recommendations.

#### Audit Entry Point

If the user wants to audit an existing feature view:

1. **Ask** for the feature store location (database and schema)
2. **Connect** to the feature store
3. **List** entities and feature views
4. **Ask** the user which entity and feature view to audit
5. **Retrieve** the feature view:
   ```python
   fv = fs.get_feature_view(name="<FV_NAME>", version="<VERSION>")
   print(fv.query)
   print(fv.feature_descs)
   print(fv.entities)
   ```
6. **Identify** the source table from the query SQL
7. **Run** the checklists below

#### Entity Checklist

| # | Check | Criteria |
|---|-------|----------|
| E1 | **Business naming** | Entity name is SCREAMING_SNAKE_CASE business object, not a table name |
| E2 | **Join key uniqueness** | Join keys uniquely identify the entity or grain is intentional |
| E3 | **Description provided** | `desc` parameter is non-empty and meaningful |
| E4 | **Consistent key naming** | Same key column name used everywhere |

#### Feature View Checklist

| # | Check | Criteria |
|---|-------|----------|
| F1 | **Description provided** | `desc` parameter is non-empty and meaningful |
| F2 | **All features documented** | Every feature column has an entry in `attach_feature_desc` |
| F3 | **Incremental refresh compatible** | Query avoids incremental blockers (see `../references/troubleshooting.md`) |
| F4 | **Change tracking enabled** | Source table has `CHANGE_TRACKING = TRUE` |
| F5 | **Label separation** | Prediction target columns NOT included as features |
| F6 | **Source table fully qualified** | SQL uses `DATABASE.SCHEMA.TABLE` format |
| F7 | **Data quality filters** | WHERE clause filters invalid/null rows |
| F8 | **Refresh frequency appropriate** | Matches source data update frequency |
| F9 | **Naming convention** | FV name follows `<ENTITY>_<DOMAIN>_FV` pattern; features use standard suffixes |
| F10 | **Version format** | Version uses zero-padded format (`V01`, `V02`) |
| F11 | **Timestamp column** | `timestamp_col` is set if PIT retrieval is needed |
| F12 | **No MDT in FeatureView** | No hard-coded scaling, encoding, or imputation |

#### Feature Engineering Checklist

| # | Check | Criteria |
|---|-------|----------|
| G1 | **Recency features** | Includes `MAX(timestamp)` for time-since-last |
| G2 | **Time-window aggregations** | Uses Aggregation API or tiled windows — or documents trade-off |
| G3 | **Variance/spread features** | Includes `STDDEV()` or range metrics (DECIMAL-cast) |
| G4 | **Feature view scope** | View has focused scope (<15 features). Split wide views using `.slice()` |
| G5 | **Temporal features** | If source has date/timestamp columns, temporal FV has been created — or reason documented |
| G6 | **Model consumers identified** | Feature lineage has been run (lineage/SKILL.md); impact understood |
| G7 | **Inference FV exists** | If model consumes this FV, inference pipeline exists — or reason documented |

#### Inference Feature View Checklist

| # | Check | Criteria |
|---|-------|----------|
| I1 | **Model signature coverage** | All non-ODT model input features present |
| I2 | **Source FV lineage documented** | Inference FV description records source FVs |
| I3 | **ODT features identified** | Unmapped features documented as ODT |
| I4 | **Preprocessing passthrough** | If model has MDT pipeline, FV provides raw columns |
| I5 | **Entity key alignment** | Inference FV entity keys match source FVs |
| I6 | **Refresh frequency** | Matches or exceeds fastest source FV |

**Present results as a table** with columns: Check, Status (Pass/Warn/Fail), Notes.

**⚠️ STOP**: If any item is **Fail**, recommend a specific fix. If any item is **Warn**, explain the trade-off.

---

### Step 7: Remediate Issues

After validation, **ask the user** if they'd like to fix issues found.

For each non-passing item, in priority order (Fail first, then Warn):

1. **Explain** the proposed change
2. **Ask** for approval
3. **Implement** after confirmation
4. **Verify** the fix

**Common remediation patterns** — see `../references/troubleshooting.md` for full list.

If the query changes, a new version must be registered:
```python
fs.register_feature_view(feature_view=updated_fv, version="V02", block=True)
```

After all fixes, **re-run Step 6** to confirm all checks pass.

**⚠️ STOP**: Never implement a fix without user approval.

---

### Step 8: Promote Features (DEV → PROD)

**Schema-based promotion** using zero-copy cloning:
```sql
CREATE OR REPLACE SCHEMA PROD_FEATURE_STORE CLONE DEV_FEATURE_STORE;
```

**Python-based promotion** (controlled recreation):
```python
dev_fs = FeatureStore(session, database, "DEV_FEATURE_STORE", warehouse, CreationMode.FAIL_IF_NOT_EXIST)
prod_fs = FeatureStore(session, database, "PROD_FEATURE_STORE", warehouse, CreationMode.CREATE_IF_NOT_EXIST)

fv = dev_fs.get_feature_view("USER_PURCHASE_FV", "V01")
# Recreate entity and FV in prod with same query and metadata
```

**Validation after promotion**: Schema match, row counts, sample value comparison.

**⚠️ MANDATORY CHECKPOINT**: Confirm target environment before promoting.

---

### Step 9: Update / Delete Feature Views and Entities

**Update description:**
```python
fs.update_feature_view(name="<FV_NAME>", version="<VERSION>", desc="Updated description")
```

**Delete a feature view:**
```python
fs.delete_feature_view("<FV_NAME>", "<VERSION>")
```

**Delete an entity** (must not be referenced by any feature views):
```python
fs.delete_entity("<ENTITY_NAME>")
```

**⚠️ STOP**: Confirm with user before deleting any objects.

---

## Stopping Points

- ✋ Before suspending production feature views
- ✋ Before deleting any objects
- ✋ Before implementing remediation fixes
- ✋ Before promoting to target environment

## Output

- Health status of all feature views
- Validation audit report with Pass/Warn/Fail
- Cost analysis and optimization recommendations
- Promoted feature views (if applicable)

## Next Skill

- If user wants to create new features → **Load** `create/SKILL.md`
- If user wants to adjust pipelines → **Load** `pipelines/SKILL.md`
- If user wants online serving → **Load** `online/SKILL.md`
- If user wants lineage analysis → **Load** `lineage/SKILL.md`
