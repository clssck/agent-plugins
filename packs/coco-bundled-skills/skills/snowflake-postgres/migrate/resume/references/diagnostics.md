# Diagnostic Commands & Recovery Procedures

## Diagnostic Commands Cheat Sheet

```sql
-- === RUN ON SOURCE ===

-- Publication status
SELECT * FROM pg_publication;
SELECT * FROM pg_publication_tables;

-- Replication slot status  
SELECT slot_name, active, restart_lsn,
    pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained_wal
FROM pg_replication_slots;

-- Active replication connections
SELECT * FROM pg_stat_replication;


-- === RUN ON TARGET ===

-- NOTE: pg_stat_subscription, pg_subscription_rel, and
-- pg_stat_subscription_stats are the portable Snowflake Postgres checks.
-- Some targets may also expose pg_subscription; if yours does, you can use
-- it as an additional verification query, but the diagnostics below avoid
-- depending on it.

-- Subscription worker(s): if rows exist, the subscription is enabled and
-- has a worker connected; subname is reported here too so this stands in
-- for the old `SELECT subname, subenabled FROM pg_subscription` query.
SELECT subname, pid, received_lsn, last_msg_send_time, last_msg_receipt_time
FROM pg_stat_subscription;

-- Table sync status
SELECT srrelid::regclass AS table_name, srsubstate 
FROM pg_subscription_rel ORDER BY srsubstate;

-- Sync summary
SELECT srsubstate, count(*) FROM pg_subscription_rel GROUP BY srsubstate;

-- Recent errors (if pg_stat_subscription_stats exists)
SELECT * FROM pg_stat_subscription_stats;
```

## Recovery from Common Interruption Scenarios

### Scenario: Cortex Code Session Timed Out

1. **Don't panic** - replication continues without Cortex Code
2. Run diagnostic commands above to determine state
3. Update your state file
4. Resume from appropriate phase

### Scenario: Source Database Connection Lost

```sql
-- On TARGET: Subscription will show errors
SELECT * FROM pg_stat_subscription;
-- last_msg_receipt_time will be stale

-- When connection restored:
-- Subscription auto-reconnects (usually)
-- If not, restart it:
ALTER SUBSCRIPTION migration_sub DISABLE;
ALTER SUBSCRIPTION migration_sub ENABLE;
```

### Scenario: Target Instance Unavailable

```sql
-- On SOURCE: Slot will show inactive
SELECT slot_name, active FROM pg_replication_slots;

-- WAL will accumulate - monitor disk space!
SELECT pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn))
FROM pg_replication_slots WHERE slot_name = 'migration_sub';

-- When target restored:
-- Replication resumes automatically from slot position
```

### Scenario: Replication Slot Dropped

**This is serious** - you may need to restart initial sync:

```sql
-- On SOURCE: Recreate slot
SELECT pg_create_logical_replication_slot('migration_sub', 'pgoutput');

-- On TARGET: Point subscription to new slot
ALTER SUBSCRIPTION migration_sub SET (slot_name = 'migration_sub');

-- May need to resync tables
ALTER SUBSCRIPTION migration_sub REFRESH PUBLICATION;
```
