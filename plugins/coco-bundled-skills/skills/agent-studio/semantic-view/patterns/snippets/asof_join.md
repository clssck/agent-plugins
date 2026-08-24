---
name: asof-join
description: ASOF join reference — attribute each fact row to the dimension record active at event time when the dimension only has a start date (no end date).
parent_skill: sv-modeling-patterns
---

# ASOF Join

## How it works

When a dimension table has only a `start_date` (no explicit `end_date`), an ASOF join finds the dimension row with the largest `start_date` that is `<=` the event date for the same key. This is the "as-of" record — the one that was in effect *as of* the event.

Two requirements:

1. **`primary_key` (or `unique_keys`) on `(key, start_date)`** on the dimension table — no end date column needed.
2. **`type: asof`** on the date column inside the relationship's `relationship_columns`. Pair it with a regular `left_column`/`right_column` entry for the entity key.

The SV resolves the historically-correct dimension row automatically — no date-range filtering, no row-numbered sub-query, no ETL view.

## Snippet

```yaml
tables:
  - name: Customer_address
    base_table: { database: TARGET_DB, schema: TARGET_SCHEMA, table: CUSTOMER_ADDRESS }
    primary_key: { columns: [CA_CUSTID, CA_START_DATE] }
    dimensions:
      - name: zip
        synonyms: [zip code, postal code, delivery zip]
        expr: CA_ZIPCODE
        data_type: VARCHAR

  - name: Orders
    base_table: { database: TARGET_DB, schema: TARGET_SCHEMA, table: ORDERS }
    primary_key: { columns: [O_ORDID] }
    metrics:
      - name: total_revenue
        synonyms: [revenue, order revenue, total order value]
        expr: SUM(O_AMOUNT)

relationships:
  - name: orders_to_addr
    left_table: Orders
    right_table: Customer_address
    relationship_columns:
      - left_column: O_CUSTID
        right_column: CA_CUSTID
      # ASOF: for each order, find the address row with the largest
      # CA_START_DATE that is <= O_ORDDATE for the same customer.
      - left_column: O_ORDDATE
        right_column: CA_START_DATE
        type: asof
```

## Gotchas

- **Wrong without `type: asof`.** Joining only on the customer key (no date qualifier) attributes every fact row to whichever dimension row happens to be returned first — typically the most recent. All historical orders get re-attributed to the customer's current address. The pattern's whole purpose is to prevent that mistake.
- **Dimension uniqueness on `(key, start_date)` is required.** Without it the engine cannot resolve the "latest on or before" semantics.
- **Only a `start_date` column is supported.** If you have explicit `start_date` + `end_date` (SCD2 with closed periods) use `range_join.md` (`type: range` + `right_range`) instead — it handles closed validity windows directly.
- **Cross-period dimension breakdowns work as expected** when the breakdown lives on the dimension itself (e.g. `Customer_address.zip`). The ASOF resolution happens before grouping.
- **Base-table columns projected through the ASOF relationship must be NULLABLE.** Querying a `SEMANTIC_VIEW(...)` whose ASOF-joined dimension column is declared `NOT NULL` on the underlying table currently crashes the planner with `XP_WORKER_FAILURE: Unexpected error … Assert "key "pos" not found"` (the planner reports the column as `nullable: true` because ASOF can produce NULLs, but its position lookup uses the base-table NOT NULL signature). Workaround: drop `NOT NULL` on those columns (`ALTER TABLE <dim> ALTER COLUMN <col> DROP NOT NULL;`) — existing SVs start working immediately. The official Snowflake ASOF example happens to use nullable columns; the requirement is **not** documented as of this writing.

## Docs

- [Using a date, time, timestamp, or numeric range to join logical tables (ASOF)](https://docs.snowflake.com/en/user-guide/views-semantic/sql#using-a-date-time-timestamp-or-numeric-range-to-join-logical-tables)
- [YAML specification for semantic views](https://docs.snowflake.com/en/user-guide/views-semantic/semantic-view-yaml-spec)
