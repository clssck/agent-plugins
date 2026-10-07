# `TOP_LEVEL_AGGREGATE_EXPRESSIONS_NOT_PERSISTED`

Per-code handler for the `dynamic-tables-apply-recommendations` skill. The shared handler contract (field definitions, DDL composition rules, and the disclosure of unverified rewrites) lives in [../recommendation-codes.md](../recommendation-codes.md).

- `code`: `TOP_LEVEL_AGGREGATE_EXPRESSIONS_NOT_PERSISTED`
- `status`: **implemented** (with a manual fallback for the escape cases listed below)
- `customer_description`: The dynamic table runs incrementally, but its aggregate state-reuse optimization is unavailable: some `GROUP BY` key columns and/or aggregate expressions (e.g. `SUM(amount)`) are missing from the output, so Snowflake cannot reuse aggregate state across refreshes. Adding the missing expressions as output columns enables this optimization and is expected to reduce refresh cost.
- `plan_summary`: Add the missing GROUP BY keys / aggregate expressions to `<DT>`'s output.
- `plan_why`: They're required for Snowflake to reuse aggregate state across refreshes; without them refreshes take a slower path. Adds columns and forces a one-time full reinitialize.
- **Explaining the recommended columns (avoid confusing the customer).** The expressions the recommendation asks to persist are **not always the aggregates the customer wrote**. To maintain an aggregate incrementally, Snowflake decomposes it into the sub-aggregates ("building blocks") it needs, and it is those it wants materialized — so the list can include **derived aggregates the customer never wrote**. For example, to efficiently maintain a `SUM(x)` it may need `COUNT(x)` and `COUNT(*)` persisted (the counts let it keep the sum correct as rows are deleted/updated and detect when a group becomes empty); similarly `AVG(x)` decomposes into `SUM(x)` + `COUNT(x)`. When you present the fix, **call this out plainly**: explain that some of the columns being added (e.g. a `COUNT(*)` or `COUNT(x)` when the customer only wrote `SUM(x)`) are internal building blocks Snowflake needs to maintain the customer's *own* aggregate efficiently — they are expected and not a sign anything is wrong with the query. Do not drop an unexplained `COUNT(*)` into the recommendation as if the customer had asked for it.
- **The `info` lists at most 5 missing expressions — extras are truncated with `...`.** The GS engine caps the missing-expression list in the recommendation's `info` string at 5 entries and appends a trailing `...` when there are more. If you see that truncation (a trailing `...`, or exactly 5 listed):
  - **Tell the customer** the recommendation is only showing the first 5 missing expressions and that additional ones were omitted, so the real set is larger.
  - **Persist the expressions `info` explicitly lists** (those are authoritative). You may extend the fix to *additional* missing expressions read from `GET_DDL` **only if you are VERY confident they are correct** — e.g. `GROUP BY` keys or literal aggregate expressions written in the query and plainly absent from the projection, which you can read unambiguously from the `GET_DDL` body. **Do not guess.** In particular, some missing expressions are engine-derived building blocks (e.g. `COUNT(*)` / `COUNT(x)` needed to maintain a `SUM`/`AVG`) that do **not** appear in `GET_DDL` and cannot be reconstructed from it — never fabricate these.
  - **If in doubt, do not invent expressions.** Apply only what you are sure of, and tell the customer that the remaining required expressions weren't listed here and will be surfaced by this recommendation on the DT's **next refresh** (it is re-evaluated each refresh), so they can apply a follow-up fix then. Iterating this way — apply the listed expressions, let the next refresh report what's still missing — reaches the complete set without guessing.
- `detection_signature`: A **top-level** `GROUP BY` with one or more decomposable aggregate functions (MIN, MAX, SUM, COUNT, COUNT(*)) whose `GROUP BY` key expressions and/or the aggregate result expressions are not all present in the dynamic table's projection.
  - **Detection scope is `REFRESH`** — Snowflake emits this code during an *incremental* refresh, not at `CREATE`/`ALTER`. A freshly created DT that has not yet run an incremental refresh will not show it yet.
  - **Mutually exclusive with `TOP_LEVEL_AGGREGATE_NOT_TOP_LEVEL`.** This code fires only when the `GROUP BY` is *already* top-level. If the GROUP BY is nested inside a CTE or subquery under real outer work, the engine emits `TOP_LEVEL_AGGREGATE_NOT_TOP_LEVEL` instead, and you never see both at once.
  - **What does NOT trigger it:** a `SELECT *` projection (all source columns are already output, so the keys are present); a DT in `REFRESH_MODE = FULL` or `CUSTOM_INCREMENTAL`; a `GROUP BY` where every key and every aggregate result expression is already in the output.
  - **Missing expressions can be `GROUP BY` keys, aggregate expressions, or both.** "Missing" means at least one expression is not equivalence-present in the projection. Common cases:
    - `GROUP BY` key not in `SELECT`: e.g. `SELECT SUM(amount) AS total FROM orders GROUP BY region, category` where neither `region` nor `category` is selected.
    - An aggregate expression not directly in `SELECT`: e.g. `SELECT region * 2 AS adjusted FROM orders GROUP BY region` where `region` (the GROUP BY key) isn't a direct output column.
- `ddl_transformation`:
  1. Take the original `GET_DDL` and locate the **top-level** `GROUP BY`.
  2. Determine the missing expressions from the recommendation's `info` string (which may list them specifically) or by reading the DT's own `GROUP BY` clause and `SELECT` list from the `GET_DDL` body: identify every `GROUP BY` key expression and every aggregate expression (e.g. `SUM(amount)`, `COUNT(*)`) that appears in the `GROUP BY` / aggregate logic but is not already present as a direct output column. **If the `info` list is truncated (5-entry cap, trailing `...`), it is incomplete** — but extend beyond the listed expressions only when you can determine the extras with high confidence from `GET_DDL` (see the truncation note above); if in doubt, apply the listed expressions and let the next refresh surface the rest rather than guessing. Persisting only a subset leaves the optimization disabled until every missing expression is present, so this may take more than one round.
  3. For each missing expression, add it to the outermost `SELECT` list **only if it is not already there**. A bare column key (`region`) is added as `region`. A compound/computed key (`SUBSTR(code, 1, 3)`) or an aggregate expression (`SUM(amount)`) is added with an explicit alias. Choose an alias that does not collide with any existing output column name (suffix a counter if needed, e.g. `..._key`, `..._agg`); a duplicate output column name makes the `CREATE OR ALTER` fail.
  4. Emit **exactly one** `CREATE OR ALTER DYNAMIC TABLE` for the original `<DT>`. **This is an in-place, single-DT rewrite — never a split.** Always `CREATE OR ALTER`, never `CREATE OR REPLACE`.
  5. Preserve the original `TARGET_LAG`, `WAREHOUSE`, `INITIALIZE`, `FROZEN WHERE`, every other setting, and inline comments. The `GROUP BY` clause, `FROM`, `WHERE`, and all original output columns are unchanged — the only change is the *appended* missing expressions.

  **This handler intentionally adds output columns**, so its result does **not** preserve the original column list. Its `SELECT` list changes, so it is **not** a structural exception — show the standard AI-accuracy disclaimer from [../recommendation-codes.md](../recommendation-codes.md) like any other body-changing rewrite, **in addition to** the schema-change confirmation gate below (the two disclose different things: one that the rewrite is unverified, the other that columns are being added and a reinit is forced).

- **Schema-change confirmation gate.** Adding output columns changes the dynamic table's schema, which downstream consumers that use `SELECT *` (or positional references) will see. **Before applying**, tell the customer plainly that the fix **adds output columns** and this specific change **will force the dynamic table to fully reinitialize** on its next refresh rather than incrementally pick up the new columns, instead of only surfacing that after the fact. An explicit approval to add columns / run DDL, given anywhere in the request (e.g. "adding columns is fine", "I approve running any DDL"), satisfies this gate — the bar is that the reinitialize was *disclosed* before the DDL ran, not that the customer re-approve it in a fresh round-trip on top of an approval they already gave.
- **Escape cases → manual fallback (no DDL).** When the missing expressions cannot be safely reproduced as output columns, do **not** compose DDL — present the customer guidance explaining why the fix cannot be applied automatically:
  - every missing `GROUP BY` key is a constant or `NULL` (nothing meaningful to persist);
  - the missing expressions cannot be read unambiguously from the DT's own `GET_DDL` (e.g. masked by a secure boundary);
  - any expression you cannot reproduce as a valid output column.
- `example_before` (top-level GROUP BY; `category` key and `region` key not in the output):
  ```sql
  CREATE OR ALTER DYNAMIC TABLE my_dt
    TARGET_LAG   = '5 minutes'
    WAREHOUSE    = my_wh
    REFRESH_MODE = INCREMENTAL
    AS
      SELECT SUM(amount) AS total_amount
      FROM orders
      GROUP BY region, category;
  ```
- `example_after` (add the missing `GROUP BY` keys `region` and `category` as output columns — in place, no split):
  ```sql
  CREATE OR ALTER DYNAMIC TABLE my_dt
    TARGET_LAG   = '5 minutes'
    WAREHOUSE    = my_wh
    REFRESH_MODE = INCREMENTAL
    AS
      SELECT region, category, SUM(amount) AS total_amount   -- << added: the GROUP BY keys
      FROM orders
      GROUP BY region, category;
  ```
- Verbatim `info` (as it appears in the `RECOMMENDATIONS` column): *"A top-level aggregate can be refreshed incrementally, but its optimized state-reuse path is unavailable because some expressions it depends on are not persisted as top-level columns in the DT."* The info string may additionally list the specific missing expressions when the emitter can resolve them; if it does, use those names as the primary lookup key before falling back to the DT's `GET_DDL` body.
- Verbatim `remedy`: *"Add the listed expressions as explicit output columns in the DT definition so the optimizer can reuse aggregate state across incremental refreshes."*
- `routes_to_on_manual`: none — for escape cases, surface guidance to the customer.
