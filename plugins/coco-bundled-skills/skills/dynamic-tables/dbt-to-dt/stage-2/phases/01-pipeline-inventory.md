## Context

You are a worker dispatched by the orchestrator.

# Phase 1 — Pipeline Inventory

Read the DAG of existing FULL DTs, identify topological layers, determine which layer to work on.

## Inputs

- `<dbt_project>` path (for manifest.json)
- `<dbt_project>/.dt-migration/stage-2/state/` (check for existing layer-N-report.json files)

## Workflow

### Step 1 — Read the DAG

Use manifest.json (preferred) or DYNAMIC_TABLE_GRAPH_HISTORY (fallback):

**From manifest.json:**
```
For each node where config.materialized == 'dynamic_table':
  - name
  - depends_on.nodes (upstream refs)
  - config.refresh_mode (current: should be 'full' for candidates)
```

**Fallback — DYNAMIC_TABLE_GRAPH_HISTORY:**
```sql
SELECT NAME, SCHEMA_NAME, DATABASE_NAME, INPUTS, SCHEDULER, QUERY_TEXT
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_GRAPH_HISTORY(
  NAME_PREFIX => '<db>.<schema>.'
))
WHERE VALID_TO IS NULL;
```

### Step 2 — Check for blocked annotations

For each FULL DT model file, check for `-- DT-INC-BLOCKED:` comment:
- If present AND model SQL unchanged since last assessment → mark as "previously blocked, skipping"
- If present BUT model SQL changed → clear the annotation, include for re-assessment in Phase 2

### Step 3 — Compute topological layers

```
Layer 0: DTs whose INPUTS are ALL base tables/views (not other DTs)
Layer 1: DTs whose INPUTS include Layer 0 DTs (but no higher)
Layer 2: DTs whose INPUTS include Layer 1 DTs
...
```

### Step 4 — Determine current layer

Read `<dbt_project>/.dt-migration/stage-2/state/layer-*-report.json` files:
- If `layer-0-report.json` exists → Layer 0 is done, current = Layer 1
- If no layer reports → current = Layer 0

### Step 5 — Show current state

Write `<dbt_project>/.dt-migration/stage-2/state/01-pipeline-state.json`:
- Full DAG with layer annotations
- Per-DT: name, current refresh_mode, layer number, blocked status
- Highlight current layer

## Output

```
Pipeline: <N> FULL DTs across <L> layers

Layer 0 (leaf — reads from base tables):
  source(raw_orders) ──→ stg_orders [FULL]
  source(raw_users)  ──→ stg_users [FULL]
  source(raw_events) ──→ stg_events [FULL, DT-INC-BLOCKED: DISTINCT]

Layer 1 (reads from Layer 0 DTs):
  stg_orders ──→ fct_revenue [FULL]
  stg_users  ──→ fct_user_activity [FULL]

Current layer: <N> (<count> models, <blocked> previously blocked)
Details: .dt-migration/stage-2/state/01-pipeline-state.json
```
