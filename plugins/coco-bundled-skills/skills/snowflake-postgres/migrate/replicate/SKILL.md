---
name: replicate
description: "Logical replication setup from PostgreSQL to Snowflake Postgres for near-zero downtime migration. Use for: logical replication, setup replication, live sync, near-zero downtime, publication, subscription, pglogical, CREATE SUBSCRIPTION, streaming replication, target-to-source connectivity."
parent_skill: migrate
---

# Logical Replication Migration

> **Windows users:** see [references/windows.md](../../references/windows.md) — install prereqs, credential file paths (`%APPDATA%\postgresql\` instead of `~/`), and command-flow notes differ on native Windows. WSL behaves as Linux.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Connection Variables](#connection-variables)
- [Step 0: Verify Connections](#step-0-verify-connections-mandatory)
- [Architecture](#architecture)
- [Migration Plan Display](#migration-plan-display)
- [Workflow Steps](#workflow)
- [Troubleshooting](#troubleshooting)

## When to Load

Main skill routes here for: "logical replication", "setup replication", "live sync", "near-zero downtime"

> **Credentials:** Use `--source-service` / `--target-service` flags; passwords resolve from `~/.pgpass`, never CLI or chat. See `migrate/SKILL.md` "Credentials" callout for details. (Env-var examples below are kept for operators running from a trusted shell only.)

## Prerequisites

- Assessment completed (no blocking issues)
- Source PostgreSQL 10+ with `wal_level = logical`
- All tables have primary keys or REPLICA IDENTITY
- Snowflake Postgres instance created
- Network connectivity between source and target
- **Connection configured** (service profiles preferred; see main skill for prompts and trusted-shell env-file flow)

## Connection Variables

This skill can use environment variables for the legacy `psql` steps below, but
the Python scripts prefer saved service profiles:

| Variable | Description | Example |
|----------|-------------|---------|
| `SOURCE_PGHOST` | Source PostgreSQL host | `source-db.example.com` |
| `SOURCE_PGPORT` | Source port (default: 5432) | `5432` |
| `SOURCE_PGDATABASE` | Source database name | `mydb` |
| `SOURCE_PGUSER` | Source migration user | `migration_user` |
| `TARGET_PGHOST` | Snowflake Postgres host | `sf-pg.example.com` |
| `TARGET_PGPORT` | Target port (default: 5432) | `5432` |
| `TARGET_PGDATABASE` | Target database name | `postgres` |
| `TARGET_PGUSER` | Target admin user | `admin` |

**Passwords**: Prefer service profiles backed by `~/.pgpass`. The legacy
env-file flow remains supported for trusted-shell `psql` examples below.

## Step 0: Verify Connections (MANDATORY)

**⚠️ ALWAYS run these checks before starting any migration work.**

### Recommended: Python Connectivity Test

Use `<SKILL_DIR>/scripts/shared/test_connectivity.py` for a comprehensive check (no psql needed):

```bash
# Preferred, chat-safe workflow:
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/shared/test_connectivity.py \
    --source-service prod_source --target-service sf_target

# Trusted-shell fallback:
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/shared/test_connectivity.py \
    --host $SOURCE_PGHOST -d $SOURCE_PGDATABASE -U $SOURCE_PGUSER \
    --target-host $TARGET_PGHOST --target-dbname $TARGET_PGDATABASE --target-user $TARGET_PGUSER
```

This tests DNS, TCP, PostgreSQL auth, replication settings, write access, and target-to-source network path in one pass.

### Fallback: Manual psql Verification

**Source the environment file first:**

```bash
source ~/.pg_migration_env
```

### 0.1 Verify Source Connection and Permissions

```bash
setup_connection "SOURCE"

psql --no-psqlrc --quiet <<'EOF'
SELECT 
    'SOURCE' AS connection,
    version() AS pg_version,
    current_database() AS database,
    current_user AS connected_user,
    pg_size_pretty(pg_database_size(current_database())) AS db_size;

SELECT rolname, rolreplication AS has_replication, rolcanlogin AS can_login
FROM pg_roles WHERE rolname = current_user;

SHOW wal_level;
EOF
```

**Required results:**
- Connection succeeds
- `rolreplication` = `t` (true)
- `wal_level` = `logical`

### 0.2 Verify Target Connection and Permissions

```bash
setup_connection "TARGET"

psql --no-psqlrc --quiet <<'EOF'
SELECT 
    'TARGET' AS connection,
    version() AS pg_version,
    current_database() AS database,
    current_user AS connected_user;

CREATE TABLE IF NOT EXISTS _migration_conn_test (id int);
DROP TABLE IF EXISTS _migration_conn_test;
SELECT 'Target write access verified' AS status;
EOF
```

### 0.3 Verify Network Connectivity (Target → Source) — MANDATORY PRE-TEST

**⚠️ CRITICAL: This step MUST pass before proceeding with logical replication setup. Do NOT skip this step.**

**⚠️ CRITICAL: Logical replication requires the TARGET (Snowflake Postgres) to connect TO the SOURCE.**

The subscriber (Snowflake Postgres) initiates connections to the publisher (source), so:
- Snowflake Postgres network rules must allow **egress** to the source host/port
- Source firewall/security groups must allow **ingress** from Snowflake Postgres IPs

#### Test Connectivity FROM Snowflake Postgres TO Source

**Use postgres_fdw for connectivity testing** (more reliable than dblink). This validates the exact network path that logical replication will use:

```bash
# Preferred: use saved service profiles so passwords stay in ~/.pgpass instead
# of shell args or psql variables.
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/shared/test_connectivity.py \
    --source-service <source_service_name> \
    --target-service <target_service_name>

# Or, if you've already sourced ~/.pg_migration_env, pass host/db/user flags
# only. The script reads SOURCE_PGPASSWORD / TARGET_PGPASSWORD from the
# environment without exposing them in the command line.
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/shared/test_connectivity.py \
    --host "$SOURCE_PGHOST" --dbname "$SOURCE_PGDATABASE" --user "$SOURCE_PGUSER" \
    --target-host "$TARGET_PGHOST" --target-dbname "$TARGET_PGDATABASE" --target-user "$TARGET_PGUSER"
```

#### If Connectivity Fails - Configure Network Rules

**⚠️ MANDATORY: Always confirm with the user before creating or modifying any network rules or network policies. Show the exact SQL that will be executed and wait for explicit approval.**

⚠️ **CRITICAL**: Snowflake Postgres egress rules MUST use:
- `TYPE = IPV4` (NOT `HOST_PORT`) 
- `MODE = POSTGRES_EGRESS` (NOT `EGRESS`)

```sql
-- On SNOWFLAKE (not Snowflake Postgres):
-- Step 1: Resolve source hostname to IP: dig +short <SOURCE_PGHOST>

CREATE OR REPLACE NETWORK RULE <database>.<schema>.migration_egress_rule
    TYPE = IPV4
    VALUE_LIST = ('<resolved_ip>/32')
    MODE = POSTGRES_EGRESS
    COMMENT = 'Egress to source PostgreSQL for migration';

ALTER NETWORK POLICY <your_network_policy> SET
    ALLOWED_NETWORK_RULE_LIST = (
        <existing_ingress_rule>,
        <database>.<schema>.migration_egress_rule
    );
```

**Common mistakes that cause "could not connect to publisher":**
| Mistake | Fix |
|---------|-----|
| Using `TYPE = HOST_PORT` | Use `TYPE = IPV4` |
| Using `MODE = EGRESS` | Use `MODE = POSTGRES_EGRESS` |
| Using hostname in VALUE_LIST | Resolve to IP with `dig +short` |
| Missing /32 CIDR suffix | Always use `<ip>/32` format |

**⚠️ DO NOT proceed until network connectivity is verified from Snowflake Postgres to Source.**

### 0.4 Verify Source pg_hba.conf Allows Replication

```bash
setup_connection "SOURCE"

psql --no-psqlrc --quiet <<'EOF'
SELECT current_setting('wal_level') AS wal_level,
       current_setting('wal_level') = 'logical' AS wal_level_ok,
       current_setting('max_replication_slots')::int AS max_replication_slots,
       (SELECT count(*) FROM pg_replication_slots) AS used_slots,
       current_setting('max_wal_senders')::int AS max_wal_senders,
       (SELECT count(*) FROM pg_stat_replication) AS active_senders;

SELECT slot_name, slot_type, active FROM pg_replication_slots;
EOF
```

**Required:** `wal_level_ok = t`, available slots > 0, available senders > 0.

If `wal_level != logical`, it requires a reboot:
```sql
-- RDS: modify parameter group, reboot
-- Self-hosted: ALTER SYSTEM SET wal_level = 'logical'; then restart PostgreSQL
```

### 0.5 AWS RDS: Verify Security Group Allows Inbound from Snowflake Postgres

**Skip this step if source is not AWS RDS.**

Snowflake Postgres IPs must be allowed through the RDS security group for logical replication:

```bash
# 1. Resolve Snowflake Postgres egress IP(s)
dig +short $TARGET_PGHOST

# 2. Check the RDS security group allows inbound on port 5432 from those IPs
# In AWS Console: RDS > Instance > Security Groups > Inbound Rules
# Or via CLI:
aws ec2 describe-security-groups --group-ids sg-XXXXXXXX \
    --query 'SecurityGroups[*].IpPermissions[?FromPort==`5432`]'
```

**Required:** Inbound rule allowing TCP 5432 from Snowflake Postgres IP(s).

If using a NAT Gateway or VPC peering, verify the route table allows traffic.

## Architecture

```
┌──────────────────────────┐                         ┌──────────────────────────┐
│   Source PostgreSQL      │                         │   Snowflake Postgres     │
│   (Publisher)            │                         │   (Subscriber)           │
│                          │                         │                          │
│  ┌────────────────────┐  │    TCP Connection      │  ┌────────────────────┐  │
│  │    Publication     │  │◀────────────────────────│  │    Subscription    │  │
│  │   (tables/schema)  │  │   (Target connects     │  │                    │  │
│  └────────────────────┘  │    TO Source)          │  └────────────────────┘  │
│                          │                         │                          │
│  WAL → pgoutput          │                         │  Apply worker pulls     │
│                          │                         │  changes via streaming  │
│  Port 5432 must accept   │                         │  Network rules must     │
│  inbound from Target     │                         │  allow EGRESS to Source │
└──────────────────────────┘                         └──────────────────────────┘

⚠️ NETWORK REQUIREMENT:
The SUBSCRIBER (Snowflake Postgres) initiates the connection TO the PUBLISHER (Source).
```

## Migration Plan Display

**After user confirms logical replication, display:**

```
╔═══════════════════════════════════════════════════════════════════════════════════╗
║         LOGICAL REPLICATION MIGRATION PLAN - PostgreSQL → Snowflake Postgres      ║
╠═══════════════════════════════════════════════════════════════════════════════════╣
│  STEP 0: Verify Network Connectivity (CRITICAL)                          ⚠ FIRST  │
│  STEP 0.5: Preflight Check - Verify target schemas are clean              ⚠ SAFETY │
│  STEP 1: Configure Source Database (wal_level, publication)                        │
│  STEP 2: Migrate Roles (if opted)                                                  │
│  STEP 3: Prepare Target (schema DDL BEFORE subscription)                           │
│  STEP 4: Create Subscription & Initial Sync                              ⏱ LONG   │
│  STEP 5: Monitor & Validate                                                        │
│  STEP 6: Cutover (Scheduled Maintenance Window)                          ⚠ FINAL  │
╚═══════════════════════════════════════════════════════════════════════════════════╝

Estimated Duration:
  • Setup (Steps 1-3):    ~30-60 min
  • Initial Sync (Step 4): Varies (typically 50-100 GB/hour)
  • Monitoring (Step 5):  Ongoing
  • Cutover (Step 6):     ~15-30 min
```

## Final Confirmation Before Migration

**⚠️ MANDATORY: Ask for final confirmation before proceeding:**

```
╔═══════════════════════════════════════════════════════════════════════════╗
║                      FINAL CONFIRMATION REQUIRED                          ║
╠═══════════════════════════════════════════════════════════════════════════╣
║  You are about to start a logical replication migration.                  ║
║                                                                           ║
║  This will:                                                               ║
║    ✓ Create a replication slot on your source database                   ║
║    ✓ Create schema objects on the Snowflake Postgres target              ║
║    ✓ Begin copying data (can take hours for large databases)             ║
║    ✓ Consume WAL space on source until replication catches up            ║
║                                                                           ║
║  Prerequisites confirmed:                                                 ║
║    [ ] Source connection verified                                         ║
║    [ ] Target connection verified                                         ║
║    [ ] Target schemas preflight check passed                              ║
║    [ ] wal_level = logical on source                                      ║
║    [ ] Network path from target to source verified                        ║
║    [ ] Assessment report reviewed                                         ║
╚═══════════════════════════════════════════════════════════════════════════╝

Proceed with migration? (yes/no):
```

## Workflow

**For detailed step-by-step instructions, load the appropriate reference:**

| Step | Reference Document |
|------|-------------------|
| Steps 1-3: Publication, Roles, Target Prep | `references/subscription-management.md` |
| Steps 4-5: Create Subscription, Monitor Sync | `references/initial-sync.md` |
| Steps 6-9: Cutover, Validation, Sequence Sync | `references/cutover-sequence.md` |

### Quick Reference: Key Commands

**Step 0.5: Preflight Check - Verify Target Schemas (MANDATORY)**

Before creating schemas on the target, verify that the migration schemas (except `public`) do not already exist with objects. This prevents conflicts and silent data corruption.

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/prepare_target.py preflight-check \
    --target-host $TARGET_PGHOST --target-dbname $TARGET_PGDATABASE --target-user $TARGET_PGUSER \
    --schemas public,analytics,reporting
```

**Create Publication (Source):**
```sql
-- For databases WITHOUT partitioned tables:
CREATE PUBLICATION snowflake_migration FOR ALL TABLES;

-- For databases WITH partitioned tables (PG 10-12):
CREATE PUBLICATION snowflake_migration FOR ALL TABLES WITH (publish_via_partition_root = true);

-- PostgreSQL 13+ handles partitioned tables natively in logical replication.
-- publish_via_partition_root is still recommended for consistent behavior.
```

**Create Subscription (use the safe-DSN helper — preferred):**

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/setup_replication.py \
    create-subscription \
    --source-service prod_source --target-service sf_target \
    --subscription-name migrate_from_source \
    --publication-name snowflake_migration
```

The helper resolves the source password from `~/.pgpass` (via `--source-service`), constructs the DSN in-process, and executes `CREATE SUBSCRIPTION` via psycopg2. The password never appears on the command line, in shell history, in chat transcripts, or in process argv. (Postgres still stores the password in the target's `pg_subscription` system catalog — that's a libpq subscription protocol constraint we can't avoid — but every other leakage path is closed.) Default `connect_timeout=300` (5 min) accommodates initial slot creation on large DBs.

Flag reference: `--no-copy-data`, `--no-create-slot`, `--no-enabled` flip the defaults; `--source-sslmode verify-ca` upgrades from `require` once the cert is in place.

**Operator-only fallback (NOT chat-safe — agent must not run this):**

```bash
# ⚠️ Only safe in a trusted shell where $SOURCE_PGPASSWORD was set BEFORE the
# session started AND will not be echoed by the agent. The literal command
# (with $SOURCE_PGPASSWORD interpolation point) ends up in the chat transcript.
psql --no-psqlrc <<EOF
CREATE SUBSCRIPTION migrate_from_source
CONNECTION 'host=$SOURCE_PGHOST dbname=$SOURCE_PGDATABASE user=$SOURCE_PGUSER password=$SOURCE_PGPASSWORD sslmode=require connect_timeout=300'
PUBLICATION snowflake_migration
WITH (copy_data = true, create_slot = true);
EOF
```

**Monitor Sync Status:**
```sql
SELECT srrelid::regclass, srsubstate FROM pg_subscription_rel;
-- States: i=initializing, d=data copying, s=synchronized, r=ready
```

**Monitor Lag:**
```sql
SELECT slot_name,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn)) AS lag
FROM pg_replication_slots WHERE slot_type = 'logical';
```

## Troubleshooting

| Error | Solution |
|-------|----------|
| "could not connect to publisher" | Check POSTGRES_EGRESS network rule with TYPE=IPV4 |
| "relation does not exist" | Apply schema DDL BEFORE creating subscription |
| "CREATE SUBSCRIPTION cannot run inside a transaction block" | Use heredoc or -f file, not psql -c |
| "table has no REPLICA IDENTITY" | Add PK or `ALTER TABLE ... REPLICA IDENTITY FULL` |
| Replication slot grows without progress | Check `pg_stat_subscription` for errors |
| Partitioned table data missing on target | Use `publish_via_partition_root = true` on publication |

**For detailed troubleshooting, see `references/subscription-management.md`**

## Output

- Replication configured and running
- Initial data sync completed
- Ongoing replication with minimal lag
- Cutover executed successfully

## Stopping Points

- ✋ Before creating publication on source
- ✋ Before creating Snowflake Postgres instance (billable)
- ✋ Before creating subscription
- ✋ Before cutover (point of no return)
- ✋ Before dropping subscription
