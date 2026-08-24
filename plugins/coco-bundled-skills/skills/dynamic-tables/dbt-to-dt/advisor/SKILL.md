---
name: dbt-to-dt-advisor
description: Single-model dbt-to-DT advisor. Stateless. Classifies one model and suggests a config block. Surfaces caveats. Does not run dbt or query Snowflake.
---

# dbt-to-dt — Advisor

Use when:
- The user pasted SQL or a single `.sql` file path.
- The user asks "should this be DT incremental or full?" about one model.
- The orchestrator was requested but isn't available on this surface (router redirected here).

---

## Workflow

### Step 1 — Parse input

Accept one of three input shapes:

- **Pasted SQL:** Treat the message body as the model SQL. If the user did not include a `{{ config(...) }}` block, proceed without one — suggest the canonical config from scratch in Step 6.
- **Single `.sql` file path:** Read the file. Extract the config block and SQL body. On Snowsight, file-path input is valid only for Workspace files; pasted SQL is the primary input on that surface.
- **Model name + project context:** Read `dbt_project.yml`, locate the model file, read it.

On Snowsight non-sandbox, `read_active_pane` is available as an alternative to paste — capture SQL from the user's open worksheet if offered.

Normalize all shapes into: `model_sql`, `config_block` (may be None), `model_name` (may be None).

### Step 2 — Load classification knowledge

Load:
- `../references/classification-rules.md` — bucket definitions, signal lists, assignment algorithm, inferred-PK rules, "Never AUTO" constant.
- `../../references/incremental-operators.md` — operator-by-operator incremental support matrix (the authoritative source for which operators support incremental refresh).

### Step 3 — Detect signals

Walk the SQL once. Use `classification-rules.md` (Step 1 SKIP check + Step 3 classify) and `incremental-operators.md` as the authoritative lookup. Extract every operator and match against the reference — do NOT classify from memory.

**Key examples** (not exhaustive — defer to the reference files):

- SKIP: `WITH RECURSIVE`, `UNPIVOT`, `SAMPLE`, `UUID_STRING()` in SELECT, `RANDOM()` in SELECT
- FULL: `WHERE EXISTS (SELECT ...)`, `WHERE IN (SELECT ...)`, `EXCEPT`, outer join with `ON a.id > b.id`, `CURRENT_DATE()` in SELECT, `LEAD()`/`LAG()`, `LIMIT`
- INC: equi-joins, `GROUP BY`, `SUM`/`COUNT`/`AVG`/`MIN`/`MAX`, `UNION ALL`, `LATERAL FLATTEN`, `ROW_NUMBER()`, `RANK()`

**Inferred-PK signals:**
- `GROUP BY` columns (simple columns only)
- `QUALIFY ROW_NUMBER() OVER (PARTITION BY ...)` — the PARTITION BY columns
- Base-table `PRIMARY KEY RELY` (if user mentions it)

### Step 4 — Bucket the model

Apply the decision tree from `classification-rules.md` in strict order (first match wins):

1. **SKIP** — Any SKIP trigger present? → SKIP. Record which trigger.
2. **INCREMENTAL_CANDIDATE** — Are ALL operators confirmed incremental-safe? → INCREMENTAL_CANDIDATE.
3. **FULL_BY_SQL** — Any FULL_BY_SQL trigger present? → FULL_BY_SQL. Record the specific trigger as `bucket_reason`.
4. **FULL_AS_DEFAULT** — Anything remaining. Record: "defaulting to FULL for safety".

### Step 5 — Surface caveats

Load:
- `../references/conversion-rules.md` — post_hook compatibility, config params that stay/go/flag
- `../references/invariants.md` — production-safety constraints, dbt-snowflake version contract
- `../references/runtime-failures.md` — caveat detection only; never auto-fix from the advisor

Scan the model and surface applicable caveats:

- **post_hook compatibility:** If `config_block` has a scalar `post_hook`, mention that list-form preserves both project-level and model-level hooks.
- **Masking on PK:** If model references `POLICY` or masking-related constructs AND inferred PK is detected → mention as a caveat (masking on PK columns degrades PK-based CT optimization for INSERT OVERWRITE workloads, but does NOT block incremental refresh).
- **Change-tracking on source:** ALWAYS mention "verify source has `change_tracking = ON`" — the advisor does not query Snowflake, so this is always a caveat.
- **dbt-snowflake version:** Mention that `scheduler='disable'` requires `dbt-snowflake >= 1.11.5`.
- **SELECT * fragility:** If model uses `SELECT *`, mention that schema changes on the source will break the DT — always use explicit columns.

### Step 6 — Suggested config block

Output the `{{ config(...) }}` block based on the bucket:

For **INCREMENTAL_CANDIDATE**:
```jinja
{{
  config(
    materialized='dynamic_table',
    snowflake_warehouse='<your-warehouse>',
    scheduler='disable',
    refresh_mode='adaptive'
  )
}}
```

For **FULL_BY_SQL** or **FULL_AS_DEFAULT**:
```jinja
{{
  config(
    materialized='dynamic_table',
    snowflake_warehouse='<your-warehouse>',
    scheduler='disable',
    refresh_mode='full'
  )
}}
```

For **SKIP**: Do not output a config block. Tell the user: "This model should not become a Dynamic Table — keep as table."

Config param handling:
- **Preserve** from existing config: `schema`, `database`, `tags`, `alias`
- **Flag for removal** (DT does not support): `on_schema_change`, `unique_key`, `incremental_strategy`
- **NEVER** write `refresh_mode='auto'` — the advisor's bucket determines the mode explicitly.

### Step 7 — Output

Format the response as structured Markdown with these required sections:

```
**Classification:** <SKIP | FULL_BY_SQL | INCREMENTAL_CANDIDATE | FULL_AS_DEFAULT>
**Reason:** <specific bucket_reason — e.g., the trigger, the operator, or "all operators confirmed incremental-safe">
**Inferred PK:** <comma-separated column list, or "none detected">

**Suggested config:**
<the config block from Step 6, or "keep as table" message for SKIP>

**Caveats to verify before applying:**
- <each caveat from Step 5, one bullet each>

**What's NOT covered by this advisor:**
- DAG-level cascade analysis (if this model has FULL upstream DTs, this classification may not hold). For project-wide migration, use the CLI orchestrator.
- Validation against actual Snowflake state (refresh_mode confirmation, parity checks). The advisor reasons from SQL only.
- Source `change_tracking` verification. Listed as a caveat the user must check.
- Automated conversion. This advisor returns a suggested config as text — it does not modify any file.

For project-wide migration including DAG analysis, source verification, conversion, and validation:
- **CLI:** run `cortex` from your dbt project root and ask "migrate my dbt project at <path>".
- **Snowsight:** the orchestrator is not available on this surface; use this advisor one model at a time.
```

---

## Surface-specific behavior

- On **Snowsight non-sandbox**: use `ask_user_question` for structured interaction (e.g., asking the user to confirm which model they want assessed, or bridging to the orchestrator suggestion). `read_active_pane` is available as an alternative input channel to paste. `execute_sql` is available but the advisor does not use it — "no source verification" is a deliberate design choice, not a platform constraint.
- On **CLI**: file-path input and model-name input are fully supported. Markdown output renders directly.
- On **all surfaces**: no filesystem writes, no Bash execution, no sub-agents. The advisor's reasoning is from SQL only.

---

## What this advisor explicitly does NOT do

1. **DAG analysis.** Cascade rules are not applied. A model classified as INCREMENTAL_CANDIDATE here may not hold that classification if its upstream is FULL. The advisor calls this out so users on multi-model projects know to switch to the CLI orchestrator.
2. **Source verification.** Source `change_tracking` status is mentioned as a caveat; the advisor does not run `SHOW TABLES` itself.
3. **Conversion.** Returns the suggested config block as text; does not modify any file.
4. **Validation.** Cannot run `dbt run` or query DT state. Its reasoning is from SQL alone.

---

## Bridging to the orchestrator

For project-wide migration including DAG analysis, source verification, conversion, and validation:
- **CLI:** run `cortex` from your dbt project root and ask "migrate my dbt project at `<path>`" — the orchestrator handles classification, cascade analysis, batched conversion, and auto-validation across all models.
- **Snowsight:** the orchestrator is not available on this surface; use this advisor one model at a time and verify sources manually.

---

## Loaded references

- `../references/classification-rules.md` (Step 2 — bucket rules, signals, assignment algorithm)
- `../../references/incremental-operators.md` (Step 2 — parent operator support matrix)
- `../references/conversion-rules.md` (Step 5 — post_hook compatibility, config param handling)
- `../references/invariants.md` (Step 5 — production-safety constraints)
- `../references/runtime-failures.md` (Step 5 — caveat detection only; never auto-fix from advisor)
