---
name: resume
description: "Track migration progress and pause/resume/repeat phases. Use for: resume migration, migration status, where did I leave off, continue migration, pause migration, repeat phase, re-run validation, redo pg_dump, lost connection, migration state, recover after interruption."
parent_skill: migrate
---

# Migration State Tracking, Pause/Resume & Phase Repeat

> **Windows users:** see [references/windows.md](../../references/windows.md) — install prereqs, credential file paths (`%APPDATA%\postgresql\` instead of `~/`), and command-flow notes differ on native Windows. WSL behaves as Linux.

## When to Load

Main skill routes here for: "resume migration", "migration status", "where did I leave off", "continue migration", "migration state", "lost connection", "pause migration", "repeat phase", "re-run phase", "redo validation"

> **Credentials:** Resume/repeat workflows re-invoke migration scripts that all accept `--source-service` / `--target-service`; passwords resolve from `~/.pgpass`, never CLI or chat. See `migrate/SKILL.md` "Credentials" callout for details.

## Why This Matters

Migrations span days or weeks. You will need to:
- **Planned pause** — stop after a phase (e.g., wait days for initial sync) and resume in a new session
- **Repeat a phase** — re-run validation or pg_dump before cutover
- **Recover from interruption** — session timeout, network drop, system issue

**This guide covers all three workflows.**

## Quick State Check

Run these queries to determine where you are:

### 1. Check if Snowflake Postgres Instance Exists

```sql
-- In Snowflake (not Postgres)
SHOW POSTGRES INSTANCES;
```

### 2. Check Subscription State (on TARGET)

> **Snowflake Postgres note:** `pg_stat_subscription` and `pg_subscription_rel` are the portable target-side checks for resume/status on Snowflake Postgres. Some targets may also expose `pg_subscription`; if yours does, you can use it as an additional verification query (for example, to confirm a subscription was dropped), but the resume flow should not depend on it. To get subscription names, use the names you set when running `setup_replication.py`, or query the source-side replication slots.

```sql
-- Active subscription workers and last-message timestamps (works on
-- Snowflake Postgres). If this returns rows, a subscription is enabled and
-- has a worker connected — pause was likely "between phases", resume can
-- continue from initial-sync or streaming as appropriate.
SELECT pid, relid::regclass AS currently_syncing,
       received_lsn, last_msg_receipt_time
FROM pg_stat_subscription;

-- What's the per-phase sync state?
SELECT 
    CASE srsubstate
        WHEN 'i' THEN 'initializing'
        WHEN 'd' THEN 'copying data'
        WHEN 'f' THEN 'finished copy'
        WHEN 's' THEN 'streaming'
        WHEN 'r' THEN 'ready'
    END AS state,
    count(*) AS tables
FROM pg_subscription_rel
GROUP BY srsubstate;
```

### 3. Check Replication Slot (on SOURCE)

```sql
-- Does slot exist? Is it active?
SELECT slot_name, active, restart_lsn,
    pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS lag
FROM pg_replication_slots
WHERE slot_name LIKE '%migration%';
```

### 4. Check Publication (on SOURCE)

```sql
-- Does publication exist?
SELECT pubname, puballtables 
FROM pg_publication;

-- What tables are published?
SELECT * FROM pg_publication_tables;
```

## State Decision Tree

```
START: What state is the migration in?
│
├─► No Snowflake Postgres instance exists
│   └─► Resume from: ASSESS or CREATE INSTANCE
│
├─► Instance exists, no schema on target
│   └─► Resume from: SCHEMA DDL
│
├─► Schema applied, no subscription (hybrid/replication method)
│   └─► Resume from: LOGICAL REPLICATION setup
│
├─► Subscription exists, tables in 'i' or 'd' state
│   └─► Initial sync in progress — WAIT or check for errors
│   └─► [COMMON PAUSE POINT: days/weeks while sync completes]
│
├─► Subscription exists, all tables in 's' or 'r' state
│   ├─► Hybrid + dump_timing=now: pg_dump phase not done → DUMP NON-REPLICABLE
│   ├─► Hybrid + dump_timing=cutover: proceed to VALIDATE (dump deferred)
│   └─► Replication-only: proceed to VALIDATE
│
├─► Subscription exists but disabled
│   └─► May need to re-enable: ALTER SUBSCRIPTION x ENABLE;
│
├─► pg_dump phase completed, MVs not refreshed
│   └─► Resume from: MATERIALIZED VIEWS
│
├─► Validation incomplete or needs re-run
│   └─► Resume from: VALIDATE (repeatable)
│
├─► Validation passed, cutover not done
│   └─► Resume from: CUTOVER planning
│   └─► If hybrid + dump_timing=cutover: cutover includes dump phase
│
└─► Cutover completed
    └─► Migration complete — proceed to cleanup
```

## Planned Pause Workflow

Use this when you want to stop after a phase and return later (e.g., wait for initial sync).

> **When advising on a pause, ALWAYS include both:**
> 1. **State capture via SQL** — show the user how to inspect `pg_stat_subscription`, `pg_subscription_rel` (portable target-side checks on Snowflake Postgres), and `pg_replication_slots` (source-side) so they can verify where they are. If the target also exposes `pg_subscription`, it can be used as an extra verification query, but do not make resume depend on it.
> 2. **Update `migration_state.yaml`** — this is what makes "resume" pick up at the correct phase in a future session. Without it, the next session has to re-derive state from scratch.
>
> Capturing replication state in SQL is great for verification, but it is NOT a substitute for the state file — a future "resume my postgres migration" call reads the YAML first.

### Step 1: Check if the phase supports pausing

Phases generated by `generate_hybrid_plan.py` include `pause_after` and `repeatable` flags. Phases where `pause_after: true` are safe long-term pause points. Phases where `pause_after: false` (sequence sync, cutover dump) mean writes are stopped — minimize downtime, do not pause.

### Step 2: Update state file before exiting

**Load** `resume/references/state-file-template.md` if `migration_state.yaml` does not yet exist in the working directory — copy the template, then update.

Set the following fields:
- `phases.<current_phase>.status: completed` and `completed_at: <ISO timestamp>`
- `last_phase_completed: <phase name>`
- `next_action: <description of next step>`
- `paused_at: <ISO timestamp>` and `paused_after_phase: <phase name>` (only when pausing for a future session)

Use `ask_user_question` to confirm:
```
question: "Which phase did you just complete?"
header: "Pause"
options:
  - label: "Pre-Migration Setup"
  - label: "Roles"
  - label: "Schema DDL"
  - label: "Logical Replication"
  - label: "pg_dump"
  - label: "Validation"
```

### Step 3: Resume in a new session

Say: "resume my postgres migration" or "continue migration"

The skill will:
1. Read `migration_state.yaml` if it exists
2. Run diagnostic queries to auto-detect current state
3. Place you at the correct phase
4. Show next steps

## Repeat Phase Workflow

Use this to re-run a phase before moving forward (e.g., re-validate, re-dump).

### Which phases are repeatable?

| Phase | Repeatable | Notes |
|-------|-----------|-------|
| Pre-Migration Setup | Yes | Connectivity tests are idempotent |
| Migrate Roles | Yes | Roles are idempotent (CREATE IF NOT EXISTS) |
| Schema DDL | Yes | Drop and re-apply, or use --if-not-exists |
| Logical Replication | No | Do not recreate subscription — it triggers full re-sync |
| pg_dump (non-replicable) | Yes | Truncate target tables first, then re-dump |
| Materialized Views | Yes | REFRESH is idempotent |
| Sequence Sync | Yes | Values are read fresh from source each time |
| Cutover Dump + Seq Sync | Yes | Safe if cutover is aborted and restarted |
| Validation | Yes | Run as many times as needed |

### How to repeat a phase

Say: "repeat phase 5" or "re-run validation" or "redo the pg_dump phase"

The skill will:
1. Confirm which phase to repeat
2. Show any prerequisites (e.g., truncate tables before re-dump)
3. Execute the phase commands
4. Update the state file

### Repeat-phase prerequisites

**pg_dump phase**: Truncate target tables before re-dumping to avoid duplicate data:
```sql
-- On TARGET: truncate non-replicable tables before re-dump
TRUNCATE TABLE schema.unlogged_table;
TRUNCATE TABLE schema.no_pk_table;
```

**Schema DDL**: If schema has changed on source, drop and re-apply:
```bash
pg_dump -h $SOURCE_PGHOST -U $SOURCE_PGUSER -d $SOURCE_PGDATABASE --schema-only --no-owner -f schema.sql
python <SKILL_DIR>/migrate/scripts/filter_vendor_dump.py schema.sql > schema_clean.sql
psql --no-psqlrc -h $TARGET_PGHOST -d $TARGET_PGDATABASE -f schema_clean.sql
```

**Validation**: No prerequisites — just re-run:
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/validate_migration.py --host $SOURCE_PGHOST --dbname $SOURCE_PGDATABASE --user $SOURCE_PGUSER \
    --target-host $TARGET_PGHOST --target-dbname $TARGET_PGDATABASE --target-user $TARGET_PGUSER --mode full
```

## State File

The canonical schema for `migration_state.yaml` lives in [`references/state-file-template.md`](references/state-file-template.md).

**When to load that reference:**
- **First time creating the file** (start of a migration after assessment approval) — copy the template into `migration_state.yaml`.
- **Updating fields during a pause** — confirm field names and the `phases.<name>.status` enum.
- **Resuming a session** — confirm what the file's `last_phase_completed` and `next_action` should look like before reading the user's actual file.

The reference includes the full YAML schema, a field-by-field reference table, and instructions for how the pause/resume/repeat workflows interact with the file.

## Resume Procedures by Phase

### Resume: Assessment Incomplete

```
1. Run pre-migration checks on source (assess/SKILL.md)
2. Get user approval before proceeding
```

### Resume: Instance Not Created

```sql
-- Check if instance exists
SHOW POSTGRES INSTANCES;
```

```bash
# If not, create it with pg_connect.py so the saved service profile and
# ~/.pgpass entry exist for the later migration steps.
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py \
    --create \
    --instance-name migration_target \
    --compute-pool <COMPUTE_FAMILY> \
    --storage <GB>
```

### Resume: Publication/Subscription Not Created

```sql
-- On SOURCE: Check/create publication
SELECT * FROM pg_publication WHERE pubname = 'migration_pub';
-- If not exists:
CREATE PUBLICATION migration_pub FOR ALL TABLES;

-- On TARGET: Check whether the subscription's worker is connected.
-- pg_stat_subscription is the portable Snowflake Postgres check here; a row
-- means the named subscription exists and is enabled. If your target also
-- exposes pg_subscription, you can additionally query it to confirm disable /
-- drop state outside the active-worker path.
SELECT subname, pid, received_lsn, last_msg_receipt_time
FROM pg_stat_subscription WHERE subname = 'migration_sub';

-- If no row above, the subscription is missing or disabled. Recreate via the
-- safe-DSN helper (keeps the password out of chat / shell history / argv;
-- see `../scripts/setup_replication.py` and `../replicate/SKILL.md`).
-- Operator-only SQL form (NOT chat-safe — agent must not run this because it interpolates the password literal):
CREATE SUBSCRIPTION migration_sub
    CONNECTION 'host=<source> dbname=<db> user=<user> password=<pass>'
    PUBLICATION migration_pub;
```

### Resume: Initial Sync In Progress

```sql
-- Check sync progress (on TARGET)
SELECT 
    srsubstate AS state,
    count(*) AS tables
FROM pg_subscription_rel
GROUP BY srsubstate;

-- If stuck, check for errors:
SELECT * FROM pg_stat_subscription;

-- Check logs for replication worker errors
```

**If sync appears stuck:**
```sql
-- Restart subscription worker
ALTER SUBSCRIPTION migration_sub DISABLE;
ALTER SUBSCRIPTION migration_sub ENABLE;
```

### Resume: Replication Streaming (Ready for Validation)

```sql
-- Verify all tables are streaming
SELECT count(*) FROM pg_subscription_rel WHERE srsubstate NOT IN ('s', 'r');
-- Should return 0

-- Proceed to validation
-- See validate/SKILL.md
```

### Resume: Validation Incomplete

```sql
-- Re-run row count comparison
SELECT 
    schemaname || '.' || relname AS table_name,
    n_live_tup AS row_count
FROM pg_stat_user_tables
ORDER BY relname;

-- Compare with source
```

### Resume: Cutover Not Started

```
1. Verify replication lag is zero
2. Verify validation passed
3. Confirm rollback strategy is in place
4. Schedule cutover window
5. Follow `../cutover/SKILL.md`
```

### Resume: Cutover In Progress

**⚠️ CRITICAL**: Cutover is time-sensitive. Determine exactly where it stopped:

```sql
-- On SOURCE: Are writes stopped?
-- Check for recent transactions
SELECT max(xact_start) FROM pg_stat_activity WHERE state != 'idle';

-- On TARGET: Is lag at zero?
SELECT * FROM pg_stat_subscription;

-- Has DNS been switched?
-- Check externally: nslookup <app_db_hostname>
```

**If cutover was interrupted:**
1. If writes NOT stopped yet → Can safely restart cutover
2. If writes stopped, lag at zero, DNS not switched → Switch DNS
3. If DNS switched → Verify apps are connecting to target

For detailed diagnostic commands and recovery procedures, see `resume/references/diagnostics.md`.

## Best Practices for Resilience

1. **Save state file locally** — update `migration_state.yaml` after each phase
2. **Note LSN positions** — especially before manual operations
3. **Screenshot key outputs** — publication, slot, subscription info
4. **Document connection strings** — securely, not in chat
5. **Set calendar reminders** — for checking long-running syncs
6. **Source your env file** — `source ~/.pg_migration_env` at session start
7. **Plan pause points** — schema DDL and logical replication are the most common long pauses
8. **Run validation before cutover** — repeat the validation phase to confirm data integrity

## Output

- Current migration state determined
- Resume point identified
- Next actions provided
- Phase repeat prerequisites shown (if repeating)

## Stopping Points

- ⚠️ Before any destructive recovery action
- ⚠️ Before dropping/recreating replication slot
- ⚠️ Before restarting initial sync (loses progress)
- ⚠️ Before repeating pg_dump phase (must truncate target tables first)
