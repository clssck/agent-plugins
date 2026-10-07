# Limitations Reference

Key constraints and limitations for interactive tables and warehouses.

---

## Interactive Warehouse Limitations

| Limitation | Details |
|------------|---------|
| **Query timeout** | 5 seconds on interactive warehouse. Queries exceeding this fail unless FALLBACK_WAREHOUSE is configured, in which case they are transparently retried on the (non-interactive) fallback warehouse. |
| **Standard tables** | Cannot query standard tables |
| **Mixed queries** | Cannot JOIN interactive with standard tables |
| **Auto-suspend** | Supported. Configure via `ALTER WAREHOUSE ... SET AUTO_SUSPEND = <seconds>`. |
| **Auto-scale** | Supported. MIN_CLUSTER_COUNT and MAX_CLUSTER_COUNT can differ for auto-scaling. |
| **Stored procedures** | CALL commands not supported |
| **Pipe operator** | ->> operator not supported |

---

## Interactive Table Limitations

| Limitation | Details |
|------------|---------|
| **UPDATE** | Not supported |
| **DELETE** | Not supported |
| **ALTER columns** | Cannot add/drop columns (only RENAME table) |
| **INSERT (streaming)** | Cannot SQL INSERT into streaming tables |
| **Streams** | Cannot create streams on interactive tables |
| **Materialized views** | Cannot be source for materialized views |
| **Dynamic tables** | Cannot be base table for dynamic tables |
| **Replication** | Supported. Can be included in replication/failover groups. |

**Note**: Masking policies, row access policies, aggregation policies, and join policies ARE now supported via ALTER TABLE commands.

---

## Workarounds

### For UPDATE/DELETE

Use **Standard + Dynamic Pattern**:
1. Create standard table for DML operations
2. Create dynamic interactive table with TARGET_LAG
3. Perform UPDATE/DELETE on standard table
4. Changes sync to interactive table automatically

### For Standard Table Access

Convert to interactive table:
```sql
CREATE INTERACTIVE TABLE my_table_interactive
CLUSTER BY (id)
AS SELECT * FROM my_standard_table;
```

### For Column Changes

Recreate the table:
```sql
CREATE OR REPLACE INTERACTIVE TABLE my_table
CLUSTER BY (id)
AS SELECT *, NULL AS new_column FROM source_table;
```

---

## ✅ Supported Operations

| Operation | Supported |
|-----------|-----------|
| SELECT | ✅ Yes |
| WHERE, GROUP BY, ORDER BY | ✅ Yes |
| LIMIT | ✅ Yes |
| JOINs (between interactive tables) | ✅ Yes |
| Aggregations (COUNT, SUM, AVG, etc.) | ✅ Yes |
| INSERT OVERWRITE (static tables) | ✅ Yes |
| CREATE, DROP | ✅ Yes |
| RENAME table | ✅ Yes |
| SHOW, DESCRIBE | ✅ Yes |

---

## TARGET_LAG Constraints

| Constraint | Value |
|------------|-------|
| Minimum | 60 seconds (1 minute) |
| Requires WAREHOUSE | Yes |
| Format | `'<num> { seconds \| minutes \| hours \| days }'` |

---

## Region Availability

Interactive tables and warehouses are available across AWS, Azure, and GCP.

For the current list of supported regions, see the [Snowflake documentation](https://docs.snowflake.com/en/user-guide/interactive#label-interactive-region-availability).
