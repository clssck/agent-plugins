# Incremental Sync — pg_incremental Pipelines

Continuous, exactly-once sync from a Postgres source (operational table, sequence, or object-storage files) into an Iceberg table or aggregate. Backed by the `pg_incremental` extension (Crunchy Data) + `pg_cron` for scheduling.

If the user actually wants the managed Snowflake-side mirroring feature (`SNOWFLAKE.POSTGRES.CREATE_MIRROR`, base tables plus `$live` / `$changes` in Snowflake), route to `../../mirror/SKILL.md` instead. This doc is for DIY `pg_incremental` pipelines inside Postgres.

## When to use

Use when PG should remain the operational source of truth and a derived Iceberg table needs to stay in sync with PG on an interval. Typical setups:

- An operational row-oriented PG table that needs an analytics mirror (Iceberg) queryable from Snowflake
- New rows keyed by a sequence ID or event timestamp column
- New files landing in object storage that need to be appended to an Iceberg table

Don't use for: one-shot backfills (plain `INSERT INTO target SELECT FROM source` is simpler), or writes that must be transactional with operational reads on the Iceberg side — the mirror only advances when the pipeline runs.

## Prerequisites

```sql
CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS pg_incremental CASCADE;
```

`pg_cron` is a required dependency — `pg_incremental` uses it to schedule pipeline runs. Both extensions come bundled with pg_lake on Snowflake Postgres instances.

## Exactly-once semantics

Progress state (last processed sequence value, last processed time interval, processed file paths) is written inside the same transaction as the command. A command either commits together with its state update, or neither happens — the pipeline survives crashes, restarts, and failed SQL runs without duplicating rows.

## Pipeline types

Three constructor functions under the `incremental.` schema. Pick the one matching the source shape.

### Time-interval pipeline

Use when the source table has a timestamp column (event time, reading time, etc.) and you want to sync all rows that fall into each passing interval.

```sql
select incremental.create_time_interval_pipeline(
    pipeline_name     := 'sync_events_to_iceberg',
    time_interval     := '1 hour',
    source_table_name := 'events',
    start_time        := (select min(event_time) from events),
    command           := $$
        insert into events_iceberg
        select * from events
        where event_time >= $1 and event_time < $2
    $$
);
```

Signature:

```sql
create_time_interval_pipeline(
    pipeline_name      text,
    time_interval      interval,
    command            text,
    batched            bool        default true,
    start_time         timestamptz default '2000-01-01 00:00:00',
    source_table_name  regclass    default null,
    schedule           text        default '* * * * *',
    min_delay          interval    default '30 seconds',
    execute_immediately bool       default true
)
```

`$1` and `$2` in the command bind to the interval's start (inclusive) and end (exclusive). `min_delay` holds back the trailing edge so in-flight writes can commit before an interval closes. `schedule` is a pg_cron expression — tighten for faster mirrors, loosen to reduce overhead.

### Sequence pipeline

Use when the source table has a monotonically increasing ID column (the "new rows since last run" pattern without timestamps — often for incremental aggregates).

```sql
select incremental.create_sequence_pipeline(
    pipeline_name := 'aggregate_orders',
    sequence_name := 'orders_order_id_seq',
    command       := $$
        insert into orders_daily
        select date_trunc('day', created_at), count(*)
        from orders where order_id between $1 and $2
        group by 1
        on conflict (day) do update
          set order_count = orders_daily.order_count + excluded.order_count
    $$
);
```

Signature:

```sql
create_sequence_pipeline(
    pipeline_name       text,
    sequence_name       regclass,
    command             text,
    schedule            text    default '* * * * *',
    max_batch_size      bigint  default null,
    execute_immediately bool    default true
)
```

`max_batch_size` bounds how many sequence values are processed per run — useful when backfilling a large range without blocking operational writes. Sequence pipelines automatically wait for concurrent write transactions before closing an interval, so in-flight inserts never fall outside the processed range.

> ⚠️ **Truncating the source silently strips new rows until you reset the pipeline.** The pipeline persists a high-water mark (`last_processed_sequence_number` for sequence pipelines; the last interval for time pipelines). If you `TRUNCATE` and reload the source, the sequence restarts at 1 but the pipeline still thinks it processed up to (say) 241500 — so new rows with IDs 1, 2, 3… are treated as "already synced" and **never reach the target**, with no error. After any truncate/reload of the source, call `incremental.reset_pipeline('<name>')` to clear the high-water mark before the next run. This is the same bookmark/watermark class of issue as `_data_version` resets on the managed mirror `$changes` feed.

### File-list pipeline

Use when new files land in object storage and need to be appended to an Iceberg table — log ingestion is the canonical case.

```sql
select incremental.create_file_list_pipeline(
    'ingest_logs',
    's3://my-bucket/logs/*.json.gz',
    $$
        insert into logs_iceberg
        select ts, level, message, _filename
        from crunchy_lake.query($1)
    $$
);
```

Signature:

```sql
create_file_list_pipeline(
    pipeline_name       text,
    file_pattern        text,
    command             text,
    list_function       text   default 'crunchy_lake.list_files',
    batched             bool   default false,
    max_batch_size      int    default 100,
    schedule            text   default '*/15 * * * *',
    execute_immediately bool   default true,
    max_batches_per_run int    default -1
)
```

Default schedule is every 15 minutes — object-storage listing is more expensive than table polling, so the default cadence is slower than the other pipeline types.

## Managing pipelines

```sql
-- Fire a pipeline manually (runs only if new data exists)
call incremental.execute_pipeline('sync_events_to_iceberg');

-- Clear progress tracking and re-run from the beginning
-- (REQUIRED after truncating/rebuilding the source — see warning below)
call incremental.reset_pipeline('sync_events_to_iceberg');

-- Tear down — removes the pipeline and its pg_cron job
call incremental.drop_pipeline('sync_events_to_iceberg');

-- Mark a problem file as processed without importing it
-- (file-list pipelines only)
call incremental.skip_file('ingest_logs', 's3://my-bucket/logs/corrupt.json.gz');
```

## Inspecting state

```sql
-- One view per pipeline type
select * from incremental.sequence_pipelines;
select * from incremental.time_interval_pipelines;
select * from incremental.file_list_pipelines;

-- Files a file-list pipeline has processed
select * from incremental.processed_files
where pipeline_name = 'ingest_logs';

-- Underlying pg_cron jobs and their run history
select * from cron.job;
select * from cron.job_run_details order by start_time desc limit 20;
```

## Choosing a sync pattern

| Pattern | Use when |
|---------|----------|
| **pg_incremental pipeline** (this doc) | Continuous sync with exactly-once, cross-run state, bounded work per run — time-windowed, sequence-bounded, or file-list |
| **pg_cron staging-table flush** (`iceberg-tables.md`) | Streaming single-row inserts — buffer them in a transient staging table and flush to Iceberg periodically to avoid small-file sprawl. No cross-run state; each run drains whatever accumulated |
| **Plain `INSERT ... SELECT`** | One-shot backfill or bulk copy. No scheduling, no state — just load the data |

## End-to-end: operational PG table → Iceberg → Snowflake

A pipeline feeds the Iceberg side in PG. To expose that Iceberg table to Snowflake with auto-refresh, pair this with the catalog-integration flow in `snowflake-catalog-integration.md`:

1. Create the operational table and its Iceberg mirror in PG (see `iceberg-tables.md`)
2. Bulk-copy existing rows (`INSERT INTO mirror SELECT * FROM operational`)
3. Create a time-interval or sequence pipeline to keep the mirror current
4. Expose the Iceberg table to Snowflake via `CATALOG_SOURCE = SNOWFLAKE_POSTGRES` — per-table or catalog-linked database (see `snowflake-catalog-integration.md`)
5. Enable `AUTO_REFRESH = TRUE` on the Snowflake Iceberg table so query results stay current

Two cadences govern freshness end-to-end:

- The pipeline's `schedule` controls how fresh the PG-side Iceberg table is relative to the operational table
- `REFRESH_INTERVAL_SECONDS` on the Snowflake catalog integration controls how fresh Snowflake's view is relative to PG's Iceberg metadata

Match both to the freshness SLA the consumer needs — tighter cadences cost more (pg_cron overhead + Snowpipe polling), looser cadences let data age.
