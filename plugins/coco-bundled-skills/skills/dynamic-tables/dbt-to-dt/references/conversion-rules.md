# Conversion Rules Reference

Rules for converting dbt models from `materialized='table'` to `materialized='dynamic_table'`, organized by risk level.

## Escalation Policy

| Tier | Action | Escalate? |
|------|--------|-----------|
| Tier 1 — Config swap | Auto-apply | No |
| Tier 2 — SQL fixes | Auto-apply, ONE retry | Report in summary — user reviews post-hoc |
| Tier 3 — Config flags | Flag at checkpoint | Yes — user decides before conversion |
| Tier 4 — New models | Propose at checkpoint | Yes — user approves DAG changes |

**Rule:** Tier 1 is the only fully autonomous change. Tier 2+ must be visible to the user — either reported (tier 2) or gated on approval (tier 3-4).

---

## Risk Tier 1 — Transparent (config-only, no semantic change)

These changes are purely mechanical. No query behavior changes. Auto-apply without escalation.

### Config Parameters That Stay

| Parameter  | Notes                          |
|------------|--------------------------------|
| `schema`   | Carries over directly          |
| `database` | Carries over directly          |
| `tags`     | Carries over directly          |
| `alias`    | Carries over directly          |

### Config Parameters to Add

| Parameter             | Value                                      |
|-----------------------|--------------------------------------------|
| `snowflake_warehouse` | Required — set to the designated DT warehouse |
| `scheduler`           | `'disable'`                                |
| `refresh_mode`        | `'full'` (Stage 1) or `'adaptive'` (Stage 2 upgrade) — never `'auto'` |
| `initialize`          | Omit (defaults to `'on_create'`). With `scheduler='disable'`, using `'on_schedule'` leaves the DT empty and unqueryable until manually refreshed — downstream models would fail during `dbt build`. |

### Config Parameters to Remove

| Parameter    | Why                                                    |
|--------------|--------------------------------------------------------|
| `target_lag` | **Mutually exclusive with scheduler='disable'.** Snowflake rejects DDL containing both. |

### Materialization Swap

```sql
-- Before
{{ config(materialized='table', schema='analytics') }}

-- After
{{ config(materialized='dynamic_table', schema='analytics', snowflake_warehouse='DT_WH', scheduler='disable', refresh_mode='full') }}
```

SQL body is UNCHANGED at this tier.

---

## Risk Tier 2 — Low-risk SQL fixes (mechanical, math-preserving)

Narrow SQL body modifications that preserve semantics. Auto-apply with ONE retry cap.

### Fix: post_hook scalar → list-form

A scalar `post_hook` overrides the project-level `post_hook`. Convert to list-form to preserve both.

```sql
-- Before (project-level CT hook is lost)
{{ config(post_hook="ALTER TABLE {{ this }} CLUSTER BY (ds, region)") }}

-- After (both preserved)
{{ config(post_hook=[
    "ALTER TABLE {{ this }} CLUSTER BY (ds, region)",
    "ALTER TABLE {{ this }} SET CHANGE_TRACKING = TRUE",
]) }}
```

---

## Risk Tier 3 — Config flags requiring user decision

Parameters that have no DT equivalent. Escalate — user must decide what to do.

| Parameter              | Why                                              |
|------------------------|--------------------------------------------------|
| `on_schema_change`     | No DT equivalent exists                          |
| `unique_key`           | Incremental-specific param — no DT equivalent    |
| `incremental_strategy` | Incremental-specific param — no DT equivalent    |

If present on a table model, flag for user review at the checkpoint. Do NOT silently drop.

### Hooks requiring review

| Parameter   | Concern                                                        |
|-------------|----------------------------------------------------------------|
| `post_hook` | May contain arbitrary SQL incompatible with DTs (grants, masking, clustering) |
| `pre_hook`  | Same concern                                                   |

For each hook: read the macro source, reason about DT compatibility, classify as:
- **Keep as-is** (e.g., masking — reattach via list-form post_hook)
- **Migrate to config** (e.g., clustering → `cluster_by` config keyword)
- **Escalate** (e.g., grants that reference table-specific syntax)

**Idempotency check (invariant #5):** DT post-hooks fire every run, but the DT isn't recreated between runs (unlike CTAS), so a hook that attaches state assuming a fresh object breaks on the second run. For each post_hook, ask: **"will it error if its effect is already present?"**
- If no (most hooks): keep as-is.
- If yes: make it idempotent. Known case: `ADD ROW ACCESS POLICY` → `DROP ALL ROW ACCESS POLICIES` before `ADD` (see `runtime-failures.md` → 003549). Reason per hook — don't assume.

Hooks that map to a native DT config (`row_access_policy`, `table_tag`, `cluster_by`) may move to config instead — optional. Classify a mechanical idempotency fix as Tier 2; escalate anything ambiguous as Tier 3.

---

## Risk Tier 4 — New model creation (changes DAG structure)

> **Scope:** Tier 4 applies only in Stage 2 (INC upgrade). Stage 1 converts all models to FULL — no new models needed.

These create new files, change `ref()` targets, and alter the project DAG. Always present to user for approval.

### Staging-Table Pattern

**When:** An external-source upstream view contains non-deterministic functions (e.g., `CURRENT_DATE()`) blocking DT INC via error 091912, AND the view cannot be modified.

**What it does:**
1. Creates a NEW `materialized='table'` model
2. Reads from the problematic upstream view
3. Enables change tracking via `post_hook`
4. Downstream DTs `ref()` the staging-table instead of the view

**Model template:**

```sql
{{ config(
    materialized='table',
    schema='<target_schema>',
    post_hook=[
      "ALTER TABLE {{ this }} CLUSTER BY (<clustering_columns>)",
      "ALTER TABLE {{ this }} SET CHANGE_TRACKING = TRUE",
    ]
) }}

SELECT
    <only columns downstream models actually join on>
FROM {{ ref('<problematic_upstream_view>') }}
WHERE <date_column> >= '<reasonable_lower_bound>'
```

**Safety criteria:**
1. **Slim columns** — only columns downstream joins actually read
2. **Date filter** — remove irrelevant historical rows, keep safety buffer
3. **List-form post_hook** — preserve both clustering and change tracking
4. **No entity-level filters** — keep all entities for new entries
5. **Materialized as table, not DT** — DT would inherit the blocker

**Risk:** High — changes DAG, adds maintenance surface, requires ref remapping in consuming models. Always escalate to user at checkpoint.
