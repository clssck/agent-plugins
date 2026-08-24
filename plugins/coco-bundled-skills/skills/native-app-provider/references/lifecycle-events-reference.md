# Lifecycle Events & APPLICATION_STATE Reference

## APPLICATION_STATE View

`SNOWFLAKE.DATA_SHARING_USAGE.APPLICATION_STATE` provides current health and upgrade status per consumer instance. No setup needed beyond calling `SYSTEM$REPORT_HEALTH_STATUS` from the app.

**Key columns:** `PACKAGE_NAME`, `LAST_HEALTH_STATUS`, `LAST_HEALTH_STATUS_UPDATED_ON`, `UPGRADE_STATE`, `CURRENT_VERSION`, `CURRENT_PATCH`, `CONSUMER_ORGANIZATION_NAME`, `CONSUMER_ACCOUNT_NAME`, `APPLICATION_NAME_HASH`.

```sql
SELECT CONSUMER_ORGANIZATION_NAME, CONSUMER_ACCOUNT_NAME,
       LAST_HEALTH_STATUS, LAST_HEALTH_STATUS_UPDATED_ON
FROM SNOWFLAKE.DATA_SHARING_USAGE.APPLICATION_STATE
WHERE PACKAGE_NAME = '<package_name>'
ORDER BY LAST_HEALTH_STATUS_UPDATED_ON DESC;
```

For **historical** health changes and audit trails, query lifecycle events below (requires event sharing).

## Lifecycle Events

Lifecycle events are Snowflake-generated `RECORD_TYPE = 'EVENT'` entries that record status changes for native app instances.

**Prerequisites:** Set `log_event_level` (BCR 2026_02) or `log_level` (pre-BCR) to `INFO` or more verbose in the manifest — lifecycle events are NOT emitted when the controlling level is `OFF`.

All lifecycle events share the base filter `SCOPE:"name"::STRING = 'snow.application.lifecycle'`. Use `RECORD:name` to distinguish event types and null-check `VALUE` fields to filter:

| Event type | `RECORD:name` | Filter | Key `VALUE` fields |
|---|---|---|---|
| Health status change | `application.state_change` | `VALUE:health_status IS NOT NULL` | `health_status` (OK/FAILED/PAUSED) |
| Upgrade state change | `application.state_change` | `VALUE:upgrade_state IS NOT NULL` | `upgrade_state`, `upgrade_attempt`; also `target_upgrade_version`/`target_upgrade_patch` (QUEUED/INSTALLING/UPGRADING), `upgrade_failure_reason` (FAILED/QUEUED_RETRY/DISABLED/INSTALL_FAILED), `disablement_reasons` (DISABLED) |
| Auto-grant change | `application.auto_grant_change` | — | `action` (GRANTED/REVOKED), `privileges` (array of privilege names) |

**Example** — health status changes (adapt filters from table above for other event types):

```sql
SELECT TIMESTAMP, RESOURCE_ATTRIBUTES:"snow.application.name"::STRING AS app_name,
       VALUE:health_status::STRING AS health_status
FROM <your_event_table>
WHERE RECORD_TYPE = 'EVENT' AND SCOPE:"name"::STRING = 'snow.application.lifecycle'
  AND RECORD:"name"::STRING = 'application.state_change'
  AND VALUE:health_status IS NOT NULL
ORDER BY TIMESTAMP DESC LIMIT 20;
```

For shared events from consumers, `RESOURCE_ATTRIBUTES` includes `snow.application.package.name`, `snow.application.consumer.organization/name`; consumer-identifying fields are SHA-1 hashed.
