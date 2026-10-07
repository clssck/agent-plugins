# Restore Commands Reference

Detailed pg_restore commands, monitoring, and post-restore tasks.

## Step 5.5: Pre-Restore - Create Extensions (MANDATORY)

Extensions installed in `public` schema (uuid-ossp, postgis, hstore, vector, etc.) are NOT included in schema-filtered dumps (`-n` flag). You MUST create them on the target before restoring.

```bash
python scripts/prepare_target.py extensions \
    -H $SOURCE_PGHOST -d $SOURCE_PGDATABASE -U $SOURCE_PGUSER \
    --target-host $TARGET_PGHOST --target-dbname $TARGET_PGDATABASE --target-user $TARGET_PGUSER
```

If Python is not available:
```sql
-- On TARGET: Create each extension the source uses
-- Query source first: SELECT extname, nspname FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace WHERE extname != 'plpgsql';
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";
CREATE EXTENSION IF NOT EXISTS "hstore";
CREATE EXTENSION IF NOT EXISTS "vector";
```

## Step 5.6: Pre-Restore Safety Check (if re-running after failure)

If a previous restore attempt failed partway, you MUST check for existing data:

```bash
python scripts/prepare_target.py check-data \
    --target-host $TARGET_PGHOST --target-dbname $TARGET_PGDATABASE --target-user $TARGET_PGUSER \
    --schemas public,analytics

# If data exists, clean before re-restore:
python scripts/prepare_target.py clean-schemas \
    --target-host $TARGET_PGHOST --target-dbname $TARGET_PGDATABASE --target-user $TARGET_PGUSER \
    --schemas public,analytics --confirm
```

**WARNING**: Re-running pg_restore on a partially-restored target will silently duplicate data in tables without primary keys. Tables WITH PKs get harmless `already exists` errors but tables WITHOUT PKs will double their row counts.

## Step 6: Restore to Snowflake Postgres

### 6.0 PROMPT: Monitor Restore Progress

**Before starting restore, ASK the user with `ask_user_question`:**

```
Ready to start restoring to Snowflake Postgres. This is typically the longest step.

How would you like to monitor the restore progress?

1) Live dashboard - Monitor table counts and activity in real-time (recommended)
2) Background restore - Run in background, notify on completion or errors
3) Show progress commands - Display commands for me to run manually
4) Skip monitoring - Just run the restore
```

### 6.1 Create Database Structure First (Optional)

```bash
# Source environment and set up TARGET connection
source ~/.pg_migration_env
setup_connection "TARGET"

# Restore schema only to verify structure (uses PGHOST etc from env)
pg_restore --schema-only --no-owner -v source_backup.dump
```

### 6.2 Full Restore

```bash
# Source environment and set up TARGET connection
source ~/.pg_migration_env
setup_connection "TARGET"

# Parallel restore (much faster) - uses PGHOST, PGUSER etc from environment
pg_restore \
    -j 4 \                          # Parallel jobs
    --no-owner \                    # Skip ownership
    --no-privileges \               # Skip grants
    -v \                            # Verbose output
    source_backup.dump

# Or for SQL format
gunzip -c source_backup.sql.gz | psql --no-psqlrc
```

### 6.3 Monitor Restore Progress (During Restore)

**If user selected live monitoring, run in parallel with restore:**

```bash
# Use migration monitor script  
source ~/.pg_migration_env
python scripts/migration_monitor.py sync
```

**Or manual monitoring queries:**
```bash
# Set up TARGET connection
source ~/.pg_migration_env
setup_connection "TARGET"

# Check active restore operations
psql --no-psqlrc --quiet -c "
SELECT pid, state, query_start, 
       now() - query_start as duration,
       left(query, 50) as query
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY query_start;"

# Check table row counts growing
psql --no-psqlrc --quiet -c "
SELECT schemaname || '.' || relname AS table_name,
       n_live_tup AS row_count
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC
LIMIT 10;"
```

### 6.4 Handle Restore Errors

Common errors and solutions:

| Error | Solution |
|-------|----------|
| `role "xxx" does not exist` | Use `--no-owner` flag |
| `extension "xxx" not available` | Check Snowflake Postgres supported extensions |
| `permission denied` | Ensure using admin role |
| `out of disk space` | Increase STORAGE_SIZE_GB |

### 6.5 PROMPT: Restore Complete

**After restore completes, ASK the user with `ask_user_question`:**

```
The restore has completed. 

What would you like to do next?

1) Run post-restore tasks - Analyze tables, verify indexes, refresh materialized views
2) Run validation - Compare row counts and optionally run pgCompare
3) Proceed to cutover - Skip validation (not recommended for production)
4) Show summary - Display restore statistics before deciding
```

## Step 7: Post-Restore Tasks

### 7.1 Recreate Indexes (if not included)

```sql
-- Indexes should be included in dump, but verify:
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE schemaname NOT IN ('pg_catalog', 'information_schema');
```

### 7.2 Verify Sequences (sync in final step)

```sql
-- Sequences are included but verify:
SELECT n.nspname || '.' || c.relname AS sequence_name,
       pg_sequence_last_value(c.oid) AS current_value
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'S';
```

### 7.3 Analyze Tables

```sql
-- Update statistics for query planner
ANALYZE;

-- Or specific tables
ANALYZE public.large_table;
```

### 7.4 Recreate Materialized Views

```sql
-- Materialized views need manual refresh
REFRESH MATERIALIZED VIEW schema.matview_name;
```

## Step 10: Sync Sequences (FINAL STEP)

**⚠️ CRITICAL**: This MUST be the final step after cutover.

Even though pg_dump includes sequences, the values may be stale if any writes occurred during migration.

### 10.1 Generate Sequence Sync Script on Source

```sql
-- On SOURCE: Generate setval commands with buffer
SELECT 'SELECT setval(''' || n.nspname || '.' || c.relname || ''', ' || 
       (COALESCE(pg_sequence_last_value(c.oid), 1) + 1000)::text || ');'
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'S'
AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname;
```

Or use the provided script:
```bash
python scripts/cutover_tools.py sequences -o sequence_sync_commands.sql
```

### 10.2 Apply Sequence Values on Target

```bash
psql --no-psqlrc --quiet -h $TARGET_PGHOST -p ${TARGET_PGPORT:-5432} -U $TARGET_PGUSER -d $TARGET_PGDATABASE \
    -f sequence_sync_commands.sql
```

### 10.3 Verify Sequences

```sql
-- On SNOWFLAKE POSTGRES: Verify sequence values are ahead of max IDs
SELECT n.nspname || '.' || c.relname AS sequence_name,
       pg_sequence_last_value(c.oid) AS current_value
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'S'
AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1;
```

**⚠️ IMPORTANT**: The +1000 buffer ensures new inserts get unique IDs.
