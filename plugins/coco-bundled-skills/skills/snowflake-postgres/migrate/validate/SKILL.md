---
name: validate
description: "Validate data integrity after PostgreSQL to Snowflake Postgres migration. Use for: validate migration, data validation, compare data, verify migration, row count comparison, checksum validation, pgCompare, SnowConvert, sample data check, aggregation comparison, pre-cutover validation."
parent_skill: migrate
---

# Migration Validation

> **Windows users:** see [references/windows.md](../../references/windows.md) — install prereqs, credential file paths (`%APPDATA%\postgresql\` instead of `~/`), and command-flow notes differ on native Windows. WSL behaves as Linux.

## When to Load

Main skill routes here for: "validate migration", "data validation", "compare data", "verify migration"

> **Credentials:** `validate_migration.py` accepts `--source-service` / `--target-service`; passwords resolve from `~/.pgpass`, never CLI or chat. See `migrate/SKILL.md` "Credentials" callout for details.

## Prerequisites

- Migration completed (replication or dump/restore)
- Access to both source and target databases
- Source/target service profiles or connection environment variables available (see main skill)

## FIRST: Confirm Validation

**MANDATORY: Ask before running any validation using `ask_user_question`:**

```
question: "Do you want to run data validation? This compares source and target data (row counts, checksums, etc.) and can take a long time on large tables."
header: "Validate"
options:
  - label: "Yes"
    description: "Run validation checks before cutover (recommended)"
  - label: "No"
    description: "Skip validation entirely and proceed to cutover"
```

**STOP**: Wait for response.
- If **No** → Skip to Output section. Note in the migration state that validation was skipped.
- If **Yes** → Continue to method selection below.

## Ask User for Verification Method

**Present this prompt using `ask_user_question`:**

```
question: "Which validation methods do you want to run?"
multiSelect: true
options:
  - label: "Row counts"
    description: "Quick SQL-based comparison of table row counts"
  - label: "Sample data comparison"
    description: "Compare the same deterministic sample rows between source and target"
  - label: "Checksum validation"
    description: "MD5 hash comparison for data integrity verification"
  - label: "Aggregation checks"
    description: "Compare SUM/AVG/MIN/MAX on numeric columns"
  - label: "SnowConvert (scai)"
    description: "Automated schema analysis (requires Python 3.8+)"
  - label: "pgCompare"
    description: "Full row-by-row data comparison (requires Java 21+)"
  - label: "Show tool instructions"
    description: "Display manual setup guides"
```

## Validation Method Comparison

| Method | What it checks | Speed | Best for |
|--------|---------------|-------|----------|
| Row counts | Table counts match | Fast | Quick sanity check |
| Sample data | Deterministic keyed rows match exactly | Medium | Spot-checking data quality |
| Checksum | MD5 of sorted data matches | Medium | Detecting bit-level differences |
| Aggregation | Numeric totals match | Fast | Financial/metric data |
| SnowConvert | Schema compatibility | Fast | Pre-migration planning, schema issues |
| pgCompare | Every row compared | Slow | Full production validation |

## Recommended Combinations

- **Development/Staging**: Row counts + Sample data
- **Production (basic)**: Row counts + Aggregation + Checksum
- **Production (full)**: Row counts + pgCompare + SnowConvert

## Route Based on Selection

| Selection | Action |
|-----------|--------|
| Row counts | Run `scripts/validate_migration.py --mode quick` |
| Sample data | Run `scripts/validate_migration.py --mode full` |
| Checksum | Run `scripts/validate_migration.py --mode full` |
| Aggregation | Run `scripts/validate_migration.py --mode full` |
| SnowConvert | See `references/validate-snowconvert.md` |
| pgCompare | See `references/validate-pgcompare.md` |
| Sample data (psql fallback) | See `references/validate-sample-data.md` |
| Aggregation (psql fallback) | See `references/validate-aggregation.md` |
| Show tool instructions | Display both manual instruction sections |

### Python-based Validation (RECOMMENDED)

**IMPORTANT:** After bulk data loads (pg_dump/pg_restore, postgres_fdw), row count statistics (`n_live_tup`) are stale. Use `--analyze` to refresh statistics before validation, or use `--mode exact` which runs `SELECT count(*)`:

Use `<SKILL_DIR>/migrate/scripts/validate_migration.py` which connects to both databases and compares automatically:

```bash
# Preferred, chat-safe workflow:
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/validate_migration.py \
    --source-service prod_source --target-service sf_target \
    --mode full --analyze --html validation_report.html

# Trusted-shell fallback:
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/validate_migration.py \
    --host $SOURCE_PGHOST -d $SOURCE_PGDATABASE -U $SOURCE_PGUSER \
    --target-host $TARGET_PGHOST --target-dbname $TARGET_PGDATABASE --target-user $TARGET_PGUSER \
    --mode full --analyze --html validation_report.html
```

Modes:
- `quick` — Compare `pg_stat` row counts (fast, approximate)
- `exact` — Run `SELECT count(*)` on mismatched tables
- `full` — Row counts + checksums + aggregates

For scoped validation (specific schemas only), add `--schemas`:
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/validate_migration.py \
    --source-service prod_source --target-service sf_target \
    --mode full --schemas public,app --html validation_report.html
```

Legacy `--host` / `--target-host` flags remain supported for trusted-shell workflows.

## Validation Report Template

After running validation, present this summary:

```
## Migration Validation Report

### Method Used
[Row counts / SnowConvert / pgCompare / Both]

### Quick Checks
- Total tables: [N] / [N]
- Row count match: [N] / [N] tables
- Total rows: [X,XXX,XXX]

### Schema Validation (if SnowConvert used)
- Objects analyzed: [N]
- Compatibility: [N]% 
- Warnings: [N]
- Errors: [N]

### Data Validation (if pgCompare used)
- Tables compared: [N]
- Tables passed: [N]
- Tables failed: [N]
- Mismatched rows: [N]

### Issues Found
[List any discrepancies]

### Recommendation
[GO / NO-GO for cutover]
```

## Output

- Validation method selected by user
- Validation results
- Clear GO/NO-GO recommendation
- List of any discrepancies

## Stopping Points

- After presenting verification options (user must select)
- Before installing tools (user must confirm)
- After displaying results (user must acknowledge before cutover)
