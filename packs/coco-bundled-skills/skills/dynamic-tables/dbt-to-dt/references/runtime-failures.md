# Runtime Failures Reference

This is a living document. Append-only. Every new migration that surfaces a new failure mode adds an entry.

## Tier Classification

- **tier-1 (auto-safe):** Math impact zero / syntax-only fix. The workaround changes the query shape but produces identical output. Safe to apply automatically.
- **tier-2 (escalate-on-semantic-change):** Modifies semantics, introduces a new object, or requires external-source coordination. Must be surfaced to the user for review before applying.

---

## Entry Schema

Each entry follows this structure:

```
### Error code or pattern name
Detection signal: ...
Tier: ...
Workaround: ...
Validation: ...
```

---

## Stage Applicability

| Entry | Stage 1 | Stage 2 | Notes |
|-------|---------|---------|-------|
| 091912 — current_date() upstream | ✗ | ✓ | FULL DTs don't need CT |
| 091941 — FULL DT lacks CT | ✗ | ✓ | Only relevant for INC downstream |
| 003001 — external-source CT | ✗ | ✓ | FULL doesn't need CT |
| post_hook clobber | ✓ (Tier 2 auto-fix) | ✓ | Hook form conversion |
| 003549 — RAP post-hook not idempotent | ✓ (Tier 2 auto-fix) | ✓ | Violates invariant #5 |
| Masking on PK | ✗ | ✓ (perf) | Does NOT block INC — degrades PK-based CT optimization |
| FULL OUTER JOIN non-equi | ✗ | ✓ | Forces FULL — relevant when assessing INC candidates |
| 300005 OOM | ✓ | ✓ | Can happen on any large DT initial refresh |
| 002742 wrapper | ✓ | ✓ | Wraps any inner error |
| Non-atomic table drop | ✓ | ✗ | Relevant for Stage 1 production deploy |
| refresh_mode='auto' fallback | ✗ | ✗ | We never use 'auto' |
| Sharded UNION ALL | ✗ | ✓ | CT coordination concern |

---

## Failure Modes


### 091912 — current_date() in upstream view body blocks INC

**Detection signal:** Error code `091912`: "change tracking is not supported on queries with non-deterministic functions." Triggered when a DT INC joins a view whose SQL body inlines `current_date()`, `current_timestamp()`, or similar non-deterministic functions in projection. Snowflake inlines the view body into the DT query, inheriting the blocker.

**Tier:** tier-1 (staging-table pattern) / tier-2 (if external-source view must be modified)

**Workaround:**
1. Create a NEW helper model (`materialized='table'`) that materializes the external-source view's output as a regular table
2. Enable `CHANGE_TRACKING = TRUE` on the helper table (via `post_hook`)
3. In consuming DT models, swap the view ref to the helper table ref
4. Add a date filter on the helper to keep row count manageable (only rows within the DT's data range)

Example helper config:
```sql
{{ config(
    materialized='table',
    post_hook=[
      "ALTER TABLE {{ this }} CLUSTER BY (date_col, partition_col)",
      "ALTER TABLE {{ this }} SET CHANGE_TRACKING = TRUE",
    ]
) }}
SELECT <slim_columns> FROM {{ ref('problematic_view') }} WHERE date_col >= '<cutoff>'
```

**Validation:**
- Helper table: `SHOW TABLES LIKE '%snapshot%'` confirms `change_tracking = ON`
- Consumer DTs: `SHOW DYNAMIC TABLES` shows `refresh_mode = INCREMENTAL` and `refresh_mode_reason = None`
- Second manual refresh returns `NO_DATA` (proves INC is working)

---

### 091941 — FULL DT cannot have CHANGE_TRACKING (without IMMUTABLE)

**Detection signal:** Error code `091941`: "Change tracking is not supported on dynamic tables with FULL REFRESH_MODE unless IMMUTABLE constraint specified." Appears when a downstream DT attempts INC refresh against an upstream FULL DT that lacks primary key-based change tracking.

**Tier:** tier-2 escalate-on-semantic-change

**Workaround:**
1. Check if the FULL upstream DT has a derived or declared primary key
2. If PK exists: attempt primary key-based change tracking (Snowflake may allow downstream INC)
3. If no PK: either (a) keep the FULL model as `materialized='table'` with CT enabled, or (b) accept cascade — downstream also becomes FULL
4. Present pipeline shape options to user before deciding

**Validation:**
- If kept as table: `SHOW TABLES` confirms `change_tracking = ON`; downstream DT shows `refresh_mode = INCREMENTAL`
- If cascade accepted: downstream DT shows `refresh_mode = FULL`, `refresh_mode_reason = None`
- If PK-based CT: `SHOW UNIQUE KEYS IN <upstream_dt>` shows keys; downstream builds as INC

---

### 003001 — Auto-CT-enable external-source failure

**Detection signal:** Error code `003001`: "Insufficient privileges to operate on table." Appears during DT creation when Snowflake attempts to automatically enable change tracking on an upstream table that the executing role lacks MODIFY privilege on. The upstream table is owned by another team/role.

**Tier:** tier-2 escalate-on-semantic-change

**Workaround:**
1. Identify the upstream table where auto-CT-enable failed (from error message)
2. Determine the owning role (`SHOW TABLES LIKE '<table>' IN SCHEMA ...` — check `owner` column)
3. Options:
   a. Request MODIFY grant from the owning team (preferred — one-time coordination)
   b. Request owning team to enable CT themselves: `ALTER TABLE <table> SET CHANGE_TRACKING = TRUE`
   c. If neither is possible: keep the consuming model as `materialized='table'` (skip DT conversion for this model)

**Validation:**
- `SHOW TABLES LIKE '<upstream>'` shows `change_tracking = ON`
- DT creation succeeds on retry with `dbt run --full-refresh --select <model>`
- `SHOW DYNAMIC TABLES` shows the model with expected `refresh_mode`

---

### post_hook clobber — model-level post_hook overrides project-level CT hook

**Detection signal:** After `dbt run`, the table/DT does NOT have `change_tracking = ON` despite the project-level post_hook being configured. Observed when a model defines its own `post_hook` (string form) which replaces the project-level hook list instead of appending to it.

**Tier:** tier-1 auto-safe

**Workaround:**
1. Convert model-level `post_hook` from string form to list form
2. Include BOTH the model-specific hooks AND the CT hook in the list:
```sql
post_hook=[
  "ALTER TABLE {{ this }} CLUSTER BY (col1, col2)",
  "ALTER TABLE {{ this }} SET CHANGE_TRACKING = TRUE",
]
```
3. Rebuild the model

**Validation:**
- `SHOW TABLES LIKE '%<model>%'` shows `change_tracking = ON`
- All other post_hook effects are also present (clustering applied, masking policies attached, etc.)

---

### 003549 — Row Access Policy post_hook not idempotent

**Detection signal:** Error code `003549 (23505)`: "Object already has a ROW_ACCESS_POLICY. Only one ROW_ACCESS_POLICY is allowed at a time." A post_hook issues bare `ADD ROW ACCESS POLICY` and fails on the second `dbt run` onward (not the first). Root cause is the DT re-run behavior in invariant #5 — the DT isn't recreated between runs, so the RAP from the prior run persists.

**Tier:** tier-1 auto-safe — semantically safe to apply (identical end state), but surface the hook rewrite to the user rather than applying it silently.

**Workaround:** Make the hook idempotent — issue `DROP ALL ROW ACCESS POLICIES` before `ADD`, guarded by `{%- if execute -%}`:

```jinja
{%- set obj_kind = 'DYNAMIC TABLE' if model.config.materialized.startswith('dynamic_table') else 'TABLE' -%}
{%- if execute -%}
    {% do run_query("ALTER " ~ obj_kind ~ " " ~ this ~ " DROP ALL ROW ACCESS POLICIES") %}
{%- endif -%}
ALTER {{ obj_kind }} {{ this }} ADD ROW ACCESS POLICY <policy> ON (<column>);
```

`DROP ALL ROW ACCESS POLICIES` is a no-op when none is attached.

**Validation:**
- Second consecutive `dbt run` (no `--full-refresh`) succeeds
- `INFORMATION_SCHEMA.POLICY_REFERENCES` shows exactly one RAP

---

### Masking policy on PK column — degrades PK-based change tracking optimization

**Detection signal:** This is a performance degradation, NOT a creation or refresh blocker. When a masking policy is applied to a primary key column, Snowflake cannot use PK-based change tracking and falls back to standard change-tracking columns. The DT still creates and refreshes as INCREMENTAL — but for INSERT OVERWRITE workloads, the fallback means every refresh processes all rows (since INSERT OVERWRITE resets standard tracking columns). For normal DML (INSERT, UPDATE, DELETE), standard CT still detects row-level changes correctly.

**Tier:** tier-1 (informational — no action required unless INSERT OVERWRITE performance is unacceptable)

**Impact:**
- DT creation: NOT blocked (still creates as INCREMENTAL)
- Normal DML refreshes: no impact (standard CT works)
- INSERT OVERWRITE refreshes: every refresh reprocesses all rows (loses PK optimization)

**Detection:**
```sql
-- Check for masking policies on PK columns
SELECT * FROM TABLE(INFORMATION_SCHEMA.POLICY_REFERENCES(
  REF_ENTITY_NAME => '<table>',
  REF_ENTITY_DOMAIN => 'TABLE'
));
```

**Workaround (only needed for INSERT OVERWRITE sources with performance issues):**
1. Remove masking from the PK column (if policy allows — PK values are typically non-sensitive identifiers)
2. Move masking to a non-key column
3. Accept the performance cost if INSERT OVERWRITE is infrequent

**Validation:**
- DT shows `refresh_mode = INCREMENTAL` (confirms not blocked)
- For INSERT OVERWRITE sources: monitor refresh duration after masking removal

---

### FULL OUTER JOIN with non-equi predicates — forces FULL refresh

**Detection signal:** DT created with `refresh_mode='incremental'` but `SHOW DYNAMIC TABLES` shows `refresh_mode = FULL` and `refresh_mode_reason` indicates the join pattern is unsupported for INC. Applies to queries with `FULL OUTER JOIN` combined with non-equijoin conditions or certain aggregate patterns (APPROX_PERCENTILE).

**Tier:** tier-2 escalate-on-semantic-change

**Workaround:**
1. Accept FULL refresh for models with FULL OUTER JOIN + complex predicates
2. Set `refresh_mode='full'` explicitly in the config (never rely on 'auto')
3. Evaluate cascade impact: if this model has downstream INC consumers, consider keeping it as table with CT instead
4. For models where FULL OUTER JOIN is combined with other FULL-forcing patterns (APPROX_PERCENTILE), document all reasons

**Validation:**
- `SHOW DYNAMIC TABLES` shows `refresh_mode = FULL` and `refresh_mode_reason = None` (explicit FULL, not forced)
- Manual `ALTER ... REFRESH` returns `NO_DATA` when sources unchanged (FULL DTs still detect no-change state)
- Row count matches original

---

### 300005 / XP_WORKER_DISAPPEARED — OOM during DT initial refresh

**Detection signal:** Error code `300005` with signature `DISAPPEARED_SF_OOM_KILLED`: "Processing aborted due to error 300005; Disappeared worker(s)." Workers are killed by Snowflake OOM killer during DT initial refresh. Memory reports show operators (Aggregate, Sort, HashJoinProbe) exceeding per-worker memory limits. Typically manifests on large tables (>100GB) during initial `--full-refresh`.

**Tier:** tier-2 escalate-on-semantic-change

**Workaround:**
1. Identify the model causing OOM (from dbt error output or query history)
2. Options (in order of preference):
   a. Use `INITIALIZATION_WAREHOUSE` with a larger warehouse (e.g., 2XL = ~31GB/worker vs XL = ~15.6GB/worker) for initial creation only
   b. Run the DT migration during off-peak hours to avoid concurrent warehouse contention
   c. Migrate the large model separately (`dbt run --full-refresh --select <model>`) — not batched with other models
   d. Size up the primary warehouse temporarily for initial creation
3. After initial creation succeeds, subsequent refreshes (INC or FULL NO_DATA) use far less memory — revert warehouse sizing

**Validation:**
- DT creation succeeds (check `SHOW DYNAMIC TABLES`)
- Refresh history shows `state = SUCCEEDED` for the initial refresh
- No OOM incidents in query history for the model

---

### 002742 — DT initial refresh compilation failure (wraps inner error)

**Detection signal:** Error code `002742`: "SQL compilation error: Failed to refresh dynamic table with refresh_trigger INITIAL at data_timestamp ... because of the error: <inner_error>." This is a wrapper error — the actual root cause is the inner error (e.g., 300005 OOM, privilege errors, etc.).

**Tier:** depends on inner error (see specific entry)

**Workaround:**
1. Parse the inner error from the 002742 message
2. Look up the inner error code in this document
3. Apply the workaround for the inner error

**Validation:**
- Same as the inner error's validation

---

### Non-atomic table drop — DT migration drops existing table before DT is ready

**Detection signal:** Downstream queries fail with "Object '<schema>.<table>' does not exist" during a DT migration deploy. Occurs because `dbt run --full-refresh` drops the existing table to create the DT replacement. If DT creation fails mid-way, the original table is gone and queries against it break.

**Tier:** tier-2 escalate-on-semantic-change

**Workaround:**
1. Before production cutover, clone the existing table as a backup:
   ```sql
   CREATE TABLE <schema>.<table>_backup CLONE <schema>.<table>;
   ```
2. Migrate one model at a time (not all at once) to limit blast radius
3. Have a rollback plan: if DT creation fails, restore from backup:
   ```sql
   ALTER TABLE <schema>.<table>_backup RENAME TO <schema>.<table>;
   ```
4. Consider blue-green strategy: create DTs with a suffix first (parallel), validate, then swap names

**Validation:**
- DT exists and is refreshing successfully (`SHOW DYNAMIC TABLES`)
- No downstream query failures referencing the object name
- Backup table can be dropped after validation period

---

### refresh_mode='auto' fallback — all models fall to FULL

**Detection signal:** All DTs show `refresh_mode = FULL` after creation despite using `refresh_mode='auto'` in config. The `refresh_mode_reason` field shows various reasons (CURRENT_DATE non-deterministic, APPROX_PERCENTILE, source row access policies, FULL cascade).

**Tier:** tier-1 auto-safe

**Workaround:**
1. Never use `refresh_mode='auto'` — always set explicit `'incremental'` or `'full'` per model
2. Classify each model's refresh mode during assessment (Step 3 of migration workflow)
3. If a model is expected to be INC but falls to FULL, check `refresh_mode_reason` and apply the specific fix (e.g., 091912 staging-table)

**Validation:**
- `SHOW DYNAMIC TABLES` shows the explicitly-set `refresh_mode` matching config
- `refresh_mode_reason = None` (not forced by Snowflake)

---

### Sharded UNION ALL source — no change tracking available

**Detection signal:** DT INC creation fails because the source is a UNION ALL view reading from many regional shard tables, none of which have change tracking enabled. The executing role lacks MODIFY on the shard tables (owned by another team).

**Tier:** tier-2 escalate-on-semantic-change

**Workaround:**
1. Keep the consuming model as `materialized='table'` (do not convert to DT)
2. Enable `CHANGE_TRACKING = TRUE` on the table via post_hook so downstream DTs can read from it
3. This table effectively becomes a "CT bridge" — it's rebuilt by dbt as a regular table, but downstream DTs treat it as an INC-compatible upstream

```sql
{{ config(
    materialized='table',
    post_hook="ALTER TABLE {{ this }} SET CHANGE_TRACKING = TRUE"
) }}
```

**Validation:**
- Table builds successfully via `dbt run`
- `SHOW TABLES LIKE '%<model>%'` shows `change_tracking = ON`
- Downstream DTs that ref this table show `refresh_mode = INCREMENTAL` and can refresh without error
