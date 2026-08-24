# Migration Lessons Learned

Real-world migration issues and solutions captured from actual PostgreSQL to Snowflake Postgres migrations.

## Network Configuration Issues

### Issue: Subscription Cannot Connect to Publisher

**Symptom:** `CREATE SUBSCRIPTION` hangs or fails with connection timeout.

**Root Cause:** Snowflake Postgres egress network rules were not configured or used wrong parameters.

**Solution:**

1. Resolve source hostname to IP: `dig +short <hostname>`
2. Create network rule with correct parameters:

```sql
-- CRITICAL: Must use TYPE = IPV4 and MODE = POSTGRES_EGRESS
CREATE OR REPLACE NETWORK RULE <db>.<schema>.migration_egress
    TYPE = IPV4                    -- NOT HOST_PORT
    VALUE_LIST = ('<ip>/32')       -- NOT hostname
    MODE = POSTGRES_EGRESS         -- NOT EGRESS
    COMMENT = 'Migration egress to source';

-- Add to existing network policy
ALTER NETWORK POLICY <policy_name> SET
    ALLOWED_NETWORK_RULE_LIST = (
        <existing_rules>,
        <db>.<schema>.migration_egress
    );
```

**Key Learning:** Network configuration must happen BEFORE creating the subscription, not after failures.

---

## Schema Synchronization Issues

### Issue: Subscription Fails - Tables Don't Exist

**Symptom:** `ERROR: relation "schema.table" does not exist`

**Root Cause:** Schema DDL was not copied to target before creating subscription.

**Solution:** Always copy schema BEFORE creating subscription:

```bash
# Step 1: Dump schema with vendor filtering
pg_dump --schema=$SCHEMA --schema-only --no-owner --no-acl 2>/dev/null \
  | grep -v '\\restrict\|\\unrestrict' \
  | grep -v 'rds\.' \
  | grep -v 'azure\.' \
  > schema.sql

# Step 2: Create schema on target
psql --no-psqlrc -c "CREATE SCHEMA IF NOT EXISTS $SCHEMA;"

# Step 3: Apply DDL
psql --no-psqlrc -f schema.sql

# Step 4: THEN create subscription
```

**Key Learning:** The subscription expects tables to already exist on the target.

---

## Vendor-Specific Command Issues

### Issue: Crunchy Bridge pg_dump Contains Unrecognized Commands

**Symptom:** `\restrict` and `\unrestrict` commands not recognized

**Root Cause:** Crunchy Bridge adds proprietary psql commands to pg_dump output.

**Solution:** Filter the output:

```bash
pg_dump ... | grep -v '\\restrict\|\\unrestrict' | psql --no-psqlrc
```

### Known Vendor Patterns to Filter

| Vendor | Pattern | Filter Command |
|--------|---------|----------------|
| Crunchy Bridge | `\restrict`, `\unrestrict` | `grep -v '\\restrict\|\\unrestrict'` |
| AWS RDS | `rds.*` functions | `grep -v 'rds\.'` |
| AWS RDS | `-- Dumped by.*rds` | `grep -v '^-- Dumped by.*rds'` |
| Azure | `azure.*` functions | `grep -v 'azure\.'` |
| Azure | `pgtle.*` | `grep -v 'pgtle\.'` |

---

## Transaction Block Issues

### Issue: CREATE SUBSCRIPTION Cannot Run Inside Transaction Block

**Symptom:** `ERROR: CREATE SUBSCRIPTION ... WITH (create_slot = true) cannot run inside a transaction block`

**Root Cause:** Using `psql -c "CREATE SUBSCRIPTION..."` runs in implicit transaction mode.

**Solution:** Use heredoc or file:

```bash
# WRONG
psql -c "CREATE SUBSCRIPTION my_sub CONNECTION '...' PUBLICATION my_pub WITH (create_slot = true);"

# RIGHT - heredoc
psql --no-psqlrc <<EOF
CREATE SUBSCRIPTION my_sub
CONNECTION '...'
PUBLICATION my_pub
WITH (copy_data = true, create_slot = true);
EOF

# RIGHT - file
echo "CREATE SUBSCRIPTION ..." > /tmp/sub.sql
psql --no-psqlrc -f /tmp/sub.sql
```

---

## Database Creation Issues

### Issue: Target Database Doesn't Exist

**Symptom:** `FATAL: database "mydb" does not exist`

**Root Cause:** Trying to connect to a database that hasn't been created yet.

**Solution:** Connect to `postgres` database first, then create:

```bash
PGDATABASE=postgres psql --no-psqlrc -c "CREATE DATABASE mydb;"
```

---

## Sequence Synchronization Issues

### Issue: Sequences Not Synced After Cutover

**Root Cause:** Logical replication does NOT replicate sequence values.

**Solution:** Auto-detect and sync all sequences as the FINAL step:

```sql
-- Detect all sequences
SELECT sequence_schema || '.' || sequence_name
FROM information_schema.sequences
WHERE sequence_schema NOT IN ('pg_catalog', 'information_schema');

-- Generate setval commands with buffer
SELECT 'SELECT setval(''' || n.nspname || '.' || c.relname || ''', ' || 
       (COALESCE(pg_sequence_last_value(c.oid), 1) + 1000) || ');'
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'S'
AND n.nspname NOT IN ('pg_catalog', 'information_schema');
```

---

## Workflow Order

Based on real migrations, the correct order is:

1. **Network Configuration** - Configure egress rules FIRST
2. **Test Connectivity** - Verify target can reach source
3. **Create Publication** - On source
4. **Copy Schema** - pg_dump with vendor filtering, apply to target
5. **Create Subscription** - Using heredoc, not -c flag
6. **Monitor Sync** - Wait for all tables to reach 'ready'
7. **Validate** - Row counts, data verification
8. **Cutover** - Stop writes, wait for zero lag
9. **Sync Sequences** - FINAL step after cutover

---

## pg_dump Parallel Format Issue

### Issue: Parallel Dump With Custom Format Fails

**Symptom:** `pg_dump: error: parallel backup only supported by the directory format`

**Root Cause:** The `-j` (parallel jobs) flag requires `-Fd` (directory format), not `-Fc` (custom format).

**Solution:** Use directory format for parallel, or drop `-j` for single-file custom format:

```bash
# RIGHT — parallel with directory format:
pg_dump -Fd -j 4 -f backup_dir/

# RIGHT — single-process custom format:
pg_dump -Fc -f backup.dump
```

Avoid combining custom format (`-Fc`) with any `-j` value. If you need
parallel dump workers, switch the archive format to `-Fd`.

**Key Learning:** For small databases, single-process `-Fc` is fine and produces a single portable file. Only use `-j` with `-Fd`.

---

## pg_dump Text Output Contains psql Meta-Commands (PG 17+)

### Issue: \restrict/\unrestrict in pg_dump --schema-only Output

**Symptom:** Running `pg_dump --schema-only` (text format) from a PG 17.x Docker container produces output containing `\restrict` and `\unrestrict` psql meta-commands. Executing this SQL via psycopg2, JDBC, or any non-psql client fails because these are psql-specific commands, not valid SQL.

**Root Cause:** PostgreSQL 17 introduced `\restrict` / `\unrestrict` as psql security meta-commands to prevent SQL injection in generated scripts. These are emitted in plain-text `pg_dump` output (not in `-Fc` custom format). They are harmless when applied via `psql` but break when applied via any other SQL client.

**Solution:**

1. **Preferred:** Use custom format (`-Fc`) instead of text format — `pg_restore` handles this properly:
```bash
pg_dump -Fc --schema-only -f schema.dump ...
pg_restore --no-owner --no-privileges -d target_db schema.dump
```

2. **If text format is needed:** Filter out the meta-commands before applying:
```bash
pg_dump --schema-only ... | grep -v '^\\\(restrict\|unrestrict\)' > schema_clean.sql
psql --no-psqlrc -f schema_clean.sql  # or apply via any client
```

3. **Using filter_vendor_dump.py** (already handles this):
```bash
pg_dump --schema-only ... | python ./scripts/filter_vendor_dump.py > schema_clean.sql
```

**Key Learning:** Always use `-Fc` (custom format) for pg_dump output that will be applied via psycopg2 or JDBC. If text format is required, pipe through `filter_vendor_dump.py` to strip psql meta-commands. This affects PG 17+ and some managed providers (Crunchy Bridge) on earlier versions.

---

## Role Migration Issues

### Issue: ALTER ROLE Fails on Snowflake Postgres

**Symptom:** `pg_dumpall --globals-only` output applied to target — `CREATE ROLE` succeeds but `ALTER ROLE` fails with `permission denied to alter role`.

**Root Cause:** Snowflake Postgres restricts superuser-level role attribute changes. This is expected and non-critical — the role exists and can log in.

**Solution:** Filter `ALTER ROLE` lines from globals output before applying:

```bash
PGSERVICE=prod_source pg_dumpall --globals-only | grep -v '^ALTER ROLE' > globals_clean.sql
psql --no-psqlrc -f globals_clean.sql
```

**Key Learning:** This is a known Snowflake Postgres limitation, not a migration failure. The roles are functional without the ALTER ROLE attributes.

### Issue: SUPERUSER Privilege Not Available

**Symptom:** Roles with SUPERUSER on the source cannot be granted SUPERUSER on Snowflake Postgres.

**Root Cause:** Snowflake Postgres does not support the SUPERUSER privilege. The `filter_vendor_dump.py` script strips SUPERUSER from role definitions, but the resulting roles will have fewer privileges than on the source.

**Solution:**
1. Run `filter_vendor_dump.py` to strip SUPERUSER (and REPLICATION, BYPASSRLS) from role definitions
2. After migration, review what the SUPERUSER roles were used for on the source
3. Grant specific privileges as needed on the target:

```sql
-- Instead of SUPERUSER, grant specific capabilities:
GRANT CREATE ON DATABASE mydb TO admin_role;
GRANT ALL ON SCHEMA public TO admin_role;
-- etc.
```

**Key Learning:** Always flag SUPERUSER roles during assessment. Plan a privilege mapping before migration — document what each superuser role actually does and translate to specific grants on the target.

---

## Password Authentication Mismatch (MD5 vs SCRAM)

### Issue: Source Uses MD5, Target Uses SCRAM-SHA-256

**Symptom:** Logical replication subscription fails to connect, or migrated roles cannot authenticate against the target.

**Root Cause:** Source database uses `md5` password encryption while Snowflake Postgres uses `scram-sha-256`. MD5 hashes cannot be converted to SCRAM — they are different one-way hash algorithms.

**Solution:**

1. Check source password encryption:
```sql
SHOW password_encryption;  -- 'md5' or 'scram-sha-256'
```

2. If source is MD5, you have two options:

**Option A: Set passwords manually on target** (recommended for small role count):
```bash
# On TARGET: use psql's interactive password prompt so the password is not
# written to shell history, process args, or chat transcripts.
psql --no-psqlrc -h <target_host> -U <admin_user> -d postgres

# Then at the psql prompt:
\password myuser
```

**Option B: Upgrade source to SCRAM before migration** (if you control source):
```sql
-- On SOURCE: switch to SCRAM (requires PG 10+)
ALTER SYSTEM SET password_encryption = 'scram-sha-256';
SELECT pg_reload_conf();
```

```bash
# Then each user must change their password so PostgreSQL re-hashes it as SCRAM.
# Run this from a trusted shell and use the interactive prompt:
psql --no-psqlrc -h <source_host> -U <admin_user> -d <db_name>

# Then at the psql prompt:
\password myuser
```

3. For the replication subscription connection string, always use explicit password (not relying on pg_hba trust):
```sql
CREATE SUBSCRIPTION migration_sub
    CONNECTION 'host=<source> dbname=<db> user=<user> password=<password-from-secret-store>'
    PUBLICATION migration_pub;
```

Build that connection string on a trusted host from a saved profile, secret
manager, or generated SQL file. Never ask the user to paste a real password into
chat just to fill in the `password=` field.

**Key Learning:** Check `password_encryption` on both source and target during
assessment. Plan for manual password resets if source uses MD5, and use
interactive `\password` or another out-of-band secret workflow instead of
inline SQL password literals in chat.

---

## pg_dumpall Requires Explicit PGPASSWORD Prefix

### Issue: pg_dumpall Prompts for Password Despite Environment Variable

**Symptom:** Running `pg_dumpall --globals-only` prompts for a password and times out, even though `$SOURCE_PGPASSWORD` is set in the shell environment.

**Root Cause:** `pg_dumpall` (and `pg_dump`) only reads the `PGPASSWORD` environment variable, not custom variable names like `SOURCE_PGPASSWORD`. The variable must be named exactly `PGPASSWORD`.

**Solution:** Prefer a service profile. When using direct flags, always prefix
with `PGPASSWORD=` and include the maintenance database so `.pgpass` matches:

```bash
# WRONG — custom variable name is not read by pg tools:
export SOURCE_PGPASSWORD="mypass"
pg_dumpall --globals-only -h $SOURCE_PGHOST -U $SOURCE_PGUSER

# PREFERRED — service profile + ~/.pgpass:
PGSERVICE=prod_source pg_dumpall --globals-only > globals.sql

# RIGHT — explicit prefix + explicit maintenance database:
PGPASSWORD="$SOURCE_PGPASSWORD" pg_dumpall \
  --globals-only \
  -h $SOURCE_PGHOST -p ${SOURCE_PGPORT:-5432} -U $SOURCE_PGUSER \
  --database="$SOURCE_PGDATABASE" > globals.sql

# ALSO RIGHT — set PGPASSWORD directly:
export PGPASSWORD="$SOURCE_PGPASSWORD"
pg_dumpall --globals-only \
  -h $SOURCE_PGHOST -p ${SOURCE_PGPORT:-5432} -U $SOURCE_PGUSER \
  --database="$SOURCE_PGDATABASE" > globals.sql
```

**Key Learning:** Always use `PGPASSWORD=` prefix or export it before running
any `pg_dump`/`pg_dumpall`/`psql` commands, and give `pg_dumpall` the same
database identity your `.pgpass` entry expects.

---

## Stale Row Count Statistics After Bulk Load

### Issue: validate_migration.py Row Counts Are Wrong After pg_dump/pg_restore

**Symptom:** `validate_migration.py --mode quick` reports mismatches right after bulk loading data via `pg_restore` or `pg_dump`.

**Root Cause:** `pg_stat_user_tables.n_live_tup` is an estimated count updated by autovacuum/ANALYZE. After a bulk load, these statistics are stale until ANALYZE runs.

**Solution:** Run ANALYZE on the target before validation:

```bash
# On TARGET: analyze all tables to refresh statistics
psql --no-psqlrc -h $TARGET_PGHOST -d $TARGET_PGDATABASE -U $TARGET_PGUSER -c "ANALYZE;"

# Then run validation
python scripts/validate_migration.py --mode quick ...
```

For individual tables:
```sql
ANALYZE schema.table_name;
```

**Key Learning:** Always run `ANALYZE` on the target database after bulk data load and before running `quick` mode validation. Alternatively, use `--mode exact` which runs `SELECT count(*)` instead of relying on statistics.

---

## Multi-Database Extension Creation

### Issue: Extensions Must Be Created Per Database

**Symptom:** Extensions exist in one target database but `pg_restore` for a second database fails because extensions are missing.

**Root Cause:** PostgreSQL extensions are per-database objects. When migrating multiple databases, each target database needs its own `CREATE EXTENSION` commands.

**Solution:** Run `prepare_target.py` against each target database individually:

```bash
# For each database being migrated:
python scripts/prepare_target.py extensions \
    --host $SOURCE_PGHOST --dbname db1 --user $SOURCE_PGUSER \
    --target-host $TARGET_PGHOST --target-dbname db1 --target-user $TARGET_PGUSER

python scripts/prepare_target.py extensions \
    --host $SOURCE_PGHOST --dbname db2 --user $SOURCE_PGUSER \
    --target-host $TARGET_PGHOST --target-dbname db2 --target-user $TARGET_PGUSER
```

**Key Learning:** For multi-database migrations, run extension creation on each target database before running `pg_restore`.

---

## Time Estimates (Real World)

Based on a 7.5 GB database with 48.6M rows:

| Phase | Duration |
|-------|----------|
| Assessment | ~5 min |
| Network rule setup | ~5 min |
| Schema copy | ~1 min |
| Initial data sync | ~15-20 min |
| Validation | ~2 min |
| Cutover | ~2 min |
| **Total** | **~30 min** |

Sync rate: ~25-30 GB/hour for this migration.
