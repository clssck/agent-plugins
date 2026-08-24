---
name: sv-diagnostics
description: SV diagnostics reference — six structural failure modes (ambiguous path, fan trap, missing relationship, duplicate names, wrong cardinality, semi-additive forgotten) with exact errors and broken/fixed YAML pairs.
parent_skill: sv-modeling-patterns
---

# SV Diagnostics

## How it works

Six common SV failure modes. Some surface as deploy-time errors; some only appear at query time; some never error and silently return wrong numbers. Each entry below names the symptom, the exact error message (if any), the root cause, and a YAML-form broken/fixed pair.

## Snippet

### 1. Ambiguous Path Relationship

**Error (query time, on grouping by ambiguous dim):**
```
Invalid dimension specified: Multi-path relationship between the dimension
entity 'DATE_DIM' and the base metric or dimension entity 'DEALS' is not supported.
```

**Cause:** Fact has two FKs to the same dimension (e.g. `CREATED_DATE` + `CLOSE_DATE` both → `DIM_DATE`); no disambiguation.

**Fix:** Add `using_relationships: [<name>]` to every metric.

```yaml
# BROKEN: no using_relationships — ambiguous at query time
- name: total_amount
  expr: SUM(AMOUNT)

# FIXED: each metric owns its date path
- name: total_amount_created
  expr: SUM(AMOUNT)
  using_relationships: [deals_to_created_date]
- name: total_amount_closed
  expr: SUM(AMOUNT)
  using_relationships: [deals_to_close_date]
```

See `multi_path_metrics.md` for the full pattern.

---

### 2. Fan Trap

**Error (query time):**
```
Invalid dimension specified: The dimension entity 'PRODUCTS' must be related to
and have an equal or lower level of granularity compared to the base metric or
dimension entity 'DEALS'.
```

**Cause:** Metric is at a coarser grain than the dimension it's being grouped by. Revenue lives at `DEALS` header (one row per deal); `DIM_PRODUCT` is only reachable via `DEAL_ITEMS` (many rows per deal). Engine refuses to fan-out.

**Distinguishing from #3:** Same error. In a fan trap the relationship exists but at the wrong grain; in #3 it's missing entirely.

**Fix:** Move the metric to the table that directly joins the dimension.

```yaml
# BROKEN: metric at DEALS grain, dim only reachable via DEAL_ITEMS
- name: deals
  metrics:
    - { name: total_amount, expr: SUM(AMOUNT) }   # can't group by products.category

# FIXED: metric at DEAL_ITEMS grain — same level as DIM_PRODUCT
- name: deal_items
  metrics:
    - { name: total_revenue, expr: SUM(LINE_AMOUNT) }
```

---

### 3. Table With No Relationship

**Error (query time, same as #2):**
```
Invalid dimension specified: The dimension entity 'DIM_REGION' must be related
to and have an equal or lower level of granularity ...
```

**Cause:** Table listed in `tables:` but no `relationships:` entry connects it.

**Distinguishing from #2:** Search `relationships:` for the orphaned table's name — it won't appear on either side.

**Fix:** Add the missing relationship, or remove the orphaned table.

```yaml
# BROKEN: no relationship for dim_region
relationships:
  - { name: deals_to_rep, left_table: deals, right_table: rep_dim,
      relationship_columns: [{ left_column: REP_ID, right_column: REP_ID }] }

# FIXED: add the missing link
relationships:
  - { name: deals_to_rep, left_table: deals, right_table: rep_dim,
      relationship_columns: [{ left_column: REP_ID, right_column: REP_ID }] }
  - { name: rep_to_region, left_table: rep_dim, right_table: dim_region,
      relationship_columns: [{ left_column: REGION, right_column: REGION_CODE }] }
```

---

### 4. Duplicate Names / Overlapping Synonyms

**4a. Duplicate logical name (deploy-time):**
```
SQL compilation error: invalid identifier '<name>'
```
Two dimensions or metrics share the same logical name. Fix: entity-scope the names.

```yaml
# BROKEN
- name: rep_dim
  dimensions: [{ name: segment, expr: REGION,   data_type: VARCHAR }]   # logical: "segment" — duplicate
- name: products
  dimensions: [{ name: segment, expr: CATEGORY, data_type: VARCHAR }]   # logical: "segment" — duplicate → deploy error

# FIXED
- name: rep_dim
  dimensions: [{ name: rep_segment,     expr: REGION,   data_type: VARCHAR }]
- name: products
  dimensions: [{ name: product_segment, expr: CATEGORY, data_type: VARCHAR }]
```

**4b. Overlapping synonyms (Cortex Analyst refuses NL queries):**
```
The term 'segment' is ambiguous. It could refer to 'product_segment' or
'rep_segment'. Could you clarify which segment you mean?
```
Fix: never share high-value terms (`revenue`, `total`, `count`, `segment`, `area`) across multiple definitions.

---

### 5. Wrong Relationship Direction / Wrong Cardinality

**5a. Reversed direction (deploy-time):**
```
The referenced key in the relationship 'REP_DIM REFERENCES DEALS' must be the
primary or unique key of the referenced entity.
```
Cause: dimension is on the `left_table` (many side) but the right side doesn't have a declared `primary_key`. The engine enforces that the right side's key is a declared `primary_key` / `unique_keys`.

**Fix:** Always model `left_table = many side`, `right_table = one side` (with the PK).

**5b. Wrong cardinality / lying about the PK (silent wrong results — most dangerous):**

No error. SV deploys. Most queries return correct numbers. Header-level metrics grouped by fine-grain dimensions return silently inflated numbers because the engine trusts the wrong PK declaration and disables its fan trap guard.

```yaml
# WRONG: declaring the FK column as PK (DEAL_ID is not unique in DEAL_ITEMS)
- name: deal_items
  primary_key: { columns: [DEAL_ID] }

# CORRECT: declare the actually-unique column
- name: deal_items
  primary_key: { columns: [ITEM_ID] }
```

**Detection:** compare SV metric total against raw `SELECT SUM(...)` on the table — they must match when grouping across all rows.

---

### 6. Forgotten Semi-Additive Behavior

No error. No query failure. Just wrong answers. Ask for every fact / metric:

> Does this column represent a **snapshot** (account balance, headcount, inventory, open pipeline) or a **flow** (revenue, quantity sold)?

Snapshot + `SUM` across time = wrong (n× too large). Fix with `non_additive_dimensions`. See `semi_additive_metric.md`.

---

### Diagnostic Cheat Sheet

| Error / Symptom | Cause | How to tell apart | Fix |
|---|---|---|---|
| "Multi-path relationship not supported" | #1 ambiguous path | Check `relationships:` for two paths to same target | Add `using_relationships` to each metric |
| "Dimension must be equal or lower granularity" | #2 fan trap OR #3 missing relationship | Is the table connected at all? | Move metric to bridge grain (#2) or add relationship (#3) |
| "invalid identifier" at deploy | #4a duplicate logical name | Scan dimensions/metrics for repeats | Entity-scope all names |
| CA refuses with "ambiguous" explanation | #4b overlapping synonyms | Scan `synonyms:` for shared terms | Unique synonym sets per definition |
| "Referenced key must be PK/UK" at deploy | #5a reversed direction | Right side is the many-side | Flip: many-side is `left_table`, PK side is `right_table` |
| **No error, silently inflated numbers** | #5b wrong PK | Compare SV total to raw SQL total | Declare `primary_key` on the actually-unique column |
| **No error, subtly wrong over time** | #6 snapshot using SUM | Snapshot or flow? | `non_additive_dimensions` |

## Gotchas

- **Use `SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML(..., TRUE)` as a dry-run** before the real deploy — it validates structure without creating the SV. Catches deploy-time errors early.
- **`DESCRIBE` is not a validator.** It shows structure after deployment but cannot detect fan traps, ambiguous paths, or cardinality lies.
- **Snowflake does not enforce PK uniqueness.** The SV engine trusts whatever `primary_key` you declare. A wrong PK declaration deploys silently and disables cardinality guards. Always verify PK declarations against actual data.
- **Overlapping synonyms cannot be fixed at query time.** Once deployed, CA will refuse those questions until the SV is altered.

## Docs

- [Semantic view overview](https://docs.snowflake.com/en/user-guide/views-semantic/overview)
- [YAML specification for semantic views](https://docs.snowflake.com/en/user-guide/views-semantic/semantic-view-yaml-spec)
- [Cortex Analyst — semantic model spec](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst/semantic-model-spec)
