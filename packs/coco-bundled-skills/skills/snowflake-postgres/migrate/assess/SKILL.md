---
name: assess
description: "Assess PostgreSQL database for migration readiness to Snowflake Postgres. Use for: migration assessment, readiness check, check blockers, complexity score, recommend method, can I migrate, pre-migration audit. Detects unsupported extensions, missing PKs, wal_level issues, complex factors (PostGIS, partitions, custom types) and produces an HTML report."
parent_skill: migrate
---

# Migration Assessment

> **Windows users:** see [references/windows.md](../../references/windows.md) — install prereqs, credential file paths (`%APPDATA%\postgresql\` instead of `~/`), and command-flow notes differ on native Windows. WSL behaves as Linux.

## When to Load

Main skill routes here for: "migration readiness", "can I migrate", "check blockers", "assessment"

> **Credentials:** Use `--source-service` / `--target-service` flags; passwords resolve from `~/.pgpass`, never CLI or chat. If the user provides raw source connection fields in chat instead of an existing service profile, direct them to `/secrets` for the password, register the source profile so the password lands in `~/.pgpass`, then continue with `--source-service`. See `../SKILL.md` "Credentials" callout for the canonical pattern. (Env-var examples below are kept for operators running from a trusted shell only.)

## Prerequisites

- Source PostgreSQL connection details available
- User has read access to `pg_catalog` on source
- Python 3 with psycopg2 or pg8000 installed

## Important Notes

- **All tooling is Python-based** (`scripts/` directory). No psql dependency.
- **ALWAYS generate the HTML assessment report** after running the assessment. This is mandatory, not optional.

## Workflow

### Step 1: Gather Source Information

**Load** `../references/connection-setup.md` and use its Step 5 menu **exactly** for the assessment intake:

- `Saved connection`
- `Enter source details now`
- `Legacy environment file`

Assessment is **source-only** at this stage. Do not replace the menu with a prose checklist.

Make the existing-connection path explicit:
- If the user already has a saved source connection, list saved connections first and present a picker of likely matches.
- Only ask for host / port / dbname / user / sslmode when the user chose `Enter source details now`.
- Keep the follow-up crisp; do not mix source connection intake with target planning.

**Do NOT ask about target instance existence, target service profiles, or billable target creation yet.**
- `run_assessment.py` needs only the source connection.
- Target creation / approval belongs **after** the assessment report, when the user reviews the recommended method and sizing.

**STOP**: Wait for source connection details. Never ask for passwords in chat.

If the user provides host / port / dbname / user values instead of a saved profile:

1. Ask them to add the password via `/secrets`
2. Register the source profile with `scripts/shared/pg_common.py --add-source-service ...`
3. Run the assessment with `--source-service <NAME>`

Preferred crisp follow-up patterns:

- If `Saved connection`:
  1. Run:
     `uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py --list`
  2. Identify likely source-connection matches from the output.
  3. Present those likely matches via `ask_user_question`.
  4. Include fallback choices: `A different saved connection`, `Enter source details now`, `I need clarification`.
  5. Only if needed, ask for the exact saved connection name in normal chat.

- If `Enter source details now`:
  `Please send the non-secret source fields: host, port, dbname, user, sslmode, and the short service name you want me to save it under. After that, add the password via /secrets and I'll write it into ~/.pgpass.`

### Step 2: Run Assessment

Use the Python assessment script which handles PG version differences (including PG17 column name changes) and always generates the HTML report:

```bash
# Preferred, chat-safe workflow:
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/run_assessment.py \
    --source-service prod_source \
    --html migration_assessment_report.html \
    --json assessment_data.json

# Trusted-shell fallback:
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/run_assessment.py \
    --host $SOURCE_PGHOST \
    --port ${SOURCE_PGPORT:-5432} \
    --dbname $SOURCE_PGDATABASE \
    --user $SOURCE_PGUSER \
    --html migration_assessment_report.html \
    --json assessment_data.json
```

This single command:
- Connects directly to PostgreSQL (psycopg2 or pg8000, no psql needed)
- Detects PG version and adapts queries for compatibility (e.g., PG17 catalog changes)
- Runs all 19+ assessment checks in one pass
- Calculates migration complexity score
- Generates interactive HTML report
- Saves JSON data for downstream tools
- Prints text summary to console

**If Python driver is not installed**, `pg_common.check_driver()` fires at script entry and prints actionable install guidance (via `uv sync` against `<SKILL_DIR>/pyproject.toml`, which pins `psycopg2-binary` with a `pg8000` fallback).

#### Additional Python-based tools (optional):

```bash
# Preferred, chat-safe workflow:
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/validate_schema_compatibility.py \
    --source-service prod_source \
    --format html --output validation_report

uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/generate_hybrid_plan.py \
    --source-service prod_source \
    --target-service sf_target \
    --output migration_plan

# Trusted-shell fallback:
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/validate_schema_compatibility.py \
    --host $SOURCE_PGHOST --dbname $SOURCE_PGDATABASE --user $SOURCE_PGUSER \
    --format html --output validation_report

uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/generate_hybrid_plan.py \
    --host $SOURCE_PGHOST --dbname $SOURCE_PGDATABASE --user $SOURCE_PGUSER \
    --target-host $TARGET_PGHOST \
    --output migration_plan
```

### Step 3: Open HTML Assessment Report (WHEN POSSIBLE)

**MANDATORY: ALWAYS generate the HTML report. Open it automatically when the session is interactive; otherwise provide the report path and summary. Do NOT block the workflow on browser-launch failures.**

`run_assessment.py` already opens the generated report in the default browser
on completion via `webbrowser.open()` — no extra command is needed. (Pass
`--no-open` to suppress, or `--open <file>` to reopen an existing report
without re-running.)

If the session is interactive and the auto-open didn't fire, re-run with:

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/run_assessment.py \
    --open migration_assessment_report.html
```

**Tell the user:**
```
I've generated the interactive HTML assessment report. If this session supports browser launch, it should already be open; otherwise the file is at `migration_assessment_report.html`. It includes:
- Migration readiness status (GO / CONDITIONAL / ACTION REQUIRED)
- Complexity score with explanation and breakdown
- Recommended migration method with rationale
- Findings & Recommendations with severity levels
- Database overview (size, tables, rows, indexes)
- Critical blockers (tables without PKs, WAL level, unsupported extensions, unsupported languages)
- Extension compatibility matrix
- Detailed table and index inventory
- Roles requiring migration

**Additional warnings to surface (if found):**
- Objects owned by `postgres` role (not accessible in Snowflake Postgres — must reassign ownership)
- MD5 password encryption on source (Snowflake Postgres uses SCRAM-SHA-256 — passwords must be reset, see `../references/lessons-learned.md`)
- Roles with SUPERUSER privilege (SUPERUSER is not available in Snowflake Postgres — these privileges will not be migrated; `snowflake_admin` is the target admin role, but it is not a 1:1 replacement for every source superuser, so map duties to explicit grants, see `../references/lessons-learned.md`)
- Table inheritance (treat as a critical follow-up item: PostgreSQL inheritance is different from partitioning and does not replicate cleanly. Investigate the inheritance trees and application behavior before choosing a migration method; only then decide whether redesign or pg_dump/manual handling is required)

Please review the report and let me know when you're ready to proceed.
```

**STOP**: Wait for user to review the HTML report before proceeding to approval.

### Step 3.5: Generate Instance Sizing Recommendations

After assessment completes, **automatically generate Snowflake Postgres instance recommendations** based on the source database characteristics. This helps users (especially new customers) make informed decisions about instance sizing.

**The assessment script outputs `instance_recommendations` in the JSON data:**

```json
{
  "instance_recommendations": {
    "compute_pool": {
      "recommended": "<compute_family>",
      "alternatives": [...],
      "rationale": "..."
    },
    "storage": {
      "recommended_gb": 0,
      "minimum_gb": 0,
      "calculation": "..."
    },
    "high_availability": {
      "recommended": false,
      "rationale": "...",
      "timing": "after validation, before cutover if target is production"
    }
  }
}
```

**Use the references with distinct roles:**
- `../references/instance-sizing.md` explains the recommendation policy and HA timing guidance.
- `../../references/instance-options.md` is the **single source of truth** for supported compute families, storage bounds, HA restrictions, and CREATE/ALTER syntax.

**Do not restate the full option matrix here.** The assessment should only present:
- the recommended instance settings
- the rationale and trade-offs
- any operational warnings (existing replicas, logical slots, active app traffic, etc.)

**HA guidance:**
- If the target will become the production system, recommend enabling HA **after validation and before cutover**.
- Do not infer production status or existing HA with certainty from source SQL alone; ask when that intent is unclear.

### Step 4: Present Summary and Approval Options

**Present** findings to user in a structured summary:

```
## Migration Assessment Report

### Database Overview
- Database: [name]
- Size: [X GB]
- Tables: [N]
- Indexes: [N]
- Source Platform: [AWS RDS / Azure / Cloud SQL / Self-managed / etc.]
- Complexity Score: [N] ([SIMPLE / MODERATE / COMPLEX / VERY COMPLEX])
- Estimated migration time: [based on size and method]

### Migration Readiness: [GO / CONDITIONAL / NO-GO]

### Blockers Found
| Issue | Severity | Count | Action Required |
|-------|----------|-------|-----------------|
| Tables without PKs | CRITICAL | [N] | Add PKs or use COPY |
| Unsupported extensions | CRITICAL | [N] | Remove dependencies |
| Unsupported languages | CRITICAL | [N] | Rewrite in plpgsql |
| wal_level not logical | CRITICAL | - | Set wal_level=logical, restart |
| Large objects | WARNING | [N] | Export separately |
| Table inheritance | CRITICAL | [N] | Investigate inheritance trees first; then decide on redesign or pg_dump/manual handling |

### Complex Migration Factors
| Factor | Detected | Notes |
|--------|----------|-------|
| PostGIS spatial data | Yes/No | [N] geometry columns, [N] custom SRIDs |
| Partitioned tables | Yes/No | [N] partitioned tables |
| Custom types | Yes/No | [N] enums, [N] composites, [N] domains |
| Non-plpgsql functions | Yes/No | Languages: [list] |
| pg_cron jobs | Yes/No | [N] scheduled jobs to recreate |

### Objects Requiring Manual Handling
| Object Type | Count | Notes |
|-------------|-------|-------|
| Sequences | [N] | Sync after cutover |
| Materialized views | [N] | Recreate and refresh |
| Foreign tables | [N] | Reconfigure FDW |

### Extension Compatibility
| Extension | Supported | Notes |
|-----------|-----------|-------|
| [ext1] | Y / N | [if unsupported, note alternative] |

### Recommended Migration Method
[Based on findings: Logical Replication / pg_dump / COPY]
Reason: [brief justification]

**If the assessment only shows potential non-replicable objects** (for example unlogged tables, table inheritance, or tables without PKs that might still be fixable), do **not** treat "hybrid" as final yet. If table inheritance is involved, investigate the inheritance trees and application behavior first. After that, use `generate_hybrid_plan.py` to classify actual objects and confirm whether a hybrid plan is truly needed.

### Recommended Snowflake Postgres Instance
| Setting | Recommended | Rationale |
|---------|-------------|-----------|
| Compute Pool | [valid family, e.g. STANDARD_XL] | [Based on size/complexity] |
| Storage | [X GB] | [Source size × 1.5 + buffer] |
| High Availability | [Single-instance initially / Enable after validation if production] | [Based on user intent and criticality] |

**Alternative Options:**
| Option | Compute Pool | Pros | Cons |
|--------|--------------|------|------|
| Cost-optimized | [smaller] | Lower cost | Less headroom |
| Performance-optimized | [larger] | More headroom, faster queries | Higher cost |

### Additional Resources
- **Complex migrations detected**: See `../references/complex-migrations.md` for detailed guidance
- **Instance recommendation policy**: See `../references/instance-sizing.md`
- **Valid instance options and limits**: See `../../references/instance-options.md`
```

**MANDATORY APPROVAL CHECKPOINT**

Present the assessment summary and **WAIT for explicit user approval** before proceeding.

**Ask user:**
```
I've completed the migration assessment. Please review the findings above.

Do you approve this assessment and want to proceed?

Options:
A) Approved - Proceed with logical replication (near-zero downtime)
B) Approved - Proceed with pg_dump/restore (requires downtime window)
C) Investigate hybrid fit (classify actual non-replicable objects before choosing hybrid)
D) Approved - Proceed with postgres_fdw (target queries source via SQL — see `../references/complex-migration-strategies.md`)
E) Approved - Use replica-assisted sync for very large databases (TB+, S3 export) → load `../large-db/SKILL.md`
F) Hold - I need to address blockers first
G) Hold - I have questions about the findings
```

> **Surface option E (LARGE-DB) automatically** when assessment reports
> `total_size_bytes >= 2 TB`, source is RDS/Aurora and S3 export is
> available, OR the user mentions any of: "TB", "terabyte", "large database",
> "S3 export". Otherwise the option is still listed but the chosen branch
> will be hybrid/pg_dump as appropriate.

**When to recommend Hybrid (option C):**
- Assessment found non-replicable objects (unlogged tables, table inheritance, tables without PKs that cannot be modified) **alongside** tables that qualify for logical replication
- The `generate_hybrid_plan.py` script classified objects into both methods
- User wants near-zero downtime for the bulk of the data but has some objects that require pg_dump

**Do not recommend Hybrid from high-level counts alone.**
- Unlogged tables are a strong signal, but still require object-level classification.
- Table inheritance is a stronger caution flag: inspect the inheritance trees and any parent/child query or insert-routing behavior before calling hybrid the answer. The planner can bucket objects, but it does not decide redesign strategy for you.
- Tables without PKs are especially ambiguous: the user may choose to add PKs / row identity instead, which can remove the need for hybrid.
- Before calling hybrid the chosen strategy, use `generate_hybrid_plan.py` and confirm there are still both replicable and non-replicable branches after remediation decisions.

**User-facing phrasing rule:** when describing option C or the next step, phrase it as work you can do next for the user ("I can investigate the inheritance trees / classify the affected objects next"), not as a command they must go run themselves.

**NEVER proceed to migration setup without explicit approval** (e.g., "approved", "proceed", "yes", "go ahead", "A", "B", "C", "D", "E").

If user selects G (questions), answer their questions and re-present the approval options.

### Step 5: Route to Migration Method

**If user selects A (Logical Replication):**
- Verify all blockers resolved
- Load `../replicate/SKILL.md`

**If user selects B (pg_dump/restore):**
- Load `../dump-restore/SKILL.md`

**If user selects C (Investigate hybrid fit):**
- If inherited tables are present, load `../references/complex-schema-objects.md` (table inheritance section) and review the inheritance trees / application behavior first
- Then run `generate_hybrid_plan.py` to classify actual objects and produce the phased plan
- Tell the user you are doing this investigation for them; do not tell them to go run the script themselves
- If the generated plan is truly hybrid, re-present the approval choice as:
  `Approved - Proceed with hybrid (logical replication + pg_dump for non-replicable objects)`
- Only after the plan is confirmed hybrid, ask about dump timing for non-replicable tables and continue with the hybrid workflow below
- If the generated plan collapses to replication-only or dump-only after classification/remediation choices, re-present the corrected method options instead of forcing hybrid
- **If the confirmed plan is hybrid, ask user about dump timing for non-replicable tables:**
  ```
  question: "When should non-replicable tables be dumped via pg_dump?"
  header: "Dump timing"
  options:
    - label: "Now (during migration)"
      description: "Dump non-replicable tables immediately after replication starts. Requires brief write pause on those tables."
    - label: "At cutover"
      description: "Defer pg_dump of non-replicable tables to the cutover phase, alongside sequence sync. Minimizes disruption during migration but increases cutover window."
  ```
- Pass `--dump-timing now` or `--dump-timing cutover` to `generate_hybrid_plan.py`
- Execute the hybrid plan phases: logical replication first, then pg_dump tables per chosen timing
- For **"Now"**: pg_dump phase runs after replication initial sync completes, then proceed to monitor/validate/cutover
- For **"At cutover"**: pg_dump tables are deferred to the cutover phase — after writes stop, dump non-replicable tables, sync sequences, then validate
- Load `../replicate/SKILL.md` for the logical replication portion
- Load `../dump-restore/SKILL.md` for the pg_dump portion
- Load `../cutover/SKILL.md` when ready for cutover

**If user selects D (postgres_fdw):**
- Load `../references/complex-migration-strategies.md` and follow the postgres_fdw section
- This method has no dedicated sub-skill; the reference doc covers the full
  workflow (CREATE SERVER, USER MAPPING, IMPORT FOREIGN SCHEMA, INSERT…SELECT
  with batching, validation)
- Can be used standalone OR within a hybrid migration in place of pg_dump

**If user selects E (LARGE-DB / replica-assisted):**
- Load `../large-db/SKILL.md`
- This is the only path that handles RDS/Aurora S3 Parquet exports + pg_lake;
  for very large databases (≥2 TB) it is significantly faster than logical
  replication's initial sync

**If user selects F (Address blockers):**
- Provide specific remediation steps for each blocker

## Blocker Remediation

### Tables Without Primary Keys

```sql
-- Option 1: Add a primary key (recommended)
ALTER TABLE schema.table ADD PRIMARY KEY (column);

-- Option 2: Add generated identity column
ALTER TABLE schema.table ADD COLUMN id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY;

-- Option 3: Use REPLICA IDENTITY FULL (slower, last resort)
ALTER TABLE schema.table REPLICA IDENTITY FULL;
```

### WAL Level Not Logical

```sql
-- Requires superuser on source
ALTER SYSTEM SET wal_level = 'logical';
-- Then restart PostgreSQL
```

### Unsupported Extensions

If unsupported extensions are detected:
1. Identify which tables/functions depend on the extension
2. Refactor to remove the dependency or find a supported alternative
3. Test thoroughly before migration

Common alternatives:
- `timescaledb` -> Use native partitioning with pg_partman
- `pg_repack` -> Already supported in Snowflake Postgres
- Custom extensions -> Rewrite functionality in plpgsql

### Unsupported Languages (plpython3u, plperl, etc.)

Functions written in unsupported languages must be rewritten:
1. List all affected functions: Check the HTML report "Functions by Language" section
2. Analyze each function's logic
3. Rewrite in plpgsql or SQL
4. Alternatively, move the logic to the application layer

### Replication Permission

```sql
-- Grant replication privilege to migration user
ALTER ROLE migration_user REPLICATION;
```

## Output

Assessment report with:
- Migration feasibility (GO/NO-GO)
- Recommended method
- List of blockers with remediation steps
- Estimated timeline
- HTML report (always generated)
- JSON data file (for downstream tools)

## Stopping Points

- After gathering connection details
- **MANDATORY APPROVAL** after presenting assessment report - user must explicitly approve before any migration action
- Before proceeding to migration method
