---
name: native-app-configure-telemetry-event-and-health-update
description: "Configure telemetry levels, event definitions, health status reporting, and object-level telemetry overrides for a Snowflake Native App. Covers manifest telemetry settings, SYSTEM$REPORT_HEALTH_STATUS, and per-object logging overrides. Triggers: health status, health monitoring, logging, tracing, telemetry, event definitions, log_level, trace_level, metric_level, SYSTEM$REPORT_HEALTH_STATUS, configure telemetry, health update, health check."
parent_skill: native-app-provider
---

# Native App Telemetry & Health Configuration

> **⚠️ MANDATORY**: If your system prompt mentions Snowsight, load [`../references/native-apps-snowsight.md`](../references/native-apps-snowsight.md) before doing anything else.

## When to Load

From the root `native-app` skill when user wants to configure logging/tracing/metrics, add health reporting (`SYSTEM$REPORT_HEALTH_STATUS`), add event definitions, or set object-level telemetry overrides.

For **querying** APPLICATION_STATE, lifecycle events, or monitoring app health — load `monitor-app-telemetry-event-and-status/SKILL.md`.

## Guard Rails

- **Do NOT** create event tables or configure event accounts — use `configure-event-sharing/SKILL.md`.
- **Do NOT** configure consumer-side event sharing — consumers manage that themselves.
- **Do NOT** modify setup scripts without presenting changes to the user first.

## Workflow

```
Start → Step 1: Detect intent
  ├─→ Path A: Configure telemetry levels in manifest
  ├─→ Path B: Add event definitions to manifest
  ├─→ Path C: Add health status reporting
  └─→ Path D: Set object-level telemetry overrides
```

Multiple paths may apply. Process each in order (A → D).

---

### Step 1: Detect Intent

Map the user's request to paths: "logging/tracing/metrics" → **A**; "event definitions/share telemetry" → **B**; "health status/monitor health" → **C**; "override log level on procedure" / "detailed logging on specific procedure" → **D**; "full observability" → **A+B+C+D**. If unclear, recommend **A+B+C** as standard provider setup.

For "query lifecycle events" / "upgrade tracking" / "audit trail" / "APPLICATION_STATE" → **load** `monitor-app-telemetry-event-and-status/SKILL.md` instead.

Present a numbered task list of selected paths, then **STOP** and wait for user confirmation before proceeding.

---

### Path A: Configure Telemetry Levels in Manifest

**Load** `references/event-definitions-reference.md` for the full telemetry levels table, valid values, and recommendations. The key fields are `log_level`, `log_event_level` (BCR 2026_02), `trace_level`, and `metric_level` — all set under `configuration:` in `manifest.yml`.

Present manifest changes for review. **STOP** and wait for user confirmation before modifying files.

---

### Path B: Add Event Definitions to Manifest

Event definitions configure what telemetry consumers share back to the provider. This is covered in detail by `configure-event-sharing/SKILL.md` Path A — **load that skill** for event definitions setup. If the user only needs event definitions (not the full event sharing workflow), use the reference at `references/event-definitions-reference.md` for the supported types, sharing modes, and recommendations, then add `telemetry_event_definitions` under `configuration:` in `manifest.yml`.

Present manifest changes for review. **STOP** and wait for user confirmation before modifying files.

---

### Path C: Add Health Status Reporting

`SYSTEM$REPORT_HEALTH_STATUS` lets the app report health (`OK`, `FAILED`, `PAUSED`) from consumer instances back to the provider. The provider monitors via `SNOWFLAKE.DATA_SHARING_USAGE.APPLICATION_STATE`.

#### C1: Health-check procedure

Ask the user what health criteria to check (table exists, SP runs, reference registered, endpoint responsive) — or infer from context if the user described their app. Generate a procedure that runs those checks and calls `SYSTEM$REPORT_HEALTH_STATUS('OK')` on success and `SYSTEM$REPORT_HEALTH_STATUS('FAILED')` on failure. Add the procedure to the **setup script**.

**Key constraints:**
- Accepts one argument: `'OK'`, `'FAILED'`, or `'PAUSED'`
- Returns `TRUE` if accepted, `FALSE` if rate-limited (one report per 55 minutes per instance)
- Only retains the most recent status per consumer instance

#### C2: Periodic task

Add a scheduled task to the **setup script** that calls the health-check procedure periodically. Tasks **cannot** be in versioned schemas — create a non-versioned schema and put the task there. **Always include `ALTER TASK ... RESUME`** after creating the task — tasks are created in suspended state.

**Serverless tasks** (recommended — no warehouse dependency): add both `EXECUTE TASK` and `EXECUTE MANAGED TASK` to the manifest privileges block. **User-managed tasks**: add `EXECUTE TASK` and specify a `WAREHOUSE`. See `request-account-privilege/SKILL.md` for the manifest privileges format.

```sql
CREATE SCHEMA IF NOT EXISTS internal;
GRANT USAGE ON SCHEMA internal TO APPLICATION ROLE app_user;

CREATE OR REPLACE TASK internal.health_report_task
  SCHEDULE = '60 MINUTE'
  USER_TASK_MANAGED_INITIAL_WAREHOUSE_SIZE = 'XSMALL'
  ALLOW_OVERLAPPING_EXECUTION = FALSE
  AS CALL <schema>.health_check_and_report();

ALTER TASK internal.health_report_task RESUME;
```

#### C3: Provider-side monitoring

Query `SNOWFLAKE.DATA_SHARING_USAGE.APPLICATION_STATE` for current health/upgrade status per consumer instance. No setup needed beyond `SYSTEM$REPORT_HEALTH_STATUS`. For details on APPLICATION_STATE columns and lifecycle event queries, **load** `monitor-app-telemetry-event-and-status/SKILL.md`.

Present setup script changes for review. **STOP** and wait for user confirmation before modifying files.

---

### Path D: Object-Level Telemetry Overrides

Fine-tune `LOG_LEVEL`, `LOG_EVENT_LEVEL` (BCR 2026_02), `TRACE_LEVEL`, and `METRIC_LEVEL` for specific objects independent of the app-level manifest settings. Add these overrides to the **setup script** so they apply on install/upgrade.

Use `ALTER PROCEDURE ... SET LOG_LEVEL = 'DEBUG'` for individual procedures/UDFs. For versioned schemas, use `CREATE OR ALTER VERSIONED SCHEMA ... SET LOG_LEVEL = '...'` in the setup script. Example — elevate logging on a diagnostics procedure:

```sql
ALTER PROCEDURE core.run_diagnostics() SET LOG_LEVEL = 'DEBUG';
```

**Precedence** (highest to lowest):
1. **Stored procedure / UDF** override
2. **Schema / versioned schema** override
3. **App-level manifest** `configuration` block

---

## Completion

Verify: manifest installs/upgrades successfully after changes. If `MANDATORY` event definitions are present, ensure `CREATE APPLICATION` uses `AUTHORIZE_TELEMETRY_EVENT_SHARING = TRUE`. Confirm `telemetry_event_definitions` is nested under `configuration:` (not top-level). Present a summary of what was configured and which files changed.

**Next steps:** Deploy and test — load `deploy-test/SKILL.md`. Set up event accounts — load `configure-event-sharing/SKILL.md`. Monitor app health — load `monitor-app-telemetry-event-and-status/SKILL.md`.
