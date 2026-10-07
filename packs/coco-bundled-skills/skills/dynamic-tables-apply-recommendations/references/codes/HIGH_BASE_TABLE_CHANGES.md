# `HIGH_BASE_TABLE_CHANGES`

Per-code handler for the `dynamic-tables-apply-recommendations` skill. The shared handler contract (field definitions, DDL composition rules, and the disclosure of unverified rewrites) lives in [../recommendation-codes.md](../recommendation-codes.md).

- `code`: `HIGH_BASE_TABLE_CHANGES`
- `status`: **implemented**, offering **more than one remediation, resolved sequentially — never as an upfront menu** (see the shared contract's sequential-ask design): switch the DT to `REFRESH_MODE = ADAPTIVE`, and/or add a `PRIMARY KEY ... RELY` to the base table. These two are **combinable**, not mutually exclusive (see "Both Option 1 + Option 2" below). A pre-check on overwrite frequency decides which one is offered as the default. The primary-key option only takes effect once the dynamic table is **recreated** so its plan recompiles against the new key (see Option 2 below).
- `customer_description`: One or more of the dynamic table's base tables had a large number of changed rows (inserts + deletes) since the last refresh, relative to their size. When the changed slice approaches the size of the table, an incremental refresh does roughly the same work as a full recompute but with extra change-tracking overhead, so the incremental path stops paying off for those cycles.
- `plan_summary`: Reduce refresh cost from heavy base-table churn on `<base>`.
- `plan_why` (default case — no majority-overwrite pattern): Large row swings make incremental refresh cost as much as a full recompute; switching to ADAPTIVE lets the engine auto full-recompute only when it's actually cheaper.
- `plan_why` (majority-overwrite case — Step 0 below establishes `<base>` is fully overwritten most refreshes): ADAPTIVE would reinitialize every cycle here anyway, so it isn't worth it; a `PRIMARY KEY ... RELY` on `<base>` — once verified genuinely unique — lets incremental refresh skip the rows that didn't actually change, and only takes effect after `<DT>` is recreated.
- Whichever variant renders in the plan, that's the **default** for the sequential ask in Step 5. **For a normal "apply the recommendations" request**, don't mention the other option (or Option 3 / `FROZEN WHERE`) in the plan entry itself — they come up afterward per the Remediation section below, only if needed. **But if the customer's own request explicitly asks what their options are** (e.g. "what are my options", "what would you recommend"), name the other viable option(s) — including `FROZEN WHERE` when applicable — in a short trailing clause, per the shared contract's disclosure exception; that's answering what was asked, not opening a decision gate.
- **Co-occurrence with `CHANGED_BASE_TABLES_UNDER_JOIN` (address this code first):** if the DT *also* surfaces `CHANGED_BASE_TABLES_UNDER_JOIN`, handle this code **first** rather than applying a separate join remediation up front. The same heavy base-table churn is **most likely a major driver of** the join-maintenance cost, so addressing it here (and investigating its source) will **likely** reduce or clear the under-join recommendation too — though this is not guaranteed: if other join inputs are *independently* churning, the under-join recommendation may persist and can be revisited afterward. Tell the customer the under-join recommendation is most likely driven largely by these same high base-table changes, so it makes sense to address those first. See the co-occurrence rule in `SKILL.md` Step 4.
- `detection_signature`: A **refresh-scope** signal (not a query-shape signal): the engine emits this on an `INCREMENTAL` or `ADAPTIVE` dynamic table when, on a refresh, the estimated changed rows of a base table cross both an absolute row-count threshold and a fraction-of-table threshold. Documentation only — the engine performs the actual detection during refresh; it does not depend on anything you can read from the DT's definition.

## Step 0 — overwrite-frequency pre-check (do this BEFORE proposing remediation)

Identify the churning base table (from the recommendation's `info`, which usually names `Table <TABLE>`; if redacted, fall back to the DT's base tables in the `GET_DDL`). Then determine **whether the MAJORITY of the DT's refreshes fully overwrite that base table** — i.e. the whole table is replaced most cycles, via `INSERT OVERWRITE`, or `TRUNCATE` / unconditional `DELETE` (no `WHERE`) followed by `INSERT`.

**This is a "majority of refreshes" judgment, not a single-refresh one.** A *single* large-change refresh (e.g. a one-off bulk purge or backfill) is **NOT** a full-rewrite pattern — do not treat one big delete as an overwrite pattern. The pre-check only decides whether `REFRESH_MODE = ADAPTIVE` is worth offering; the primary-key option (below) helps regardless.

**How to determine the overwrite frequency.** Combine these signals (change counts are only meaningful relative to the table's total — never read them in isolation, and **do not** use added/removed partition counts as an absolute fraction of the table):

1. **The recommendation `info` gives the magnitude for the triggering refresh.** It reads *"...(`<N>` inserts and `<N>` deletes) since the last refresh (previous count: `<M>`)"*. `previous count: <M>` is the base table's total row count at the prior refresh — the denominator. If `deletes ≈ M` (and/or `inserts ≈ M`), that one refresh replaced ~the whole table. (This alone is only one refresh — not yet a "majority" pattern.)
2. **Cross-refresh consistency from `DYNAMIC_TABLE_REFRESH_HISTORY`** establishes the *majority*. `FLATTEN(inputs_with_changed_data)` for the churning base table across recent refreshes and compare each refresh's `numAddedPartitions` / `numRemovedPartitions` and `numDeletedRows` to the triggering refresh's. If a **similar or higher** churn appears in the **majority** of refreshes, assume overwrite behavior. (Validated signature: a full reload — `DELETE`-all+`INSERT`, `TRUNCATE`+`INSERT`, or `INSERT OVERWRITE`, all identical — removes ≈ the table's entire partition count and shows `numDeletedRows ≈ numInsertedRows ≈ total` every refresh, whereas an upsert touches very few partitions with low `numDeletedRows`.) Example:

   ```sql
   SELECT rh.refresh_start_time, rh.refresh_action,
          f.value:statistics:"numAddedPartitions"::int   AS added_partitions,
          f.value:statistics:"numRemovedPartitions"::int AS removed_partitions,
          f.value:statistics:"numDeletedRows"::int        AS deleted_rows,
          f.value:statistics:"numInsertedRows"::int       AS inserted_rows
   FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(NAME => '<DB>.<SCHEMA>.<DT>')) rh,
        LATERAL FLATTEN(input => rh.inputs_with_changed_data) f
   WHERE f.value:name::string = '<fully-qualified base table>'
     AND rh.refresh_trigger <> 'CREATION'
   ORDER BY rh.refresh_start_time DESC;
   ```
   Note: `refresh_action` typically stays `INCREMENTAL` even for a full `DELETE`+`INSERT` reload, so judge by the partition/row stats, not by `refresh_action`. Partition counts are reliable only as a **relative** measure across refreshes (consistently large vs. the triggering refresh), not as an absolute fraction of the table.
3. **Confirm with the customer.** The metadata is corroboration; the loader often runs under another role you cannot see. Ask: "Is `<base>` fully reloaded *each cycle* (INSERT OVERWRITE, or TRUNCATE / DELETE-all + INSERT), or incrementally updated (MERGE / targeted DML)?" Treat the answer as authoritative for the majority judgment.

**If you cannot establish a majority-overwrite pattern, assume there is none** (the common case): offer `ADAPTIVE` normally. Only suppress `ADAPTIVE` when the majority-overwrite pattern is established.

## Remediation — resolve Option 1 and Option 2 sequentially, as independent add-ons

These two options are **combinable**, so Step 5 asks about them one at a time rather than presenting a menu: settle the default named in the Step 4 plan entry first (accept or decline), then separately ask about the other as an *additional* fix — accepting or declining one says nothing about the other. Adding a reliable primary key helps in essentially all cases; switching to `ADAPTIVE` helps *unless* the base is overwritten on the majority of refreshes.

**Default order:** Option 1 (`ADAPTIVE`) is the default unless Step 0 establishes majority-overwrite, in which case Option 2 (primary key) is the default and Option 1 is not offered at all (see Option 1's own note below). Whichever is default, ask about the other as the combinable add-on afterward — and **default to mentioning it rather than applying it** unless the customer specifically agrees to the add-on too; "helps in essentially all cases" is a reason to *offer* it, not license to add an unprompted base-table `PRIMARY KEY` + `CREATE OR REPLACE` recreate on the strength of a blanket DDL approval that was really about the default fix. See the shared caution in `SKILL.md` Step 5.

- **Option 1 — `REFRESH_MODE = ADAPTIVE`** (settings-only `CREATE OR ALTER` on the DT).
  - Change **only** `REFRESH_MODE` to `ADAPTIVE`; preserve the `AS <query>` body, column list, `TARGET_LAG`, `WAREHOUSE`, `INITIALIZE`, `FROZEN WHERE` (legacy DTs may show the old `IMMUTABLE WHERE` keyword — preserve whichever the DT already uses), comments and every other setting. The `SELECT` is unchanged, so there is nothing to disclaim — say the body is unchanged instead of showing the disclaimer.
  - **Do NOT offer Option 1 when the majority of refreshes fully overwrite the base** (Step 0) — `ADAPTIVE` would reinitialize every cycle (≡ `FULL`), no benefit. Say so explicitly and steer to Option 2.
  - **If the DT is already `ADAPTIVE`**, it is a no-op — do not propose it (the recommendation `info` is typically prefixed *"Dynamic Table was reinitialized. Reason: "*).
- **Option 2 — `ALTER TABLE <base> ADD PRIMARY KEY (<pk_cols>) RELY`** (base-table change; only when `<base>` is a real TABLE).
  - A reliable primary key lets incremental refresh match rows across loads by key and skip the ones whose values did not change — this **helps in general**, and is the **primary** fix when the base is fully reloaded each cycle (it is what lets the engine avoid reprocessing an overwrite).
  - **Only valid when `<base>` is an actual table.** If the churning "base" is itself a dynamic table or a view, you cannot add a primary key — drop this option (offer Option 1 / Option 3 + the investigate guidance).
  - Follow the uniqueness-validation procedure in [`../primary-key-rely.md`](../primary-key-rely.md) — gather the PK column(s) from the customer, ask permission to run the check against `<base>`, and only proceed if uniqueness is confirmed.
  - **You MUST recreate the dynamic table afterward, or the key does nothing.** Adding a primary key to the base table does **not** retroactively affect an already-existing dynamic table. Snowflake binds base-table constraints into the DT's compiled plan **at DT-creation time**, so a newly-added `RELY` key stays invisible to the running DT until the DT is reinitialized — the recommendation will simply persist. A bare `CREATE OR ALTER` with an **unchanged** definition is a **no-op** here and does **not** trigger reinitialization, so it will not pick up the key. After the `ALTER TABLE ... ADD PRIMARY KEY ... RELY`, recreate the DT with `CREATE OR REPLACE DYNAMIC TABLE <DT> ...` re-issuing its **exact current definition** (preserve `TARGET_LAG`, `WAREHOUSE`, `REFRESH_MODE`, `INITIALIZE`, `FROZEN WHERE`, comments, and every other setting) so the plan recompiles against the base table's new metadata and adopts the key.
    - **This is the one place the skill uses `CREATE OR REPLACE` instead of `CREATE OR ALTER`** — only for adopting a newly-added base-table primary key. State the trade-offs explicitly: `CREATE OR REPLACE` rebuilds the DT from scratch (one full recompute), resets its refresh history, re-establishes grants/dependencies, and forces downstream dynamic tables to recompute on their next cycle. This cost is unavoidable — an in-place `CREATE OR ALTER` will not pick up the new key.
    - **Ordering:** (1) run the uniqueness check (from [`../primary-key-rely.md`](../primary-key-rely.md)) and confirm it passes, (2) add the primary key to the base table, (3) recreate the DT — the recompile must see the constraint already in place.
    - **Exception — combining with a reinit-triggering DT change:** if the customer is *also* applying a DT change that itself triggers reinitialization in the same operation (in practice the Option 1 `REFRESH_MODE = ADAPTIVE` switch, available only when the base is **not** majority-overwrite), that `CREATE OR ALTER` already recompiles the plan and adopts the new key — no separate `CREATE OR REPLACE` is needed (still add the PK to the base first). In the majority-overwrite case (the primary PK scenario) `ADAPTIVE` is ruled out, so the explicit `CREATE OR REPLACE` recreate **is** required.
- **Both Option 1 + Option 2** is valid and often the best outcome (adaptivity *and* row-level filtering) — except when majority-overwrite rules out Option 1.
- **Option 3 (alternative) — `FROZEN WHERE`** for a portion of the data the customer knows no longer changes, so the engine stops re-scanning that immutable slice each refresh. Follow [../frozen-where-guidance.md](../frozen-where-guidance.md) to identify the right columns and predicate, then compose the DDL: use `ALTER DYNAMIC TABLE ... SET FROZEN WHERE (...)` when this is the only change, or fold `FROZEN WHERE (...)` into the `CREATE OR ALTER` when Option 1 is also being applied.

Compose only the DDL for the option(s) the customer selects. Use `CREATE OR ALTER` for DT changes, **never `CREATE OR REPLACE`** — with the single exception above: recreating the DT via `CREATE OR REPLACE DYNAMIC TABLE` to adopt a newly-added base-table primary key (Option 2 applied on its own).

## Mandatory guidance (always include in your wrap-up message — whichever option is chosen, or none)

The recommendation points at the **source** of the changes. None of these remediations addresses *why* the base table is churning so heavily. Your customer-facing wrap-up **must** state both of the following in plain language (this is separate from, and in addition to, any pointer to the `optimize/` workflow):

1. **Investigate the source of the large base-table changes** — explicitly tell the customer to *investigate / look into* the **source / upstream load pattern** driving the churn (full-table reloads, large periodic deletes/re-inserts, or an unbounded backfill) and whether it can be made more incremental at the source. Phrase it as investigating *why the base table changes so much*, not as deeper tuning of the dynamic table itself.
2. **(Whenever the primary-key option was proposed or applied)** repeat the warning that the chosen key must be **genuinely unique** — `RELY` is trusted but unenforced, so duplicate keys will make the dynamic table produce wrong results or fail to refresh. Uniqueness should be **verified against the data** with the pre-check in [`../primary-key-rely.md`](../primary-key-rely.md) (asking the customer's permission before running it), not taken on assertion alone. Also remind the customer the key **only takes effect once the dynamic table has been recreated** (`CREATE OR REPLACE`, Option 2) — adding it to the base table alone changes nothing on the running DT — so any post-change monitoring should start from the recreate.

## Examples

- Option 1 `example_before` (explicit `INCREMENTAL` DT) → `example_after` (only `REFRESH_MODE` changes):
  ```sql
  -- before
  CREATE OR ALTER DYNAMIC TABLE my_dt
    TARGET_LAG = '5 minutes' WAREHOUSE = my_wh REFRESH_MODE = INCREMENTAL
    AS SELECT order_id, customer_id, amount, order_ts FROM source_orders;
  -- after
  CREATE OR ALTER DYNAMIC TABLE my_dt
    TARGET_LAG = '5 minutes' WAREHOUSE = my_wh REFRESH_MODE = ADAPTIVE
    AS SELECT order_id, customer_id, amount, order_ts FROM source_orders
  /* Generated by Snowflake CoCo DT recommendations skill: HIGH_BASE_TABLE_CHANGES */;
  ```
- Option 2 (base fully reloaded each batch; add a reliable PK on the base — customer-supplied columns — then recreate the DT so it adopts the key):
  ```sql
  -- Step 0 — with the customer's OK, verify the proposed key is actually unique (RELY is unenforced).
  -- Zero rows here = unique. Any row = duplicate key ⇒ STOP, do not create the PK.
  SELECT order_id, COUNT(*) AS n
  FROM source_orders
  GROUP BY order_id
  HAVING COUNT(*) > 1
  ORDER BY n DESC LIMIT 20;
  -- Step 1 — base-table change (NOT a DT change). order_id must be unique, or the DT will break.
  -- Tagged at the end.
  ALTER TABLE source_orders ADD PRIMARY KEY (order_id) RELY
  /* Generated by Snowflake CoCo DT recommendations skill: HIGH_BASE_TABLE_CHANGES */;
  -- Step 2 — recreate the DT so its plan recompiles against the new key.
  -- CREATE OR REPLACE is the one exception to the CREATE OR ALTER rule: an
  -- unchanged CREATE OR ALTER is a no-op and would NOT pick up the key. Re-issue the exact
  -- current definition, all settings preserved, tagged with the same code.
  CREATE OR REPLACE DYNAMIC TABLE my_dt
    TARGET_LAG = '5 minutes' WAREHOUSE = my_wh REFRESH_MODE = ADAPTIVE
    AS SELECT order_id, customer_id, amount, order_ts FROM source_orders
  /* Generated by Snowflake CoCo DT recommendations skill: HIGH_BASE_TABLE_CHANGES */;
  ```

## Verbatim text

- Verbatim `info` (as it appears in the `RECOMMENDATIONS` column; exact text varies with privileges and whether an automatic reinit was applied): *"High number of changes since the last refresh. Table `<TABLE>` has a high number of changed rows (`<N>` inserts and `<N>` deletes) since the last refresh (previous count: `<M>`)"* — or, when the role cannot see base-table details, the redacted *"High number of changes from one or more base tables since the last refresh."* If an automatic reinitialization was already applied, the message is prefixed with *"Dynamic Table was reinitialized. Reason: "*.
- Verbatim `remedy`: the engine returns *"Investigate the source of the large base-table changes. Consider REFRESH_MODE = ADAPTIVE so the system can reinitialize automatically when changes outweigh the incremental cost."* (or, when reinit was already applied, just *"Investigate the source of the large base-table changes."*). The engine's `remedy` always frames `ADAPTIVE`; when Step 0 establishes a majority-overwrite pattern you must override that and steer to the primary-key option instead.
- `routes_to_on_manual`: n/a (this code is `implemented`).
