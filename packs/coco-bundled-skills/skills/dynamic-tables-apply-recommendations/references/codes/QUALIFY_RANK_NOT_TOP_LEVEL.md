# `QUALIFY_RANK_NOT_TOP_LEVEL`

Per-code handler for the `dynamic-tables-apply-recommendations` skill. The shared handler contract (field definitions, DDL composition rules, and the disclosure of unverified rewrites) lives in [../recommendation-codes.md](../recommendation-codes.md).

- `code`: `QUALIFY_RANK_NOT_TOP_LEVEL`
- `status`: **implemented**
- `customer_description`: The dynamic table's query has a `QUALIFY ROW_NUMBER() = 1` (or `RANK() = 1`) dedup, but it is not the top-level operation of the dynamic table — an aggregation, a join, or an explicit top-level `ORDER BY` sits above it. When the `QUALIFY ... = 1` is the outermost operation, Snowflake can apply an optimized incremental path for the dedup; when other work sits above it, that optimization is unavailable.
- `plan_summary`: Move the QUALIFY clause to the top level (may split `<DT>` into two tables).
- `plan_why`: The QUALIFY clause can't use Snowflake's fast incremental path while other work sits above it — every refresh takes a slower incremental path instead.
- `detection_signature`: A `QUALIFY ROW_NUMBER() OVER (...) = 1` / `RANK() OVER (...) = 1` dedup with non-trivial work above it.
  - **What triggers it:** the work above the dedup is something the optimizer cannot strip — an outer aggregation / `GROUP BY`, a join, or an explicit top-level `ORDER BY` above the QUALIFY.
  - **What does NOT trigger it:** a *trivial pass-through wrapper* that re-selects the same columns, e.g. `SELECT a, b FROM (SELECT a, b ... QUALIFY ...)`. The engine flattens that wrapper and treats the QUALIFY as already top-level, so **no recommendation is emitted**. (Do not expect this code from a query whose only wrapper is a column passthrough.)
  - Note: an explicit `REFRESH_MODE = FULL` suppresses this code, and `REFRESH_MODE = AUTO` that resolves to FULL additionally emits `AUTO_RESOLVED_TO_FULL_REFRESH`.
- `ddl_transformation`:
  1. Take the original `GET_DDL`.
  2. Identify the inner `SELECT` that carries the `QUALIFY ... = 1` dedup and the work sitting above it.
  3. Choose the fix based on what sits above the dedup:
     - **An aggregation / `GROUP BY` / join above the dedup** (the most common trigger shape) → **split into two dynamic tables**: a *producer* DT holding the dedup with `QUALIFY ... = 1` at its outermost `SELECT` (this gets the optimized incremental path), and a *consumer* DT that keeps the original DT's name, `TARGET_LAG`, `WAREHOUSE`, `INITIALIZE`, `FROZEN WHERE` and inline comments, and performs the aggregation/join by selecting from the producer. The producer DT may use `TARGET_LAG = DOWNSTREAM`. **Set `REFRESH_MODE = ADAPTIVE` on the producer DT** — this is a new DT and `ADAPTIVE` lets the engine choose `INCREMENTAL` or `REINIT` per-refresh; never use `AUTO` (it resolves the mode at compile time and may conservatively choose `FULL` permanently). The consumer's `SELECT` differs from the original, so show the shared AI-accuracy disclaimer before presenting it. **This always requires interactive approval — even in headless / auto-apply mode**; apply intent / `auto-accept plans: true` do not skip the presentation + approval step for a split. **Nor does a generic approval given earlier that was never tied to this specific fix** — describe the split (what the producer/consumer will each do) and the disclaimer, and get a response to that description (a clear "yes, go ahead and split it" is enough; no extra round-trip needed after composing the literal SQL).
     - **Top-level `ORDER BY` only, with no `LIMIT` / `FETCH` / `OFFSET` / `TOP`** → remove the redundant top-level `ORDER BY` (a dynamic table has no inherent row order, so this is semantics-preserving) so the `QUALIFY` is the outermost operation. Single DT, rewritten in place. **Equivalent by construction — no disclaimer needed** (see the shared contract's structural exceptions).
     - **Anything else above the dedup that isn't provably a no-op** — including a top-level `ORDER BY` with a `LIMIT` / `FETCH` / `OFFSET` / `TOP` attached, since that determines *which* rows survive, not just presentation order, so dropping or restructuring it can change the result set — → treat it the same as the split case above: show the shared AI-accuracy disclaimer and require an explicit interactive approval turn, **even in headless / auto-apply mode**; apply intent / `auto-accept plans: true` do not skip the presentation + approval step. **Nor does a generic approval given earlier that was never tied to this specific fix** — describe the fix and disclaimer and get a response to that description (a clear "yes" is enough; no extra round-trip needed after composing the literal SQL).
  4. Always preserve the original column list, settings, and comments unless the customer explicitly asks to change them.
- Split `example_before` (QUALIFY dedup under an outer `GROUP BY` — the common triggering shape):
  ```sql
  CREATE OR ALTER DYNAMIC TABLE my_dt
    TARGET_LAG = DOWNSTREAM
    WAREHOUSE  = my_wh
    REFRESH_MODE = INCREMENTAL
    AS
      SELECT grp, COUNT(*) AS cnt
      FROM (
        SELECT id, grp, ts
        FROM source_events
        QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY ts DESC) = 1
      )
      GROUP BY grp;
  ```
- Split `example_after` (producer DT with top-level QUALIFY + consumer DT keeping the original name):
  ```sql
  -- producer: the dedup, now with QUALIFY at the outermost SELECT
  CREATE OR ALTER DYNAMIC TABLE my_dt_dedup
    TARGET_LAG = DOWNSTREAM
    WAREHOUSE  = my_wh
    REFRESH_MODE = ADAPTIVE        -- new intermediate DT: ADAPTIVE, never AUTO
    AS
      SELECT id, grp, ts
      FROM source_events
      QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY ts DESC) = 1;

  -- consumer: keeps the original name + TARGET_LAG, aggregates over the producer
  CREATE OR ALTER DYNAMIC TABLE my_dt
    TARGET_LAG = DOWNSTREAM
    WAREHOUSE  = my_wh
    REFRESH_MODE = INCREMENTAL     -- preserved from the original DT; use ADAPTIVE in case that's the original refresh_mode
    AS
      SELECT grp, COUNT(*) AS cnt
      FROM my_dt_dedup
      GROUP BY grp;
  ```
- Top-level-`ORDER BY` `example_before` (in-place fix):
  ```sql
  CREATE OR ALTER DYNAMIC TABLE my_dt
    TARGET_LAG = '5 minutes'
    WAREHOUSE  = my_wh
    REFRESH_MODE = INCREMENTAL
    AS
      SELECT id, grp, ts
      FROM source_events
      QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY ts DESC) = 1
      ORDER BY ts;
  ```
- Top-level-`ORDER BY` `example_after` (drop the redundant top-level `ORDER BY`):
  ```sql
  CREATE OR ALTER DYNAMIC TABLE my_dt
    TARGET_LAG = '5 minutes'
    WAREHOUSE  = my_wh
    REFRESH_MODE = INCREMENTAL
    AS
      SELECT id, grp, ts
      FROM source_events
      QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY ts DESC) = 1;
  ```
- Verbatim `info` (as it appears in the `RECOMMENDATIONS` column): *"QUALIFY RANK()/ROW_NUMBER() = 1 clause exists but is not at the top level of the DT definition."*
- Verbatim `remedy`: *"Restructure the DT so the QUALIFY RANK()/ROW_NUMBER() = 1 and PARTITION BY/ORDER BY columns are in the outermost SELECT."*
- `routes_to_on_manual`: n/a (this code is `implemented`).
