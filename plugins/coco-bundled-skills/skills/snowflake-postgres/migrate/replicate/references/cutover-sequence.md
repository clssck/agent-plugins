# Cutover Sequence Reference

This document covers the cutover process from source to Snowflake Postgres.

## Step 6: Cutover Preparation

### 6.1 Pre-Cutover Checklist

| Check | Command | Expected |
|-------|---------|----------|
| All tables synced | `TARGET: SELECT * FROM pg_subscription_rel WHERE srsubstate != 'r'` | Empty result |
| Lag < 1 MB | `SOURCE: check pg_replication_slots` | Minimal lag |
| No errors | `TARGET: SELECT * FROM pg_stat_subscription` | No `last_msg_send_time` delays |

### 6.2 ⚠️ PROMPT: Cutover Approval

**Before executing cutover, ASK the user with `ask_user_question`:**

```
Pre-cutover checklist complete. Ready to execute cutover.

⚠️ WARNING: Cutover will:
- Stop writes to source database
- Switch application connections to Snowflake Postgres
- This is the point of no return

Confirm you are ready to proceed:

1) Execute cutover now - All stakeholders notified, maintenance window active
2) Run final validation first - One more check before cutover
3) Schedule for later - Not ready yet, save progress
4) Show rollback plan - Review rollback options before proceeding
```

## Step 7: Execute Cutover

**⚠️ MANDATORY CHECKPOINT**: Cutover is the point of no return. Confirm:
1. All stakeholders notified
2. Rollback plan documented
3. Maintenance window scheduled

### 7.1 Stop Writes to Source

```sql
-- On SOURCE: Revoke write access (optional, or stop applications)
REVOKE INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public FROM app_user;
```

### 7.2 Wait for Final Sync

```sql
-- On SOURCE: Wait for lag to reach 0
SELECT pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn))
FROM pg_replication_slots WHERE slot_name LIKE 'migrate%';
-- Should show '0 bytes'
```

### 7.3 Run Final Validation Gate

Before flipping applications, run the final targeted validation pass for the
cutover scope. Load `validate/SKILL.md` and confirm the critical tables and
workflows are clean while writes are still stopped on the source.

```sql
-- Examples of final pre-switch checks
-- Row counts match for critical tables
-- Checksums / aggregates match for the cutover scope
-- Application write path is disabled on SOURCE
```

If final validation does not pass, do NOT switch applications yet. Investigate,
re-run validation, or abort cutover.

### 7.4 Sync Sequences (FINAL PRE-SWITCH STEP)

**⚠️ CRITICAL**: Sequence values are not replicated. Generate and apply the
sequence sync after writes stop and lag reaches zero, but before applications
begin writing to Snowflake Postgres.

### 7.4.1 Auto-Detect All Sequences on Source

```bash
source ~/.pg_migration_env
setup_connection "SOURCE"

# List all sequences in the schema
psql --no-psqlrc --quiet -t -A <<'EOF'
SELECT sequence_schema || '.' || sequence_name AS sequence_fqn
FROM information_schema.sequences
WHERE sequence_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY sequence_schema, sequence_name;
EOF
```

### 7.4.2 Generate Sequence Sync Commands

```bash
source ~/.pg_migration_env
# Use the maintained helper instead of hand-written MAX(id) SQL.
# It reads source sequence state, quotes identifiers safely, and applies the
# standard +1000 cutover buffer.
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/cutover_tools.py sequences \
    -H "$SOURCE_PGHOST" -d "$SOURCE_PGDATABASE" -U "$SOURCE_PGUSER" \
    --buffer 1000 \
    --output /tmp/sequence_sync.sql

echo "Generated $(wc -l < /tmp/sequence_sync.sql | tr -d ' ') sequence sync commands"
```

### 7.4.3 Apply Sequence Values on Target

```bash
setup_connection "TARGET"
psql --no-psqlrc --quiet -f /tmp/sequence_sync.sql
```

**⚠️ SERIAL/BIGSERIAL note:** `cutover_tools.py sequences` already includes
owned serial/bigserial sequences. Do not append separate hand-written
`MAX(column)` SQL for those sequences.

### 7.4.4 Verify Sequences

```sql
-- On SNOWFLAKE POSTGRES: Verify sequence values
SELECT n.nspname || '.' || c.relname AS sequence_name,
       pg_sequence_last_value(c.oid) AS current_value
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'S'
AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1;
```

**⚠️ IMPORTANT**: The +1000 buffer ensures new inserts get unique IDs even if
there's slight timing overlap.

### 7.5 Switch Applications to Snowflake Postgres

Update application connection strings to point to Snowflake Postgres only after
lag is zero, final validation has passed, and sequence values have been applied
on the target.

### 7.6 Keep Source Readable During Rollback Window

Keep the source online and readable for the rollback window after the flip. Do
not disable or drop the subscription immediately after switching applications.

## Step 8: Post-Cutover Validation

Load `validate/SKILL.md` for comprehensive validation while the source remains
available for rollback if needed.

### 8.1 Quick Checks

```sql
-- Row counts match
-- Data checksums match
-- Application functionality verified
```

### 8.2 Deep Data Verification

**Ask user to select verification method while the rollback window is still open:**

```
How would you like to verify the migration?

1) Skip verification - No validation (not recommended)
2) Row counts only - Quick validation using SQL queries
3) Execute SnowConvert - Automated schema analysis (requires Python 3.8+)
4) Execute pgCompare - Automated data comparison (requires Java 21+)
5) Execute both tools - SnowConvert + pgCompare (recommended for production)
6) Show SnowConvert instructions - Manual setup guide
7) Show pgCompare instructions - Manual setup guide
```

**Based on selection, load `validate/SKILL.md` and execute the corresponding section.**

## Step 9: Close Rollback Window and Disable Subscription

Only after post-cutover validation passes and the rollback window closes:

```sql
-- On SNOWFLAKE POSTGRES: Disable subscription
ALTER SUBSCRIPTION migrate_from_source DISABLE;

-- Optionally drop after the rollback window closes
-- DROP SUBSCRIPTION migrate_from_source;
```

## Stopping Points

- ✋ Before creating publication on source
- ✋ Before creating Snowflake Postgres instance (billable)
- ✋ Before creating subscription
- ✋ Before cutover (point of no return)
- ✋ Before dropping subscription
