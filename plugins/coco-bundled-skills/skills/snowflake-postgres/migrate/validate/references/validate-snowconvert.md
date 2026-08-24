# SnowConvert (scai) Validation

SnowConvert AI (scai) provides schema analysis and compatibility checking.

## Prerequisites

- Python 3.8+
- pip package manager

## Installation

```bash
pip install scai
scai --version
```

## Automated Execution

### Step 1: Create Project Directory

```bash
SCAI_PROJECT="pg_migration_validation_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$SCAI_PROJECT"
cd "$SCAI_PROJECT"
```

### Step 2: Export Source Schema

```bash
source ~/.pg_migration_env
# Connection details are set via environment variables (SOURCE_PGHOST, etc.)
setup_connection "SOURCE"

pg_dump --schema-only --no-owner --no-privileges -f source_schema.sql
```

### Step 3: Initialize and Convert

```bash
scai init -n pg_validation -l PostgreSQL -i ./source_schema.sql
scai code convert
```

### Step 4: Export Target Schema

```bash
setup_connection "TARGET"
pg_dump --schema-only --no-owner --no-privileges -f target_schema.sql
```

### Step 5: Compare Results

```bash
echo "=== Schema Comparison ==="
echo "Source objects:"
grep -c "CREATE TABLE" source_schema.sql | xargs echo "  Tables:"
grep -c "CREATE INDEX" source_schema.sql | xargs echo "  Indexes:"
grep -c "CREATE FUNCTION" source_schema.sql | xargs echo "  Functions:"

echo "Target objects:"
grep -c "CREATE TABLE" target_schema.sql | xargs echo "  Tables:"
grep -c "CREATE INDEX" target_schema.sql | xargs echo "  Indexes:"
grep -c "CREATE FUNCTION" target_schema.sql | xargs echo "  Functions:"
```

## Key Metrics

| Metric | Description | Expected |
|--------|-------------|----------|
| Total Objects | Count of all database objects | Should match source |
| Converted Successfully | Objects with no issues | 100% or close |
| Warnings (EWIs) | Minor compatibility notes | Review each one |
| Errors | Blocking issues | Must be 0 |
