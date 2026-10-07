---
parent_skill: data-quality
---

# Workflow 6: Compare Tables

Compare Snowflake tables to identify row-level and schema-level differences for pipeline validation, migration testing, and data reconciliation.

## When to Load
Data-quality Step 1: compare tables/data diff/migration/reconciliation intent.

## Workflow Decision Tree

```
User provides comparison request
  |
  v
Step 1: Extract table references and key columns
  |
  v
Step 2: Identify intent --> Load workflow
  |
  ├── Quick check / summary --------> Load workflows/compare-tables/summary-diff.md
  |
  ├── Row-level details ------------> Load workflows/compare-tables/row-level-diff.md
  |
  ├── Schema comparison ------------> Load workflows/compare-tables/schema-comparison.md
  |
  ├── Distribution analysis --------> Load workflows/compare-tables/distribution-analysis.md
  |
  └── Full validation report -------> Load workflows/compare-tables/validation-report.md
```

## Workflow

### Step 1: Extract Comparison Parameters

**Goal:** Identify the source table, target table, and key columns from the user's message.

**Actions:**

1. Parse the user's message for table references (DATABASE.SCHEMA.TABLE format)
2. Identify which is source (baseline/before) and which is target (new/after)
3. Ask for primary key column(s) if not provided
4. Store as `<source_table>`, `<target_table>`, and `<key_column>` for template replacement

**If ambiguous, ask:**
```
Which table is the baseline (source) and which is the new version (target)?

1. SOURCE (baseline): ?
2. TARGET (new version): ?
3. Primary key column(s): ?
```

### Step 2: Route to Workflow

**Goal:** Determine which workflow matches the user's intent and load it.

**Actions:**

| User Intent | Workflow to Load |
|---|---|
| Quick summary, how many differences | **Load** `workflows/compare-tables/summary-diff.md` |
| Show me the actual rows, drill down | **Load** `workflows/compare-tables/row-level-diff.md` |
| Compare table schemas first | **Load** `workflows/compare-tables/schema-comparison.md` |
| Distribution shift, statistical comparison | **Load** `workflows/compare-tables/distribution-analysis.md` |
| Full validation, migration sign-off | **Load** `workflows/compare-tables/validation-report.md` |

If the intent is ambiguous, default to `summary-diff.md` (quick overview first).

### Step 3: Execute Template from Workflow

**Goal:** Run the SQL template or data_diff tool specified by the loaded workflow.

**Actions:**

1. Read the SQL template specified in the workflow file (from `templates/compare-tables/` directory)
2. Replace all placeholders:
   - `<source_table>` with the actual source table (DATABASE.SCHEMA.TABLE)
   - `<target_table>` with the actual target table (DATABASE.SCHEMA.TABLE)
   - `<key_column>` with the primary key column(s)
3. For detailed row-level diff, use the `data_diff` tool directly
4. Execute using `snowflake_sql_execute` for SQL templates

**Error handling:**
- If tables don't exist: report clearly and stop
- If key column doesn't exist: ask user to provide correct column
- If comparison times out: suggest filtering with `-w` option

### Step 4: Present Results

**Goal:** Format and present results per the workflow's output guidelines.

Follow the output format specified in the loaded workflow file. Suggest logical next steps based on findings.

## Tools

### data_diff

**Description:** Compare two Snowflake tables and identify row-level differences (added, removed rows).

**When to use:** Detailed row-level comparison between tables.

**Usage patterns:**

```bash
# Same-database diff
"snowflake://<connection>/DATABASE/SCHEMA" table1 table2 -k key_col -c %

# Cross-database diff
"snowflake://<connection>/DB1/SCHEMA" table1 "snowflake://<connection>/DB2/SCHEMA" table2 -k key_col -c %

# Summary only
"snowflake://<connection>/DATABASE/SCHEMA" table1 table2 -k key_col -c % -s

# With filter
"snowflake://<connection>/DATABASE/SCHEMA" table1 table2 -k key_col -c % -w "created_at > '2024-01-01'"

# Materialize results
"snowflake://<connection>/DATABASE/SCHEMA" table1 table2 -k key_col -c % -m DIFF_RESULTS_%t
```

**Key options:**
- `-k`: Primary key column (required, can use multiple for compound keys)
- `-c %`: Compare all columns (or specify individual columns with `-c col1 -c col2`)
- `-s`: Summary statistics only (counts, no row details)
- `-w`: WHERE clause filter
- `-m`: Materialize diff results to a new table

### snowflake_sql_execute

**Description:** Executes SQL queries against the user's Snowflake account.

**When to use:** Schema comparison, aggregate summaries, distribution analysis, and custom queries.

**Templates available:**

| Template | Purpose | Type |
|---|---|---|
| `compare-tables/schema-comparison.sql` | Compare table schemas | Read |
| `compare-tables/row-count-comparison.sql` | Compare row counts | Read |
| `compare-tables/aggregate-comparison.sql` | Compare aggregates (SUM, AVG, etc.) | Read |
| `compare-tables/added-rows.sql` | Find rows in target but not source | Read |
| `compare-tables/removed-rows.sql` | Find rows in source but not target | Read |
| `compare-tables/modified-rows.sql` | Find rows with changed values | Read |
| `compare-tables/distribution-categorical.sql` | Compare categorical value distributions | Read |
| `compare-tables/distribution-numeric.sql` | Compare numeric distributions (percentiles) | Read |
| `compare-tables/exact-match.sql` | Check if tables are identical | Read |

## Execution Rule

All SQL comparison templates (`SELECT`-based) and `data_diff` comparisons are **read-only — execute immediately without confirmation**.

Exception: the `-m` (materialize) option in `data_diff` creates a new table — confirm the table name and location with the user before using it.

## Stopping Points

- Before detailed row-level diff: Present summary first, ask if user wants to drill down
- After finding significant differences: Present findings and ask for next action (drill down, export, or accept)
- Before materializing results with `-m` (creates a table): Confirm table name and location with user

**Resume rule:** Upon user approval, proceed directly to the next step without re-asking.

## Output

Each workflow produces structured output:

- **Summary Diff**: Row counts, added/removed/modified counts, quick health check
- **Row-Level Diff**: Actual rows that differ with key and changed values
- **Schema Comparison**: Column additions, removals, type changes
- **Distribution Analysis**: Statistical comparison of value distributions
- **Validation Report**: Comprehensive report with PASS/FAIL/REVIEW recommendation

## Error Handling

| Error | Action |
|---|---|
| Table not found | Verify table name and permissions |
| Key column not found | Ask user to specify correct primary key |
| Timeout on large tables | Suggest adding filter with `-w` option |
| No differences found | Report "Tables are identical" |
| Cross-database permission error | Verify user has access to both databases |

## Reference

For detailed data_diff tool usage, **Load** `reference/compare-tables/compare-tables-concepts.md` when the user asks about tool options, connection strings, or comparison strategies.
