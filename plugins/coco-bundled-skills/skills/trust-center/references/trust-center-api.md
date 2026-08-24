# Trust Center API Reference

This reference documents the known Trust Center views and stored procedures in the `snowflake.trust_center` schema. Some views and procedures may not be present in every account. To discover what is actually available in the current account, you must use these commands:

```sql
-- List all available views
SHOW VIEWS IN SCHEMA snowflake.trust_center;

-- Inspect columns for a specific view
DESCRIBE VIEW snowflake.trust_center.<view_name>;

-- List all available stored procedures
SHOW PROCEDURES IN SCHEMA snowflake.trust_center;
```

## Required Roles

- `trust_center_admin` — Full access to all views and all stored procedures listed below.
- `trust_center_viewer` — Read-only access to all views. Cannot call configuration or mutation procedures (except `set_account_notification_enabled` and `get_trusted_extensions`).

For executing remediation SQL outside of Trust Center (e.g., setting network policies, disabling users), `ACCOUNTADMIN`, `SECURITYADMIN`, or roles with the necessary privileges are required.

---

## Views

### `snowflake.trust_center.findings`

Contains all finding records from scanner runs. Every scanner run creates a record, even if no issues are detected (`TOTAL_AT_RISK_COUNT = 0`). Union of scheduled vulnerability findings and event-driven detection findings.

| Column | Type | Description |
|--------|------|-------------|
| `SCANNER_PACKAGE_ID` | varchar | Unique ID for the scanner package |
| `SCANNER_PACKAGE_NAME` | varchar | Display name of the scanner package |
| `SCANNER_PACKAGE_DESCRIPTION` | varchar | Full description of the scanner package |
| `SCANNER_PACKAGE_SHORT_DESCRIPTION` | varchar | Brief scanner package description |
| `SCANNER_ID` | varchar | Unique ID for the scanner |
| `SCANNER_NAME` | varchar | Display name of the scanner |
| `SCANNER_DESCRIPTION` | varchar | Full description of what the scanner checks |
| `SCANNER_SHORT_DESCRIPTION` | varchar | Brief scanner description (dynamically constructed for strong-auth readiness scanners based on remediation metadata) |
| `EVENT_ID` | number | Unique ID for every scanner run event |
| `SCANNER_TYPE` | varchar | `Vulnerability`, `Detection`, or NULL. Value is `initcap`-formatted. Legacy values `Alert` and `Threat` are equivalent to `Detection`. |
| `COMPLETION_STATUS` | varchar | `SUCCEEDED` if scanner completed successfully, `FAILED` otherwise |
| `SUGGESTED_ACTION` | varchar | Detailed markdown remediation steps with SQL examples |
| `IMPACT` | varchar | Side effects and risks of applying the remediation |
| `SEVERITY` | varchar | `Critical`, `High`, `Medium`, `Low` |
| `TOTAL_AT_RISK_COUNT` | number | Count of affected entities (0 = no issues found) |
| `AT_RISK_ENTITIES` | array | JSON array of affected entities (see AT_RISK_ENTITIES Structure below) |
| `START_TIMESTAMP` | timestamp_ltz | When the scanner run started |
| `END_TIMESTAMP` | timestamp_ltz | When the scanner run completed |
| `CREATED_ON` | timestamp_ltz | When the finding was first logged |
| `FINDING_IDENTIFIER` | varchar | Fully qualified finding ID: `<package_id>.<scanner_id>.<risk_id>.<severity>`. For extension scanners the format includes the source prefix. |
| `STATE` | varchar | `Open`, `Resolved`, or `Muted`. Derived from manual state overrides and at-risk count. `Muted` appears when a finding was manually muted via `post_finding_activity` (may show as `Resolved` in some accounts). Use `UPPER()` in comparisons. |
| `STATE_LAST_MODIFIED_ON` | timestamp_ltz | When finding state was last manually changed by a user |
| `METADATA` | object | Optional custom metadata from the scanner |

**Additional columns** (may not be present in all accounts — use `DESCRIBE VIEW` to check):

| Column | Type | Description |
|--------|------|-------------|
| `ERROR_CODE` | varchar | Scanner failure error code |
| `ERROR_MESSAGE` | varchar | Scanner failure error message |
| `EXTENSION_ID` | number | ID of the Trust Center Extension Native App instance |
| `EXTENSION_NAME` | varchar | Name of the Trust Center Extension Native App instance |
| `SCANNER_PACKAGE_SOURCE_TYPE` | varchar | `APPLICATION PACKAGE` or `LISTING` (NULL for built-in scanners) |
| `SCANNER_PACKAGE_SOURCE` | varchar | Name of the application package or listing ID |
| `EXTENSION_VERSION` | varchar | Version of the Extension at scan time |
| `EXTENSION_PATCH` | number | Patch number of the Extension at scan time |

---

### `snowflake.trust_center.scanners`

Contains metadata about each installed (non-deregistered) scanner in the account.

| Column | Type | Description |
|--------|------|-------------|
| `NAME` | varchar | Display name of the scanner |
| `ID` | varchar | Unique ID for the scanner (use this in API calls, not `NAME`) |
| `SHORT_DESCRIPTION` | varchar | Brief description |
| `DESCRIPTION` | varchar | Full description |
| `SCANNER_PACKAGE_ID` | varchar | ID of the parent scanner package |
| `STATE` | varchar | `TRUE` = enabled, `FALSE` or NULL = not enabled. From running configuration. Use `UPPER()` in comparisons. |
| `SCHEDULE` | varchar | Cron schedule (e.g., `USING CRON 7 6 * * 2 America/Los_Angeles`). NULL for event-driven scanners. |
| `NOTIFICATION` | varchar | JSON notification config: `{"NOTIFY_ADMINS":"TRUE","SEVERITY_THRESHOLD":"CRITICAL","USERS":[]}`. Empty `{}` = no notification. |
| `LAST_SCAN_TIMESTAMP` | timestamp_ltz | When last scan completed. NULL for event-driven scanners or scanners that haven't run. |

**Additional columns** (may not be present in all accounts — use `DESCRIBE VIEW` to check):

| Column | Type | Description |
|--------|------|-------------|
| `MAX_SEVERITY` | varchar | Max severity of findings emitted by scanner; `UNSPECIFIED` if not set in manifest |
| `TYPE` | varchar | Type of the scanner: `SCHEDULED` or `EVENT_DRIVEN` |
| `HAS_CUSTOM_CONFIGURATION` | boolean | `TRUE` if the scanner exposes configurable parameters (thresholds, windows, etc.) that can be tuned via `set_configuration`. Query `configuration_view` filtered by this scanner to see the available config names, current values, allowed values, and defaults. |
| `EXTENSION_ID` | number | ID of the Trust Center Extension Native App instance |
| `EXTENSION_NAME` | varchar | Name of the Extension |
| `SCANNER_PACKAGE_SOURCE_TYPE` | varchar | `APPLICATION PACKAGE` or `LISTING` (NULL for built-in scanners) |
| `SCANNER_PACKAGE_SOURCE` | varchar | Name of the application package or listing ID |

---

### `snowflake.trust_center.scanner_packages`

Contains metadata about each installed (non-deregistered) scanner package.

| Column | Type | Description |
|--------|------|-------------|
| `NAME` | varchar | Display name of the package |
| `ID` | varchar | Unique ID for the package (use this in API calls, not `NAME`) |
| `DESCRIPTION` | varchar | Package description |
| `DEFAULT_SCHEDULE` | varchar | Default schedule per the package manifest |
| `STATE` | varchar | `TRUE` = enabled, `FALSE` or NULL = not enabled. Uses configuration table or defaults. Use `UPPER()` in comparisons. |
| `SCHEDULE` | varchar | Current active schedule (may differ from `DEFAULT_SCHEDULE` if customized) |
| `NOTIFICATION` | varchar | JSON notification config (same format as scanners) |
| `LAST_ENABLED_TIMESTAMP` | timestamp_ltz | When the package was last enabled |
| `LAST_DISABLED_TIMESTAMP` | timestamp_ltz | When the package was last disabled |
| `PROVIDER` | varchar | `Snowflake` (built-in), `External` (listing-based extension), or `Custom` (application-package-based extension) |

**Additional columns** (may not be present in all accounts — use `DESCRIBE VIEW` to check):

| Column | Type | Description |
|--------|------|-------------|
| `EXTENSION_ID` | number | ID of the Trust Center Extension Native App instance |
| `EXTENSION_NAME` | varchar | Name of the Extension |
| `SCANNER_PACKAGE_SOURCE_TYPE` | varchar | `APPLICATION PACKAGE` or `LISTING` (NULL for built-in scanners) |
| `SCANNER_PACKAGE_SOURCE` | varchar | Name of the application package or listing ID |
| `LATEST_ASYNC_JOB_ID` | varchar | ID of the latest async job for this scanner package |
| `LATEST_ASYNC_JOB_STATUS` | varchar | `PENDING`, `PROCESSING`, `COMPLETED`, or `FAILED` |
| `LATEST_ASYNC_JOB_ERROR_MESSAGE` | varchar | Error message from the latest async job |

---

### `snowflake.trust_center.configuration_view`

Contains the full configuration resolution chain for each scanner. Shows configuration values at every level (override, package, scanner, org, default) and the effective running value.

| Column | Type | Description |
|--------|------|-------------|
| `SCANNER_PACKAGE_ID` | varchar | Package ID |
| `SCANNER_ID` | varchar | Scanner ID |
| `TYPE` | varchar | Scanner type: `SCHEDULED` or `EVENT_DRIVEN` (defaults to `SCHEDULED` if not set) |
| `CONFIGURATION_NAME` | varchar | Config type. Standard values: `ENABLED`, `SCHEDULE`, `NOTIFICATION`, `NOTIFICATION_INTEGRATION`. For scanners where `HAS_CUSTOM_CONFIGURATION = TRUE`, additional rows appear with scanner-defined names (e.g., `MIN_PASSWORD_LENGTH`). These custom config names are the values to pass to `set_configuration` and `unset_configuration`. |
| `RUNNING_CONFIGURATION_VALUE` | varchar | Current runtime value of this configuration (from the task state cache) |
| `SET_CONFIGURATION_VALUE` | varchar | Effective resolved value after applying the full precedence chain: platform override > package override > scanner config > package config > org config > scanner default > package default. `NULL` means no override is set and the scanner is using its default. |
| `PLATFORM_OVERRIDE_CONFIGURATION_VALUE` | varchar | Value from platform-level overrides, or NULL if not overridden |
| `SCANNER_PACKAGE_CONFIGURATION_VALUE` | varchar | Value explicitly set at the package level by the user |
| `SCANNER_CONFIGURATION_VALUE` | varchar | Value explicitly set at the scanner level by the user |
| `DEFAULT_SCANNER_VALUE` | varchar | Default value for this configuration at scanner level |
| `DEFAULT_SCANNER_PACKAGE_VALUE` | varchar | Default value for this configuration at package level |
| `SCANNER_PACKAGE_CONFIGURATION_OVERRIDE` | boolean | Whether the package-level config overrides scanner-level config |
| `EXTENSION_ID` | number | Extension ID (NULL for built-in scanners) |

**Additional columns** (may not be present in all accounts — use `DESCRIBE VIEW` to check):

| Column | Type | Description |
|--------|------|-------------|
| `ORG_SCANNER_PACKAGE_CONFIGURATION_VALUE` | varchar | Organization-level package configuration value |
| `ORG_SCANNER_CONFIGURATION_VALUE` | varchar | Organization-level scanner configuration value |
| `ORG_SCANNER_PACKAGE_CONFIGURATION_OVERRIDE` | boolean | Whether org package-level config overrides scanner-level |
| `ALLOWED_VALUES` | array | Allowed values for this configuration. Non-NULL for custom configs with a fixed value set. |
| `ALLOWED_PATTERN` | varchar | Regex pattern for valid values. Non-NULL for custom configs with free-form string validation. |
| `DESCRIPTION` | varchar | Human-readable description of what this configuration controls. Most useful for custom config rows. |
| `EXPECTED_TYPE` | varchar | Expected data type for the value: `BOOLEAN`, `VARCHAR`, `OBJECT`, or `ARRAY`. Custom config values are always passed as VARCHAR strings — use this column to know the underlying type. |
| `EXTENSION_NAME` | varchar | Name of the Extension |
| `SCANNER_PACKAGE_SOURCE_TYPE` | varchar | `APPLICATION PACKAGE` or `LISTING` |
| `SCANNER_PACKAGE_SOURCE` | varchar | Name of the application package or listing |

**Note:** `SCHEDULE` configuration is excluded for `EVENT_DRIVEN` scanners to prevent confusion from inherited schedule values.

---

### `snowflake.trust_center.time_series_daily_findings`

Pre-aggregated daily snapshots of findings for trend analysis. Selects the most recent scanner run per day per scanner, and aggregates by severity. Muted/resolved findings are excluded from the day they were muted onward.

| Column | Type | Description |
|--------|------|-------------|
| `SCANNER_PACKAGE_ID` | varchar | Package ID |
| `SCANNER_PACKAGE_NAME` | varchar | Package display name |
| `SCANNER_PACKAGE_DESCRIPTION` | varchar | Package description |
| `SCANNER_ID` | varchar | Scanner ID |
| `SCANNER_TYPE` | varchar | `Vulnerability`, `Detection`, or `Threat` (initcap-formatted) |
| `RUN_ID` | varchar | Unique ID (UUID) for the scanner run |
| `COMPLETION_STATUS` | varchar | `SUCCEEDED` or `FAILED` |
| `CRITICAL_RISK_COUNT` | number | Count of critical-severity findings with at-risk entities on that day |
| `HIGH_RISK_COUNT` | number | High-severity findings count |
| `MEDIUM_RISK_COUNT` | number | Medium-severity findings count |
| `LOW_RISK_COUNT` | number | Low-severity findings count |
| `NONE_RISK_COUNT` | number | Findings with 0 at-risk entities (compliant) |
| `END_TIMESTAMP` | timestamp_ltz | When the scanner run finished |
| `DAY_PARTITION` | timestamp_ltz | Date partition (truncated to day) |

**Additional columns** (may not be present in all accounts — use `DESCRIBE VIEW` to check):

| Column | Type | Description |
|--------|------|-------------|
| `EXTENSION_ID` | varchar | Extension app instance ID |

**Note:** Queries against this view can be slow due to the complex underlying query.

---

### `snowflake.trust_center.finding_comments`

Contains comments made by users on findings.

| Column | Type | Description |
|--------|------|-------------|
| `FINDING_IDENTIFIER` | varchar | Fully qualified finding ID (`package_id.scanner_id.risk_id.severity`) |
| `COMMENT_ID` | number | Unique ID for the comment |
| `COMMENT` | varchar | Comment text (max 500 characters) |
| `CREATED_ON` | timestamp_ltz | When the comment was created |
| `EDITED_ON` | timestamp_ltz | When the comment was last edited (NULL if never edited) |
| `USER` | varchar | User who made the comment |
| `USER_ID` | varchar | User ID of the commenter |

Results are ordered by `CREATED_ON DESC`.

---

### `snowflake.trust_center.finding_activity_history`

Tracks user activity on findings (state changes, comment additions/edits/deletions).

| Column | Type | Description |
|--------|------|-------------|
| `ID` | varchar | UUID for each activity record |
| `FINDING_IDENTIFIER` | varchar | Fully qualified finding ID |
| `COMMENT_ID` | number | Comment ID (NULL for state changes) |
| `COMMENT` | varchar | Comment text (NULL for state changes and comment deletions) |
| `STATE` | varchar | New finding state after update (NULL for comment activities) |
| `TYPE` | varchar | Activity type: `state_change`, `comment_addition`, `comment_alteration`, `comment_deletion` |
| `USER` | varchar | User who triggered the activity |
| `USER_ID` | varchar | User ID of the triggering user |
| `CREATED_ON` | timestamp_ltz | When the activity was performed |

Results are ordered by `CREATED_ON DESC`.

---

### `snowflake.trust_center.overview_metrics`

Contains Trust Center overview health metrics for the account (MFA readiness, passwordless readiness, and sector benchmarks).

| Column | Type | Description |
|--------|------|-------------|
| `METRIC_NAME` | varchar | Metric identifier. One of: `PERSON_USERS_MFA_READY_PERCENT`, `SERVICE_USERS_PASSWORDLESS_READY_PERCENT`, `PERSON_USERS_MFA_READY_SECTOR_BENCHMARK`, `SERVICE_USERS_PASSWORDLESS_READY_SECTOR_BENCHMARK` |
| `VALUE` | float | Metric value (rounded to 2 decimal places). Percentage or benchmark value. |

---

### `snowflake.trust_center.notification_history`

Contains history of notifications sent by Trust Center scanners.

| Column | Type | Description |
|--------|------|-------------|
| `EXTENSION_ID` | number | Extension ID (NULL for built-in scanners) |
| `SCANNER_PACKAGE_ID` | varchar | Scanner package that triggered the notification |
| `SCANNER_ID` | varchar | Scanner that triggered the notification |
| `SENT_ON` | timestamp_ltz | When the notification was sent |
| `NOTIFICATION_INTEGRATION_NAME` | varchar | `SYSTEM EMAIL` for system email notifications, or the name of the notification integration |
| `STATUS` | varchar | `SUCCESS` or `FAILURE` |
| `FINDINGS` | array | Array of `{finding_identifier, event_id}` objects for associated findings (NULL for system email notifications) |
| `ERROR_MESSAGE` | varchar | Error message if notification failed |

---

### `snowflake.trust_center.account_notification_recipients`

Contains the configured notification recipients for each account-level notification type.

| Column | Type | Description |
|--------|------|-------------|
| `NOTIFICATION_TYPE` | varchar | Notification type: `MFA_READINESS`, `EXTENSION_AVAILABLE_IN_MARKETPLACE`, or `FINDINGS_DIGEST` |
| `USERS` | array | Array of usernames configured as recipients for this notification type |

---

### `snowflake.trust_center.extensions`

Contains metadata about registered (non-deregistered) Trust Center Extensions. May not be available in all accounts.

| Column | Type | Description |
|--------|------|-------------|
| `NAME` | varchar | Name of the Trust Center Extension Native App instance |
| `ID` | number | Unique ID for the Extension |
| `SOURCE_TYPE` | varchar | `APPLICATION PACKAGE` or `LISTING` |
| `SOURCE` | varchar | Name of the application package or listing ID |
| `VERSION` | varchar | Current registered version |
| `PATCH` | number | Current registered patch number |
| `PREVIOUS_VERSION` | varchar | Previously registered version |
| `PREVIOUS_PATCH` | number | Previously registered patch number |
| `REGISTRATION_STATE` | varchar | `COMPLETE`, `FAILED`, or `REGISTERING` |
| `REGISTRATION_TARGET_VERSION` | varchar | Version being registered (during registration) |
| `REGISTRATION_TARGET_PATCH` | number | Patch number being registered (during registration) |
| `REGISTRATION_ATTEMPTED_ON` | timestamp_ltz | When the last registration attempt occurred |
| `REGISTRATION_FAILURE_REASON` | varchar | Reason the registration failed (NULL if successful) |
| `REGISTERED_TIMESTAMP` | timestamp_ltz | When the extension was first registered |

---

### `snowflake.trust_center.async_jobs`

Contains the current state of asynchronous jobs. May not be available in all accounts.

| Column | Type | Description |
|--------|------|-------------|
| `JOB_ID` | varchar | UUID v4 unique identifier for the job |
| `JOB_TYPE` | varchar | Type of job (e.g., `SET_PACKAGE_CONFIGURATION`) |
| `JOB_ARGS` | variant | Job arguments as JSON |
| `STATUS` | varchar | `PENDING`, `PROCESSING`, `COMPLETED`, or `FAILED` |
| `CREATED_TIME` | timestamp_ltz | When the job was created |
| `LAST_UPDATED_TIME` | timestamp_ltz | When the job status was last updated |
| `ERROR_MESSAGE` | varchar | Error message if the job failed |
| `RETRY_COUNT` | number | Number of retries attempted |
| `MAX_RETRY_COUNT` | number | Maximum allowed retries |

---

## Key Concepts

### Finding Types (`SCANNER_TYPE`)

- **`Vulnerability`** — A persistent configuration issue (e.g., missing network policy). Remediation is a specific configuration change. Also called "Violation" — treat both terms as equivalent.
- **`Detection`** — A threat event or anomaly (e.g., unusual login activity). Requires investigation. `Alert` and `Threat` are legacy names — treat them identically to `Detection`.
- **`NULL`** — Type not set. Inspect the scanner description for context.

### Finding States

Case may vary — always use `UPPER()` in SQL comparisons:
- `Open` — Active finding with at-risk entities requiring attention
- `Resolved` — Finding has been resolved (either `TOTAL_AT_RISK_COUNT` dropped to 0 naturally, or manually set)
- `Muted` — Finding was manually muted via `post_finding_activity` (may show as `Resolved` in some accounts)
- `NULL` — State not yet determined

### Scanner Execution Types

- **Scheduled scanners** — Have a `SCHEDULE` value (cron expression). Run periodically. `TYPE` = `SCHEDULED`.
- **Event-driven scanners** — `SCHEDULE` is NULL. Trigger on relevant events. `LAST_SCAN_TIMESTAMP` will also be NULL even when enabled — this is normal. `TYPE` = `EVENT_DRIVEN`.

### AT_RISK_ENTITIES Structure

Each element is a JSON object with:
- `entity_id` — Unique identifier for the entity
- `entity_name` — Human-readable name
- `entity_object_type` — Type (not exhaustive): `PARAMETER`, `USER`, `TASK`, `PROCEDURE`, `NETWORK_POLICY`, `ACCOUNT`
- `entity_detail` — Object with type-specific details (e.g., current parameter value, role assignments)

---

## Stored Procedures

**Always use `SCANNER_PACKAGE_ID` and `SCANNER_ID` column values from the views when calling procedures. Never use display names like "CIS Benchmarks" — use the actual ID value from the `ID` column.**

---

### `snowflake.trust_center.execute_scanner`

Runs a scanner package (all enabled scanners in it) or an individual scanner.

**RBAC:** `trust_center_admin`

**Overloads:**

| Signature | Description |
|-----------|-------------|
| `execute_scanner(scanner_package_id VARCHAR)` | Execute all enabled scanners in the specified package |
| `execute_scanner(scanner_package_id VARCHAR, scanner_id VARCHAR)` | Execute a specific scanner within a package |
| `execute_scanner(scanner_package_source_type VARCHAR, scanner_package_source VARCHAR, scanner_package_id VARCHAR)` | Execute all enabled scanners in a package (extension-aware). May not be available in all accounts. |
| `execute_scanner(scanner_package_source_type VARCHAR, scanner_package_source VARCHAR, scanner_package_id VARCHAR, scanner_id VARCHAR)` | Execute a specific scanner (extension-aware). May not be available in all accounts. |

**Parameters:**
- `scanner_package_id` (VARCHAR) — The unique ID of the scanner package (from `scanner_packages.ID`)
- `scanner_id` (VARCHAR) — The unique ID of the scanner (from `scanners.ID`)
- `scanner_package_source_type` (VARCHAR) — `APPLICATION PACKAGE` or `LISTING` (for extension scanners)
- `scanner_package_source` (VARCHAR) — Name of the application package or listing ID

**Examples:**
```sql
-- Execute entire package
CALL snowflake.trust_center.execute_scanner('SECURITY_ESSENTIALS');

-- Execute a specific scanner
CALL snowflake.trust_center.execute_scanner('THREAT_INTELLIGENCE', 'THREAT_INTELLIGENCE_NON_MFA_PERSON_USERS');
```

---

### `snowflake.trust_center.set_configuration`

Manages enablement, schedules, and notifications for packages and scanners.

**RBAC:** `trust_center_admin`

**Overloads:**

| Signature | Description |
|-----------|-------------|
| `set_configuration(configuration_name VARCHAR, configuration_value VARCHAR, scanner_package_id VARCHAR, configuration_override BOOLEAN)` | Set package-level configuration |
| `set_configuration(configuration_name VARCHAR, configuration_value VARCHAR, scanner_package_id VARCHAR, scanner_id VARCHAR)` | Set scanner-level configuration |
| `set_configuration(configuration_name VARCHAR, configuration_value VARCHAR, scanner_package_source_type VARCHAR, scanner_package_source VARCHAR, scanner_package_id VARCHAR, configuration_override BOOLEAN)` | Set package-level configuration (extension-aware). May not be available in all accounts. |
| `set_configuration(configuration_name VARCHAR, configuration_value VARCHAR, scanner_package_source_type VARCHAR, scanner_package_source VARCHAR, scanner_package_id VARCHAR, scanner_id VARCHAR)` | Set scanner-level configuration (extension-aware). May not be available in all accounts. |

**Parameters:**
- `configuration_name` (VARCHAR) — Config type. Standard values: `ENABLED`, `SCHEDULE`, `NOTIFICATION`, `NOTIFICATION_INTEGRATION`. For custom scanner configurations, pass the `CONFIGURATION_NAME` value from `configuration_view` (only valid for scanners where `HAS_CUSTOM_CONFIGURATION = TRUE`).
- `configuration_value` (VARCHAR) — The value to set. For custom configs, always pass as a VARCHAR string (e.g., `'16'`, `'3'`). Check `EXPECTED_TYPE`, `ALLOWED_VALUES`, and `ALLOWED_PATTERN` in `configuration_view` for valid values.
- `scanner_package_id` (VARCHAR) — The package ID
- `scanner_id` (VARCHAR) — The scanner ID (omit for package-level config). **Custom configurations must always be set at scanner scope** — always provide `scanner_id`.
- `configuration_override` (BOOLEAN, default `FALSE`) — When `TRUE`, package-level config overrides scanner-level config
- `scanner_package_source_type` (VARCHAR) — `APPLICATION PACKAGE` or `LISTING` (for extension scanners)
- `scanner_package_source` (VARCHAR) — Name of the application package or listing ID

**Examples:**
```sql
-- Enable a package
CALL snowflake.trust_center.set_configuration('ENABLED', 'TRUE', 'CIS_BENCHMARKS', false);

-- Disable a package
CALL snowflake.trust_center.set_configuration('ENABLED', 'FALSE', 'CIS_BENCHMARKS', false);

-- Enable a specific scanner (parent package must be enabled first)
CALL snowflake.trust_center.set_configuration('ENABLED', 'TRUE', 'CIS_BENCHMARKS', 'CIS_BENCHMARKS_CIS1_4');

-- Set package-level schedule
CALL snowflake.trust_center.set_configuration('SCHEDULE', 'USING CRON 0 6 * * * UTC', 'CIS_BENCHMARKS', false);

-- Set scanner-level notification
CALL snowflake.trust_center.set_configuration('NOTIFICATION', '{"NOTIFY_ADMINS":"TRUE","SEVERITY_THRESHOLD":"CRITICAL","USERS":[]}', 'THREAT_INTELLIGENCE', 'THREAT_INTELLIGENCE_NON_MFA_PERSON_USERS');

-- Set a custom configuration (config name discovered from configuration_view)
CALL snowflake.trust_center.set_configuration(
  'MIN_PASSWORD_LENGTH', '16',
  'cis_benchmarks', 'password_min_length'
);
```

**Notes:**
- Security Essentials package cannot have its `ENABLED` or `SCHEDULE` configuration changed (only `NOTIFICATION` is allowed).
- A scanner cannot be enabled if its parent package is disabled — enable the package first.
- When `NOTIFY_ADMINS` is `TRUE`, the `USERS` array is ignored.
- When `NOTIFY_ADMINS` is `FALSE` and `USERS` is empty, the notification configuration is invalid.
- Notification JSON format: `{"NOTIFY_ADMINS":"TRUE","SEVERITY_THRESHOLD":"CRITICAL","USERS":[]}`

---

### `snowflake.trust_center.unset_configuration`

Removes a user-set configuration, reverting to the default value.

**RBAC:** `trust_center_admin`

**Overloads:**

| Signature | Description |
|-----------|-------------|
| `unset_configuration(configuration_name VARCHAR, scanner_package_id VARCHAR)` | Unset package-level configuration |
| `unset_configuration(configuration_name VARCHAR, scanner_package_id VARCHAR, scanner_id VARCHAR)` | Unset scanner-level configuration |
| `unset_configuration(configuration_name VARCHAR, scanner_package_source_type VARCHAR, scanner_package_source VARCHAR, scanner_package_id VARCHAR)` | Unset package-level config (extension-aware). May not be available in all accounts. |
| `unset_configuration(configuration_name VARCHAR, scanner_package_source_type VARCHAR, scanner_package_source VARCHAR, scanner_package_id VARCHAR, scanner_id VARCHAR)` | Unset scanner-level config (extension-aware). May not be available in all accounts. |

**Parameters:**
- `configuration_name` (VARCHAR) — Config type to unset. Standard values: `ENABLED`, `SCHEDULE`, `NOTIFICATION`, `NOTIFICATION_INTEGRATION`. For custom scanner configurations, pass the `CONFIGURATION_NAME` value from `configuration_view`. Unsetting a custom config reverts the scanner to its built-in default.
- `scanner_package_id` (VARCHAR) — The package ID
- `scanner_id` (VARCHAR) — The scanner ID (omit for package-level)
- `scanner_package_source_type` / `scanner_package_source` (VARCHAR) — For extension scanners

**Example:**
```sql
-- Revert scanner-level schedule to package default
CALL snowflake.trust_center.unset_configuration('SCHEDULE', 'CIS_BENCHMARKS', 'CIS_BENCHMARKS_CIS1_1');

-- Revert a custom configuration to its scanner default
CALL snowflake.trust_center.unset_configuration(
  'MIN_PASSWORD_LENGTH',
  'cis_benchmarks', 'password_min_length'
);
```

---

### `snowflake.trust_center.set_configurations`

Batch set multiple configurations for a scanner package in a single atomic transaction. All configurations are validated upfront (fail-fast) before any are applied.

**RBAC:** `trust_center_admin`

**Signature:** `set_configurations(configurations_json VARCHAR, scanner_package_source_type VARCHAR, scanner_package_source VARCHAR, scanner_package_id VARCHAR, configuration_override BOOLEAN)`

**Parameters:**
- `configurations_json` (VARCHAR) — JSON object mapping configuration names to values. Valid keys: `ENABLED`, `SCHEDULE`, `NOTIFICATION`, `NOTIFICATION_INTEGRATION`. Example: `'{"ENABLED":"TRUE","SCHEDULE":"USING CRON 0 6 * * * UTC"}'`
- `scanner_package_source_type` (VARCHAR) — `APPLICATION PACKAGE` or `LISTING` (for extension scanners). Can be NULL for built-in packages.
- `scanner_package_source` (VARCHAR) — Name of the application package or listing ID. Can be NULL for built-in packages.
- `scanner_package_id` (VARCHAR) — The package ID
- `configuration_override` (BOOLEAN, default `FALSE`) — When `TRUE`, package-level config overrides scanner-level config

**Returns:** VARCHAR — JSON array of results, one per configuration. Each element: `{"config_name":"<NAME>","config_value":"<VALUE>","status":"SUCCESS"}`.

**Examples:**

Prefer `OBJECT_CONSTRUCT` for readability:
```sql
-- Enable a package and set schedule in one call
CALL snowflake.trust_center.set_configurations(
  TO_JSON(OBJECT_CONSTRUCT(
    'ENABLED', 'TRUE',
    'SCHEDULE', 'USING CRON 0 6 * * * UTC'
  )),
  NULL, NULL, 'CIS_BENCHMARKS', false
);

-- Set multiple configs for an extension package
CALL snowflake.trust_center.set_configurations(
  TO_JSON(OBJECT_CONSTRUCT(
    'ENABLED', 'TRUE',
    'NOTIFICATION', TO_JSON(OBJECT_CONSTRUCT(
      'NOTIFY_ADMINS', 'TRUE',
      'SEVERITY_THRESHOLD', 'HIGH',
      'USERS', ARRAY_CONSTRUCT()
    ))
  )),
  'LISTING', '<listing_id>', 'MY_EXTENSION_PACKAGE', false
);
```

Raw JSON string (use only if the customer explicitly requests it):
```sql
-- Enable a package and set schedule in one call
CALL snowflake.trust_center.set_configurations(
  '{"ENABLED":"TRUE","SCHEDULE":"USING CRON 0 6 * * * UTC"}',
  NULL, NULL, 'CIS_BENCHMARKS', false
);

-- Set multiple configs for an extension package
CALL snowflake.trust_center.set_configurations(
  '{"ENABLED":"TRUE","NOTIFICATION":"{\"NOTIFY_ADMINS\":\"TRUE\",\"SEVERITY_THRESHOLD\":\"HIGH\",\"USERS\":[]}"}',
  'LISTING', '<listing_id>', 'MY_EXTENSION_PACKAGE', false
);
```

---

### `snowflake.trust_center.post_finding_activity`

Performs a user activity on a finding: change state, add/edit/delete comments.

**RBAC:** `trust_center_admin`

**Signature:** `post_finding_activity(activity VARCHAR)`

**Parameters:**
- `activity` (VARCHAR) — JSON string describing the activity. Must contain a `type` field.

**Supported activity types:**

```sql
-- Change finding state (to "Fixed", "Open", or "Resolved"/"Muted")
CALL snowflake.trust_center.post_finding_activity('{"type":"state_change","finding_identifier":"THREAT_INTELLIGENCE.THREAT_INTELLIGENCE_NON_MFA_PERSON_USERS.THREAT_INTELLIGENCE_NON_MFA_PERSON_USERS.Critical","state":"Fixed"}');

-- Add a comment
CALL snowflake.trust_center.post_finding_activity('{"type":"comment_addition","finding_identifier":"<FINDING_IDENTIFIER>","comment":"Investigating this issue"}');

-- Edit a comment
CALL snowflake.trust_center.post_finding_activity('{"type":"comment_alteration","finding_identifier":"<FINDING_IDENTIFIER>","comment_id":123,"comment":"Updated comment text"}');

-- Delete a comment
CALL snowflake.trust_center.post_finding_activity('{"type":"comment_deletion","finding_identifier":"<FINDING_IDENTIFIER>","comment_id":123}');
```

**Notes:**
- Currently limited to Vulnerability-type findings only.
- For backwards compatibility, `event_id` can be used instead of `finding_identifier`, but `finding_identifier` is preferred.

---

### `snowflake.trust_center.get_user_email_verification_status`

Fetches email verification status for specified users. Used to validate notification recipients.

**RBAC:** `trust_center_admin`

**Signature:** `get_user_email_verification_status(user_list VARCHAR)`

**Parameters:**
- `user_list` (VARCHAR) — JSON array of user names. User names are case-insensitive by default. Use escaped quotes for case-sensitive names: `'["user1", "\"CaseSensitiveUser\""]'`

---

### `snowflake.trust_center.register_extension`

Registers a Trust Center Extension (from a Native App or Listing).

**RBAC:** `trust_center_admin` (may not be available in all accounts)

**Signature:** `register_extension(source_type VARCHAR, source VARCHAR, extension_name VARCHAR)`

**Parameters:**
- `source_type` (VARCHAR) — `APPLICATION PACKAGE` or `LISTING`
- `source` (VARCHAR) — Name of the application package or the global listing ID
- `extension_name` (VARCHAR) — Name of the Extension Native App instance. Cannot be `SNOWFLAKE`.

---

### `snowflake.trust_center.deregister_extension`

Deregisters a Trust Center Extension by its ID.

**RBAC:** `trust_center_admin` (may not be available in all accounts)

**Signature:** `deregister_extension(extension_id NUMBER)`

**Parameters:**
- `extension_id` (NUMBER) — The ID of the extension (from `extensions.ID`)

---

### `snowflake.trust_center.get_trusted_extensions`

Returns a table of trusted extension listing IDs configured for the account.

**RBAC:** `trust_center_admin`, `trust_center_viewer`

**Signature:** `get_trusted_extensions()`

**Returns:** `TABLE(listing_id VARCHAR)`

---

### `snowflake.trust_center.set_account_notification_enabled`

Enables or disables an account-level notification type (e.g., MFA readiness notifications, findings digest).

**RBAC:** `trust_center_admin`, `trust_center_viewer`

**Signature:** `set_account_notification_enabled(notification_type VARCHAR, is_enabled BOOLEAN)`

**Parameters:**
- `notification_type` (VARCHAR) — One of: `MFA_READINESS`, `EXTENSION_AVAILABLE_IN_MARKETPLACE`, `FINDINGS_DIGEST`
- `is_enabled` (BOOLEAN) — `TRUE` to enable, `FALSE` to disable

---

### `snowflake.trust_center.set_org_package_configuration`

Sets organization-level configuration for a scanner package. Organization-level config is applied across all accounts in the organization.

**RBAC:** `trust_center_admin` (may not be available in all accounts)

**Signature:** `set_org_package_configuration(provider_id VARCHAR, scanner_package_id VARCHAR, enabled BOOLEAN, schedule VARCHAR, notification VARCHAR)`

**Parameters:**
- `provider_id` (VARCHAR) — The provider ID (e.g., `SNOWFLAKE` for built-in packages, or a listing ID for extensions)
- `scanner_package_id` (VARCHAR) — The package ID
- `enabled` (BOOLEAN) — Whether the package should be enabled
- `schedule` (VARCHAR) — Cron schedule for the package, or NULL to leave unchanged
- `notification` (VARCHAR) — Notification configuration JSON, or NULL to leave unchanged

---

### `snowflake.trust_center.set_org_scanner_configuration`

Sets organization-level configuration for a specific scanner within a package.

**RBAC:** `trust_center_admin` (may not be available in all accounts)

**Signature:** `set_org_scanner_configuration(provider_id VARCHAR, scanner_package_id VARCHAR, scanner_id VARCHAR, enabled BOOLEAN, schedule VARCHAR, notification VARCHAR)`

**Parameters:**
- `provider_id` (VARCHAR) — The provider ID
- `scanner_package_id` (VARCHAR) — The package ID
- `scanner_id` (VARCHAR) — The scanner ID
- `enabled` (BOOLEAN) — Whether the scanner should be enabled
- `schedule` (VARCHAR) — Cron schedule, or NULL to leave unchanged
- `notification` (VARCHAR) — Notification configuration JSON, or NULL to leave unchanged

---

### `snowflake.trust_center.unset_org_package_configuration`

Removes organization-level configuration for a scanner package.

**RBAC:** `trust_center_admin` (may not be available in all accounts)

**Signature:** `unset_org_package_configuration(provider_id VARCHAR, scanner_package_id VARCHAR)`

**Parameters:**
- `provider_id` (VARCHAR) — The provider ID
- `scanner_package_id` (VARCHAR) — The package ID

---

### `snowflake.trust_center.unset_org_scanner_configuration`

Removes organization-level configuration for a specific scanner.

**RBAC:** `trust_center_admin` (may not be available in all accounts)

**Signature:** `unset_org_scanner_configuration(provider_id VARCHAR, scanner_package_id VARCHAR, scanner_id VARCHAR)`

**Parameters:**
- `provider_id` (VARCHAR) — The provider ID
- `scanner_package_id` (VARCHAR) — The package ID
- `scanner_id` (VARCHAR) — The scanner ID

---

### `snowflake.trust_center.submit_async_job`

Submits an asynchronous job for background processing. Returns a job ID that can be tracked via the `async_jobs` view.

**RBAC:** `trust_center_admin`

**Signature:** `submit_async_job(job_type VARCHAR, job_args VARCHAR)`

**Parameters:**
- `job_type` (VARCHAR) — The type of async job. Currently only `SET_PACKAGE_CONFIGURATION` is supported.
- `job_args` (VARCHAR) — JSON string with job-specific arguments. For `SET_PACKAGE_CONFIGURATION`:
  - **Required fields:**
    - `scanner_package_id` (VARCHAR) — The package ID
    - `configurations_json` (VARCHAR/OBJECT) — Configuration key-value pairs to apply
  - **Optional fields:**
    - `scanner_package_source_type` (VARCHAR) — `APPLICATION PACKAGE` or `LISTING`
    - `scanner_package_source` (VARCHAR) — Name of the application package or listing ID
    - `configuration_override` (BOOLEAN) — Whether package config overrides scanner config

**Returns:** VARCHAR — The job ID (UUID v4). Use this ID to track job status in the `async_jobs` view.

**Examples:**

Prefer `OBJECT_CONSTRUCT` for readability:
```sql
-- Submit an async job to enable a package with a schedule
CALL snowflake.trust_center.submit_async_job(
  'SET_PACKAGE_CONFIGURATION',
  TO_JSON(OBJECT_CONSTRUCT(
    'scanner_package_id', 'CIS_BENCHMARKS',
    'configurations_json', OBJECT_CONSTRUCT(
      'ENABLED', 'TRUE',
      'SCHEDULE', 'USING CRON 0 6 * * * UTC'
    )
  ))
);

-- Track job status
SELECT * FROM snowflake.trust_center.async_jobs WHERE job_id = '<returned_job_id>';
```

Raw JSON string (use only if the customer explicitly requests it):
```sql
CALL snowflake.trust_center.submit_async_job(
  'SET_PACKAGE_CONFIGURATION',
  '{"scanner_package_id":"CIS_BENCHMARKS","configurations_json":{"ENABLED":"TRUE","SCHEDULE":"USING CRON 0 6 * * * UTC"}}'
);
```

**Notes:**
- Only one active job (status `PENDING` or `PROCESSING`) is allowed per scanner package per job type. Submitting a duplicate raises an error — wait for the existing job to complete first.
- The job is immediately triggered for processing after insertion, but execution is asynchronous.
- Job status progression: `PENDING` -> `PROCESSING` -> `COMPLETED` or `FAILED`.
- Use the `async_jobs` view to monitor status. The `scanner_packages` view also exposes `LATEST_ASYNC_JOB_ID`, `LATEST_ASYNC_JOB_STATUS`, and `LATEST_ASYNC_JOB_ERROR_MESSAGE` columns.

---

## Scanner Packages

### First-Party Packages (pre-installed)

| Package | Description | Default Schedule | Schedule Configurable? | Cost |
|---------|-------------|-----------------|----------------------|------|
| Security Essentials | Snowflake-recommended checks | Monthly | No (fixed, but on-demand runs can be triggered) | Default monthly run is free. Ad-hoc runs incur credits. |
| CIS Benchmarks | Snowflake CIS Benchmark scanners | Daily | Yes | Credits consumed per scan |
| Threat Intelligence | Detection scanners for unauthorized access risks | Daily/event-driven | Yes | Credits consumed per scan |
| AI Security | AI-related security configurations and usage monitoring | Daily | Yes | Credits consumed per scan |

### Extension-Based Packages

These come from the Snowflake Trust Center extension and include packages such as Roles, Secrets & Privileged Access, Sharing, Users, Authentication, Configuration, and Application Security. Their scanner IDs are not in the first-party mapping below — always query the views to look up their IDs:

```sql
SELECT s.ID AS scanner_id, s.NAME, s.SCANNER_PACKAGE_ID, sp.NAME AS package_name, sp.STATE AS package_state
FROM snowflake.trust_center.scanners s
LEFT JOIN snowflake.trust_center.scanner_packages sp ON s.SCANNER_PACKAGE_ID = sp.ID
WHERE s.NAME ILIKE '%<search term>%' OR s.SHORT_DESCRIPTION ILIKE '%<search term>%';
```

### First-Party Scanner ID Mapping

| Scanner Id | Scanner Name | Severity | Type |
|------------|--------------|----------|------|
| threat_intelligence_non_mfa_person_users | Human User MFA Readiness | Critical | Scheduled |
| threat_intelligence_password_service_users | Service User Passwordless Readiness | Critical | Scheduled |
| threat_intelligence_users_with_high_job_errors | Users with High Job Errors | High | Scheduled |
| threat_intelligence_users_with_high_authn_failures | Users with High Volume of Authentication Failures | High | Scheduled |
| threat_intelligence_users_with_admin_privileges | Users with Admin Privileges | High | Scheduled |
| threat_intelligence_login_protection | Login Protection | High | Event-Driven |
| threat_intelligence_unusual_app_used_in_session | Users with Unusual Application Used in Sessions | Medium | Scheduled |
| threat_intelligence_entities_with_long_running_queries | Users with Long-Running Queries | Medium | Scheduled |
| threat_intelligence_authentication_policy_changes | Authentication Policy Changes | Low | Event-Driven |
| threat_intelligence_sensitive_parameter_protection | Sensitive Parameter Protection | High | Event-Driven |
| threat_intelligence_dormant_user_login | Dormant User Login | Medium | Event-Driven |
| threat_intelligence_sensitive_policy_changes | Sensitive Policy Changes | Low | Event-Driven |
| security_essentials_strong_auth_person_users_readiness | PERSON User Strong Authentication Readiness | High/Medium | Scheduled |
| security_essentials_strong_auth_legacy_service_users_readiness | LEGACY SERVICE User Strong Authentication Readiness | High/Medium | Scheduled |
| security_essentials_cis1_4 | 1.4 | Critical | Scheduled |
| security_essentials_cis3_1 | 3.1 | Critical | Scheduled |
| security_essentials_client_security | Client Application Security Risks | Critical | Scheduled |
| cis_benchmarks_cis1_1 | 1.1 — Ensure SSO is configured | High | Scheduled |
| cis_benchmarks_cis1_2 | 1.2 — Ensure SCIM integration is configured | Medium | Scheduled |
| cis_benchmarks_cis1_3 | 1.3 — Ensure password is unset for SSO users | High | Scheduled |
| cis_benchmarks_cis1_4 | 1.4 — Ensure MFA is on for all human users | Critical | Scheduled |
| cis_benchmarks_cis1_5 | 1.5 — Ensure min password length >= 14 | Medium | Scheduled |
| cis_benchmarks_cis1_6 | 1.6 — Ensure legacy service users use key pair auth | High | Scheduled |
| cis_benchmarks_cis1_7 | 1.7 — Ensure key pair rotation every 180 days | Medium | Scheduled |
| cis_benchmarks_cis1_8 | 1.8 — Ensure inactive users (90 days) are disabled | Medium | Scheduled |
| cis_benchmarks_cis1_9 | 1.9 — Ensure idle session timeout <= 15 min for admins | Low | Scheduled |
| cis_benchmarks_cis1_10 | 1.10 — Limit ACCOUNTADMIN/SECURITYADMIN users | Medium | Scheduled |
| cis_benchmarks_cis1_11 | 1.11 — Ensure ACCOUNTADMIN users have email | Low | Scheduled |
| cis_benchmarks_cis1_12 | 1.12 — Ensure no users default to admin roles | Low | Scheduled |
| cis_benchmarks_cis1_13 | 1.13 — Ensure admin roles not granted to custom roles | Medium | Scheduled |
| cis_benchmarks_cis1_14 | 1.14 — Ensure tasks not owned by admin roles | High | Scheduled |
| cis_benchmarks_cis1_15 | 1.15 — Ensure tasks don't run with admin privileges | High | Scheduled |
| cis_benchmarks_cis1_16 | 1.16 — Ensure stored procs not owned by admin roles | High | Scheduled |
| cis_benchmarks_cis1_17 | 1.17 — Ensure stored procs don't run with admin privileges | High | Scheduled |
| cis_benchmarks_cis1_18 | 1.18 — Ensure PATs require network policies | Medium | Scheduled |
| cis_benchmarks_cis2_1 | 2.1 — Monitor ACCOUNTADMIN/SECURITYADMIN role grants | Medium | Scheduled |
| cis_benchmarks_cis2_2 | 2.2 — Monitor MANAGE GRANTS privilege grants | Low | Scheduled |
| cis_benchmarks_cis2_4 | 2.4 — Monitor password sign-in without MFA | Medium | Scheduled |
| cis_benchmarks_cis2_5 | 2.5 — Monitor security integration changes | Low | Scheduled |
| cis_benchmarks_cis2_6 | 2.6 — Monitor network policy changes | Low | Scheduled |
| cis_benchmarks_cis2_7 | 2.7 — Monitor SCIM token creation | Low | Scheduled |
| cis_benchmarks_cis2_8 | 2.8 — Monitor new share exposures | Low | Scheduled |
| cis_benchmarks_cis2_9 | 2.9 — Monitor unsupported client sessions | Low | Scheduled |
| cis_benchmarks_cis3_1 | 3.1 — Ensure account-level network policy | Critical | Scheduled |
| cis_benchmarks_cis3_2 | 3.2 — Ensure service account network policies | Medium | Scheduled |
| cis_benchmarks_cis4_1 | 4.1 — Ensure yearly rekeying enabled | Low | Scheduled |
| cis_benchmarks_cis4_2 | 4.2 — Ensure AES 256-bit for internal stages | Low | Scheduled |
| cis_benchmarks_cis4_3 | 4.3 — Ensure retention >= 90 days for critical data | Low | Scheduled |
| cis_benchmarks_cis4_4 | 4.4 — Ensure MIN_DATA_RETENTION >= 7 days | Low | Scheduled |
| cis_benchmarks_cis4_5 | 4.5 — Ensure REQUIRE_STORAGE_INTEGRATION for stage creation | Medium | Scheduled |
| cis_benchmarks_cis4_6 | 4.6 — Ensure REQUIRE_STORAGE_INTEGRATION for stage operation | Medium | Scheduled |
| cis_benchmarks_cis4_7 | 4.7 — Ensure all external stages have storage integrations | Medium | Scheduled |
| cis_benchmarks_cis4_8 | 4.8 — Ensure PREVENT_UNLOAD_TO_INLINE_URL = true | Medium | Scheduled |
| cis_benchmarks_cis4_9 | 4.9 — Ensure Tri-Secret Secure enabled | Medium | Scheduled |
| cis_benchmarks_cis4_10 | 4.10 — Ensure data masking for sensitive data | Low | Scheduled |
| cis_benchmarks_cis4_11 | 4.11 — Ensure row-access policies for sensitive data | Low | Scheduled |
| ai_security_cortex_search_service_privileged_roles | Cortex Search Service Privileged Roles | High | Scheduled |
| ai_security_cortex_code_usage_with_pat | Cortex Code PAT Usage Without Role Restriction and Network Policy | High | Scheduled |
| ai_security_agent_sensitive_data_access | Sensitive Data Accessed by Agent | High | Scheduled |
| ai_security_advanced_prompt_injection_guardrail | Cortex AI Guardrails (Advanced Prompt Injection Guardrail) are not enabled | High | Scheduled |
