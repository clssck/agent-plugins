---
name: native-app-monitor-app-telemetry-event-and-status
description: "Query and monitor Snowflake Native App health status, lifecycle events, and telemetry from the provider side. Covers APPLICATION_STATE view, lifecycle event queries, and health/upgrade tracking. Triggers: APPLICATION_STATE, monitor app, query health, check app status, lifecycle events, upgrade tracking, audit trail, consumer health, app monitoring, health status query."
parent_skill: native-app-provider
---

# Native App Telemetry & Status Monitoring

## When to Load

From the root `native-app` skill when user wants to query APPLICATION_STATE, monitor consumer health status, track lifecycle events, or audit app upgrades from the provider side.

For **configuring** telemetry levels, event definitions, health reporting, or object-level overrides — load `configure-telemetry-event-and-health-update/SKILL.md`.

## Guard Rails

- These are **read-only provider-side queries** — they do not modify the app or consumer accounts.
- APPLICATION_STATE is in `SNOWFLAKE.DATA_SHARING_USAGE` (NOT `ACCOUNT_USAGE`).
- Lifecycle events require `log_event_level` (BCR 2026_02) or `log_level` to be set to `INFO` or more verbose in the manifest — if the level is `OFF`, lifecycle events are NOT emitted. Recommend the user load `configure-telemetry-event-and-health-update/SKILL.md` Path A if not configured.

## Workflow

```
Start → Step 1: Detect intent
  ├─→ Path A: Query APPLICATION_STATE for current health/upgrade status
  └─→ Path B: Query lifecycle events from event table
```

Both paths may apply. Process in order (A → B).

---

### Step 1: Detect Intent

Map the user's request to paths: "health status" / "consumer health" / "app status" / "upgrade state" → **A**; "lifecycle events" / "audit trail" / "health history" / "upgrade history" → **B**; "monitor everything" / "full monitoring" → **A+B**.

**Load** `references/lifecycle-events-reference.md` for full column details, event type filters, and SQL examples.

---

### Path A: Query APPLICATION_STATE

`SNOWFLAKE.DATA_SHARING_USAGE.APPLICATION_STATE` provides current health and upgrade status per consumer instance. No setup needed beyond calling `SYSTEM$REPORT_HEALTH_STATUS` from the app (see `configure-telemetry-event-and-health-update/SKILL.md` Path C).

**Key columns:** `PACKAGE_NAME`, `LAST_HEALTH_STATUS`, `LAST_HEALTH_STATUS_UPDATED_ON`, `UPGRADE_STATE`, `CURRENT_VERSION`, `CURRENT_PATCH`, `CONSUMER_ORGANIZATION_NAME`, `CONSUMER_ACCOUNT_NAME`, `APPLICATION_NAME_HASH`.

Generate queries tailored to the user's needs. Common patterns:

```sql
-- Current health status of all consumer instances
SELECT CONSUMER_ORGANIZATION_NAME, CONSUMER_ACCOUNT_NAME,
       LAST_HEALTH_STATUS, LAST_HEALTH_STATUS_UPDATED_ON
FROM SNOWFLAKE.DATA_SHARING_USAGE.APPLICATION_STATE
WHERE PACKAGE_NAME = '<package_name>'
ORDER BY LAST_HEALTH_STATUS_UPDATED_ON DESC;

-- Instances reporting FAILED
SELECT CONSUMER_ORGANIZATION_NAME, CONSUMER_ACCOUNT_NAME,
       LAST_HEALTH_STATUS_UPDATED_ON, UPGRADE_STATE, CURRENT_VERSION
FROM SNOWFLAKE.DATA_SHARING_USAGE.APPLICATION_STATE
WHERE PACKAGE_NAME = '<package_name>'
  AND LAST_HEALTH_STATUS = 'FAILED';

-- Upgrade rollout progress
SELECT CURRENT_VERSION, CURRENT_PATCH, UPGRADE_STATE, COUNT(*) AS instance_count
FROM SNOWFLAKE.DATA_SHARING_USAGE.APPLICATION_STATE
WHERE PACKAGE_NAME = '<package_name>'
GROUP BY ALL
ORDER BY CURRENT_VERSION, CURRENT_PATCH;
```

---

### Path B: Query Lifecycle Events

Lifecycle events are Snowflake-generated `RECORD_TYPE = 'EVENT'` entries that record status changes for native app instances. They require event sharing to be configured (see `configure-event-sharing/SKILL.md`).

**Prerequisites:** `log_event_level` (BCR 2026_02) or `log_level` must be `INFO` or more verbose in the manifest — lifecycle events are NOT emitted when the controlling level is `OFF`.

All lifecycle events share the base filter `SCOPE:"name"::STRING = 'snow.application.lifecycle'`. Use `RECORD:name` to distinguish event types. See `references/lifecycle-events-reference.md` for the full event type table and filters.

Common query patterns:

```sql
-- Recent health status changes
SELECT TIMESTAMP, RESOURCE_ATTRIBUTES:"snow.application.name"::STRING AS app_name,
       VALUE:health_status::STRING AS health_status
FROM <event_table>
WHERE RECORD_TYPE = 'EVENT' AND SCOPE:"name"::STRING = 'snow.application.lifecycle'
  AND RECORD:"name"::STRING = 'application.state_change'
  AND VALUE:health_status IS NOT NULL
ORDER BY TIMESTAMP DESC LIMIT 20;

-- Upgrade state transitions
SELECT TIMESTAMP, RESOURCE_ATTRIBUTES:"snow.application.name"::STRING AS app_name,
       VALUE:upgrade_state::STRING AS upgrade_state,
       VALUE:upgrade_attempt::INTEGER AS attempt,
       VALUE:target_upgrade_version::STRING AS target_version,
       VALUE:upgrade_failure_reason::STRING AS failure_reason
FROM <event_table>
WHERE RECORD_TYPE = 'EVENT' AND SCOPE:"name"::STRING = 'snow.application.lifecycle'
  AND RECORD:"name"::STRING = 'application.state_change'
  AND VALUE:upgrade_state IS NOT NULL
ORDER BY TIMESTAMP DESC LIMIT 20;
```

For shared events from consumers, `RESOURCE_ATTRIBUTES` includes `snow.application.package.name`, `snow.application.consumer.organization`, `snow.application.consumer.name` — consumer-identifying fields are SHA-1 hashed.

---

## Completion

Present the generated queries to the user. If running against a live deployment, offer to execute them. Summarize findings (healthy vs failed instances, upgrade progress, recent events).

**Next steps:** Configure telemetry — load `configure-telemetry-event-and-health-update/SKILL.md`. Set up event accounts for cross-region monitoring — load `configure-event-sharing/SKILL.md`.
