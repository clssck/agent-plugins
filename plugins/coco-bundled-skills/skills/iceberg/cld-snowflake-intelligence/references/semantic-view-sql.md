# CREATE SEMANTIC VIEW SQL Reference

Source: https://docs.snowflake.com/en/sql-reference/sql/create-semantic-view

## Syntax

```sql
CREATE [ OR REPLACE ] SEMANTIC VIEW [ IF NOT EXISTS ] <name>
  TABLES ( logicalTable [ , ... ] )
  [ RELATIONSHIPS ( relationshipDef [ , ... ] ) ]
  [ FACTS ( factExpression [ , ... ] ) ]
  [ DIMENSIONS ( dimensionExpression [ , ... ] ) ]
  [ METRICS ( metricExpression [ , ... ] ) ]
  [ COMMENT = '<comment>' ]
```

**Clause order matters**: TABLES → RELATIONSHIPS → FACTS → DIMENSIONS → METRICS

## Logical Tables

```sql
[ <alias> AS ] <fully_qualified_table_name>
  [ PRIMARY KEY ( <col> [ , ... ] ) ]
  [ UNIQUE ( <col> [ , ... ] ) ]
  [ WITH SYNONYMS = ( '<synonym>' [ , ... ] ) ]
  [ COMMENT = '<comment>' ]
```

## Relationships

```sql
<table_alias> ( <column> [ , ... ] ) REFERENCES <ref_table_alias>
```

## Dimensions

```sql
<table_alias>.<dimension_name> AS <sql_expr>
  [ WITH SYNONYMS = ( '<synonym>' [ , ... ] ) ]
  [ COMMENT = '<comment>' ]
```

## Facts

```sql
[ PRIVATE | PUBLIC ] <table_alias>.<fact_name> AS <sql_expr>
  [ WITH SYNONYMS = ( '<synonym>' [ , ... ] ) ]
  [ COMMENT = '<comment>' ]
```

## Metrics

```sql
[ PRIVATE | PUBLIC ] <table_alias>.<metric_name> AS <aggregate_expr>
  [ WITH SYNONYMS = ( '<synonym>' [ , ... ] ) ]
  [ COMMENT = '<comment>' ]
```

## Complete Example (TPC-H)

```sql
CREATE OR REPLACE SEMANTIC VIEW tpch_analysis
  TABLES (
    region AS SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.REGION
      PRIMARY KEY (r_regionkey),
    nation AS SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.NATION
      PRIMARY KEY (n_nationkey),
    customer AS SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.CUSTOMER
      PRIMARY KEY (c_custkey),
    orders AS SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.ORDERS
      PRIMARY KEY (o_orderkey)
  )
  RELATIONSHIPS (
    nation (n_regionkey) REFERENCES region,
    customer (c_nationkey) REFERENCES nation,
    orders (o_custkey) REFERENCES customer
  )
  FACTS (
    customer.c_customer_order_count AS COUNT(orders.o_orderkey)
  )
  DIMENSIONS (
    nation.nation_name AS n_name,
    customer.customer_name AS c_name,
    customer.customer_market_segment AS c_mktsegment,
    orders.order_date AS o_orderdate
  )
  METRICS (
    customer.customer_count AS COUNT(c_custkey),
    orders.order_count AS COUNT(o_orderkey),
    orders.order_average_value AS AVG(o_totalprice)
  );
```

## CLD-Specific Example

**Note**: Before drafting a semantic view, fetch the latest documentation at https://docs.snowflake.com/en/sql-reference/sql/create-semantic-view to ensure syntax is current.

Example using CLD tables with fully qualified names:

```sql
CREATE OR REPLACE SEMANTIC VIEW <target_db>.<schema>.<view_name>
  TABLES (
    orders AS <cld_db>.<cld_schema>.ORDERS
      PRIMARY KEY (ORDER_ID)
      WITH SYNONYMS = ('purchases', 'transactions')
      COMMENT = 'Customer orders',
    products AS <cld_db>.<cld_schema>.PRODUCTS
      PRIMARY KEY (PRODUCT_ID)
      COMMENT = 'Product catalog',
    users AS <cld_db>.<cld_schema>.USERS
      PRIMARY KEY (USER_ID)
      WITH SYNONYMS = ('customers')
      COMMENT = 'User information'
  )
  RELATIONSHIPS (
    orders (USER_ID) REFERENCES users,
    orders (PRODUCT_ID) REFERENCES products
  )
  DIMENSIONS (
    orders.order_date AS ORDER_DATE
      WITH SYNONYMS = ('date', 'when')
      COMMENT = 'Order date',
    products.category AS CATEGORY
      WITH SYNONYMS = ('product type')
      COMMENT = 'Product category',
    users.country AS COUNTRY
      WITH SYNONYMS = ('region', 'location')
      COMMENT = 'User country'
  )
  METRICS (
    orders.total_revenue AS SUM(TOTAL_AMOUNT)
      WITH SYNONYMS = ('revenue', 'sales')
      COMMENT = 'Total revenue',
    orders.order_count AS COUNT(ORDER_ID)
      WITH SYNONYMS = ('number of orders')
      COMMENT = 'Order count',
    orders.avg_order_value AS AVG(TOTAL_AMOUNT)
      COMMENT = 'Average order value'
  )
  COMMENT = 'Semantic view for CLD Iceberg data';
```

## Key Points

- Dimensions: categorical columns for grouping/filtering (no aggregation)
- Facts: computed values or counts used internally
- Metrics: aggregated measures (SUM, COUNT, AVG, etc.)
- Synonyms help natural language understanding
- Comments improve discoverability
