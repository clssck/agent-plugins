# Subscription Management Reference

This document covers publication and subscription setup for logical replication.

## Step 1: Configure Source Database

### 1.1 Verify WAL Level

```sql
-- On SOURCE: Check wal_level
SHOW wal_level;
-- Must return 'logical'

-- If not logical, requires restart:
ALTER SYSTEM SET wal_level = 'logical';
ALTER SYSTEM SET max_replication_slots = 10;
ALTER SYSTEM SET max_wal_senders = 10;
-- Then restart PostgreSQL
```

### 1.2 Create Migration User with Replication Privileges

```sql
-- On SOURCE: Create replication user (set password via \password or ~/.pgpass)
CREATE ROLE migration_user WITH LOGIN REPLICATION;
-- Set password securely (not in SQL):
-- Option 1: \password migration_user (interactive)
-- Option 2: Add to ~/.pgpass on source

-- Grant access to schemas being migrated
GRANT USAGE ON SCHEMA public TO migration_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO migration_user;
```

### 1.3 Create Publication

```sql
-- On SOURCE: Create publication for all tables
CREATE PUBLICATION snowflake_migration FOR ALL TABLES;

-- Or for specific schemas:
CREATE PUBLICATION snowflake_migration FOR TABLES IN SCHEMA public, app;

-- Or for specific tables:
CREATE PUBLICATION snowflake_migration FOR TABLE 
    public.users, 
    public.orders, 
    public.products;
```

**Verify publication:**
```sql
SELECT * FROM pg_publication;
SELECT * FROM pg_publication_tables WHERE pubname = 'snowflake_migration';
```

**⚠️ STOP**: Confirm publication created successfully before proceeding.

## Step 2: Migrate Users, Roles, and Permissions (If Opted)

**⚠️ NOTE**: This step is only required if the user chose to migrate roles during scope check.

**Skip this step if:**
- User opted not to migrate roles
- Roles already exist on target
- Roles will be managed separately (e.g., via IaC)

**Execute this step if:** User confirmed roles should be migrated.

### 2.0 Export Global Objects from Source

```bash
# Preferred: service profile + ~/.pgpass
PGSERVICE=prod_source pg_dumpall --globals-only \
    --no-role-passwords \
    -f globals.sql

# Trusted-shell fallback: include the maintenance database so .pgpass matches
pg_dumpall -h source_host -p 5432 -U postgres --database=source_db --globals-only \
    --no-role-passwords \
    -f globals.sql
```

**What `--globals-only` includes:**
- All roles and users (CREATE ROLE statements)
- Role attributes (LOGIN, CREATEDB, etc.)
- Role memberships (GRANT role TO member)
- Tablespace definitions (if any)

**What it does NOT include:**
- Passwords (use `--no-role-passwords` for security)
- Database-level grants (handled separately)

### 2.0.1 Transform and Apply Globals

```bash
# Remove unsupported attributes and managed-platform roles (RDS, Azure, GCP,
# Neon, Crunchy/PG17 meta-commands) in one pass.
python <SKILL_DIR>/migrate/scripts/filter_vendor_dump.py globals.sql > globals_clean.sql

# Apply to Snowflake Postgres
psql --no-psqlrc --quiet -h snowflake_pg_host -U snowflake_admin -d postgres -f globals_clean.sql
```

### 2.0.2 Set Passwords for Migrated Roles

```bash
# On SNOWFLAKE POSTGRES: set passwords interactively so they do not appear in
# shell history, process args, or chat transcripts.
psql --no-psqlrc --quiet -h snowflake_pg_host -U snowflake_admin -d postgres

# Then at the psql prompt:
\password app_user
\password readonly_user
```

If you need a non-interactive rotation flow, use your approved secrets manager
or another out-of-band admin workflow on a trusted host rather than typing real
passwords into SQL shown in chat.

**⚠️ STOP**: Verify all required roles exist on target before proceeding.

```sql
-- Verify roles on target
SELECT rolname, rolcanlogin FROM pg_roles WHERE rolname NOT LIKE 'pg_%';
```

## Step 3: Prepare Snowflake Postgres Target

### 3.1 Create Snowflake Postgres Instance (if not exists)

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py \
    --create \
    --instance-name snowflake_pg \
    --compute-pool <COMPUTE_FAMILY> \
    --storage 100
```

Use `pg_connect.py --create` instead of raw Snowflake SQL so the saved service profile, password entry, and CA handling are in place before the replication steps begin.

**⚠️ MANDATORY CHECKPOINT**: Instance creation is billable. Confirm before proceeding.

### 3.2 Create Target Database (if different from postgres)

**⚠️ If migrating to a database OTHER than `postgres`**, create it first:

```bash
# Connect to postgres database to create the target database
setup_connection "TARGET"
PGDATABASE=postgres psql --no-psqlrc --quiet -c "CREATE DATABASE $TARGET_PGDATABASE;"
```

### 3.3 Create Schema Structure on Target (BEFORE Subscription)

**⚠️ CRITICAL**: Schema DDL MUST be applied to target BEFORE creating the subscription.
The subscription will FAIL if target tables don't exist.

**Step 1: Dump schema from source with vendor filtering**

```bash
source ~/.pg_migration_env
setup_connection "SOURCE"

# Dump schema, filtering out vendor-specific commands
pg_dump --schema=$SCHEMA_NAME --schema-only --no-owner --no-acl 2>/dev/null \
  | grep -v '\\restrict\|\\unrestrict' \
  | grep -v '^-- Dumped by.*rds' \
  | grep -v 'rds\.' \
  | grep -v 'azure\.' \
  > /tmp/schema_dump.sql
```

**Known vendor-specific commands to filter:**
| Vendor | Commands/Patterns | Filter |
|--------|-------------------|--------|
| Crunchy Bridge | `\restrict`, `\unrestrict` | `grep -v '\\\\restrict\|\\\\unrestrict'` |
| AWS RDS | `rds.*` functions, `-- Dumped by.*rds` | `grep -v 'rds\\.'` |
| Azure | `azure.*` functions | `grep -v 'azure\\.'` |

**Step 2: Create schema and extensions on target**

```bash
setup_connection "TARGET"

# Create schema if it doesn't exist
psql --no-psqlrc --quiet -c "CREATE SCHEMA IF NOT EXISTS $SCHEMA_NAME;"

# Create required extensions (from assessment)
psql --no-psqlrc --quiet -c "CREATE EXTENSION IF NOT EXISTS btree_gist;"
# Add other extensions as needed
```

**Step 3: Apply schema DDL to target**

```bash
setup_connection "TARGET"
psql --no-psqlrc --quiet -f /tmp/schema_dump.sql
```

**⚠️ STOP**: Verify schema was applied successfully before proceeding.

```bash
setup_connection "TARGET"
psql --no-psqlrc --quiet -c "
  SELECT schemaname, tablename 
  FROM pg_tables 
  WHERE schemaname = '$SCHEMA_NAME' 
  ORDER BY tablename;
"
```

## Troubleshooting

**Error: "could not connect to publisher"**
- Check network egress rule uses `TYPE = IPV4` and `MODE = POSTGRES_EGRESS`
- Resolve source hostname to IP: `dig +short <hostname>`
- Verify network rule is added to the correct network policy
- Ensure source allows connections from Snowflake Postgres IP range

**Error: "relation does not exist" when creating subscription**
- Schema DDL must be copied to target BEFORE creating subscription
- Run `pg_dump --schema-only` and apply to target first
- See Step 3.3 for vendor-specific filtering

**Error: "CREATE SUBSCRIPTION cannot run inside a transaction block"**
- Do NOT use `psql -c "CREATE SUBSCRIPTION..."`
- Use heredoc format or `-f` file instead
- See `references/initial-sync.md` Step 4.1 for correct syntax

**Error: Vendor-specific commands in pg_dump (\\restrict, rds.*, azure.*)**
- Filter pg_dump output through grep to remove vendor extensions
- Crunchy: `grep -v '\\\\restrict\\|\\\\unrestrict'`
- RDS: `grep -v 'rds\\.'`
- Azure: `grep -v 'azure\\.'`

**Error: "database does not exist"**
- Create target database first: `CREATE DATABASE <name>;`
- Connect to `postgres` database to create other databases

**Error: "table has no REPLICA IDENTITY"**
```sql
-- On SOURCE: Add replica identity
ALTER TABLE schema.table REPLICA IDENTITY FULL;
-- Or add a primary key (preferred)
```

**Replication slot grows without progress**
- Check `pg_stat_subscription` for errors
- Verify target has sufficient resources
- Check for long-running transactions on target
