# pgCompare Validation

Full row-by-row data comparison with diff detection.

## Prerequisites

- Java 21+ ([Download from Adoptium](https://adoptium.net/))
- Maven 3.9+ (`brew install maven` on macOS)

## Installation

```bash
PGCOMPARE_DIR="${HOME}/.pgcompare"

if [ ! -f "$PGCOMPARE_DIR/target/pgcompare.jar" ]; then
    mkdir -p "$PGCOMPARE_DIR"
    git clone --depth 1 https://github.com/CrunchyData/pgCompare.git "$PGCOMPARE_DIR"
    cd "$PGCOMPARE_DIR"
    mvn clean install -DskipTests
fi

PGCOMPARE_JAR="$PGCOMPARE_DIR/target/pgcompare.jar"
```

## Configuration

```bash
source ~/.pg_migration_env

PGCOMPARE_WORKDIR="${PWD}/pgcompare_validation_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$PGCOMPARE_WORKDIR"

cat > "$PGCOMPARE_WORKDIR/pgcompare.properties" <<EOF
# Repository (using target database)
repo-host=$TARGET_PGHOST
repo-port=${TARGET_PGPORT:-5432}
repo-dbname=$TARGET_PGDATABASE
repo-user=$TARGET_PGUSER
repo-password=$TARGET_PGPASSWORD
repo-schema=pgcompare_repo

# Source: Original PostgreSQL
source-type=postgres
source-host=$SOURCE_PGHOST
source-port=${SOURCE_PGPORT:-5432}
source-dbname=$SOURCE_PGDATABASE
source-user=$SOURCE_PGUSER
source-password=$SOURCE_PGPASSWORD
source-schema=public

# Target: Snowflake Postgres
target-type=postgres
target-host=$TARGET_PGHOST
target-port=${TARGET_PGPORT:-5432}
target-dbname=$TARGET_PGDATABASE
target-user=$TARGET_PGUSER
target-password=$TARGET_PGPASSWORD
target-schema=public

batch-fetch-size=2000
batch-commit-size=2000
loader-threads=4
EOF

chmod 600 "$PGCOMPARE_WORKDIR/pgcompare.properties"
```

## Execution

```bash
cd "$PGCOMPARE_WORKDIR"

# Create repository schema
setup_connection "TARGET"
psql --no-psqlrc --quiet -c "CREATE SCHEMA IF NOT EXISTS pgcompare_repo;"

# Initialize and discover
java -jar "$PGCOMPARE_JAR" init --config pgcompare.properties
java -jar "$PGCOMPARE_JAR" discover --config pgcompare.properties

# Run comparison
java -jar "$PGCOMPARE_JAR" compare --batch 0 --config pgcompare.properties
```

## View Results

```sql
SELECT 
    table_name,
    status,
    equal_cnt AS matching_rows,
    not_equal_cnt AS mismatched_rows,
    missing_source_cnt AS missing_in_source,
    missing_target_cnt AS missing_in_target,
    CASE 
        WHEN not_equal_cnt = 0 AND missing_source_cnt = 0 AND missing_target_cnt = 0 
        THEN 'PASS' ELSE 'FAIL'
    END AS result
FROM pgcompare_repo.dc_result
WHERE rid = (SELECT max(rid) FROM pgcompare_repo.dc_result)
ORDER BY table_name;
```
