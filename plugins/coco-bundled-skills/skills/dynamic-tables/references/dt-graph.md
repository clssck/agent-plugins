# Pipeline Dependencies Reference

Functions for understanding dynamic table dependency graphs (DAG structure) and retrieving DT definitions.

---

## DYNAMIC_TABLE_GRAPH_HISTORY()

Returns dependency graph information for dynamic tables — which tables feed into which.

### Syntax

```sql
SELECT * FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_GRAPH_HISTORY(
  [ AS_OF => <timestamp_expr> ]
  [ , HISTORY_START => <timestamp_expr> [ , HISTORY_END => <timestamp_expr> ] ]
));
```

All arguments are optional. If none are provided, only the most recent description of existing dynamic tables is returned.

### Key Columns

| Column | Type | Description |
|--------|------|-------------|
| `name` | STRING | Dynamic table name |
| `qualified_name` | STRING | Fully qualified name — use to join with `DYNAMIC_TABLE_REFRESH_HISTORY` output |
| `inputs` | ARRAY of OBJECTs | Upstream dependencies. Each object has `name` (fully qualified) and `kind` (`TABLE`, `VIEW`, or `DYNAMIC TABLE`) |
| `query_text` | STRING | The SELECT statement defining this dynamic table |
| `scheduling_state` | OBJECT | JSON with `state` (`ACTIVE` or `SUSPENDED`), optional `reason_code`, `reason_message`, `suspended_on`, `resumed_on` |
| `target_lag_type` | STRING | `USER_DEFINED` or `DOWNSTREAM` |
| `target_lag_sec` | NUMBER | Target lag in seconds |
| `valid_from` | TIMESTAMP_LTZ | Start of the time range this description was valid (new entry created on each DDL change) |
| `valid_to` | TIMESTAMP_LTZ | End of validity. NULL if this is the current version |
| `alter_trigger` | ARRAY | Why this entry was created: `CREATE_DYNAMIC_TABLE`, `ALTER_TARGET_LAG`, `SUSPEND`, `RESUME`, `ALTER_WAREHOUSE`, `REPLICATION_REFRESH`, or `NONE` |

### Example Queries

```sql
USE DATABASE MY_DB;

-- View all current dependencies
SELECT name, inputs, scheduling_state:"state"::STRING as state, target_lag_type
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_GRAPH_HISTORY());

-- Find upstream tables for a specific DT
SELECT name, inputs
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_GRAPH_HISTORY())
WHERE name = 'MY_DT';

-- Find downstream tables that depend on a specific table
SELECT name, inputs
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_GRAPH_HISTORY())
WHERE ARRAY_CONTAINS('MY_UPSTREAM_TABLE'::VARIANT, inputs);

-- View version history of a DT (shows CREATE OR REPLACE, ALTER events)
SELECT name, valid_from, valid_to, alter_trigger, target_lag_sec, query_text
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_GRAPH_HISTORY(
  HISTORY_START => DATEADD('day', -7, CURRENT_TIMESTAMP())
))
WHERE name = 'MY_DT'
ORDER BY valid_from DESC;
```

---

## GET_DDL()

Retrieve the DDL definition of a dynamic table.

### Syntax

```sql
SELECT GET_DDL('DYNAMIC_TABLE', '<fully_qualified_name>');
```

### Example

```sql
SELECT GET_DDL('DYNAMIC_TABLE', 'MY_DB.MY_SCHEMA.MY_DT');
```
