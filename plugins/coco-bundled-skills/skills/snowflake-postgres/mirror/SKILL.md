---
name: snowflake-postgres-mirror
description: "Managed Snowflake Postgres Mirroring: continuous, Snowflake-managed CDC replication from a Snowflake Postgres instance into Snowflake native tables via SNOWFLAKE.POSTGRES.CREATE_MIRROR. Triggers: create mirror, managed mirror, postgres mirroring, Snowflake Postgres mirroring, mirror postgres tables into snowflake continuously, CREATE_MIRROR, ALTER_MIRROR, DROP_MIRROR, LIST_MIRRORS, $live, $changes. Do NOT use for one-time / cutover migrations into Snowflake Postgres (that is `snowflake-postgres/migrate`), for converting legacy databases / SQL / ETL into Snowflake (that is the top-level `migration-guide` skill), or for generic change-data-capture outside Snowflake Postgres mirroring."
parent_skill: snowflake-postgres
---

# Snowflake Postgres - Mirroring

## When to Load

From `snowflake-postgres/SKILL.md` when the user wants managed continuous replication from a **Snowflake Postgres instance** into **Snowflake native tables**, or asks about `CREATE_MIRROR`, `$live`, `$changes`, `snowflake_cdc`, or Postgres CDC into Snowflake.

Use this managed-mirror skill instead of `pg-lake/` when the desired outcome is native Snowflake tables maintained continuously by Snowflake. Use `pg-lake/` only when the user explicitly wants to hand-build Postgres-resident Iceberg tables / catalog-linked databases. Use `migrate/` when moving an external Postgres database into Snowflake Postgres.

**Note:** All `<SKILL_DIR>` placeholders below refer to the **snowflake-postgres/** directory (absolute path).

## Intent Detection

| Intent | Trigger | Workflow |
|--------|---------|----------|
| **SETUP** | "create mirror", "mirror my table", "postgres to snowflake continuously", "set up CDC", `CREATE_MIRROR` | SETUP Workflow |
| **QUERY** | `$live`, `$changes`, "latest mirrored rows", "change history", "read mirror" | QUERY Workflow |
| **OPERATE** | "add/remove table", "change interval", "pause/resume/restart/drop mirror", "monitor lag" | OPERATE + MONITOR Workflow |
| **TROUBLESHOOT** | "mirror failed", "permission denied", "stuck snapshotting", "behind", "type error", "no primary key" | TROUBLESHOOT Workflow + references |

---

## SETUP Workflow

Managed mirroring creates the Snowflake target database, serverless apply task, source publication, replication slot, and PG-side mirroring plumbing. **Do not add a manual `CREATE EXTENSION snowflake_cdc` step** in this managed flow; `snowflake_cdc` is a useful trigger/troubleshooting term, but `CREATE_MIRROR` provisions the required plumbing.

### Step 0: Gather Scope

Collect or infer:
- Snowflake connection / role to use
- Postgres instance name and Postgres database name
- Mirror name (≤50 chars; mirror names fold to lowercase)
- Target Snowflake database name — **must not already exist**
- Either `postgres_tables` **or** `postgres_schemas` (XOR, not both)
- Optional `refresh_interval` (default `10 minutes`; valid `30 seconds` to `1 day` / 24 hours)
- Optional warehouse (otherwise serverless task)

If the user is vague ("mirror my orders table"), ask for missing identifiers before running SQL.

### Step 1: Pre-flight Checks

Run safe read-only checks before presenting the create plan. The purpose of pre-flight is to **know and report the real state before creating billable mirror infrastructure**; never skip a check silently.

```sql
SHOW POSTGRES INSTANCES LIKE '<instance_name>';
DESCRIBE POSTGRES INSTANCE <instance_name>;
SHOW DATABASES LIKE '<target_database>';
```

Verify and report:
- Instance tier is **STANDARD** or **HIGH MEMORY**; BURSTABLE is unsupported.
- Instance/account/cloud is supported (**AWS + Azure only**; no cross-account/region/cloud mirrors).
- Target database does **not** exist. If it exists, pick a new target DB name; failed creates should retry with a different target DB name.
- Existing pre-mirroring instances may need a **Snowsight UI refresh** to install current extensions. There is no SQL/CLI refresh path. If `CREATE_MIRROR` later fails with permission/extension errors, stop and route to the UI-refresh troubleshooting path.

If `DESCRIBE POSTGRES INSTANCE` or related account metadata shows the instance is stale for mirroring support, stop and hand the user to Snowsight before attempting `CREATE_MIRROR`. The refresh is a hard user stopping point.

Check source tables through the Postgres connection for the **Postgres database that contains the source tables** (`<POSTGRES_DATABASE>` may be `postgres`, `appdb`, or any user database):

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py \
  --ensure-ready --instance-name <INSTANCE_NAME> \
  --database <POSTGRES_DATABASE> \
  [--snowflake-connection <SF_CONNECTION>]
```

```bash
psql "service=<PG_CONNECTION> dbname=<POSTGRES_DATABASE> connect_timeout=10" -c "
SELECT n.nspname AS schema_name,
       c.relname AS table_name,
       c.relkind,
       c.relpersistence,
       EXISTS (
         SELECT 1
         FROM pg_index i
         WHERE i.indrelid = c.oid AND i.indisprimary
       ) AS has_primary_key
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname || '.' || c.relname IN (<schema.table list>);
"
```

If `psql` is not installed, do **not** skip the PK/type checks. Use the shared driver path in `<SKILL_DIR>/scripts/shared/pg_common.py`: it provides dual-driver `connect()`/`query()` support (`psycopg2`, then `pg8000`) and `check_psql()` for scripts that require the CLI. Do not hand-roll a separate driver path.

```bash
PYTHONPATH=<SKILL_DIR>/scripts uv run --project <SKILL_DIR> python - \
  --source-service <PG_CONNECTION> --dbname <POSTGRES_DATABASE> <<'PY'
import argparse, json
from shared import pg_common

parser = argparse.ArgumentParser()
pg_common.add_source_args(parser)
args = parser.parse_args()
with pg_common.connect_source(args) as conn:
    rows = pg_common.query(conn, """
SELECT n.nspname AS schema_name,
       c.relname AS table_name,
       c.relkind,
       c.relpersistence,
       EXISTS (
         SELECT 1
         FROM pg_index i
         WHERE i.indrelid = c.oid AND i.indisprimary
       ) AS has_primary_key
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname || '.' || c.relname IN (<schema.table list>);
""")
print(json.dumps(rows, indent=2, default=str))
PY
```

Source-table rules to check/explain:
- Ordinary or partitioned **logged** tables only (`relkind` `r`/`p`; not UNLOGGED).
- Not views, foreign tables, sequences, or extension-owned objects.
- Names must not end in `$changes` or `$live`.
- `schema.table` names must be case-insensitively unique.
- Avoid source shapes that are rejected at publication time, including ANSI-reserved column names, virtual/generated columns that cannot be replicated, and nested UUID values.
- No primary key means **insert-only** replication for that table; UPDATE/DELETE replication requires a PK.

For schemas, sample/list candidate tables first and warn that the same constraints apply to every included table.

Pre-flight result contract:
- If all checks run: summarize the observed state (instance support, target DB availability, source table eligibility/PKs) and explain the proposed next steps.
- If any check fails or cannot be verified (connection/auth error, wrong database, missing service profile, no `psql` and no working Python driver), **stop**. Tell the user exactly which check is unverified, why it matters, how to resolve it, and provide a concrete fix plan you can execute after approval. Do not proceed as if the check passed.

### Step 2: Type Pre-scan

Before `CREATE_MIRROR`, scan for blocked/lossy source types in `<POSTGRES_DATABASE>`. Load `references/type-mapping.md` and flag:
- **Blocked at publication:** `map`/`pg_map`, nested geometry, nested range/multirange, non-composite table types, domains over unsupported base types.
- **Lossy/fallback:** unbounded `numeric` or precision/scale >38 → double; json/jsonb/hstore/vector/ranges → string; geometry → binary. PostGIS geometry support uses `pg_lake_spatial`, which is auto-installed when PostGIS is present; do not add a manual spatial-extension step unless troubleshooting shows it is missing.

Use this query as a starting point for selected tables:

```bash
psql "service=<PG_CONNECTION> dbname=<POSTGRES_DATABASE> connect_timeout=10" -c "
SELECT table_schema, table_name, column_name, udt_name, data_type,
       numeric_precision, numeric_scale
FROM information_schema.columns
WHERE table_schema || '.' || table_name IN (<schema.table list>)
ORDER BY table_schema, table_name, ordinal_position;
"
```

If `psql` is unavailable, run the same SQL through the `pg_common` driver fallback from Step 1. If the type scan cannot be completed, stop with resolution guidance and an approvable fix plan; do not treat blocked/lossy type protection as verified.

If blocked types are present, stop and ask whether the user wants to adjust the source schema / select different tables before creating the mirror. If only lossy/fallback types are present, report the semantic changes before asking for approval.

### Step 3: Grants

The Snowflake role executing mirror operations needs the mirroring application role, and the Snowflake application needs USAGE on the Postgres instance:

```sql
GRANT APPLICATION ROLE snowflake.postgres_mirror_admin TO ROLE <role>;
GRANT USAGE ON POSTGRES INSTANCE <instance_name> TO APPLICATION snowflake;
```

If the current role lacks privileges, use the same role-picker pattern as `manage/SKILL.md`: present available roles if known, prefer ACCOUNTADMIN/security-admin-capable roles, and retry with the chosen role. Do not expose DESCRIBE `access_roles` or credentials.

### Step 4: Mandatory Stopping Point — Present the Plan

**⚠️ STOP. Do not run `CREATE_MIRROR` until the user explicitly approves.** Creating a mirror creates a target database, serverless apply task, PG replication objects, and ongoing compute/storage cost.

Present:

```text
I will create a managed Snowflake Postgres mirror:

  Mirror:              <mirror_name>
  Postgres instance:   <instance_name>
  Postgres database:   <postgres_database>
  Source scope:        <tables | schemas>
  Target database:     <target_database> (must not pre-exist)
  Refresh interval:    <interval, default 10 minutes>
  Warehouse:           <serverless | warehouse>

Important caveats:
- Tables without primary keys are insert-only for UPDATE/DELETE replication.
- `$live` is near-real-time but non-transactional and can cost more when backlog grows.
- Existing/stale instances may require a Snowsight UI refresh if create returns permission errors.

Proceed?
```

### Step 5: Create Mirror

After approval, execute `CREATE_MIRROR` with **either** `postgres_tables` or `postgres_schemas`:

```sql
CALL SNOWFLAKE.POSTGRES.CREATE_MIRROR(
  mirror_name       => '<mirror_name>',
  postgres_instance => '<instance_name>',
  postgres_database => '<postgres_database>',
  target_database   => '<target_database>',
  postgres_tables   => ['public.orders', 'public.order_items'],
  postgres_schemas  => NULL,
  refresh_interval  => '<interval>',
  warehouse         => NULL
);
```

Schema-scope variant:

```sql
CALL SNOWFLAKE.POSTGRES.CREATE_MIRROR(
  mirror_name       => '<mirror_name>',
  postgres_instance => '<instance_name>',
  postgres_database => '<postgres_database>',
  target_database   => '<target_database>',
  postgres_tables   => NULL,
  postgres_schemas  => ['public'],
  refresh_interval  => '<interval>',
  warehouse         => NULL
);
```

If create fails with permission/extension errors, do not keep retrying. Go to TROUBLESHOOT → "Instance refresh required".

### Step 6: Verify

Verify the mirror and table states:

```sql
CALL SNOWFLAKE.POSTGRES.LIST_MIRRORS('<instance_name>');
CALL SNOWFLAKE.POSTGRES.DESCRIBE_MIRROR('<mirror_name>');
CALL SNOWFLAKE.POSTGRES.LIST_MIRRORED_TABLES('<mirror_name>');
```

Use `LIST_MIRRORED_TABLES` as the source for per-table `STATE`. `LIST_MIRRORS` and `DESCRIBE_MIRROR` do **not** expose a mirror-level `STATE` column. Expected per-table progression: `SNAPSHOTTING` → `REPLICATING`. For large initial snapshots, stay in `SNAPSHOTTING` until the initial copy completes.

Immediately after `CREATE_MIRROR`, `LIST_MIRRORED_TABLES` rows and `LIST_MIRRORS.TABLE_COUNT` can take a few seconds to populate. Re-poll before concluding that an empty table list or zero table count is a failure.

Run row-count sanity checks once tables surface:

```sql
SELECT COUNT(*) FROM <target_database>.<schema>.<table>;
```

Use unquoted identifiers unless the object was intentionally created quoted; mirrored identifiers are uppercased in Snowflake.

---

## QUERY Workflow

Choose the object based on the user's consistency/freshness requirement:

| Need | Query | Caveat |
|------|-------|--------|
| Transactionally consistent analytics | Base target table: `<db>.<schema>.<table>` | Fresh after apply task runs (`refresh_interval`) |
| Latest rows / lower latency | `<db>.<schema>.<table>$live` | ~30s, non-transactional, may expose partial transactions; cost grows with unmerged backlog |
| 7-day audit/change feed | `<db>.<schema>.<table>$changes` | System columns: `_COMMIT_LSN`, `_LSN`, `_XID`, `_COMMIT_TIME`, `_CHANGE_TYPE`, `_IS_UPDATE`, `_DATA_VERSION`. `_CHANGE_TYPE` = `S` (snapshot), `I` (insert), `D` (delete/update pre-image); use `_IS_UPDATE` to distinguish standalone deletes from update pre-images. |

Examples:

```sql
-- Consistent base table
SELECT COUNT(*) FROM ORDERS_DB.PUBLIC.ORDERS;

-- Near-real-time view. Do not quote column/table names unless they were quoted at creation.
SELECT ORDER_ID, STATUS, UPDATED_AT
FROM ORDERS_DB.PUBLIC.ORDERS$LIVE
WHERE STATUS = 'OPEN';

-- Change history for the last 7 days
SELECT _CHANGE_TYPE, _IS_UPDATE, _DATA_VERSION, _XID, ORDER_ID, UPDATED_AT
FROM ORDERS_DB.PUBLIC.ORDERS$CHANGES
ORDER BY UPDATED_AT DESC
LIMIT 100;
```

See `references/troubleshooting.md` → [`$changes` / Watermark / Sequence Reset Notes](references/troubleshooting.md#changes--watermark--sequence-reset-notes) for full `_CHANGE_TYPE` and `_IS_UPDATE` semantics (including `_DATA_VERSION` watermark resets).

Identifier rule: Postgres identifiers are exposed as uppercase Snowflake identifiers. Prefer **unquoted** table and column names (`ORDER_ID`, not `"order_id"`). Quoted lowercase references often fail with `invalid identifier`.

---

## OPERATE + MONITOR Workflow

### Lifecycle Procedures (non-destructive)

```sql
-- Change interval and/or add/remove tables
CALL SNOWFLAKE.POSTGRES.ALTER_MIRROR(
  mirror_name      => '<mirror_name>',
  refresh_interval => '<interval>',
  add_tables       => ['public.new_table'],
  remove_tables    => NULL
);

-- Apply pending changes now
CALL SNOWFLAKE.POSTGRES.REFRESH_MIRROR('<mirror_name>');

-- Pause apply work
CALL SNOWFLAKE.POSTGRES.SUSPEND_MIRROR('<mirror_name>');
```

`ALTER_MIRROR` **table removals** are high-impact. Confirm exactly which tables will be removed before executing `remove_tables`.

### Destructive lifecycle — mandatory approval

**⚠️ MANDATORY CHECKPOINT**: Before `RESTART_MIRROR`, `DROP_MIRROR`, or `drop_target_database => TRUE`:

Present the exact impact (what will be rebuilt or deleted), then wait for explicit user approval. NEVER proceed without confirmation.

```text
I will run a destructive mirror operation:

  Procedure:           <RESTART_MIRROR | DROP_MIRROR>
  Mirror:              <mirror_name>
  Impact:              <full re-snapshot + lose 7-day $changes | tear down mirror [+ drop target DB]>

Proceed?
```

```sql
-- Full re-snapshot; rebuilds the 7-day $changes feed and loses existing change-feed history
CALL SNOWFLAKE.POSTGRES.RESTART_MIRROR('<mirror_name>');

-- Tear down mirror infrastructure; optionally drop target DB
CALL SNOWFLAKE.POSTGRES.DROP_MIRROR('<mirror_name>', drop_target_database => FALSE);
```

### Monitoring

```sql
CALL SNOWFLAKE.POSTGRES.DESCRIBE_MIRROR('<mirror_name>');
CALL SNOWFLAKE.POSTGRES.LIST_MIRRORS('<instance_name>');
CALL SNOWFLAKE.POSTGRES.LIST_MIRRORED_TABLES('<mirror_name>');
```

Use `LIST_MIRRORED_TABLES` as the primary per-table state view. `LIST_MIRRORS` and `DESCRIBE_MIRROR` do **not** expose a mirror-level `STATE` column. Expect `SNAPSHOTTING` during the initial copy and `REPLICATING` once steady-state CDC is live.

After create or table-add operations, table rows and `LIST_MIRRORS.TABLE_COUNT` can populate asynchronously; re-poll before treating an empty list or stale count as failure. A null `LAST_APPLY_TIME` on an idle mirror with successful recent runs or `no operations to process` admin-log messages is not by itself a failure.

For admin-log errors, apply-task history (`TASK_HISTORY` with pushed filters), and `$live` lag remediation via `REFRESH_CHANGES_TABLE`, **Load** `references/troubleshooting.md` → [Table State / Lag Checks](references/troubleshooting.md#table-state--lag-checks). Keep those query templates there so they do not drift from the TROUBLESHOOT path.

---

## TROUBLESHOOT Workflow

Load `references/troubleshooting.md` for detailed decision trees.

Load `references/type-mapping.md` whenever the symptom suggests publication/type incompatibility or when planning a type-focused pre-flight review.

Fast routes:

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| Permission/extension error on create | Existing instance needs refresh | **Stop**: user must refresh in Snowsight (Postgres → Manage); no SQL/CLI path |
| Target DB error | Target DB already exists or failed partial create | Pick a new target DB name; inspect/drop only with approval |
| Table stays `SNAPSHOTTING` | Large initial copy, blocked source table, apply error | `LIST_MIRRORED_TABLES`, named-arg `QUERY_ADMIN_LOG`, task history |
| UPDATE/DELETE not replicated | Source table has no PK | Explain insert-only behavior; add PK then consider restart/full re-snapshot with warning |
| Auth failures mid-mirror | App lost instance USAGE | Re-run `GRANT USAGE ON POSTGRES INSTANCE ... TO APPLICATION snowflake` |
| `$live` partial/inconsistent reads | `$live` is non-transactional | Query base table for transactional consistency |
| New mirror shows empty table list / `TABLE_COUNT=0` | Metadata can populate asynchronously just after create | Re-poll `LIST_MIRRORED_TABLES` / `LIST_MIRRORS` before concluding failure |
| Null `LAST_APPLY_TIME` with successful recent runs and no-op admin logs | Idle mirror with no pending operations | Not a failure by itself; inspect `ERROR_MESSAGE`, admin log, and task history |
| Type/publication error | Blocked type or rejected source-table shape | Load `type-mapping.md`, adjust source schema or omit table |

---

## Tools

No mirror-specific scripts yet. Use Snowflake SQL execution for `SNOWFLAKE.POSTGRES.*` procedures and existing Postgres connection helpers for pre-flight checks:

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py --list
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py \
  --ensure-ready --instance-name <INSTANCE_NAME> [--snowflake-connection <SF_CONNECTION>]
psql "service=<PG_CONNECTION> connect_timeout=10" -c "<read-only SQL>"
```

All Postgres commands need 60s+ bash timeout; bulk checks may need 120s+.

## Safety Rules

- Never ask for passwords in chat or echo secrets.
- Do not display DESCRIBE `access_roles` or raw CREATE/RESET outputs that may contain credentials.
- Always include `connect_timeout=10` in `psql` commands.
- Use 60s+ command timeouts for networked Postgres/Snowflake operations.
- Require explicit user approval before `CREATE_MIRROR`, `ALTER_MIRROR` table removals, `RESTART_MIRROR`, `DROP_MIRROR`, or any target database drop.
- Warn that `RESTART_MIRROR` is a full re-snapshot and loses the current 7-day change feed.
- Treat Snowsight instance refresh as a user stopping point; there is no SQL/CLI substitute.

## Output

- Setup: pre-flight findings, approval plan, `CREATE_MIRROR`, verification state, and next query examples.
- Query: recommended object (base/`$live`/`$changes`) with consistency/cost caveat.
- Operate: exact proc, impact warning, approval checkpoint if mutating/destructive.
- Troubleshoot: likely cause, verification command, and next action or stopping point.
