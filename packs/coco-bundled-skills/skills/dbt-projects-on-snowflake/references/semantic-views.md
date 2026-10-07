# Semantic Views in dbt

Snowflake semantic views define a business-friendly metadata layer over tables, enabling Cortex Analyst to answer natural language questions about your data. They define tables, relationships, dimensions, and metrics in a single DDL object.

## Default Structure

Unless the user specifies otherwise, a well-formed semantic view should include:

- **TABLES** — the fact and dimension models being exposed
- **RELATIONSHIPS** — FK joins between fact and dimension tables
- **DIMENSIONS** — business-friendly column aliases with synonyms
- **METRICS** — at least 2–3 aggregate measures (e.g., `COUNT`, `SUM`, `AVG` over key fact columns). A semantic view without metrics is technically valid but severely limits Cortex Analyst — it can describe *who/what/where* but cannot answer any *how much / how many* questions.

> If the user's instruction is silent on metrics, default to including them. Derive reasonable measures from the fact table (totals, counts, averages of key numeric columns).

## The dbt_semantic_view Package

The `Snowflake-Labs/dbt_semantic_view` package provides a `semantic_view` materialization for dbt that generates `CREATE OR REPLACE SEMANTIC VIEW` DDL.

### Installation

Add to `packages.yml`:

```yaml
packages:
  - package: Snowflake-Labs/dbt_semantic_view
    version: [">=1.0.0"]
```

Then deploy with an External Access Integration (required for package download):

```bash
snow dbt deploy my_project --source /path --database DB --schema SCHEMA \
    --external-access-integration MY_EAI
```

> Snowflake runs `dbt deps` internally during deploy. You do not need to run it manually.

### Writing a Semantic View Model

Set `materialized='semantic_view'` in the config. The model body IS the DDL body — it gets placed directly after `CREATE OR REPLACE SEMANTIC VIEW <name>`.

Use `{{ ref('model_name') }}` to reference tables (dbt resolves to fully-qualified names and tracks DAG dependencies).

## Syntax Reference

### TABLES (required)

```sql
TABLES (
    sales AS {{ ref('fct_sales') }} PRIMARY KEY (order_id),
    customers AS {{ ref('dim_customers') }} PRIMARY KEY (customer_id)
)
```

Each table can have: `PRIMARY KEY`, `UNIQUE`, `WITH SYNONYMS`, `COMMENT`.

### RELATIONSHIPS

```sql
RELATIONSHIPS (
    sales_to_customers AS sales(customer_id) REFERENCES customers(customer_id)
)
```

Supports standard FK, `ASOF` (time-based), and `BETWEEN ... EXCLUSIVE` (range) joins.

> The referenced column must be declared as `PRIMARY KEY` or `UNIQUE` on the referenced table. If you join on a column that isn't the primary key, add `UNIQUE (<column>)` to that table's definition.

### FACTS

Computed or passthrough fact columns:

```sql
FACTS (
    sales.revenue AS sales.amount * sales.quantity,
    sales.order_count AS sales.order_id
)
```

Facts can be `PUBLIC` (default) or `PRIVATE`, and support `WITH SYNONYMS` and `COMMENT`.

### DIMENSIONS

Business-friendly column aliases with optional synonyms:

```sql
DIMENSIONS (
    customers.customer_name AS customers.customer_name
        WITH SYNONYMS = ('client name', 'account name'),
    sales.sale_year AS YEAR(sales.sale_date)
        WITH SYNONYMS = ('year')
)
```

Dimensions are always public. Support `WITH SYNONYMS`, `COMMENT`, and `WITH CORTEX SEARCH SERVICE`.

### METRICS

Aggregate calculations with optional synonyms:

```sql
METRICS (
    sales.total_revenue AS SUM(sales.revenue)
        WITH SYNONYMS = ('total sales', 'gross revenue'),
    sales.average_order_value AS AVG(sales.amount)
)
```

Derived metrics reference other metrics without a table prefix:

```sql
METRICS (
    sales.total_revenue AS SUM(sales.amount),
    sales.total_orders AS COUNT(sales.order_id),
    avg_revenue_per_order AS sales.total_revenue / sales.total_orders
)
```

Metrics support `USING (relationship)` for path disambiguation, `NON ADDITIVE BY` for semi-additive measures, and window function syntax.

### Additional Clauses

- `COMMENT = 'description'` — describe the semantic view's purpose
- `COPY GRANTS` — preserve grants on replace (or use `config(copy_grants=true)`)
- `AI_SQL_GENERATION 'instructions'` — guide Cortex Analyst SQL generation behavior
- `AI_QUESTION_CATEGORIZATION 'instructions'` — guide question classification

### AI_VERIFIED_QUERIES

Define verified queries inline in the model body — they survive `dbt run` because they become part of the DDL:

```sql
AI_VERIFIED_QUERIES (
    total_revenue_by_region AS (
        QUESTION 'What is the total revenue by region?'
        VERIFIED_AT 1775663123
        ONBOARDING_QUESTION TRUE
        VERIFIED_BY '(STEWARD = data_stewards)'
        SQL 'SELECT * FROM SEMANTIC_VIEW(
            db.schema.sv_name
            DIMENSIONS customers.region
            METRICS sales.total_revenue
        ) ORDER BY total_revenue DESC'
    )
)
```

Only `QUESTION` and `SQL` are required. `VERIFIED_AT`, `ONBOARDING_QUESTION` (default: FALSE), and `VERIFIED_BY` are optional. `VERIFIED_BY` must use a predefined Snowflake contact purpose (e.g., `STEWARD`). `SQL` must always be the last field in the block.

VQR SQL must reference only the **dimensions and metrics defined in this semantic view** — not raw table columns.

No dbt package version bump required: `AI_VERIFIED_QUERIES` is a DDL pass-through in the `dbt_semantic_view` package.

**Legacy fallback — `WITH EXTENSION`:** For environments where `AI_VERIFIED_QUERIES` is not yet available, embed VQRs as JSON:

```sql
WITH EXTENSION (CA = '{"verified_queries":[
    {
        "name": "total_revenue_by_region",
        "question": "What is the total revenue by region?",
        "sql": "SELECT * FROM SEMANTIC_VIEW(...)",
        "verified_at": 1775663123,
        "verified_by": "Jane Smith",
        "use_as_onboarding_question": false
    }
]}')
```

`WITH EXTENSION` will continue to work after `AI_VERIFIED_QUERIES` is live — it will not be deprecated.

### Clause Ordering

`TABLES` → `RELATIONSHIPS` → `FACTS` → `DIMENSIONS` → `METRICS` → `COMMENT` → `AI_SQL_GENERATION` → `AI_QUESTION_CATEGORIZATION` → `AI_VERIFIED_QUERIES` → `COPY GRANTS`

## Complete Example

```sql
{{ config(materialized='semantic_view') }}

TABLES (
    shipments AS {{ ref('fct_shipments') }} PRIMARY KEY (shipment_id),
    warehouses AS {{ ref('dim_warehouses') }} PRIMARY KEY (warehouse_id),
    carriers AS {{ ref('dim_carriers') }} PRIMARY KEY (carrier_id) UNIQUE (carrier_code)
)

RELATIONSHIPS (
    shipments_to_warehouses AS shipments(origin_warehouse_id) REFERENCES warehouses(warehouse_id),
    shipments_to_carriers AS shipments(carrier_code) REFERENCES carriers(carrier_code)
)

FACTS (
    shipments.delivery_days AS DATEDIFF('day', shipments.ship_date, shipments.delivery_date)
)

DIMENSIONS (
    warehouses.warehouse_name AS warehouses.warehouse_name WITH SYNONYMS = ('facility'),
    warehouses.country AS warehouses.country WITH SYNONYMS = ('origin country'),
    carriers.carrier_name AS carriers.carrier_name WITH SYNONYMS = ('shipper')
)

METRICS (
    shipments.total_shipments AS COUNT(shipments.shipment_id),
    shipments.avg_delivery_time AS AVG(shipments.delivery_days)
        WITH SYNONYMS = ('average transit time'),
    shipments.total_weight AS SUM(shipments.weight_kg)
)

COMMENT = 'Logistics semantic view for shipment analysis'
```

## Managing Semantic Views

### List

```sql
SHOW SEMANTIC VIEWS IN SCHEMA <database>.<schema>;
SHOW SEMANTIC VIEWS LIKE 'sales%' IN SCHEMA <database>.<schema>;
```

### Describe

```sql
DESCRIBE SEMANTIC VIEW <database>.<schema>.<name>;
```

Returns rows with `object_kind` (TABLE, RELATIONSHIP, DIMENSION, FACT, METRIC, DERIVED_METRIC, AI_VERIFIED_QUERY, CUSTOM_INSTRUCTIONS), `object_name`, `parent_entity`, `property`, `property_value`.

### Query

```sql
-- Specific dimensions and metrics
SELECT * FROM SEMANTIC_VIEW(
    <database>.<schema>.<name>
    DIMENSIONS <table_alias>.<dimension>
    METRICS <table_alias>.<metric>
);

-- All dimensions/metrics from a table (must be table-qualified)
SELECT * FROM SEMANTIC_VIEW(
    <database>.<schema>.<name>
    DIMENSIONS <table_alias>.*
    METRICS <table_alias>.*
);
```

> Bare wildcards (`DIMENSIONS *`) are not supported — always qualify with the logical table alias.

> FACTS and METRICS cannot be combined in the same `SEMANTIC_VIEW()` query.

### Drop

```sql
DROP SEMANTIC VIEW IF EXISTS <database>.<schema>.<name>;
```

### Alter

Only RENAME and COMMENT are supported. Structural changes require `CREATE OR REPLACE`.

```sql
ALTER SEMANTIC VIEW <name> RENAME TO <new_name>;
ALTER SEMANTIC VIEW <name> SET COMMENT = 'description';
```

## Verified Queries

Verified queries (VQRs) are ground-truth question/SQL pairs embedded in the semantic view that help Cortex Analyst generate better answers. Define them inline in the dbt model body using `AI_VERIFIED_QUERIES` — they become part of the DDL and are recreated on every `dbt run`, so they never get wiped.

To add, update, or validate verified queries on an already-deployed semantic view (outside of dbt), load the **`semantic-view` skill**.

## Key Notes

- The model body IS the DDL — no transformation by the package
- `persist_docs` is not supported for semantic views; use inline `COMMENT`
- ALTER SEMANTIC VIEW only supports RENAME and COMMENT — all other changes require CREATE OR REPLACE
- Projects using this package require an External Access Integration for package download at deploy time
