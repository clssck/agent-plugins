---
name: dump-restore
description: "Offline PostgreSQL migration via pg_dump/pg_restore to Snowflake Postgres. Use for: pg_dump, pg_restore, dump and restore, offline migration, backup and restore, full database export, schema-only dump, COPY-based table migration. Requires a downtime window."
parent_skill: migrate
---

# pg_dump/pg_restore Migration

> **Windows users:** see [references/windows.md](../../references/windows.md) — install prereqs, credential file paths (`%APPDATA%\postgresql\` instead of `~/`), and command-flow notes differ on native Windows. WSL behaves as Linux.

## Table of Contents

- [When to Use](#when-to-use-this-method)
- [Prerequisites](#prerequisites)
- [Connection Variables](#connection-variables)
- [Step 0: Check Required Tools](#step-0-check-required-tools-mandatory)
- [Step 0.5: Verify Connections](#step-05-verify-connections-mandatory)
- [Migration Plan](#migration-plan-display)
- [Workflow Overview](#workflow)
- [Alternative: COPY](#alternative-copy-for-individual-tables)
- [Troubleshooting](#troubleshooting)

## When to Load

Main skill routes here for: "pg_dump", "dump and restore", "offline migration", "backup and restore"

> **Credentials:** Migration scripts use `--source-service` / `--target-service`; `pg_dump`/`pg_restore` read `~/.pgpass` natively when given `-h $HOST -U $USER` (no `-W`). Never use `--password` or `-W` in chat. See `migrate/SKILL.md` "Credentials" callout for details.

## Prerequisites

- Downtime window scheduled
- pg_dump/pg_restore tools available (version compatible with source)
- Sufficient disk space for dump files
- Snowflake Postgres instance created
- **Connection configured** (see main skill for environment variables or prompts)

## Step 0: Check Required Tools (MANDATORY)

**Before proceeding with any dump/restore commands, verify that pg_dump, pg_restore, and psql are installed:**

```bash
which pg_dump && pg_dump --version || echo "pg_dump NOT FOUND"
which pg_restore && pg_restore --version || echo "pg_restore NOT FOUND"
which psql && psql --version || echo "psql NOT FOUND"
```

**If any tool is missing**, ask the user:

```
question: "pg_dump/pg_restore/psql was not found on this system. These tools are required for dump/restore migration. Would you like to install them now, or do you already have them installed elsewhere?"
header: "PG Tools"
options:
  - label: "Install now"
    description: "Install PostgreSQL client tools (brew install libpq / apt install postgresql-client)"
  - label: "Already installed elsewhere"
    description: "I have them at a different path — I'll provide the location"
  - label: "Skip — use a different method"
    description: "Switch to a migration method that doesn't require local PG tools"
```

**If Install now:**
```bash
# macOS
brew install libpq && brew link --force libpq

# Ubuntu/Debian
sudo apt-get install -y postgresql-client

# Amazon Linux / RHEL
sudo yum install -y postgresql
```

**If Skip:** Route back to main SKILL.md to select a different migration method (logical replication or postgres_fdw do not require local PG tools).

## Connection Variables

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

**Passwords**: Use `~/.pgpass` file or set in environment file (see main skill).

## When to Use This Method

| Scenario | Recommended |
|----------|-------------|
| Development/staging environments | ✅ Yes |
| Database < 50 GB | ✅ Yes |
| Downtime acceptable | ✅ Yes |
| Tables without PKs (can't use logical rep) | ✅ Yes |
| Database > 500 GB | ⚠️ Consider logical rep |
| Zero downtime required | ❌ Use logical rep |

## Step 0.5: Verify Connections (MANDATORY)

**⚠️ ALWAYS run these checks before starting any migration work.**

```bash
source ~/.pg_migration_env
```

### 0.5.1 Verify Source Connection

```bash
setup_connection "SOURCE"

psql --no-psqlrc --quiet <<'EOF'
SELECT 'SOURCE' AS connection, version() AS pg_version,
       current_database() AS database, current_user AS connected_user,
       pg_size_pretty(pg_database_size(current_database())) AS db_size;

SELECT COUNT(*) AS table_count FROM information_schema.tables 
WHERE table_schema NOT IN ('pg_catalog', 'information_schema');
EOF
```

### 0.5.2 Verify Target Connection

```bash
setup_connection "TARGET"

psql --no-psqlrc --quiet <<'EOF'
SELECT 'TARGET' AS connection, version() AS pg_version,
       current_database() AS database, current_user AS connected_user;

CREATE TABLE IF NOT EXISTS _migration_conn_test (id int);
DROP TABLE IF EXISTS _migration_conn_test;
SELECT 'Target write access verified' AS status;
EOF
```

### 0.5.3 Verify pg_dump/pg_restore Version Compatibility

```bash
echo "pg_dump version:" && pg_dump --version
echo "pg_restore version:" && pg_restore --version
# pg_dump/pg_restore version should be >= source PostgreSQL version
```

### 0.5.4 Verify Disk Space

```bash
source ~/.pg_migration_env
setup_connection "SOURCE"

DB_SIZE_PRETTY=$(psql --no-psqlrc --quiet -t -A -c "SELECT pg_size_pretty(pg_database_size(current_database()));")
AVAILABLE_PRETTY=$(df -h . | tail -1 | awk '{print $4}')

echo "Source database size: $DB_SIZE_PRETTY"
echo "Estimated dump size (-Fc): ~30% of source"
echo "Available disk space: $AVAILABLE_PRETTY"
```

## Migration Plan Display

```
╔═══════════════════════════════════════════════════════════════════════════════════╗
║         PG_DUMP/PG_RESTORE MIGRATION PLAN                                         ║
╠═══════════════════════════════════════════════════════════════════════════════════╣
│  STEP 0.5: Preflight Check - Verify target schemas are clean              ⚠ SAFETY │
│  STEP 1: Create Snowflake Postgres Instance (if needed)                           │
│  STEP 2: Migrate Roles (if opted) - pg_dumpall --globals-only                     │
│  STEP 3: Dump Source Database                                              ⏱ LONG │
│  STEP 4: Transfer Dump File                                                ⏱ LONG │
│  STEP 4.5: Pre-Restore: Create Extensions on Target                       ⚠ CRITICAL│
│  STEP 5: Restore to Snowflake Postgres                                     ⏱ LONG │
│  STEP 6: Post-Restore Tasks (indexes, constraints, ANALYZE)                       │
│  STEP 7: Validate & Cutover                                                ⚠ FINAL│
╚═══════════════════════════════════════════════════════════════════════════════════╝

Time Estimates (100 GB database):
  • Dump:     ~10 hours
  • Transfer: ~2-4 hours (compressed)
  • Restore:  ~7-20 hours
  • TOTAL:    ~20-35 hours
```

## Final Confirmation

**⚠️ MANDATORY: Ask for final confirmation before proceeding:**

```
Prerequisites confirmed:
  [ ] Source connection verified
  [ ] Target connection verified
  [ ] Target schemas preflight check passed
  [ ] pg_dump/pg_restore versions compatible
  [ ] Maintenance window scheduled
  [ ] Sufficient disk space for dump file

Proceed with migration? (yes/no):
```

## Workflow

**For detailed step-by-step instructions, load the appropriate reference:**

| Steps | Reference Document |
|-------|-------------------|
| Steps 3-4: Dump and Transfer | `references/dump-commands.md` |
| Steps 5-7, 10: Restore, Post-tasks, Sequences | `references/restore-commands.md` |

### Quick Reference: Key Commands

**Step 0.5: Preflight Check - Verify Target Schemas (MANDATORY)**

Before starting the migration, verify that the schemas you intend to migrate (except `public`) do not already exist on the target with objects. If they do, the migration will be aborted to prevent conflicts or data loss.

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/prepare_target.py preflight-check \
    --target-host $TARGET_PGHOST --target-dbname $TARGET_PGDATABASE --target-user $TARGET_PGUSER \
    --schemas public,analytics,reporting
```

If the check fails, you must either:
1. Clean the conflicting schemas: `prepare_target.py clean-schemas --schemas ... --confirm`
2. Use a different target database
3. Override with `--i-understand-the-risks` (acknowledges that target schemas may already contain objects that will be overwritten/merged)

**Step 1: Create Snowflake Postgres Instance**
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py \
    --create \
    --instance-name target_pg \
    --compute-pool <COMPUTE_FAMILY> \
    --storage 150
```

Use `pg_connect.py --create` instead of raw Snowflake SQL so the target service profile, password entry, and CA handling are saved automatically for later migration steps.

**Step 2: Migrate Roles (if opted)**
```bash
# Preferred, chat-safe path: service profile carries host/port/db/user and ~/.pgpass
# supplies the password.
PGSERVICE=prod_source pg_dumpall --globals-only --no-role-passwords -f globals.sql

# Trusted-shell fallback: include port + maintenance database so libpq tools and
# .pgpass match the same connection identity you used elsewhere in the runbook.
PGPASSWORD="$SOURCE_PGPASSWORD" pg_dumpall \
    -h $SOURCE_PGHOST -p ${SOURCE_PGPORT:-5432} -U $SOURCE_PGUSER \
    --database="$SOURCE_PGDATABASE" \
    --globals-only --no-role-passwords -f globals.sql
# IMPORTANT: pg_dumpall does NOT read $SOURCE_PGPASSWORD — must use PGPASSWORD=
# prefix (or set PGPASSWORD in the shell first).
# Filter unsupported attributes (SUPERUSER, REPLICATION, etc.), then apply to target
python <SKILL_DIR>/migrate/scripts/filter_vendor_dump.py globals.sql > globals_clean.sql
```

**⚠️ SUPERUSER roles:** SUPERUSER privilege is not available in Snowflake Postgres. The filter script strips SUPERUSER from CREATE/ALTER ROLE statements. Roles will be created without SUPERUSER — review and assign appropriate permissions on the target after migration.

**Step 3: Full Database Dump**
```bash
pg_dump -h $SOURCE_PGHOST -U $SOURCE_PGUSER -d $SOURCE_PGDATABASE \
    -Fc --no-owner --no-privileges -f source_backup.dump

# For a parallel dump, switch to directory format:
# pg_dump -h $SOURCE_PGHOST -U $SOURCE_PGUSER -d $SOURCE_PGDATABASE \
#     -Fd -j 4 --no-owner --no-privileges -f source_backup_dir
```

**⚠️ PG 17+ text format warning:** If using text-format `pg_dump --schema-only` (without `-Fc`), the output may contain `\restrict`/`\unrestrict` psql meta-commands that fail when applied via psycopg2, JDBC, or any non-psql client. Always use `-Fc` (custom format) or pipe text output through `python <SKILL_DIR>/migrate/scripts/filter_vendor_dump.py` to strip these commands.

**Step 4.5: Pre-Restore - Create Extensions on Target (MANDATORY)**

Extensions (uuid-ossp, postgis, hstore, vector, etc.) are often installed in `public` schema on the source. If your dump uses `-n` (schema filter), the extension definitions won't be in the dump and the restore will fail with `function does not exist` or `type does not exist` errors.

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/prepare_target.py extensions \
    -H $SOURCE_PGHOST -d $SOURCE_PGDATABASE -U $SOURCE_PGUSER \
    --target-host $TARGET_PGHOST --target-dbname $TARGET_PGDATABASE --target-user $TARGET_PGUSER
```

**Step 4.6: Pre-Restore Safety Check (if re-running after a failed restore)**

If a previous restore failed partway through, check for existing data before re-restoring. Tables without primary keys will silently get duplicate rows.

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/prepare_target.py check-data \
    --target-host $TARGET_PGHOST --target-dbname $TARGET_PGDATABASE --target-user $TARGET_PGUSER \
    --schemas public,analytics,reporting

# If data exists, clean schemas first:
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/prepare_target.py clean-schemas \
    --target-host $TARGET_PGHOST --target-dbname $TARGET_PGDATABASE --target-user $TARGET_PGUSER \
    --schemas analytics,reporting --confirm
```

**Step 5: Parallel Restore**
```bash
setup_connection "TARGET"
pg_restore -j 4 --no-owner --no-privileges -v source_backup.dump
```

**Step 6: Post-Restore**
```sql
ANALYZE;  -- Update statistics
REFRESH MATERIALIZED VIEW schema.matview_name;  -- If any
```

**Step 7: Sync Sequences**

After `pg_restore` finishes, sequences on the target reflect the values they
had at the *start* of the dump. Any sequence advances during the dump window
need to be replayed before applications point at the target — otherwise the
next INSERT may collide with an existing key.

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/cutover_tools.py sequences \
    --source-service prod_source --target-service sf_target \
    --execute
```

`cutover_tools.py sequences --execute` reads each sequence's current
`pg_sequence_last_value` from the source and applies `setval('sch.seq', N + buffer)`
on the target (default buffer: 1000). For dump-and-restore migrations this is
the equivalent of the cutover-time sync step from the logical-replication path.

**Step 8: Validation**
```sql
SELECT schemaname || '.' || relname AS table_name, n_live_tup AS row_count
FROM pg_stat_user_tables ORDER BY schemaname, relname;
```

Or use the structured comparison:

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/validate_migration.py \
    --source-service prod_source --target-service sf_target --mode full
```

**Step 9: Cutover**

Once validation passes, hand off to the dedicated cutover sub-skill: load `../cutover/SKILL.md` for the application-write stop, sequence-sync confirmation, target-flip, and rollback-window guidance. Do not put any Snowflake-side `ALTER` here — there's no instance-level cutover knob to flip; the cutover is an application-side switch from source to target.

## Alternative: COPY for Individual Tables

For specific tables or data refresh:

```bash
# Export from source
psql --no-psqlrc -h $SOURCE_PGHOST -U $SOURCE_PGUSER -d $SOURCE_PGDATABASE -c \
    "\COPY public.table_name TO '/tmp/table_data.csv' WITH CSV HEADER"

# Import to Snowflake Postgres
psql --no-psqlrc -h $TARGET_PGHOST -U $TARGET_PGUSER -d $TARGET_PGDATABASE -c \
    "\COPY public.table_name FROM '/tmp/table_data.csv' WITH CSV HEADER"
```

## Troubleshooting

| Error | Solution |
|-------|----------|
| `function public.uuid_generate_v4() does not exist` | Run `prepare_target.py extensions` BEFORE restore. Extensions in `public` schema are not included in schema-filtered dumps (`-n` flag). |
| `type "public.geometry" does not exist` | Same as above - PostGIS extension must be created on target first. |
| `role "xxx" does not exist` | Use `--no-owner` flag |
| `extension "xxx" not available` | Check Snowflake Postgres supported extensions |
| `permission denied` | Ensure using admin role |
| `out of disk space` | Increase STORAGE_SIZE_GB |
| Restore hanging on specific table | Check for blocking queries; may be waiting for large index |
| Out of memory during restore | Reduce `-j` parallelism |
| pg_restore version mismatch | Use pg_restore version >= pg_dump version |

### Failed Restore Recovery

If a restore fails partway through and you need to re-run it:

1. **DO NOT** simply re-run `pg_restore` on top of the partial restore
2. Tables WITH primary keys will get harmless `already exists` errors
3. Tables WITHOUT primary keys will **silently duplicate all data**
4. Run `prepare_target.py check-data` to see which tables have data
5. Run `prepare_target.py clean-schemas` to DROP and recreate affected schemas before re-restoring

### Data Duplication Recovery

If you already have duplicate data from a re-restore on tables without PKs:
- **DO NOT** attempt ctid-based deduplication - it is error-prone without knowledge of the natural key and can cause data loss
- **RECOMMENDED**: Truncate affected tables and re-import via `\COPY` from the source:

```bash
# For each affected table:
psql --no-psqlrc -h $SOURCE_PGHOST -U $SOURCE_PGUSER -d $SOURCE_PGDATABASE -c \
    "\COPY schema.table_name TO '/tmp/table_data.csv' WITH CSV HEADER"

psql --no-psqlrc -h $TARGET_PGHOST -U $TARGET_PGUSER -d $TARGET_PGDATABASE -c \
    "TRUNCATE schema.table_name"

psql --no-psqlrc -h $TARGET_PGHOST -U $TARGET_PGUSER -d $TARGET_PGDATABASE -c \
    "\COPY schema.table_name FROM '/tmp/table_data.csv' WITH CSV HEADER"
```

## Output

- Database fully migrated to Snowflake Postgres
- All tables, indexes, constraints restored
- Sequences at correct values
- Application connected and functional

## Stopping Points

- ✋ Before creating Snowflake Postgres instance (billable)
- ✋ Before starting dump (may impact source performance)
- ✋ Before restore (point of commitment)
- ✋ Before cutover (application switch)
