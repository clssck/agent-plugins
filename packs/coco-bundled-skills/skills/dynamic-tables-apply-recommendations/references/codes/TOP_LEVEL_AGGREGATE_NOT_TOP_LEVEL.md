# `TOP_LEVEL_AGGREGATE_NOT_TOP_LEVEL`

Per-code handler for the `dynamic-tables-apply-recommendations` skill. The shared handler contract (field definitions, DDL composition rules, and the disclosure of unverified rewrites) lives in [../recommendation-codes.md](../recommendation-codes.md).

- `code`: `TOP_LEVEL_AGGREGATE_NOT_TOP_LEVEL`
- `status`: **implemented**
- `customer_description`: The dynamic table's query has a `GROUP BY` / aggregate (`SUM`, `COUNT`, `AVG`, `MIN`, `MAX`, etc.) that is not the top-level operation of the dynamic table — the `GROUP BY` is inside a CTE or a subquery, and the outer query performs additional work (a `QUALIFY` filter, a join, etc.) on the aggregated result. When the `GROUP BY` is the outermost operation, Snowflake can apply an optimized incremental path for the aggregation; when it is nested, that optimization is unavailable.
- `plan_summary`: Move the GROUP BY aggregate to the top level (splits `<DT>` into two tables).
- `plan_why`: The aggregate can't use the faster incremental state-reuse path while it's nested under other work — every refresh takes a slower maintenance path instead.
- `detection_signature`: A `GROUP BY` with one or more aggregate functions that is defined inside a CTE or a subquery, with the outer query doing non-trivial work on the aggregate result.
  - **What triggers it:** the `GROUP BY` is inside a CTE or inline subquery and the work above it — an outer `QUALIFY` / window filter, a join, a `WHERE` clause on the aggregate result — is something the optimizer cannot strip.
  - **What does NOT trigger it:** a *trivial pass-through wrapper* that re-selects the same columns without further processing, e.g. `SELECT a, b FROM (SELECT a, b ... GROUP BY a) sub` or `WITH cte AS (SELECT a, b ... GROUP BY a) SELECT a, b FROM cte`. The engine flattens that wrapper and treats the `GROUP BY` as already top-level, so **no recommendation is emitted**.
  - Note: an explicit `REFRESH_MODE = FULL` suppresses this code, and `REFRESH_MODE = AUTO` that resolves to FULL additionally emits `AUTO_RESOLVED_TO_FULL_REFRESH`.
- `ddl_transformation`:
  1. Take the original `GET_DDL`.
  2. Identify the CTE or subquery that carries the `GROUP BY` + aggregate and the work sitting above it in the outer query.
  3. **Split into two dynamic tables**: a *producer* DT whose body is the CTE / subquery body (the `GROUP BY` + aggregate at its outermost `SELECT` — this gets the optimized incremental path), and a *consumer* DT that keeps the original DT's name, `TARGET_LAG`, `WAREHOUSE`, `INITIALIZE`, `FROZEN WHERE` and inline comments, and selects from the producer to perform the outer work (`QUALIFY`, join, etc.). The producer DT may use `TARGET_LAG = DOWNSTREAM`. **Set `REFRESH_MODE = ADAPTIVE` on the producer DT** — this is a new DT and `ADAPTIVE` lets the engine choose `INCREMENTAL` or `REINIT` per-refresh; never use `AUTO` (it resolves the mode at compile time and may conservatively choose `FULL` permanently).
  4. Always preserve the original column list, settings, and comments unless the customer explicitly asks to change them. This handler always splits, so the consumer's `SELECT` always differs from the original — show the shared AI-accuracy disclaimer (see the shared contract) before presenting. **This always requires interactive approval — even in headless / auto-apply mode** (see the *Headless / Auto-Apply Mode* carve-out in `SKILL.md`); apply intent / `auto-accept plans: true` do not skip the presentation + approval step for this handler. **Nor does a generic approval given earlier that was never tied to this specific fix** ("I approve any DDL changes you recommend" said up front, before this split was ever described, does not count) — describe the split (what the producer/consumer will each do) and the disclaimer, and get a response to that description before executing. A clear "yes, go ahead and split it" to that description is sufficient — you don't need a further round-trip after composing the literal SQL just to re-confirm it.
- CTE `example_before` (GROUP BY inside a CTE, outer SELECT applies a QUALIFY filter):
  ```sql
  CREATE OR ALTER DYNAMIC TABLE my_dt
    TARGET_LAG = DOWNSTREAM
    WAREHOUSE  = my_wh
    REFRESH_MODE = INCREMENTAL
    AS
      WITH agg AS (
        SELECT category, SUM(amount) AS total_amount
        FROM orders
        GROUP BY category
      )
      SELECT category, total_amount
      FROM agg
      QUALIFY ROW_NUMBER() OVER (ORDER BY total_amount DESC) = 1;
  ```
- CTE `example_after` (producer DT with top-level GROUP BY + consumer DT keeping the original name):
  ```sql
  -- producer: the CTE body, now its own DT with GROUP BY at the outermost SELECT
  CREATE OR ALTER DYNAMIC TABLE my_dt_agg
    TARGET_LAG = DOWNSTREAM
    WAREHOUSE  = my_wh
    REFRESH_MODE = ADAPTIVE        -- new intermediate DT: ADAPTIVE, never AUTO
    AS
      SELECT category, SUM(amount) AS total_amount
      FROM orders
      GROUP BY category;

  -- consumer: keeps the original name + TARGET_LAG, applies the QUALIFY over the producer
  CREATE OR ALTER DYNAMIC TABLE my_dt
    TARGET_LAG = DOWNSTREAM
    WAREHOUSE  = my_wh
    REFRESH_MODE = INCREMENTAL     -- preserved from the original DT; use ADAPTIVE in case that's the original refresh_mode
    AS
      SELECT category, total_amount
      FROM my_dt_agg
      QUALIFY ROW_NUMBER() OVER (ORDER BY total_amount DESC) = 1;
  ```
- Verbatim `info` (as it appears in the `RECOMMENDATIONS` column): *"Aggregate/GROUP BY clause exists but is not at the top level of the DT definition."*
- Verbatim `remedy`: *"Restructure the DT so the GROUP BY and aggregate functions are in the outermost SELECT."*
- `routes_to_on_manual`: n/a (this code is `implemented`).
