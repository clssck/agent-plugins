# Dynamic Tables SQL Syntax Reference

Complete SQL syntax for dynamic table operations.

---

## CREATE DYNAMIC TABLE

```sql
CREATE [ OR REPLACE ] [ TRANSIENT ] DYNAMIC TABLE [ IF NOT EXISTS ] <name>
  TARGET_LAG = { '<time>' | DOWNSTREAM }
  WAREHOUSE = <warehouse_name>
  [ INITIALIZATION_WAREHOUSE = <warehouse_name> ]
  [ REFRESH_MODE = { AUTO | FULL | INCREMENTAL | ADAPTIVE } ]
  [ INITIALIZE = { ON_CREATE | ON_SCHEDULE } ]
  [ FROZEN WHERE ( <predicate> ) ]
  [ BACKFILL FROM <source_table> ]
  [ DATA_RETENTION_TIME_IN_DAYS = <integer> ]
  [ MAX_DATA_EXTENSION_TIME_IN_DAYS = <integer> ]
  [ CLUSTER BY ( <expr> [ , ... ] ) ]
  [ COMMENT = '<comment>' ]
  AS <query>
```

### Custom Incremental Variant (REFRESH USING)

```sql
CREATE [ OR REPLACE ] DYNAMIC TABLE <name> (
  <col_name> <col_type> [ , ... ]
)
  TARGET_LAG = { '<time>' | DOWNSTREAM }
  WAREHOUSE = <warehouse_name>
  [ INITIALIZE = { ON_CREATE | ON_SCHEDULE } ]
  [ COMMENT = '<comment>' ]
  REFRESH USING (
    { MERGE INTO SELF AS <alias> USING ( <subquery> ) AS <src> ON <condition> ... }
    |
    { INSERT INTO SELF SELECT ... FROM <source> [ CHANGES(...) ] ... }
  );
```

**Key differences from standard syntax:**
- Explicit column list required (no schema inference)
- `REFRESH USING` replaces `AS <query>`
- No `REFRESH_MODE` parameter required (defaults to `CUSTOM_INCREMENTAL` when `REFRESH USING` is present; `AUTO` also resolves to it). Optional to specify explicitly.
- Uses `SELF` keyword to reference the DT's own state
- `CHANGES()` clause reads incremental changes from source tables

See [references/custom-incrementalization.md](custom-incrementalization.md) for full semantics.

### Required Parameters

| Parameter | Description |
|-----------|-------------|
| `TARGET_LAG` | Data freshness requirement. Time value (e.g., `'5 minutes'`) or `DOWNSTREAM` |
| `WAREHOUSE` | Virtual warehouse for refresh operations |
| `AS <query>` | SELECT statement defining the transformation |

### Optional Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `REFRESH_MODE` | `AUTO` | `AUTO`, `FULL`, `INCREMENTAL`, or `ADAPTIVE` |
| `INITIALIZE` | `ON_CREATE` | `ON_CREATE` (immediate) or `ON_SCHEDULE` (deferred) |
| `INITIALIZATION_WAREHOUSE` | - | Separate warehouse for initial/reinitialization refreshes. Use a larger warehouse for the initial full scan, keep a smaller one for steady-state. Can also be set/unset via ALTER. |
| `TRANSIENT` | - | No Fail-safe, reduced storage costs |
| `FROZEN WHERE` | - | Predicate defining rows that won't change. **Formerly `IMMUTABLE WHERE`** — that keyword is the legacy alias; existing/older dynamic tables and their `GET_DDL` may still show `IMMUTABLE WHERE`, so recognize and preserve whichever a DT already uses. |
| `BACKFILL FROM` | - | Source table for initial data (requires `FROZEN WHERE`) |

### TARGET_LAG Values

- **Time-based**: `'1 minute'`, `'5 minutes'`, `'1 hour'`, `'1 day'`
- **DOWNSTREAM**: Refresh only when downstream DTs need it (for intermediate tables)

### REFRESH_MODE Values

| Mode | Description | Use When |
|------|-------------|----------|
| `AUTO` | Snowflake chooses optimal mode | Development, testing |
| `INCREMENTAL` | Process only changed data | Simple queries, small changes |
| `FULL` | Recompute entire table | Complex queries, unsupported constructs |
| `ADAPTIVE` | Snowflake refreshes incrementally, but automatically reinitializes (full recompute) for individual refresh cycles where the changed data is large enough that incremental maintenance no longer pays off | Incrementalizable queries with bursty / heavy base-table change, or many changing inputs under a join — lets the system pick per refresh instead of locking in one mode |

### Examples

**Basic dynamic table:**
```sql
CREATE DYNAMIC TABLE analytics.sales_summary
  TARGET_LAG = '10 minutes'
  WAREHOUSE = compute_wh
  AS
    SELECT 
      region,
      DATE_TRUNC('day', order_date) as order_day,
      SUM(amount) as total_sales
    FROM raw.orders
    GROUP BY 1, 2;
```

**Intermediate table in pipeline:**
```sql
CREATE DYNAMIC TABLE staging.enriched_orders
  TARGET_LAG = DOWNSTREAM
  WAREHOUSE = compute_wh
  REFRESH_MODE = ADAPTIVE
  AS
    SELECT o.*, c.customer_name
    FROM raw.orders o
    JOIN raw.customers c ON o.customer_id = c.id;
```

**With immutability constraint:**
```sql
CREATE DYNAMIC TABLE analytics.historical_metrics
  TARGET_LAG = '1 hour'
  WAREHOUSE = compute_wh
  FROZEN WHERE (event_date < CURRENT_DATE() - 7)
  AS
    SELECT * FROM raw.events;
```

**Transient (reduced storage costs):**
```sql
CREATE TRANSIENT DYNAMIC TABLE temp.daily_agg
  TARGET_LAG = '1 hour'
  WAREHOUSE = compute_wh
  AS
    SELECT DATE(ts) as day, COUNT(*) as cnt
    FROM raw.events
    GROUP BY 1;
```

---

## CREATE OR ALTER DYNAMIC TABLE

Idempotent declarative DDL — applies the minimal change to reach the desired state. Preferred over `CREATE OR REPLACE` for both creating and modifying dynamic tables.

```sql
CREATE OR ALTER [ TRANSIENT ] DYNAMIC TABLE <name> (
    <col_name> <col_type>
      [ COLLATE '<collation_specification>' ]
      [ COMMENT '<string_literal>' ]
    [ , ... ]
  )
  TARGET_LAG = { '<num> { seconds | minutes | hours | days }' | DOWNSTREAM }
  [ SCHEDULER = DISABLE | ENABLE ]
  WAREHOUSE = <warehouse_name>
  [ INITIALIZATION_WAREHOUSE = <warehouse_name> ]
  [ REFRESH_MODE = { AUTO | FULL | INCREMENTAL | ADAPTIVE | CUSTOM_INCREMENTAL } ]
  [ INITIALIZE = { ON_CREATE | ON_SCHEDULE } ]
  [ CLUSTER BY ( <expr> [ , ... ] ) ]
  [ DATA_RETENTION_TIME_IN_DAYS = <integer> ]
  [ MAX_DATA_EXTENSION_TIME_IN_DAYS = <integer> ]
  [ COMMENT = '<string_literal>' ]
  [ REQUIRE USER ]
  [ FROZEN WHERE ( <expr> ) ]
  [ BACKFILL FROM <table_name> ]
  [ START AT ... ]
  [ EXECUTE AS USER <user_name> ... ]
  [ ROW_TIMESTAMP = { TRUE | FALSE } ]
  { AS <query> | REFRESH USING ( <dml_statement> ) }
```

**Key differences from `CREATE [ OR REPLACE ]`:**
- No `IF NOT EXISTS`, `COPY GRANTS`, `COPY TAGS`
- No `ROW ACCESS POLICY`, `AGGREGATION POLICY`, `TAG`, `CONTACT` in the statement (use separate `ALTER`)
- Column-level masking policies, projection policies, tags not supported in column list
- `BACKFILL FROM` and `START AT` cannot be changed after creation
- `TRANSIENT` flag cannot be changed (adding or removing TRANSIENT on an existing DT fails)

**Downstream protection**: Unlike `CREATE OR REPLACE`, this command does **not** cascade reinitialization to downstream incremental dynamic tables.

See [create-or-alter-guidance.md](create-or-alter-guidance.md) for reinit trigger reference, column change rules, and property omission behavior.

### Examples

**Idempotent create (first run creates, subsequent runs are no-ops if unchanged):**
```sql
CREATE OR ALTER DYNAMIC TABLE analytics.clean_events (
    event_id    NUMBER,
    event_type  VARCHAR,
    event_ts    TIMESTAMP_NTZ
)
  TARGET_LAG = '10 minutes'
  WAREHOUSE = compute_wh
  REFRESH_MODE = ADAPTIVE
  INITIALIZE = ON_SCHEDULE
  AS
    SELECT event_id, event_type, event_ts
    FROM raw.events
    WHERE event_type IS NOT NULL;
```

**Property-only update (swap warehouse — no reinit):**
```sql
CREATE OR ALTER DYNAMIC TABLE analytics.clean_events (
    event_id    NUMBER,
    event_type  VARCHAR,
    event_ts    TIMESTAMP_NTZ
)
  TARGET_LAG = '10 minutes'
  WAREHOUSE = transform_wh_xl        -- changed from compute_wh
  REFRESH_MODE = ADAPTIVE
  INITIALIZE = ON_SCHEDULE
  AS
    SELECT event_id, event_type, event_ts
    FROM raw.events
    WHERE event_type IS NOT NULL;
```

**Add a column (reinitializes — query changes):**
```sql
CREATE OR ALTER DYNAMIC TABLE analytics.clean_events (
    event_id      NUMBER,
    event_type    VARCHAR,
    event_ts      TIMESTAMP_NTZ,
    region_code   VARCHAR          -- new column appended at end
)
  TARGET_LAG = '10 minutes'
  WAREHOUSE = transform_wh_xl
  REFRESH_MODE = ADAPTIVE
  INITIALIZE = ON_SCHEDULE
  DATA_RETENTION_TIME_IN_DAYS = 7  -- carry forward; omitting would reset to default
  AS
    SELECT event_id, event_type, event_ts, region_code
    FROM raw.events
    WHERE event_type IS NOT NULL;
```

**Switch refresh mode INCREMENTAL → FULL (reinitializes this table; downstream DTs protected):**
```sql
CREATE OR ALTER DYNAMIC TABLE analytics.clean_events (
    event_id      NUMBER,
    event_type    VARCHAR,
    event_ts      TIMESTAMP_NTZ,
    region_code   VARCHAR
)
  TARGET_LAG = '10 minutes'
  WAREHOUSE = transform_wh_xl
  REFRESH_MODE = FULL              -- changed from INCREMENTAL
  INITIALIZE = ON_SCHEDULE
  DATA_RETENTION_TIME_IN_DAYS = 7  -- carry forward; omitting would reset to default
  AS
    SELECT event_id, event_type, event_ts, region_code
    FROM raw.events
    WHERE event_type IS NOT NULL;
```

---

## ALTER DYNAMIC TABLE

```sql
ALTER DYNAMIC TABLE [ IF EXISTS ] <name> { <action> | <property_action> }
```

### Actions

| Action | Syntax | Description |
|--------|--------|-------------|
| Suspend | `SUSPEND` | Stop automatic refreshes |
| Resume | `RESUME` | Resume automatic refreshes |
| Manual Refresh | `REFRESH` | Trigger immediate refresh |
| Add Immutability | `ADD FROZEN WHERE (<predicate>)` | Add immutability constraint (legacy: `ADD IMMUTABLE WHERE`) |
| Drop Immutability | `DROP FROZEN WHERE` | Remove immutability constraint (legacy: `DROP IMMUTABLE`) |

### Property Actions

```sql
ALTER DYNAMIC TABLE <name> SET
  [ TARGET_LAG = { '<time>' | DOWNSTREAM } ]
  [ WAREHOUSE = <warehouse_name> ]
  [ INITIALIZATION_WAREHOUSE = <warehouse_name> ]
  [ DATA_RETENTION_TIME_IN_DAYS = <integer> ]
  [ MAX_DATA_EXTENSION_TIME_IN_DAYS = <integer> ]
  [ COMMENT = '<comment>' ]

ALTER DYNAMIC TABLE <name> UNSET
  INITIALIZATION_WAREHOUSE
```

### Examples

**Suspend and resume:**
```sql
ALTER DYNAMIC TABLE analytics.sales_summary SUSPEND;
ALTER DYNAMIC TABLE analytics.sales_summary RESUME;
```

**Force immediate refresh:**
```sql
ALTER DYNAMIC TABLE analytics.sales_summary REFRESH;
```

**Change target lag:**
```sql
ALTER DYNAMIC TABLE analytics.sales_summary SET TARGET_LAG = '30 minutes';
```

**Add immutability constraint:**
```sql
ALTER DYNAMIC TABLE analytics.sales_summary 
ADD FROZEN WHERE (order_date < CURRENT_DATE() - 30);
```

**Remove immutability constraint:**
```sql
ALTER DYNAMIC TABLE analytics.sales_summary DROP FROZEN WHERE;
```

**Set initialization warehouse (larger WH for initial/reinit refreshes only):**
```sql
ALTER DYNAMIC TABLE analytics.sales_summary SET INITIALIZATION_WAREHOUSE = large_wh;
```

**Remove initialization warehouse (use primary warehouse for all refreshes):**
```sql
ALTER DYNAMIC TABLE analytics.sales_summary UNSET INITIALIZATION_WAREHOUSE;
```

---

## DROP DYNAMIC TABLE

```sql
DROP DYNAMIC TABLE [ IF EXISTS ] <name> [ CASCADE | RESTRICT ]
```

### Options

| Option | Description |
|--------|-------------|
| `CASCADE` | Also drop dependent objects |
| `RESTRICT` | Fail if dependent objects exist (default) |

### Examples

```sql
DROP DYNAMIC TABLE analytics.sales_summary;
DROP DYNAMIC TABLE IF EXISTS staging.temp_data CASCADE;
```

---

## UNDROP DYNAMIC TABLE

Restore a dropped dynamic table (within retention period).

```sql
UNDROP DYNAMIC TABLE <name>
```

### Example

```sql
UNDROP DYNAMIC TABLE analytics.sales_summary;
```

---

## SHOW DYNAMIC TABLES

```sql
SHOW DYNAMIC TABLES [ LIKE '<pattern>' ]
  [ IN { ACCOUNT | DATABASE [ <db_name> ] | SCHEMA [ <schema_name> ] } ]
```

### Output Columns

| Column | Description |
|--------|-------------|
| `name` | Dynamic table name |
| `database_name` | Database containing the DT |
| `schema_name` | Schema containing the DT |
| `warehouse` | Warehouse used for refreshes |
| `target_lag` | Configured target lag |
| `refresh_mode` | AUTO, FULL, INCREMENTAL, or ADAPTIVE |
| `scheduling_state` | ACTIVE or SUSPENDED |

### Examples

```sql
SHOW DYNAMIC TABLES IN SCHEMA analytics;
SHOW DYNAMIC TABLES LIKE 'sales%';
```

---

## DESCRIBE DYNAMIC TABLE

```sql
DESCRIBE DYNAMIC TABLE <name>
-- or
DESC DYNAMIC TABLE <name>
```

### Output

Returns column information for the dynamic table (same as regular tables).

---

## GET_DDL for Dynamic Tables

```sql
SELECT GET_DDL('DYNAMIC_TABLE', '<fully_qualified_name>');
```

### Example

```sql
SELECT GET_DDL('DYNAMIC_TABLE', 'analytics.reporting.sales_summary');
```

Returns the CREATE DYNAMIC TABLE statement that would recreate the table.

---

## Change Tracking (Required for Base Tables)

```sql
-- Enable change tracking
ALTER TABLE <table_name> SET CHANGE_TRACKING = TRUE;

-- Check change tracking status
SHOW TABLES LIKE '<table_name>';
-- Look for change_tracking column = TRUE
```

---

## Quick Reference

| Operation | Command |
|-----------|---------|
| Create DT | `CREATE DYNAMIC TABLE ... AS SELECT ...` |
| Create transient | `CREATE TRANSIENT DYNAMIC TABLE ...` |
| Suspend | `ALTER DYNAMIC TABLE ... SUSPEND` |
| Resume | `ALTER DYNAMIC TABLE ... RESUME` |
| Manual refresh | `ALTER DYNAMIC TABLE ... REFRESH` |
| Change lag | `ALTER DYNAMIC TABLE ... SET TARGET_LAG = '...'` |
| Set init warehouse | `ALTER DYNAMIC TABLE ... SET INITIALIZATION_WAREHOUSE = ...` |
| Add immutability | `ALTER DYNAMIC TABLE ... ADD FROZEN WHERE (...)` |
| Drop | `DROP DYNAMIC TABLE ...` |
| Undrop | `UNDROP DYNAMIC TABLE ...` |
| List | `SHOW DYNAMIC TABLES` |
| Describe | `DESC DYNAMIC TABLE ...` |
| Get DDL | `SELECT GET_DDL('DYNAMIC_TABLE', '...')` |
