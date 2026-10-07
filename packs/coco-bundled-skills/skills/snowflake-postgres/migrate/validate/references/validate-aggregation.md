# Aggregation Validation

Compare aggregate values (SUM, COUNT, AVG, MIN, MAX) on numeric columns.

## Quick Aggregate Comparison

```bash
source ~/.pg_migration_env
# Connection details are set via environment variables (SOURCE_PGHOST, etc.)

compare_aggregate() {
    local TABLE=$1
    local COLUMN=$2
    
    setup_connection "SOURCE"
    SOURCE_SUM=$(psql --no-psqlrc --quiet -t -A -c "SELECT SUM($COLUMN)::numeric FROM $TABLE;")
    SOURCE_COUNT=$(psql --no-psqlrc --quiet -t -A -c "SELECT COUNT(*) FROM $TABLE;")
    
    setup_connection "TARGET"
    TARGET_SUM=$(psql --no-psqlrc --quiet -t -A -c "SELECT SUM($COLUMN)::numeric FROM $TABLE;")
    TARGET_COUNT=$(psql --no-psqlrc --quiet -t -A -c "SELECT COUNT(*) FROM $TABLE;")
    
    echo "$TABLE.$COLUMN:"
    echo "  COUNT: Source=$SOURCE_COUNT, Target=$TARGET_COUNT $([ "$SOURCE_COUNT" = "$TARGET_COUNT" ] && echo 'Pass' || echo 'Fail')"
    echo "  SUM:   Source=$SOURCE_SUM, Target=$TARGET_SUM $([ "$SOURCE_SUM" = "$TARGET_SUM" ] && echo 'Pass' || echo 'Fail')"
}

compare_aggregate "public.orders" "total_amount"
compare_aggregate "public.transactions" "amount"
```
