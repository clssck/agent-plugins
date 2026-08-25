# `CHANGED_BASE_TABLES_UNDER_JOIN`

Per-code handler for the `dynamic-tables-apply-recommendations` skill. The shared handler contract (field definitions, DDL composition rules, and the disclosure of unverified rewrites) lives in [../recommendation-codes.md](../recommendation-codes.md).

- `code`: `CHANGED_BASE_TABLES_UNDER_JOIN`
- `status`: **implemented** — this handler offers **two mutually-exclusive remediation options, resolved sequentially** (see the shared contract's sequential-ask design): present Option A (`ADAPTIVE`) as the default; only if the customer declines it, offer Option B (decomposition) as a fresh, standalone ask. Never present both together and ask which they want. **Exception:** when the DT is already `REFRESH_MODE = ADAPTIVE`, Option A is moot (see "Already ADAPTIVE" below) — Option B becomes the default outright, and it's the only one ever asked about.
- **Co-occurrence with `HIGH_BASE_TABLE_CHANGES` (address that code first):** if the DT *also* surfaces `HIGH_BASE_TABLE_CHANGES`, address **that** code first rather than applying a separate remediation for this one up front. The heavy base-table churn it flags is **most likely a major driver of** this under-join recommendation, so resolving it (via the `HIGH_BASE_TABLE_CHANGES` handler) will **likely** reduce or clear this one too — though not necessarily: if other join inputs are *independently* changing heavily, this under-join recommendation may persist after the base-table fix and can be revisited then. Tell the customer this. See the co-occurrence rule in `SKILL.md` Step 4.
- `customer_description`: The dynamic table joins several base tables, and too many of those join inputs are changing between refreshes (or the changing inputs are large enough that the join becomes expensive to maintain incrementally). When many inputs under a join change at once, incremental maintenance of that join can cost as much as — or more than — recomputing it, so the incremental path stops paying off.
- `plan_summary`: Reduce refresh cost from too many changing join inputs on `<DT>`.
- `plan_why` (default case — DT is not already `ADAPTIVE`): When many join inputs change at once, maintaining the join incrementally can cost as much as recomputing it; switching to ADAPTIVE lets the engine reinitialize only on the cycles where that's actually cheaper.
- `plan_why` (already-`ADAPTIVE` case): `ADAPTIVE` is already in effect, so the remaining lever is splitting the join into smaller fragments (2–3 tables each) so a churning input only invalidates the fragment it feeds.
- Whichever variant renders in the plan, that's the **default** for the sequential ask in Step 5. **For a normal "apply the recommendations" request**, don't mention the other option in the plan entry itself; Option B only comes up if the customer declines Option A (see `ddl_transformation` below). **But if the customer's own request explicitly asks what their options are** (e.g. "what are my options", "what would you recommend"), name the other option too, per the shared contract's disclosure exception — that's answering what was asked, not opening a decision gate. (The `FROZEN WHERE` additional mitigation below is unaffected either way — it's always mentioned when applicable, independent of this Option A/B pairing.)
- `detection_signature`: A **refresh-scope** signal. The DT's plan contains at least one join, and on a refresh the engine finds either (a) the number of *changed* scan inputs under a join crosses a threshold, or (b) the average change ratio under a join crosses a size-aware formula. Documentation only — detection happens at refresh time and is not something you can read off the definition (beyond confirming the DT does contain joins).
- **First, check the DT's current resolved `refresh_mode`** via `SHOW DYNAMIC TABLES LIKE '<DT>' IN SCHEMA <DB>.<SCHEMA>;` + `RESULT_SCAN` (not `GET_DDL`, which shows only the requested mode; and `refresh_mode` is not a column of `INFORMATION_SCHEMA.DYNAMIC_TABLES()`), then pick the right path below.
- `ddl_transformation`: **resolve sequentially — Option A first, Option B only if declined** (unless the DT is already `ADAPTIVE`, in which case skip straight to Option B as the only ask). They are mutually exclusive for a given DT, so at most one is ever composed.

  **Option A — switch to `REFRESH_MODE = ADAPTIVE` (settings-only, in place).**
  1. Take the original `GET_DDL`.
  2. Change **only** `REFRESH_MODE` to `ADAPTIVE`; leave the `AS <query>` body, column list, `TARGET_LAG`, `WAREHOUSE`, `INITIALIZE`, comments and all other settings unchanged.
  3. With `ADAPTIVE`, Snowflake reinitializes (full recompute) for the cycles where the join inputs change too much to maintain incrementally, and stays incremental otherwise.
  4. The `SELECT` is unchanged, so there is nothing to disclaim — say so instead of showing the disclaimer. Single in-place `CREATE OR ALTER`.

  **Option B — decompose the DT into smaller join fragments (2–3 joins each).**
  1. A single DT that joins many base tables forces the engine to maintain one large join graph. Splitting it into a chain of producer DTs that each join only **2–3 tables**, feeding a final consumer DT that keeps the original `<DT>`'s name and contract, lets the engine maintain each smaller join independently — a churning input then only invalidates the fragment it feeds, not the whole graph.
  2. Group the joins so each intermediate (producer) DT performs at most 2–3 joins. Producer DTs can use `TARGET_LAG = DOWNSTREAM` and the same `WAREHOUSE`; the final consumer DT **keeps the original name, `TARGET_LAG`, `WAREHOUSE`, `INITIALIZE`, `FROZEN WHERE`, comments and column contract**.
  3. This emits **multiple `CREATE OR ALTER DYNAMIC TABLE` statements — one per resulting DT** (producers before the consumer). Never `CREATE OR REPLACE` — `CREATE OR ALTER` fully supports rewriting the query body (the `AS <query>`), which is exactly what redirecting the consumer to read from the new producer(s) is; the fact that the `SELECT` itself changes, not just a setting, is not a reason to reach for `CREATE OR REPLACE`.
  4. The consumer's `SELECT` differs from the original, so show the shared AI-accuracy disclaimer before presenting it. **This always requires interactive approval — even in headless / auto-apply mode** (see the *Headless / Auto-Apply Mode* carve-out in `SKILL.md`); apply intent / `auto-accept plans: true` do not skip the presentation + approval step for Option B. **Nor does a generic approval given earlier that was never tied to this specific fix** — describe the decomposition (the fragments and how they connect) and the disclaimer, and get a response to that description (a clear "yes, go ahead and split it" is enough; no extra round-trip needed after composing the literal SQL).

  **Additional mitigation to call out — `FROZEN WHERE` over a no-longer-changing slice.** Separately from Options A/B, always mention this when it could apply: **if the customer knows a portion of the data is not expected to change anymore** (e.g. closed historical periods), they can add a `FROZEN WHERE` clause marking that slice immutable, so the engine stops tracking and re-scanning it for changes under the join — shrinking the changed-input volume that triggers this recommendation. This is an optional callout, not a substitute for the customer's Option A/B choice. If the customer wants to pursue it (either standalone or combined with Option A), follow [../frozen-where-guidance.md](../frozen-where-guidance.md) to identify the right columns and predicate, then compose the DDL: use `ALTER DYNAMIC TABLE ... SET FROZEN WHERE (...)` when this is the only change, or fold `FROZEN WHERE (...)` into the `CREATE OR ALTER` when Option A is also being applied.

- Accompanying guidance (**mandatory — always include, in every case: whichever option is chosen, and even when the DT is already ADAPTIVE and there is no DDL to apply**): like `HIGH_BASE_TABLE_CHANGES`, the engine also points at the **source** of the changes feeding the joins. The remediations mitigate refresh cost; none addresses *why* the join inputs churn. You **must** call out that the customer should investigate the source of the changes feeding the JOIN(s) — e.g. the upstream load pattern of the changing inputs.
- **Already ADAPTIVE** (the DT's `REFRESH_MODE` is already `ADAPTIVE`): do **not** propose or apply Option A — `ADAPTIVE` is already in effect (the engine already reinitializes when join inputs become expensive; the recommendation's `info` is typically prefixed *"Dynamic Table was reinitialized. Reason: "*). Present **only** Option B (decomposition) as the actionable choice — the customer may take it or decline — and always include the mandatory investigate-the-source guidance above. Never emit a `CREATE OR ALTER` that merely re-states `ADAPTIVE`.
- Option A `example_before` (one DT joining four base tables, explicit `INCREMENTAL`):
  ```sql
  CREATE OR ALTER DYNAMIC TABLE my_dt
    TARGET_LAG   = '10 minutes'
    WAREHOUSE    = my_wh
    REFRESH_MODE = INCREMENTAL
    AS
      SELECT o.order_id, c.name, p.product_name, s.region
      FROM orders o
      JOIN customers c ON o.customer_id = c.id
      JOIN products  p ON o.product_id  = p.id
      JOIN stores    s ON o.store_id    = s.id;
  ```
- Option A `example_after` (only `REFRESH_MODE` changes):
  ```sql
  CREATE OR ALTER DYNAMIC TABLE my_dt
    TARGET_LAG   = '10 minutes'
    WAREHOUSE    = my_wh
    REFRESH_MODE = ADAPTIVE
    AS
      SELECT o.order_id, c.name, p.product_name, s.region
      FROM orders o
      JOIN customers c ON o.customer_id = c.id
      JOIN products  p ON o.product_id  = p.id
      JOIN stores    s ON o.store_id    = s.id;
  ```
- Option B `example_after` (decomposed into a 2-join producer + a consumer keeping the original name):
  ```sql
  -- producer: joins orders to its two most-churned inputs
  CREATE OR ALTER DYNAMIC TABLE my_dt_orders_enriched
    TARGET_LAG   = DOWNSTREAM
    WAREHOUSE    = my_wh
    REFRESH_MODE = ADAPTIVE
    AS
      SELECT o.order_id, o.product_id, o.store_id, c.name
      FROM orders o
      JOIN customers c ON o.customer_id = c.id;

  -- consumer: keeps the original name, TARGET_LAG and column contract;
  -- finishes the remaining joins over the smaller producer
  CREATE OR ALTER DYNAMIC TABLE my_dt
    TARGET_LAG   = '10 minutes'
    WAREHOUSE    = my_wh
    REFRESH_MODE = INCREMENTAL
    AS
      SELECT e.order_id, e.name, p.product_name, s.region
      FROM my_dt_orders_enriched e
      JOIN products p ON e.product_id = p.id
      JOIN stores   s ON e.store_id   = s.id;
  ```
- Verbatim `info` (as it appears in the `RECOMMENDATIONS` column; exact wording depends on which sub-rule fired): *"`<N>` non-empty joins detected in the Dynamic Table"* (too many changed inputs under a join) or *"`<N>` expensive joins detected in the Dynamic Table"* (high average change ratio under a join). When an automatic reinitialization was already applied, the message is prefixed with *"Dynamic Table was reinitialized. Reason: "*.
- Verbatim `remedy`: *"Investigate the source of the changes feeding the JOIN(s) in the Dynamic Table. Consider REFRESH_MODE = ADAPTIVE so the system can reinitialize when JOIN inputs become expensive."*
- `routes_to_on_manual`: n/a (this code is `implemented`; if the customer wants a deeper hand-tuned decomposition than the 2–3-join fragmenting above, route to `../dynamic-tables/optimize/SKILL.md`).
