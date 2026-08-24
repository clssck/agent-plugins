## Context

You are a worker dispatched by the orchestrator. You receive a context pack with inputs.

# Phase 1 — Model Inventory

Scan the dbt project and classify every model as convertible, SKIP, or out-of-scope.

## Inputs

- `<dbt_project>` path
- `<dbt_project>/.dt-migration/stage-1/state/00-test-strategy.json`

## Workflow

### Step 1 — Read dbt project

Manifest resolution chain (try in order):
1. `target/manifest.json` — check freshness vs newest .sql file. If fresh, use directly.
2. `dbt compile` — if manifest stale/missing and dbt auth available. Read-only, regenerates manifest.
3. SQL regex — parse `ref()`/`source()` from .sql files directly. Last resort.

### Step 2 — Classify each model

For each model in the project:

| Materialization | Classification |
|----------------|---------------|
| `table` | Check for DDL blockers → CONVERTIBLE or SKIP |
| `incremental` | OUT_OF_SCOPE (has own refresh strategy) |
| `view` | OUT_OF_SCOPE (no materialization cost) |
| `ephemeral` | OUT_OF_SCOPE (inlined CTE) |
| `dynamic_table` | ALREADY_DT (skip) |

**DDL blockers (→ SKIP):**
- `UUID_STRING()`
- `RANDOM()`
- `WITH RECURSIVE`
- `UNPIVOT`
- `SAMPLE`

Scan model SQL for these patterns. If found → SKIP with reason.

### Step 3 — Query table sizes (optional)

For convertible models, query Snowflake for current sizes:
```sql
SELECT TABLE_NAME, ROW_COUNT, BYTES
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = '<schema>'
  AND TABLE_NAME IN (<model_list>);
```

### Step 4 — Write artifacts

Write to `<dbt_project>/.dt-migration/stage-1/state/`:

`01-inventory.json` — each entry MUST have all fields:
```json
{
  "dbt_project_path": "<path>",
  "test_strategy": "from .dt-migration/stage-1/state/00-test-strategy.json",
  "models": [
    {
      "name": "stg_orders",
      "path": "models/staging/stg_orders.sql",
      "materialization": "table",
      "classification": "CONVERTIBLE",
      "ddl_blocker": null,
      "refs": ["stg_customers"],
      "sources": ["raw.orders"],
      "size_bytes": 1048576
    },
    {
      "name": "audit_trail",
      "path": "models/audit_trail.sql",
      "materialization": "table",
      "classification": "SKIP",
      "ddl_blocker": "UUID_STRING()",
      "refs": [],
      "sources": ["raw.events"],
      "size_bytes": null
    }
  ]
}
```

Required fields per model: `name`, `path`, `materialization`, `classification` (CONVERTIBLE | SKIP | OUT_OF_SCOPE | ALREADY_DT), `ddl_blocker`, `refs`, `sources`.

Also write `01-inventory.md` — human-readable summary.

## Output

Your final text (returned to orchestrator):

```
<N> models scanned
├─ <N> convertible (table → FULL DT)
├─ <N> SKIP (DDL blockers: <list reasons>)
├─ <N> out-of-scope (incremental/view/ephemeral)
└─ <N> already DT
Details: .dt-migration/stage-1/state/01-inventory.md
```
