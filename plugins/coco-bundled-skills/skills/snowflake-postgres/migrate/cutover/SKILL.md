---
name: cutover
description: "Step-by-step cutover runbook with timing, GO/NO-GO checkpoints, and rollback windows. Use for: cutover plan, go-live, switch over, migration day, cutover checklist, application switchover, sequence sync, post-migration cleanup."
parent_skill: migrate
---

# Cutover Runbook

> **Windows users:** see [references/windows.md](../../references/windows.md) — install prereqs, credential file paths (`%APPDATA%\postgresql\` instead of `~/`), and command-flow notes differ on native Windows. WSL behaves as Linux.

## When to Load

Main skill routes here for: "cutover plan", "go-live", "switch over", "migration day", "cutover checklist"

> **Credentials:** `cutover_tools.py` accepts `--source-service` / `--target-service`; passwords resolve from `~/.pgpass`, never CLI or chat. See `migrate/SKILL.md` "Credentials" callout for details.

## Prerequisites

- Migration method completed (replication synced OR dump restored)
- Validation passed (row counts, checksums verified)
- Rollback strategy in place
- Team assembled and communication channels ready

## Cutover Tools (RECOMMENDED)

Generate the full cutover runbook (sequence sync + trigger management) using Python:

```bash
# Preferred, chat-safe workflow:
# Generate cutover SQL scripts
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/cutover_tools.py all \
    --source-service prod_source \
    --output cutover_runbook.sql

# Or generate individual pieces:
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/cutover_tools.py sequences \
    --source-service prod_source -o seq_sync.sql
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/cutover_tools.py triggers \
    --source-service prod_source -o triggers.sql

# Execute sequence sync directly on target:
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/cutover_tools.py sequences \
    --source-service prod_source --target-service sf_target --execute

# Trusted-shell fallback:
# Generate cutover SQL scripts
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/cutover_tools.py all \
    --host $SOURCE_PGHOST -d $SOURCE_PGDATABASE -U $SOURCE_PGUSER \
    --output cutover_runbook.sql

# Or generate individual pieces:
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/cutover_tools.py sequences -H $SOURCE_PGHOST -d $SOURCE_PGDATABASE -U $SOURCE_PGUSER -o seq_sync.sql
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/cutover_tools.py triggers -H $SOURCE_PGHOST -d $SOURCE_PGDATABASE -U $SOURCE_PGUSER -o triggers.sql

# Execute sequence sync directly on target:
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/cutover_tools.py sequences -H $SOURCE_PGHOST -d $SOURCE_PGDATABASE -U $SOURCE_PGUSER \
    --execute --target-host $TARGET_PGHOST --target-dbname $TARGET_PGDATABASE --target-user $TARGET_PGUSER
```

## Pre-Cutover Checklist (T-24 hours)

```
## Day Before Cutover

[ ] Replication lag at zero (or dump/restore complete)
[ ] Validation report approved
[ ] Rollback strategy tested
[ ] All team members confirmed availability
[ ] Stakeholders notified of maintenance window
[ ] Monitoring dashboards ready
[ ] Runbook printed/accessible offline
[ ] Emergency contacts list ready
```

## Cutover Runbook

### Phase 1: Preparation (T-30 min)

| Step | Action | Command/Check | Est. Time | Owner |
|------|--------|---------------|-----------|-------|
| 1.1 | Verify replication lag | `SOURCE: SELECT * FROM pg_stat_replication;` | 1 min | DBA |
| 1.2 | Notify stakeholders | Send "cutover starting" message | 1 min | PM |
| 1.3 | Open monitoring dashboards | Grafana/PMM ready | 2 min | DBA |
| 1.4 | Verify rollback readiness | Reverse sub exists, backup confirmed | 2 min | DBA |
| 1.5 | Final validation spot-check | Compare 3 table row counts | 5 min | DBA |

**GO/NO-GO Decision Point #1**

```
All preparation checks passed?
- YES: Proceed to Phase 2
- NO: Abort, reschedule
```

### Phase 2: Stop Writes (T-0)

| Step | Action | Command | Est. Time |
|------|--------|---------|-----------|
| 2.1 | Revoke write permissions on SOURCE | See SQL below | 30 sec |
| 2.2 | Verify no active transactions | Check `pg_stat_activity` | 1 min |
| 2.3 | Note cutover timestamp | Record in log | 10 sec |

```sql
-- 2.1: Revoke writes (faster than stopping services)
REVOKE INSERT, UPDATE, DELETE, TRUNCATE 
ON ALL TABLES IN SCHEMA public 
FROM app_user, api_user, batch_user;

-- 2.2: Verify no active writes
SELECT pid, usename, application_name, state, query
FROM pg_stat_activity 
WHERE state != 'idle' 
AND query NOT LIKE '%pg_stat%';
```

### Phase 3: Final Sync (Logical Replication Only)

| Step | Action | Command | Est. Time |
|------|--------|---------|-----------|
| 3.1 | Wait for replication lag = 0 | Monitor `pg_stat_replication` on SOURCE | 1-5 min |
| 3.2 | Verify TARGET row counts | Run validation query on TARGET | 2 min |
| 3.3 | Sync sequences | Run sequence sync script | 1 min |

```sql
-- 3.1: Check replication lag on SOURCE (publisher)
SELECT 
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    pg_wal_lsn_diff(sent_lsn, replay_lsn) AS lag_bytes
FROM pg_stat_replication;

-- 3.3: Sync sequences (generate and run)
SELECT 'SELECT setval(''' || n.nspname || '.' || c.relname || ''', ' || 
       (pg_sequence_last_value(c.oid) + 1000) || ');'
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'S'
AND n.nspname NOT IN ('pg_catalog', 'information_schema');
```

**GO/NO-GO Decision Point #2**

```
Replication fully synced and sequences updated?
- YES: Proceed to Phase 4
- NO: Investigate or rollback
```

### Phase 4: Switch Applications

| Step | Action | Est. Time |
|------|--------|-----------|
| 4.1 | Update DNS/connection strings to TARGET | 1-5 min |
| 4.2 | Restart/redeploy applications (if needed) | 5-10 min |
| 4.3 | Verify applications connecting to TARGET | 2 min |

```sql
-- 4.3: Verify connections on TARGET
SELECT 
    application_name, 
    client_addr, 
    count(*) 
FROM pg_stat_activity 
WHERE datname = current_database()
GROUP BY application_name, client_addr;
```

### Phase 5: Validation (T+10 min)

| Step | Action | Est. Time |
|------|--------|-----------|
| 5.1 | Run smoke tests | 5 min |
| 5.2 | Check application logs for errors | 3 min |
| 5.3 | Verify critical workflows | 5 min |
| 5.4 | Monitor query performance | 5 min |

**GO/NO-GO Decision Point #3**

```
All validations passed?
- YES: Proceed to Phase 6 (Cleanup)
- NO: Execute rollback procedure
```

### Phase 6: Cleanup (T+30 min, after monitoring period)

| Step | Action | Est. Time |
|------|--------|-----------|
| 6.1 | Disable forward replication subscription | 1 min |
| 6.2 | Notify stakeholders of success | 1 min |
| 6.3 | Keep SOURCE running (24-48 hr safety period) | - |
| 6.4 | Tear down replication artifacts on both sides | 5 min |
| 6.5 | Schedule SOURCE decommission | - |

```sql
-- 6.1: Disable replication (on TARGET)
ALTER SUBSCRIPTION migration_sub DISABLE;
-- Don't DROP yet - keep for potential rollback
```

**Step 6.4: Drop replication artifacts (after the safety window)**

Once the rollback window has closed, tear down subscriptions, publications,
slots, and migration test objects on both sides in one pass:

```bash
# Preview first
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/post_migration_cleanup.py \
    --source-service prod_source --target-service sf_target --dry-run

# Execute
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/post_migration_cleanup.py \
    --source-service prod_source --target-service sf_target
```

The script returns a non-zero exit code if any DROP fails so a CI job can
flag stale artifacts; failures are also printed individually rather than
swallowed.

**Step 6.4 verification: confirm the artifacts are really gone**

Run these checks after cleanup completes. Adjust the names if you used custom
subscription / slot names.

```sql
-- On SOURCE: publication removed
SELECT pubname
FROM pg_publication
WHERE pubname = 'snowflake_migration';

-- On SOURCE: replication slots removed
SELECT slot_name
FROM pg_replication_slots
WHERE slot_name IN ('migration_sub', 'migrate_from_source', 'reverse_sub');

-- On TARGET: enabled subscription workers gone
SELECT subname, pid
FROM pg_stat_subscription
WHERE subname IN ('migration_sub', 'migrate_from_source', 'reverse_sub');

-- Optional on TARGET, if your Snowflake Postgres target exposes pg_subscription:
SELECT subname
FROM pg_subscription
WHERE subname IN ('migration_sub', 'migrate_from_source', 'reverse_sub');
```

Expect zero rows from each query after cleanup. If you used
`--subscription-name <custom_name>` with `post_migration_cleanup.py`, verify
that exact name instead of the defaults above.

## Application Connection Audit

**CRITICAL**: Before cutover, audit ALL database consumers:

```sql
-- Find all connection sources (run during normal operations)
SELECT DISTINCT
    application_name,
    client_addr,
    usename
FROM pg_stat_activity
WHERE datname = current_database();
```

**Check these often-forgotten consumers:**
- [ ] Cron jobs / scheduled tasks
- [ ] CI/CD pipelines
- [ ] Admin scripts
- [ ] Monitoring/alerting systems
- [ ] Data pipelines (Airflow, etc.)
- [ ] Analytics tools
- [ ] Backup systems
- [ ] Other microservices
- [ ] Argo Workflows / Kubernetes jobs
- [ ] Third-party integrations

## Timing Estimates

| Migration Type | Expected Downtime |
|----------------|-------------------|
| Logical Replication | 5-15 minutes |
| pg_dump (small <10GB) | 30-60 minutes |
| pg_dump (medium 10-100GB) | 1-4 hours |
| pg_dump (large >100GB) | 4+ hours |

## Communication Templates

### Pre-Cutover (T-24hr)
```
Subject: [Planned] Database Migration - [DATE] [TIME]

We will be performing a database migration from [SOURCE] to Snowflake Postgres.

Maintenance Window: [START] - [END]
Expected Impact: [Brief write unavailability / Full downtime]
Affected Systems: [List]

Contact: [Name] at [Phone/Slack]
```

### Cutover Start (T-0)
```
Subject: [In Progress] Database Migration Starting Now

Database migration is now in progress.
Status updates will be posted every 15 minutes.
```

### Cutover Complete
```
Subject: [Complete] Database Migration Successful

Migration completed at [TIME].
All systems operational.
Please report any issues to [Contact].
```

### Rollback (if needed)
```
Subject: [Action Required] Database Migration Rolled Back

Migration has been rolled back due to [brief reason].
Applications restored to previous database.
New migration window TBD.
```

## Output

- Executed cutover with documented timeline
- Validation confirmation
- Stakeholder notifications sent

## Stopping Points

- ✋ GO/NO-GO #1: Before stopping writes
- ✋ GO/NO-GO #2: Before switching applications  
- ✋ GO/NO-GO #3: Before cleanup (rollback window)
