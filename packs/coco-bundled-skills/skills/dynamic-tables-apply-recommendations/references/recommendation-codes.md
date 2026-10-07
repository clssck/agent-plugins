# Dynamic Table Recommendation Codes

Reference for the recommendation codes Snowflake produces for a dynamic table, the per-code handler contract used by the `dynamic-tables-apply-recommendations` skill, and the canonical SQL for fetching, presenting, and applying them.

This file is the single place to add a new code's behavior. The sub-skill's orchestration step is generic and reads from this registry — adding a new code = appending one section here, not editing the workflow.

---

## How recommendations are exposed

Recommendations for a dynamic table appear as a JSON array in the `RECOMMENDATIONS` column of `INFORMATION_SCHEMA.DYNAMIC_TABLES()`. Each array entry has the shape:

```json
{
  "code": "<RECOMMENDATION_CODE>",
  "info": "<plain-language description of the issue>",
  "remedy": "<plain-language suggested fix>",
  "createdOn": <epoch milliseconds when the recommendation was first detected>,
  "lastDetectedAt": <epoch milliseconds when the recommendation was last re-confirmed — advances on each refresh ONLY for refresh-scope codes; for create/evolve-time codes it is stamped once at compile and never advances (see "Timestamp semantics" below)>
}
```

### Canonical fetch query

```sql
SELECT
  rec.value:"code"::STRING            AS code,
  rec.value:"info"::STRING            AS info,
  rec.value:"remedy"::STRING          AS remedy,
  TO_TIMESTAMP_LTZ(rec.value:"createdOn"::NUMBER / 1000)      AS first_detected_at,
  TO_TIMESTAMP_LTZ(rec.value:"lastDetectedAt"::NUMBER / 1000) AS last_detected_at
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES(NAME => '<DB>.<SCHEMA>.<DT>')) dt,
     LATERAL FLATTEN(INPUT => dt.recommendations:recommendations) rec;
```

If the `RECOMMENDATIONS` column does not exist (the recommendations feature is not enabled for the session/account), is `NULL`, or the array is empty for the target dynamic table, Snowflake currently has no recommendations for it. The sub-skill does **not** stop here — it continues to Step 3c (the synthetic `WAREHOUSE_TOO_SMALL` check), which runs regardless of whether INFORMATION_SCHEMA emitted any codes. The sub-skill stops only after that synthetic check finds no issues either.

The `RECOMMENDATIONS` column may take time to update after the dynamic table is modified — Snowflake re-evaluates recommendations on subsequent refresh cycles, so previously listed entries may linger for some time. Outcomes can only be confirmed by running the dynamic table further.

### Timestamp semantics & detection scope — do NOT infer staleness

Each code is detected at one of two **scopes**, which governs how its `createdOn` / `lastDetectedAt` behave:

- **Create/evolve-time (structural, query-shape) codes** — detected when the DT's query is compiled (`CREATE` / `ALTER` / evolve), from the shape of the definition. Their `createdOn` and `lastDetectedAt` are stamped **once, at that compile time, and are never advanced by later refreshes** (the two are typically equal). This group: `QUALIFY_RANK_NOT_TOP_LEVEL`, `TOP_LEVEL_AGGREGATE_NOT_TOP_LEVEL`, `NON_MONOTONIC_GROUPING_KEY`, `EXPENSIVE_ORDER_DEPENDENT_WINDOW_FUNCTION`, `AUTO_RESOLVED_TO_FULL_REFRESH`, `ICEBERG_BASE_TABLE_V2_TO_V3`.
- **Refresh-scope codes** — re-evaluated on each incremental refresh, so `lastDetectedAt` advances as the code is re-confirmed. This group: `HIGH_BASE_TABLE_CHANGES`, `CHANGED_BASE_TABLES_UNDER_JOIN`, `QUALIFY_RANK_KEYS_NOT_PERSISTED`, `TOP_LEVEL_AGGREGATE_EXPRESSIONS_NOT_PERSISTED`. (Each per-code file states its scope under `detection_signature`.)

**A recommendation's presence in the array is authoritative.** Do **not** infer that a listed code is stale, "not re-confirmed", or already resolved from the age of its timestamps. For a create/evolve-time code it is **expected and correct** that `lastDetectedAt` predates recent refreshes — e.g. `lastDetectedAt = createdOn`, older than the last 47 incremental refreshes — because these codes are only ever stamped at compile time; that is how they work, not a sign the issue is gone. Never skip, downgrade, or caveat a returned code as "probably already fixed" on a timestamp basis, and do not present `last_detected_at` age as evidence of resolution. Whether an applied fix has actually cleared a recommendation can only be confirmed by re-running the DT (see the paragraph above) — the timestamps are not a resolution signal for any code.

---

## Health-signal queries

The sub-skill uses these two signals to decide whether to frame recommendations strongly ("you should consider applying these") or softly ("nice to have"):

### (a) Target-lag breach

```sql
SELECT
  target_lag_sec,
  target_lag_type,
  mean_lag_sec,
  maximum_lag_sec,
  time_within_target_lag_ratio
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES(NAME => '<DB>.<SCHEMA>.<DT>'));
```

Breach indicator: `time_within_target_lag_ratio < 1.0`.

**Select only these columns — they are the ones this function exposes.** `INFORMATION_SCHEMA.DYNAMIC_TABLES()` does **not** have a `target_lag` (string) column, nor `refresh_mode`, `refresh_mode_reason`, or `warehouse` — selecting any of those raises `invalid identifier`. The target lag is `target_lag_sec` (NUMBER) + `target_lag_type` (`USER_DEFINED` / `DOWNSTREAM`) here. If you also need the raw `target_lag` string or `refresh_mode`, get them from `SHOW DYNAMIC TABLES` (see [dynamic-tables/references/dt-state.md](../../dynamic-tables/references/dt-state.md)) — do not add them to this query.

**`DOWNSTREAM` lag exception.** When the DT's lag type is `DOWNSTREAM` (`target_lag_type = 'DOWNSTREAM'`), both `target_lag_sec` and `time_within_target_lag_ratio` come back as `NULL`. There is no fixed target to breach — the DT refreshes only when downstream consumers ask for fresh data — so the breach check is meaningless and the sub-skill should skip it. Detect this case from `target_lag_type = 'DOWNSTREAM'` (equivalently `target_lag_sec IS NULL`) and treat the breach signal as "undefined", not "no breach". Don't compare a `target_lag` string against `'DOWNSTREAM'` — that column doesn't exist on this function. Don't synthesize a breach signal from `mean_lag_sec` or `maximum_lag_sec` against an arbitrary threshold — those numbers reflect downstream demand, not a target violation.

### (b) Cost of refreshes (last 7 days)

Compute the total estimated cost of this dynamic table's refreshes over the last week by joining `SNOWFLAKE.ACCOUNT_USAGE.DYNAMIC_TABLE_REFRESH_HISTORY` (per-refresh records, including `query_id`) to `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` (warehouse name and size) and `SNOWFLAKE.ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY` (per-query attributed compute credits). Convert credits to dollars using the customer's credit price.

```sql
-- Per-refresh cost detail for <DB>.<SCHEMA>.<DT> over the last 7 days.
-- <USD_PER_CREDIT> depends on the customer's edition / contract; ask if unknown.
WITH dt_refresh_costs AS (
    SELECT
        name AS dynamic_table_name,
        database_name,
        schema_name,
        query_id,
        refresh_action,
        state AS refresh_state,
        refresh_start_time,
        refresh_end_time,
        DATEDIFF('second', refresh_start_time, refresh_end_time) AS duration_seconds
    FROM SNOWFLAKE.ACCOUNT_USAGE.DYNAMIC_TABLE_REFRESH_HISTORY
    WHERE refresh_start_time >= DATEADD('day', -7, CURRENT_TIMESTAMP())
      AND query_id IS NOT NULL  -- excludes NO_DATA triggers that didn't run a query
      AND database_name = '<DB>'
      AND schema_name   = '<SCHEMA>'
      AND name          = '<DT>'
),
query_warehouse AS (
    SELECT query_id, warehouse_name, warehouse_size
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
    WHERE start_time >= DATEADD('day', -7, CURRENT_TIMESTAMP())
),
query_credits AS (
    SELECT query_id, credits_attributed_compute
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY
    WHERE start_time >= DATEADD('day', -7, CURRENT_TIMESTAMP())
)
SELECT
    r.database_name || '.' || r.schema_name || '.' || r.dynamic_table_name AS full_dt_name,
    w.warehouse_name,
    w.warehouse_size,
    r.refresh_action,
    r.refresh_state,
    r.refresh_start_time,
    r.duration_seconds,
    ROUND(c.credits_attributed_compute, 4)                       AS credits_consumed,
    ROUND(c.credits_attributed_compute * <USD_PER_CREDIT>, 4)    AS cost_usd,
    r.query_id
FROM dt_refresh_costs r
LEFT JOIN query_warehouse w ON r.query_id = w.query_id
LEFT JOIN query_credits   c ON r.query_id = c.query_id
ORDER BY r.refresh_start_time DESC;
```

For the threshold check, aggregate the per-refresh result:

```sql
WITH per_refresh AS ( /* the query above, without ORDER BY */ )
SELECT
    SUM(credits_consumed)                       AS est_credits_7d,
    SUM(credits_consumed) * <USD_PER_CREDIT>    AS est_cost_usd_7d
FROM per_refresh;
```

Default heuristic: `est_cost_usd_7d > $10`. **This is a deliberately rough starter** — tunable in one place (Step 3 of the sub-skill); the right value depends on the customer's overall pipeline cost profile.

**Caveats:**

- `ACCOUNT_USAGE` views have a propagation latency (typically 45 min – 3 hours). Refreshes that just completed will not appear yet.
- `credits_attributed_compute` may be `NULL` for very small refreshes on small warehouses where Snowflake didn't attribute credits at the per-query level. Treat NULL as "negligible".

If either (a) or (b) holds, frame recommendations strongly. Otherwise the DT is healthy — frame the recommendations as strictly optional and make clear that leaving it as-is is a perfectly fine outcome. A cheap DT (a small fraction of a credit per day) that is keeping up is running well; say so, and don't imply the customer needs to act. The main reason such a customer might revisit later is a large increase in data volume. (For a `USER_DEFINED` target lag, "keeping up" means it is meeting that lag; for a `DOWNSTREAM` DT there is no fixed target lag — say it refreshes on-demand as expected rather than claiming it "meets its lag".)

---

## Per-code handler contract

Each handler entry below has these fields:

| Field | Meaning |
|---|---|
| `code` | The recommendation code as it appears in the `RECOMMENDATIONS` column |
| `status` | `implemented` (the sub-skill produces an automated DDL fragment for this code) or `manual` (no auto-fix; sub-skill emits guidance and routes to `optimize/` or delivers the guidance directly, depending on the handler) |
| `customer_description` | Detailed plain-language explanation of the issue. Reference material for the assistant's own understanding and for manual-code guidance — **not** what gets shown in the Step 4 plan (see `plan_summary` / `plan_why`) |
| `plan_summary` | One imperative sentence naming the action, for the Step 4 plan list (e.g. "Switch REFRESH_MODE to ADAPTIVE"). Filled in with the DT/column/table names at presentation time. |
| `plan_why` | 1–2 precise sentences explaining why the action matters — no more. This is what a customer reads to decide whether to accept a step; keep it concrete, not generic. |
| `detection_signature` | What in the dynamic table's definition or refresh behavior triggers this code (documentation only — the engine performs the actual detection) |
| `ddl_transformation` | For `implemented`: recipe to transform the dynamic table's `GET_DDL` output into a fixed form. For `manual`: empty. |
| `example_before` / `example_after` | SQL pair illustrating the transformation. Omitted for `manual`. |
| `routes_to_on_manual` | When `status = manual`, which sub-skill the customer is routed to (typically `optimize/`). |

### Plan presentation contract (Step 4)

Once Steps 2–3 have run (silently — no need to narrate each query) and every returned code's per-code specifics are resolved (already-`ADAPTIVE` checks, the `HIGH_BASE_TABLE_CHANGES` overwrite-frequency pre-check, escape-case detection for the column-adding handlers, the `WAREHOUSE_TOO_SMALL` decision tree, etc. — all still run, just without narrating the process), present **one** plan message instead of a running commentary:

```
I looked at <DB>.<SCHEMA>.<DT> — <framing>:

1. **<plan_summary>** — <automatic fix | needs your confirmation | informational only>
   Why: <plan_why>

2. **<plan_summary>** — ...
   Why: ...

Want me to go ahead with these?
```

**`<framing>` is fixed, not improvised** — use one of these two sentences verbatim (fill in the DT name), matching `has_issue` from Step 3:
- `has_issue = TRUE`: "I have recommendations worth applying"
- `has_issue = FALSE`: "it's currently meeting its target lag; here are some optional improvements you could make"

**When `has_issue = FALSE`, say more than the one-clause framing — make explicit that doing nothing is a perfectly good outcome.** Don't imply the customer should apply anything. Fold these into the opening line (before the numbered list) and change the closing question:

- **Cost figure** — use the DT's **actual** 7-day cost from Step 3; `has_issue = FALSE` only means it's under the breach threshold, not necessarily cheap.
  - Genuinely low (a fraction of a credit/day): call it **inexpensive** and give the figure — *"...and its refreshes are inexpensive (about `<est_credits_7d>` credits over the last 7 days)."*
  - Present but not low: state the figure plainly, no "inexpensive" label — *"...its refreshes cost about `<est_credits_7d>` credits over the last 7 days."*
  - No cost baseline available (DT hasn't run recently, or `ACCOUNT_USAGE` had no rows): omit the cost clause entirely, keep the rest.
- **"You don't need to change anything"** — state this plainly as part of the framing, not just implied by soft tone: *"...so you don't need to change anything. If you're happy with how it's performing and don't expect a large increase in its data volume, leaving it exactly as-is is a perfectly good choice."*
- **`TARGET_LAG = DOWNSTREAM` exception** — a DT with `DOWNSTREAM` lag has no fixed target, so never claim it's "meeting its target lag." Replace that clause with something like *"it's refreshing on-demand (its lag is `DOWNSTREAM`) as expected"* — keep the cost clause and "you don't need to change anything" framing unchanged.
- **Closing question** — replace `Want me to go ahead with these?` with *"Happy to apply any of these if you'd like, or we can leave everything as-is."*

Rules for this message:
- One numbered entry per returned code (including `manual`/informational ones, tagged "informational only", so the customer sees full coverage without a paragraph per code).
- `plan_summary` and `plan_why` come straight from the per-code file, filled in with the actual DT/column/table names — do not fall back to `customer_description` here; that field is reference material, not customer-facing text.
- **A code offering more than one remediation (`HIGH_BASE_TABLE_CHANGES`, `CHANGED_BASE_TABLES_UNDER_JOIN`) shows only its single preferred default here** — per the per-code file's own stated preference order (e.g. `HIGH_BASE_TABLE_CHANGES` defaults to `ADAPTIVE` unless majority-overwrite rules it out, in which case the primary-key option becomes the default). No menu, no "pick one" — it reads exactly like every other entry. If the customer declines this specific entry in Step 5, the alternative is offered *then*, one at a time — see [DDL composition — Handlers may offer more than one remediation](#ddl-composition) below. This plan message is never the place multiple options get *decided between*.
  **Exception — the customer explicitly asked to know their options** (e.g. "what are my options", "what could I do about this", "what would you recommend and what else is possible"). That is a request for information, not a request to apply a fix, and the default-only rule above must not cause the other option(s) to go unmentioned in that case — add one short trailing clause naming the other viable option(s) (not their full trade-offs; the per-code file has those) so the answer to what was actually asked is complete, e.g. "...(a `FROZEN WHERE` alternative also exists for data that's stopped changing)." This is disclosure, not a decision gate — it doesn't turn the entry back into a "pick one" menu, and the sequential ask in Step 5 still governs how execution is actually resolved once/if the customer decides to proceed with something.
- The `REFRESH_MODE` downstream-latency note (for any `ADAPTIVE` switch) becomes a trailing clause on that entry's `Why` line, not a new paragraph. The `HIGH_BASE_TABLE_CHANGES` / `CHANGED_BASE_TABLES_UNDER_JOIN` "investigate the source" guidance is **not** part of this message — it's a mandatory Step 7 wrap-up point regardless of what was decided here (see Step 7 in `SKILL.md`).
- This single message is the only stopping point for "which recommendations to apply" as a whole — it replaces what used to be a separate wall of prose per code. Individual multi-option follow-ups (declining a default, being offered its alternative) happen later, in Step 5, one at a time.

This does not change *what* is computed, only when it's narrated — Steps 2–3 and the per-code resolution logic they depend on are unchanged.

### DDL composition

When the customer accepts one or more `implemented` recommendations, the sub-skill composes the DDL needed to apply all selected fixes. The output is **one or more `CREATE OR ALTER DYNAMIC TABLE` statements — one per resulting dynamic table**:

- Most fixes rewrite the existing DT in place and produce **exactly one** `CREATE OR ALTER` for the original `<DT>`.
- A handler that requires splitting the DT into two (e.g. `QUALIFY_RANK_NOT_TOP_LEVEL` when the wrapping levels do meaningful work) produces **two** `CREATE OR ALTER` statements: one for the producer DT, one for the consumer DT (which keeps the original `<DT>`'s name).
- The skill never emits multiple `CREATE OR ALTER` statements targeting the same `<DT>`. If multiple selected recommendations apply to one resulting DT, their `ddl_transformation` recipes are composed together (handlers must be commutative for codes that can co-occur — verified per code below) and emitted as a single statement for that DT.

Use `GET_DDL('DYNAMIC_TABLE', '<fully_qualified_name>')` as the seed for the original DT, apply each selected handler's `ddl_transformation` to the seed in order, and emit the resulting `CREATE OR ALTER` statement(s). Always preserve the original `TARGET_LAG`, `WAREHOUSE`, `INITIALIZE`, `FROZEN WHERE` (legacy DTs may carry the old `IMMUTABLE WHERE` keyword — preserve whichever the DT already uses), all other settings and inline comments unless the customer explicitly requests changing them. When a handler splits the DT, the producer DT can use `TARGET_LAG = DOWNSTREAM` and the consumer DT keeps the original `TARGET_LAG`.

**`CREATE OR ALTER` fully supports rewriting the query body, not just settings.** A consumer DT whose new `SELECT` reads from a producer instead of the original base tables is still just a changed `AS <query>` — that the body (not merely a setting like `WAREHOUSE`) is what's changing is never, by itself, a reason to reach for `CREATE OR REPLACE`. `CREATE OR REPLACE` is reserved for the single documented exception below (base-table PK adoption); every rewrite and every split/decomposition producer or consumer statement, however extensively the `SELECT` changes, is a `CREATE OR ALTER`.

**`REFRESH_MODE` for new intermediate (producer) DTs.** When a handler creates a *new* intermediate DT (e.g. the producer DT in a split), always set `REFRESH_MODE = ADAPTIVE` on it. `ADAPTIVE` lets the engine choose between `INCREMENTAL` and `REINIT` per-refresh based on actual data patterns. **Never use `REFRESH_MODE = AUTO`** for a newly-created intermediate DT — `AUTO` resolves the mode once at compile time and may conservatively choose `FULL` permanently, defeating the purpose of the optimization. The consumer DT (which keeps the original DT's name) preserves whatever `REFRESH_MODE` the original DT had.

**A few handlers emit a base-table DDL or need customer-supplied inputs.** Most fixes are `CREATE OR ALTER DYNAMIC TABLE` on the DT itself, but a handler may instead (or additionally) emit a statement against a **base table** — e.g. `HIGH_BASE_TABLE_CHANGES` Path B proposes `ALTER TABLE <base> ADD PRIMARY KEY (<cols>) RELY` when the base is fully rewritten each load. Such fixes change the base table, not the DT, and may require the customer to supply values (the PK columns) and confirm a precondition (the key is truly unique). Treat these as per-code stopping points: gather the inputs and confirm the precondition before composing the statement. **Confirming the precondition means verifying it against the data, not just taking the customer's word** — for the PK case, ask permission to run a read-only uniqueness check on the proposed column(s) and only proceed if it comes back clean (emphasize uniqueness is critical because `RELY` is unenforced). **A newly-added base-table primary key is not adopted by the already-compiled DT**, so this fix must be followed by a `CREATE OR REPLACE DYNAMIC TABLE` recreate of the DT (re-issuing its exact current definition) so the plan recompiles against the new key — the **one exception** to the "always `CREATE OR ALTER`, never `CREATE OR REPLACE`" rule. The exception is limited to this PK-adoption case; when the PK is applied together with a reinit-triggering DT change (the `ADAPTIVE` switch), that `CREATE OR ALTER` recompiles and adopts the key on its own, so no `CREATE OR REPLACE` is needed.

**DDL tagging (mandatory).** Every DDL statement this skill executes — `CREATE OR ALTER DYNAMIC TABLE`, the PK-adoption `CREATE OR REPLACE DYNAMIC TABLE`, a standalone `ALTER DYNAMIC TABLE ... SET WAREHOUSE` or `SET INITIALIZATION_WAREHOUSE`, and a base-table `ALTER TABLE <base> ADD PRIMARY KEY (...) RELY` — must embed an inline SQL comment naming the recommendation code(s) it applies. Insert the comment at the **very end of the statement**, immediately before the trailing semicolon:

```sql
CREATE OR ALTER DYNAMIC TABLE <DT> ... /* Generated by Snowflake CoCo DT recommendations skill: HIGH_BASE_TABLE_CHANGES */;
CREATE OR REPLACE DYNAMIC TABLE <DT> ... /* Generated by Snowflake CoCo DT recommendations skill: HIGH_BASE_TABLE_CHANGES */;
ALTER DYNAMIC TABLE <DT> SET WAREHOUSE = ... /* Generated by Snowflake CoCo DT recommendations skill: WAREHOUSE_TOO_SMALL */;
ALTER TABLE <base> ADD PRIMARY KEY (<cols>) RELY /* Generated by Snowflake CoCo DT recommendations skill: HIGH_BASE_TABLE_CHANGES */;
```

- Format: `/* Generated by Snowflake CoCo DT recommendations skill: <CODE1>[, <CODE2>, ...] */` — list every recommendation code whose `ddl_transformation` contributed to that specific statement, comma-separated, in the order applied.
- When multiple selected codes are composed into a single statement for one resulting DT (see above), list all of them in that one statement's tag — do not emit separate tags per code.
- The base-table `ALTER TABLE ... ADD PRIMARY KEY ... RELY` step and the `CREATE OR REPLACE DYNAMIC TABLE` recreate it triggers both carry the same code (currently `HIGH_BASE_TABLE_CHANGES`) even though they are two separate statements.

**No live data diff — disclose unverified rewrites (mandatory).** Handler recipes are pattern-based rewrites; edge cases (NULL handling, tie-breaking in window functions, implicit type coercions) can silently change semantics. The sub-skill does **not** run a row-level data comparison (e.g. an `EXCEPT`-based diff) against the live base tables to verify this as it can lead to high costs. **Never claim a rewrite was verified against live data.**

**Show the AI-accuracy disclaimer** whenever a proposed `CREATE OR ALTER DYNAMIC TABLE` has a `SELECT` body that differs from the original (i.e. anything other than the structural exceptions below). Keep it to one line. Ordering is always **DDL, then disclaimer, then the run-approval ask** — action before explanation, never the reverse — and never earlier in the conversation (e.g. not in the Step 4 plan, where it would just be noise repeated once per risky step before anything is even selected):

> This is a pattern-based rewrite, not verified against your live data — spot-check row counts and a sample of rows before relying on it in production.

**`REFRESH_MODE` changes can affect downstream consumers.** Whenever a fix changes `REFRESH_MODE` — a settings-only `ADAPTIVE` switch (`HIGH_BASE_TABLE_CHANGES`, `CHANGED_BASE_TABLES_UNDER_JOIN`) or the `ADAPTIVE` mode assigned to a new producer DT in a split — tell the customer that consumers of the DT (queries, other DTs, tasks) may notice different refresh latency or staleness characteristics afterward, since `ADAPTIVE` can pick a different refresh strategy per run than the previous mode did.

**Structural exceptions — no disclaimer needed, nothing to verify:**
- **Settings-only changes.** Some `implemented` handlers change only a table setting (e.g. `REFRESH_MODE = ADAPTIVE`) and leave the `AS <query>` body byte-for-byte unchanged. When the `SELECT` is identical to the original there is nothing to diff or disclaim — state explicitly that the query body is unchanged so equivalence is trivially preserved.
- **`QUALIFY_RANK_NOT_TOP_LEVEL`'s in-place top-level `ORDER BY` drop.** A dynamic table has no inherent row order, so dropping a redundant top-level `ORDER BY` is equivalent by construction — **but only when that `ORDER BY` has no `LIMIT` / `FETCH` / `OFFSET` / `TOP` attached to it.** If a `LIMIT`/`FETCH`/`OFFSET`/`TOP` is present, the `ORDER BY` determines *which* rows survive, not just their presentation order, so dropping it can change the result set — that case is **not** a structural exception; it needs the disclaimer above like any other rewrite. See [codes/QUALIFY_RANK_NOT_TOP_LEVEL.md](codes/QUALIFY_RANK_NOT_TOP_LEVEL.md).

`QUALIFY_RANK_KEYS_NOT_PERSISTED` and `TOP_LEVEL_AGGREGATE_EXPRESSIONS_NOT_PERSISTED` append output columns and so are **not** structural exceptions — their `SELECT` list changes, so they get the standard AI-accuracy disclaimer above like any other body-changing rewrite. (They previously had a bespoke, mandatory, data-driven "added-columns equivalence check" in place of the disclaimer; that check has been removed for the same cost/soundness reasons that ruled out the live `EXCEPT`-based diff for every other handler.) Each still has its own **schema-change confirmation gate** (see the handler file) disclosing that output columns are being added — that's a distinct, additional disclosure about the schema change itself, not a substitute for the disclaimer.

**One other per-code check also touches live data, for a different reason than the mandatory-disclosure policy above, and is kept as-is:**
- `HIGH_BASE_TABLE_CHANGES`' PK-uniqueness precondition check (see [DDL composition](#ddl-composition) above and [codes/HIGH_BASE_TABLE_CHANGES.md](codes/HIGH_BASE_TABLE_CHANGES.md)) — this validates a precondition on a **new constraint** being added (is the proposed key actually unique?), not an old-vs-new query diff; getting it wrong silently corrupts the DT via an unenforced `RELY`, which is a materially different risk than a slow/flaky verification query.

**Handlers may offer more than one remediation — resolve *which* one(s) sequentially, never as an upfront menu, and never with a DDL preview per option.** A single `implemented` code can expose more than one remediation option, and the per-code file states a preference order (which option is the default, and whether the options are mutually exclusive or combinable). The Step 4 plan (see the *Plan presentation contract* above) shows only that default. What happens next depends on the handler's own combination rule — and it's a plain-language decision at this stage, not SQL:

- **Mutually exclusive** (e.g. `CHANGED_BASE_TABLES_UNDER_JOIN`: `ADAPTIVE` **or** join decomposition, never both). If the customer declines the default when it comes up for confirmation in Step 5, offer the next option in preference order as a fresh, standalone ask — its one-line why in plain language, then "want this instead?" Only one option is ever included.
- **Combinable** (e.g. `HIGH_BASE_TABLE_CHANGES`: `ADAPTIVE` and the base-table primary key are independent add-ons, not alternatives). Resolve the default first; once settled (accepted or declined), separately ask about the next option as an *additional* fix, not a replacement — accepting one says nothing about the other. **A blanket approval already given doesn't carry over to this add-on** — it was a response to the default, given before the add-on was even described, so treat it the same as any other approval-given-before-the-fix-was-described case (see the *generic blanket approval* rule above): default to naming the add-on and its rationale without including it, and only include it on a real signal tied to the add-on specifically.

Either way: one option, one ask, one answer, before moving to the next — but **no DDL and no disclaimer at this stage, for any option.** These exchanges only decide the *set* of fixes going into the DT; composing and showing the actual SQL happens once, after every code (multi-option or not) is resolved, per [DDL composition](#ddl-composition) above — the customer reviews one real definition change, not a new draft after every yes/no. Never present two or more options together and ask the customer to choose among them either — that round-trip is exactly what this design replaces. **In headless/auto-accept-plans mode**, this sequential design needs no special-casing: whichever option is currently first-in-line is treated exactly like any other single recommendation, so it already falls under the existing headless carve-outs (Step 5's settings-only auto-execute, and the PK-uniqueness check's auto-run-if-read-only rule in [primary-key-rely.md](primary-key-rely.md)) — auto-confirming without waiting, precisely because it's no longer wrapped in a "pick one" gate. If the first-in-line option isn't itself headless-safe (e.g. decomposition, or a PK whose columns aren't known), headless mode correctly stalls on that one ask, same as it would for any other approval-required action.

`manual` codes are never included in the composed DDL — they are presented separately with their guidance text and then handled per their `routes_to_on_manual`: most route to `optimize/`, while a self-contained informational handler (`routes_to_on_manual: none`) delivers its guidance directly without routing.

**Co-occurring `HIGH_BASE_TABLE_CHANGES` + `CHANGED_BASE_TABLES_UNDER_JOIN`.** When both fire on the same DT, address `HIGH_BASE_TABLE_CHANGES` **first** rather than treating them as two independent fixes. The heavy base-table churn it flags is **most likely a major driver of** `CHANGED_BASE_TABLES_UNDER_JOIN`, so resolving it first will **likely** reduce or clear the under-join recommendation too — though not necessarily: if other join inputs are *independently* changing heavily, it may persist and can be revisited afterward. Tell the customer the under-join recommendation is most likely driven largely by the same high base-table changes, so it makes sense to address those first. See the co-occurrence rule in `SKILL.md` Step 4.

---

## Codes

Each recommendation code's full handler entry lives in its own file under [`codes/`](codes/). **Load only the file(s) for the codes returned by the [canonical fetch query](#canonical-fetch-query)** — do not load the whole set. Every per-code file uses the shared handler contract above (field definitions, DDL composition, disclosure of unverified rewrites).

| Code | File |
|---|---|
| `QUALIFY_RANK_NOT_TOP_LEVEL` | [codes/QUALIFY_RANK_NOT_TOP_LEVEL.md](codes/QUALIFY_RANK_NOT_TOP_LEVEL.md) |
| `TOP_LEVEL_AGGREGATE_NOT_TOP_LEVEL` | [codes/TOP_LEVEL_AGGREGATE_NOT_TOP_LEVEL.md](codes/TOP_LEVEL_AGGREGATE_NOT_TOP_LEVEL.md) |
| `QUALIFY_RANK_KEYS_NOT_PERSISTED` | [codes/QUALIFY_RANK_KEYS_NOT_PERSISTED.md](codes/QUALIFY_RANK_KEYS_NOT_PERSISTED.md) |
| `TOP_LEVEL_AGGREGATE_EXPRESSIONS_NOT_PERSISTED` | [codes/TOP_LEVEL_AGGREGATE_EXPRESSIONS_NOT_PERSISTED.md](codes/TOP_LEVEL_AGGREGATE_EXPRESSIONS_NOT_PERSISTED.md) |
| `AUTO_RESOLVED_TO_FULL_REFRESH` | [codes/AUTO_RESOLVED_TO_FULL_REFRESH.md](codes/AUTO_RESOLVED_TO_FULL_REFRESH.md) |
| `EXPENSIVE_ORDER_DEPENDENT_WINDOW_FUNCTION` | [codes/EXPENSIVE_ORDER_DEPENDENT_WINDOW_FUNCTION.md](codes/EXPENSIVE_ORDER_DEPENDENT_WINDOW_FUNCTION.md) |
| `NON_MONOTONIC_GROUPING_KEY` | [codes/NON_MONOTONIC_GROUPING_KEY.md](codes/NON_MONOTONIC_GROUPING_KEY.md) |
| `HIGH_BASE_TABLE_CHANGES` | [codes/HIGH_BASE_TABLE_CHANGES.md](codes/HIGH_BASE_TABLE_CHANGES.md) |
| `CHANGED_BASE_TABLES_UNDER_JOIN` | [codes/CHANGED_BASE_TABLES_UNDER_JOIN.md](codes/CHANGED_BASE_TABLES_UNDER_JOIN.md) |
| `WAREHOUSE_TOO_SMALL` | [codes/WAREHOUSE_TOO_SMALL.md](codes/WAREHOUSE_TOO_SMALL.md) |
| `ICEBERG_BASE_TABLE_V2_TO_V3` | [codes/ICEBERG_BASE_TABLE_V2_TO_V3.md](codes/ICEBERG_BASE_TABLE_V2_TO_V3.md) |

**Adding a new code:** create one file in [`codes/`](codes/) following the handler contract above, and add one row to this table. The sub-skill's orchestration is generic and does not change.

---

## Verification language for Step 7 of the sub-skill

After running `CREATE OR ALTER DYNAMIC TABLE`, the sub-skill must wrap up with a neutral message. Authoring guard — the wrap-up must NOT promise improvement. Deliver this as **one short paragraph**, not five separate call-outs — but it must still carry every required point below:

1. The DDL has been applied.
2. The `RECOMMENDATIONS` column may take time to update — do not expect previously listed recommendations to disappear immediately.
3. Whether the change actually improves performance can only be validated by running the dynamic table further. The customer should monitor refresh times over the next several refresh cycles.
4. Provide the canonical refresh-statistics query (parameterized for a post-change time window) so the customer can compare against the baseline captured in Step 3.
5. If refresh times do not improve over a meaningful number of cycles, suggest revisiting with `optimize/` for deeper performance analysis.

Compact template (fill in the bracketed values) — **use the bolded phrases below verbatim, not a paraphrase**; they are the literal words a customer (or downstream tooling) should be able to search for:

> Applied. The `RECOMMENDATIONS` column **may take time to update** — definition-level fixes clear immediately, refresh-level ones need a few more refresh cycles. Whether this actually helps can only be confirmed by **running the dynamic table further** — **monitor refresh times** over the next several cycles and compare against the baseline (`<Step 3 numbers>`) with:
> `<comparison query>`
> If it doesn't improve, revisit with the `optimize/` workflow.
