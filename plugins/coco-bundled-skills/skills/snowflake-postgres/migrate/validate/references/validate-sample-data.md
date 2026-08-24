# Sample Data Validation

Compare the same deterministic sample rows between source and target to verify
data integrity.

## Step 1: Generate Sample Comparison for Key Tables

```bash
source ~/.pg_migration_env
# Connection details are set via environment variables (SOURCE_PGHOST, etc.)

compare_samples() {
    local TABLE=$1
    local KEY_COLUMN=$2
    local SAMPLE_SIZE=${3:-100}
    
    echo "Comparing $SAMPLE_SIZE rows from $TABLE using key $KEY_COLUMN..."
    
    setup_connection "SOURCE"
    psql --no-psqlrc --quiet -t -A <<EOF > /tmp/sample_keys.csv
SELECT $KEY_COLUMN::text
FROM $TABLE
ORDER BY md5($KEY_COLUMN::text)
LIMIT $SAMPLE_SIZE;
EOF

    setup_connection "SOURCE"
    psql --no-psqlrc --quiet <<EOF
CREATE TEMP TABLE _sample_keys (key_text text);
\copy _sample_keys FROM '/tmp/sample_keys.csv'
\copy (
    SELECT t.*
    FROM $TABLE t
    JOIN _sample_keys k ON t.$KEY_COLUMN::text = k.key_text
    ORDER BY t.$KEY_COLUMN
) TO '/tmp/source_sample.csv' WITH (FORMAT csv, HEADER true)
EOF
    
    setup_connection "TARGET"
    psql --no-psqlrc --quiet <<EOF
CREATE TEMP TABLE _sample_keys (key_text text);
\copy _sample_keys FROM '/tmp/sample_keys.csv'
\copy (
    SELECT t.*
    FROM $TABLE t
    JOIN _sample_keys k ON t.$KEY_COLUMN::text = k.key_text
    ORDER BY t.$KEY_COLUMN
) TO '/tmp/target_sample.csv' WITH (FORMAT csv, HEADER true)
EOF
    
    diff /tmp/source_sample.csv /tmp/target_sample.csv && echo "Pass: $TABLE samples match" || echo "Fail: $TABLE differences found"
}

compare_samples "public.users" "id" 100
compare_samples "public.orders" "id" 100
```

Use a stable unique key (primary key or another deterministic unique column) for
`KEY_COLUMN` so both sides compare the exact same row set.
