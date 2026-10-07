---
name: snowflake-apps-operate
description: "Post-deploy operations for SAR apps (Snowflake App Runtime apps, also called Snowflake Apps): logs, status, suspend/resume, upgrade, rollback. Use when the user wants to monitor, troubleshoot, or manage a running app."
---

# Operate a SAR App

Use this skill when the user wants to monitor, troubleshoot, or manage a deployed SAR app (Snowflake App Runtime app). The rest of this skill just says "app".

> Operations below use SQL, which works in any environment. Some also have a `snow app` CLI equivalent — prefer it when available, and fall back to SQL if the CLI is unavailable or its session token has expired.

> **Confirm before acting**: Always confirm with the user before any destructive or user-visible operation — suspend, restart, upgrade, rollback, drop, rename, teardown, or persistent property changes. These take the service offline or cause a brief interruption for all users.

---

## Find the service you're operating on

Every statement below needs the service's `<database>.<schema>.<app_name>`. Read it from the manifest that drives the project ([`@../references/manifests.md`](../references/manifests.md)). If that manifest declares `targets`, each target is a **separate application service** — resolve the one the user means before running anything, and name it in your summary so a `prod` operation is never mistaken for `dev`.

> **On an `app.yml` v2 project, property changes made here do not survive a redeploy.** Deploys apply the manifest declaratively, so `SET AUTO_SUSPEND_SECS`, `SET QUERY_WAREHOUSE`, `SET EXTERNAL_ACCESS_INTEGRATIONS`, and similar revert to whatever the manifest says the next time anyone deploys. When the user wants a lasting change, put it in `app.yml` — and tell them that's why.

---

## Check App Status

### Quick status

```sql
DESCRIBE APPLICATION SERVICE <database>.<schema>.<app_name>;
```

Key columns:

| Column | What to look for |
|--------|------------------|
| `status` | `RUNNING` = healthy; `SUSPENDED` = paused; `SUSPENDING` = transitioning to suspended; `FAILED` = fatal error; `PENDING` = starting up; `DONE` = job service completed; `DELETING` = drop in progress; `INTERNAL_ERROR` = platform-level error |
| `url` | Public endpoint; empty or "provisioning in progress" = not ready yet |
| `is_upgrading` | `true` during an upgrade; if stuck, the upgrade may have failed |
| `compute_pool` | Empty string when managed pools are active (expected) |
| `source` | JSON: `artifactRepository`, `package`, `version`, `alias` |
| `auto_resume` | `true` = resumes automatically; default is `true` |
| `auto_suspend_secs` | `0` = never auto-suspend; minimum non-zero value is 300 |

### List all apps

```sql
-- All apps in a schema
SHOW APPLICATION SERVICES IN SCHEMA <database>.<schema>;

-- Filter by name pattern
SHOW APPLICATION SERVICES LIKE '<pattern>' IN SCHEMA <database>.<schema>;

-- All in account
SHOW APPLICATION SERVICES IN ACCOUNT;

-- Additional filter options
SHOW APPLICATION SERVICES IN SCHEMA <database>.<schema> STARTS WITH '<prefix>';
SHOW APPLICATION SERVICES IN SCHEMA <database>.<schema> LIMIT 10;
SHOW APPLICATION SERVICES IN SCHEMA <database>.<schema> LIMIT 10 FROM '<name>'; -- exclusive resume
```

`SHOW APPLICATION SERVICES` returns 21 columns:
`created_on`, `name`, `status`, `database_name`, `schema_name`, `query_warehouse`, `compute_pool`, `url`, `privatelink_url`, `owner`, `owner_role_type`, `created_by`, `source`, `resumed_on`, `suspended_on`, `is_upgrading`, `auto_resume`, `auto_suspend_secs`, `external_access_integrations`, `comment`, `additional_properties`

> Application services are invisible in `SHOW SERVICES`. Always use `SHOW APPLICATION SERVICES`.

---

## View Logs

```sql
CALL SYSTEM$GET_APPLICATION_SERVICE_LOGS('<database>.<schema>.<app_name>');

-- With explicit line count
CALL SYSTEM$GET_APPLICATION_SERVICE_LOGS('<database>.<schema>.<app_name>', 500);
```

For structured logs, metrics, and event records from the event table (including the `SYSTEM$GET_APPLICATION_SERVICE_EVENT_TABLE_DATA` function, column layouts, and large-result pagination), see [`@../references/logs.md`](../references/logs.md).

---

## Monitor Resource Health (CPU / Memory / Restarts)

For runtime health monitoring — CPU and memory usage vs. limits, in-memory caching headroom, restart counts, and crash-loop detection — see [`@../references/monitoring.md`](../references/monitoring.md).

---

## Suspend and Resume

```sql
ALTER APPLICATION SERVICE <database>.<schema>.<app_name> SUSPEND;
ALTER APPLICATION SERVICE <database>.<schema>.<app_name> RESUME;
```

### Auto-suspend and auto-resume

```sql
-- Enable auto-suspend after 10 minutes idle (minimum non-zero: 300 seconds)
ALTER APPLICATION SERVICE <database>.<schema>.<app_name>
    SET AUTO_SUSPEND_SECS = 600;

-- Disable auto-suspend (resets to 0 = never)
ALTER APPLICATION SERVICE <database>.<schema>.<app_name>
    UNSET AUTO_SUSPEND_SECS;

-- Disable auto-resume
ALTER APPLICATION SERVICE <database>.<schema>.<app_name>
    SET AUTO_RESUME = FALSE;

-- Re-enable auto-resume (resets to true)
ALTER APPLICATION SERVICE <database>.<schema>.<app_name>
    UNSET AUTO_RESUME;
```

---

## Open the App

Requires `USAGE` privilege on the application service. Get the URL via SHOW:

```sql
SHOW APPLICATION SERVICES LIKE '<app_name>' IN SCHEMA <database>.<schema>;
-- Read the 'url' column from the result
```

---

## Upgrade

```sql
-- Upgrade to the latest version
ALTER APPLICATION SERVICE <database>.<schema>.<app_name> UPGRADE;

-- Upgrade to a specific version
ALTER APPLICATION SERVICE <database>.<schema>.<app_name>
    UPGRADE TO VERSION <version_or_alias>;
```

Requires `OPERATE` privilege (or `OWNERSHIP`). During upgrade, `is_upgrading = 'true'` in DESCRIBE output; the URL does not change.

## Restart

Restart = SUSPEND then RESUME. Causes a brief service outage for all users — confirm with the user first. Requires `OPERATE` privilege (or `OWNERSHIP`).

```sql
ALTER APPLICATION SERVICE <database>.<schema>.<app_name> SUSPEND;
ALTER APPLICATION SERVICE <database>.<schema>.<app_name> RESUME;
```

## Rollback, Rename, Modify Properties, Drop, Teardown, Share / Grant Access

See [`@../references/lifecycle.md`](../references/lifecycle.md).

---

## Common Issues

See [`@../references/debugging.md`](../references/debugging.md) for the full debugging guide covering deploy failures, RBAC diagnostics, build log retrieval, and the end-to-end debugging checklist.
