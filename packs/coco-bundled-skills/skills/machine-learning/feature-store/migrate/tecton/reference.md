# Reference — Snowflake Feature Store SDK

Detailed API notes for translating Tecton specs. Read `SKILL.md` first; consult this
file for exact signatures, type mappings, and edge cases.

## Public SDK surface

| Object / call                                                        | Module                                       |
| ---------------------------------------------------------------------- | ---------------------------------------------- |
| `Session.builder.configs({...}).getOrCreate()`                       | `snowflake.snowpark`                          |
| `FeatureStore(session, database, name, default_warehouse, creation_mode)` | `snowflake.ml.feature_store`            |
| `CreationMode.CREATE_IF_NOT_EXIST`                                   | `snowflake.ml.feature_store`                  |
| `Entity(name, join_keys)` / `fs.register_entity(entity)`             | `snowflake.ml.feature_store`                  |
| `Feature.<fn>(column, window, ...)`                                  | `snowflake.ml.feature_store`                  |
| `FeatureView(...)` / `fs.register_feature_view(fv, version)`         | `snowflake.ml.feature_store`                  |
| `OnlineConfig(enable, target_lag, store_type)` / `OnlineStoreType`  | `snowflake.ml.feature_store`                  |
| `FeatureAggregationMethod.CONTINUOUS` / `.TILES`                     | `snowflake.ml.feature_store`                  |
| `StreamSource(name, schema, desc)` / `fs.register_stream_source(ss)`| `snowflake.ml.feature_store`                  |
| `fs.get_stream_source(name)`                                        | `snowflake.ml.feature_store`                  |
| `StreamConfig(stream_source, transformation_fn, backfill_df)`       | `snowflake.ml.feature_store.stream_config`    |

## Tecton type → Snowpark type

| Tecton      | Snowpark                               |
| ------------- | ---------------------------------------- |
| `String`    | `StringType()`                         |
| `Float64`   | `DoubleType()`                         |
| `Int64`     | `LongType()`                           |
| `Timestamp` | `TimestampType(TimestampTimeZone.NTZ)` |
| `Bool`      | `BooleanType()`                        |

Only `TIMESTAMP_NTZ` is allowed in stream-source schemas; all timestamps are stored as UTC.
Supported stream-source types: `StringType`, `LongType`, `DoubleType`, `DecimalType`,
`BooleanType`, `BinaryType`, `TimestampType`.

## `Feature` factory reference

| Tecton aggregate          | SDK                                                    |
| --------------------------- | ------------------------------------------------------- |
| `count`                   | `Feature.count(col, window)`                          |
| `sum`                     | `Feature.sum(col, window)`                            |
| `mean` / `avg`            | `Feature.avg(col, window)`                            |
| `max` / `min`             | `Feature.max(col, window)` / `Feature.min(col, window)` |
| `stddev`                  | `Feature.stddev(col, window)`                         |
| `variance`                | `Feature.var(col, window)`                            |
| `last_n(N)`               | `Feature.last_distinct_n(col, window, n=N)` — the Postgres online store has no `last_n` |
| `last_distinct(N)`        | `Feature.last_distinct_n(col, window, n=N)`           |
| `first_n(N)`              | `Feature.first_distinct_n(col, window, n=N)` — the Postgres online store has no `first_n` |
| `first_distinct_n(N)`     | `Feature.first_distinct_n(col, window, n=N)`          |
| `approx_count_distinct`   | `Feature.approx_count_distinct(col, window)`          |
| `approx_percentile(p)`    | `Feature.approx_percentile(col, window, percentile=p)`|

- `window` / `offset` are duration strings: `"30m"`, `"24h"`, `"7d"`, `"90d"`.
- `.alias("NAME")` sets the output column (uppercased unless `case_sensitive=True`).
- Distinct-N on Postgres is capped at `n ≤ 1000`.

## Streaming backfill notes

- `StreamConfig.backfill_df` must be re-executable from a fresh session: build it from a
  permanent table/view (`session.table(...)`) or, for the stub-backfill path (no historical
  data), from `session.create_dataframe(stub_data, schema=stub_schema)` which re-creates the
  data each run. Never use a temp table that won't survive a new session.
- The stub schema must mirror **every column** in the StreamSource's `StructType` — the SDK
  validates `backfill_df` against the full StreamSource schema, not just the columns the
  transform uses. See `sfv/SKILL.md` Path B for the template.
- `backfill_df` must contain at least one row — registration probes `.limit(10).to_pandas()`
  to infer the transform output schema.
- Cast entity/join-key columns to unbounded `StringType()` to avoid length-bounded VARCHAR
  join-key mismatches.

## `FeatureView` key arguments

| Argument                      | Notes                                                            |
| ------------------------------- | ----------------------------------------------------------------- |
| `name`, `entities`, `version` | version accepts letters/numbers/underscore; is uppercased        |
| `feature_df`                  | BFV source projection (join keys + timestamp + feature columns)  |
| `stream_config`               | SFV; requires `timestamp_col` and a backfill DataFrame           |
| `timestamp_col`               | point-in-time column                                             |
| `refresh_freq`                | offline refresh cadence; unset → registered as a static View     |
| `feature_granularity`         | tile size (with `features`)                                      |
| `features`                    | list of `Feature` (required when `feature_granularity` set)      |
| `feature_aggregation_method`  | `CONTINUOUS` or `TILES` (SFV only)                              |
| `online_config`               | `OnlineConfig`; SFV stream_config always uses Postgres online    |
| `realtime_config`             | RTFV; mutually exclusive with `feature_df` / `stream_config` / `rollup_config`; online always enabled |

## `RealtimeConfig`

| Argument       | Notes                                                                 |
| ---------------- | ----------------------------------------------------------------------- |
| `compute_fn`   | Named module-level `def`; same validation policy as SFV `transformation_fn` |
| `sources`      | `[RequestSource, FV1, FV2, ...]` — `RequestSource` at position 0 if present; then 1+ `FeatureView`/`FeatureViewSlice` |
| `output_schema`| `StructType` describing columns `compute_fn` returns; must be non-empty |

- Positional parameter count of `compute_fn` must equal `len(sources)`.
- No `*args`, `**kwargs`, or keyword-only arguments.
- `FeatureGroup` is **not** a valid source — use the underlying FeatureViews.
- Runtime namespace provides `pd`, `np`, `re`, `copy` without importing.

## `FeatureGroup`

| Argument       | Notes                                                                 |
| ---------------- | ----------------------------------------------------------------------- |
| `name`         | Max 255 chars; no `$` delimiter                                       |
| `features`     | Non-empty list of `FeatureView` / `FeatureViewSlice` — all must be registered, online-enabled, Postgres store |
| `desc`         | Human-readable description                                            |
| `auto_prefix`  | Default `True`; prefixes output columns with `"<FV_NAME>_<FV_VERSION>_"` |

- Registered via `fs.register_feature_group(fg, version)`.
- OFT primary key = ordered union of source FVs' join keys.
- Sources may join at different grains (coarser sources broadcast over the wider key).

## Object name length limits (SDK ≥ 1.43.0)

The SDK enforces these at registration time. All limits stem from the Postgres online
store's 63-byte `NAMEDATALEN`; the SDK reserves room for internal suffixes (`$VERSION`,
`$UDF_TRANSFORMED`, column prefixes, etc.).

| Object                          | Max length | SDK constant                              |
| --------------------------------- | ------------ | ------------------------------------------- |
| FV name + version (combined)    | 45 chars   | `_POSTGRES_ONLINE_MAX_NAME_VERSION_LEN`   |
| Entity name                     | 32 chars   | `_ENTITY_NAME_LENGTH_LIMIT`               |
| Stream Source name               | 32 chars   | `_STREAM_SOURCE_NAME_LENGTH_LIMIT`        |
| Feature column name (online)    | 30 chars   | `_POSTGRES_ONLINE_MAX_COLUMN_LEN`         |
| Feature Group name               | 255 chars  | `_FEATURE_GROUP_NAME_MAX_LENGTH`          |
| FV version (without Postgres)   | 128 chars  | `_FEATURE_VIEW_VERSION_MAX_LENGTH`        |

With version `"V1"` (2 chars), max FV name = **43 characters**. The 45-char combined
limit applies to all FV types (batch, streaming, RTFV) when Postgres online is configured.

> **Note:** Empirical testing shows only streaming FVs are actually constrained by
> Postgres `NAMEDATALEN` — batch FVs and RTFVs don't create a `NAME$VERSION` Postgres
> table, so longer names work at the Postgres layer. However, the SDK still rejects
> names exceeding 45 combined chars for all types as of SDK ≥ 1.43.0.

### Naming strategy — abbreviate to stay under budget

Use standard domain abbreviations to keep FV names ≤ 43 chars (with `V1`):

| Pattern          | Abbreviation |
| ------------------ | -------------- |
| `TRANSACTION`    | `TXN`        |
| `DOCUMENT`       | `DOC`        |
| `AMOUNT`         | `AMT`        |
| `COUNT`          | `CNT`        |
| `AVERAGE`        | `AVG`        |
| `SUMMARY` / `SUM`| `SUM`        |
| `DISTINCT`       | `DIST`       |
| `NETWORK`        | `NET`        |
| `SENDER` / `RECEIVER` | `SNDR` / `RCVR` |
| `7d` / `24h` / `30d` | suffix with window |

## Registration order & gotchas

1. `fs.register_stream_source(...)` (SFV) — name ≤ 32 chars; can't delete while FVs reference it.
2. `fs.register_entity(...)` for each entity — must precede the feature view.
3. `fs.register_feature_view(draft_fv, version, overwrite=...)`.
4. `fs.register_feature_group(fg, version)` — all source FVs must already be registered and online-enabled.

Common errors:
- "entity has not been registered" → register entities first.
- Postgres online reads require a non-empty `keys` list (no unbounded scans).
