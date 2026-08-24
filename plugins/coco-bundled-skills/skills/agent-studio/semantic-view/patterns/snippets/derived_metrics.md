---
name: derived-metrics
description: Derived metric reference — cross-entity totals and ratios (e.g. total = store + web + catalog; store_pct = store / total) defined at the SV level without table prefix.
parent_skill: sv-modeling-patterns
---

# Derived Metrics

## How it works

A derived metric combines other metrics — typically across multiple entities — into a new metric that lives at the SV level (not scoped to a single entity). Examples: `total_revenue = store + web + catalog`; `store_pct = store / total`.

Two rules:

1. **Cross-table derived metrics live at the top-level `metrics:` block of the YAML** — not nested under any `tables[].metrics`.
2. **Constituent references on the right side keep their entity prefix** — `store_sales.store_revenue + web_sales.web_revenue`.

A derived metric can reference other derived metrics, so `store_pct: store_sales.store_revenue / total_revenue` works.

## Snippet

```yaml
tables:
  - name: store_sales
    metrics:
      - name: store_revenue
        expr: SUM(REVENUE)
  - name: web_sales
    metrics:
      - name: web_revenue
        expr: SUM(REVENUE)
  - name: catalog_sales
    metrics:
      - name: catalog_revenue
        expr: SUM(REVENUE)

# Cross-table derived metrics live HERE (top-level), not nested under any table.
metrics:
  - name: total_revenue
    synonyms: [total sales, all channel revenue, combined revenue]
    expr: store_sales.store_revenue + web_sales.web_revenue + catalog_sales.catalog_revenue

  - name: store_pct_of_total
    synonyms: [store share, store contribution, "% from store"]
    expr: store_sales.store_revenue / total_revenue
```

## Gotchas

- **Top-level `metrics:` placement is required for cross-table derivations.** Nesting a cross-table derived metric under one of the `tables[].metrics` arrays will fail or behave unexpectedly. Only single-table aggregations belong in `tables[].metrics`.
- **Division returns a decimal (0.0–1.0), not a percent.** Multiply × 100 in standard SQL wrapping for display as `%`.
- **All referenced metrics must be reachable via the same set of relationships/dimensions in the query.** If `store_sales` and `web_sales` only join through `dim_date`, you can't break the derived `total_revenue` down by a dimension that only one of them has.
- **Derived metrics are additive by default — they do not support `non_additive_dimensions`.** If you need semi-additive behavior, define it on the constituent metric and let the derived metric inherit.

## Docs

- [Defining derived metrics](https://docs.snowflake.com/en/user-guide/views-semantic/sql#defining-derived-metrics)
- [YAML specification for semantic views](https://docs.snowflake.com/en/user-guide/views-semantic/semantic-view-yaml-spec)
