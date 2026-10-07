---
name: rollback
description: "Plan and execute rollback/failback if migration encounters critical issues. Use for: rollback plan, failback, reverse migration, abort migration, undo cutover, reverse replication, point-in-time recovery, dual-write strategy, rollback triggers, post-cutover recovery."
parent_skill: migrate
---

# Rollback & Failback Strategy

> **Windows users:** see [references/windows.md](../../references/windows.md) — install prereqs, credential file paths (`%APPDATA%\postgresql\` instead of `~/`), and command-flow notes differ on native Windows. WSL behaves as Linux.

## When to Load

Main skill routes here for: "rollback plan", "failback", "reverse migration", "abort migration", "undo cutover"

> **Credentials:** Reverse-replication CREATE SUBSCRIPTION must use `migrate/scripts/setup_replication.py`, which constructs the DSN in-process from `~/.pgpass`. Never interpolate passwords into heredoc DSNs in chat. See `migrate/SKILL.md` "Credentials" callout for details.

## Why This Matters

**A migration without a rollback plan is gambling with production.**

Common scenarios requiring rollback:
- Performance degradation on target
- Application compatibility issues discovered post-cutover
- Data integrity problems
- Unexpected downtime during cutover window

## Rollback Strategies by Migration Method

### Strategy A: Reverse Replication (Recommended for Logical Rep)

Setup bidirectional replication BEFORE cutover so you can switch back.

#### A.1 Pre-Cutover: Setup Reverse Replication

**⚠️ Use the safe-DSN helper. Reverse replication makes the original SOURCE the subscriber and the new TARGET the publisher — for setup_replication.py, this means swapping `--source-service` and `--target-service` from their forward-direction roles.**

```bash
# 1. Create reverse publication on the new TARGET (Snowflake Postgres)
psql "service=sf_target connect_timeout=10" --no-psqlrc --quiet -c "CREATE PUBLICATION reverse_pub FOR ALL TABLES;"

# 2. Create reverse subscription on the original SOURCE (Postgres).
#    --source-service points at sf_target (because TARGET is the publisher
#    in reverse direction); --target-service points at the original source
#    where the subscription will live.
#    --no-enabled keeps the subscription dormant until rollback is invoked.
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/setup_replication.py \
    create-subscription \
    --source-service sf_target --target-service prod_source \
    --subscription-name reverse_sub \
    --publication-name reverse_pub \
    --no-enabled --no-copy-data
```

The helper resolves the password for `sf_target` from `~/.pgpass`, constructs the DSN in-process, and executes `CREATE SUBSCRIPTION` on `prod_source`. The password never appears in chat transcripts or shell history.

**Operator-only fallback (NOT chat-safe — agent must not run this):**

```bash
# ⚠️ Only safe in a trusted shell where $TARGET_PGPASSWORD was set BEFORE the
# session started. The literal `password=$TARGET_PGPASSWORD` interpolation
# point ends up in the chat transcript when an agent runs it.
source ~/.pg_migration_env
setup_connection "TARGET"
psql --no-psqlrc --quiet << 'EOF'
CREATE PUBLICATION reverse_pub FOR ALL TABLES;
EOF

setup_connection "SOURCE"
psql --no-psqlrc --quiet \
    -v target_host="$TARGET_PGHOST" \
    -v target_port="${TARGET_PGPORT:-5432}" \
    -v target_db="$TARGET_PGDATABASE" \
    -v target_user="$TARGET_PGUSER" \
    -v target_pass="$TARGET_PGPASSWORD" << 'EOF'
CREATE SUBSCRIPTION reverse_sub
    CONNECTION format('host=%s port=%s dbname=%s user=%s password=%s sslmode=require',
        :'target_host', :'target_port', :'target_db', :'target_user', :'target_pass')
    PUBLICATION reverse_pub
    WITH (enabled = false, copy_data = false);
EOF
```

#### A.2 During Normal Operation

- Primary replication: Source → Target (forward)
- Reverse subscription: Disabled, ready to activate

#### A.3 If Rollback Needed

```sql
-- Step 1: Stop applications writing to TARGET
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM app_user;

-- Step 2: Wait for forward replication to drain
-- Check: SELECT * FROM pg_stat_replication; (lag should be 0)

-- Step 3: Disable forward subscription on TARGET
ALTER SUBSCRIPTION forward_sub DISABLE;

-- Step 4: Enable reverse subscription on SOURCE
ALTER SUBSCRIPTION reverse_sub ENABLE;

-- Step 5: Wait for reverse sync to catch up
-- Monitor lag until zero

-- Step 6: Switch applications back to SOURCE
-- Update connection strings/DNS
```

### Strategy B: Point-in-Time Recovery (PITR)

For pg_dump migrations or when reverse replication isn't possible.

#### B.1 Pre-Cutover Preparation

```bash
# Take a PITR-compatible backup of SOURCE before cutover
pg_basebackup -h <source_host> -D /backup/pre_cutover -Fp -Xs -P

# Note the exact cutover timestamp
echo "Cutover started: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> migration_log.txt
```

#### B.2 If Rollback Needed

```bash
# Restore SOURCE to pre-cutover state
pg_restore --clean --if-exists -d <database> /backup/pre_cutover

# Or restore to specific point in time
recovery_target_time = '2026-02-12 14:30:00 UTC'
```

**⚠️ WARNING**: PITR rollback loses all data written to TARGET after cutover.

### Strategy C: Dual-Write Period (Zero Data Loss)

For critical systems where no data loss is acceptable.

#### C.1 Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Application │────▶│  Write Proxy │────▶│   SOURCE     │
│              │     │              │────▶│   TARGET     │
└──────────────┘     └──────────────┘     └──────────────┘
                                                 │
                                          Both receive
                                          all writes
```

#### C.2 Implementation Options

- **Application-level**: Modify app to write to both DBs
- **Proxy-level**: Use pgpool-II or similar to duplicate writes
- **CDC-based**: Use Debezium to replicate writes both directions

#### C.2 Rollback

Simply point applications back to SOURCE - no data lost.

**⚠️ Complexity**: Requires conflict resolution if reads happen on both.

## Rollback Decision Matrix

| Scenario | Strategy | Data Loss Risk | Complexity |
|----------|----------|----------------|------------|
| Performance issues on target | Reverse Replication | Low | Medium |
| App compatibility issues | Reverse Replication | Low | Medium |
| Data corruption discovered | PITR | Medium-High | Low |
| Critical bug in target | Reverse Replication | Low | Medium |
| Complete target failure | PITR | High | Low |
| Regulatory/compliance block | Dual-Write | None | High |

## Pre-Cutover Checklist for Rollback Readiness

```
## Rollback Readiness Checklist

Before proceeding to cutover, verify:

[ ] Reverse replication subscription created (disabled)
[ ] SOURCE backup taken with PITR capability
[ ] Rollback runbook documented with step-by-step commands
[ ] Rollback tested in staging/dev environment
[ ] Team knows rollback decision criteria
[ ] Rollback decision-maker identified
[ ] Communication plan for rollback scenario
[ ] Estimated rollback time documented
```

## Rollback Triggers

Define clear criteria for when to rollback:

| Trigger | Threshold | Action |
|---------|-----------|--------|
| Query latency | >2x baseline for 15+ min | Investigate, consider rollback |
| Error rate | >1% of transactions | Immediate rollback |
| Data inconsistency | Any detected | Immediate rollback |
| Application failures | >3 services affected | Immediate rollback |
| Replication lag | Stuck >30 min | Investigate, consider rollback |

## Post-Rollback Actions

If rollback executed:

1. **Stabilize** - Ensure SOURCE is operating normally
2. **Investigate** - Root cause analysis on TARGET issues
3. **Communicate** - Notify stakeholders of rollback and timeline
4. **Document** - Update runbook with lessons learned
5. **Replan** - Schedule new migration window after fixes

## Output

- Rollback strategy selected and documented
- Reverse replication configured (if applicable)
- Rollback runbook with specific commands
- Team trained on rollback procedure

## Stopping Points

- ✋ Before configuring reverse replication
- ✋ After rollback testing in staging
- ✋ During cutover if rollback criteria met
