# Monitoring Functions Reference

Router for dynamic table monitoring and analysis functions. Load the specific reference for your scenario.

## Which Reference to Load

| Need | Load | Covers |
|------|------|--------|
| Current health / status | [dt-state.md](dt-state.md) | `SHOW DYNAMIC TABLES` + `INFORMATION_SCHEMA.DYNAMIC_TABLES()` — configuration, lag metrics, `scheduling_state` format differences |
| Refresh outcomes + performance analysis | [dt-refresh-analysis.md](dt-refresh-analysis.md) | `DYNAMIC_TABLE_REFRESH_HISTORY()`, `GET_QUERY_OPERATOR_STATS`, `QUERY_HISTORY_BY_WAREHOUSE`, `ACCOUNT_USAGE.QUERY_HISTORY` — including privilege requirements |
| Pipeline dependencies | [dt-graph.md](dt-graph.md) | `DYNAMIC_TABLE_GRAPH_HISTORY()` + `GET_DDL()` |

---

## Critical Usage Requirements

These apply to **all** INFORMATION_SCHEMA functions below.

### ⛔ MANDATORY: Set Database Context First

**ALWAYS** run `USE DATABASE` before calling any INFORMATION_SCHEMA function (required for execution, not for scoping):
```sql
-- ✅ CORRECT: Set database context first
USE DATABASE ANY_DATABASE;
SELECT * FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES(...));

-- ❌ WRONG: Will fail with "Invalid identifier"
SELECT * FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES(...));
```

### Named Parameters

INFORMATION_SCHEMA functions use **named parameters** (not positional):
```sql
-- ✅ CORRECT: Named parameters
SELECT * FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
  NAME => 'MY_DB.MY_SCHEMA.MY_DT',
  ERROR_ONLY => TRUE
));

-- ❌ WRONG: Positional parameters
SELECT * FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
  'MY_DB.MY_SCHEMA.MY_DT',
  TRUE
));
```
