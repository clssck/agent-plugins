---
name: large-db
description: "Replica-assisted initial sync for very large PostgreSQL databases (500 GB+, especially 1 TB+). Use for: large database migration, terabyte migration, TB migration, replica sync, fast initial load, minimize source load, RDS S3 Parquet export, pg_lake-based migration, Aurora clone migration."
parent_skill: migrate
---

# Large Database Migration (Replica-Assisted Sync)

> **Windows users:** see [references/windows.md](../../references/windows.md) — install prereqs, credential file paths (`%APPDATA%\postgresql\` instead of `~/`), and command-flow notes differ on native Windows. WSL behaves as Linux.

## Table of Contents

- [Why Use This Technique](#why-use-this-technique)
- [When to Use](#when-to-use)
- [Architecture Overview](#architecture-overview)
- [Workflow](#workflow)
- [Timing Estimates](#timing-estimates)
- [Critical Checkpoints](#critical-checkpoints)
- [Troubleshooting](#troubleshooting)

## When to Load

Main skill routes here for: "large database migration", "replica sync", "fast initial load", "terabyte migration", "minimize source load"

> **Credentials:** Always prefer `migrate/scripts/setup_replication.py` over raw `CREATE SUBSCRIPTION` SQL — the helper constructs the DSN in-process from `~/.pgpass` so passwords never touch the command line or chat transcript. See `migrate/SKILL.md` "Credentials" callout for details.

## Why Use This Technique

Standard logical replication initial sync has limitations:
- **Slow**: Logical decoding is slower than pg_dump/COPY
- **Source load**: Initial sync puts load on production database
- **Long sync window**: Large databases can take days to sync via logical rep

**This technique** uses a physical replica to export data, then repositions logical replication to catch up from the snapshot point.

## When to Use

| Database Size | Recommended Approach |
|---------------|---------------------|
| < 100 GB | Standard logical replication (`replicate/SKILL.md`) — too small to benefit from replica-assisted setup |
| 100 GB - 500 GB | Consider this technique |
| 500 GB - 2 TB | **Strongly recommended**, especially on RDS / Aurora where snapshot/clone primitives make replica setup cheap |
| ≥ 2 TB | **Required** for reasonable timelines — auto-routed by `migrate/SKILL.md` |
| RDS/Aurora ≥ 2 TB with S3 export | Use `references/rds-parquet-export.md` (pg_lake) instead of pg_dump from a replica |

`migrate/SKILL.md` auto-routes here when `total_size_bytes >= 2_000_000_000_000` or the user mentions TB / "S3 export" hints. Below 2 TB the operator can still opt in — the trade-off is replica-assisted is faster but requires a replica and a maintenance window to pause it, while standard logical replication is simpler but the initial sync can take days for 500 GB+.

## Architecture Overview

### On-Premises (Replica Pause)

```
┌─────────────────┐     Physical         ┌─────────────────┐
│     SOURCE      │     Replication      │     REPLICA     │
│   (Production)  │ ──────────────────▶  │   (Snapshot)    │
│                 │                      │                 │
│  Publication    │                      │  Pause WAL      │
│  (created but   │                      │  Apply at LSN   │
│   not active)   │                      │                 │
└────────┬────────┘                      └────────┬────────┘
         │                                        │
         │ Logical Rep                            │ pg_dump / COPY
         │ (catches up                            │ (initial load)
         │  after sync)                           │
         │                                        │
         │            ┌─────────────────┐         │
         └───────────▶│     TARGET      │◀────────┘
                      │ (Snowflake PG)  │
                      └─────────────────┘
```

### Cloud Platforms (Clone/Snapshot)

```
┌─────────────────┐                      ┌─────────────────┐
│     SOURCE      │   Clone/Restore      │     CLONE       │
│   (Production)  │ ──────────────────▶  │   (Snapshot)    │
│                 │   at LSN             │                 │
│  Publication    │                      │  Ephemeral -    │
│  Repl Slot      │                      │  delete after   │
│                 │                      │  export done    │
└────────┬────────┘                      └────────┬────────┘
         │                                        │
         │ Logical Rep                            │ pg_dump / COPY
         │ (repositioned                          │ (initial load)
         │  to clone LSN)                         │
         │                                        │
         │            ┌─────────────────┐         │
         └───────────▶│     TARGET      │◀────────┘
                      │ (Snowflake PG)  │
                      └─────────────────┘
```

**For platform-specific instructions (AWS, Azure, GCP), see `references/platform-specific.md`**

**For RDS S3 Parquet export with pg_lake, see `references/rds-parquet-export.md`**

## Workflow

### Phase 1: Setup (No Data Movement Yet)

#### 1.1 Create Publication on SOURCE (Disabled)

```sql
-- On SOURCE (production)
CREATE PUBLICATION migration_pub FOR ALL TABLES;
SELECT * FROM pg_publication;
```

#### 1.2 Create Subscription on TARGET (Disabled, No Copy)

**Preferred — use the safe-DSN helper:**

```bash
# Disabled, no initial copy, no slot creation — we'll wire the slot manually
# in step 5 after the replica snapshot has been loaded.
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/setup_replication.py \
    create-subscription \
    --source-service prod_source --target-service sf_target \
    --subscription-name migration_sub \
    --publication-name migration_pub \
    --no-enabled --no-copy-data --no-create-slot
```

The helper resolves the source password from `~/.pgpass` and constructs the DSN in-process, so the password never appears in chat transcripts or shell history.

#### 1.3 Create Replication Slot on SOURCE

```sql
-- On SOURCE
SELECT pg_create_logical_replication_slot('migration_sub', 'pgoutput');
SELECT pg_current_wal_lsn();  -- Note for reference
```

### Phase 2: Prepare Replica Snapshot

#### 2.1 Ensure Replica is in Sync

```sql
-- On REPLICA
SELECT pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn(),
       pg_wal_lsn_diff(pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn()) AS lag_bytes;
```

#### 2.2 Pause WAL Apply on Replica

```sql
-- On REPLICA
SELECT pg_wal_replay_pause();
SELECT pg_is_wal_replay_paused();  -- Should return 't'

-- ⚠️ CRITICAL: Record this LSN
SELECT pg_last_wal_replay_lsn() AS snapshot_lsn;
```

**⚠️ IMPORTANT**: Write down the `snapshot_lsn` - you'll need it to position the subscription.

### Phase 3: Export Data from Replica

```bash
# Export from REPLICA (not source!)
pg_dump --host=<replica_host> --port=5432 --username=<user> --dbname=<database> \
    --format=custom --jobs=8 --no-owner --no-privileges --file=replica_dump.pgdump

# For very large databases, use directory format
pg_dump --host=<replica_host> --format=directory --jobs=16 --file=replica_dump_dir/
```

### Phase 4: Load Data into Target

```bash
# Restore to Snowflake Postgres
pg_restore --host=<snowflake_pg_host> --port=5432 --username=<user> --dbname=<database> \
    --jobs=8 --no-owner --no-privileges replica_dump.pgdump
```

#### Verify Row Counts

```sql
-- On both REPLICA and TARGET, compare key tables
SELECT schemaname || '.' || relname AS table_name, n_live_tup AS row_count
FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 20;
```

### Phase 5: Position and Enable Logical Replication

#### 5.1 Advance Replication Slot to Snapshot LSN

```sql
-- On SOURCE
SELECT pg_replication_slot_advance('migration_sub', '<snapshot_lsn>');

-- Verify
SELECT slot_name, confirmed_flush_lsn FROM pg_replication_slots WHERE slot_name = 'migration_sub';
```

#### 5.2 Associate Subscription with Slot

```sql
-- On TARGET (Snowflake Postgres)
ALTER SUBSCRIPTION migration_sub SET (slot_name = 'migration_sub');

-- Use the portable Snowflake Postgres path here rather than depending on a
-- pg_subscription read. The replication origin name is
-- 'pg_<oid>' for every subscription, and pg_replication_origin_status IS
-- readable — use it to resolve the origin we just created and advance it
-- to the snapshot LSN. If multiple subscriptions exist on this target,
-- replace the subquery with the literal origin name from
-- `SELECT external_id FROM pg_replication_origin_status` so you advance the
-- right one.
SELECT pg_replication_origin_advance(
    (SELECT external_id
     FROM pg_replication_origin_status
     WHERE external_id LIKE 'pg\_%' ESCAPE '\'
     ORDER BY local_id DESC
     LIMIT 1),
    '<snapshot_lsn>'
);
```

#### 5.3 Enable Subscription

```sql
-- On TARGET
ALTER SUBSCRIPTION migration_sub ENABLE;
SELECT * FROM pg_stat_subscription;
```

### Phase 6: Cleanup

```sql
-- On REPLICA (if keeping it running)
SELECT pg_wal_replay_resume();

-- On SOURCE - monitor catch-up
SELECT slot_name, active,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn)) AS lag
FROM pg_replication_slots WHERE slot_name = 'migration_sub';
```

## Timing Estimates

| Phase | Duration (1TB database) |
|-------|------------------------|
| Setup (Phase 1) | 5-10 minutes |
| Pause replica (Phase 2) | 1 minute |
| pg_dump from replica (Phase 3) | 4-8 hours |
| pg_restore to target (Phase 4) | 4-8 hours |
| Reposition & enable (Phase 5) | 5-10 minutes |
| Catch-up period (Phase 6) | Depends on write rate |

**Comparison**: Standard logical rep initial sync for 1TB could take 24-72+ hours.

## Critical Checkpoints

```
### Before Starting
[ ] Replica exists and is in sync with source
[ ] Target (Snowflake Postgres) provisioned with adequate storage
[ ] Network bandwidth assessed for dump transfer
[ ] Maintenance window planned (replica will be paused)

### Phase 2 Checkpoint
[ ] Replica WAL replay paused
[ ] snapshot_lsn recorded: ____________________
[ ] No active transactions on replica

### Phase 4 Checkpoint  
[ ] Dump restore completed successfully
[ ] Row counts match between replica snapshot and target
[ ] Indexes and constraints verified

### Phase 5 Checkpoint (⚠️ CRITICAL)
[ ] Replication slot advanced to correct LSN
[ ] Subscription origin set correctly
[ ] Subscription enabled and catching up
[ ] Monitoring shows lag decreasing
```

## Troubleshooting

### Subscription Not Catching Up

```sql
SELECT * FROM pg_stat_subscription;
-- Check for errors in PostgreSQL logs
```

### LSN Mismatch Errors

```sql
-- On TARGET - check subscription's expected LSN
SELECT * FROM pg_replication_origin_status;

-- May need to re-advance origin
SELECT pg_replication_origin_advance('pg_<subscription_oid>', '<correct_lsn>');
```

### Slot Was Dropped

```sql
-- Recreate slot at the correct position
SELECT pg_create_logical_replication_slot('migration_sub', 'pgoutput');
SELECT pg_replication_slot_advance('migration_sub', '<snapshot_lsn>');
```

## Output

- Data loaded from replica snapshot
- Logical replication catching up from snapshot point
- Minimal load on production source during initial sync

## Parallel Data Transfer Strategies

For large databases, parallelism is critical for meeting migration timelines.

### Parallel pg_dump (Directory Format)

```bash
# -Fd = directory format (required for -j)
# -j 4 = 4 parallel workers
pg_dump -Fd -j 4 -f backup_dir/ \
    -h $SOURCE_PGHOST -d $SOURCE_PGDATABASE -U $SOURCE_PGUSER

# Parallel restore
pg_restore -Fd -j 4 -d $TARGET_PGDATABASE \
    -h $TARGET_PGHOST -U $TARGET_PGUSER backup_dir/
```

**Note:** `-j` (parallel) only works with `-Fd` (directory format), NOT `-Fc` (custom format).

### Parallel postgres_fdw (Multiple Sessions)

When using `postgres_fdw`, run multiple `INSERT INTO ... SELECT FROM` in parallel sessions:

```bash
# Session 1 (large table A):
psql --no-psqlrc -h $TARGET_PGHOST -d $TARGET_PGDATABASE -U $TARGET_PGUSER \
    -c "INSERT INTO target.table_a SELECT * FROM fdw_staging.table_a;"

# Session 2 (large table B):
psql --no-psqlrc -h $TARGET_PGHOST -d $TARGET_PGDATABASE -U $TARGET_PGUSER \
    -c "INSERT INTO target.table_b SELECT * FROM fdw_staging.table_b;"

# Run as many parallel sessions as your source can handle (typically 4-8)
```

### Choosing Parallel Strategy

| Strategy | Best For | Setup Complexity |
|----------|---------|-----------------|
| `pg_dump -Fd -j N` | Full database dump/restore | Low |
| `postgres_fdw` parallel sessions | Selective tables, hybrid migration | Medium |
| `pg_dumpall` | Multi-database cluster dump | Low (inherently serial) |
| Replica-assisted (above) | 500 GB+ databases, minimize source load | High |

For **multi-database** migrations, run `pg_dump` for each database in parallel:

```bash
# Parallel per-database dumps
pg_dump -Fd -j 4 -f db1_dir/ -h $SOURCE_PGHOST -d db1 -U $SOURCE_PGUSER &
pg_dump -Fd -j 4 -f db2_dir/ -h $SOURCE_PGHOST -d db2 -U $SOURCE_PGUSER &
pg_dump -Fd -j 4 -f db3_dir/ -h $SOURCE_PGHOST -d db3 -U $SOURCE_PGUSER &
wait
```

## Stopping Points

- ✋ Before pausing replica (confirm maintenance window)
- ✋ After recording snapshot LSN (critical value!)
- ✋ Before enabling subscription (verify LSN positioning)
- ✋ After enabling subscription (confirm catch-up is progressing)
