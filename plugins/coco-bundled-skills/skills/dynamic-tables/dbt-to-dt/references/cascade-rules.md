# Cascade Rules — Dynamic Table Pipeline Shape Resolution

## 1. Core Cascade Rule: FULL Upstream Forces Downstream FULL

The fundamental Snowflake constraint: a FULL-refresh upstream dynamic table forces all downstream DTs to also become FULL — unless the PK escape hatch applies.

**Rule:** If any upstream DT has `refresh_mode='full'`:
- Check if **every** FULL upstream DT has a system-derived unique key (from GROUP BY or QUALIFY ROW_NUMBER)
- If ALL FULL upstreams have keys: downstream may still support ADAPTIVE. Attempt `refresh_mode='adaptive'` — if creation fails, fall back to FULL.
- If ANY FULL upstream lacks a key: the downstream model must be `refresh_mode='full'`

**Impact:** A single FULL DT without a system-derived key can cascade FULL status to all transitive downstream INCREMENTAL models in the pipeline.


## 2. PK Escape Hatch — System-Derived Unique Key (GA Apr 2026)

When a FULL upstream has a system-derived unique key, Snowflake can compute row-level changes across full refreshes, enabling downstream INC.

### Valid Key Sources (produce `SYS_CONSTRAINT_DERIVED_PK`)

**Derived from query shape:**
- `GROUP BY col1, col2` (basic columns only) — the GROUP BY columns form a derived key
- `QUALIFY ROW_NUMBER() OVER (PARTITION BY pk_col ...) = 1` — the partition column is a derived key

**Passthrough from base table:**
- Base table with `PRIMARY KEY ... RELY` — key propagates if column is passed through without functions/casts

### Invalid (do NOT produce system-derived keys)

- `GROUP BY ROLLUP(...)`, `GROUP BY CUBE(...)`, `GROUP BY GROUPING SETS(...)` — subtotal rows break uniqueness
- Inline `PRIMARY KEY RELY` on the DT itself (syntax not supported; use query shape instead)

### Verification

```sql
SHOW UNIQUE KEYS IN <upstream_dt>;
```

If this returns `SYS_CONSTRAINT_DERIVED_PK` rows, downstream INC is possible. If empty, downstream must be FULL.

### Important: Must use explicit ADAPTIVE

To create INC downstream of a FULL DT with a system-derived key, you must set `REFRESH_MODE = ADAPTIVE` explicitly. `REFRESH_MODE = AUTO` still resolves to FULL in this scenario.

Note: masking policies on PK columns degrade PK-based CT optimization (performance) but do NOT block INCREMENTAL refresh on regular tables with standard change tracking.


## 3. Keep-as-Table-with-CT Alternative

A regular table with `CHANGE_TRACKING=ON` is a valid INCREMENTAL-compatible upstream. It avoids the cascade entirely because it is not a FULL DT — it is a regular table that exposes change streams.

### When to Use

When a model would be classified as FULL DT and has downstream INCREMENTAL consumers, keeping it as a table with CT is often the safest choice. Especially when:
1. The source has no change tracking (UNION ALL view, no CT)
2. Converting to FULL DT would cascade to many transitive INC downstreams
3. Table + CT ON is functionally equivalent to INC DT for downstream consumers

### Enabling CT via dbt

To persist change tracking across rebuilds, use a `post_hook`:

```sql
{{ config(materialized='table', post_hook="ALTER TABLE {{ this }} SET CHANGE_TRACKING = TRUE") }}
```

### Risk: Full-refresh Resets CT

`CREATE OR REPLACE TABLE` during `dbt run --full-refresh` resets change tracking. Ensure the DAG never runs this model with `--full-refresh` after downstream DTs exist, or re-enable CT immediately after.


## 4. Source-with-No-CT Cascade Implication

A source table (or view) without change tracking forces the model reading from it to either stay as a table-with-CT or use another workaround.

### Resolution by Ownership

**If the user owns the source table:**
```sql
ALTER TABLE <source_table> SET CHANGE_TRACKING = TRUE;
```

**If the table is owned by another team:**
The model reading from it should stay as `materialized='table'`. DT creation will fail without MODIFY privileges on the source.

### Common Patterns That Lack CT

- `UNION ALL` views — no change tracking support
- Tables owned by other teams — privilege blocker (need MODIFY to enable CT)
- Incremental models — CT can be disrupted if the post_hook is not maintained

### CT Disruption Risk

For incremental source models that feed downstream DTs: if `change_tracking` is ever disrupted on the source, the entire downstream DT pipeline fails. Verify that the project-level `post_hook` keeps CT enabled after each incremental rebuild.


## 5. DAG Walk Algorithm

The cascade rules are applied via a topological walk from sources downward.

### Steps

1. **Build the graph** from `dbt list --output json --resource-type model` or `target/manifest.json` (after `dbt compile`). Do not manually trace `ref()` calls across files.

2. **Walk topologically (roots first).** For each model classified as INCREMENTAL:
   - Check its upstream `ref()` targets
   - If all upstream DTs have been resolved as INCREMENTAL in this pass (or are regular tables with `change_tracking = ON`) — confirm as `refresh_mode='adaptive'`
   - If any upstream DT has been resolved as FULL — apply the cascade rule (Section 1)

3. **Output per-model decision** — one of:
   - DT with `refresh_mode='adaptive'`
   - DT with `refresh_mode='full'`
   - Keep as `materialized='table'` (DDL blocker, pipeline shape decision, or change tracking constraint)

### Pipeline Shape Options for FULL Models with Downstream INC

When a FULL model has downstream INCREMENTAL consumers, present three choices:

1. **Keep as table (safest):** Don't convert the FULL model to DT — keeps downstream INCREMENTAL-eligible
2. **Convert with primary key-based change tracking (if available):** If the FULL model has a derived or declared primary key, downstream INCREMENTAL may still work
3. **Accept cascade:** Convert to FULL DT and accept that downstream models also become FULL


## Quick Decision Matrix

| Upstream State | Has PK? | Downstream Can Be INC? |
|---|---|---|
| DT INCREMENTAL | N/A | Yes |
| Table with CT ON | N/A | Yes |
| DT FULL | Yes (derived or declared) | Maybe — attempt, fall back to FULL |
| DT FULL | No | No — must be FULL |
| Source without CT | N/A | Model must stay as table |
