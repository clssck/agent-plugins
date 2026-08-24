---
name: migration-guide
description: >-
  Migration and conversion of databases, SQL, stored procedures, DDL, and ETL/integration
  workloads into Snowflake using the Snowflake migrations plugin, including SnowConvert-based code
  conversion. ALWAYS invoke this skill — do NOT answer source-vendor SQL questions directly — for:
  (1) any Snowflake equivalent of non-Snowflake SQL, even simple single-statement syntax questions
  (T-SQL MERGE / sp_send_dbmail, Oracle CONNECT BY / SYSDATE / DUAL / DBMS_OUTPUT, MySQL ON
  DUPLICATE KEY UPDATE); (2) decommissioning, sunsetting, replatforming, lift-and-shift, or
  modernization of a legacy data warehouse or ETL stack, even when 'Snowflake' is not named yet;
  (3) any request to convert source code to Snowflake, even one-off. Triggers: migrate, migration,
  into snowflake, snowconvert, conversion report, unsupported objects, PL/SQL, T-SQL, SQL Server,
  MySQL, BigQuery, Redshift, Netezza, SSIS, Informatica, CDC, data validation, migration testing,
  decommission, sunset, replatform, modernize.
---

# Migration Guide

Helps users migrate database and ETL objects to Snowflake. Walks through confirmation, installs the migration plugin via `cortex plugin install`, and hands off to the full migration skill.

## Instructions

Follow the steps below **in order**. Do not skip ahead.

### Step 1 — Confirm plugin installation

Tell the user:

> To guide you through the migration I'll install a **Snowflake migration plugin** as a managed Cortex plugin to help migrate database, ETL, and reporting workloads to Snowflake. No data is sent anywhere during installation.
>
> Shall I go ahead and install it?

Wait for explicit approval. If the user declines, respect their decision and stop.

### Step 2 — Install the plugin

Once the user approves, run the installer script. It calls `cortex plugin install` to clone and register the managed plugin, then disables the bundled `migration-guide` stub in settings.

**macOS / Linux:**
```bash
python3 scripts/install_plugin.py
```

**Windows:**
```cmd
python scripts\install_plugin.py
```

- If the script fails because **git is not installed or not on PATH** (surfaced by `cortex plugin install`), tell the user they need to install git and restart their terminal / PowerShell before continuing and point them to <https://git-scm.com/downloads>. **Stop here** until they confirm git is installed, then re-run the script. Do NOT try to debug — without git the plugin cannot be cloned.

- If the script reports the plugin is **already installed**, tell the user no changes were needed; the script is idempotent and they can proceed.

- If the install **succeeds**, tell the user:
  > Plugin installed and bundled stub disabled. Please run `/plugin reload` in this Cortex session to hot-reload the plugin runtime — no restart needed. Once reloaded, say "migrate" to start the migration workflow.

Once the user says "migrate", try to load the `snowflake-migration:migration` skill to start their workflow. If that is not available, ask the user to run `/plugin reload` again.
