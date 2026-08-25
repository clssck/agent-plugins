---
name: dynamic-tables-apply-recommendations
description: "Apply Snowflake-emitted recommendations to a specific dynamic table. Triggers: apply DT recommendations, apply recommendations to dynamic table, look at recommendations for, RECOMMENDATIONS column, AUTO_RESOLVED_TO_FULL_REFRESH, QUALIFY_RANK_NOT_TOP_LEVEL, TOP_LEVEL_AGGREGATE_NOT_TOP_LEVEL, QUALIFY_RANK_KEYS_NOT_PERSISTED, TOP_LEVEL_AGGREGATE_EXPRESSIONS_NOT_PERSISTED, EXPENSIVE_ORDER_DEPENDENT_WINDOW_FUNCTION, NON_MONOTONIC_GROUPING_KEY, HIGH_BASE_TABLE_CHANGES, CHANGED_BASE_TABLES_UNDER_JOIN, WAREHOUSE_TOO_SMALL, ICEBERG_BASE_TABLE_V2_TO_V3."
---

# Apply Dynamic Table Recommendations

Customer asked to look at and apply Snowflake's recommendations for a specific dynamic table. Workflow: analyze in the background, then present one short plan (summary + why per action, framed to severity), let the customer pick a subset, then apply the selected fixes via a single `CREATE OR ALTER DYNAMIC TABLE` statement.

## When to Load

Load this skill when the customer asks specifically about recommendations for a single dynamic table — e.g. "look at the recommendations for `db.sch.dt`", "apply DT recommendations", or names a specific recommendation code. The skill always begins by checking whether Snowflake has emitted recommendations for that DT: if it has, the skill triages and applies them; if it has not (the `RECOMMENDATIONS` column is absent/NULL or empty), the skill stops and points the customer to general performance optimization rather than running that analysis itself. Because of this gate it is a reasonable first stop even for general performance/cost prompts on a specific DT ("my DT is too slow", "this DT is too expensive"), but when no recommendations exist it hands off rather than diagnosing.

For general performance optimization that does not start from the recommendations column (decomposition, immutability constraints, warehouse-size changes, deeper operator-stat analysis), route to `../dynamic-tables/optimize/SKILL.md` instead.

### Out of scope — route back to `dynamic-tables`

This skill is narrowly focused on the recommendations workflow. For any other dynamic-tables topic — creating a new DT, monitoring health, troubleshooting refresh failures, alerting on failures, permissions / privilege errors, converting streams+tasks or dbt models, custom incrementalization, or pipeline-wide diagnostics (Gantt charts, UPSTREAM_FAILED, critical-path tracing) — load the parent dynamic-tables skill at [../dynamic-tables/SKILL.md](../dynamic-tables/SKILL.md) and let it route to the right sub-skill. The parent skill's intent table covers CREATE / MONITOR / TROUBLESHOOT / OPTIMIZE / ALERTING / PERMISSIONS / TASK-TO-DT / CUSTOM-INCREMENTALIZATION / DBT-TO-DT / PIPELINE-DIAGNOSTICS.

## Reference

**Load** [references/recommendation-codes.md](references/recommendation-codes.md) for the shared handler contract, JSON shape of the `RECOMMENDATIONS` column, the canonical health-signal queries, the code index, and the verification wrap-up language. The orchestration in this file is generic.

Each recommendation code's full handler entry lives in its own file under [references/codes/](references/codes/). **Do not load them all up front** — after Step 2 fetches the recommendations, load only `references/codes/<CODE>.md` for each code actually present on the target dynamic table. The index table in `recommendation-codes.md` maps every code to its file.

---

## ⚠️ MANDATORY INITIALIZATION

Before running the workflow below, you MUST do all three of the following. These initialization steps mirror the parent `dynamic-tables` skill so this skill can stand on its own when invoked directly without the parent being loaded.

### Init Step 1: Load core references

Load both reference documents from the parent dynamic-tables skill (they ship alongside this skill in builds where this skill is present):

1. **Load**: [../dynamic-tables/references/sql-syntax.md](../dynamic-tables/references/sql-syntax.md) — Dynamic Table SQL command syntax (`CREATE`, `CREATE OR ALTER`, `CREATE OR REPLACE`, `ALTER`, refresh modes, `FROZEN WHERE`, etc.).
2. **Load**: [../dynamic-tables/references/monitoring-functions.md](../dynamic-tables/references/monitoring-functions.md) — monitoring-function router (database-context rules + links to state, refresh-analysis, and graph references).

**⚠️ MANDATORY STOPPING POINT**: Do NOT proceed until both references are loaded.

### Init Step 2: Establish session context

Confirm which Snowflake account, region, user, and role this session is running under so subsequent queries land on the right objects:

```sql
SELECT CURRENT_ACCOUNT() AS account,
       CURRENT_REGION()  AS region,
       CURRENT_USER()    AS username,
       CURRENT_ROLE()    AS active_role;
```

If `active_role` cannot see the dynamic table the customer is asking about, ask the customer which role they expect to use and re-run with `USE ROLE <role>;`.

**⚠️ MANDATORY STOPPING POINT**: Do NOT proceed until session context is confirmed.

### Init Step 3: Confirm database context for `INFORMATION_SCHEMA` calls

`INFORMATION_SCHEMA.DYNAMIC_TABLES()` and `INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY()` are per-database. Run a `USE DATABASE <DB>;` on the database that contains the target dynamic table before issuing those calls (or use the fully-qualified `NAME => '<DB>.<SCHEMA>.<DT>'` form everywhere, which the canonical queries in this skill already do).

---

## Headless / Auto-Apply Mode

> **Note:** `auto-accept plans: true` / `--auto-accept-plans` is an eval-harness flag, not a production customer feature. These rules govern how the skill behaves when run by the eval harness.

**When `auto-accept plans: true` appears in the session context** (set by `--auto-accept-plans`) AND the customer's request contains explicit apply intent (e.g. "apply the recommendations", "look at and apply", "fix it", "improve it", "I approve") AND **`has_issue = TRUE`** (the DT has a measurable performance issue — lag breach, cost breach, or the customer's prompt explicitly signals a problem like "too slow" or "I approve running the changes"), skip the Step 5 confirmation entirely and execute the DDL immediately — **for the recipes covered by the carve-out below.** Do not ask "Would you like me to apply this?", "Want me to run it?", or any similar question for those. Just execute.

**This never authorizes skipping Step 4.** Apply intent, blanket approval, and `auto-accept plans: true` only ever remove the *wait for a reply* to the Step 4 batched question and/or the Step 5 DDL-approval ask — they never remove the Step 4 plan message itself. The numbered `plan_summary` + `Why: <plan_why>` disclosure must still be rendered as its own customer-facing turn, for every returned code, before any DDL is composed or shown — in every mode, headless included.

**Carve-out — auto-apply is limited to recipes with no unverified `SELECT`-body change.** Only two categories of recipe qualify for the auto-execute above:
- **Settings-only changes** — the `AS <query>` body is byte-for-byte unchanged (e.g. `REFRESH_MODE = ADAPTIVE`).
- **`QUALIFY_RANK_NOT_TOP_LEVEL`'s guarded in-place `ORDER BY` drop** — equivalent by construction, and only when that `ORDER BY` has no `LIMIT` / `FETCH` / `OFFSET` / `TOP` attached (see its per-code file).

**Any handler that splits or decomposes the DT into a producer + consumer (or otherwise changes the `SELECT` body without a static-by-construction proof) never auto-executes — in every mode, regardless of `auto-accept plans: true`, apply intent, or `has_issue`.** This includes `QUALIFY_RANK_NOT_TOP_LEVEL`'s split case, `TOP_LEVEL_AGGREGATE_NOT_TOP_LEVEL` (always splits), `CHANGED_BASE_TABLES_UNDER_JOIN` Option B (decomposition), and the guarded `ORDER BY` case when a `LIMIT`/`FETCH`/`OFFSET`/`TOP` is attached. For these, always show the AI-accuracy disclaimer and the composed DDL, and wait for an explicit approval turn before executing — headless/apply-intent cannot supply that approval on its own. (`QUALIFY_RANK_KEYS_NOT_PERSISTED` and `TOP_LEVEL_AGGREGATE_EXPRESSIONS_NOT_PERSISTED` are separately excluded from headless auto-apply per their own schema-change rule below; unaffected by this carve-out.)

**A generic blanket approval does not satisfy this.** If the customer's original request contains a generic statement like "I approve running any DDL changes you recommend" — made before this specific fix was ever described, and not tied to it — that does **not**, by itself, count as the explicit approval this section requires. Do not bypass the wait, skip it, or execute solely on the strength of that generic statement. Instead, describe the specific fix (which recommendation, what it changes — e.g. "split the DT into a producer that does X and a consumer that does Y") along with the disclaimer, and get a response to *that* description before executing. The approval doesn't need a second round-trip after literally rendering the SQL text — if the customer has already clearly approved the specific fix as described (e.g. "yes, go ahead and split it"), that is sufficient; you don't need to re-ask after composing the DDL. What's never sufficient on its own is apply intent, `auto-accept plans: true`, or a generic statement that was never tied to this specific fix.

**Exception — explicit ongoing delegation of authority, for non-structural fixes only.** The rule above is about split/decomposition and other structurally risky changes (line "never auto-executes... in every mode"), which always need approval of the specific fix as described, no matter what — that stays absolute. But for everything else Step 5 handles — a settings-only change, a single straightforward `CREATE OR ALTER`, or a live-data check that's part of delivering it — a customer who explicitly hands over ongoing authority ("handle everything", "look at the recommendations and fix what needs fixing", "I approve running any DDL changes and any verification queries needed") has already answered "want me to do this?" for whichever safe, default fix turns out to be needed, even though they couldn't have named the exact mechanism in advance (they don't know the diagnosis yet). **Don't manufacture a "want me to apply `<mechanism>` specifically?" question in that case** — re-asking is exactly the per-item back-and-forth this kind of statement is meant to skip. This is narrower than apply intent alone (e.g. a bare "fix it" doesn't reach this bar) — it requires the customer explicitly saying they don't need to be asked per-item. It does **not** extend to a combinable *add-on* beyond a code's default recommendation (see the separate add-on rule in Step 5), and it never overrides the split/decomposition carve-out above.

**If `has_issue = FALSE`** (the DT is healthy and meeting its target), the normal interactive flow applies regardless of headless mode — present the recommendation with soft framing and wait for explicit approval before executing.

**Headless mode never auto-applies when there are no recommendations.** The Step 2 early-exit gate runs before the Step 3 baseline, so a DT with no recommendations exits at Step 2 — before any performance-issue determination is made — regardless of headless mode or apply intent.

---

## Workflow

**Investigation isolation.** Each time the customer names a dynamic table to investigate, treat it as a completely fresh, independent investigation. Do not carry over findings, baselines, recommendations, DDL, or any other context from a different DT investigated earlier in the same session. Do not make comparisons to prior DTs or reference facts from those investigations unless the customer explicitly asks you to. When explicitly asked to compare, you may reference baseline metrics, recommendation codes, or composed DDL from earlier DTs in this session — label each fact by its source DT name and present it alongside the current investigation rather than blending it in.

### Step 1: Confirm scope

**Goal:** confirm the customer named a specific dynamic table.

If the customer has not named one, ask:

> Which dynamic table do you want me to look at? Please give the fully qualified name (`<database>.<schema>.<dynamic_table>`).

Do not proceed without a single fully qualified name. If the customer asks about "all DTs in this schema", route to `../dynamic-tables/monitor/SKILL.md` for schema-wide health checks instead.

**⚠️ MANDATORY STOPPING POINT:** the dynamic table identifier is required before any further query.

---

### Step 2: Fetch recommendations

**Goal:** read the recommendations Snowflake has produced for this dynamic table. This step is the **gate** for the rest of the skill — nothing downstream (the baseline, framing, DDL composition, or execution) runs unless at least one recommendation exists. **Run this step's queries silently** — no need to narrate each one; the first customer-facing message is the Step 4 plan.

**Step 2a — Check that the `RECOMMENDATIONS` column is available.**

Before fetching recommendations, probe whether the `RECOMMENDATIONS` column exists in `INFORMATION_SCHEMA.DYNAMIC_TABLES()`:

```sql
SELECT recommendations
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES(NAME => '<DB>.<SCHEMA>.<DT>'))
LIMIT 1;
```

- **If this query errors** with a SQL compilation error indicating the `RECOMMENDATIONS` column does not exist (e.g. `invalid identifier 'RECOMMENDATIONS'`, `unknown identifier`, or any column-not-found error): the BCR bundle **2026_06** has not been enabled for this account. Tell the customer:

  > The `RECOMMENDATIONS` column is not available in `INFORMATION_SCHEMA.DYNAMIC_TABLES()`. This feature requires opting in to BCR bundle **2026_06**. Before enabling it, please review the BCR documentation to understand any breaking changes it may introduce for your account.
  >
  > To opt in, run the following using a role with ACCOUNTADMIN privileges (or equivalent):
  > ```sql
  > SELECT SYSTEM$ENABLE_BEHAVIOR_CHANGE_BUNDLE('2026_06');
  > ```

  **Stop here. Do not proceed with the recommendations workflow.**

- **If this query errors** for any other reason (e.g. insufficient privileges on `INFORMATION_SCHEMA`, an invalid DT name, or a generic Snowflake error): surface the raw error message to the customer and stop. Do not assume the cause is BCR 2026_06.

- **If the query succeeds** (returns a row or 0 rows, even with a NULL value): the column exists — proceed to the canonical fetch query below.

Run the canonical fetch query from [references/recommendation-codes.md — Canonical fetch query](references/recommendation-codes.md#canonical-fetch-query):

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

**⚠️ Do NOT infer staleness from the timestamps.** `first_detected_at` / `last_detected_at` are informational only. Many codes are detected at **create/evolve time** (`QUALIFY_RANK_NOT_TOP_LEVEL`, `TOP_LEVEL_AGGREGATE_NOT_TOP_LEVEL`, `NON_MONOTONIC_GROUPING_KEY`, `EXPENSIVE_ORDER_DEPENDENT_WINDOW_FUNCTION`, `AUTO_RESOLVED_TO_FULL_REFRESH`, `ICEBERG_BASE_TABLE_V2_TO_V3`) and their timestamps are stamped once and **never advance on refreshes** — so an old `last_detected_at` (even one predating dozens of recent refreshes, or equal to `first_detected_at`) does **not** mean the recommendation is stale, unconfirmed, or already resolved. A code's presence in the result is authoritative: handle every returned code per its per-code file, and never skip, downgrade, or caveat one as "probably already fixed" because its timestamp looks old. See [references/recommendation-codes.md — Timestamp semantics & detection scope](references/recommendation-codes.md#timestamp-semantics--detection-scope--do-not-infer-staleness).

**⚠️ CONDITIONAL EARLY-EXIT GATE.** If the `RECOMMENDATIONS` column does not exist, is `NULL`, or the recommendations array is empty (the fetch query returns zero rows), there are no INFORMATION_SCHEMA-emitted recommendations. **Do not run Steps 3a or 3b** (the lag-breach and cost queries). **Proceed directly to Step 3c** (warehouse spilling check) before deciding whether to stop.

- If Step 3c finds a warehouse issue → continue to Step 4 presenting only the `WAREHOUSE_TOO_SMALL` recommendation.
- If Step 3c also finds nothing → **stop here**. Do **not** compose or apply any DDL, do **not** route anywhere automatically. Emit this message as your final natural-language response before ending the turn:

> Snowflake has no recommendations for this dynamic table right now, and I found no issues in recent refresh history, so there's nothing to apply here. If you'd like, you can separately ask for general performance optimization — but I'll stop here.

Exiting is the correct, complete outcome when neither INFORMATION_SCHEMA recs nor refresh history issues are found; do **not** ask "Want me to do that?", and do **not** begin any other workflow.

**Only if the fetch query returns at least one recommendation row**, load the per-code handler files (below) and continue to Step 3 (all of 3a, 3b, and 3c).

**Load the per-code handler files.** For each `code` returned by the fetch query, load its handler file `references/codes/<CODE>.md` (the index table in [references/recommendation-codes.md — Codes](references/recommendation-codes.md#codes) maps each code to its file). Load only the files for the codes that are actually present — Steps 4 and 5 read the handler details from these files.

---

### Step 3: Capture health-signal baseline

**Goal:** record the dynamic table's current performance posture so Step 4 can frame recommendations correctly and Step 7 can compare post-change. **Run this step's queries silently too** — same as Step 2, no per-query narration; save the results and carry them into Step 4.

Run both queries below and save the results as the **baseline**.

**(a) Target-lag breach:** run the canonical target-lag breach query from [references/recommendation-codes.md — Health-signal queries](references/recommendation-codes.md#health-signal-queries) with `NAME => '<DB>.<SCHEMA>.<DT>'`. Select only the columns that query lists — `INFORMATION_SCHEMA.DYNAMIC_TABLES()` has no `target_lag` (string) or `refresh_mode` column, so don't add them here (get those from `SHOW DYNAMIC TABLES` if needed).

Breach indicator: `time_within_target_lag_ratio < 1.0`.

**Skip the breach check entirely when the lag type is DOWNSTREAM.** A DT whose `target_lag_type` is `DOWNSTREAM` has no fixed target — it refreshes only when downstream consumers need fresh data — so `target_lag_sec` and `time_within_target_lag_ratio` are both `NULL` and there is no meaningful "breach" to compute. Detect this case from the query result: if `target_lag_type = 'DOWNSTREAM'` (equivalently `target_lag_sec IS NULL`), set `lag_breach = NULL` (not `FALSE`) and move on. Detect it from `target_lag_type` / `target_lag_sec`, not by comparing a `target_lag` string to `'DOWNSTREAM'` (that column isn't on this function). Don't treat NULL as "no breach", and don't synthesize a breach signal from `mean_lag_sec` or `maximum_lag_sec` against an arbitrary threshold — those numbers reflect downstream demand, not a target violation.

For all other DTs (with a time-based `TARGET_LAG`), use the breach indicator above.

**(a.i) Lag source attribution (run when `lag_breach = TRUE`):**

A lag breach does not necessarily mean the DT's own query is slow. If even the slowest recent refresh completes within the target lag interval, the breach is caused by upstream delays — not by the DT's own work — and investigating this DT's recommendations will not fix the problem.

Compute the DT's maximum refresh duration over the same 7-day window, and get `target_lag_sec` from the graph history:

```sql
-- Maximum refresh duration (last 7 days, SUCCEEDED non-NO_DATA refreshes)
SELECT
  MAX(DATEDIFF('second', refresh_start_time, refresh_end_time)) AS max_duration_sec,
  COUNT(*) AS refresh_count
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
    NAME => '<DB>.<SCHEMA>.<DT>'
))
WHERE state = 'SUCCEEDED'
  AND refresh_action != 'NO_DATA'
  AND refresh_start_time >= DATEADD('day', -7, CURRENT_TIMESTAMP());

-- Target lag for this DT (current config)
SELECT target_lag_sec, target_lag_type
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_GRAPH_HISTORY())
WHERE name = '<DT>'
  AND valid_to IS NULL;
```

**If `max_duration_sec < target_lag_sec`** (and `refresh_count > 0`): even the slowest refresh completed within the target window — the breach is upstream. Identify upstream DTs via the graph:

```sql
SELECT f.value:name::STRING AS upstream_fqn,
       f.value:kind::STRING AS upstream_kind
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_GRAPH_HISTORY()),
     LATERAL FLATTEN(INPUT => inputs) f
WHERE name    = '<DT>'
  AND valid_to IS NULL;
```

Filter to rows where `upstream_kind = 'DYNAMIC TABLE'`. For each upstream DT, run the canonical lag breach query from Step 3a to get its `time_within_target_lag_ratio` and `maximum_lag_sec`, and look up its `target_lag_type` from `TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_GRAPH_HISTORY())` (`WHERE name = '<UPSTREAM_DT>' AND valid_to IS NULL`).

**If no upstream DTs are found** (all sources are base tables or views): tell the customer that even the slowest refresh finished within the target window but all upstream sources are base tables, so the most likely cause is high-frequency or high-volume writes to those base tables. Continue the current investigation as-is.

Separate upstream DTs into two groups based on their `target_lag_type`:

- **Fixed-lag** (`target_lag_type != 'DOWNSTREAM'`): these have a measurable `time_within_target_lag_ratio`. Run the canonical lag breach query from Step 3a for each to obtain their `time_within_target_lag_ratio` and `maximum_lag_sec`.
- **DOWNSTREAM** (`target_lag_type = 'DOWNSTREAM'`): these refresh on-demand with no fixed target; `time_within_target_lag_ratio` is NULL. For these, compute `avg_duration_sec` using `AVG(DATEDIFF('second', refresh_start_time, refresh_end_time))` from `DYNAMIC_TABLE_REFRESH_HISTORY` (same 7-day SUCCEEDED non-NO_DATA filter).

**Primary check — fixed-lag upstream DTs:** Rank them by `time_within_target_lag_ratio ASC` (most-breaching first), ties broken by `maximum_lag_sec DESC`. If any are breaching (`time_within_target_lag_ratio < 1.0`), the top-ranked is the most likely cause. Present the finding and ask:

> `<DT>`'s slowest recent refresh took ~`<max_duration_sec>`s, well under its `<target_lag_sec>`s target — so its own query is not the bottleneck. The lag breach is most likely propagating from upstream. The upstream DT most likely responsible is **`<UPSTREAM_DT>`** (meeting its target lag only `<X>`% of the time, maximum lag `<Y>`s).
>
> Would you like me to run the recommendations investigation on `<UPSTREAM_DT>` instead?

**Fallback — DOWNSTREAM upstream DTs (only when all fixed-lag upstream DTs are healthy):** If all fixed-lag upstream DTs have `time_within_target_lag_ratio >= 1.0` (or there are no fixed-lag upstream DTs), look at DOWNSTREAM upstream DTs. Rank them by `avg_duration_sec DESC` — the one with the longest average refresh time is the most likely source of delay. Present the finding and ask:

> `<DT>`'s slowest recent refresh took ~`<max_duration_sec>`s, well under its `<target_lag_sec>`s target. All upstream DTs with a fixed target lag are currently healthy. However, an upstream DT with a DOWNSTREAM lag type (**`<UPSTREAM_DT>`**) has an average refresh time of ~`<Z>`s and may be introducing delay.
>
> Would you like me to run the recommendations investigation on `<UPSTREAM_DT>` instead?

If the customer says **yes**: re-enter the workflow from Step 1 with `<UPSTREAM_DT>` as the new target, following the investigation isolation rule — this is a fresh investigation with no carryover from the current one.

If the customer says **no**: continue the current investigation as-is, noting that fixing `<DT>`'s recommendations is unlikely to resolve the lag breach since the bottleneck is upstream.

**If `max_duration_sec >= target_lag_sec`**, or if no SUCCEEDED non-NO_DATA refreshes exist in the window: the DT's own refresh is the bottleneck — continue as normal.

**(b) Cost of refreshes (last 7 days):**

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

To get the 7-day total for the threshold check, wrap the above in an aggregate:

```sql
WITH per_refresh AS ( /* the query above, without ORDER BY */ )
SELECT
    SUM(credits_consumed)                       AS est_credits_7d,
    SUM(credits_consumed) * <USD_PER_CREDIT>    AS est_cost_usd_7d
FROM per_refresh;
```

Default heuristic: `est_cost_usd_7d > $10`. **This threshold is a deliberately rough starter** — tunable here in one place. Refine as operational experience accumulates (the right value depends on the customer's overall pipeline cost profile, not a universal number).

**Caveats on the cost query:**

- `ACCOUNT_USAGE` views have a propagation latency (typically 45 min – 3 hours). Refreshes that just completed will not appear yet.
- `credits_attributed_compute` may be `NULL` for very small refreshes on small warehouses where Snowflake didn't attribute credits at the per-query level. Treat NULL as "negligible".
- If the customer's role lacks `IMPORTED PRIVILEGES on SNOWFLAKE` (so `ACCOUNT_USAGE` is unavailable), or `<USD_PER_CREDIT>` is unknown, don't block — fall through to the prompt-based override below.

**Handle no-refresh-history DTs.** A freshly-created dynamic table will have no refreshes yet, so the cost query returns `NULL` and the lag-ratio is undefined. In that case, tell the customer:

> Your dynamic table hasn't run any refreshes yet, so I can't measure its cost or lag. Snowflake will keep generating recommendations as the dynamic table runs — additional ones (especially refresh-time ones) may appear later. For now, I'll work with whatever recommendations are already available.

Then proceed to Step 4 (Build and present the plan) treating the DT as having no measurable performance issue (unless the prompt-based override below applies).

**(c) Warehouse spilling check (ALWAYS run — even when no INFORMATION_SCHEMA recs):**

Follow the detection procedure in [`references/codes/WAREHOUSE_TOO_SMALL.md`](references/codes/WAREHOUSE_TOO_SMALL.md) (Steps 1–3 of that file). Record whether the check triggered (`warehouse_issue = TRUE/FALSE`). If it triggered, also record `<CURRENT_WH>`, `<CURRENT_WH_SIZE>`, and the spilling evidence (spilling refresh count, local bytes spilled — remote-storage spill is disregarded when QAS is enabled, per the per-code file — and duration comparison). If neither data source is accessible (privilege error on both), set `warehouse_issue = FALSE` and skip silently.

**If no INFORMATION_SCHEMA recs were found (Step 2 returned zero rows) AND `warehouse_issue = FALSE`:** stop here per the Step 2 gate above.

**If no INFORMATION_SCHEMA recs were found AND `warehouse_issue = TRUE`:** continue to Step 4 with only the `WAREHOUSE_TOO_SMALL` recommendation to present. In this case Steps 3a and 3b were skipped, so `lag_breach = NULL`, `cost_breach = NULL`, and the performance-issue determination is driven solely by the customer's stated problem (prompt-based override), or defaults to "no issue" if the customer gave no such signal.

---

**Determine whether the DT has a measurable performance issue.** Treat a NULL lag-breach (i.e. `TARGET_LAG = DOWNSTREAM`, where breach is undefined) as "not contributing":

```
lag_breach  = (target_lag_sec IS NOT NULL) AND (time_within_target_lag_ratio < 1.0)
cost_breach = (est_cost_usd_7d > 10)
has_issue   = COALESCE(lag_breach, FALSE) OR COALESCE(cost_breach, FALSE)
```

**Prompt-based override.** If the customer's request itself signals a problem — e.g. "my DT is too slow", "my DT is too expensive", "this is killing my warehouse credits", "refresh keeps timing out" — treat `has_issue` as true regardless of the query results. The customer telling you something is wrong is itself the strongest health signal.

When `has_issue = TRUE`, frame recommendations assertively in Step 4 (the DT is visibly struggling). When `has_issue = FALSE`, the DT is healthy — frame the recommendations as strictly optional and make clear that **taking no action is a perfectly fine outcome**: the DT is running well (and, when cost is low, cheaply), so it does not need changing. Do not imply the customer should apply them; a healthy, cheap DT the customer is happy with is best left as-is unless they expect a large increase in data volume.

---

### Step 4: Build and present the plan

**Goal:** silently resolve every per-code specific, then present **one** plan and get a single batched decision — replaces the old per-code walk-through with the format defined in [references/recommendation-codes.md — Plan presentation contract](references/recommendation-codes.md#plan-presentation-contract-step-4).

**4a — Resolve per-code specifics silently.** Before rendering anything, work out — without narrating the process — everything Step 4's plan entry and Step 5's DDL will need:

- For `HIGH_BASE_TABLE_CHANGES` / `CHANGED_BASE_TABLES_UNDER_JOIN`: the already-`ADAPTIVE` check (`SHOW DYNAMIC TABLES` + `RESULT_SCAN` for `refresh_mode`, not `GET_DDL`) and, for `HIGH_BASE_TABLE_CHANGES`, the overwrite-frequency pre-check (recommendation `info` magnitude + cross-refresh consistency from `DYNAMIC_TABLE_REFRESH_HISTORY`) that decides whether `ADAPTIVE` is worth offering at all. **The resolution runs silently, but its outcome doesn't stay silent when it changes the menu:** if the DT is already `ADAPTIVE`, don't just quietly drop that choice from the entry — the `Why` line must say so explicitly (e.g. "...already ADAPTIVE, so only the decomposition/primary-key option applies"). Same for majority-overwrite ruling out `ADAPTIVE` in `HIGH_BASE_TABLE_CHANGES` — name the reason, don't just omit the option.
- For `QUALIFY_RANK_KEYS_NOT_PERSISTED` / `TOP_LEVEL_AGGREGATE_EXPRESSIONS_NOT_PERSISTED`: whether an escape case applies (missing keys unresolvable from `info` or `GET_DDL`).
- For `QUALIFY_RANK_NOT_TOP_LEVEL`: which sub-case applies (split vs. the guarded in-place `ORDER BY` drop vs. "anything else") per its per-code file.
- For the synthetic `WAREHOUSE_TOO_SMALL` (Step 3c's `warehouse_issue = TRUE`): whether it belongs in the selectable plan at all, per [`references/codes/WAREHOUSE_TOO_SMALL.md`](references/codes/WAREHOUSE_TOO_SMALL.md) Step 4 — when **no other actionable INFORMATION_SCHEMA codes** are present (or the rest are `manual`/informational), include it as **STRONGLY RECOMMENDED** with the spilling evidence in the `Why` line; when **other `implemented` codes with real DDL** are also present, **leave it out of the selectable list** and instead fold the spilling finding into that entry's `Why` as context (recommend applying the other fixes first, monitoring, and revisiting the warehouse size only if spilling persists) — if the customer explicitly asks for the warehouse upgrade anyway, honor it and proceed with Steps 7–8 of the per-code file.
- Ordering: when both `HIGH_BASE_TABLE_CHANGES` and `CHANGED_BASE_TABLES_UNDER_JOIN` are present, list `HIGH_BASE_TABLE_CHANGES` first and fold `CHANGED_BASE_TABLES_UNDER_JOIN` into it as a one-line dependent note (its `plan_why` should say it's likely driven by the same churn) rather than a separate top-level entry — the base-table fix is addressed first because it's the more likely root cause.

None of this produces customer-visible output yet — it only determines what the plan (4b) says.

**4b — Render the plan once.** Use the template and rules in [references/recommendation-codes.md — Plan presentation contract](references/recommendation-codes.md#plan-presentation-contract-step-4): a one-sentence `has_issue` framing, then one numbered entry per returned code (`plan_summary` + `plan_why`, tagged automatic fix / needs your confirmation / informational only). `manual` codes are listed too (tagged "informational only") so the customer sees full coverage. **For a multi-option code, this entry describes only its single preferred default option** — never a "pick one" menu; the alternative (or, for combinable options, the add-on) is raised later in Step 5, one at a time, only if needed. **Exception:** if the customer's own request explicitly asked what their options are (not just "apply the fix"), still lead with the default, but name the other viable option(s) in a short trailing clause — see the disclosure exception in [references/recommendation-codes.md — Plan presentation contract](references/recommendation-codes.md#plan-presentation-contract-step-4). Otherwise a customer who only asked to be advised, and is never taken to Step 5, would never learn an alternative existed.

**When `has_issue = FALSE` specifically, the plan must make clear that doing nothing is a perfectly good outcome** — don't just soften the framing, say so explicitly, and don't imply the customer should apply anything. Set the cost figure from the DT's **actual** 7-day cost (don't assume `has_issue = FALSE` means cheap — it only means under the breach threshold), and handle the `TARGET_LAG = DOWNSTREAM` case (no fixed lag to "meet") — see [references/recommendation-codes.md — Plan presentation contract](references/recommendation-codes.md#plan-presentation-contract-step-4) for the exact wording and these two variants.

**⚠️ MANDATORY STOPPING POINT:** end with a single batched question — which of these to go ahead with (all / a subset / none). Wait for one explicit reply covering all of it. This replaces the old separate "which recommendations" question. Multi-option follow-ups (declining a default, being offered its alternative or add-on) are separate, later stopping points in Step 5 — not resolved here.

**This message is never skipped, shortened to an acknowledgment, or merged into Step 5 — no matter how much approval the customer's own request already contains.** A customer who already says "apply the fix," names the exact code, gives blanket DDL approval ("I approve running any DDL changes you recommend"), or is in a headless auto-accept session has answered *whether* to proceed — that is not the same as having been told *what* the fix is or *why* it's needed, and it never substitutes for the disclosure. Compose no DDL and show no DDL until the numbered `plan_summary` + `Why: <plan_why>` text for every returned code has been rendered as its own customer-facing message. In particular, do not jump straight from Step 3's silent analysis to Step 5's DDL composition with something like *"I'll take that as selecting `<CODE>` — let me compose the fix"* — that skips the one message whose entire purpose is explaining the diagnosis. Pre-existing approval can shorten or eliminate the *wait* for a reply (see Headless / Auto-Apply Mode above for exactly which cases), but it can never eliminate the plan text itself.

---

### Step 5: Resolve remaining inputs and compose DDL

**Goal:** for everything the customer accepted in Step 4, silently compose the DDL, and ask permission **only** immediately before something that touches the account — a live-data validation query, or presenting DDL for the run-approval in Step 6. Whether it's already `ADAPTIVE`, or an escape case applies, was already resolved in Step 4's 4a — this step composes against those resolved facts, it doesn't re-ask. **Multi-option codes are the one thing still resolved here, not in Step 4** — see the sequential-ask bullet below.

**Multi-option codes (`HIGH_BASE_TABLE_CHANGES`, `CHANGED_BASE_TABLES_UNDER_JOIN`): resolve *which* option(s) to include one at a time, never as a menu — but this is a plain-language decision, not a DDL preview.** The Step 4 plan already named the default option (per the per-code file's preference order). Here, in plain language (no SQL, no disclaimer yet — those come once, later, when everything gets composed and shown together per *Compose the DDL(s)* below):
1. Confirm the default in plain language — a short, specific yes/no framed around what the fix does (e.g. "Want me to switch this to ADAPTIVE?"), not its SQL. **This is the same run-approval gate every other code goes through, not an extra one** — it's already satisfied, and this ask should be skipped, when either: (a) the customer's original request named this exact fix and approved it specifically (e.g. they described the diagnosis themselves and said to apply the best fix for it), **or** (b) the customer explicitly delegated ongoing authority without needing to name the mechanism (e.g. "handle everything", "I approve any DDL changes and any verification queries needed") — see the *generic blanket approval* rule and its delegation-of-authority exception in the *Headless / Auto-Apply Mode* section above (this exception isn't only for headless mode — it applies to interactive requests phrased that way too). Either way, don't manufacture a round-trip re-asking something already answered. A live-data check (if this default needs one) is separately, always mandatory — see the bullet below — but a pending check doesn't mean the fix itself is unapproved.
2. If **declined** and the code's options are **mutually exclusive** (`CHANGED_BASE_TABLES_UNDER_JOIN`), offer the next option in preference order the same way — plain language, its own why, a fresh yes/no. Stop once one is accepted or all options are exhausted.
3. If the code's options are **combinable** (`HIGH_BASE_TABLE_CHANGES`'s `ADAPTIVE` switch and base-table primary key), the default's outcome (accepted or declined) doesn't answer the other option — ask about it separately, plain language, framed as an *additional* fix, not a substitute. **This ask needs its own real answer, not silent inclusion.** A blanket approval the customer gave earlier ("apply the best fix", "I approve any DDL you recommend") was necessarily a response to the *default* — the add-on wasn't described yet when they said it, so it doesn't carry over (mirrors the *generic blanket approval* rule: approval given before a specific fix was described doesn't cover that fix). Default to **mentioning the add-on is available and why, without including it**, unless the customer's own message separately and specifically asked for it too, or clearly pre-approves going beyond just the default recommendation (e.g. "handle everything, including anything else that would help"). Don't add it just because it's generally beneficial and DDL is broadly pre-approved — an unprompted `CREATE OR REPLACE` recreate is a real cost (full recompute, reset history) the customer didn't specifically sign up for.

Never bundle two options into one ask ("want ADAPTIVE, the primary key, or both?") — each gets its own turn. **But never show DDL at this stage either, for any option, default or alternative** — these plain-language exchanges only decide the *set* of fixes going into the DT; once every code (multi-option or not) is resolved to an accept/decline, move to *Compose the DDL(s)* below and show the customer the **one, final, fully-composed** statement — they review a real definition change exactly once, however many codes or options it took to get there, never a running series of "here's a new version, approve this too."

The skill still emits **one or more `CREATE OR ALTER DYNAMIC TABLE` statements — one per resulting dynamic table** (never multiple statements for the same `<DT>`; a split handler produces a producer statement plus a consumer statement that keeps the original `<DT>`'s name), and still composes multiple selected recipes together into one statement when they land on the same resulting DT. All of that composition logic is unchanged — see [references/recommendation-codes.md — DDL composition](references/recommendation-codes.md#ddl-composition) for the full rules (preserve `TARGET_LAG`/`WAREHOUSE`/`INITIALIZE`/`FROZEN WHERE`/etc.; `CREATE OR ALTER` always except the single sanctioned `CREATE OR REPLACE` for base-table-PK adoption; new producer DTs get `REFRESH_MODE = ADAPTIVE`, never `AUTO`).

For each accepted code, using its per-code handler file (loaded in Step 2):

- **`implemented`, escape case applies** (e.g. `QUALIFY_RANK_KEYS_NOT_PERSISTED` / `TOP_LEVEL_AGGREGATE_EXPRESSIONS_NOT_PERSISTED` when the key can't be safely reproduced) — compose no DDL; deliver the per-code escape-case guidance concisely instead.
- **`implemented`, live-data check required** (PK-uniqueness pre-check for `HIGH_BASE_TABLE_CHANGES` Option 2) — ask permission right before running it, tersely (e.g. "I need to check `<cols>` are actually unique on `<table>` — OK to run a read-only scan?"), not as a paragraph explaining why the check exists (the customer already saw the one-line reason in the Step 4 plan). This approval can't be inferred from an earlier or *unrelated* approval — but it **is** satisfied if the customer's original request already named this exact fix (the table, the key column(s), "apply the best fix" or equivalent) with a blanket approval covering it; the check is an inseparable step of delivering that fix, not an independent action needing its own round-trip (see [references/primary-key-rely.md](references/primary-key-rely.md)). Only proceed to compose/apply the dependent DDL if the check passes; if it fails, surface the discrepancy and stop for that code.
- **`WAREHOUSE_TOO_SMALL`** — if a target warehouse wasn't already implied, ask the customer to pick one from the existing same-tier warehouses or have you create one (`references/codes/WAREHOUSE_TOO_SMALL.md` Steps 7–8); this is a genuine input, not narration, so it still needs a real answer. Fold into the same `CREATE OR ALTER` as other DDL when both apply (Case A); otherwise a standalone `ALTER DYNAMIC TABLE ... SET WAREHOUSE` (Case B).
- **`manual`** — no DDL. Deliver the guidance concisely and dispatch on `routes_to_on_manual`: a named sub-skill (most manual codes → `../dynamic-tables/optimize/SKILL.md`) gets an explicit, named hand-off in one sentence; `none` (currently `AUTO_RESOLVED_TO_FULL_REFRESH`, `EXPENSIVE_ORDER_DEPENDENT_WINDOW_FUNCTION`) delivers that handler's own explanation directly, no routing.

**Compose the DDL(s)**: `GET_DDL('DYNAMIC_TABLE', '<DB>.<SCHEMA>.<DT>')` as the seed, apply each accepted handler's `ddl_transformation` in turn, emit the resulting statement(s).

**Presentation order is always action → explanation → approval ask: the DDL first, then its one-line caveat, then "Want me to run it?"** Never lead with the caveat — the customer needs to see what will run before reading why to be careful with it.

**In interactive mode:** present the composed DDL (batched across all resulting DTs from this round), then immediately below it:
- the one-line disclaimer from [references/recommendation-codes.md](references/recommendation-codes.md#ddl-composition), whenever a resulting DT's `SELECT` differs from the original and isn't a structural exception (settings-only change, or `QUALIFY_RANK_NOT_TOP_LEVEL`'s guarded `ORDER BY` drop with no `LIMIT`/`FETCH`/`OFFSET`/`TOP`) — for a structural exception, say in one clause that the body is unchanged / equivalent by construction instead; `QUALIFY_RANK_KEYS_NOT_PERSISTED` / `TOP_LEVEL_AGGREGATE_EXPRESSIONS_NOT_PERSISTED` are not structural exceptions, so they get this disclaimer too;
- for `QUALIFY_RANK_KEYS_NOT_PERSISTED` / `TOP_LEVEL_AGGREGATE_EXPRESSIONS_NOT_PERSISTED` specifically, also add a one-line schema-change confirmation *alongside* the disclaimer above (not instead of it) — state plainly that it adds output columns, and for `TOP_LEVEL_AGGREGATE_EXPRESSIONS_NOT_PERSISTED` specifically that it forces a full reinitialize (state this now, before running — not only in Step 7);
- a one-line reminder that each affected DT — and anything downstream of it — fully recomputes once after the change;

**Tag every DDL statement composed here** — `CREATE OR ALTER`, the PK-adoption `CREATE OR REPLACE`, the standalone `ALTER DYNAMIC TABLE ... SET WAREHOUSE`/`SET INITIALIZATION_WAREHOUSE`, and the base-table `ALTER TABLE ... ADD PRIMARY KEY ... RELY` alike — with a trailing `/* Generated by Snowflake CoCo DT recommendations skill: <CODE1>[, <CODE2>, ...] */` comment immediately before the semicolon, naming the code(s) that statement applies. See [references/recommendation-codes.md — DDL tagging](references/recommendation-codes.md#ddl-composition) for the exact format.

then ask "Want me to run it?"

**⚠️ Headless / auto-apply carve-out unchanged:** settings-only changes and the guarded `ORDER BY` drop skip straight to Step 6 execution (per *Headless / Auto-Apply Mode*) — no disclaimer, no run-approval ask, just execute. Every other recipe (any split/decomposition, or a rewrite without a static-by-construction proof) **always** shows the DDL + disclaimer, in that order, and waits for an explicit approval turn to *this specific fix*, in every mode — apply intent, `auto-accept plans: true`, and a generic blanket approval given before this fix was ever described do not satisfy that; a clear "yes" to the fix as described does, with no extra round-trip needed after the literal SQL is rendered.

---

### Step 6: Execute

**Goal:** run the DDL.

Execute each `CREATE OR ALTER DYNAMIC TABLE` statement in order (producer DT before consumer DT when a handler splits the dynamic table). Surface any errors verbatim — do not retry automatically. Every statement executed here — including the standalone `ALTER DYNAMIC TABLE ... SET WAREHOUSE` (Step 5's `WAREHOUSE_TOO_SMALL` case B) and the base-table `ALTER TABLE ... ADD PRIMARY KEY ... RELY` below — must already carry its trailing `/* Generated by Snowflake CoCo DT recommendations skill: <CODE(s)> */` tag from Step 5; do not strip it before running.

**Split/decomposition DDL only executes after the customer has explicitly approved this specific fix in this conversation.** Headless mode and apply intent do not supply that approval by themselves for these recipes (see the *Headless / Auto-Apply Mode* carve-out) — if you have not yet described the fix (and shown the disclaimer) and gotten an explicit yes to it, go back to Step 5 instead of executing. **A generic "I approve any DDL changes" said earlier in the conversation, before this fix was ever described, is not that yes** — it wasn't a response to anything specific, so it isn't approval of this. Treat it the same as no approval at all. But once the customer has clearly approved the described fix (e.g. "yes, go ahead and split it"), that is enough — you do not need a further round-trip after composing the literal SQL just to re-confirm it.

**Ordering for `HIGH_BASE_TABLE_CHANGES` Option 2 (base-table primary key):** (0) with the customer's OK, run the read-only uniqueness check on the proposed key and confirm it passes (zero duplicates, zero NULL keys) — if it fails, do **not** create the key; then (1) run the `ALTER TABLE <base> ADD PRIMARY KEY (...) RELY` (tagged `/* Generated by Snowflake CoCo DT recommendations skill: HIGH_BASE_TABLE_CHANGES */` at the end, before the semicolon), and (2) recreate the DT with `CREATE OR REPLACE DYNAMIC TABLE <DT> ...` (same tag, same placement) — the recompile must see the key already in place, or the DT will not adopt it. (When Option 2 is applied together with the Option 1 `ADAPTIVE` switch, run the `ALTER TABLE` first, then the single `CREATE OR ALTER` that switches `REFRESH_MODE` — that reinitialization adopts the key, so no `CREATE OR REPLACE` is needed.)

For any selected `manual` handler, **do not apply anything** — dispatch on its `routes_to_on_manual`. If it **names a sub-skill** (the `optimize/` workflow at `../dynamic-tables/optimize/SKILL.md` for most manual codes), **explicitly route** the customer there, **naming it in your message**: say plainly that you're handing it to the `optimize/` workflow (it has no automated fix) and pass the relevant context (DT name, baseline metrics from Step 3, the `code` and `info` from Step 2). If it is **`none`** (a self-contained informational handler, currently `AUTO_RESOLVED_TO_FULL_REFRESH` and `EXPENSIVE_ORDER_DEPENDENT_WINDOW_FUNCTION`), deliver that handler's explanation **directly** and do not route. Never offer to compose or run a DDL fix for a manual code.

---

### Step 7: Verify

**Goal:** wrap up with **one short, neutral paragraph** — not a five-point list — that still carries every required point below.

**Authoring guard — do NOT phrase Step 7 as a success claim.** Do not assert that performance has improved or will improve. Outcomes can only be validated by observing further refreshes.

Use the compact template from [references/recommendation-codes.md — Verification language](references/recommendation-codes.md#verification-language-for-step-7-of-the-sub-skill) as your final natural-language response (not a tool call or a terse echo). It must contain:

1. In substance: the DDL has been applied. If the fix added output columns, name them: `QUALIFY_RANK_KEYS_NOT_PERSISTED` appends ordinary columns (mention `SELECT *` consumers will now see them); `TOP_LEVEL_AGGREGATE_EXPRESSIONS_NOT_PERSISTED` forces a full reinitialize (restate, don't newly introduce, what Step 5 already disclosed).
2. **Verbatim, not paraphrased:** the phrase **"may take time to update"** (recommendations column caveat).
3. **Verbatim, not paraphrased:** both **"running the dynamic table further"** and **"monitor refresh times"** (improvement isn't guaranteed) — use these exact words even if a synonym reads more naturally in context; this wording is load-bearing, not decorative.
4. The comparison query, parameterized for a post-change window, with the Step 3 baseline values named so the customer knows what to compare against:

   ```sql
   -- Run this after several refresh cycles have completed post-change.
   -- See ../dynamic-tables/references/dt-refresh-analysis.md for the full canonical query.
   SELECT
     name,
     COUNT(*)                         AS total_refreshes,
     AVG(IFF(refresh_action IN ('INCREMENTAL','FULL') AND refresh_trigger != 'CREATION',
             DATEDIFF('second', refresh_start_time, refresh_end_time), NULL))  AS avg_duration_sec,
     PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY
           IFF(refresh_action IN ('INCREMENTAL','FULL') AND refresh_trigger != 'CREATION',
               DATEDIFF('second', refresh_start_time, refresh_end_time), NULL)) AS p50_duration_sec,
     PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY
           IFF(refresh_action IN ('INCREMENTAL','FULL') AND refresh_trigger != 'CREATION',
               DATEDIFF('second', refresh_start_time, refresh_end_time), NULL)) AS p95_duration_sec,
     COUNT_IF(refresh_action = 'INCREMENTAL' AND refresh_trigger != 'CREATION')  AS incremental_count,
     COUNT_IF(refresh_action = 'FULL'        AND refresh_trigger != 'CREATION')  AS full_count
   FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(NAME => '<DB>.<SCHEMA>.<DT>'))
   WHERE refresh_start_time > '<DDL_APPLIED_AT>'
   GROUP BY name;
   ```

5. The escalation path: revisit with `optimize/` if refresh times don't improve over a meaningful number of cycles.

**Append one sentence per code, if applicable, whether or not DDL was applied for it:**
- `HIGH_BASE_TABLE_CHANGES` and/or `CHANGED_BASE_TABLES_UNDER_JOIN` were in play (any outcome — fixed, declined, or already `ADAPTIVE`) → tell the customer to **investigate** the source / upstream load pattern of the churn; the remediation only mitigates refresh cost, it doesn't address why the data churns. Use the word "investigate" (or "look into" / "dig into") literally — don't soften it into "worth confirming" or "it's expected and understood"; those don't convey that this needs active follow-up.
- A base-table primary key was proposed or applied (`HIGH_BASE_TABLE_CHANGES` Option 2) → repeat that the key must be genuinely unique (`RELY` is unenforced) and only takes effect after the recreate.

---

## Stopping Points Summary

1. ✋ Init Step 1: both core references (`sql-syntax.md`, `monitoring-functions.md`) loaded.
2. ✋ Init Step 2: session context (account / region / user / role) confirmed.
3. ✋ Step 1: dynamic table identifier confirmed.
4. ✋ Step 2: if there are no INFORMATION_SCHEMA recommendations, skip Steps 3a/3b and proceed to Step 3c (warehouse check). Only STOP (with the informational message) if Step 3c also finds no issue.
5. ✋ Step 4: **one** batched stopping point — customer has replied to the single plan message with which recommendations to apply (subset, all, or none). Multi-option codes show only their default here; the choice among options is not asked yet.
6. ✋ Step 5: for a multi-option code's default option, an explicit yes/no on that specific option. If declined (mutually exclusive) or in addition (combinable), a further explicit yes/no on the next option — presented one at a time, never as a combined "pick one" menu.
7. ✋ Step 5: for any live-data validation query (PK-uniqueness pre-check), the customer has given explicit permission right before it runs — not inferred from an earlier or unrelated approval.
8. ✋ Step 5: customer has seen the one-line disclaimer (when applicable) and approved the composed `CREATE OR ALTER DYNAMIC TABLE` statement(s) before execution.
9. ✋ Step 5/6: for split/decomposition rewrites, headless auto-accept does **not** skip the DDL-approval step — always describe the specific fix + disclaim + wait for explicit approval, even with `auto-accept plans: true` and apply intent. A generic approval given before this specific fix was described does not count; a clear yes to the described fix does (no extra round-trip needed after composing the literal SQL).

**Resume rule:** only proceed after explicit user approval. Read-only diagnostic queries can run freely — the recommendations fetch (Step 2) first, and the baseline queries (Step 3) only once the Step 2 gate has confirmed at least one recommendation exists.

---

## Supported Recommendation Codes

This is the source-of-truth list of recommendation codes the skill handles. Adding a new code = appending one row here and adding one file in [references/codes/](references/codes/). The orchestration steps above do not need to change.

| Code | Customer-friendly summary | Reference |
|---|---|---|
| `QUALIFY_RANK_NOT_TOP_LEVEL` | `QUALIFY ... = 1` clause is nested instead of at the outermost SELECT — automated fix available | [codes/QUALIFY_RANK_NOT_TOP_LEVEL.md](references/codes/QUALIFY_RANK_NOT_TOP_LEVEL.md) |
| `TOP_LEVEL_AGGREGATE_NOT_TOP_LEVEL` | `GROUP BY` + aggregate is nested inside a CTE or subquery instead of the outermost SELECT — automated fix available | [codes/TOP_LEVEL_AGGREGATE_NOT_TOP_LEVEL.md](references/codes/TOP_LEVEL_AGGREGATE_NOT_TOP_LEVEL.md) |
| `QUALIFY_RANK_KEYS_NOT_PERSISTED` | `PARTITION BY` / `ORDER BY` keys of a top-level `QUALIFY ... = 1` are not exposed as output columns — automated fix adds them (changes the output schema) | [codes/QUALIFY_RANK_KEYS_NOT_PERSISTED.md](references/codes/QUALIFY_RANK_KEYS_NOT_PERSISTED.md) |
| `TOP_LEVEL_AGGREGATE_EXPRESSIONS_NOT_PERSISTED` | Top-level `GROUP BY` aggregate's state-reuse optimization is blocked — some `GROUP BY` keys or aggregate expressions are missing from the DT output columns; automated fix adds them (changes the output schema) | [codes/TOP_LEVEL_AGGREGATE_EXPRESSIONS_NOT_PERSISTED.md](references/codes/TOP_LEVEL_AGGREGATE_EXPRESSIONS_NOT_PERSISTED.md) |
| `AUTO_RESOLVED_TO_FULL_REFRESH` | DT requested `REFRESH_MODE = AUTO` and resolved to `FULL` — either the query isn't incrementalizable, or AUTO's conservative heuristic chose FULL for a query that *is*. Handler surfaces the engine's reason and gives case-specific guidance: suggest trying explicit `REFRESH_MODE = ADAPTIVE` (incrementalizable case) or point to the supported-queries docs for restructuring (structural case) — no automated DDL; self-contained informational handler | [codes/AUTO_RESOLVED_TO_FULL_REFRESH.md](references/codes/AUTO_RESOLVED_TO_FULL_REFRESH.md) |
| `EXPENSIVE_ORDER_DEPENDENT_WINDOW_FUNCTION` | Order-dependent window function (`LEAD`, `LAG`, `LAST_VALUE`, `NTILE`, `NTH_VALUE`) in incremental mode — informational: explains that incremental refresh re-evaluates whole window partitions; no automated DDL, self-contained (no routing) | [codes/EXPENSIVE_ORDER_DEPENDENT_WINDOW_FUNCTION.md](references/codes/EXPENSIVE_ORDER_DEPENDENT_WINDOW_FUNCTION.md) |
| `NON_MONOTONIC_GROUPING_KEY` | Non-monotonic `GROUP BY` key (e.g. `HASH`) makes partition pruning ineffective during refresh — no automated DDL | [codes/NON_MONOTONIC_GROUPING_KEY.md](references/codes/NON_MONOTONIC_GROUPING_KEY.md) |
| `HIGH_BASE_TABLE_CHANGES` | Base table(s) churned heavily since the last refresh, so incremental no longer pays off — automated fix: switch to `REFRESH_MODE = ADAPTIVE` | [codes/HIGH_BASE_TABLE_CHANGES.md](references/codes/HIGH_BASE_TABLE_CHANGES.md) |
| `CHANGED_BASE_TABLES_UNDER_JOIN` | Too many / too-large changing inputs under a join — automated fix: customer chooses `REFRESH_MODE = ADAPTIVE` **or** decomposing the DT into 2–3-join fragments | [codes/CHANGED_BASE_TABLES_UNDER_JOIN.md](references/codes/CHANGED_BASE_TABLES_UNDER_JOIN.md) |
| `WAREHOUSE_TOO_SMALL` | ≥3 recent refreshes have memory-pressure spill (to **local** storage, or to **remote** storage when QAS is disabled) AND those refreshes are slower — warehouse is too small; automated fix: upgrade by one tier (detected via refresh + spilling history, not from INFORMATION_SCHEMA; remote-storage spill under QAS is ignored to avoid false positives) | [codes/WAREHOUSE_TOO_SMALL.md](references/codes/WAREHOUSE_TOO_SMALL.md) |
| `ICEBERG_BASE_TABLE_V2_TO_V3` | One or more Snowflake-managed Iceberg V2 base tables referenced by the DT — V2 has no change tracking, degrading incremental refresh performance; automated DDL fix: zero-downtime swap (CREATE V3 table → INSERT backfill → ALTER TABLE SWAP WITH → DROP old V2) | [codes/ICEBERG_BASE_TABLE_V2_TO_V3.md](references/codes/ICEBERG_BASE_TABLE_V2_TO_V3.md) |

Codes with no automated DDL fix route to `../dynamic-tables/optimize/SKILL.md` for follow-up, with the exception of `AUTO_RESOLVED_TO_FULL_REFRESH` and `EXPENSIVE_ORDER_DEPENDENT_WINDOW_FUNCTION`, which are self-contained informational handlers that deliver their explanation directly. `QUALIFY_RANK_KEYS_NOT_PERSISTED` and `TOP_LEVEL_AGGREGATE_EXPRESSIONS_NOT_PERSISTED` both have automated fixes but **add output columns** (a schema change): they require explicit approval of the column additions, are excluded from headless auto-apply, and fall back to routing to `optimize/` on their escape cases. See each per-code file for details.
