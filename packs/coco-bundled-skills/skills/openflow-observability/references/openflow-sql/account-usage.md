---
name: openflow-observability-account-usage
description: Read-only historical context for SQL-managed Openflow runtimes and deployments via ACCOUNT_USAGE.OPENFLOW_DEPLOYMENTS and ACCOUNT_USAGE.OPENFLOW_RUNTIMES. Tier 2 only; load when historical change context, recently-deleted-runtime context, or cross-referencing with event-table evidence is needed.
---

# Openflow ACCOUNT_USAGE Views (Read-Only)

> Customer-facing name: **Openflow account usage views**.

`SHOW OPENFLOW *` and `DESCRIBE OPENFLOW *` only see the live state of objects the current role has `MONITOR` on. Two `ACCOUNT_USAGE` views complement them with **historical metadata** for SQL-managed deployments and runtimes:

- `SNOWFLAKE.ACCOUNT_USAGE.OPENFLOW_DEPLOYMENTS`
- `SNOWFLAKE.ACCOUNT_USAGE.OPENFLOW_RUNTIMES`

These views follow standard `ACCOUNT_USAGE` semantics: they include deleted rows (with `DELETED` populated), they have latency on the order of minutes-to-hours, and they require the standard `SNOWFLAKE` database access (typically `ACCOUNTADMIN`, `SECURITY_ADMIN`, or a role with `IMPORTED PRIVILEGES` on the `SNOWFLAKE` database).

Load this file when:

- The customer asks "when did this last change?" / "when was this last resumed?" / "when was this deleted?".
- A runtime listed in a recent error is no longer visible to `SHOW OPENFLOW RUNTIMES` (was it deleted? when?).
- Cross-referencing event-table timestamps against last-altered / last-resumed metadata for incident reconstruction.
- Identifying recently-deleted runtimes / orphans before proposing customer-run cleanup.

Nothing in this file mutates state.

---

## ACCOUNT_USAGE.OPENFLOW_DEPLOYMENTS

### Columns (relevant subset)

| Column                            | Data Type | Notes                                                                                                                  |
| --------------------------------- | --------- | ---------------------------------------------------------------------------------------------------------------------- |
| `NAME`                            | VARCHAR   | Deployment name.                                                                                                       |
| `DEPLOYMENT_ID`                   | NUMBER    | Internal/system-generated identifier for the deployment.                                                               |
| `DATA_PLANE_ID`                   | VARCHAR   | Internal data plane ID (used by the Openflow CP/UI).                                                                   |
| `DEPLOYMENT_KEY`                  | VARCHAR   | Stable string mapping to the deployment; used internally and for joining to other Openflow telemetry.                  |
| `DEPLOYMENT_TYPE`                 | VARCHAR   | `BYOC` or `SNOWFLAKE` (SPCS).                                                                                          |
| `VPC_TYPE`                        | VARCHAR   | `MANAGED` or `PROVIDED`.                                                                                               |
| `USE_PRIVATELINK`                 | BOOLEAN   | Whether PrivateLink is enabled for the deployment.                                                                     |
| `USE_USER_AUTH_OVER_PRIVATELINK`  | BOOLEAN   | Whether browser-based authentication uses the PrivateLink endpoint.                                                    |
| `CUSTOM_INGRESS_HOSTNAME`         | VARCHAR   | FQDN for custom ingress.                                                                                               |
| `DISPLAY_NAME`                    | VARCHAR   | Display name in the UI.                                                                                                |
| `CREATED`                         | TIMESTAMP | When the deployment was created.                                                                                       |
| `LAST_ALTERED`                    | TIMESTAMP | When any deployment-level setting was last changed.                                                                    |
| `DELETED`                         | TIMESTAMP | When the deployment was deleted. NULL for live deployments.                                                            |
| `OWNER`                           | VARCHAR   | Role that owns the deployment.                                                                                         |
| `OWNER_ROLE_TYPE`                 | VARCHAR   | Type of the owning role.                                                                                               |
| `COMMENT`                         | VARCHAR   | Optional comment.                                                                                                      |

### Use cases

- **"When was this deployment last touched?"** -- `SELECT NAME, LAST_ALTERED FROM SNOWFLAKE.ACCOUNT_USAGE.OPENFLOW_DEPLOYMENTS WHERE NAME = '{deployment_name}';`
- **"What deployments did we delete in the last 30 days?"** -- filter `DELETED IS NOT NULL AND DELETED >= DATEADD(day, -30, CURRENT_TIMESTAMP())`.
- **Confirming a deployment is BYOC vs SPCS for branching** without needing live `SHOW OPENFLOW DEPLOYMENTS` access (useful when the role has `IMPORTED PRIVILEGES` on `SNOWFLAKE` but not `MONITOR` on the deployment object).

---

## ACCOUNT_USAGE.OPENFLOW_RUNTIMES

### Columns (relevant subset)

| Column                  | Data Type | Notes                                                                                                                     |
| ----------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------- |
| `RUNTIME_NAME`          | VARCHAR   | SQL name of the runtime.                                                                                                  |
| `RUNTIME_DISPLAY_NAME`  | VARCHAR   | Display name in the UI (if set).                                                                                          |
| `RUNTIME_ID`            | NUMBER    | Internal/system-generated identifier of the runtime.                                                                      |
| `RUNTIME_SCHEMA`        | VARCHAR   | Schema this runtime belongs to.                                                                                           |
| `RUNTIME_SCHEMA_ID`     | NUMBER    | Internal ID of the runtime's schema.                                                                                      |
| `RUNTIME_CATALOG`       | VARCHAR   | Catalog (database) this runtime belongs to.                                                                               |
| `RUNTIME_CATALOG_ID`    | NUMBER    | Internal ID of the runtime's catalog.                                                                                     |
| `DEPLOYMENT_ID`         | NUMBER    | Internal/system-generated identifier for the parent deployment.                                                           |
| `DEPLOYMENT_NAME`       | VARCHAR   | Name of the parent deployment.                                                                                            |
| `DISPLAY_NAME`          | VARCHAR   | Same as `RUNTIME_DISPLAY_NAME` for some queries; verify against your view definition before relying on either.            |
| `CREATED`               | TIMESTAMP | When the runtime was created.                                                                                             |
| `LAST_RESUMED`          | TIMESTAMP | When the runtime was most recently resumed from `SUSPENDED`. NULL for runtimes that have never been resumed.              |
| `LAST_ALTERED`          | TIMESTAMP | When any runtime-level setting was last changed.                                                                          |
| `DELETED`               | TIMESTAMP | When the runtime was deleted. NULL for live runtimes.                                                                     |
| `OWNER`                 | VARCHAR   | Role that owns the runtime.                                                                                               |
| `OWNER_ROLE_TYPE`       | VARCHAR   | Type of the owning role.                                                                                                  |
| `COMMENT`               | VARCHAR   | Optional comment.                                                                                                         |

### Use cases

- **Anchoring an incident to a recent change** -- if the customer reports degradation since a specific timestamp, run:
  ```sql
  SELECT RUNTIME_NAME, DEPLOYMENT_NAME, LAST_RESUMED, LAST_ALTERED
    FROM SNOWFLAKE.ACCOUNT_USAGE.OPENFLOW_RUNTIMES
   WHERE RUNTIME_NAME = '{runtime_name}'
     AND (LAST_ALTERED >= DATEADD(hour, -24, CURRENT_TIMESTAMP())
          OR LAST_RESUMED >= DATEADD(hour, -24, CURRENT_TIMESTAMP()));
  ```
  A `LAST_ALTERED` close to the incident `{error_timestamp}` is strong evidence the change correlates.
- **Finding recently-deleted runtimes / orphans** -- filter `DELETED IS NOT NULL AND DELETED >= DATEADD(day, -7, CURRENT_TIMESTAMP())`. Combine with event-table queries to see whether any logs still mention the deleted runtime's namespace.
- **Cross-referencing the parent deployment** -- `DEPLOYMENT_NAME` and `DEPLOYMENT_ID` join cleanly to `ACCOUNT_USAGE.OPENFLOW_DEPLOYMENTS`. Use this when the runtime is visible but the parent deployment is not (privilege gap), or vice versa.

---

## Latency, Privilege, and Trust Notes

- **Latency.** `ACCOUNT_USAGE` views can lag the live state by 45 minutes to a few hours. For real-time state always prefer `SHOW OPENFLOW *` / `DESCRIBE OPENFLOW *`. Use these views for **history**, not for "is it ACTIVE right now?"
- **Privilege.** Access requires `SNOWFLAKE` database access. If the customer's role cannot query these views, do not attempt -- ask them to run the query themselves with `ACCOUNTADMIN` or whichever role has the necessary `IMPORTED PRIVILEGES`.
- **Trust boundary.** These views are authoritative for what they show, but they only show SQL-managed (Object-Model-based) entities. Legacy runtimes that were never migrated to the object model do not appear. If a runtime is missing from both `SHOW OPENFLOW RUNTIMES` and `ACCOUNT_USAGE.OPENFLOW_RUNTIMES`, it is either legacy or never existed -- direct the customer to the Openflow UI for legacy listings.
- **Customer-facing wording.** Refer to these as "the historical Openflow account usage views" or "Snowflake's `ACCOUNT_USAGE.OPENFLOW_*` views".
