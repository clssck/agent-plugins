---
name: range-join
description: Range join (SCD2) reference — attribute each fact row to the dimension version active during a closed [valid_from, valid_to) period using a constraints[].distinct_range block plus a relationship column with type, range, and right_range.
parent_skill: sv-modeling-patterns
---

# Range Join (SCD2 Temporal)

## How it works

When a dimension table has explicit `valid_from` + `valid_to` columns (SCD2), a range join finds the single dimension row whose validity period contains the fact event date.

Three pieces:

1. **Declare the time range on the dimension** — `unique_keys` on `(key, valid_from, valid_to)` plus a `constraints[].distinct_range` block naming the start/end columns.
2. **Compound relationship** matches on the key *and* uses `type: range` + `right_range` for the date column.
3. **Use dimensions from the dimension table** — they automatically resolve to the historically-correct record per fact row.

`EXCLUSIVE` end semantics: `valid_to` is the first day the record is *no longer* active. An order on `2024-04-01` falls in `[2024-04-01, 2024-07-01)` → that period's segment.

## Snippet

```yaml
tables:
  - name: customer_segments
    base_table: { database: TARGET_DB, schema: TARGET_SCHEMA, table: CUSTOMER_SEGMENTS }
    primary_key: { columns: [SEGMENT_ID] }
    unique_keys:
      - columns: [CUSTOMER_ID, VALID_FROM, VALID_TO]
    constraints:
      - name: segment_period
        distinct_range:
          start_column: VALID_FROM
          end_column: VALID_TO
    dimensions:
      - name: segment
        synonyms: [tier, subscription tier, plan, customer plan]
        expr: SEGMENT
        data_type: VARCHAR(20)

  - name: orders
    base_table: { database: TARGET_DB, schema: TARGET_SCHEMA, table: ORDERS }
    primary_key: { columns: [ORDER_ID] }
    metrics:
      - name: total_revenue
        expr: SUM(ORDER_AMOUNT)

relationships:
  - name: orders_to_segment
    left_table: orders
    right_table: customer_segments
    relationship_columns:
      - left_column: CUSTOMER_ID
        right_column: CUSTOMER_ID
      # Range join: ORDER_DATE must fall within [VALID_FROM, VALID_TO)
      - left_column: ORDER_DATE
        type: range
        right_range:
          start_column: VALID_FROM
          end_column: VALID_TO
```

## Gotchas

- **Inclusive vs exclusive end dates.** This pattern uses `EXCLUSIVE` semantics — `valid_to` is the first day the record is no longer active. If your data uses inclusive end dates (`valid_to = 2024-03-31` means active *through* that day), convert at load time or wrap with a view that adds 1 day.
- **Type compatibility.** The fact's temporal column must be type-coercible to the dimension's range columns. If your fact has `DATE` but the dimension has `TIMESTAMP_NTZ`, add a `private_access` fact to cast the value, then reference it in the relationship.
- **Entity isolation across range joins.** You cannot use a dimension from a range-joined entity with a metric defined on a *different* entity that is only connected through that range join. If a second fact (e.g. `support_tickets`) is not directly related to `customer_segments`, you cannot break down its metrics by `customer_segments.segment`. Add the dimension directly to the second fact's entity, or establish a direct relationship.
- **No end date column?** Use `asof_join.md` instead — `type: asof` finds the latest record on or before the event without needing a `valid_to`.

## Docs

- [Joining logical tables that contain ranges of values](https://docs.snowflake.com/en/user-guide/views-semantic/sql#joining-logical-tables-that-contain-ranges-of-values)
- [YAML specification for semantic views](https://docs.snowflake.com/en/user-guide/views-semantic/semantic-view-yaml-spec)
