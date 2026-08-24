# Supported Queries and Limitations

Query patterns, limitations, and best practices for Snowflake Dynamic Tables.

---

## Fully Supported Query Patterns

### Basic Transformations

```sql
-- Simple projection and filtering
CREATE DYNAMIC TABLE dt AS
SELECT col1, col2, col3
FROM source_table
WHERE status = 'active';

-- Column expressions
CREATE DYNAMIC TABLE dt AS
SELECT 
  id,
  UPPER(name) as name_upper,
  amount * 1.1 as amount_with_tax,
  CASE WHEN type = 'A' THEN 'Alpha' ELSE 'Other' END as type_label
FROM source_table;
```

### Aggregations

```sql
-- GROUP BY with aggregates
CREATE DYNAMIC TABLE dt AS
SELECT 
  region,
  DATE_TRUNC('day', order_date) as order_day,
  SUM(amount) as total_amount,
  COUNT(*) as order_count,
  AVG(amount) as avg_amount
FROM orders
GROUP BY 1, 2;

-- HAVING clause
CREATE DYNAMIC TABLE dt AS
SELECT customer_id, SUM(amount) as total
FROM orders
GROUP BY customer_id
HAVING SUM(amount) > 1000;
```

### Joins

```sql
-- INNER JOIN
CREATE DYNAMIC TABLE dt AS
SELECT o.*, c.customer_name
FROM orders o
INNER JOIN customers c ON o.customer_id = c.id;

-- LEFT JOIN
CREATE DYNAMIC TABLE dt AS
SELECT o.*, c.customer_name
FROM orders o
LEFT JOIN customers c ON o.customer_id = c.id;

-- Multiple joins
CREATE DYNAMIC TABLE dt AS
SELECT o.id, c.name, p.product_name
FROM orders o
JOIN customers c ON o.customer_id = c.id
JOIN products p ON o.product_id = p.id;
```

### Subqueries

```sql
-- Scalar subquery
CREATE DYNAMIC TABLE dt AS
SELECT *,
  (SELECT MAX(amount) FROM orders) as max_order_amount
FROM orders;

-- IN subquery
CREATE DYNAMIC TABLE dt AS
SELECT * FROM orders
WHERE customer_id IN (SELECT id FROM vip_customers);

-- EXISTS subquery
CREATE DYNAMIC TABLE dt AS
SELECT * FROM customers c
WHERE EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.id);
```

### Set Operations

```sql
-- UNION ALL (supported for incremental)
CREATE DYNAMIC TABLE dt AS
SELECT id, name, 'source_a' as source FROM table_a
UNION ALL
SELECT id, name, 'source_b' as source FROM table_b;
```

---

## Partially Supported Patterns

### DISTINCT

```sql
-- DISTINCT may trigger full refresh in some cases
CREATE DYNAMIC TABLE dt AS
SELECT DISTINCT customer_id, product_id
FROM orders;
```

**Recommendation:** Use GROUP BY instead if incremental is important:
```sql
CREATE DYNAMIC TABLE dt AS
SELECT customer_id, product_id
FROM orders
GROUP BY customer_id, product_id;
```

### UNION (Distinct)

```sql
-- May require full refresh
CREATE DYNAMIC TABLE dt AS
SELECT id FROM table_a
UNION
SELECT id FROM table_b;
```

**Recommendation:** Use UNION ALL if duplicates are acceptable.

### Window Functions

```sql
-- Simple window functions may work
CREATE DYNAMIC TABLE dt AS
SELECT *,
  ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_date) as rn
FROM orders;
```

**Note:** Complex window functions or multiple windows may trigger full refresh.

### Outer Joins (With Restrictions)

Outer joins support incremental refresh but with restrictions. See [incremental-operators.md](incremental-operators.md) for full details.

```sql
-- ✅ LEFT OUTER JOIN - supported with restrictions
CREATE DYNAMIC TABLE dt AS
SELECT * FROM table_a a
LEFT JOIN table_b b ON a.id = b.id;

-- ✅ RIGHT OUTER JOIN - supported with restrictions
CREATE DYNAMIC TABLE dt AS
SELECT * FROM table_a a
RIGHT JOIN table_b b ON a.id = b.id;

-- ✅ FULL OUTER JOIN - supported with restrictions
CREATE DYNAMIC TABLE dt AS
SELECT * FROM table_a a
FULL OUTER JOIN table_b b ON a.id = b.id;
```

**Restrictions (falling back to FULL if violated):**
- Equality predicates only in ON clause (non-equality predicates such as `ON a.id > b.id` force FULL refresh)

---

## NOT Supported Patterns

### Set Operations

```sql
-- ❌ EXCEPT - not supported for incremental
CREATE DYNAMIC TABLE dt AS
SELECT id FROM table_a
EXCEPT
SELECT id FROM table_b;

-- ❌ INTERSECT - not supported
CREATE DYNAMIC TABLE dt AS
SELECT id FROM table_a
INTERSECT
SELECT id FROM table_b;
```

### Non-Deterministic Functions

```sql
-- ❌ RANDOM() - not supported
CREATE DYNAMIC TABLE dt AS
SELECT *, RANDOM() as random_val FROM table_a;

-- ❌ UUID_STRING() - not supported
CREATE DYNAMIC TABLE dt AS
SELECT *, UUID_STRING() as unique_id FROM table_a;
```

**Exception:** Timestamp functions ARE supported:
```sql
-- ✅ CURRENT_TIMESTAMP is supported
CREATE DYNAMIC TABLE dt AS
SELECT *, CURRENT_TIMESTAMP() as load_time FROM table_a;
```

---

## SELECT * Caveats

### Problem

Using `SELECT *` causes the DT to fail if the base table schema changes:

```sql
-- ⚠️ Risky: Will fail if source_table adds/removes columns
CREATE DYNAMIC TABLE dt AS
SELECT * FROM source_table;
```

### Recommendation

Always use explicit column names:

```sql
-- ✅ Safe: Schema changes won't break DT
CREATE DYNAMIC TABLE dt AS
SELECT id, name, amount, order_date FROM source_table;
```

---

## Base Table Requirements

### Change Tracking

Dynamic tables require change tracking on base tables:

```sql
-- Check if enabled
SHOW TABLES LIKE 'source_table';
-- Look for change_tracking = TRUE

-- Enable if needed
ALTER TABLE source_table SET CHANGE_TRACKING = TRUE;
```

### Views as Source

- Views CAN be used as source for DTs
- The underlying tables must have change tracking enabled
- Materialized views can also be used

---

## FROZEN WHERE Constraints

> `FROZEN WHERE` was formerly called `IMMUTABLE WHERE`. The old keyword is a legacy alias — existing/older dynamic tables and their `GET_DDL` may still show `IMMUTABLE WHERE`; recognize and preserve whichever a DT already uses.

### Supported Predicates

```sql
-- ✅ Simple comparison
FROZEN WHERE (order_date < '2024-01-01')

-- ✅ CURRENT_TIMESTAMP functions
FROZEN WHERE (created_at < CURRENT_TIMESTAMP() - INTERVAL '7 days')

-- ✅ CURRENT_DATE
FROZEN WHERE (event_date < CURRENT_DATE() - 30)

-- ✅ Compound conditions
FROZEN WHERE (status = 'archived' AND created_at < CURRENT_DATE() - 90)
```

### NOT Supported in FROZEN WHERE

```sql
-- ❌ Subqueries
FROZEN WHERE (id IN (SELECT id FROM other_table))

-- ❌ UDFs
FROZEN WHERE (my_udf(column) = TRUE)

-- ❌ Non-deterministic (except timestamp)
FROZEN WHERE (RANDOM() < 0.5)
```

---

## Query Size and Complexity Limits

### Recommendations

| Metric | Recommendation |
|--------|----------------|
| Query complexity | Break into multiple DTs if query has >5 joins |
| Refresh time | Should be less than target lag |
| Data volume | Consider partitioning for large tables |
| Intermediate results | Materialize expensive operations |

### Signs You Should Decompose

- Refresh takes longer than target lag
- Query has multiple expensive JOINs
- Query has multiple aggregation stages
- refresh_mode_reason shows unsupported constructs

---

## Best Practices Summary

1. **Use explicit columns** - Avoid `SELECT *`
2. **Enable change tracking** - On all base tables
3. **Prefer LEFT JOIN** - Over RIGHT or FULL OUTER
4. **Use UNION ALL** - Instead of UNION when possible
5. **Decompose complex queries** - Into intermediate DTs
6. **Use DOWNSTREAM lag** - For intermediate tables
7. **Test with AUTO** - Check what Snowflake chooses
8. **Review refresh_mode_reason** - Understand why FULL is used

