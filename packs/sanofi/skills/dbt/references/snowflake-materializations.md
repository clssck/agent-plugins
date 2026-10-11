# Snowflake Materializations and Incremental Models

dbt-snowflake defaults that change how a model should be materialized, plus the Sanofi incremental-model rules. Governing principle: a persisted relation keeps its history, grants, and Time Travel lineage across runs, so prefer strategies that update in place over drop/recreate or truncate. Layer defaults (which layer is `view`, `table`, `incremental`) stay in [general-dbt-guide.md](general-dbt-guide.md#layers-and-materializations).

## Tables, Transience, and Grants

- **Transient by default.** dbt-snowflake creates tables as `transient`: no Fail-safe, 1 day of Time Travel by default. Persisted Sanofi layers therefore set `+transient: false` at project or folder level; not redundant.
- **Plain `table` drops and recreates** every run → resets Time Travel and Fail-safe. Keep it for small lookup/reference data where history does not matter.
- **`copy_grants` defaults to `false`.** Set `+copy_grants: true` so a rebuild of a table, view, or dynamic table (dynamic tables: dbt-snowflake >= 1.11) keeps existing grants. Grants themselves stay with the approved schema-management path.
- **`cluster_by`** adds clustering to tables and incrementals; align it with filter/predicate columns. `secure: true` on consumer views where the schema requires it.

**NEVER use `insert_overwrite` to "replace a partition".** dbt-snowflake's `insert_overwrite` is not partition-based: it behaves like `INSERT OVERWRITE`, truncating and re-inserting the whole table every run. It keeps the object but erases every row the model query does not return — including history on history-bearing models (SCD2, PSA, anything where source rows disappear). Use it only when the query rebuilds the complete result every run (`overwrite_columns` limits the inserted column list); otherwise `merge` (keyed by `unique_key`) or `delete+insert` with `incremental_predicates`, which preserve unaffected rows and Time Travel lineage.

## Dynamic Tables

Exception only: when the orchestrator cannot meet the required latency, or for internal helper tables; document the reason in the model YAML. When justified:

- **`copy_grants: true`** (dbt-snowflake >= 1.11; default `false` drops grants when `--full-refresh` recreates it) and `refresh_warehouse` apart from the DDL `snowflake_warehouse` (>= 1.11).
- **Set `scheduler` and `target_lag` together.** On 1.12 dbt defaults `scheduler` to `DISABLE`, but `target_lag` without `scheduler` turns Snowflake's scheduler on. `DISABLE` with `target_lag`, or `ENABLE` without it → error.
- **`transient`** on a dynamic table defaults to `false`; changing it recreates the table.

## Incremental Strategies on Snowflake

| Strategy | Behavior | Use when |
|---|---|---|
| `merge` (default) | Upsert on `unique_key` | Keyed rows that update in place |
| `delete+insert` | Delete target rows matching the batch keys, then insert | Replacing a whole key set or window |
| `append` | Insert only | Immutable events with no reprocessing |
| `insert_overwrite` | Truncate + insert the full result | Full-result rebuilds only (see above) |
| `microbatch` | `delete+insert` per time batch | Large time series with a trusted event time |

- **Non-deterministic merge error = grain bug.** The batch holds more than one row for a `unique_key` matching a target row (Snowflake `ERROR_ON_NONDETERMINISTIC_MERGE`, default `TRUE`). Deduplicate the batch on the key (e.g. `qualify row_number() over (partition by <key> order by <changed_ts> desc) = 1`) or fix the key. dbt's documented workaround (`delete+insert`) and setting the parameter to `FALSE` (Snowflake picks an undefined duplicate) both hide the duplicate; `delete+insert` writes every duplicate row. The error fires only for keys already in the target; duplicated new keys are inserted once per source copy, silently. Keep the `unique` test on the grain.
- **`tmp_relation_type`** controls the merge staging relation: `view` (default), `table` (session-scoped temporary table), `transient` (real table, deterministic name). `delete+insert` with a `unique_key` requires a temporary table, not a view. With `transient`, concurrent runs of one model in one schema (shared dev schema, overlapping CI and prod) overwrite each other's tmp relation → route it with a `snowflake__resolve_incremental_tmp_relation` override or keep schemas per run.

## Incremental Models

Each incremental model needs: `unique_key` correct and truly unique · `incremental_strategy` matching warehouse behavior · intentional `on_schema_change` · `cluster_by` aligned with filter/predicate columns · `is_incremental()` with adequate lookback for late data.

**Separate source and target pruning:** `is_incremental()` filters source reads, `incremental_predicates` filter destination scans, `unique_key` matches incoming to target rows, `cluster_by` SHOULD align with predicate/filter columns. The source lookback SHOULD be smaller than the target predicate window — e.g. read the last 3 days from source, let Snowflake scan the last 7 days of target, so late data still merges into existing records.

**First vs later runs:** first run `is_incremental()` false → build full history; later runs true → read only the configured delta window.

**Schema change:**

| `on_schema_change` | Use |
|---|---|
| `ignore` (default) | Stable schemas |
| `append_new_columns` | Evolving schemas |
| `sync_all_columns` | Cautiously: can break consumers, also drops columns missing from the query |
| `fail` | Drift should stop the run |

No option backfills new columns on existing rows → full refresh for small/medium tables, variable windows for large tables, direct DML only for exceptional fixes.

**Full refresh** may require drop permissions; simple but potentially costly and disruptive for large or permission-constrained tables. Resource config `full_refresh: false` overrides the `--full-refresh` flag (never fully refreshed); `full_refresh: true` forces a rebuild without the flag. Check the resource config before assuming the flag rebuilds a protected layer. Snapshots ignore both.

### Late-Arriving and Multi-Parent Changes

A watermark on the driving table alone loses changes arriving on another parent: an orders model filtered on `orders.updated_at` and joined to payments never sees a payment added to an old order. Before writing the `is_incremental()` filter:

1. **List every parent** (`dbt ls --select "1+<model>" --exclude <model>`) and record its change signal: reliable modified timestamp, load timestamp, append-only event time, hash/CDC, or none.
2. **Derive affected keys** as the union over parents: grain keys whose own row changed in the window plus keys referenced by changed child rows. Recompute those keys from **all** their child rows, not only new ones; aggregating only the delta double-counts or drops values. State what key detection scans each run: re-aggregating a whole child table is correct but costs a full child scan every run → bound it with the child's own change signal or a window, or accept it explicitly.
3. **Add a lookback** sized to the source's documented maximum lateness (`>= dateadd(day, -<n>, max(<watermark>))`, not `>`); keep it smaller than any target `incremental_predicates` window.
4. **Child without a timestamp:** prefer a load timestamp added by ingestion or staging. Otherwise re-derive the key set from a bounded parent window and replace those keys with `delete+insert` (or `merge`) on the grain key, or detect child changes with a payload hash stored on the target (Hash-Based Change Detection). Neither affordable → materialize as `table`.
5. **Deletes:** an incremental run never removes rows absent from the batch. Handle source deletes explicitly (soft-delete flag, key-set `delete+insert`, or scheduled rebuild).
6. **Set `on_schema_change`** explicitly (Sanofi default `append_new_columns`).
7. **Schedule a periodic full refresh** or bounded backfill to repair drift, unless the layer is history-bearing with `full_refresh: false`; there, bounded backfill only.
8. **Prove it:** unit-test the `is_incremental: true` branch with a late child row ([unit-tests.md](unit-tests.md#incremental-models)); in dev, add a late child row for an old parent, run incrementally, compare with a full-refresh build of a copy (`audit_helper.compare_relations`).

Shape of a multi-parent key set (adapt names, windows, grain):

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

Identify rows with a stable technical key hash from the business key (e.g. `dbt_utils.generate_surrogate_key`); detect changes with a payload hash over the payload columns. `merge` with the technical key as `unique_key`; exclude audit columns such as creation timestamps from updates via `merge_exclude_columns` when the repo does so. Select new or changed rows by hash comparison, not a time watermark. Truncate/reload working-layer exceptions SHOULD NOT carry an `is_incremental()` delta filter.

### Filter Placement

**Filter the driving table before joins.** Read the high-water mark once in a small watermark CTE (`select coalesce(max(<changed_ts>), <floor_date>) from {{ this }}`) and apply it inside the driving table's `WHERE`, so Snowflake prunes micro-partitions at the storage layer. The same filter in an outer `WHERE` after all joins is a common anti-pattern: Snowflake still scans the full source and evaluates every join before discarding unchanged rows — can be slower than a full rebuild.

- **Nullable watermark columns:** guard with `OR <col> IS NULL`; a modification date on a left-joined table needs `OR <joined>.<date> IS NULL` so unmatched rows are not silently dropped.
- **Derived timestamp:** use the same expression in the filter (e.g. a `GREATEST(...)` of lifecycle timestamps).
- **No reliable modification timestamp:** `merge` or `delete+insert` on `unique_key` alone (no delta filter) still avoids drop/recreate and preserves Time Travel, though every source row is scanned.
- **Orchestrated run windows:** pipelines often make runs idempotent and reprocessable by filtering the source on an explicit window passed as vars (e.g. `var('data_interval_start')` / `var('data_interval_end')` from the scheduler) instead of, or alongside, a `max()` watermark. Seed with one full refresh, then run incrementally; keep a manual full refresh for periodic rebuilds.

### Microbatch

For large time-series models with a reliable event timestamp, consider `incremental_strategy='microbatch'` (dbt >= 1.9) instead of a hand-written `is_incremental()` window. On Snowflake dbt implements it as `delete+insert` per batch → no `unique_key`; each batch replaced whole.

- **Required:** `event_time`, `begin`, `batch_size` (`hour|day|month|year`); `lookback` (default 1) reprocesses prior batches for late data. All values UTC.
- **`event_time` on the model AND every upstream model to filter.** An upstream without it is fully scanned every batch. Opt a ref out only deliberately, with `ref('x').render()`.
- **The query MUST return exactly one batch window. NEVER add an `is_incremental()` filter.**
- **`full_refresh: false`** (persistent-layer rule). Reprocess history with a bounded backfill; both bounds required together: `dbt run --select <model> --event-time-start "2024-01-01" --event-time-end "2024-02-01"`. `dbt retry` reruns only failed batches; Snowflake batches can run concurrently (`concurrent_batches`).
- **Poor fit:** no trustworthy event timestamp, hash-based change detection, or logic needing previous table state. A reprocessed window drops rows the query no longer returns → not for history-bearing PSA/SCD models.

## Verification

- Persisted layers set `transient: false`; `copy_grants: true` where grants MUST survive rebuilds.
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
