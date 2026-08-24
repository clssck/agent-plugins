---
name: ai-metadata
description: AI metadata reference — module_custom_instructions (sql_generation style hints, question_categorization topic scoping) and verified_queries (pre-approved SQL) for steering Cortex Analyst.
parent_skill: sv-modeling-patterns
---

# AI Metadata

## How it works

Three SV-level metadata blocks steer Cortex Analyst behavior on top of the model definition:

1. **`module_custom_instructions.sql_generation`** — free-text instructions injected into every SQL generation call for this SV. Encodes formatting preferences (`round to 2 decimal places`), implicit business rules (`never include refunded orders`), or disambiguation hints (`use customer_name for customer breakdowns`).
2. **`module_custom_instructions.question_categorization`** — instructions for the intent-classification step *before* SQL generation. Defines which topics the SV handles; can reject or redirect off-topic questions.
3. **`verified_queries`** — pre-approved SQL paired with a natural-language question. When a user's question closely matches, the engine uses this SQL **verbatim**, bypassing generation. Use the `SEMANTIC_VIEW(...)` SQL form (works in both AUTO and REQUIRE modes) over physical SQL (AUTO only).

## Snippet

```yaml
name: ORDERS_AI_SV

# tables, relationships, dimensions, metrics defined as usual ...

# Free-text steering for the SQL-generation step
module_custom_instructions:
  sql_generation: |
    Always round monetary values to 2 decimal places.
    When asked about revenue, never include orders with status = 'refunded'.
    Use customer_name for customer-level breakdowns.
  question_categorization: |
    Answer questions about revenue, orders, and customers.
    Politely decline questions about individual customer PII or internal pricing margins.

# Pre-approved SQL: SEMANTIC_VIEW() form works in both AUTO and REQUIRE modes
verified_queries:
  - name: order_count_by_customer
    question: How many orders does each customer have?
    verified_by: jklahr
    verified_at: 1750000000
    sql: >
      SELECT * FROM SEMANTIC_VIEW(TARGET_DB.TARGET_SCHEMA.ORDERS_AI_SV
        METRICS ai_orders.order_count
        DIMENSIONS ai_customers.customer_name)
      ORDER BY order_count DESC
  - name: revenue_by_region
    question: What is the revenue by region?
    verified_by: jklahr
    verified_at: 1750000000
    sql: >
      SELECT * FROM SEMANTIC_VIEW(TARGET_DB.TARGET_SCHEMA.ORDERS_AI_SV
        METRICS ai_orders.total_revenue
        DIMENSIONS ai_customers.region)
      ORDER BY total_revenue DESC
```

## Gotchas

- **Use `SEMANTIC_VIEW(...)` SQL in verified queries, not physical SQL.** Physical SQL (`SELECT col FROM table WHERE...`) only works in AUTO mode. `SEMANTIC_VIEW(...)` works in both AUTO and REQUIRE modes — always preferred.
- **`verified_at` is a Unix timestamp** (seconds), not an ISO date.
- **`question_categorization` is conservative — it can suppress queries.** Test with representative user phrasings before deploying — overly strict scoping makes the SV feel broken to users.
- **Question text should be specific.** "How many orders" is too generic; "How many orders does each customer have?" matches the agent's classification more reliably.

## Docs

- [Custom instructions in Cortex Analyst](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst/custom-instructions)
- [YAML specification for semantic views — verified_queries](https://docs.snowflake.com/en/user-guide/views-semantic/semantic-view-yaml-spec)
