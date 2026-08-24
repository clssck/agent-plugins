# Snowflake Catalog Integration for pg_lake (Managed Storage)

Deep reference for the **`CATALOG_SOURCE = SNOWFLAKE_POSTGRES`** path — the managed-storage + VENDED_CREDENTIALS way to query pg_lake Iceberg tables from Snowflake.

**When to use this reference:** The user wants to read pg_lake Iceberg tables from Snowflake and the PG instance uses managed storage (no customer S3 bucket attached). For customer-S3 + external-stage flows, see `data-movement.md`. For the latest platform support matrix and any cloud/region restrictions, run `cortex search docs "snowflake_postgres catalog integration"`.

All commands live in `pg_lake_catalog.py`. The parent `SKILL.md` has the 5-step workflow — this reference documents the pieces.

## Prerequisites

| Requirement | Why it matters |
|-------------|----------------|
| **Supported cloud platform** | The catalog integration path doesn't support every cloud + region. `pg_lake_storage.py verify` surfaces the instance host so the agent can compare against current Snowflake support. The server is the source of truth — unsupported configurations return a translated error from `create-integration` and the workflow falls back to the external-stage path. For the current support matrix, see Snowflake docs (`cortex search docs "snowflake_postgres catalog integration"`). |
| **Managed-storage PG instance** | The feature reads Iceberg metadata from a Snowflake-managed bucket. PG instances with a `STORAGE_INTEGRATION` attached are writing to a customer bucket and are not eligible. |
| **Same Snowflake account** | The SF account running `CREATE CATALOG INTEGRATION` must be the same one hosting the PG instance. Cross-account pairing fails with `Object 'X' does not exist or not authorized`. |
| **Account params enabled** | `ENABLE_SNOWFLAKE_POSTGRES` + the managed-volume flag (see "Account-param naming" below) must both be `TRUE` on the SF account. If absent, work with your Snowflake account admin (ACCOUNTADMIN) to enable them; they can escalate to Snowflake support if the feature isn't yet available on the account. |
| **Instance pg_lake maintenance** | The specific PG instance must have had the pg_lake maintenance operation applied. Without it, `CREATE CATALOG INTEGRATION` returns error `604061` even if the account-level params are on. |

> **Account-param naming**: `pg_lake_catalog.py check-account-params` looks up both `ENABLE_POSTGRES_HIDDEN_EXTERNAL_VOLUME` and `ENABLE_POSTGRES_EXTERNAL_VOLUME` and treats either being `TRUE` as satisfying the managed-volume requirement. The two names exist because Snowflake renamed the flag during rollout — the dual lookup keeps the script working across both names without prose updates.

Pre-flight the first three via the existing `pg_lake_storage.py verify --instance` output (host region + `storage_integration` field); the last two via `pg_lake_catalog.py check-account-params`. See SKILL.md Step 0 and Step 1.

## Two Paths

```
PG iceberg tables (N)
        │
        ▼
  CREATE CATALOG INTEGRATION <ci>       ← one per PG instance + database pair
  (pg_lake_catalog.py create-integration)
        │
        ├────────────────────────────────────┐
        ▼                                    ▼
  Per-table:                          CLD (recommended for 2+ tables):
  CREATE ICEBERG TABLE <t>            CREATE DATABASE <cld>
    CATALOG = '<ci>'                    LINKED_CATALOG = (
    CATALOG_TABLE_NAME = '<pg>'           CATALOG = '<ci>',
    CATALOG_NAMESPACE = '<schema>'        ALLOWED_WRITE_OPERATIONS = NONE
                                        )
  (create-iceberg-table)              (create-cld)
        │                                    │
        ▼                                    ▼
  SELECT ... FROM <t>                 SELECT ... FROM <cld>.<schema>.<t>
                                      (all PG iceberg tables auto-surface)
```

## Per-Table Path (explicit, narrow exposure)

Good when the user wants one or two specific tables exposed to Snowflake. Each `CREATE ICEBERG TABLE` is a separate DDL.

```sql
-- 1. Catalog integration (one per PG instance + database)
CREATE CATALOG INTEGRATION my_ci
  CATALOG_SOURCE = SNOWFLAKE_POSTGRES
  TABLE_FORMAT = ICEBERG
  REST_CONFIG = (
    POSTGRES_INSTANCE = 'my_pg_instance',
    CATALOG_NAME = 'postgres',
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS
  )
  ENABLED = TRUE;

-- 2. One or more iceberg tables
CREATE ICEBERG TABLE sensor_readings
  CATALOG = 'my_ci'
  CATALOG_TABLE_NAME = 'sensor_readings'
  CATALOG_NAMESPACE = 'public';

-- 3. Query
SELECT COUNT(*) FROM sensor_readings;
SELECT * FROM sensor_readings WHERE station_name = 'A' LIMIT 10;
```

Each iceberg table is an independent SF object — drop one without affecting others.

## CLD Path (recommended for bulk exposure)

A Catalog-Linked Database is a single `CREATE DATABASE` that auto-surfaces every PG iceberg table behind the catalog integration. New PG tables appear within the refresh window (~30-35s at the default interval). Existing SF-side iceberg tables do not disappear when new PG tables are added — the CLD is additive.

```sql
-- 1. Catalog integration (same as per-table path)
CREATE CATALOG INTEGRATION my_ci
  CATALOG_SOURCE = SNOWFLAKE_POSTGRES
  TABLE_FORMAT = ICEBERG
  REST_CONFIG = (
    POSTGRES_INSTANCE = 'my_pg_instance',
    CATALOG_NAME = 'postgres',
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS
  )
  ENABLED = TRUE;

-- 2. CLD — ALLOWED_WRITE_OPERATIONS = NONE is mandatory for SNOWFLAKE_POSTGRES
CREATE DATABASE my_cld
  LINKED_CATALOG = (
    CATALOG = 'my_ci',
    ALLOWED_WRITE_OPERATIONS = NONE
  );

-- 3. Query via fully-qualified name
SELECT COUNT(*) FROM my_cld.public.sensor_readings;

-- 4. Discover tables (populates as pg_lake tables surface)
SHOW TABLES IN DATABASE my_cld;
```

### CLD is read-only by server-side mandate

`ALLOWED_WRITE_OPERATIONS = NONE` is the only accepted value. Omitting the clause or passing anything else returns a compile error:

- Missing clause: `094124 (22023): SQL Compilation Error: SNOWFLAKE_POSTGRES catalog-linked databases must explicitly specify ALLOWED_WRITE_OPERATIONS.`
- Wrong value: `094123 (22023): SQL Compilation Error: SNOWFLAKE_POSTGRES catalog-linked databases must be read-only. ALLOWED_WRITE_OPERATIONS must be set to NONE, but 'ALL' was provided.`

`pg_lake_catalog.py create-cld` always emits `= NONE` for this reason — there's no flag to override.

### `CATALOG =` silently creates a STANDARD database (no error)

The linking clause is `LINKED_CATALOG = (...)`. Writing `CATALOG = 'my_ci'` instead **does not error** — it silently creates an ordinary **STANDARD** database that is *not* catalog-linked, so no PG tables ever surface and the failure is invisible:

```sql
-- WRONG: silently creates a plain STANDARD database, no linkage, no error
CREATE DATABASE my_cld CATALOG = 'my_ci';

-- RIGHT
CREATE DATABASE my_cld
  LINKED_CATALOG = ( CATALOG = 'my_ci', ALLOWED_WRITE_OPERATIONS = NONE );
```

After creating a CLD, verify the database kind — it must be `LINKED`, not `STANDARD`:

```sql
SHOW DATABASES LIKE 'my_cld';   -- inspect the "kind" column
-- kind = STANDARD  → wrong clause was used; DROP and recreate with LINKED_CATALOG = (...)
-- kind = LINKED    → correct
```

If `SHOW TABLES IN DATABASE <cld>` is empty and no error was ever raised, check the kind first — a STANDARD database from the wrong clause is the most common cause.

### Propagation window

New PG iceberg tables typically surface through the CLD within one `REFRESH_INTERVAL_SECONDS` cycle (default 30s). When waiting for a specific table to appear, poll `cld-status` with a 60+ second budget to absorb scheduler jitter:

```bash
pg_lake_catalog.py cld-status --name my_cld --snowflake-connection <conn> --json
```

Returns `healthy` (derived from `executionState == "RUNNING"`), `iceberg_tables` (list of `{schema, name, rows}` for every surfaced Iceberg table), and `failure_details`. Non-running states → wait and retry; persistent non-running → check PG-side instance health.

## Auto-Refresh

Each `CREATE ICEBERG TABLE` can opt in to automatic metadata refresh via `AUTO_REFRESH = TRUE`. Integration-level `REFRESH_INTERVAL_SECONDS` controls cadence — it applies to **every** iceberg table under the integration (not per-table).

```sql
-- Opt in at creation time
CREATE ICEBERG TABLE sensor_readings
  CATALOG = 'my_ci'
  CATALOG_TABLE_NAME = 'sensor_readings'
  CATALOG_NAMESPACE = 'public'
  AUTO_REFRESH = TRUE;

-- Or toggle later
ALTER ICEBERG TABLE sensor_readings SET AUTO_REFRESH = TRUE;
ALTER ICEBERG TABLE sensor_readings SET AUTO_REFRESH = FALSE;

-- Manual one-shot refresh (no polling needed)
ALTER ICEBERG TABLE sensor_readings REFRESH;

-- Change interval (integration-level)
ALTER CATALOG INTEGRATION my_ci SET REFRESH_INTERVAL_SECONDS = 300;
```

Valid range for `REFRESH_INTERVAL_SECONDS`: **[30, 86400]** inclusive (minimum 30s, maximum 24h). `pg_lake_catalog.py validate_refresh_interval` enforces this client-side; if Snowflake widens or narrows the range, the server will return `001008 (22023) invalid value [...] for parameter 'REFRESH_INTERVAL_SECONDS'` and the `refresh_interval_out_of_range` translator surfaces the current bounds.

### Cost model

Auto-refresh uses Snowpipe metadata-refresh cycles — billed per table per interval. Aggregate cost scales linearly with table count and inversely with interval. Rule of thumb from our cost-warning heuristic:

- **< 10 tables at 30s default** → typically fine
- **≥ 10 tables at 30s default** → Snowpipe cost becomes non-trivial; raise interval to 300s (5 min) or higher

The `pg_lake_catalog.build_auto_refresh_cost_warning(table_count)` helper returns `warn=True` + a ready-to-paste `set-refresh-interval` command at or above the threshold. SKILL.md Step 3 calls this before confirming a bulk `--auto-refresh` pass.

### Status + history

```bash
pg_lake_catalog.py status --name sensor_readings --snowflake-connection <conn> --json
```

Returns `execution_state` (`RUNNING` = healthy), `healthy` boolean, and the last 10 refresh history rows (`REFRESHED_ON`, `STATUS`, `DURATION_MS`, ...) from `INFORMATION_SCHEMA.ICEBERG_TABLE_SNAPSHOT_REFRESH_HISTORY`.

## Error Patterns

`pg_lake_catalog.translate_error()` converts known Snowflake error shapes into actionable messages. The raw errors vary from terse to misleading; the translator gives the agent a friendly redirect when it matches, and falls through to the raw error otherwise.

| Pattern | Raw error (truncated) | Friendly redirect |
|---------|----------------------|-------------------|
| `insufficient_privileges_account` | `003001 (42501) Insufficient privileges to operate on account '<acct>'. Your primary role X must have CREATE CATALOG INTEGRATION granted on ACCOUNT Y.` | Retry with `--use-role ACCOUNTADMIN` + GRANT SQL for the specific privilege |
| `feature_not_enabled` | `004101 (42601) Invalid option CATALOG_SOURCE on catalog integration.` | Points at `check-account-params` to confirm `ENABLE_SNOWFLAKE_POSTGRES` |
| `pg_instance_pg_lake_not_supported` | `604061 (22000) POSTGRES INSTANCE 'X' does not support use of pg_lake. Please run a Postgres maintenance operation on your instance.` | Server-side maintenance — no client SQL or role retry will fix it. Surface raw error and ask user to consult their account admin or current Snowflake docs |
| `invalid_instance` | `002001 (02000) Object 'X' does not exist or not authorized.` | Causes ranked by likelihood: (1) role lacks USAGE, (2) instance doesn't exist, (3) wrong SF account. `check-account-params` + `--use-role` retry |
| `invalid_table` | `093740 (22023) Could not find Iceberg table 'Table 'X' not found in namespace 'Y''` (literal `{1}/{2}` at end) | Run `list-pg-iceberg` for valid triples |
| `wrong_catalog_name` | `000603 (XX000) INTERNAL_ERROR: ...catalog file...databaseName X` | `CATALOG_NAME` is the **PG database name** (commonly confused with the SF database name). Verify with `list-pg-iceberg` first; only drop and recreate if the name is genuinely wrong |
| `missing_external_volume` | `393923 (42601) Iceberg table X must have the table parameter EXTERNAL_VOLUME defined` | Most misleading error — **do NOT add EXTERNAL_VOLUME**. It means `--catalog` points at a non-existent integration. Verify with `describe-integration` |
| `object_already_exists` | `002002 (42710) Object 'X' already exists.` | `describe-integration` (inspect) / `drop-integration --confirm` (replace) |
| `object_not_found` | `002003 (02000) Integration/Iceberg table/Database 'X' does not exist or not authorized.` | Run the appropriate `list-*` / SHOW command, or retry with `--use-role ACCOUNTADMIN` |
| `refresh_interval_out_of_range` | `001008 (22023) invalid value [X] for parameter 'REFRESH_INTERVAL_SECONDS'` | Valid range [30, 86400] + common choices |
| `cld_allowed_write_missing` | `094124 (22023) SNOWFLAKE_POSTGRES catalog-linked databases must explicitly specify ALLOWED_WRITE_OPERATIONS` | Use `create-cld` subcommand (auto-emits the clause) |
| `cld_allowed_write_wrong_value` | `094123 (22023) ALLOWED_WRITE_OPERATIONS must be set to NONE, but 'X' was provided` | NONE is the only accepted value |

When a translation isn't available, the raw Snowflake error surfaces — safe fallback, agent can escalate to the user.

### Brittleness note

Each pattern was extracted from a single Snowflake error sample. When Snowflake changes error wording across releases, `translate_error()` returns `None` and the raw error surfaces — safe fallback, no incorrect advice. Two patterns are especially at risk because they pin to internal strings:

- **`wrong_catalog_name`** — pinned to the internal Java class name embedded in the `INTERNAL_ERROR` message. May rename across releases.
- **`object_not_found`** — case-exact match on `Integration|Iceberg table|Database`. Keyword casing has shifted across Snowflake releases before.

When wording drifts, capture a fresh raw error from a live round-trip and update the corresponding regex in `ERROR_PATTERNS`. The unit tests pin against the captured sample, so a regex change pairs with a test sample update.

## Limitations

| Limitation | Why | Alternative |
|------------|-----|-------------|
| **Cloud platform support** | The catalog integration path doesn't support every cloud + region. Refer to current Snowflake docs for the supported matrix. `pg_lake_storage.py verify` surfaces the instance host so the agent can compare against current support. The server is the ultimate source of truth: when an unsupported cloud is attempted, `create-integration` returns a translated error and the workflow falls back. | When unsupported, use the external-stage + customer-bucket flow in `data-movement.md`. |
| **Managed storage only** | The integration reads metadata from the Snowflake-managed bucket. Customer-S3 bucket paths aren't mountable this way. | On customer-S3, use external-stage (Parquet) flow. |
| **Read-only from SF** | CLD is hard-read-only (`ALLOWED_WRITE_OPERATIONS = NONE` is mandatory). Per-table `CREATE ICEBERG TABLE` via this catalog is also read-only. | Writes happen on the PG side; they propagate to SF via refresh. |
| **Same SF account pairing** | PG instance must be on the same SF account as the connection running `CREATE CATALOG INTEGRATION`. | No workaround — move the PG instance, or query directly via PG. |
| **One PG database per integration** | `CATALOG_NAME` is scalar; one integration = one PG database. | Create multiple integrations if you have multiple PG databases to expose. |
| **Integration-level refresh interval** | `REFRESH_INTERVAL_SECONDS` applies to every iceberg table under the integration. | Split into multiple integrations if you need per-table cadence. |

## End-to-End Cleanup

```sql
-- Per-table cleanup
DROP ICEBERG TABLE IF EXISTS sensor_readings;
DROP CATALOG INTEGRATION IF EXISTS my_ci;

-- CLD cleanup (order matters — CLD references the integration)
DROP DATABASE IF EXISTS my_cld;
DROP CATALOG INTEGRATION IF EXISTS my_ci;
```

Via the CLI (`drop-integration` dry-runs without `--confirm`):
```bash
pg_lake_catalog.py drop-integration --name my_ci --confirm \
  --snowflake-connection <conn> [--use-role ACCOUNTADMIN] --json
```

Dropping an integration that's still referenced by iceberg tables or CLDs fails on the server side — drop the dependent objects first. The raw Snowflake error surfaces directly when this happens (no specific translator); the message names the dependent object and is usually self-explanatory.

## Related

- **`data-movement.md`** — customer-S3 + external-stage alternative for non-eligible PG instances.
- **`iceberg-tables.md`** — PG-side Iceberg table syntax (the input to this flow).
- **`manage/SKILL.md`** — role-picker pattern referenced in Step 2 of the workflow.
- **`pg_lake_catalog.py --help`** — canonical subcommand list (the script is the source of truth; check `--help` for the current set).
