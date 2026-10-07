# Dump Commands Reference

Detailed pg_dump commands and monitoring for source database export.

## Step 4: Dump Source Database

### 4.1 Full Database Dump (Recommended)

```bash
# Schema + Data in custom format (parallel restore capable)
# Password from ~/.pgpass or PGPASSWORD environment variable
pg_dump -h $SOURCE_PGHOST -p ${SOURCE_PGPORT:-5432} -U $SOURCE_PGUSER -d $SOURCE_PGDATABASE \
    -Fc \                           # Custom format
    --no-owner \                    # Skip ownership
    --no-privileges \               # Skip grants
    -f source_backup.dump

# For a parallel dump, switch to directory format:
# pg_dump -h $SOURCE_PGHOST -p ${SOURCE_PGPORT:-5432} -U $SOURCE_PGUSER -d $SOURCE_PGDATABASE \
#     -Fd -j 4 --no-owner --no-privileges -f source_backup_dir

# Compress if using plain SQL format
pg_dump -h $SOURCE_PGHOST -p ${SOURCE_PGPORT:-5432} -U $SOURCE_PGUSER -d $SOURCE_PGDATABASE \
    --no-owner --no-privileges \
    | gzip > source_backup.sql.gz
```

### 4.2 Schema-Only Dump (For verification first)

```bash
pg_dump -h $SOURCE_PGHOST -p ${SOURCE_PGPORT:-5432} -U $SOURCE_PGUSER -d $SOURCE_PGDATABASE \
    --schema-only \
    --no-owner --no-privileges \
    -f schema_only.sql
```

### 4.3 Per-Table Dumps (For large databases)

```bash
# Dump specific tables for parallel restore
for table in users orders products; do
    pg_dump -h $SOURCE_PGHOST -p ${SOURCE_PGPORT:-5432} -U $SOURCE_PGUSER -d $SOURCE_PGDATABASE \
        -t public.$table \
        -Fc \
        -f ${table}.dump &
done
wait
```

**Monitor dump progress:**
```bash
# Use migration monitor script
python scripts/migration_monitor.py dashboard

# Or manually check dump file size growth
watch -n 10 'ls -lh *.dump'
```

### 4.4 PROMPT: Monitor Dump Progress

**After starting the dump, ASK the user with `ask_user_question`:**

```
The database dump has started. This may take a while for large databases.

How would you like to monitor the dump progress?

1) Live monitoring - Watch dump file size growth in real-time
2) Background agent watcher - Keep a background agent watching progress and notify me when complete
3) Show progress commands - Display commands for me to run manually
4) Skip monitoring - I'll check back later
```

**Based on selection:**

**Option 1 - Live Monitoring:**
```bash
source ~/.pg_migration_env
python scripts/migration_monitor.py dashboard
```

**Option 2 - Background Agent Watcher:**
- Monitor file size growth periodically
- Estimate completion based on source database size
- Notify user when dump completes
- Use this only for same-session observation; if the dump is likely to outlive the session, pause and resume later instead of depending on a long-lived watcher

**Option 3 - Show Commands:**
```bash
# Check dump progress
ls -lh source_backup.dump
# Estimate completion: compare current size to expected (source DB size)
```

## Step 5: Transfer Dump Files

### Option A: Direct Transfer (if network allows)
```bash
# SCP to intermediate server or local machine
scp source_backup.dump user@intermediate:/migration/
```

### Option B: Cloud Storage (for large files)
```bash
# Upload to S3/GCS/Azure Blob
aws s3 cp source_backup.dump s3://migration-bucket/

# Download to restore location
aws s3 cp s3://migration-bucket/source_backup.dump .
```

## Disk Space Requirements

| Format | Flag | Typical Size | Use Case |
|--------|------|--------------|----------|
| Custom | `-Fc` | 20-40% of DB | Recommended (parallel restore) |
| Directory | `-Fd` | 20-40% of DB | Large DBs (parallel dump+restore) |
| Plain SQL | (none) | ~100% of DB | Human-readable, single-threaded |
| Plain gzipped | `\| gzip` | 15-25% of DB | Space-constrained |
