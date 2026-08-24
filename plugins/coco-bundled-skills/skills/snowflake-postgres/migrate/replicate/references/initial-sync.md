# Initial Sync Reference

This document covers the initial data synchronization phase of logical replication.

## Step 4: Create Subscription on Snowflake Postgres

**Prerequisites before this step:**
1. ✅ Network egress rule configured (Step 0.3)
2. ✅ Schema DDL applied to target (Step 3.3)
3. ✅ Publication created on source (Step 1.3)

### 4.1 Create Subscription

**⚠️ CRITICAL**: `CREATE SUBSCRIPTION ... WITH (create_slot = true)` cannot run inside a transaction block. The recommended path below handles autocommit correctly; the legacy psql heredoc / `-f` patterns at the end of this section are kept only for trusted-shell operators who can't use the Python helper.

#### Recommended: `setup_replication.py` (chat-safe)

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/setup_replication.py \
    create-subscription \
    --source-service prod_source --target-service sf_target \
    --subscription-name migrate_from_source \
    --publication-name snowflake_migration
```

The helper:
- Resolves the source password from `~/.pgpass` via `--source-service` (never on the command line, in shell history, or in chat transcripts).
- Builds the libpq DSN in-process with proper quoting and a 5-minute `connect_timeout` (large DBs need it for slot creation).
- Issues `CREATE SUBSCRIPTION` with `autocommit=True`, so the transaction-block error below cannot occur.
- Defaults to `copy_data=true, create_slot=true, enabled=true`. Flip with `--no-copy-data`, `--no-create-slot`, `--no-enabled` (the large-db replica-assisted path uses `--no-enabled --no-copy-data --no-create-slot`).
- Promotes saved verify-ca settings from the source service profile automatically; pass `--source-sslmode verify-ca` to force it from the CLI.

The only credential leak this path can't close is libpq's own behavior: `CREATE SUBSCRIPTION` stores the connection string (with password) in `pg_subscription` on the target. That's a Postgres protocol constraint, not a script-level issue.

#### Legacy: psql heredoc (trusted shell only — leaks credentials in chat)

> Only safe in a trusted shell where `$SOURCE_PGPASSWORD` was set BEFORE the session started AND will not be echoed by the agent. The literal command (with the `password=$SOURCE_PGPASSWORD` interpolation point) ends up in the chat transcript when run via an agent. Use `setup_replication.py` instead in any chat-driven workflow.

```bash
source ~/.pg_migration_env
setup_connection "TARGET"

CONN_STRING="host=$SOURCE_PGHOST port=${SOURCE_PGPORT:-5432} dbname=$SOURCE_PGDATABASE user=$SOURCE_PGUSER password=$SOURCE_PGPASSWORD sslmode=require"

psql --no-psqlrc <<EOF
CREATE SUBSCRIPTION migrate_from_source
CONNECTION '$CONN_STRING'
PUBLICATION snowflake_migration
WITH (copy_data = true, create_slot = true);
EOF
```

**Alternative legacy form: SQL file**
```bash
cat > /tmp/create_subscription.sql << SQLEOF
CREATE SUBSCRIPTION migrate_from_source
CONNECTION 'host=$SOURCE_PGHOST port=${SOURCE_PGPORT:-5432} dbname=$SOURCE_PGDATABASE user=$SOURCE_PGUSER password=$SOURCE_PGPASSWORD sslmode=require'
PUBLICATION snowflake_migration
WITH (copy_data = true, create_slot = true);
SQLEOF

setup_connection "TARGET"
psql --no-psqlrc -f /tmp/create_subscription.sql
rm -f /tmp/create_subscription.sql
```

**⚠️ If you see this error with the legacy path:**
```
ERROR: CREATE SUBSCRIPTION ... WITH (create_slot = true) cannot run inside a transaction block
```
**Solution**: Use `setup_replication.py` (which sets autocommit) or the heredoc / `-f` form above — never `psql -c`.

### 4.2 Monitor Initial Sync

```sql
-- On SNOWFLAKE POSTGRES: Check that the subscription worker is running.
-- pg_stat_subscription is the portable Snowflake Postgres check here; if a
-- row shows up below, the named subscription exists, is enabled, and has a
-- worker connected. If your target also exposes pg_subscription, you can use
-- it as an additional verification query, but the monitoring flow does not
-- depend on it.
SELECT subname, pid, received_lsn, last_msg_receipt_time
FROM pg_stat_subscription;

-- Check sync status per table (pg_subscription_rel IS readable)
SELECT srrelid::regclass AS table_name, srsublsn, srsubstate
FROM pg_subscription_rel;
-- States: i=initializing, d=data copying, s=synchronized, r=ready
```

```sql
-- On SOURCE: Check replication slot
SELECT slot_name, active, restart_lsn, confirmed_flush_lsn,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS lag
FROM pg_replication_slots
WHERE slot_name LIKE 'migrate%';
```

**Wait for all tables to reach state 'r' (ready) before cutover.**

### 4.3 ⚠️ PROMPT: Monitor Migration Progress

**After subscription is created, ASK the user with `ask_user_question`:**

```
The subscription has been created and initial data sync is starting.

How would you like to monitor the migration progress?

1) Live dashboard - Run migration_monitor.py with auto-refresh (recommended)
2) Manual checks - I'll run monitoring queries periodically
3) Background agent watcher - Keep a background agent watching progress and notify me when ready for cutover
4) Show me the commands - Display monitoring commands for me to run manually
```

**Based on selection:**

**Option 1 - Live Dashboard:**
```bash
# Recommended: service-profile flow (chat-safe)
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/migration_monitor.py \
    dashboard \
    --source-service prod_source --target-service sf_target

# Or, if you're using the legacy env-file flow instead of service profiles:
# source ~/.pg_migration_env
# python migrate/scripts/migration_monitor.py dashboard
# python migrate/scripts/migration_monitor.py sync
# python migrate/scripts/migration_monitor.py replication
```

**Option 2 - Manual Checks:**
Run the monitoring queries in Step 5 at regular intervals and report status to user.

**Option 3 - Background Agent Watcher:**
- Set up periodic checks (every 30 seconds)
- Notify user when all tables reach 'r' (ready) state
- Alert if errors or excessive lag detected
- Use this only for same-session observation; if the wait may last hours/days or outlive the session, pause cleanly and route to `../../resume/SKILL.md`

**Option 4 - Show Commands:**
Display the monitoring commands for the user to run themselves.

## Step 5: Monitor Replication Lag

### 5.1 Use Migration Monitor Script

```bash
# Recommended: service-profile flow (chat-safe)
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/migration_monitor.py \
    sync --target-service sf_target

uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/migration_monitor.py \
    replication --source-service prod_source

uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/migration_monitor.py \
    dashboard \
    --source-service prod_source --target-service sf_target

# Legacy env-file flow (only if you've sourced ~/.pg_migration_env already):
# python migrate/scripts/migration_monitor.py sync
# python migrate/scripts/migration_monitor.py replication
# python migrate/scripts/migration_monitor.py dashboard
```

### 5.2 Manual Monitoring Queries

```sql
-- On SOURCE: Monitor lag
SELECT 
    slot_name,
    pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn)) AS replication_lag,
    active
FROM pg_replication_slots
WHERE slot_type = 'logical';
```

```sql
-- On SNOWFLAKE POSTGRES: Check for errors
SELECT * FROM pg_stat_subscription;
```

**Replication should show minimal lag before cutover.**

### 5.3 ⚠️ PROMPT: Replication Status Check

**After initial sync completes and replication is running, ASK the user with `ask_user_question`:**

```
Replication is now running. Current status:
- Tables synced: [X] of [Y]
- Current lag: [Z] MB
- Errors: [None/List any]

What would you like to do?

1) Continue monitoring - Keep watching lag and sync status
2) Ready for cutover - Lag is acceptable, proceed to cutover preparation
3) Run validation - Verify data before cutover (recommended)
4) Check detailed status - Show per-table sync status and any issues
5) Pause here - I'll come back later to proceed with cutover
```

**Based on selection:**
- Option 1 → Continue Step 5 monitoring loop
- Option 2 → Proceed to Step 6 (Cutover Preparation)
- Option 3 → Load `validate/SKILL.md` and run validation
- Option 4 → Run detailed status queries and report
- Option 5 → Save state and provide resume instructions
