# Snowflake Materializations and Incremental Models

dbt-snowflake behavior that changes how a model should be materialized, plus the Sanofi
incremental-model rules. Layer defaults (which layer is `view`, `table`, `incremental`)
stay in [general-dbt-guide.md](general-dbt-guide.md#layers-and-materializations).

## Tables, Transience, and Grants

- **dbt-snowflake creates tables as `transient` by default.** Transient tables have no
  Fail-safe and only 1 day of Time Travel by default. Persisted Sanofi layers therefore set
  `+transient: false` at project or folder level; it is not redundant.
- A plain `table` drops and recreates the object every run, which resets Time Travel and
  Fail-safe. Keep it for small lookup/reference data where history does not matter.
- `copy_grants` defaults to `false`. Set `+copy_grants: true` so a rebuild of a table,
  view, or dynamic table (dynamic tables: dbt-snowflake >= 1.11) keeps the object's
  existing grants. Grants themselves stay with the approved schema-management path.
- `cluster_by` adds clustering to tables and incrementals; align it with the
  filter/predicate columns. `secure: true` on consumer views where the schema requires it.

NEVER use `insert_overwrite` on Snowflake to "replace a partition". dbt-snowflake's
`insert_overwrite` is not partition-based: it behaves like `INSERT OVERWRITE`, truncating
and re-inserting the whole table every run, so it keeps the object but erases any rows
the model query does not return — including history, on history-bearing models (SCD2,
PSA, anything where source rows disappear). Use it only when the model query rebuilds
the complete result every run (`overwrite_columns` limits the inserted column list);
otherwise use `merge` (keyed by `unique_key`) or `delete+insert` with
`incremental_predicates`, which preserve unaffected rows and the table's Time Travel
lineage.

## Dynamic Tables

Snowflake dynamic tables are an exception, to use only when the orchestrator cannot meet
the required latency, or for internal helper tables; document the reason in the model
YAML. When one is justified:

- Set `copy_grants: true` (dbt-snowflake >= 1.11; the default `false` drops grants when
  `--full-refresh` recreates it) and `refresh_warehouse` apart from the DDL
  `snowflake_warehouse` (>= 1.11).
- On 1.12 dbt defaults `scheduler` to `DISABLE`, but setting `target_lag` without
  `scheduler` turns Snowflake's scheduler on, so set both deliberately. `DISABLE` with
  `target_lag`, or `ENABLE` without it, is an error.
- `transient` on a dynamic table defaults to `false`; changing it recreates the table.

## Incremental Strategies on Snowflake

| Strategy | Behavior | Use when |
|---|---|---|
| `merge` (default) | Upsert on `unique_key` | Keyed rows that update in place |
| `delete+insert` | Delete target rows matching the batch keys, then insert | Replacing a whole key set or window |
| `append` | Insert only | Immutable events with no reprocessing |
| `insert_overwrite` | Truncate + insert the full result | Full-result rebuilds only (see above) |
| `microbatch` | `delete+insert` per time batch | Large time series with a trusted event time |

- **Non-deterministic merge error** means the batch holds more than one row for a
  `unique_key` that matches a target row (Snowflake `ERROR_ON_NONDETERMINISTIC_MERGE`,
  default `TRUE`). Treat it as a grain bug: deduplicate the batch on the key (for example
  `qualify row_number() over (partition by <key> order by <changed_ts> desc) = 1`) or fix
  the key. dbt's documented workaround is `delete+insert`, and setting the parameter to
  `FALSE` makes Snowflake pick an undefined duplicate for the update; both hide the
  duplicate instead of resolving it, and `delete+insert` writes every duplicate row. The
  error only fires for keys that already match a target row; duplicated new keys are
  inserted once per source copy, silently. Keep the `unique` test on the grain.
- `tmp_relation_type` controls the staging relation for the merge: `view` (default),
  `table` (session-scoped temporary table), or `transient` (a real table under a
  deterministic name). `delete+insert` with a `unique_key` requires a temporary table, not
  a view. With `transient`, concurrent runs of the same model in one schema (shared dev
  schema, overlapping CI and prod) overwrite each other's tmp relation; route it with a
  `snowflake__resolve_incremental_tmp_relation` override or keep schemas per run.

## Incremental Models

For incremental models, verify:

- `unique_key` is correct and truly unique.
- `incremental_strategy` matches the warehouse behavior.
- `on_schema_change` is intentional.
- `cluster_by` aligns with filter or predicate columns.
- `is_incremental()` includes an adequate lookback for late-arriving data.

Separate source and target pruning: `is_incremental()` filters source reads,
`incremental_predicates` filter destination scans, `unique_key` matches incoming rows
to target rows, and `cluster_by` should align with predicate/filter columns.

The source lookback window should be smaller than the target predicate window. Example:
read the last 3 days from source, but let Snowflake scan the last 7 days of the target
so late-arriving data can still merge into existing records.

On the first run, `is_incremental()` is false and the model should build full history.
On later incremental runs, it is true and should read only the configured delta window.

Schema-change choices: `ignore` (the default) for stable schemas, `append_new_columns` for
evolving schemas, `sync_all_columns` cautiously because it can break consumers (it also
drops columns missing from the query), and `fail` when drift should stop the run. No
option backfills new columns on existing rows; backfill with full refresh for
small/medium tables, variable windows for large tables, and direct DML only for
exceptional fixes.

Full refresh may require drop permissions. Treat it as the simple but potentially costly
and disruptive option for large or permission-constrained tables. A resource config
`full_refresh: false` overrides the `--full-refresh` flag (the resource is never fully
refreshed) and `full_refresh: true` forces a rebuild even without the flag, so check the
resource config before assuming the flag rebuilds a protected layer. Snapshots ignore
both.

### Late-Arriving and Multi-Parent Changes

A watermark on the driving table alone loses changes that arrive on another parent. Example:
an orders model filtered on `orders.updated_at` and joined to payments never sees a payment
added to an old order. Before writing the `is_incremental()` filter:

1. **List every parent** the model reads (`dbt ls --select "1+<model>" --exclude <model>`)
   and record its change signal: reliable modified timestamp, load timestamp, append-only
   event time, hash/CDC, or none.
2. **Derive the affected keys** as the union over parents: grain keys whose own row changed
   in the window, plus keys referenced by changed child rows. Then recompute those keys
   from **all** their child rows, not only the new ones; aggregating only the delta
   double-counts or drops values.
   State what detecting the affected keys scans each run: re-aggregating a whole child
   table to find changed keys is correct but costs a full child scan on every run; bound it
   with the child's own change signal or a window, or accept it explicitly.
3. **Add a lookback** sized to the source's documented maximum lateness
   (`>= dateadd(day, -<n>, max(<watermark>))`, not `>`); keep it smaller than any target
   `incremental_predicates` window.
4. **Child without a timestamp:** prefer a load timestamp added by ingestion or staging.
   Otherwise re-derive the key set from a bounded parent window and replace those keys with
   `delete+insert` (or `merge`) on the grain key, or detect child changes with a payload hash
   stored on the target (hash-based pattern below). If neither is affordable, materialize
   as `table`.
5. **Deletes:** an incremental run never removes rows absent from the batch. Handle source
   deletes explicitly (soft-delete flag, key-set `delete+insert`, or scheduled rebuild).
6. **Set `on_schema_change`** explicitly (Sanofi default `append_new_columns`).
7. **Schedule a periodic full refresh** or bounded backfill to repair drift, unless the
   layer is history-bearing with `full_refresh: false`; there, use a bounded backfill only.
8. **Prove it:** unit-test the `is_incremental: true` branch with a late child row
   ([unit-tests.md](unit-tests.md#incremental-models)); in dev, add a late child row for an
   old parent, run incrementally, and compare with a full-refresh build of a copy
   (`audit_helper.compare_relations`).

Shape of a multi-parent key set (adapt names, windows, and the grain to the repo):

```sql
{{ config(materialized='incremental', unique_key='order_id',
          incremental_strategy='delete+insert', on_schema_change='append_new_columns') }}

with
{% if is_incremental() %}
affected_keys as (
    select order_id from {{ ref('stg_orders') }}
    where updated_at >= (select dateadd(day, -3, coalesce(max(order_updated_at), '1900-01-01'::timestamp)) from {{ this }})
    union
    select order_id from {{ ref('stg_payments') }}
    where loaded_at >= (select dateadd(day, -3, coalesce(max(payments_loaded_at), '1900-01-01'::timestamp)) from {{ this }})
),
{% endif %}
orders as (
    select * from {{ ref('stg_orders') }}
    {% if is_incremental() %} where order_id in (select order_id from affected_keys) {% endif %}
),
payments as (
    select * from {{ ref('stg_payments') }}
    {% if is_incremental() %} where order_id in (select order_id from affected_keys) {% endif %}
)
select
    orders.order_id,
    orders.updated_at as order_updated_at,
    max(payments.loaded_at) as payments_loaded_at,
    sum(payments.amount) as amount
from orders
left join payments on payments.order_id = orders.order_id
group by orders.order_id, orders.updated_at
```

### Hash-Based Change Detection

For hash-based incremental models, identify rows with a stable technical key hash
generated from the business key (for example with `dbt_utils.generate_surrogate_key`)
and detect changes with a payload hash generated from the payload columns. Use `merge`
with the technical key as `unique_key`, and exclude audit columns such as creation
timestamps from updates via `merge_exclude_columns` when the repo does so. Select new or
changed rows by hash comparison rather than a time watermark. Truncate/reload
working-layer exceptions should not carry an `is_incremental()` delta filter.

### Filter Placement

Filter placement matters for performance. Read the current high-water mark once in a
small watermark CTE (`select coalesce(max(<changed_ts>), <floor_date>) from {{ this }}`)
and apply that value inside the driving table's `WHERE`, before any joins, so Snowflake
prunes micro-partitions at the storage layer. Applying the same filter in an outer
`WHERE` after all joins have run is a common anti-pattern: Snowflake still scans the full
source and evaluates every join before discarding unchanged rows, which can be slower
than a full rebuild. Guard nullable watermark columns with `OR <col> IS NULL`, and for a
modification date that lives on a left-joined table add `OR <joined>.<date> IS NULL` so
unmatched rows are not silently dropped. If the timestamp is derived, use the same
expression (for example a `GREATEST(...)` of lifecycle timestamps) in the filter.

When the source exposes no reliable modification timestamp, `merge` or `delete+insert`
on the `unique_key` alone (no delta filter) still avoids the drop/recreate of a full
rebuild and preserves Time Travel, even though every source row is still scanned.

Orchestrated pipelines often make runs idempotent and reprocessable by filtering the
source on an explicit run window passed as vars (for example `var('data_interval_start')`
/ `var('data_interval_end')` from the scheduler) instead of, or alongside, a `max()`
watermark. Seed the table with one full refresh, then run incrementally; keep a manual
full refresh available for periodic rebuilds.

### Microbatch

For large time-series models with a reliable event timestamp, consider
`incremental_strategy='microbatch'` (dbt >= 1.9) instead of a hand-written
`is_incremental()` window. On Snowflake dbt implements it with `delete+insert` per
batch, so no `unique_key` is needed and each batch is replaced as a whole. Rules:

- `event_time`, `begin`, and `batch_size` (`hour|day|month|year`) are required; `lookback`
  (default 1) reprocesses prior batches for late data. All values are UTC.
- Set `event_time` on the model AND on every upstream model that should be filtered. An
  upstream without it is fully scanned on every batch. Opt a ref out of filtering only
  deliberately, with `ref('x').render()`.
- The query MUST return exactly one batch window. NEVER add an `is_incremental()` filter.
- Set `full_refresh: false` (consistent with the persistent-layer rule). Reprocess
  history with a bounded backfill; both bounds are required together:
  `dbt run --select <model> --event-time-start "2024-01-01" --event-time-end "2024-02-01"`.
  `dbt retry` reruns only failed batches; Snowflake batches can run concurrently
  (`concurrent_batches`).
- Poor fit: no trustworthy event timestamp, hash-based change detection, or logic that
  needs the previous table state. A reprocessed window drops rows the query no longer
  returns, so do not use it for history-bearing PSA/SCD models.

## Checklist

- Persisted layers set `transient: false`; `copy_grants: true` where grants must survive rebuilds.
- No `insert_overwrite` on a model whose query does not return the complete result.
- Every parent of an incremental model has a change signal or an affected-key re-derivation.
- Lookback sized to real lateness; `on_schema_change` set; deletes handled.
- Merge keys proven unique in the batch; no strategy switch used to hide duplicates.
- `full_refresh` config checked before any `--full-refresh`.

## Sources

- [Snowflake configurations](https://docs.getdbt.com/reference/resource-configs/snowflake-configs): transient default, `copy_grants`, `tmp_relation_type`, `insert_overwrite`/`overwrite_columns`, non-deterministic merge, dynamic tables (`scheduler`, `target_lag`, `refresh_warehouse`, `transient`).
- [Snowflake MERGE](https://docs.snowflake.com/en/sql-reference/sql/merge): `ERROR_ON_NONDETERMINISTIC_MERGE` and duplicate source rows.
- [Incremental models](https://docs.getdbt.com/docs/build/incremental-models): `on_schema_change` options, no backfill, `full_refresh` precedence.
- [Incremental strategies](https://docs.getdbt.com/docs/build/incremental-strategy) and [Microbatch](https://docs.getdbt.com/docs/build/incremental-microbatch).
