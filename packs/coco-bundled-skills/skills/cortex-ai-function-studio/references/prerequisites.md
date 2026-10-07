<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Prerequisites

This document covers all prerequisites needed for the Cortex AI Function Studio.

## When to Load

Load from main SKILL.md Step 0 (always). Also load when: "setup", "install", "prerequisites", "requirements", "getting started".

## Environment Detection

Detect whether the session is running inside **Snowsight** (the Snowflake web UI) or a **CLI** environment. Store the result as state variable `environment` (`snowsight` | `cli`) — subsequent workflows branch on this value. You as an agent should have full awareness of where you are.

**If `environment == snowsight`:** ⚠️ **STOP — mandatory read.** Load the full contents of `references/snowsight/core.md` *now*, before any other tool call. Internalize the TL;DR rules and Notebook Harness §1–§9 (skeleton, cell snippets, view-mode, hallucinations, error recovery) — do **not** call `write` or `notebook_action` without reading them. Skipping or skimming this read is the largest cause of failed Snowsight sessions. Then complete the Snowsight-specific setup it describes before returning here.

**If `environment == cli`:** Skip Snowsight setup and proceed directly.

## Required

### Silent Prerequisite Checks

**IMPORTANT — Quiet on success**: Run all prerequisite checks in a **single parallel batch**. Do NOT narrate what you are checking beforehand — just run the checks. If everything passes, do NOT display individual results. Only mention prerequisites if something **fails**. The user should see zero prerequisite output on the happy path.

Run these following checks **in parallel** (single tool-call batch):

1. **Session role** — run this first, before any privilege checks:
```sql
SELECT CURRENT_ROLE() AS role;
```
Store the result as `{role}`. This is the **session role** that all SQL statements execute under — it may differ from the workspace role shown in the Snowsight UI. Always use this value when checking privileges and reporting missing grants.

2. **Snowflake connection + AI_COMPLETE + session defaults** (single SQL):
```sql
SELECT AI_COMPLETE('llama3.1-8b','ping') AS ai_test, CURRENT_DATABASE() AS db, CURRENT_SCHEMA() AS sch;
```

3. **uv installed** (CLI only — skip if `environment == snowsight`):
```bash
uv --version
```

If `environment == snowsight`, the `uv` check is not needed — stored procedures are built into Snowflake and no local Python runtime is required. Only run the Snowflake connection check.

**If any check fails**, stop and report only the failure:
- Connection/AI_COMPLETE fails → tell user to verify their Snowflake connection
- `uv` not found (CLI only) → install it:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
  Then restart terminal and retry. **⚠️ STOP**: Do NOT proceed until `uv --version` succeeds.

**If all checks pass**, proceed silently to the target database/schema step.

### Target Database and Schema

All workflows require a target database and schema where AI function objects will be created. Collect these now so that privilege checks and all subsequent steps use the same location.

**If `database` and `schema` are already known** (from the user's initial message or conversation context), accept silently.

**If not known**, use the session defaults from the prerequisite check above (the `db` and `sch` columns). If they are set, ask offering them as an option:
```
Which database and schema should the AI function be created in?

1. Use current session: {current_database}.{current_schema}
2. Specify a different database and schema
```

If the session has no database/schema set (NULL), omit option 1 and ask directly:
```
Which database and schema should the AI function be created in?

Database: [e.g., MY_DB]
Schema: [e.g., MY_SCHEMA]
```

Store as `{database}` and `{schema}` — these are reused by create, evaluate, and optimize workflows.

## Snowflake Privileges

The skill creates several Snowflake objects. Run the privilege checks below **silently** — same pattern as prerequisite checks. Only surface results to the user if something is **missing**.

### Privilege Check

Run these two queries **in parallel** (single tool-call batch):

```sql
SHOW GRANTS ON DATABASE {database};
```

```sql
SHOW GRANTS ON SCHEMA {database}.{schema};
```

Use the `{role}` value from the session role check (Step 1 above) — **not** the workspace role shown in the Snowsight UI. Check whether this role (or a role it inherits) has the following grants. If the role has **ALL** or **OWNERSHIP** on the database and schema, all checks pass — proceed silently.

**Required privileges:**

| Privilege | Check In | Needed For |
|-----------|----------|------------|
| USAGE | `GRANTS ON DATABASE` | Accessing the database |
| USAGE | `GRANTS ON SCHEMA` | Accessing the schema |
| CREATE FUNCTION | `GRANTS ON SCHEMA` | Creating AI function UDFs |
| CREATE TAG | `GRANTS ON SCHEMA` | Tagging UDFs for tracking |

**Optional privileges (async execution):**

These are only needed if the user explicitly requests async execution. Do not check these by default — only verify if the user asks for async.

| Privilege | Needed For |
|-----------|------------|
| CREATE TASK | Creating background tasks |
| EXECUTE TASK (account-level) | Running background tasks |
| USAGE on warehouse (direct grant) | Tasks require explicit warehouse USAGE |

### Reporting Results

**If all required privileges pass**: Proceed silently. Do NOT display a summary message — just move on to the next workflow step.

**If any required privilege is missing:**

**⚠️ STOP**: Display each missing privilege with its remediation GRANT command. Do not proceed.

```
Missing privileges for role {role} on {database}.{schema}:

✗ {PRIVILEGE} on {OBJECT}
  Needed for: {description}
  Fix: GRANT {PRIVILEGE} ON {OBJECT_TYPE} {object_name} TO ROLE {role};

Ask your account administrator to run the GRANT commands above,
or choose a different database/schema where your role has sufficient privileges.
```
