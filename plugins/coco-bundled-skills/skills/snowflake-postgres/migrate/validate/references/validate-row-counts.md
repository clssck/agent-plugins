# Row Count Validation

## Step 1: Get Source Row Counts

```bash
source ~/.pg_migration_env
# Connection details are set via environment variables (SOURCE_PGHOST, etc.)
setup_connection "SOURCE"

psql --no-psqlrc --quiet -t -A -F',' <<'EOF'
SELECT 
    schemaname || '.' || relname AS table_name,
    n_live_tup AS row_count
FROM pg_stat_user_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, relname;
EOF
```

## Step 2: Get Target Row Counts

```bash
setup_connection "TARGET"

psql --no-psqlrc --quiet -t -A -F',' <<'EOF'
SELECT 
    schemaname || '.' || relname AS table_name,
    n_live_tup AS row_count
FROM pg_stat_user_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, relname;
EOF
```

## Step 3: Compare and Report

Display comparison table:

| Table | Source Rows | Target Rows | Match |
|-------|-------------|-------------|-------|
| public.users | 1,234,567 | 1,234,567 | Pass |
| public.orders | 5,678,901 | 5,678,901 | Pass |

If mismatches found:
- List tables with different row counts
- Suggest checking replication lag or restore errors
