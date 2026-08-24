---
name: snowflake-postgres
description: >-
  **[REQUIRED]** Use for **ALL** Snowflake Postgres requests and for general help with any
  PostgreSQL database through standard PG tooling (psql, ~/.pg_service.conf, ~/.pgpass, pg_doctor
  diagnostics). Covers: creating, showing, suspending, resuming instances, resetting or rotating
  credentials, network policies, health checks; diagnostics such as slow queries, cache hit,
  bloat, vacuum, dead rows, locks and blocking queries, active queries, connection counts;
  external Postgres (RDS, Aurora, Azure, Cloud SQL, Neon, Supabase) and migration to Snowflake
  (assessment, logical replication, pg_dump, cutover and rollback plans); managed mirrors
  (CREATE_MIRROR, LIST_MIRRORS, $live, $changes); and pg_lake (Postgres-resident Iceberg tables,
  `CATALOG_SOURCE = SNOWFLAKE_POSTGRES` catalog integrations, catalog-linked databases). Do NOT
  use for generic Iceberg, catalog/storage integration, or data lake requests — those are owned by
  the `iceberg` skill; handle Iceberg here only when scoped to pg_lake.
---

# Snowflake Postgres

> **Windows users:** see [references/windows.md](references/windows.md) — install prereqs, credential file paths (`%APPDATA%\postgresql\` instead of `~/`), and command-flow notes differ on native Windows. WSL behaves as Linux.

## When to Use

When a user wants to manage Snowflake Postgres instances via Snowflake SQL, **or** when they want help working with any Postgres database using standard PostgreSQL tooling (`psql`, saved connections in `~/.pg_service.conf` / `~/.pgpass`, health diagnostics).

## Snowflake Postgres vs. Non-Snowflake Postgres

A single skill covers both, but the available operations differ:

| Operation | Snowflake Postgres | Non-Snowflake Postgres (Neon, Supabase, RDS/Aurora, Azure, Cloud SQL, Crunchy Bridge, self-hosted, etc.) |
|---|---|---|
| `psql` via `~/.pg_service.conf` + `~/.pgpass` | ✅ | ✅ |
| `pg_connect.py --list` (list saved connections) | ✅ | ✅ |
| `pg_doctor.py` health checks | ✅ | ✅ — uses standard pg_catalog; portable. Some checks (e.g. `outliers`) require `pg_stat_statements` to be enabled. |
| Running any SQL the user asks for via `psql` | ✅ | ✅ |
| `pg_connect.py --create` / `--reset` / `--fetch-cert` | ✅ | ❌ Snowflake-only |
| `SHOW / DESCRIBE / ALTER POSTGRES INSTANCE` (Snowflake SQL) | ✅ | ❌ Snowflake-only — never run these on external Postgres |
| Network policy setup | ✅ | ❌ Snowflake-only |
| `pg_lake` / Iceberg | ✅ | ❌ Snowflake-only |

**How to tell which one you're dealing with:**
- Snowflake Postgres: host ends with `snowflakecomputing.com` or `postgres.snowflake.app`, or the user mentions a Snowflake account/instance.
- Non-Snowflake Postgres: host matches a known provider (`*.neon.tech`, `*.supabase.co`, `*.rds.amazonaws.com`, `*.postgres.database.azure.com`, `*.aivencloud.com`, `*.postgresbridge.com` / `*.crunchybridge.com` for Crunchy Bridge, etc.), the user supplies a `postgres://...` connection string, or they explicitly mention another provider.

> **Note on Crunchy Bridge:** Snowflake Postgres shares its roots with Crunchy's technology, and some users may be coming from (or still using) **Crunchy Bridge** as a standalone managed Postgres product. Crunchy Bridge is NOT Snowflake Postgres — it's a separate external service. Treat it exactly like any other non-Snowflake Postgres (standard PG tools only; none of the Snowflake-specific commands apply).

**For non-Snowflake Postgres:** do NOT run Snowflake SQL commands (they will error and confuse the user). See `connect/SKILL.md` → "Non-Snowflake Postgres" for how to save connections via standard PG files, then `psql` / `pg_doctor.py` work the same as on Snowflake Postgres.

## Setup

1. **Check for connection**: Verify a saved connection using the `connect/SKILL.md` workflow.
2. **Load references** as needed based on intent.

## Connection Storage (PostgreSQL Standard Files)

Connections use PostgreSQL's native configuration files instead of custom formats. This provides:
- Compatibility with all PostgreSQL tools (`psql`, pgAdmin, DBeaver, etc.)
- OS-enforced security (PostgreSQL rejects `.pgpass` if permissions are wrong)
- Separation of connection metadata from secrets

Never ask for credentials in chat.

### Service File: `~/.pg_service.conf`

PostgreSQL service file - stores named connection profiles (no passwords). Allows connecting with `psql service=<name>` instead of specifying all parameters:

```ini
[my_instance]
host=abc123.snowflakecomputing.com
port=5432
dbname=postgres
user=snowflake_admin
sslmode=verify-ca
sslrootcert=/Users/me/.snowflake/postgres/certs/my_instance.pem
```

When `sslrootcert` is present, `sslmode=verify-ca` verifies the server's identity using the CA certificate (MITM protection). The cert is fetched automatically on `--create` and `--reset`, or manually with `--fetch-cert`. Existing connections with `sslmode=require` continue to work.

Users can connect manually with: `psql service=my_instance` (if psql is installed)

### Password File: `~/.pgpass`

PostgreSQL password file - stores credentials separately from connection profiles. PostgreSQL clients automatically look up passwords from this file when connecting. Must have `chmod 600` permissions.

**⚠️ NEVER display `.pgpass` contents or format with actual passwords.** Always use `pg_connect.py` to manage passwords - it handles the file securely without exposing credentials in chat.

**Running queries:** Use `psql "service=<instance_name> connect_timeout=10" -c "<SQL>"` — authentication is handled automatically via the service file and pgpass. Never read or echo credential files.

**⚠️ Always include `connect_timeout=10`** in psql invocations. Without it, a psql call against an instance with no network policy (or a suspended instance) will hang for 2+ minutes before giving up. `connect_timeout=10` fails fast so the agent can diagnose and offer the right next step.

**⚠️ Bash timeout:** All Postgres commands (psql, pg_connect.py, pg_lake_setup.py, pg_lake_storage.py) require network round-trips and SSL negotiation. **Never set `timeout_ms` below 60000 (60 seconds).** For bulk operations (COPY, CREATE TABLE AS, large queries), use 120000+ (2 minutes). The default `timeout_ms` is sufficient — do not lower it.

**⚠️ Check instance state before psql:** An instance may be in SUSPENDED state (e.g., after a manual `ALTER POSTGRES INSTANCE … SUSPEND` or a maintenance operation). A psql connection to a suspended instance will hang (PG instances do NOT auto-resume on connection). **Before running any psql or pg_lake_setup.py command**, ensure the instance is READY:

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py \
  --ensure-ready --instance-name <INSTANCE_NAME> \
  [--snowflake-connection <SF_CONN>]
```

This checks the instance state, auto-resumes if SUSPENDED, and waits up to 6 minutes for READY. The pg_lake_setup.py script also retries connections automatically (3 attempts with backoff), but `--ensure-ready` avoids wasting time on retries when the instance needs a full resume cycle.

## Progress Tracking

For multi-step operations, use `system_todo_write` to show progress:

```
┌──────────────────┬──────────────────────────────────────────────────────┐
│ Scenario         │ Create Todos                                         │
├──────────────────┼──────────────────────────────────────────────────────┤
│ Create + setup   │ Create instance → Save connection → Network policy   │
├──────────────────┼──────────────────────────────────────────────────────┤
│ Batch operations │ One todo per instance/object                         │
└──────────────────┴──────────────────────────────────────────────────────┘
```

**Rules:**
- Mark `in_progress` BEFORE starting each step
- Mark `completed` IMMEDIATELY after finishing
- Add new todos if issues are discovered mid-workflow

## Routing

⚠️ **MANDATORY: Execute Sub-Skill Immediately**

After detecting intent, you MUST:
1. Load the sub-skill file
2. Execute its workflow **in this same response**
3. Do NOT stop after loading — continue to completion

❌ **WRONG:** Load skill, then stop or explain without doing anything
✅ **RIGHT:** Load skill, then follow its workflow (which may include presenting a plan and waiting for user confirmation before executing)

| Intent | Trigger Phrases | Action |
|--------|-----------------|--------|
| **MANAGE** | "create instance", "show instances", "list instances", "suspend", "resume", "describe", "rotate password", "reset credentials", "reset access" | Load `manage/SKILL.md` → Execute SQL immediately |
| **CONNECT** | "my IP", "network policy", "can't connect", "add IP", "import connection", "save my postgres connection", "connect to my postgres", "add my neon/supabase/RDS connection", or any non-Snowflake Postgres setup question | Load `connect/SKILL.md` → Execute workflow immediately (Non-Snowflake Postgres subsection for external providers) |
| **DIAGNOSE** | "health check", "diagnose", "diagnostics", "insights", "pg_doctor", "cache hit", "bloat", "vacuum", "dead rows", "autovacuum", "locks", "blocking queries", "blocked", "waiting", "long running", "slow queries", "query performance", "outliers", "unused indexes", "table sizes", "disk usage", "storage", "connections", "connection count", "what's running", "active queries" | Load `diagnose/SKILL.md` → Execute diagnostics immediately |
| **PG_LAKE** | "pg_lake", "postgres iceberg", "pg iceberg", "iceberg table in postgres", "POSTGRES_EXTERNAL_STORAGE", "postgres COPY to S3", "postgres export to S3", "move data between postgres and snowflake", "read pg_lake in snowflake", "pg to snowflake iceberg", "catalog integration for pg_lake", "expose pg_lake to snowflake", "SNOWFLAKE_POSTGRES catalog", "catalog linked database for pg_lake", "query postgres iceberg from snowflake" | Load `pg-lake/SKILL.md` → Follow its workflow (has its own stopping points — present plan first for SETUP) |
| **MIRROR** | "create mirror", "postgres mirror", "mirror postgres to snowflake", "snowflake postgres mirroring", "managed cdc", "LIST_MIRRORS", "CREATE_MIRROR", "$live", "$changes", "replicate postgres tables into snowflake continuously" | Load `mirror/SKILL.md` → Follow its setup/query/operate/troubleshoot workflow |
| **MIGRATE** | "migrate postgres", "pg migration", "postgres to snowflake", "move my postgres", "transfer postgres", "copy from postgres", "logical replication setup", "pg_dump migration", "migration assessment", "migration readiness", "cutover plan", "rollback plan", "resume my migration", "validate migration", "migration monitor", "migrate from RDS", "migrate from Aurora", "migrate from Azure postgres", "migrate from Cloud SQL", "migrate from Crunchy Bridge", "migrate from Neon", "migrate from Supabase" | Load `migrate/SKILL.md` → Follow its workflow (interactive scope gathering via `ask_user_question`; presents assessment / hybrid plan / cutover plan for approval before executing) |

Generic Snowflake Iceberg, catalog integration, external volume, and storage integration requests belong to the `iceberg` skill unless the user is clearly working with Postgres-resident Iceberg / `pg_lake`. **Exception:** `CATALOG_SOURCE = SNOWFLAKE_POSTGRES` (the pg_lake-specific catalog integration path, covered by the READ-FROM-SNOWFLAKE workflow in `pg-lake/SKILL.md`) belongs here, not in the generic `iceberg` skill — that path reads Iceberg metadata from a pg_lake PG instance, not from a user-supplied REST catalog.

### Unrecognized or Extended Operations

If the user's request involves Snowflake Postgres but doesn't match the intents above (e.g., fork, replica, maintenance window, upgrade, POSTGRES_SETTINGS):

1. **First** check `references/documentation.md` for the relevant doc URL
2. **Fetch** the official docs to get current syntax
3. **Apply** the same safety rules (approval for billable/destructive operations, no secrets in chat)

Examples of operations requiring doc lookup:
- Fork instance / point-in-time recovery
- Create read replica
- Set maintenance window
- Modify POSTGRES_SETTINGS
- Major version upgrades

## Global Safety Rules

- Never ask for passwords in chat or echo secrets.
- **Never use `cat`, `echo`, heredoc (`<<`), or any shell command to create files containing `access_roles` or passwords** - these appear in chat history.
- Always require explicit approval for billable actions and network policy changes.
- For DESCRIBE responses, never show `access_roles`.
- **Prefer Cortex Search docs over web search for Snowflake-specific questions.** Check skill references and Snowflake documentation via Cortex Search first. Only fall back to web search if Cortex Search doesn't have what you need.
- For CREATE responses, never show raw SQL results - `access_roles` contains passwords.
- If any output might include secrets (passwords, access tokens), never display them in chat. Scripts save secrets to secure files (`~/.pgpass` with 0600 permissions) without echoing them.
- **For CREATE INSTANCE: MUST use `pg_connect.py --create`** - never use SQL tool directly. The script saves the connection automatically.
- **For RESET ACCESS: MUST use `pg_connect.py --reset`** - never use SQL tool directly. The script saves the password automatically.
- **Do NOT ask if user wants to save after CREATE/RESET** - the scripts save automatically.
- **Do NOT run RESET after CREATE** - CREATE already saves the password. RESET is only for rotating passwords later.
- **Never execute destructive operations (DROP TABLE, DROP COLUMN, DELETE, TRUNCATE, DROP INTEGRATION) without the user explicitly requesting it.** If the user asks to "clean up" or "remove" something, confirm exactly what will be deleted before executing. DROP TABLE on Iceberg tables permanently deletes S3 data files.

## Tools

Agent-facing tools invoked directly from this skill. Sub-skills (`migrate/`,
`pg-lake/`, etc.) document their own additional scripts in their respective
`SKILL.md` files; internal helpers under `scripts/shared/` (e.g.
`pg_common.py`, `sf_session.py`) are not listed here.

### Tool: ask_user_question

**Description:** Ask the user to choose from a fixed list of options.

**When to use:** Present configuration menus (instance size, storage, HA, version, network policy).

### Script: network_policy_check.py

**Description:** Check whether an IP is allowed by a Snowflake network policy.

**Usage:**
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/network_policy_check.py \
  --policy-name <POLICY_NAME> \
  [--ip <IP>]
```

### Script: pg_connect.py

**Description:** Manage Snowflake Postgres connections. Handles CREATE, RESET, and connection file management (`~/.pg_service.conf` and `~/.pgpass`) without exposing credentials.

**Usage (create instance - executes SQL + saves connection + probes port 5432):**
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py \
  --create \
  --instance-name <NAME> \
  --compute-pool <COMPUTE_FAMILY> \
  --storage <GB> \
  [--enable-ha] \
  [--postgres-version <VERSION>] \
  [--network-policy <POLICY_NAME>] \
  [--auth-authority <POSTGRES|POSTGRES_OR_SNOWFLAKE>] \
  [--storage-integration <INTEGRATION_NAME>] \
  [--postgres-settings '<JSON>'] \
  [--comment '<TEXT>'] \
  [--use-role <SNOWFLAKE_ROLE>] \
  [--snowflake-connection <NAME>]
```

For valid compute families, storage limits, and HA restrictions, see `references/instance-options.md`.

After a successful CREATE the script runs a 20s TCP probe against `host:5432` and prints one of: reachable, timeout (no network policy), refused (still provisioning), or dns_error (hostname not yet propagated). **The agent must act on the probe result** — see `manage/SKILL.md` Step 7.

**Usage (reset credentials - executes SQL + updates password):**
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py \
  --reset \
  --instance-name <NAME> \
  [--role <snowflake_admin|application>] \
  [--host <HOST>] \
  [--use-role <SNOWFLAKE_ROLE>] \
  [--snowflake-connection <NAME>]
```
Use `--host` to create the service entry if it doesn't exist (e.g., from DESCRIBE output).

**`--use-role`** (applies to `--create`, `--reset`, `--fetch-cert`, `--ensure-ready`, `--upgrade-ssl`): overrides the Snowflake session role for this invocation only. Passed to the Snowflake connector; does not modify `~/.snowflake/connections.toml` or `~/.snowflake/config.toml`. Use when the default role lacks `CREATE POSTGRES INSTANCE` or other required privileges.

**Usage (fetch CA certificate for server identity verification):**
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py \
  --fetch-cert \
  --instance-name <NAME> \
  [--snowflake-connection <NAME>]
```
Fetches the CA certificate via `DESCRIBE POSTGRES INSTANCE` and upgrades the service entry to `sslmode=verify-ca`. Run this for existing connections that use `sslmode=require`.

**Usage (list saved connections):**
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py --list
```

**Usage (ensure instance is ready before PG operations):**
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py \
  --ensure-ready \
  --instance-name <NAME> \
  [--snowflake-connection <NAME>] \
  [--no-auto-resume]
```
Checks instance state via Snowflake, auto-resumes if SUSPENDED, waits for READY. Use `--no-auto-resume` to only check without resuming.

Uses Snowflake connection from `~/.snowflake/connections.toml` or environment variables. Use `--snowflake-connection` to specify a named connection.

### Script: pg_doctor.py

**Description:** Run Postgres health diagnostics. All queries run in readonly mode with statement timeout.

**Usage (full health check):**
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_doctor.py \
  --connection-name <NAME>
```

**Usage (single check):**
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_doctor.py \
  --connection-name <NAME> \
  --check <CHECK_NAME>
```

**Flags:** `--json`, `--detailed`, `--category <CATEGORY>`, `--all`, `--list-checks`, `--timeout <MS>`

### Script: pg_lake_setup.py

**Description:** pg_lake extension setup and verification on Postgres. Checks extensions, enables pg_lake, configures S3, verifies access, manages Iceberg tables.

**Usage:**
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_setup.py \
  --check-extensions --connection-name <PG_CONN> --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_setup.py \
  --enable-extensions --connection-name <PG_CONN>
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_setup.py \
  --verify-s3 --connection-name <PG_CONN> --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_setup.py \
  --list-iceberg --connection-name <PG_CONN> --json
```

### Script: pg_lake_storage.py

**Description:** Snowflake storage integration management for pg_lake. Creates, describes, attaches, and drops POSTGRES_EXTERNAL_STORAGE integrations. Sensitive IAM values written to secure temp files.

**Usage:**
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_storage.py \
  create --name <NAME> --role-arn <ARN> --locations s3://bucket/ \
  --snowflake-connection <SF_CONN> --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_storage.py \
  describe --name <NAME> --snowflake-connection <SF_CONN>
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_storage.py \
  check-aws --role-arn <ARN> \
  --expected-principal <IAM_USER_ARN> --expected-external-id "<EXT_ID>" \
  [--aws-profile <PROFILE>] --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_storage.py \
  update-aws --role-arn <ARN> --sensitive-file <DESCRIBE_OUTPUT_FILE> \
  [--aws-profile <PROFILE>] --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_storage.py \
  attach --instance <INST> --integration <NAME> --snowflake-connection <SF_CONN>
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_storage.py \
  verify --instance <INST> --snowflake-connection <SF_CONN> --json
```

## Output

Routes to the correct workflow and returns the results from that sub-skill.

## Stopping Points Summary

| Operation | Approval Required |
|-----------|-------------------|
| CREATE instance | ⚠️ Yes (billable) |
| SUSPEND instance | ⚠️ Yes (drops connections) |
| Network policy changes | ⚠️ Yes |
| CREATE storage integration | ⚠️ Yes (cloud resources, ACCOUNTADMIN) |
| Update AWS trust policy | ⚠️ Yes (manual AWS step) |
| RESUME instance | No |
| LIST/DESCRIBE | No |
| Health check / diagnostics | No (readonly) |

**Resume rule:** On approval ("yes", "proceed", "approved"), continue without re-asking.

## Troubleshooting

**Error: `invalid property 'STORAGE_SIZE'`**
→ Use `STORAGE_SIZE_GB` (not `STORAGE_SIZE`)

**Error: `Missing option(s): [AUTHENTICATION_AUTHORITY]`**
→ Add `AUTHENTICATION_AUTHORITY = POSTGRES`

**Error: Network policy not working**
→ Verify rule uses `MODE = POSTGRES_INGRESS`

**Error: Connection refused**
→ IP not in network policy. Offer to check IP and add to policy.

**Error: `Insufficient privileges to operate on account`**
→ The current Snowflake role lacks `CREATE POSTGRES INSTANCE ON ACCOUNT` (or equivalent). Retry the `pg_connect.py` call with `--use-role ACCOUNTADMIN`. If no available role has the grant, ask the account admin to run `GRANT CREATE POSTGRES INSTANCE ON ACCOUNT TO ROLE <role>;`. The `--use-role` flag overrides the role for that one invocation only — it does not mutate `connections.toml` or `config.toml`.

**Error: `INTERNAL_ERROR: PostgresUtils::getOrCreateTeamAndTeamIamRole():team_iam_role_arn_not_found`**
→ Server-side error, not a client-side issue. Retry once — transient cases sometimes resolve. If persistent, verify Postgres availability in the account's region and escalate with the exact error text.

**Error: `SHOW POSTGRES INSTANCES` fails with "unsupported feature" / "syntax error"**
→ Snowflake Postgres may not be enabled on this account. Contact the account admin to verify regional availability and confirm enablement. Do not attempt `CREATE POSTGRES INSTANCE` until the pre-flight check passes.

**Error: psql hangs on connect / `connection timed out`**
→ No network policy allows the client IP. Always include `connect_timeout=10` in psql so hangs fail fast (e.g. `psql "service=<name> connect_timeout=10"`). Fix: route to `connect/SKILL.md` → Setup Network Policy.

## References

- `references/instance-options.md` - Valid compute families, storage limits
- `references/instance-states.md` - Instance state descriptions
- `references/documentation.md` - Official Snowflake docs URLs (fallback for commands not covered here)
- `references/thresholds.md` - Health check thresholds and recommended actions
