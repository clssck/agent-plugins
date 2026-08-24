# Checksum Validation

Compare MD5 checksums of table data for integrity verification.

## Step 1: Generate Table Checksums

```bash
source ~/.pg_migration_env
# Connection details are set via environment variables (SOURCE_PGHOST, etc.)

get_table_checksum() {
    local TABLE=$1
    psql --no-psqlrc --quiet -t -A -c "
    SELECT md5(string_agg(row_hash, ''))
    FROM (
        SELECT md5(CAST(t.* AS TEXT)) as row_hash
        FROM $TABLE t
        ORDER BY 1
    ) sub;"
}

echo "Calculating checksums..."

setup_connection "SOURCE"
echo "SOURCE: $(get_table_checksum 'public.users')"

setup_connection "TARGET"  
echo "TARGET: $(get_table_checksum 'public.users')"
```

## Step 2: Compare Critical Tables

```bash
source ~/.pg_migration_env
# Connection details are set via environment variables (SOURCE_PGHOST, etc.)

TABLES="public.users public.orders public.products"

for TABLE in $TABLES; do
    setup_connection "SOURCE"
    SOURCE_HASH=$(psql --no-psqlrc --quiet -t -A -c "SELECT md5(string_agg(md5(CAST(t.* AS TEXT)), '')) FROM $TABLE t;")
    
    setup_connection "TARGET"
    TARGET_HASH=$(psql --no-psqlrc --quiet -t -A -c "SELECT md5(string_agg(md5(CAST(t.* AS TEXT)), '')) FROM $TABLE t;")
    
    if [ "$SOURCE_HASH" = "$TARGET_HASH" ]; then
        echo "Pass: $TABLE checksum match ($SOURCE_HASH)"
    else
        echo "Fail: $TABLE MISMATCH (source: $SOURCE_HASH, target: $TARGET_HASH)"
    fi
done
```
