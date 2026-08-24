# Workaround Patterns for Task-to-DT Migration

Hybrid patterns for combining dynamic tables with tasks when full migration isn't possible.

---

## Task-Controlled DT Refresh (Fine-Grained Control)

Use when you need custom logic before refreshes (validation, business rules, conditional execution).

**Pattern:** Combine `TARGET_LAG = 'DOWNSTREAM'` with a Task that manually triggers refresh.

```sql
-- Dynamic Table (won't auto-refresh due to DOWNSTREAM with no downstream consumers)
CREATE OR REPLACE DYNAMIC TABLE my_dt
  TARGET_LAG = 'DOWNSTREAM'
  WAREHOUSE = mywh
AS
  SELECT id, transform(col) AS col FROM source_table;

-- Stream to detect changes
CREATE OR REPLACE STREAM source_stream ON TABLE source_table;

-- Task with custom pre-refresh logic
CREATE OR REPLACE TASK refresh_my_dt_task
  WAREHOUSE = mywh
  SCHEDULE = '5 MINUTE'
  WHEN SYSTEM$STREAM_HAS_DATA('source_stream')
AS
BEGIN
  -- Custom pre-refresh checks
  LET row_count INT := (SELECT COUNT(*) FROM source_stream);
  IF (row_count < 10000) THEN  -- Example: only refresh for small batches
    ALTER DYNAMIC TABLE my_dt REFRESH;
  END IF;
  -- Consume stream to advance offset
  CREATE OR REPLACE TEMP TABLE _stream_consume AS SELECT * FROM source_stream;
END;
```

**Benefits:**
- Declarative transformation (DT handles SQL complexity)
- Imperative control over timing (Task decides when to refresh)
- Pre-refresh validation, alerting, or conditional logic
- Can integrate with external systems before refresh

**Use cases:**
- Data quality gates before refresh
- Business hour restrictions
- Dependency on external events
- Cost control (skip refresh if changes are minimal)

---

## DT-Triggered Task (Post-Refresh Actions)

Use when you need to execute custom logic after a dynamic table refreshes.

**Pattern:** Create a stream on an incremental DT, then a triggered task that reacts to DT changes.

```sql
-- Incremental Dynamic Table
CREATE OR REPLACE DYNAMIC TABLE my_dt
  TARGET_LAG = '5 MINUTES'
  WAREHOUSE = mywh
AS
  SELECT id, col FROM source_table;

-- Stream on the DT (only works if DT is incremental)
CREATE OR REPLACE STREAM my_dt_stream ON DYNAMIC TABLE my_dt;

-- Task triggered by DT refresh
CREATE OR REPLACE TASK post_refresh_task
  WAREHOUSE = mywh
  WHEN SYSTEM$STREAM_HAS_DATA('my_dt_stream')
AS
BEGIN
  -- Post-refresh actions
  -- Example: Send notification
  CALL SYSTEM$SEND_EMAIL('alerts@company.com', 'DT Refreshed', 
    'my_dt refreshed with ' || (SELECT COUNT(*) FROM my_dt_stream) || ' changes');
  
  -- Example: Load to external system
  COPY INTO @external_stage/export/ FROM (SELECT * FROM my_dt_stream);
  
  -- Consume stream
  CREATE OR REPLACE TEMP TABLE _consume AS SELECT * FROM my_dt_stream;
END;
```

**Requirements:**
- Dynamic table must use **incremental refresh** (streams not supported on full-refresh DTs)
- Check refresh mode: `SELECT refresh_mode FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES()) WHERE name = 'MY_DT';`

**Use cases:**
- Post-refresh notifications or alerts
- Triggering downstream processes that cannot be dynamic tables
- Audit logging of changes
- Data export to external systems
- Hybrid pipelines (DT → Task → external destination)
