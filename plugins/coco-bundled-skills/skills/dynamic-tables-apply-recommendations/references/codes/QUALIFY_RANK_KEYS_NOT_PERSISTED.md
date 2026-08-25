# `QUALIFY_RANK_KEYS_NOT_PERSISTED`

Per-code handler for the `dynamic-tables-apply-recommendations` skill. The shared handler contract (field definitions, DDL composition rules, and the disclosure of unverified rewrites) lives in [../recommendation-codes.md](../recommendation-codes.md).

- `code`: `QUALIFY_RANK_KEYS_NOT_PERSISTED`
- `status`: **implemented** (with a manual fallback for the escape cases listed below)
- `customer_description`: The dynamic table's `QUALIFY ROW_NUMBER() = 1` (or `RANK() = 1`) dedup *is* at the outermost `SELECT`, but the columns/expressions referenced in its `PARTITION BY` and/or `ORDER BY` are not exposed as output columns of the dynamic table. Snowflake's optimized incremental path for the dedup (the "state-reuse" path) can only run when those keys are persisted as top-level output columns; while they are missing, every refresh falls back to a more expensive maintenance path. The fix adds the missing key expressions as output columns.
- `plan_summary`: Add the missing PARTITION BY / ORDER BY key columns to `<DT>`'s output.
- `plan_why`: Those keys must be output columns for Snowflake's fast incremental path; without them every refresh falls back to a slower one. Adds columns — downstream `SELECT *` consumers will see them.
- `detection_signature`: a **top-level** `QUALIFY ROW_NUMBER() OVER (...) = 1` / `RANK() OVER (...) = 1` dedup whose `PARTITION BY` and/or `ORDER BY` key expressions are not present in the dynamic table's projection.
  - **Detection scope is `REFRESH`** — Snowflake emits this code during an *incremental* refresh, not at `CREATE`/`ALTER`. A freshly created DT that has not yet run an incremental refresh will not show it yet.
  - **Mutually exclusive with `QUALIFY_RANK_NOT_TOP_LEVEL`.** This code fires only when the `QUALIFY ... = 1` is *already* top-level. If the QUALIFY is nested under real work (an aggregation/join/top-level `ORDER BY`), the engine emits `QUALIFY_RANK_NOT_TOP_LEVEL` instead, and you never see both at once.
  - **What does NOT trigger it:** a `SELECT *` projection (all source columns are already output, so the keys are present); a DT in `REFRESH_MODE = FULL` or `CUSTOM_INCREMENTAL`; a `QUALIFY ... = N` with `N != 1`; or a query where every partition/order key is already in the output (possibly under a different alias or an equivalent cast — the engine matches by expression equivalence, modulo redundant casts).
  - **Both `PARTITION BY` and `ORDER BY` keys are checked.** "Missing" means at least one key expression is not equivalence-present in the projection; a recommendation can name only the partition keys, only the order keys, or both.
- `ddl_transformation`:
  1. Take the original `GET_DDL` and locate the **top-level** `QUALIFY ROW_NUMBER()/RANK() OVER (...) = 1`.
  2. Read the missing key names from the recommendation's `info` string — these are the bracketed names such as `[BASE9.GRP]`, `[BASE9.VAL]`. Strip the source-table prefix to get the unqualified name (e.g. `GRP`, `VAL`). Then locate the corresponding expression **in the dynamic table's own `PARTITION BY` / `ORDER BY` clause** (the GET_DDL body) using that unqualified name as a lookup key — this gives you the expression exactly as written in the DT's scope, which is what you add as an output column. Strip `ASC`/`DESC`/`NULLS FIRST`/`NULLS LAST` sort decorations from `ORDER BY` keys — you persist the *expression*, not the sort direction. If the `info` string is the **generic fallback** (no column names inlined — the form ending in "... keys are not persisted as top-level columns in the DT" with no bracketed names), fall back to reading all `PARTITION BY` / `ORDER BY` key expressions from the GET_DDL body and filtering out those already present in the projection.
  3. For each key expression, add it to the outermost `SELECT` list **only if it is not already there**. A bare column key (`grp`) is added as `grp`. A compound/computed key (`grp + val`, `SUBSTR(k,1,5)`) is added with an explicit alias. Choose an alias that does not collide with any existing output column name (suffix a counter if needed, e.g. `..._key`, `..._key2`); a duplicate output column name makes the `CREATE OR ALTER` fail.
  4. Emit **exactly one** `CREATE OR ALTER DYNAMIC TABLE` for the original `<DT>`. **This is an in-place, single-DT rewrite — never a split.** (Contrast with the sibling `QUALIFY_RANK_NOT_TOP_LEVEL`, which can split into a producer + consumer; do not pattern-match to that recipe here.) Always `CREATE OR ALTER`, never `CREATE OR REPLACE`.
  5. Preserve the original `TARGET_LAG`, `WAREHOUSE`, `INITIALIZE`, `FROZEN WHERE`, every other setting, and inline comments. The QUALIFY clause, `FROM`, `WHERE`, and all original output columns are unchanged — the only change is the *appended* key columns.

  **This handler intentionally adds output columns**, so its result does **not** preserve the original column list. Its `SELECT` list changes, so it is **not** a structural exception — show the standard AI-accuracy disclaimer from [../recommendation-codes.md](../recommendation-codes.md) like any other body-changing rewrite, **in addition to** the schema-change confirmation gate below (the two disclose different things: one that the rewrite is unverified, the other that columns are being added).

- **Schema-change confirmation gate.** Adding output columns changes the dynamic table's schema, which downstream consumers that use `SELECT *` (or positional references) will see. Before applying, tell the customer plainly that the fix **adds output columns** and confirm that is acceptable for their downstream consumers. An explicit approval to add columns / run DDL (e.g. "adding columns is fine", "I approve running any DDL") satisfies this gate.
- **Escape cases → manual fallback (no DDL).** When the keys cannot be safely reproduced as output columns, do **not** compose DDL — present the customer guidance explaining why the fix cannot be applied automatically:
  - the `PARTITION BY` is `NULL` or a constant (nothing meaningful to persist);
  - the recommendation's `info` is the **generic** form with no inlined key names *and* the keys cannot be read unambiguously from the DT's own `GET_DDL` (e.g. masked by a secure boundary), so you cannot determine what to add;
  - any key whose expression you cannot reproduce as a valid output column.
- `example_before` (top-level QUALIFY; `grp` and `val` keys not in the output):
  ```sql
  CREATE OR ALTER DYNAMIC TABLE my_dt
    TARGET_LAG   = '5 minutes'
    WAREHOUSE    = my_wh
    REFRESH_MODE = INCREMENTAL
    AS
      SELECT id
      FROM source_events
      QUALIFY ROW_NUMBER() OVER (PARTITION BY grp ORDER BY val DESC) = 1;
  ```
- `example_after` (add the partition key `grp` and the order key `val` as output columns — in place, no split):
  ```sql
  CREATE OR ALTER DYNAMIC TABLE my_dt
    TARGET_LAG   = '5 minutes'
    WAREHOUSE    = my_wh
    REFRESH_MODE = INCREMENTAL
    AS
      SELECT id, grp, val          -- << added: the PARTITION BY / ORDER BY keys
      FROM source_events
      QUALIFY ROW_NUMBER() OVER (PARTITION BY grp ORDER BY val DESC) = 1;
  ```
- Verbatim `info` (as it appears in the `RECOMMENDATIONS` column). Snowflake inlines the missing key names by default; it falls back to the generic form when it cannot resolve them:
  - column-inlined form: *"QUALIFY ROW_NUMBER() = 1 is top-level but its PARTITION BY keys [BASE9.GRP] and ORDER BY keys [BASE9.VAL] are not persisted as top-level columns in the DT."* (only-partition and only-order variants also occur, e.g. *"... its PARTITION BY keys [BASE11.GRP] are not persisted ..."*).
  - generic fallback: *"QUALIFY RANK()/ROW_NUMBER() = 1 is top-level but its PARTITION BY / ORDER BY keys are not persisted as top-level columns in the DT."*
- Verbatim `remedy`: *"Add the PARTITION BY and ORDER BY key expressions as explicit output columns in the DT definition so the optimizer can leverage them."*
- `routes_to_on_manual`: none — for escape cases, surface guidance to the customer.
