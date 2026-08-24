---
name: feature-store-tecton
description: "Generate standalone Python setup scripts for the Snowflake Feature Store public SDK from Tecton specs or natural language. Creates stream sources, batch feature views (BFVs), stream feature views (SFVs), real-time feature views (RTFVs), and feature groups using the snowflake.ml.feature_store API. Use when the user says: 'translate this Tecton spec', '@stream_feature_view', '@batch_feature_view', 'StreamSource', 'backfill_df', 'generate FV script', 'create a feature view', 'migrate from Tecton', or pastes a Tecton-decorated Python function."
parent_skill: feature-store-migrate
path: machine-learning/feature-store/migrate/tecton
---
# Tecton → Feature Store Script Generator

Generates **customer-facing** Python scripts that call the public
`snowflake.ml.feature_store` SDK directly. The scripts have no dependency on any
benchmarking or synthetic-data helper package, YAML configs, or synthetic-data
generation. Customers bring their own source tables; the generated
script only registers Feature Store objects against that real data.

## When to Use

- User pastes a Tecton `@batch_feature_view` or `@stream_feature_view` decorated Python function
- User pastes a `BatchSource` / `StreamSource` Tecton definition
- User describes in natural language what they want a feature view to compute
- User says "create a feature view", "generate FV script", "translate this Tecton spec", "make a BFV/SFV for..."

## What Gets Generated

Standalone Python scripts a customer runs directly after `pip install snowflake-ml-python` — no YAML, no `--config` flags, no internal imports:

| Artifact                  | Generated file            | Run with                         |
| --------------------------- | --------------------------- | ---------------------------------- |
| Stream source             | `create_{source_name}.py` | `python create_{source_name}.py` |
| Batch Feature View (BFV)  | `create_{fv_name}.py`     | `python create_{fv_name}.py`     |
| Stream Feature View (SFV) | `create_{fv_name}.py`     | `python create_{fv_name}.py`     |

Every script imports only from `snowflake.snowpark` and `snowflake.ml.feature_store`.
All parameters are inlined as uppercase constants at the top of the file. The user edits
only those constants (connection, database, source table, etc.) before running.

See [reference.md](reference.md) for the full public SDK surface, type mapping, and Feature API tables.

---

## Step 1 — Classify the Artifact

Determine what the user wants:

- **Stream source**: Tecton `BatchSource`/`StreamSource`, or user says "create a stream source", or an SFV needs one that doesn't exist yet
- **BFV (Batch Feature View)**: Tecton `@batch_feature_view`, or user says "batch", "daily refresh", "historical aggregation"
- **SFV (Stream Feature View)**: Tecton `@stream_feature_view`, or user says "streaming", "continuous", "real-time"
- **RTFV (Real-Time Feature View)**: Tecton `@realtime_feature_view` → `RealtimeConfig`-based `FeatureView`. User says "real-time compute", "request-time feature", "RTFV", "RealtimeConfig", or describes a feature derived from upstream FVs at inference time
- **Feature Group**: Tecton `FeatureService` → `FeatureGroup`. User says "feature group", "feature service", "group feature views", "combine FVs into one OFT", or wants to serve multiple FVs from a single low-latency table

If unclear, use `AskQuestion`:

```
Which type of artifact are you creating?
- Stream source (register a shared event stream)
- BFV (batch feature view — daily/hourly refresh)
- SFV (stream feature view — continuous streaming aggregation)
- RTFV (real-time feature view — request-time compute against upstream FVs)
- Feature Group (combine multiple online FVs into one low-latency table)
```

**Load** the sub-skill for the classified artifact:

- **Stream source** → **Load** `stream-source/SKILL.md`
- **BFV** → **Load** `bfv/SKILL.md` (continue to Step 2 first)
- **SFV** → **Load** `sfv/SKILL.md` (continue to Step 2 first)
- **RTFV** → **Load** `rtfv/SKILL.md` (self-contained; Steps 2/4 do not apply)
- **Feature Group** → **Load** `feature-group/SKILL.md` (self-contained; Steps 2/4 do not apply)

For BFV and SFV, complete Steps 2 and 4 below before generating the script.

---

## Step 2 — Extract Required Fields

### Tecton → Feature Store SDK mapping

| Tecton field                                            | Feature Store SDK                                                  |
| --------------------------------------------------------- | ------------------------------------------------------------------- |
| `entities=[e]` (join key)                               | `Entity(name=..., join_keys=[ENTITY_COL])`                        |
| `timestamp_field`                                       | `FeatureView(..., timestamp_col=TIMESTAMP_COL)`                   |
| `source=stream_source`                                 | `StreamConfig(stream_source=STREAM_SOURCE, ...)` (SFV)           |
| `sources=[batch_source]`                               | `feature_df=session.table(SOURCE_TABLE)` (BFV)                   |
| `features=[Aggregate(function=f, input_column=Field(c), time_window=timedelta(...))]` | one `Feature.<f>(c, window, ...)` per aggregate |
| `aggregation_interval=timedelta(...)`                  | `FeatureView(..., feature_granularity="...")`                    |
| `batch_schedule=timedelta(days=1)`                     | `FeatureView(..., refresh_freq="1 day")`                         |
| `stream_processing_mode=StreamProcessingMode.CONTINUOUS` | `feature_aggregation_method=FeatureAggregationMethod.CONTINUOUS` |
| `online=True`                                           | `OnlineConfig(enable=True)` (BFV); always-on for SFV stream_config |
| `offline=True`                                          | set `refresh_freq` (managed feature view)                        |
| `last_distinct(N)`                                      | `Feature.last_distinct_n(col, window, n=N)`                      |
| inline filter/select function body                     | `transformation_fn=_transform` (SFV only)                        |
| `feature_start_time`, `max_backfill_interval`, `batch_compute`, `mode="pandas"` | **no SDK equivalent — omit** (Tecton runtime concerns) |

> **There is no `LOOK_FORWARD` in the SDK.** It is a synthetic-data
> concept and must never appear in generated customer scripts. Likewise, do **not**
> generate `NUM_ROWS`, `ROWS_PER_BUCKET`, `n_buckets`, `create_real_schema_table`,
> `backfill_df_for_real_schema`, or any synthetic-data/benchmark helper import.
> Customers supply
> their own real source table/backfill table.

> **Do not confuse `batch_schedule` with `feature_granularity`.** They are independent:
> `batch_schedule` (how often the offline refresh runs) → `refresh_freq`;
> `feature_granularity` is the aggregation tile size (Tecton `aggregation_interval`),
> derived from the windows per Step 4 — never copied from `batch_schedule`.

### From natural language, ask for any missing fields

If any of the following are missing after parsing, ask with `AskQuestion` (all missing fields in one call):

- Entity column name (e.g. `PersonUuid`, `DeviceId`)
- Timestamp column name (e.g. `CreatedAt`, `EventTimestamp`)
- BFV: the fully-qualified source table/view name that holds the feature data
- SFV: which stream source to use, and whether the user has a historical backfill table (Path A: fully-qualified table name, e.g. `MY_DB.MY_SCHEMA.USER_EVENTS_HISTORICAL`) or no historical data yet (Path B: stub backfill) — **do NOT hallucinate or invent a table name; the SFV sub-skill will ask**
- Aggregation function(s), window(s), and source column(s)

---

## Step 3 — Stream Source Check (SFV only)

Handled by `sfv/SKILL.md` — the SFV sub-skill asks the user whether the stream source
exists and loads `stream-source/SKILL.md` if it must be created first.

---

## Step 4 — Compute Smart Defaults

Apply automatically; explain each choice when writing the script.

### `FEATURE_GRANULARITY` (tile size)

For the tile concept and general sizing guidance, see [Choosing `feature_granularity`](../../references/feature-patterns.md#tile-based-aggregation-feature-store-native). The SDK constraints and the codegen selection algorithm below are the authoritative rules for generated scripts.

The SDK enforces (hard constraints):
- Granularity **≤ the smallest aggregation window**
- Granularity **evenly divides every aggregation window**
- Granularity **≥ 1 minute** (the SDK floor)

Quality target (soft): aim for **at least ~90 tiles per window**, i.e.
`granularity ≈ largest_window / 90`. More tiles → more accurate, reusable partial
aggregations; too few tiles (large granularity relative to the window) coarsens results.

Selection algorithm:
1. Compute `target = largest_window / 90` (seconds).
2. Compute `G = GCD(all windows)` (seconds).
3. Pick `granularity` = the **largest divisor of `G` that is ≤ `target` and ≥ 60s**.
   This satisfies both the divides-all-windows rule and the ≥90-tile goal.
4. If no divisor of `G` is ≤ `target` (e.g. windows are near the 1m floor), fall back to the
   largest divisor of `G` that is ≥ 60s — the ≥90-tile target is best-effort, the SDK rules are not.
5. Single window `W`: `granularity = W/90` if it's ≥ 60s and divides `W` (e.g. `W=24h → 16m`);
   otherwise the closest divisor of `W` at or below `W/90`.

For **continuous** SFVs, omitting `feature_granularity` defaults to `"1m"`; set it explicitly
only when the windows require a coarser tile.

### `refresh_freq`

- Map from Tecton `batch_schedule` (e.g. `timedelta(days=1)` → `"1 day"`, `timedelta(hours=1)` → `"1 hour"`).
- Minimum is 1 minute. If the user wants an unmanaged view (no scheduled refresh), leave it unset.

---

## Filling in `{agg_feature_lines}`

One `Feature.<fn>(...)` per aggregation, indented 12 spaces (inside the `features=[` list):

```python
            Feature.last_distinct_n("RoadZoneRegion", "24h", n=8),
            Feature.count("TransactionId", "7d"),
            Feature.sum("Amount", "24h"),
            Feature.avg("Amount", "24h"),
```

See `reference.md` § "Feature factory reference" for the full Tecton → `Feature` API mapping table
(including `offset`, `.alias()`, and duration string formats).

> **The Postgres online store does not support `last_n` / `first_n` (temporary).** It
> implements only the distinct list aggregations — `LAST_DISTINCT_N` and
> `FIRST_DISTINCT_N` — not the non-distinct `LAST_N` / `FIRST_N`. Since every
> generated script uses the Postgres online store,
> **substitute `Feature.last_distinct_n` for `last_n` and `Feature.first_distinct_n` for
> `first_n`** as a temporary replacement, and note the substitution in a comment on the
> generated line, e.g.:
>
> ```python
>             # NOTE: the Postgres online store has no last_n yet — using last_distinct_n (distinct values) instead
>             Feature.last_distinct_n("PageId", "1h", n=10),
> ```
>
> Distinct-N is also capped at `n ≤ 1000` on the Postgres online store.

---

## Step 5 — Generate the Python Script

Handled by the loaded sub-skill: `bfv/SKILL.md`, `sfv/SKILL.md`, or `stream-source/SKILL.md`.
Each sub-skill includes a **mandatory stopping point** — present the planned filename and
a summary of all constants (FV name, entity, table, features, etc.) and wait for explicit
user approval before writing the file.

---

## Step 6 — Show Run Commands

After writing the file(s), always display the run sequence:

```bash
pip install snowflake-ml-python

# SFV only: register the stream source first (if not already registered)
python create_{stream_source}.py

# Then create the feature view
python create_{fv_name}.py
```

If the stream source was newly generated in this session, show both commands in order and
emphasize the prerequisite.

---

## Transform Rules (SFV `transformation_fn` and RTFV `compute_fn`)

- Define as a **single named `def` at module level** (`StreamConfig`/`RealtimeConfig` use
  `inspect.getsource()`); no lambda/nested def.
- Use **ALL-CAPS** column names (Snowflake uppercases unquoted identifiers): `df["ORIGINVEHICLEID"]`.
- Filter, then select `[ENTITY_COL(s), TIMESTAMP_COL, *agg_source_cols]` — all uppercase.
- Allowed imports: `numpy`, `pandas`, `re`, `copy`, `dataclasses`. `datetime` is **not** allowed:

```python
# ✗ Not allowed
from datetime import datetime
dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f")

# ✓ Use pd.Timestamp; guard None/empty only; do NOT silence real parse errors
request_dt = pd.Timestamp(ts_str).tz_localize(None) if ts_str else None
```

### RTFV `compute_fn` rules

See `rtfv/SKILL.md` for the full RTFV-specific rules (single top-level `def`, no helpers).

---

## Tips — Apply These Automatically

- **`FEATURE_GRANULARITY` ≤ smallest window, divides all windows, ≥ 1 minute.** The SDK
  rejects a granularity that doesn't evenly divide every aggregation window or is below 1m.
  Ideally target ≈ `largest_window / 90` (rounded down to a divisor of all windows) so each
  window is covered by at least ~90 tiles — finer tiles give more accurate, reusable partial
  aggregations. Coarser (fewer tiles) trades accuracy for cheaper storage/refresh.
- **`batch_schedule` maps to `refresh_freq`, not `feature_granularity`.** The offline refresh
  cadence and the aggregation tile size are independent.
- **Transform at module level.** `StreamConfig` uses `inspect.getsource()`; the transform must be
  a single named `def` at module level, importing only `numpy`, `pandas`, `re`, `copy`.
- **ALL-CAPS columns everywhere in the transform and `compute_fn`.** Snowflake uppercases unquoted
  identifiers — use `df["COLUMNNAME"]` (uppercase, no spaces). Mixed-case pandas column names are
  the most common silent source of RTFV 404 errors.
- **Object name length limits (SDK ≥ 1.43.0).** FV name + version ≤ 45 chars combined
  (with `V1`, max name = 43); entity name ≤ 32; stream source name ≤ 32; feature column
  name ≤ 30 (online store). Abbreviate aggressively — see `reference.md` § "Object name
  length limits" for the full table and naming strategy.
- **No `last_n` / `first_n` on Postgres online store (temporary).** the Postgres online store implements only the
  distinct list aggregations. Substitute `Feature.last_distinct_n` / `Feature.first_distinct_n`
  and leave a `# NOTE:` comment on the line. Distinct-N is capped at `n ≤ 1000`.
- **Register order:** stream source → entity → feature view. `register_entity` before
  `register_feature_view`, or registration fails with "entity has not been registered".
- **Timestamps are `TIMESTAMP_NTZ` (UTC).** Only `TimestampType()` / `TimestampType(TimestampTimeZone.NTZ)`
  are accepted in stream-source schemas.
- **SFV: cast entity join-key to unbounded `StringType()`.** For SFVs, `session.table()` infers
  length-bounded `VARCHAR(N)` from DDL, which mismatches the StreamSource schema's unbounded
  `StringType()` and fails validation. Cast explicitly (see SFV sub-skill template). BFVs don't
  need this cast — `feature_df` is the sole type source with no cross-schema validation.
- **`backfill_df` must survive a fresh session.** Build it from a permanent table/view
  (`session.table(...)`) or, for the stub-backfill path when no historical data exists,
  from `session.create_dataframe(stub_data, schema=stub_schema)` (re-creates data each run).
  Never use a temp table. See `sfv/SKILL.md` Path A / Path B for details.
- **`backfill_df` constraints** (column completeness, minimum one row) — see `sfv/SKILL.md`
  § "Backfill DataFrame" for the full rules and exact error messages.
- **Postgres online reads require a non-empty `keys` list.** Unbounded scans are not supported;
  always supply at least one join-key value when retrieving online features.

---

## Common Tecton → Snowflake Translation Patterns

### Filter columns not in the aggregation

When the Tecton body filters on a column that isn't aggregated (e.g. `TripDirection == "outbound"`),
that column must still exist in the data:
- **BFV:** the `SOURCE_TABLE` must include it (the SDK reads the projected `feature_df`).
- **SFV:** it must be in the stream source schema and the backfill table; the `_transform` filters on it,
  then drops it from the final `return df[[...]]` selection.

### Multiple entities on the same stream

If several FVs share one stream but key on different columns (e.g. `OriginVehicleId` vs `DriverUuid`),
generate one FV script per entity — each with its own `Entity`, `_transform` return list, and `FV_NAME`.
The stream-source script is shared.

### Output column names

Tecton auto-names aggregate outputs. To pin an explicit name, chain `.alias("MY_NAME")` on the
`Feature` (uppercased by default; pass `case_sensitive=True` to preserve case).

---

## Worked Example: Tecton traffic spec → Feature Store SDK

A complete Tecton → SDK translation lives in `examples/`. **Read these before generating a
new script:**

- Input:  `examples/tecton_input/traffic_stream_source.py` (Tecton `StreamSource`),
  `examples/tecton_input/traffic_feature_view.py` (Tecton `@stream_feature_view`)
- Output: `examples/snowflake_output/deploy_traffic_fv.py` — registers the StreamSource, entity, and FeatureView

> **Note:** `deploy_traffic_fv.py` is the customer-facing output form: it edits a
> `CONFIG` block, registers the StreamSource + entity + SFV, and points
> `backfill_df` at a real permanent table (`session.table(BACKFILL_TABLE)`). It
> preserves the entity join-key cast pattern. It does **not**
> generate synthetic data — customers supply their own historical backfill table.

The distilled field mappings for the traffic example:

**`StreamSource`** (`traffic_stream_source.py` → `register_stream_source`):

| Tecton                         | SDK                                                            |
| -------------------------------- | --------------------------------------------------------------- |
| `StreamSource(name=...)`       | `StreamSource(name="EXAMPLE_TRAFFIC_SRC", ...)` (≤ 32 chars, uppercased) |
| `PushConfig(timestamp_field)`  | no separate object; timestamp handled by the FV `timestamp_col` |
| `batch_config=FileConfig(...)` | **omitted** — the customer's backfill comes from a Snowflake table, not S3 |
| `schema=[Field(name, String)]` | `StructType([StructField(name, StringType()), ...])`          |
| `Field(..., Float64/Int64/Timestamp)` | `DoubleType()` / `LongType()` / `TimestampType(TimestampTimeZone.NTZ)` |
| register                       | `fs.register_stream_source(StreamSource(...))`                |

**`FeatureView`** (`traffic_feature_view.py` → `register_feature_view`):

| Tecton                                                    | SDK                                                              |
| ----------------------------------------------------------- | ----------------------------------------------------------------- |
| `source=example_traffic_stream`                          | `StreamConfig(stream_source="EXAMPLE_TRAFFIC_SRC", ...)`         |
| `entities=[origin_vehicle]`                              | `Entity(name="origin_vehicle_id_entity", join_keys=["OriginVehicleId"])` → `fs.register_entity(entity)` |
| `stream_processing_mode=StreamProcessingMode.CONTINUOUS` | `feature_aggregation_method=FeatureAggregationMethod.CONTINUOUS` |
| `last_distinct(8)` on `RoadZoneRegion`, `time_window=24h`| `Feature.last_distinct_n("RoadZoneRegion", "24h", n=8)`         |
| function body (filter + select)                          | `def _transform(df): ...` passed as `transformation_fn`         |
| `timestamp_field="EventTimestamp"`                       | `FeatureView(..., timestamp_col="EventTimestamp")`              |
| `batch_schedule=timedelta(days=1)`                       | `FeatureView(..., refresh_freq="1 hour")` (intentionally shorter than the Tecton 1-day schedule — continuous SFVs benefit from a faster offline refresh; the general rule maps `timedelta(days=1)` → `"1 day"` for BFVs) |
| `online=True`                                            | online store auto-enabled by `stream_config` (Postgres)         |
| `feature_start_time`, `max_backfill_interval`, `batch_compute`, `mode="pandas"` | **no SDK equivalent — omitted**              |
