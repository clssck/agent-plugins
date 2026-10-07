# Query Set Summary

**This is a Phase 1 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Analyze a user-defined subset of queries — a workload. The user supplies one of:
- (a) explicit list of 2–1000 `query_id` values,
- (b) SQL `WHERE` fragment over `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` (with a time bound),
- (c) list of `query_parameterized_hash` values (with a time bound).

Resolve the input to a `query_id` list, derive the analysis scope (time window, warehouses, users, tables, query_types, duration roll-up, failure count), present a **scope card**, and STOP for confirmation before running any dimensional analysis.

## Background

The QUERY_SET entity is the user-scoped analog of ACCOUNT. It exists because most real workloads (a dashboard, an ETL batch, a tenant's queries, a release-day cohort) cross many warehouses and tables, so per-warehouse / per-table entities are too narrow, while ACCOUNT is too wide.

Scope is bounded by a **hard cap of 1,000 query_ids**. Bigger workloads must be narrowed by the user (tighter time window, tighter filter, fewer hashes).

## Prerequisites

- Exactly one of the three input forms above.
- Access to `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`, `QUERY_ACCELERATION_ELIGIBLE`, `TABLE_QUERY_PRUNING_HISTORY`, `COLUMN_QUERY_PRUNING_HISTORY`.

## Workflow

### Step 1: Resolve Input → query_id List

Branch on input form:

#### (a) Explicit list of query_ids

- Validate each is a UUID-shaped string.
- Validate `2 ≤ count ≤ 1000`. If `count = 1`, route to QUERY (or STORED_PROCEDURE if `query_type='CALL'`). If `count > 1000`, ask the user to narrow.
- No verified query needed — the list is already the resolution.

#### (b) SQL WHERE fragment over QUERY_HISTORY

- **[INPUT FORM]** The fragment is **literal SQL**, not natural language. The parent SKILL.md trigger examples ("queries by user X last week") are descriptive — the LLM must convert them to a literal SQL `WHERE` fragment (e.g. `user_name = 'X' AND start_time >= DATEADD('day', -7, CURRENT_DATE())`) before this step.
- **[VALIDATE]** Reject fragments containing `;`, DDL/DML keywords (CREATE/ALTER/DROP/INSERT/UPDATE/DELETE/MERGE/TRUNCATE/COPY), subqueries against tables other than `QUERY_HISTORY`, or UNION/JOIN clauses. Ask the user to resubmit if any of these appear.
- **[SECURITY]** Validation is best-effort string matching by the LLM, not robust SQL parsing. Bypass via `1=1`, `query_text ILIKE '%…%'` exfiltration patterns, scalar UDFs, or non-deterministic predicates is possible. **Run QUERY_SET filter form under a least-privileged role** (`SNOWFLAKE.USAGE_VIEWER` only). Future hardening will use `EXPLAIN`-based validation.
- **[DEFAULT TIME BOUND]** The verified query `Resolve query set from filter` is **unclamped** — it executes the user's `<USER_FILTER>` verbatim. The skill is responsible for the time-bound default:
  - Inspect `<USER_FILTER>` for the literal token `start_time` (case-insensitive). If absent, prepend `start_time >= DATEADD('day', -7, CURRENT_DATE()) AND ` to the fragment before substitution. **Always disclose** this default in the scope card ("Default time window applied: yes — last 7 days").
  - If the fragment already contains a `start_time` predicate, pass it through unchanged. Do NOT add an additional clamp.
- **[MANDATORY]** Fetch and execute verified query: `Resolve query set from filter` (substitutes `<USER_FILTER>`).
- The verified query is hard-capped at `LIMIT 1000` ordered by `start_time DESC`.

#### (c) Pattern hash list

- Require a time bound. If the user did not supply one, default to last 7 days and disclose.
- **[MANDATORY]** Fetch and execute verified query: `Resolve query set from pattern hashes` (substitutes `<HASH_LIST>`, `<SCOPE_START>`, `<SCOPE_END>`).
- Hard-capped at `LIMIT 1000` by `start_time DESC`.
- **Routing precedence:** 1 hash → route to QUERY_PATTERN entity instead. 2+ hashes → QUERY_SET.

After Step 1, capture:
- `<ID_LIST>` — the resolved query_ids.
- `<HASH_LIST>` — distinct `query_parameterized_hash` values from the resolved set.
- `truncated` — true if the resolution returned exactly 1000 rows AND the input form was filter/hash (callers can't distinguish "exactly 1000" from "1000+ truncated" without a separate count, so always assume `count = 1000` may be truncated and disclose).

If 0 rows resolve → **[STOP]** — explain possible causes:
- Input ids/hashes not in the look-back window (default 7 days; offer to expand).
- Filter too restrictive.
- ACCOUNT_USAGE 45-min latency.
- Outside 365-day retention.

### Step 2: Derive Analysis Scope

**[MANDATORY]** Fetch and execute verified query: `Derive scope from query set` (substitutes `<ID_LIST>`, `<SCOPE_START>`, `<SCOPE_END>`). Returns aggregated scope fields including warehouses (with sizes), users, query_types, distinct hashes, time window, duration roll-up, failure count.

Compute the touched-tables list:
- **[MANDATORY]** Fetch and execute verified query: `Derive scope tables from query set` (substitutes `<HASH_LIST>`, `<SCOPE_START>`, `<SCOPE_END>`).
- Top 10 tables by occurrence; mention total count.

### Step 3: Present the Scope Card

```
## Query Set Scope

**Input form:** explicit list (X ids) | filter (resolved X ids) | pattern hashes (resolved X ids)
**Default time window applied:** yes/no (last 7 days because no time bound supplied)
**Truncated at 1000-id cap:** yes / no

| Field | Value |
|---|---|
| Queries in set | X |
| Distinct patterns | X |
| Time window | T1 → T2 |
| Warehouses | WH1 (SIZE), WH2 (SIZE), … |
| Users | U1, U2, … |
| Query types | SELECT 312, INSERT 88, MERGE 12, … |
| Failures | X (Y%) |
| Total elapsed | Xs (compile X% / execute Y% / queue Z% / blocked W% / other R%) |
| Touched tables | DB.SCHEMA.T1, DB.SCHEMA.T2, … (top 10 of N) |
```

### Step 4: Confirm Scope and STOP

**[STOP]** Ask: "Does this scope look right? Say **'go'** to run the scoped performance analysis (spilling / pruning / cache / QAS / failures), or narrow the scope (tighter time, tighter filter, smaller hash list)."

Wait for confirmation before running Phase 2. This avoids costly fanout on a misinterpreted filter or unintended scope.

## Edge Cases

| Situation | Handling |
|---|---|
| Input is a single query_id | Reject; route to QUERY (or STORED_PROCEDURE if CALL) |
| Filter form with no time bound | Default to last 7 days; disclose in scope card |
| Hash form with no time bound | Default to last 7 days; disclose |
| 0 ids resolved | STOP and explain (latency, retention, filter too restrictive) |
| 1000 ids resolved | Surface "Truncated at 1000-id cap"; offer to narrow |
| All resolved ids are CALLs | Note that all rows are stored procedure CALLs; suggest STORED_PROCEDURE entity for tree analysis |
| All resolved ids on internal warehouses (COMPUTE_SERVICE_WH_*) | Flag as internal in the warehouse row; sizing recommendations not applicable |
| User-supplied filter rejected | Show the offending token and ask for a simpler predicate |

## Future hooks

- **STORED_PROCEDURE** call-tree leaves form a natural query_id list. The `stored-procedure/detection/SKILL.md` sub-skill can pass that list as input form (a) to QUERY_SET (wired in a future iteration).
- **MULTI_QUERY** (UI `${...}` context with multiple queries) can extract `query_id` values and delegate to QUERY_SET as input form (a) (wired in a future iteration).

## Known Limitations

Tracked for follow-up; documented here so users / agents do not assume they are silently handled:

- **Filter-form validation is LLM-prompt-only and bypassable.** Tautologies (`1=1`), `query_text ILIKE '%…%'` exfiltration patterns, scalar UDFs, non-deterministic predicates (`RANDOM()`) are not caught by the keyword-rejection list. Mitigation: run QUERY_SET filter form under a least-privileged role (`SNOWFLAKE.USAGE_VIEWER` only). Future hardening will use `EXPLAIN`-based validation or a column allow-list (`user_name`, `warehouse_name`, `query_type`, `database_name`, `schema_name`, `start_time`, `end_time`, `query_parameterized_hash`, `error_code`).
- **STORED_PROCEDURE → QUERY_SET handoff is not yet wired.** The `stored-procedure/detection/SKILL.md` sub-skill currently mentions delegation to QUERY_SET as a future hook only; the concrete handoff protocol (which placeholders, who fills `<SCOPE_START>` / `<SCOPE_END>`, whether to skip QUERY_SET's confirmation gate when receiving a curated list) is deferred to a follow-up.
- **Pruning view ingestion latency.** `TABLE_QUERY_PRUNING_HISTORY` and `COLUMN_QUERY_PRUNING_HISTORY` lag `QUERY_HISTORY` by up to 4 hours. The scoped pruning verified queries pad their upper bound by 4 hours, but very recent QUERY_SET scopes (last hour) may still see "0 tables touched" if pruning ingestion has not caught up.
- **Single-query_id metadata round-trip.** Single-id routing (QUERY vs STORED_PROCEDURE) requires a SQL fetch of the row's `query_type` first; see parent `SKILL.md` Step 0A.1.
