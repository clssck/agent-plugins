---
name: monitor
description: "Monitor replication health, lag, and migration progress. Use for: monitor replication, check lag, replication status, migration progress, WAL bloat, slot health, sync state, replication dashboard, replication slot inactive, subscription worker errors."
parent_skill: migrate
---

# Migration Monitoring

> **Windows users:** see [references/windows.md](../../references/windows.md) — install prereqs, credential file paths (`%APPDATA%\postgresql\` instead of `~/`), and command-flow notes differ on native Windows. WSL behaves as Linux.

## When to Load

Main skill routes here for: "monitor replication", "check lag", "replication status", "migration progress", "WAL bloat"

> **Credentials:** `migration_monitor.py` accepts `--source-service` / `--target-service`; passwords resolve from `~/.pgpass`, never CLI or chat. See `migrate/SKILL.md` "Credentials" callout for details.

## Safe Background-Agent Usage

Background agents are appropriate here when the job is long-running and the work is **observation only**.

- Safe: watch initial sync, track lag, monitor long dump/restore progress, and report when thresholds are reached.
- Not safe: creating or dropping subscriptions, changing credentials, running cutover steps, or triggering rollback from a background agent.
- If the expected wait may outlive the current session, pause cleanly and route to `../resume/SKILL.md` instead of relying on a long-lived background watcher.

## Python Monitoring Tools (RECOMMENDED)

Use `<SKILL_DIR>/migrate/scripts/migration_monitor.py` which connects directly to databases (no psql needed):

```bash
# Monitor initial sync progress (on target)
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/migration_monitor.py sync \
    --target-service sf_target

# Monitor replication lag (on source)
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/migration_monitor.py replication \
    --source-service prod_source

# Full dashboard (both databases)
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/migration_monitor.py dashboard \
    --source-service prod_source --target-service sf_target

# One-shot row count progress comparison
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/migration_monitor.py row-progress \
    --source-service prod_source --target-service sf_target
```

Legacy `--host` / `--target-host` flags remain supported for trusted-shell workflows.

## Fallback: SQL-based Monitoring

If Python is not available, use the SQL queries below directly.

## Initial Sync Progress Monitoring

When logical replication starts with `copy_data = true`, PostgreSQL copies all existing data before streaming changes. Monitor progress:

### Check Table Sync States (on TARGET)

> **Snowflake Postgres note:** `pg_subscription_rel` and `pg_stat_subscription` are the portable target-side monitoring surfaces on Snowflake Postgres. Some targets may also expose `pg_subscription`; if yours does, you can use it as an extra verification query, but all monitoring below sticks to the portable path. To enumerate subscriptions by name, query the source side or use the subscription names you set when running `setup_replication.py`.

```sql
-- See which tables are syncing and their state
SELECT 
    srrelid::regclass AS table_name,
    CASE srsubstate
        WHEN 'i' THEN 'initializing'
        WHEN 'd' THEN 'data copying'  -- Currently syncing
        WHEN 'f' THEN 'finished table copy'
        WHEN 's' THEN 'synchronized (streaming)'
        WHEN 'r' THEN 'ready'
    END AS sync_state,
    srsublsn AS lsn
FROM pg_subscription_rel
ORDER BY srsubstate, table_name;
```

### Summary of Sync Progress

```sql
-- Count tables by state
SELECT 
    CASE srsubstate
        WHEN 'i' THEN 'initializing'
        WHEN 'd' THEN 'copying data'
        WHEN 'f' THEN 'finished copy'
        WHEN 's' THEN 'streaming'
        WHEN 'r' THEN 'ready'
    END AS state,
    count(*) AS table_count
FROM pg_subscription_rel
GROUP BY srsubstate
ORDER BY srsubstate;
```

### Watch Active Sync Workers

```sql
-- See what subscription workers are doing right now
SELECT 
    pid,
    relid::regclass AS currently_syncing,
    received_lsn,
    last_msg_send_time,
    last_msg_receipt_time,
    now() - last_msg_receipt_time AS time_since_last_msg
FROM pg_stat_subscription;
```

### Estimate Progress by Row Count

```sql
-- Compare loaded rows (run on TARGET)
SELECT 
    schemaname || '.' || relname AS table_name,
    n_live_tup AS rows_loaded
FROM pg_stat_user_tables
WHERE n_live_tup > 0
ORDER BY n_live_tup DESC
LIMIT 20;
```

### State Reference

| State | Code | Meaning |
|-------|------|---------|  
| Initializing | `i` | Worker starting up |
| Data copy | `d` | **Currently copying rows** (bulk INSERT) |
| Finished | `f` | Table copy complete, waiting for others |
| Synced | `s` | Streaming live changes |
| Ready | `r` | Fully synchronized |

**✅ Initial sync complete when all tables show `s` (synchronized) or `r` (ready).**

---

## Replication Health Dashboard

### Key Metrics to Monitor

| Metric | Warning | Critical | Query |
|--------|---------|----------|-------|
| Replication lag (bytes) | >100MB | >1GB | See below |
| Replication lag (time) | >5 min | >30 min | See below |
| WAL retention size | >10GB | >50GB | See below |
| Slot inactive time | >1 hour | >6 hours | See below |

### 1. Replication Lag Monitoring

```sql
-- On SOURCE: Check replication lag
SELECT 
    client_addr,
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    pg_size_pretty(pg_wal_lsn_diff(sent_lsn, replay_lsn)) AS lag_size,
    pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn)) AS pending_wal
FROM pg_stat_replication;

-- Lag in seconds (approximate). Uses reply_time, which is the time of the
-- most recent reply received from the standby/subscriber — populated on the
-- primary. (pg_last_xact_replay_timestamp() is a standby-only function and
-- returns NULL when called on the source/primary, so it cannot be used here.)
SELECT 
    application_name,
    EXTRACT(EPOCH FROM (now() - reply_time)) AS lag_seconds
FROM pg_stat_replication;
```

### 2. Replication Slot Health

```sql
-- Check slot status and WAL retention
SELECT 
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained_wal
FROM pg_replication_slots;
```

**⚠️ WARNING**: Inactive slots cause WAL bloat! Monitor `retained_wal`.

### 3. WAL Directory Size

```sql
-- Check WAL directory size
SELECT 
    pg_size_pretty(sum(size)) AS wal_size,
    count(*) AS wal_files
FROM pg_ls_waldir();
```

### 4. Subscription Status (on TARGET)

> **Snowflake Postgres note:** To get subscription health on a Snowflake target, use `pg_stat_subscription` plus the per-table state in `pg_subscription_rel` — that path is portable across targets. If your target also exposes `pg_subscription`, you can use it as an additional verification query, but do not make monitoring depend on it. To check what slot a subscription points at, query the source side or use the names you set when running `setup_replication.py`.

```sql
-- Check subscription worker status (works on Snowflake Postgres)
SELECT 
    pid,
    relid::regclass AS table_name,
    received_lsn,
    last_msg_send_time,
    last_msg_receipt_time
FROM pg_stat_subscription;

-- Per-table sync state (works on Snowflake Postgres)
SELECT
    srrelid::regclass AS table_name,
    srsubstate
FROM pg_subscription_rel
ORDER BY srsubstate, table_name;
```

## Alerting Rules

### Critical Alerts (Page immediately)

```yaml
# Replication stopped
- alert: ReplicationStopped
  condition: pg_stat_replication rows = 0
  action: Check network, credentials, slot status

# WAL bloat critical
- alert: WALBloatCritical
  condition: retained_wal > 50GB
  action: Check inactive slots, replication lag

# Slot inactive
- alert: SlotInactive
  condition: slot.active = false for > 6 hours
  action: Drop orphaned slot or restart replication
```

### Warning Alerts (Investigate within 1 hour)

```yaml
# High replication lag
- alert: HighReplicationLag
  condition: lag_bytes > 100MB OR lag_seconds > 300
  action: Check target performance, network

# WAL retention growing
- alert: WALRetentionGrowing
  condition: retained_wal > 10GB
  action: Verify replication is consuming WAL
```

## Common Issues & Fixes

### Issue: Replication Lag Increasing

**Symptoms:** `lag_bytes` growing continuously

**Causes & Fixes:**

| Cause | Fix |
|-------|-----|
| Target too slow | Increase target resources (compute pool) |
| Network bottleneck | Check network latency/bandwidth |
| Long-running queries on target | Kill blocking queries |
| High write volume on source | Consider batching or throttling |
| Missing indexes on target | Add indexes matching source |

### Issue: Replication Slot WAL Bloat

**Symptoms:** `pg_wal` directory growing, disk filling

```sql
-- Find the problematic slot
SELECT 
    slot_name,
    active,
    pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained
FROM pg_replication_slots
ORDER BY pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) DESC;

-- If slot is orphaned (no active replication), drop it
-- ⚠️ CAUTION: Only drop if you're sure replication is not needed
DROP REPLICATION SLOT orphaned_slot_name;
```

### Issue: Subscription Worker Crashed

**Symptoms:** No data flowing, subscription shows errors

```sql
-- Check subscription errors
SELECT * FROM pg_stat_subscription_stats;

-- Restart subscription
ALTER SUBSCRIPTION sub_name DISABLE;
ALTER SUBSCRIPTION sub_name ENABLE;
```

### Issue: Conflict on Target (Duplicate Key)

**Symptoms:** Replication stops with unique constraint violation

```sql
-- Skip the conflicting transaction (use carefully!)
-- First, note the LSN from error message
SELECT pg_replication_origin_advance('pg_<sub_oid>', '<lsn>');

-- Or resolve by fixing the data
DELETE FROM target_table WHERE id = <conflicting_id>;
-- Then restart subscription
```

## Performance Baseline Capture

Before cutover, capture baseline metrics to compare after:

```sql
-- Save this output for comparison
SELECT 
    'Before Migration' AS snapshot,
    now() AS timestamp,
    (SELECT count(*) FROM pg_stat_user_tables) AS table_count,
    (SELECT sum(n_live_tup) FROM pg_stat_user_tables) AS total_rows,
    (SELECT count(*) FROM pg_stat_activity WHERE state = 'active') AS active_connections;

-- Top 10 slowest queries (if pg_stat_statements enabled)
SELECT 
    calls,
    round(total_exec_time::numeric, 2) AS total_ms,
    round(mean_exec_time::numeric, 2) AS mean_ms,
    query
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

## Monitoring Checklist During Migration

```
## Continuous Monitoring During Replication Sync

Every 15 minutes:
[ ] Check replication lag (should be decreasing or stable)
[ ] Check WAL retention size (should not be growing excessively)
[ ] Verify slot is active

Every hour:
[ ] Compare row counts on key tables
[ ] Check source disk space
[ ] Review error logs on both source and target

Before cutover:
[ ] Lag at zero for 5+ minutes
[ ] No pending large transactions
[ ] No error messages in logs
```

## Output

- Real-time replication status
- Alert recommendations
- Troubleshooting guidance

## Stopping Points

- ✋ If replication lag >1GB (investigate before proceeding)
- ✋ If WAL bloat >50GB (fix before cutover)
- ✋ If subscription errors detected
