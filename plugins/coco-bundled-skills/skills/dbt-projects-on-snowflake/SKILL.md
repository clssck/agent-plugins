---
name: dbt-projects-on-snowflake
description: "ONLY for dbt projects deployed INTO Snowflake as native objects via the `snow dbt` CLI, OR for authoring dbt models using Snowflake-native features (e.g., semantic_view materialization via dbt_semantic_view package). NOT for normal dbt development. Invoke ONLY when the user explicitly mentions: `snow dbt` commands (deploy, execute, list), `EXECUTE DBT PROJECT` SQL, a deployed dbt project object (e.g., DB.SCHEMA.MY_PROJECT), `ALTER/DROP/DESCRIBE/SHOW DBT PROJECT` SQL, scheduling a deployed dbt project with CREATE TASK, generating documentation/catalog/lineage for a deployed project, OR authoring Snowflake-specific dbt materializations (semantic_view, dbt_semantic_view), OR adding a semantic view to an existing dbt project. Do NOT invoke for standard dbt workflows: dbt run, dbt build, dbt test, dbt seed, dbt init, dbt compile, dbt debug, dbt snapshot, dbt deps, dbt clean, dbt retry, dbt ls, profiles.yml, dbt_project.yml, model editing, source freshness, Jinja/macro development, CI/CD pipelines, or any dbt command run from a terminal. The key distinction: this skill is about dbt-as-a-Snowflake-object (snow dbt deploy), not dbt-as-a-CLI-tool (dbt run). Triggers: snow dbt, snow dbt deploy, snow dbt execute, snow dbt list, EXECUTE DBT PROJECT, deployed dbt project, ALTER DBT PROJECT, DROP DBT PROJECT, DESCRIBE DBT PROJECT, SHOW DBT PROJECTS, VERSION$, external-access-integration, dbt project object, migrate, prepare for snowflake, docs generate deployed, documentation deployed project, data catalog deployed, lineage deployed project, generate documentation for deployed, semantic_view materialization, dbt_semantic_view, semantic view in dbt project, add semantic view to dbt, dbt project semantic view, analytical access dbt project."
---

# Snowflake-Native dbt Projects

## Mandatory Rules

**Before writing AI function SQL, read `../sql-author/SKILL.md`.**

Deploy and run dbt Core projects directly **inside Snowflake** using the `snow` CLI and `EXECUTE DBT PROJECT` SQL. Also covers authoring dbt models with Snowflake-specific materializations like `semantic_view`.

**SCOPE:** This skill covers dbt projects deployed as Snowflake objects — created via `snow dbt deploy`, executed via `snow dbt execute` or `EXECUTE DBT PROJECT` SQL, and managed via `ALTER/DESCRIBE/DROP/SHOW DBT PROJECT` SQL. It also covers authoring dbt models that use Snowflake-specific materializations (e.g., `semantic_view` via the `dbt_semantic_view` package).

**DO NOT use this skill when:**
- The user is running dbt locally against Snowflake (standard `dbt run`, `dbt build`, `dbt test`, `dbt seed`)
- The user is editing dbt models, fixing SQL bugs, writing macros, or doing dbt development work
- The user has a local `profiles.yml` with password/authenticator fields (this is normal for local dbt)
- The user is configuring `dbt_project.yml`, `packages.yml`, or project structure
- The user mentions `dbt init`, `dbt debug`, `dbt deps`, `dbt clean`, `dbt compile`, `dbt snapshot`, `dbt retry`, `dbt ls`
- The user asks about CI/CD, GitHub Actions, source freshness, or dbt documentation
- There is NO mention of `snow dbt`, a deployed project, a project in a Snowflake schema, `EXECUTE DBT PROJECT`, or Snowflake-specific materializations (`semantic_view`)

If the user's request matches the above, do NOT load any sub-skills — just answer using standard dbt knowledge.

**WHY THIS SKILL EXISTS:** Snowflake's native dbt integration uses unique syntax (`snow dbt`, `EXECUTE DBT PROJECT`) that differs from standard dbt CLI. This skill provides the correct syntax for that specific workflow, plus guidance on Snowflake-specific dbt materializations like `semantic_view`.

> **Semantic views:** For creating semantic views as part of a dbt project, this skill provides the `dbt_semantic_view` package workflow (see SEMANTIC VIEW intent below). For ongoing optimization of existing semantic views (auditing, VQR mining, Cortex Analyst tuning), use the `semantic-view` skill instead.

---

If the request involves writing dbt model SQL with AI or Cortex functions, read `../sql-author/SKILL.md` before generating any SQL.

## Intent Detection

**Only match these intents when the user is explicitly working with Snowflake-native dbt (deployed projects, `snow dbt`, `EXECUTE DBT PROJECT`).** Do NOT match for standard local dbt CLI work.

| Intent | Triggers | Action |
|--------|----------|--------|
| **DEPLOY** | "snow dbt deploy", "deploy dbt project to snowflake", "create dbt project in snowflake", "upload dbt", "external access integration" | Load `deploy/SKILL.md` |
| **EXECUTE** | "snow dbt execute", "EXECUTE DBT PROJECT", "run deployed project", "execute deployed project", "snow dbt show", "run the deployed", "run in deployed", "execute in deployed", "docs generate", "generate documentation", "documentation", "data catalog", "catalog", "lineage" | **⚠️ You MUST read `execute/SKILL.md`** - it has CRITICAL syntax for docs generate |
| **MANAGE** | "snow dbt list", "list dbt projects", "show dbt projects", "describe dbt project", "drop dbt project", "rename dbt project", "SHOW DBT PROJECTS", "ALTER DBT PROJECT", "add version", "VERSION$", "set comment", "set default target", "download project files", "get model SQL from deployed", "inspect deployed project", "access project files", "list files in project" | Load `manage/SKILL.md` |
| **SCHEDULE** | "schedule dbt project", "CREATE TASK for dbt", "EXECUTE DBT PROJECT in task", "automate dbt runs", "Snowflake task for dbt" | Load `schedule/SKILL.md` |
| **MONITOR** | "dbt execution logs", "dbt artifacts", "dbt archive", "dbt execution history", "download artifacts" | Load `monitoring/SKILL.md` |
| **MIGRATE** | "migrate", "env_var", "environment variable", "env.yml", "env yml", "migration", "prepare for snowflake" | ⚠️ **You MUST `Read` `migrate/SKILL.md` before taking any action.** Migration has complex, non-obvious requirements that will cause failures if skipped. Do NOT attempt migration from general knowledge. |
| **SEMANTIC VIEW** | "semantic view", "create semantic view", "dbt_semantic_view", "cortex analyst semantic", "semantic_view materialization" | Load `references/semantic-views.md` |

## ⚠️ Critical: Incremental Model Fixes Require `--full-refresh`

After fixing an incremental model's logic (e.g., restoring a missing `is_incremental()` guard, changing the unique key, or altering the incremental strategy), you **MUST** execute with `--full-refresh`. Without it, the existing table still contains data built by the broken logic — a normal incremental run only processes new rows and won't fix the bad data.

## Quick Reference

```bash
# Deploy (add --external-access-integration if project needs external network access)
snow dbt deploy my_project --source /path/to/dbt --database my_db --schema my_schema --external-access-integration MY_EAI

# Deploy with default environment
snow dbt deploy my_project --source /path/to/dbt --database my_db --schema my_schema --default-env prod

# PREVIEW model output (does NOT create objects)
snow dbt execute -c default --database my_db --schema my_schema my_project show --select model_name

# Execute/RUN models (creates tables/views)
snow dbt execute -c default --database my_db --schema my_schema my_project run

# Execute with a specific environment
snow dbt execute --env prod my_project run

# Execute with variable overrides (all keys in one JSON object)
snow dbt execute --env-vars '{"DBT_KEY": "value", "DBT_KEY_2": "value2"}' my_project run

# Full refresh (REQUIRED after fixing incremental model logic)
snow dbt execute -c default --database my_db --schema my_schema my_project run --full-refresh

# Execute specific models with dependencies
# Upstream deps of target:
snow dbt execute -c default --database my_db --schema my_schema my_project run --select +target_model
# Downstream deps of target:
snow dbt execute -c default --database my_db --schema my_schema my_project run --select target_model+
# Both sides:
snow dbt execute -c default --database my_db --schema my_schema my_project run --select +target_model+

# List (omit --database to use connection default)
snow dbt list --in schema my_schema --database my_db

# Schedule (via SQL - always use EXECUTE DBT PROJECT)
CREATE TASK my_db.my_schema.run_dbt_daily
  WAREHOUSE = my_wh
  SCHEDULE = 'USING CRON 0 6 * * * UTC'
AS
EXECUTE DBT PROJECT my_db.my_schema.my_project
  ARGS = 'run'
  ENVIRONMENT = 'prod';
```

## Workflow

```
User Request
     ↓
Intent Detection
     ↓
├─→ DEPLOY   → Load deploy/SKILL.md
├─→ EXECUTE  → Load execute/SKILL.md
├─→ MANAGE   → Load manage/SKILL.md
├─→ SCHEDULE → Load schedule/SKILL.md
├─→ MONITOR  → Load monitoring/SKILL.md
├─→ MIGRATE  → ⚠️ MUST Read migrate/SKILL.md first (complex requirements) → Then follow its steps exactly
└─→ SEMANTIC VIEW → Load references/semantic-views.md
```

## Stopping Points

- ⚠️ Before any destructive operation (DROP, RENAME)

## Output

- Deployed dbt projects in Snowflake
- Materialized tables/views/semantic views from dbt models
- Test results from dbt test
- Scheduled TASK objects for automated execution
- Execution logs and artifacts for debugging
