---
name: entity-facts
description: Entity-level facts and calculated dimensions reference — private (access_modifier private_access) aggregated facts (LTV per customer), CASE-derived dimensions (value tiers), and expression-based dimensions (age from birth_year).
parent_skill: sv-modeling-patterns
---

# Entity Facts and Calculated Dimensions

## How it works

Three composable patterns:

1. **Entity-level aggregated fact** — `expr: SUM(orders.order_amount)` on the parent entity aggregates a child-table column up to that entity. One number per customer. Mark it `access_modifier: private_access` so it is not queryable directly but can still be referenced inside the SV.
2. **Derived dimension from an aggregated fact** — `value_segment` is a `CASE WHEN customers.lifetime_value < 1000 ...` expression. The CASE uses the private fact internally; the user only sees the tier.
3. **Calculated dimension from a physical column** — `age: YEAR(CURRENT_DATE()) - BIRTH_YEAR`. Expression evaluated row-by-row at query time. No stored column needed.

`access_modifier: private_access` is for intermediate computation only — not queryable, not in `DESCRIBE`, not visible to Cortex Analyst, but usable in dimension expressions on the same entity. Use the default (public) access modifier when users should see/filter by the value directly.

## Snippet

```yaml
tables:
  - name: customers
    base_table: { database: TARGET_DB, schema: TARGET_SCHEMA, table: CUSTOMERS }
    primary_key: { columns: [CUSTOMER_ID] }
    facts:
      # Entity-level aggregated fact: aggregates child rows up to the customer.
      # private_access = not directly queryable, but usable in dimensions below.
      - name: lifetime_value
        synonyms: [customer LTV, customer lifetime value, total spend]
        expr: SUM(orders.order_amount)
        access_modifier: private_access

    dimensions:
      # Calculated dimension: expression on a physical column, evaluated at query time
      - name: age
        synonyms: [customer age, age in years]
        expr: YEAR(CURRENT_DATE()) - BIRTH_YEAR
        data_type: NUMBER

      # Derived dimension from the entity-level aggregated private fact
      - name: value_segment
        synonyms: [customer tier, value tier, segment]
        expr: >
          CASE
            WHEN customers.lifetime_value < 1000  THEN 'low'
            WHEN customers.lifetime_value <= 3000 THEN 'medium'
            ELSE                                       'high'
          END
        data_type: VARCHAR

  - name: orders
    base_table: { database: TARGET_DB, schema: TARGET_SCHEMA, table: ORDERS }
    primary_key: { columns: [ORDER_ID] }
    facts:
      - { name: order_amount, expr: AMOUNT, data_type: NUMBER }
```

## Gotchas

- **Private facts are not queryable directly** — Cortex Analyst won't expose them. If users need to see the LTV value itself, drop `access_modifier: private_access`.
- **Calculated dimensions are evaluated at query time on every row** — they're cheap for simple expressions (date math, CASE) but consider materializing if the expression is expensive.
- **Entity-level aggregated facts (`SUM(other_table.column)`) require the relationship to be defined.** The aggregation traverses the relationship from the parent entity to the child.
- **Don't confuse `private_access` facts with `non_additive_dimensions` metrics.** `private_access` controls *visibility*; `non_additive_dimensions` controls *aggregation behavior*. Different concerns.

## Docs

- [Defining facts, dimensions, and metrics](https://docs.snowflake.com/en/user-guide/views-semantic/sql#defining-facts-dimensions-and-metrics)
- [YAML specification for semantic views](https://docs.snowflake.com/en/user-guide/views-semantic/semantic-view-yaml-spec)
