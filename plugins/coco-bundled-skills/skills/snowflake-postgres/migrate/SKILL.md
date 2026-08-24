---
name: migrate
description: "Migrate PostgreSQL databases to Snowflake Postgres. **[REQUIRED]** Use for ALL pg migration tasks including: pg migration, migrate postgres, replicate to snowflake postgres, pg_dump migration, logical replication setup, migration assessment, data validation, cutover planning, rollback strategy, postgres sync, database move, pg transfer, copy postgres data. Triggers: migrate postgres, pg migration, postgres to snowflake, replication setup, migration readiness, cutover plan, rollback plan, move my postgres, sync databases, transfer postgres, copy from postgres, postgres dump, pg_restore, migrate from RDS, migrate from Aurora, migrate from Azure postgres, migrate from Cloud SQL."
parent_skill: snowflake-postgres
---

# PostgreSQL to Snowflake Postgres Migration

> **Windows users:** see [references/windows.md](../references/windows.md) — install prereqs, credential file paths (`%APPDATA%\postgresql\` instead of `~/`), and command-flow notes differ on native Windows. WSL behaves as Linux.

## When to Use

When migrating any PostgreSQL database to Snowflake Postgres:
- On-premises PostgreSQL → Snowflake Postgres
- Cloud PostgreSQL (RDS, Aurora, Cloud SQL, Azure, Crunchy Bridge, Neon, Supabase) → Snowflake Postgres
- Self-managed PostgreSQL → Snowflake Postgres

> **Credentials — always use service names, never passwords in chat.**
> Passwords should end up in `~/.pgpass`, referenced by a profile in `~/.pg_service.conf`, so standard PostgreSQL tools (`psql`, `pg_dump`, `pg_restore`, `pg_dumpall`) keep working. In chat-safe setup flows, gather only non-secret fields in chat, direct the user to `/secrets` for the password, then register the profile so the password is written into `~/.pgpass` without appearing in chat or process argv. Pass `--source-service <NAME>` / `--target-service <NAME>` to every migration script invocation — never `--password <pw>` or `-W <pw>` in chat.
>
> - Register a Snowflake Postgres **target** profile once: `uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py --create --instance-name <NAME> --compute-pool <COMPUTE_FAMILY> --storage <GB>` (also fetches the CA cert and saves the profile under the lowercased instance name). `--role` is for `--reset` only — `--create` provisions all roles automatically. To run the SQL with an elevated Snowflake role, pass `--use-role ACCOUNTADMIN` (session-scoped, not persisted). For valid compute families, storage bounds, and HA restrictions, see `../references/instance-options.md`.
> - Register a non-Snowflake **source** profile once: collect `host` / `port` / `dbname` / `user` / `sslmode` in chat, have the user add the password via `/secrets`, then run `uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/shared/pg_common.py --add-source-service <NAME> --host ... --port ... --dbname ... --user ... [--sslmode ...]`. `pg_common.py` accepts the password from agent-injected env vars as well as `--password`, so the chat-safe path still lands the secret in `~/.pgpass`. Trusted-shell fallback: rerun the same command once outside chat with `--password ...`. `pg_common.py` is invoked as a script because it isn't packaged as an importable module at the project root; the file's `__main__` block dispatches the CLI directly.
>
> After profiles exist, every migration script invocation looks like `… --source-service prod_source --target-service sf_target …` with no password material in sight.

## Helper: `setup_connection` shell function

Several legacy reference docs (under `replicate/`, `dump-restore/`, `rollback/`, `validate/references/`) include `psql` examples that begin with `setup_connection "SOURCE"` or `setup_connection "TARGET"`. That is a small shell helper that exports `PG*` env vars from the prefixed `SOURCE_PG*` / `TARGET_PG*` ones. The function definition lives in `migrate/references/pg_migration_env.template` alongside the env-var template — copy the template to `~/.pg_migration_env`, fill it in, and `source` it once per shell session to make every legacy example runnable.

In **chat-safe workflows you don't need this helper at all** — prefer the Python scripts under `migrate/scripts/` with `--source-service` / `--target-service` flags, which never touch `PGPASSWORD` and never echo credentials.

## First Question: Interactive Scope Gathering

**MANDATORY: Use `ask_user_question` for each fixed-choice step. Do NOT present all questions as a wall of text. For exact identifiers (database names, file paths), ask in normal chat after the relevant choice, or use the tool's automatic "Something else" path if available.**

### Step 1: Ask About Assessment

```
question: "Would you like to run a migration assessment first?"
header: "Assessment"
options:
  - label: "Yes"
    description: "Analyze the source database for blockers, complexity, and recommended method before migrating"
  - label: "No"
    description: "I already know my migration approach — skip straight to setup"
```

**If Yes** → Gather connection details (Step 1a), then load `assess/SKILL.md`. The assessment will recommend a method and present it at its approval checkpoint. After the user approves a method, proceed to Step 2 (scope).
**If No** → Skip assessment entirely. Proceed to Step 2 (scope), then ask for method directly at Step 5.

### Step 1a: Get Source Connection (if Assessment)

Load `references/connection-setup.md` to gather source connection details.

For assessment-first workflows, the first connection question should make the existing-connection path obvious:
- `Saved connection` means "I already have a saved source connection"
- `Enter source details now` means "register a new source profile now"
- `Legacy environment file` is the fallback for older shell-based workflows

If the user already has a saved source connection, **list saved connections first and let them pick**. Do not send them to inspect `~/.pg_service.conf` manually unless the picker path fails. If the user provides raw host / port / dbname / user values instead of an existing saved connection, direct them to `/secrets` for the password, register a source profile so the password lands in `~/.pgpass`, then run assessment via `assess/SKILL.md`.

**Do not ask about target instance existence, target profiles, or billable target creation during assessment intake.** Assessment presents findings and recommends a method at its approval checkpoint (assess/SKILL.md Step 4). The user selects the method there, and only then do target-creation / billable questions become relevant.

### Step 2: Ask What to Migrate

**IMPORTANT:** Even if the user has a database specified in their environment file or connection string, always confirm which database(s) to migrate. Do not assume the env variable is the correct or only target.

```
question: "What would you like to migrate to Snowflake Postgres?"
header: "Scope"
options:
  - label: "Single database"
    description: "Migrate one specific database"
  - label: "Multiple databases"
    description: "Migrate a specific list of databases"
  - label: "All databases"
    description: "Migrate the entire cluster"
```

**Based on response:**
- **Single database** → Ask for database name (Step 2a), even if one is already set in the environment
- **Multiple databases** → Ask for list of database names (Step 2b)
- **All databases** → Note will use `pg_dumpall`

### Step 2a: Get Database Name (if Single)

Ask for the exact database name in normal chat after the user chooses **Single database**. Do not use unsupported free-text question fields here.

### Step 2b: Get Database List (if Multiple)

Ask the user to send the exact database names in normal chat after they choose **Multiple databases** (comma-separated or one per line). Do not use unsupported free-text question fields here.

### Step 3: Ask About Schema Scope

```
question: "Which schemas should be migrated?"
header: "Schemas"
options:
  - label: "All schemas"
    description: "Migrate all user schemas (default)"
  - label: "Specific schemas"
    description: "Only migrate selected schemas"
  - label: "Exclude schemas"
    description: "Migrate all except certain schemas"
```

### Step 4: Ask About Users/Roles

```
question: "Should users, roles, and grants be migrated?"
header: "Roles"
options:
  - label: "Yes (recommended)"
    description: "Migrate using pg_dumpall --globals-only"
  - label: "No"
    description: "Roles already exist or managed separately"
  - label: "Partial"
    description: "Only specific roles"
```

**Based on response:**
- **Yes / Partial** → Load `security/SKILL.md` and run that workflow FIRST,
  before any data migration. Roles must exist on the target before
  ownership/grants in the data dump can resolve. Return here after
  `security/SKILL.md` completes.
- **No** → Continue to Step 5.

**Notes:** Cloud-managed roles (`rds_*`, `azure_*`, `cloudsql*`) cannot be
migrated and are filtered out by `filter_vendor_dump.py`.

### Step 5: Ask About Method (if assessment was skipped)

Only ask this if the user chose **No** at Step 1 (no assessment).

```
question: "Which migration method do you want to use?"
header: "Method"
options:
  - label: "Logical replication"
    description: "Near-zero downtime. Requires PG 10+, tables with primary keys, network connectivity (target→source)"
  - label: "pg_dump/pg_restore"
    description: "Offline migration. Requires a downtime window. Simplest approach."
  - label: "Hybrid"
    description: "Logical replication for qualifying tables + pg_dump for non-replicable objects (unlogged, no PK, inheritance)"
  - label: "postgres_fdw"
    description: "Foreign data wrapper. Target queries source directly via SQL. Good for selective/filtered migration or as alternative to pg_dump in hybrid."
  - label: "Replica-assisted (large DB)"
    description: "For databases >= 2 TB or RDS/Aurora with S3 Parquet export + pg_lake. Replica handles initial load; logical replication catches up."
```

**Based on response:**
- **Logical replication** → Load `replicate/SKILL.md`
- **pg_dump/pg_restore** → Load `dump-restore/SKILL.md`
- **Hybrid** → Investigate/classify actual objects first (and review inheritance semantics if present), then ask dump timing and execute the phased plan (see `assess/SKILL.md` Step 5 for details)
- **postgres_fdw** → See `references/complex-migration-strategies.md` (postgres_fdw section). Can also be used within Hybrid instead of pg_dump.
- **Replica-assisted (large DB)** → Load `large-db/SKILL.md`

**Auto-route to LARGE-DB** when ANY of these are detected without asking:
- User mentions "TB", "terabyte", "large database", "very large", "S3 export"
- Source is RDS/Aurora and database size > 2 TB
- Assessment reports `total_size_bytes >= 2_000_000_000_000`

If assessment **was** performed, the method was already chosen at the assessment approval checkpoint — skip this step.

### Step 6: Proceed to Connection Setup

After gathering scope and method, load `references/connection-setup.md` for connection setup, then proceed to the chosen migration method sub-skill.

## Setup

> Need **continuous managed replication from Snowflake Postgres into Snowflake tables** via `SNOWFLAKE.POSTGRES.CREATE_MIRROR`, `$live`, or `$changes`? That is owned by `../mirror/SKILL.md`, not this migration skill. Use `migrate/` for one-time or cutover-oriented moves into Snowflake Postgres.

1. **Load** `references/migration-overview.md` for architecture context
2. **Load** `references/blockers-checklist.md` for common migration blockers

## Intent Detection

| Intent | Trigger Phrases | Route |
|--------|-----------------|-------|
| **ASSESS** | "migration readiness", "check blockers", "assessment" | Load `assess/SKILL.md` |
| **REPLICATE** | "logical replication", "live sync", "near-zero downtime" | Load `replicate/SKILL.md` |
| **LARGE-DB** | "large database", "terabyte migration", "TB", "S3 export", "RDS Parquet export", "very large", "2TB", "5TB", "fast initial load", "replica-assisted" | Load `large-db/SKILL.md` |
| **DUMP** | "pg_dump", "dump and restore", "offline migration" | Load `dump-restore/SKILL.md` |
| **VALIDATE** | "validate migration", "data validation", "pgcompare" | Load `validate/SKILL.md` |
| **SECURITY** | "migrate users", "migrate roles", "grants", "RBAC" | Load `security/SKILL.md` |
| **CUTOVER** | "cutover plan", "go-live", "switch over" | Load `cutover/SKILL.md` |
| **ROLLBACK** | "rollback plan", "failback", "reverse migration" | Load `rollback/SKILL.md` |
| **MONITOR** | "monitor replication", "check lag", "replication status" | Load `monitor/SKILL.md` |
| **RESUME** | "resume migration", "continue migration", "where did I leave off" | Load `resume/SKILL.md` |
| **PAUSE** | "pause migration", "stop after this phase", "save progress" | Load `resume/SKILL.md` (pause workflow) |
| **REPEAT** | "repeat phase", "re-run validation", "redo pg_dump", "run phase again" | Load `resume/SKILL.md` (repeat workflow) |
| **PLATFORM** | "migrate from RDS", "migrate from Aurora", "migrate from Azure", "migrate from Cloud SQL", "migrate from Heroku", "migrate from Crunchy Bridge", "migrate from Supabase", "migrate from Neon", "migrate from Aiven", "on-prem postgres" | Load `references/source-platform-guide.md` (router that auto-detects platform and points to the exact per-platform file to read; do not derive filenames from the platform display name) |
| **FULL** | "full migration", "end-to-end migration" | Start with `assess/SKILL.md` |
| **FALLBACK** | (no match above) | Ask user to clarify intent, then route |

## Migration Methods

### 1. Logical Replication (Near-Zero Downtime)
- Best for: Production databases requiring minimal downtime
- Requirements: PostgreSQL 10+ source, tables with primary keys, network connectivity (Target→Source)
- Process: Network verify → Live sync → Cutover → Validation

### 2. pg_dump/pg_restore (Offline)
- Best for: Development/staging, smaller databases, simple migrations
- Requirements: Downtime window available
- Process: Dump → Transfer → Restore → Validation

### 3. Direct COPY (Bulk Transfer)
- Best for: Individual tables, data refresh scenarios
- Requirements: Network connectivity between source and target

### 4. RDS S3 Parquet Export + pg_lake (AWS Only)
- Best for: Very large RDS/Aurora databases (200GB+)
- Requirements: pg_lake extension, S3 bucket, IAM roles

### 5. Hybrid Migration (Mixed Workloads)
- Best for: Databases with mix of replicable and non-replicable objects
- Use when: Unlogged tables, table inheritance, tables without PKs that cannot be modified
- Process: Logical replication for qualifying tables + pg_dump for blockers
- Tool: `<SKILL_DIR>/migrate/scripts/generate_hybrid_plan.py` generates phased plan

**For time estimates, see `references/time-estimation.md`**

## Workflow Overview

```
┌─────────────┐     ┌─────────────────────┐     ┌──────────────┐     ┌──────────────┐
│ SCOPE CHECK │────▶│   ASSESS            │────▶│   APPROVAL   │────▶│   SECURITY   │
│             │     │                     │     │              │     │  (if opted)  │
│ • Database? │     │ • Blockers          │     │ Review       │     │              │
│ • Schemas?  │     │ • Size              │     │ findings     │     │ • Roles      │
│ • Roles?    │     │ • Features          │     │ Choose method│     │ • Grants     │
└─────────────┘     └─────────────────────┘     └──────┬───────┘     └──────┬───────┘
                                                       │                    │
                    ┌──────────────────────────────────┘    ┌───────────────┘
                    │                                       │
                    ▼                                       ▼
     ┌──────────────────────────────┐          ┌──────────────────────┐
     │  Method: Replication         │          │  Method: Dump/Restore│
     │  ─────────────────           │          │  ────────────────    │
     │  Replicate → Monitor → ...   │          │  pg_dump → restore   │
     └──────────────┬───────────────┘          └──────────┬───────────┘
                    │                                      │
                    │   ┌──────────────────────────────┐   │
                    │   │  Method: Hybrid               │   │
                    │   │  ─────────────────            │   │
                    │   │  Replicate (PK tables)        │   │
                    │   │  + pg_dump (non-replicable)   │   │
                    │   └──────────────┬───────────────┘   │
                    │                  │                    │
                    └──────────┬───────┘────────────────────┘
                               │
                               ▼
                 ┌──────────────┐     ┌──────────────┐
                 │   VALIDATE   │────▶│   CUTOVER    │
                 │              │     │              │
                 │ • Row counts │     │ • Stop writes│
                 │ • Checksums  │     │ • Switch DNS │
                 │ • pgCompare  │     │ • Sync seqs  │
                 └──────────────┘     └──────────────┘
```

## Long-Running Phases

Use background agents only for **read-mostly observation** during long-running migration work: initial sync, long `pg_dump` / `pg_restore`, replica catch-up, or a short post-cutover soak check.

- **Background agents are safe for monitoring, summarizing status, and surfacing alerts.**
- **`resume/SKILL.md` remains the durable path** for anything that may span hours, days, or a new session.
- **Do not hand off state-changing or downtime-sensitive steps** to background agents: credential setup, target create/reset, schema DDL, subscription create/drop, cutover, or rollback.

## User Prompts Summary

| Step | Prompt | Options/Type |
|------|--------|--------------|
| 1 | **Assessment** | Yes / No |
| 2 | **Migration Scope** | Single DB / Multiple DBs / All DBs |
| 2a | Database Name (if single) | Follow-up chat with exact name |
| 2b | Database List (if multiple) | Follow-up chat with exact names |
| 3 | **Schema Scope** | All schemas / Specific / Exclude |
| 4 | **Users/Roles** | Yes / No / Partial |
| 5 | **Method** (if no assessment) | Logical replication / pg_dump / Hybrid |
| 5 | **Method** (if assessment done) | Chosen at assess/SKILL.md approval checkpoint |
| 6 | **Connection Setup** | See `references/connection-setup.md` |
| If Hybrid | **Dump Timing** | Now (during migration) / At cutover (with sequences) |
| Any phase | **Pause** | Update state file, exit. Resume with "resume migration" |
| Any phase | **Repeat Phase** | Re-run a completed phase (e.g., validation before cutover) |
| Before Long Ops | **Monitor Progress** | Live dashboard / Manual / Background |
| After Migration | **Validation Method** | Row counts / Checksums / pgCompare (multi-select) |

**CRITICAL: Each fixed-choice prompt uses `ask_user_question` - NEVER dump all questions as text.**

## Critical Migration Facts

**Supported in Snowflake Postgres:** 70+ extensions (pgvector, PostGIS, pg_cron, pglogical), logical replication as subscriber, standard PostgreSQL features.

**Not supported / requires manual handling:** See [`references/blockers-checklist.md`](references/blockers-checklist.md) for the full list of 21 blockers (unlogged tables, table inheritance, large objects, sequences, MVs, missing PKs, pgvector indexes, etc.) with detection queries and remediation steps. The **assessment phase auto-detects all of these** — `assess/SKILL.md` Step 4 produces the report.

**Operational ordering for things logical replication does not carry:**
- **Users/Roles/Grants** — migrate FIRST via `security/SKILL.md` (uses `pg_dumpall --globals-only`). Required so dump ownership/grants resolve on the target.
- **Sequences** — sync as the FINAL cutover step via `cutover_tools.py sequences --execute`.
- **pgvector indexes** — rebuild AFTER replication catches up (data replicates, IVFFlat/HNSW indexes do not).

## Safety Rules

- **MANDATORY PREFLIGHT CHECK** before any migration: run `prepare_target.py preflight-check --schemas <list>` to verify that target schemas (except `public`) do not already exist with objects. If they do, abort and ask the user to clean or choose a different target.
- **MANDATORY CHECKPOINT** after assessment - user must approve before migration
- **MANDATORY CHECKPOINT** before creating Snowflake Postgres instance (billable)
- **MANDATORY CHECKPOINT** before cutover (point of no return)
- **MANDATORY CHECKPOINT** before any destructive operation (DROP, TRUNCATE)
- Always verify network connectivity before starting replication
- Never expose connection credentials in chat
- **Always have a rollback plan before cutover**

## Tool Usage Rules

- **Prefer the Python migration helpers where available.** Assessment, connectivity, validation, and replication setup are Python-based (`<SKILL_DIR>/migrate/scripts/` and `<SKILL_DIR>/scripts/shared/`), but dump/restore and some legacy operator workflows still require PostgreSQL client tools such as `pg_dump`, `pg_restore`, and `psql`.
- **Always pass `--no-psqlrc` (short form: `-X`) to every `psql` invocation in migration workflows.** A user's `~/.psqlrc` can silently flip `AUTOCOMMIT`, `ON_ERROR_STOP`, output format (`\x`, `\pset`, `\timing`), and aliases — any of which can corrupt heredocs, break output parsing in validation scripts, or leave DDL half-applied. Since PG 9.6, `psql -c "..."` no longer implies `-X`, so even one-liners need it explicitly. This applies to every form: `psql -c`, `psql -f`, `psql <<EOF`, and `... | psql`. The flag is not needed for `pg_dump` / `pg_restore` / `pg_dumpall` (they don't read `psqlrc`).
- **After assessment, ALWAYS generate the HTML report.** Open it automatically when an interactive desktop/browser is available; otherwise provide the report path and summary. `run_assessment.py` opens the report by default (pass `--no-open` to suppress for non-interactive runs; pass `--open <file>` to reopen an existing report without re-running).
- **Python dependencies** are managed by `uv` via `<SKILL_DIR>/pyproject.toml`. The `uv run --project <SKILL_DIR> python …` invocations in this skill resolve `psycopg2-binary` and `pg8000` automatically — no manual `pip install` or virtualenv setup required. Scripts call `pg_common.check_driver()` at entry and surface install guidance if the driver is missing.

## Tools

### Python Scripts

> **Full CLI reference with all flags, subcommands, and examples:** see [`references/script-usage.md`](references/script-usage.md)

#### Migration scripts (in `migrate/scripts/`)

| Script | Purpose |
|--------|---------|
| `run_assessment.py` | Full assessment + HTML report (supports `--schemas` for scoped assessment) |
| `validate_migration.py` | Compare row counts, checksums, aggregates (handles materialized views separately) |
| `prepare_target.py` | Pre-restore target prep: preflight-check, extensions, check-data, clean-schemas |
| `cutover_tools.py` | Generate/execute sequence sync + trigger management |
| `setup_replication.py` | **Safe-DSN CREATE/DROP SUBSCRIPTION wrapper** — resolves source password from `~/.pgpass` via `--source-service`, constructs DSN in-process, never leaks credentials to chat transcripts or shell history. Use instead of the legacy `psql <<EOF ... password=$SOURCE_PGPASSWORD ... EOF` heredoc pattern. |
| `migration_monitor.py` | Monitor replication lag, sync progress, dashboard |
| `migration_helpers.py` | PostGIS assessment, pgvector index rebuild, replication blocker detection, readiness check |
| `validate_schema_compatibility.py` | Pre-flight schema validation (extensions, types, indexes) |
| `generate_hybrid_plan.py` | Generate hybrid migration plan for mixed workloads |
| `post_migration_cleanup.py` | Tear down replication artifacts (subscriptions, publications, slots, test objects) — wired in by `cutover/SKILL.md` after final validation |
| `filter_vendor_dump.py` | Filter vendor-specific commands from pg_dump (Crunchy, RDS, Azure, GCP, Neon platform roles). Invoke via `python` or `uv run python`. Reads stdin or a positional input file; supports `--stats` and `--verbose`. |

#### Shared scripts (in `scripts/shared/`)

| Script | Purpose |
|--------|---------|
| `pg_common.py` | Shared DB connection, query, arg-parsing, identifier-quoting utilities (used by every script above; includes venv detection) |
| `test_connectivity.py` | Test source/target connections + network path (DNS, TCP, auth, replication readiness, target→source via postgres_fdw) |

### Sub-Skills

| Sub-Skill | Purpose |
|-----------|---------|
| `assess/` | Pre-migration assessment and blocker detection |
| `replicate/` | Logical replication setup (near-zero downtime) |
| `large-db/` | Replica-assisted migration for very large databases |
| `dump-restore/` | pg_dump/pg_restore workflow (offline) |
| `validate/` | Post-migration validation (incl. pgCompare) |
| `security/` | Users, roles, and permissions migration |
| `cutover/` | Step-by-step cutover runbook |
| `rollback/` | Rollback and failback strategies |
| `monitor/` | Replication monitoring and alerting |
| `resume/` | Track state and resume after interruption |

### Reference Documents

| Reference | Purpose |
|-----------|---------|
| `references/connection-setup.md` | Connection configuration (Steps 5-9) |
| `references/connection-troubleshooting.md` | Auth methods, common errors |
| `references/command-logging.md` | Audit trail setup |
| `references/time-estimation.md` | Migration duration estimates |
| `references/instance-sizing.md` | Snowflake Postgres instance sizing recommendations based on source DB |
| `references/source-platform-guide.md` | Platform router — auto-detects source (RDS, Aurora, Azure, GCP, Heroku, Crunchy, Supabase, Neon, Aiven, on-prem) and points to the exact per-platform reference path in `references/source-platforms/` |
| `references/blockers-checklist.md` | Migration blockers with detection queries |
| `references/complex-migrations.md` | Index: PostGIS, partitions, custom types, LOBs (split into 3 focused docs) |
| `references/complex-spatial-vector.md` | PostGIS spatial data and pgvector index migration |
| `references/complex-schema-objects.md` | Partitions, inheritance, functions, triggers, custom types, FTS, JSON, LOBs |
| `references/complex-migration-strategies.md` | Unlogged tables, hybrid migration, audit script, PgBouncer, app compat |
| `references/migration-overview.md` | Architecture and concepts |
| `references/lessons-learned.md` | Real-world issues and solutions from migrations |
| `dump-restore/references/dump-commands.md` | Detailed pg_dump commands and monitoring |
| `dump-restore/references/restore-commands.md` | Detailed pg_restore, post-tasks, sequences |
| `replicate/references/subscription-management.md` | Publication and subscription setup |
| `replicate/references/initial-sync.md` | Initial sync monitoring and management |
| `replicate/references/cutover-sequence.md` | Cutover, validation, and sequence sync |
| `validate/references/validate-row-counts.md` | Row count validation procedures |
| `validate/references/validate-checksum.md` | Checksum-based validation |
| `validate/references/validate-snowconvert.md` | SnowConvert SQL validation |
| `validate/references/validate-pgcompare.md` | pgCompare data comparison |
| `validate/references/validate-sample-data.md` | Sample data row comparison |
| `validate/references/validate-aggregation.md` | Aggregate value comparison |
| `large-db/references/platform-specific.md` | Large DB platform-specific instructions |
| `large-db/references/rds-parquet-export.md` | RDS S3 Parquet export with pg_lake |

## Common Pitfalls to Avoid

| Pitfall | Prevention |
|---------|------------|
| No rollback plan | Setup reverse replication BEFORE cutover |
| Forgot scheduled jobs | Audit ALL database consumers |
| ORM cache issues | Restart apps after DNS switch |
| Replication slot WAL bloat | Monitor slots, drop orphaned ones |
| Sequence values not synced | **Run sequence sync as FINAL step** |
| Forgot users/roles | **Ask if roles should be migrated; if yes, migrate FIRST** |
| Network rules not configured | **Configure EGRESS rules BEFORE creating subscription** |
| Schema not copied before subscription | **Run pg_dump --schema-only BEFORE creating subscription** |
| Vendor-specific pg_dump errors | **Filter Crunchy/RDS/Azure commands from pg_dump output** |
| CREATE SUBSCRIPTION in transaction | **Use heredoc or -f file, not psql -c flag** |

## Troubleshooting

For connection issues, see `references/connection-troubleshooting.md`.

### Network Connectivity Issues (Logical Replication)

**Error: "could not connect to publisher"**
→ Snowflake Postgres cannot reach the source. Check:
1. Network rules on Snowflake Postgres allow egress to source host:port
2. Source firewall/security groups allow ingress from Snowflake Postgres
3. Source `pg_hba.conf` allows replication connections

**To configure network rules for Snowflake Postgres egress:**

**⚠️ MANDATORY: Always confirm with the user before creating or modifying any network rules or network policies. Show the exact SQL that will be executed and wait for explicit approval.**

⚠️ **CRITICAL**: Snowflake Postgres egress rules MUST use:
- `TYPE = IPV4` (NOT `HOST_PORT`)
- `MODE = POSTGRES_EGRESS` (NOT `EGRESS`)

```sql
-- Step 1: Resolve source hostname to IP address
-- Run: dig +short source-host.example.com
-- Example result: 3.150.49.165

-- Step 2: Create network rule with POSTGRES_EGRESS mode and IPV4 type
CREATE OR REPLACE NETWORK RULE <database>.<schema>.migration_egress_rule
    TYPE = IPV4
    VALUE_LIST = ('3.150.49.165/32')
    MODE = POSTGRES_EGRESS
    COMMENT = 'Egress to source PostgreSQL for migration';

-- Step 3: Add rule to existing network policy attached to Postgres instance
ALTER NETWORK POLICY <your_network_policy> SET
    ALLOWED_NETWORK_RULE_LIST = (
        <existing_ingress_rules>,
        <database>.<schema>.migration_egress_rule
    );
```

**Common mistakes:**
- Using `TYPE = HOST_PORT` → Will fail, must use `TYPE = IPV4`
- Using `MODE = EGRESS` → Will fail, must use `MODE = POSTGRES_EGRESS`
- Using hostname instead of IP → Resolve with `dig +short` first

### Other Common Errors

| Error | Solution |
|-------|----------|
| "table does not have a REPLICA IDENTITY" | Add primary key or set `REPLICA IDENTITY FULL` |
| "permission denied for replication" | `ALTER ROLE user REPLICATION;` |
| "wal_level must be logical" | Set `wal_level = logical` and restart |
| Replication lag increasing | Check network bandwidth, target instance size |
| WAL directory filling up | Check for inactive replication slots |

## Output

Routes to the appropriate sub-skill and guides through complete migration workflow.
