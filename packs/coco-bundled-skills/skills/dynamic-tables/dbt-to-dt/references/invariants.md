# Invariants

Durable constraints and version requirements for dbt-to-DT migrations.

---

## The Five Constraints

1. **`SELECT *` breaks on schema change** — always use explicit column lists in DT models.

2. **`on_schema_change` has no DT equivalent** — if source columns change, the DT refresh fails.

3. **Source table rebuilds may reset change tracking** — `CREATE OR REPLACE TABLE` on a source may not preserve `CHANGE_TRACKING`. Re-enable change tracking after source rebuilds.

4. **`--full-refresh` recreates DTs** — `CREATE OR REPLACE DYNAMIC TABLE` drops and recreates the DT, triggering full reinitialization. Use only for initial setup or when changing the DT query definition.

5. **DT is not recreated every run (unlike CTAS) — so post-hooks that assume a fresh object must be made idempotent.** `materialized='table'` rebuilds a fresh object every run, so hooks always see a clean slate. A dynamic table is rebuilt only on first run, `--full-refresh`, or a config change that forces replace (`refresh_mode`/`transient`); other config changes issue `ALTER`, and a **query-only change is a no-op** (not applied until `--full-refresh` — a documented dbt limitation). But post-hooks fire on every run regardless. So a hook that attaches state assuming a freshly-created object (e.g. `ADD ROW ACCESS POLICY`) succeeds on run 1 and errors on run 2. When migrating, preserve hooks but audit each for this assumption and make the affected ones idempotent (e.g. drop-before-add). Some hooks (row access policy, tag, clustering) can alternatively move to native DT config — optional, not required.

---

## Version Contract

**Rule:** `scheduler='disable'` requires `dbt-snowflake >= 1.11.5`.

### Failure symptom on dbt-snowflake < 1.11.5

On versions prior to 1.11.5, the `Scheduler` enum does not exist, the `scheduler` field is absent from `SnowflakeDynamicTableConfig`, and Jinja templates have no scheduler-related logic. The failure cascade:

1. `scheduler` key is silently ignored
2. `target_lag` resolves to `None`
3. The Jinja template unconditionally renders `target_lag = '{{ dynamic_table.target_lag }}'` producing `target_lag = 'None'`
4. Snowflake rejects the DDL: **SQL compilation error** — `'None'` is not a valid target_lag value

### Production invariant

Assert `dbt-snowflake >= 1.11.5` in the production dependency spec (pyproject.toml / requirements.txt), not just the local venv. A local install may satisfy the constraint while CI or deployment environments run an older pinned version.

---

## Manual Refresh Non-Cascade Behavior

**Rule:** `ALTER DYNAMIC TABLE ... REFRESH` does NOT propagate to upstream or downstream DTs.

This is a Snowflake-side behavior: manual refreshes are isolated to the single DT they target. dbt exploits this to refresh individual DTs in topological order without triggering the entire pipeline.

On every `dbt run`, the adapter issues `ALTER DYNAMIC TABLE ... REFRESH` for each DT model with `scheduler='disable'`. dbt controls which models refresh and in what order (topological sort of the DAG).

---

## scheduler='disable' SQL Semantics

### DDL emitted

```sql
CREATE DYNAMIC TABLE <db>.<schema>.<model_name>
    warehouse = <snowflake_warehouse>
    refresh_mode = <INCREMENTAL|FULL>
    scheduler = 'DISABLE'
    as (
        <query>
    )
```

Key DDL behavior:

- `TARGET_LAG` is **omitted entirely** when scheduler is DISABLE
- Snowflake requires this: "TARGET_LAG can't be defined when SCHEDULER = DISABLE"
- **`target_lag` and `scheduler='disable'` are mutually exclusive.** Never include both. If you see `target_lag` in the source config, REMOVE it during conversion.
- `initialize` is omitted (defaults to `ON_CREATE`). The DT refreshes immediately on creation, making data available for downstream models during `dbt build`.
- Do NOT use `initialize = ON_SCHEDULE` with `scheduler = 'DISABLE'` — it leaves the DT empty and unqueryable (error 002741) until manually refreshed, breaking downstream dependencies.
- The scheduler line is conditionally rendered via Jinja: `{% if dynamic_table.scheduler is not none %}scheduler = '{{ dynamic_table.scheduler }}'{% endif %}`

### Initial populate

With `scheduler = 'DISABLE'` and default `initialize = ON_CREATE`, the DT refreshes once at creation time. Subsequent refreshes only happen via explicit manual trigger:

```sql
ALTER DYNAMIC TABLE <db>.<schema>.<model_name> REFRESH
```

Conditional logic in the materialization:

```jinja
{% if dynamic_table.scheduler | upper == 'DISABLE' %}
    {% call statement(name="refresh") %}
        {{ snowflake__refresh_dynamic_table(target_relation) }}
    {% endcall %}
{% endif %}
```

### What scheduler='disable' disables

1. **Snowflake auto-refresh is disabled.** The DT is excluded from automatic background refresh cycles.
2. **dbt remains the orchestrator.** On every `dbt run`, the adapter issues `ALTER DYNAMIC TABLE ... REFRESH` for each DT model with `scheduler='disable'`.
3. **Cascade isolation.** Manual refreshes do NOT propagate to upstream or downstream DTs — each model refreshes independently under dbt's control.
