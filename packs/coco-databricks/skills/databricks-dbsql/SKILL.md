---
name: databricks-dbsql
description: >-
  Databricks SQL (DBSQL) advanced features and SQL warehouse capabilities.
  Use when the user mentions: DBSQL, Databricks SQL, SQL warehouse,
  SQL scripting, stored procedure, CALL procedure, materialized view,
  CREATE MATERIALIZED VIEW, pipe syntax, pipe operator, geospatial, H3,
  ST_, spatial SQL, collation, COLLATE, ai_query, ai_classify, ai_extract,
  ai_gen, ai_analyze_sentiment, ai_similarity, ai_forecast, ai_mask,
  ai_fix_grammar, ai_parse_document, vector_search, AI function,
  http_request, remote_query, read_files, Lakehouse Federation,
  recursive CTE, WITH RECURSIVE, multi-statement transaction,
  temp table, temporary view, data modeling best practices on Databricks,
  Liquid Clustering, star schema Databricks, SCD Type 2 Databricks.
---

# Databricks SQL (DBSQL) - Advanced Features

## Prerequisites

- Databricks CLI v0.205+ installed and authenticated (see `databricks-cli-install` skill; for CLI operations see `databricks-cli` skill)
- A Databricks SQL warehouse (Serverless recommended for AI functions, MVs, and http_request)

## Detecting Unity Catalog vs Hive Metastore

**Before assuming Unity Catalog is available, always check:**

```bash
databricks metastores current --output json 2>&1
```

- **If a metastore is returned:** Unity Catalog is active. Use three-level naming (`catalog.schema.table`) throughout.
- **If it errors or returns nothing:** The workspace uses the legacy Hive Metastore. In this case:
  - Use two-level naming (`schema.table` or `database.table`) instead of three-level
  - The `default` database is always available
  - UC-only features are **unavailable**: materialized views, AI functions, grants CLI, Liquid Clustering, pipe syntax
  - SQL execution via `databricks api post /api/2.0/sql/statements` still works with two-level references
  - Skip any instructions that reference `catalog.schema.table` and adapt to `schema.table`

## When to Use

- User wants to write or debug Databricks SQL (procedural SQL, stored procedures, MVs, AI functions)
- User asks about DBSQL-specific features (pipe syntax, geospatial, collations, http_request)
- User needs data modeling guidance for the Databricks Lakehouse
- User wants to use AI functions (ai_query, ai_classify, ai_extract, etc.) in SQL

## Workflow

> **Convention:** All placeholders in `<angle-brackets>` must be replaced with actual values from the user. All SQL examples use three-level Unity Catalog naming: `catalog.schema.object`.

### Step 1: Detect Intent

**Goal:** Determine which DBSQL feature area the user needs.

**Route by topic:**

| User mentions | Load reference |
|---------------|----------------|
| SQL scripting, BEGIN...END, DECLARE, IF/WHILE/FOR, stored procedure, CREATE PROCEDURE, CALL, recursive CTE, WITH RECURSIVE, transaction | **Load** `references/sql-scripting.md` |
| ai_query, ai_classify, ai_extract, ai_gen, ai_summarize, ai_analyze_sentiment, ai_similarity, ai_mask, ai_fix_grammar, ai_forecast, ai_parse_document, vector_search, AI function, http_request, remote_query, read_files, Lakehouse Federation | **Load** `references/ai-functions.md` |
| Materialized view, CREATE MATERIALIZED VIEW, refresh, temp table, temporary view, pipe syntax, `\|>` operator | **Load** `references/materialized-views-pipes.md` |
| Geospatial, H3, h3_longlatash3, ST_Point, ST_Contains, spatial, collation, COLLATE, UTF8_LCASE, case-insensitive | **Load** `references/geospatial-collations.md` |
| Data modeling, star schema, dimension table, fact table, Liquid Clustering, partitioning, Z-ORDER, SCD, best practices, performance | **Load** `references/best-practices.md` |

If the intent spans multiple areas, load the primary reference first and additional references as needed.

### Step 2: Understand the User's Goal

**⚠️ MANDATORY STOPPING POINT**: Before writing any SQL, ask the user:

1. What are you trying to accomplish?
2. Which catalog/schema/tables are involved?
3. What SQL warehouse type are you using? (Serverless required for AI functions, MVs, http_request)

Do NOT proceed until the user responds.

### Step 3: Write or Debug SQL

**Goal:** Help the user write, optimize, or debug their SQL.

**Actions:**

1. Use the loaded reference for correct syntax, parameters, and patterns
2. Write SQL using three-level Unity Catalog naming (`catalog.schema.table`)
3. Include comments explaining non-obvious logic
4. For procedural SQL: use proper BEGIN...END blocks, DECLARE variables, and error handling
5. For AI functions: always include `LIMIT` during development to control costs

**⚠️ MANDATORY STOPPING POINT**: Before executing any DDL or DML (CREATE, ALTER, DROP, INSERT, UPDATE, DELETE, MERGE), present the SQL to the user for approval.

### Step 4: Verify Results

**Goal:** Confirm the SQL works as expected.

**Actions:**

1. If the user approved execution, run the SQL
2. Check for errors and suggest fixes if needed
3. For materialized views: verify refresh status
4. For stored procedures: test with sample parameters

## Quick Reference

| Feature | Key Syntax | Requires | Reference |
|---------|-----------|----------|-----------|
| SQL Scripting | `BEGIN...END`, `DECLARE`, `IF/WHILE/FOR` | DBR 16.3+ | `references/sql-scripting.md` |
| Stored Procedures | `CREATE PROCEDURE`, `CALL` | DBR 17.0+ | `references/sql-scripting.md` |
| Recursive CTEs | `WITH RECURSIVE` | DBR 17.0+ | `references/sql-scripting.md` |
| Transactions | `BEGIN ATOMIC...END` | Preview | `references/sql-scripting.md` |
| Materialized Views | `CREATE MATERIALIZED VIEW` | Serverless | `references/materialized-views-pipes.md` |
| Temp Tables | `CREATE TEMPORARY TABLE` | All | `references/materialized-views-pipes.md` |
| Pipe Syntax | `\|>` operator | DBR 16.1+ | `references/materialized-views-pipes.md` |
| Geospatial (H3) | `h3_longlatash3()` | DBR 11.2+ | `references/geospatial-collations.md` |
| Geospatial (ST) | `ST_Point()`, `ST_Contains()` | DBR 16.0+ | `references/geospatial-collations.md` |
| Collations | `COLLATE`, `UTF8_LCASE` | DBR 16.1+ | `references/geospatial-collations.md` |
| AI Functions | `ai_query()`, `ai_classify()`, 11+ funcs | Serverless, DBR 15.1+ | `references/ai-functions.md` |
| http_request | `http_request(conn, ...)` | Serverless | `references/ai-functions.md` |
| remote_query | `SELECT * FROM remote_query(...)` | Serverless | `references/ai-functions.md` |
| read_files | `SELECT * FROM read_files(...)` | All | `references/ai-functions.md` |
| Data Modeling | Star schema, Liquid Clustering | All | `references/best-practices.md` |

## Common Patterns

### Procedural ETL with SQL Scripting

```sql
BEGIN
  DECLARE v_count INT;
  SET v_count = (SELECT COUNT(*) FROM catalog.schema.raw_orders WHERE status = 'new');

  IF v_count > 0 THEN
    INSERT INTO catalog.schema.processed_orders
    SELECT *, current_timestamp() AS processed_at
    FROM catalog.schema.raw_orders
    WHERE status = 'new';
  END IF;

  SELECT v_count AS rows_processed;
END
```

### AI-Powered Data Enrichment

```sql
SELECT
  ticket_id,
  ai_classify(description, ARRAY('billing', 'technical', 'account')) AS category,
  ai_analyze_sentiment(description) AS sentiment
FROM catalog.schema.support_tickets
LIMIT 100;
```

### Materialized View with Scheduled Refresh

```sql
CREATE OR REPLACE MATERIALIZED VIEW catalog.schema.daily_revenue
  CLUSTER BY (order_date)
  SCHEDULE EVERY 1 HOUR
AS SELECT
    order_date, region,
    SUM(amount) AS total_revenue,
    COUNT(DISTINCT customer_id) AS unique_customers
FROM catalog.schema.fact_orders
JOIN catalog.schema.dim_store USING (store_id)
GROUP BY order_date, region;
```

### Pipe Syntax

```sql
FROM catalog.schema.fact_orders
  |> WHERE order_date >= current_date() - INTERVAL 30 DAYS
  |> AGGREGATE SUM(amount) AS total, COUNT(*) AS cnt GROUP BY region
  |> WHERE total > 10000
  |> ORDER BY total DESC
  |> LIMIT 20;
```

## Stopping Points

- Before Step 2: clarify user intent and target objects
- Before executing any DDL/DML in Step 3
- After Step 4 if results are unexpected (diagnose before retrying)

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `AI function not available` | Requires Serverless SQL warehouse. Classic SQL warehouses do not support AI functions. |
| `MATERIALIZED VIEW requires serverless` | Create/refresh MVs only on Serverless SQL warehouses. |
| `SQLSTATE error in BEGIN...END` | Check variable scoping and handler declarations. See `references/sql-scripting.md` Exception Handling. |
| `H3 function not found` | Requires DBR 11.2+. Check cluster/warehouse runtime version. |
| `ST_ function not found` | Requires DBR 16.0+. ST functions are in Public Preview. |
| `Pipe syntax parse error` | Requires DBR 16.1+. Each pipe stage must start with `\|>` on a new line. |
| `http_request connection error` | Verify CONNECTION object exists and has correct host/credentials. |
| `Collation mismatch` | Use explicit `COLLATE` in comparisons or align column collations. |

## Output

- Working Databricks SQL for the user's use case
- Correct syntax following DBSQL-specific features and requirements
- Performance-optimized queries following Lakehouse best practices
