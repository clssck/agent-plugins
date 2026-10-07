---
name: trust-center-api-management
description: Use for **ALL** Trust Center scanner management requests including: enabling/disabling scanners or packages, changing notification settings, modifying run schedules, or triggering scanner executions. **Always query current state before making changes.**
---

## Prerequisites

**MANDATORY: Load** [references/trust-center-api.md](../references/trust-center-api.md) — contains all Trust Center views, columns, stored procedure signatures, and the first-party scanner ID mapping.

## Instructions

When the user requests to manage Trust Center scanners or scanner packages, use the SQL API documented in the reference file.

**⚠️ IMPORTANT: Trust Center has a full SQL API for ALL scanner management operations.** This includes enabling/disabling scanners, enabling/disabling packages, changing schedules, configuring notifications, and triggering scanner runs. NEVER tell the user that scanner management must be done through the UI or that no API exists.

**⚠️ Always use `SCANNER_PACKAGE_ID` and `SCANNER_ID` column values from the views, never display names.** For example, use the `ID` column value from `snowflake.trust_center.scanner_packages`, not the `NAME` column.

---

### Scanner Package and Scanner Execution

Runs a scanner package or individual scanner. If a scanner package is executed, all scanners that are enabled in it will be executed. Packages or scanners that do not exist will fail if a user tries to execute them.

To execute an entire scanner package:
```sql
CALL snowflake.trust_center.execute_scanner('<SCANNER_PACKAGE_ID>');
```

To execute a specific scanner:
```sql
CALL snowflake.trust_center.execute_scanner('<SCANNER_PACKAGE_ID>', '<SCANNER_ID>');
```

---

### Scanner Package Enablement

Enables an entire scanner package and all scanners within it. Free scanner packages are enabled by default. Enabling a paid package will incur cost to the account.

```sql
CALL snowflake.trust_center.set_configuration('ENABLED', 'TRUE', '<PACKAGE_ID>');
```

---

### Scanner Package Disablement

Disables an entire scanner package. Disabling a paid package will stop future costs.


```sql
CALL snowflake.trust_center.set_configuration('ENABLED', 'FALSE', '<PACKAGE_ID>');
```

**Note**: The Security Essentials package is free and cannot be disabled. If the user requests this, inform them and check current Snowflake documentation for alternatives.

---

### Scanner Specific Enablement

Enables a specific scanner within a scanner package. Free scanners are typically enabled by default.

**⚠️ Prerequisite: The scanner's parent package must be enabled first.** A scanner cannot be enabled if its parent package is disabled. Always check the package state before enabling a scanner:

```sql
SELECT id, name, state
FROM snowflake.trust_center.scanner_packages
WHERE id = '<PACKAGE_ID>';
```

If the package `STATE` is not `TRUE`, enable the package first using Scanner Package Enablement (above), then enable the individual scanner:

```sql
CALL snowflake.trust_center.set_configuration('ENABLED', 'TRUE', '<PACKAGE_ID>', '<SCANNER_ID>');
```

---

### Scanner Specific Disablement

Disables a specific scanner within a scanner package. Disabling a paid scanner will stop future costs for that scanner.


```sql
CALL snowflake.trust_center.set_configuration('ENABLED', 'FALSE', '<PACKAGE_ID>', '<SCANNER_ID>');
```

**Note**: Any Security Essentials scanner cannot be disabled. If the user requests this, inform them and check current Snowflake documentation for alternatives.

---

### Batch Configuration (Preferred for Multiple Changes)

When the user wants to set multiple configurations at once (e.g., enable + schedule, or enable + schedule + notification), **prefer `set_configurations`** (plural) over multiple sequential `set_configuration` calls. This applies changes atomically — all succeed or all fail.

```sql
CALL snowflake.trust_center.set_configurations(
  TO_JSON(OBJECT_CONSTRUCT(
    'ENABLED', 'TRUE',
    'SCHEDULE', 'USING CRON 0 6 * * * UTC',
    'NOTIFICATION', TO_JSON(OBJECT_CONSTRUCT(
      'NOTIFY_ADMINS', 'TRUE',
      'SEVERITY_THRESHOLD', 'CRITICAL',
      'USERS', ARRAY_CONSTRUCT()
    ))
  )),
  NULL, NULL, '<PACKAGE_ID>', false
);
```

- Valid keys: `ENABLED`, `SCHEDULE`, `NOTIFICATION`, `NOTIFICATION_INTEGRATION`
- For built-in packages, pass `NULL, NULL` for source_type and source
- For extension packages, pass `'LISTING', '<listing_id>'` or `'APPLICATION PACKAGE', '<app_package_name>'`
- This is package-level only — use individual `set_configuration` calls for scanner-level config

---

### Scanner Package or Scanner-level Schedule Modification

Updates the package or scanner CRON schedule. If a package's schedule is updated, all scanners within it will be updated. Convert natural language date descriptions to CRON format.

For package-level schedule:
```sql
CALL snowflake.trust_center.set_configuration('SCHEDULE', 'USING CRON <SCHEDULE> UTC', '<PACKAGE_ID>', false);
```

For scanner-level schedule:
```sql
CALL snowflake.trust_center.set_configuration('SCHEDULE', 'USING CRON <SCHEDULE> UTC', '<PACKAGE_ID>', '<SCANNER_ID>');
```

**Note**: The Security Essentials package and contained scanners have a fixed schedule that cannot be modified. If the user requests this, inform them and check current Snowflake documentation for alternatives.

---

### Scanner Package or Scanner-level Notification Modification

Updates the package or scanner email notification configuration. If a package's notification is updated, all scanners within it will be updated.

#### Configuration Format

The notification configuration must follow this JSON format:
```json
{"NOTIFY_ADMINS":"TRUE","SEVERITY_THRESHOLD":"CRITICAL","USERS":[]}
```

- `SEVERITY_THRESHOLD`: One of `"CRITICAL"`, `"HIGH"`, `"MEDIUM"`, `"LOW"`
- `NOTIFY_ADMINS`: One of `"TRUE"`, `"FALSE"`
- `USERS`: Array of valid users from `snowflake.trust_center.users` view. **Only add users explicitly requested by the user.**

- When `NOTIFY_ADMINS` is true, users array even with value, will be ignored
- When `NOTIFY_ADMINS` is false and users is empty, this is considered invalid configuration
- An empty JSON string `{}` indicates no email notification for this package/scanner

#### Query Current Configuration

For a package:
```sql
SELECT notification 
FROM snowflake.trust_center.scanner_packages
WHERE id = '<SCANNER_PACKAGE_ID>';
```

For a scanner:
```sql
SELECT running_configuration_value
FROM snowflake.trust_center.configuration_view
WHERE configuration_name = 'NOTIFICATION'
  AND scanner_package_id = '<SCANNER_PACKAGE_ID>'
  AND scanner_id = '<SCANNER_ID>';
```

#### Apply Notification Changes

For package-level notification:
```sql
CALL snowflake.trust_center.set_configuration('NOTIFICATION', '<CONFIGURATION_JSON>', '<PACKAGE_ID>', false);
```

For scanner-level notification:
```sql
CALL snowflake.trust_center.set_configuration('NOTIFICATION', '<CONFIGURATION_JSON>', '<PACKAGE_ID>', '<SCANNER_ID>');
```

---

### Scanner Package or Scanner-level Notification Integration (Webhook) Configuration

`NOTIFICATION_INTEGRATION` is a separate configuration type from `NOTIFICATION` (email). It enables sending scanner findings to external systems (PagerDuty, AWS SNS, etc.) via outbound notification integrations. A package or scanner can have both email notifications and webhook notification integrations configured independently.

#### Prerequisites — Creating and Granting the Integration

For the underlying CREATE NOTIFICATION INTEGRATION syntax (webhook, AWS SNS, Azure Event Grid, etc.), load and follow [integrations/create-notification-integration/SKILL.md](../../integrations/create-notification-integration/SKILL.md).

**⚠️ Trust Center default for `TYPE = WEBHOOK`.** Use the linked skill for syntax, parameter names, and access-control rules, but **always propose the Trust-Center default `WEBHOOK_BODY_TEMPLATE` shown below as the initial value** — do **not** use the linked skill's generic PagerDuty/Slack/Teams body templates (which wrap `SNOWFLAKE_WEBHOOK_MESSAGE` in quotes as a string). The Trust Center emits findings as a **structured JSON object**, so `SNOWFLAKE_WEBHOOK_MESSAGE` must appear **without surrounding quotes** in order to be injected as a nested object rather than a stringified blob.

**Customer override is allowed.** The customer can change the `WEBHOOK_BODY_TEMPLATE` to anything their destination requires (different PagerDuty fields, a Slack block payload, a custom internal schema, etc.) — but you must still **present the default below first** so the integration is immediately functional, and only customize on explicit customer request. When customizing, preserve the key invariants: `SNOWFLAKE_WEBHOOK_MESSAGE` stays unquoted wherever the finding object should land, and `SNOWFLAKE_WEBHOOK_SECRET` stays quoted inside string fields.

**Default recommended template — PagerDuty:**

```sql
CREATE OR REPLACE SECRET <db>.<schema>.integration_key
  TYPE = GENERIC_STRING
  SECRET_STRING = '<pagerduty_integration_key>';

CREATE OR REPLACE NOTIFICATION INTEGRATION <integration_name>
  TYPE = WEBHOOK
  ENABLED = TRUE
  WEBHOOK_URL = 'https://events.pagerduty.com/v2/enqueue'
  WEBHOOK_SECRET = <db>.<schema>.integration_key
  WEBHOOK_BODY_TEMPLATE = '{
    "routing_key": "SNOWFLAKE_WEBHOOK_SECRET",
    "event_action": "trigger",
    "payload": {
        "summary": "Snowflake Trust Center Scanner Finding",
        "source": "Snowflake",
        "severity": "critical",
        "custom_details": SNOWFLAKE_WEBHOOK_MESSAGE
    }
  }'
  WEBHOOK_HEADERS = ('Content-Type'='application/json');
```

Key points for Trust Center webhook templates:

- `SNOWFLAKE_WEBHOOK_MESSAGE` is placed as a **bare JSON value** (no quotes) so the full Trust Center finding object (scanner_name, findings array, etc. — see payload schema below) is injected as a nested object. Preserve this in any customer-customized template.
- `SNOWFLAKE_WEBHOOK_SECRET` remains inside quotes where it substitutes into a string field (e.g., `routing_key`, auth headers).
- `summary`, `source`, and `severity` in the PagerDuty template are hardcoded descriptors for the alert itself; the real finding severity/details travel inside `custom_details`. Customers can re-map these (e.g., derive `severity` from the finding, change the `summary` string) at their discretion.
- `Content-Type: application/json` header is required whenever `WEBHOOK_BODY_TEMPLATE` is set.

The Trust Center notification payload injected into `SNOWFLAKE_WEBHOOK_MESSAGE` has the following shape:

```json
{
  "scanner_name": "<scanner_name>",
  "scanner_package_name": "<scanner_package_name>",
  "scanner_package_short_description": "<scanner_package_descr>",
  "scanner_short_description": "<scanner_descr>",
  "scanner_finish_time_unix_timestamp_ms": "<scanner_finish_time>",
  "scanner_finish_time_formatted": "<scanner_finish_time_as_date>",
  "findings": [
    {
      "event_id": "<event_id>",
      "finding_identifier": "<finding_identifier>",
      "finding_severity": "<finding_severity>",
      "at_risk_entities": [ { "entity_detail": {}, "entity_id": "...", "entity_name": "...", "entity_object_type": "..." } ],
      "total_at_risk_count": "<total_at_risk_count>",
      "metadata": {},
      "note": "The list of at-risk entities has been truncated"
    }
  ]
}
```

`at_risk_entities`, `total_at_risk_count`, and `metadata` are only populated when `INCLUDE_AT_RISK_ENTITIES_AND_FINDING_METADATA` is `TRUE` on the scanner's `NOTIFICATION_INTEGRATION` configuration (see below). Use this schema to design custom templates for other webhook destinations (Slack, Teams, custom HTTPS endpoint).

After creating the integration, the following grants are required so that the Snowflake Trust Center application can access the integration and any associated secrets on behalf of the account.

**✋ STOPPING POINT — Do NOT execute these grant commands without the user's explicit approval.** Present the grants to the user and explain:
- `GRANT USAGE ON INTEGRATION` allows the Trust Center application to send webhook payloads through the named notification integration.
- `GRANT READ ON SECRET` (only needed if the integration uses a secret, e.g., a PagerDuty routing key) allows the application to read the secret value at runtime to authenticate with the external endpoint.
- `GRANT USAGE ON DATABASE/SCHEMA` gives the application access to the database and schema where the secret is stored.

Wait for the user to confirm before running any of these statements.

```sql
-- Required: grant USAGE on the integration to the Snowflake application
GRANT USAGE ON INTEGRATION <integration_name> TO APPLICATION snowflake;

-- If the integration uses a secret (e.g., PagerDuty webhook key):
GRANT READ ON SECRET <db>.<schema>.<secret_name> TO APPLICATION snowflake;
GRANT USAGE ON DATABASE <db> TO APPLICATION snowflake;
GRANT USAGE ON SCHEMA <db>.<schema> TO APPLICATION snowflake;
```

#### Configuration Format

The configuration value is an array of JSON objects cast to string. Each object contains:

- `INTEGRATION_NAME` (required) — name of the notification integration created above
- `SEVERITY_THRESHOLD` (required) — minimum severity to trigger the webhook: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`
- `INCLUDE_AT_RISK_ENTITIES_AND_FINDING_METADATA` (optional) — `'TRUE'` or `'FALSE'` (default `'FALSE'`)

> **⚠️ WARNING — `INCLUDE_AT_RISK_ENTITIES_AND_FINDING_METADATA`**
>
> When set to `'TRUE'`, at-risk entity details and finding metadata are included in the webhook payload. This data may contain **sensitive information** such as user names, IP addresses, role assignments, and other account-specific details. Because this data **leaves the Snowflake boundary** and is sent to the configured webhook destination, only enable this if you are comfortable with such metadata being transmitted to your external endpoint. Ensure your webhook destination meets your organization's data handling and security requirements.

**✋ STOPPING POINT — You MUST ask the user** whether they want to include at-risk entity details and finding metadata in the webhook payload before generating the configuration. Explain that enabling `INCLUDE_AT_RISK_ENTITIES_AND_FINDING_METADATA` sends sensitive data (user names, IPs, role assignments) outside Snowflake to their webhook endpoint, and ask them to confirm. **Do NOT silently default to `'FALSE'`** — always surface this choice explicitly.

#### Query Current Configuration

```sql
SELECT running_configuration_value
FROM snowflake.trust_center.configuration_view
WHERE configuration_name = 'NOTIFICATION_INTEGRATION'
  AND scanner_package_id = '<PACKAGE_ID>';
```

To check a specific scanner's configuration, add the scanner filter:

```sql
SELECT running_configuration_value
FROM snowflake.trust_center.configuration_view
WHERE configuration_name = 'NOTIFICATION_INTEGRATION'
  AND scanner_package_id = '<PACKAGE_ID>'
  AND scanner_id = '<SCANNER_ID>';
```

#### Apply Notification Integration Changes

For package-level configuration:
```sql
CALL snowflake.trust_center.set_configuration(
  'NOTIFICATION_INTEGRATION',
  ARRAY_CONSTRUCT(
    OBJECT_CONSTRUCT(
      'SEVERITY_THRESHOLD', 'HIGH',
      'INTEGRATION_NAME', 'MY_PAGERDUTY_INT'
    )
  )::VARCHAR,
  '<PACKAGE_ID>'
);
```

For scanner-level configuration:
```sql
CALL snowflake.trust_center.set_configuration(
  'NOTIFICATION_INTEGRATION',
  ARRAY_CONSTRUCT(
    OBJECT_CONSTRUCT(
      'SEVERITY_THRESHOLD', 'CRITICAL',
      'INTEGRATION_NAME', 'MY_PAGERDUTY_INT',
      'INCLUDE_AT_RISK_ENTITIES_AND_FINDING_METADATA', 'TRUE'
    )
  )::VARCHAR,
  '<PACKAGE_ID>',
  '<SCANNER_ID>'
);
```

#### Troubleshooting Webhook Delivery

Use the `notification_history` view and `NOTIFICATION_HISTORY()` function to debug delivery issues:

```sql
SELECT * FROM snowflake.trust_center.notification_history ORDER BY sent_on DESC;
SELECT * FROM TABLE(snowflake.information_schema.notification_history());
```

---

### Async Job Submission

For long-running configuration changes, use `submit_async_job` to queue the operation and return immediately with a job ID. Useful when the user wants non-blocking execution.

**Supported job types:**

| `job_type` | Description | `job_args` keys |
|------------|-------------|-----------------|
| `SET_PACKAGE_CONFIGURATION` | Asynchronously apply one or more configurations (ENABLED, SCHEDULE, NOTIFICATION, NOTIFICATION_INTEGRATION) to a scanner package | `scanner_package_id` (required), `configurations_json` (required), `scanner_package_source_type`, `scanner_package_source`, `configuration_override` |

```sql
CALL snowflake.trust_center.submit_async_job(
  'SET_PACKAGE_CONFIGURATION',
  TO_JSON(OBJECT_CONSTRUCT(
    'scanner_package_id', '<PACKAGE_ID>',
    'configurations_json', OBJECT_CONSTRUCT(
      'ENABLED', 'TRUE',
      'SCHEDULE', 'USING CRON 0 6 * * * UTC'
    )
  ))
);
```

Track job status:
```sql
SELECT * FROM snowflake.trust_center.async_jobs WHERE job_id = '<returned_job_id>';
```

- Only one active job per package per job type. Wait for existing jobs to complete before submitting another.
- If a job reaches FAILED status, read ERROR_MESSAGE from the async_jobs view to diagnose the failure.

---

### Scanner Custom Configurations (Threshold / Parameter Tuning)

Some scanners expose configurable parameters that let you tune scanner behavior for your environment without disabling the scanner. Custom configurations are scanner-defined — you discover what's available by querying the views, not from a fixed list.

**This is a Public Preview feature.**

---

#### When to Use Custom Configurations (vs. Other Options)

| Situation | Recommended Action |
|-----------|-------------------|
| User wants to check whether a scanner is using default or custom settings | Inspect `configuration_view` (read-only, no confirmation needed) |
| Scanner fires too aggressively for this workload (threshold too tight) | Raise the threshold via custom configuration |
| Scanner never fires even though issues exist (threshold too loose) | Lower the threshold via custom configuration |
| One specific finding is a false positive, not the scanner generally | Mute that finding (see Finding State Management section below) |
| Scanner logic is fundamentally wrong for the environment | Disable the scanner |

---

#### Inspecting Current Configuration (Read-Only)

When a user asks whether a scanner is using default or custom settings — e.g., "was this finding generated with the default threshold?" or "has this scanner been customized?" — query `configuration_view` directly. No confirmation needed; this is a read-only inspection.

```sql
SELECT
  CONFIGURATION_NAME,
  RUNNING_CONFIGURATION_VALUE,
  SET_CONFIGURATION_VALUE,
  SCANNER_CONFIGURATION_VALUE,
  DEFAULT_SCANNER_VALUE,
  DESCRIPTION
FROM snowflake.trust_center.configuration_view
WHERE SCANNER_PACKAGE_ID = '<SCANNER_PACKAGE_ID>'
  AND SCANNER_ID = '<SCANNER_ID>';
```

**How to interpret the results:**

- `SET_CONFIGURATION_VALUE` is `NULL` → no override has been set; the scanner is running on its **default** configuration
- `SET_CONFIGURATION_VALUE` is non-null → a **custom value** has been applied, overriding the default
- `DEFAULT_SCANNER_VALUE` shows what the out-of-box default is for comparison
- `RUNNING_CONFIGURATION_VALUE` shows the value actually in use right now (reflects the task state cache)
- `SCANNER_CONFIGURATION_VALUE` shows any value set explicitly at the scanner level by the user

If the user doesn't know the scanner ID, first look it up:

```sql
SELECT SCANNER_PACKAGE_ID, ID AS SCANNER_ID, NAME
FROM snowflake.trust_center.scanners
WHERE NAME ILIKE '%<search_term>%'
  AND HAS_CUSTOM_CONFIGURATION = TRUE;
```

Present the results to the user, calling out clearly whether each parameter is at its default or has been customized.

---

#### Changing Configuration (Write Workflow)

##### Step 1: Identify which scanners support custom configurations

```sql
SELECT SCANNER_PACKAGE_ID, ID AS SCANNER_ID, NAME, HAS_CUSTOM_CONFIGURATION
FROM snowflake.trust_center.scanners
WHERE HAS_CUSTOM_CONFIGURATION = TRUE;
```

Use the `SCANNER_PACKAGE_ID` and `SCANNER_ID` values from this query in all subsequent calls. Never use display names.

##### Step 2: Inspect available config names, current values, and constraints

```sql
SELECT
  CONFIGURATION_NAME,
  SET_CONFIGURATION_VALUE,
  COALESCE(DEFAULT_SCANNER_VALUE, DEFAULT_SCANNER_PACKAGE_VALUE) AS DEFAULT_VALUE,
  DESCRIPTION,
  ALLOWED_VALUES,
  ALLOWED_PATTERN,
  EXPECTED_TYPE
FROM snowflake.trust_center.configuration_view
WHERE SCANNER_ID = '<SCANNER_ID>'
  AND SCANNER_PACKAGE_ID = '<SCANNER_PACKAGE_ID>';
```

- `CONFIGURATION_NAME` is what you pass to `set_configuration` and `unset_configuration`.
- `SET_CONFIGURATION_VALUE` is `NULL` if no override is set — the scanner is using `DEFAULT_VALUE`.
- `DESCRIPTION` explains what the parameter controls. Present this to the user before proposing a change.
- Use `ALLOWED_VALUES`, `ALLOWED_PATTERN`, and `EXPECTED_TYPE` to validate the value the user wants to set.

**✋ STOPPING POINT — Present the available configurations and current values. Confirm the desired new value with the user before proceeding.**

##### Step 3: Set the custom configuration

Custom configurations are always set at scanner scope (always provide `scanner_id`):

```sql
CALL snowflake.trust_center.set_configuration(
  '<CONFIGURATION_NAME>',
  '<VALUE>',
  '<SCANNER_PACKAGE_ID>',
  '<SCANNER_ID>'
);
```

Values are always passed as VARCHAR strings. Check `EXPECTED_TYPE` to know the underlying type (e.g., pass `'16'` for a numeric parameter, not `16`).

**✋ STOPPING POINT — Present the SQL and wait for explicit user confirmation before executing.**

##### Step 4: Unset (revert to scanner default)

```sql
CALL snowflake.trust_center.unset_configuration(
  '<CONFIGURATION_NAME>',
  '<SCANNER_PACKAGE_ID>',
  '<SCANNER_ID>'
);
```

**✋ STOPPING POINT — Present the proposed revert and wait for explicit user confirmation before executing.**

---

## Error Handling

**If a command fails:**

| Error | Resolution |
|-------|------------|
| `Insufficient privileges` | User needs ACCOUNTADMIN or TRUST_CENTER_ADMIN role. Ask user to verify their role. |
| `Object does not exist` | Verify package/scanner ID exists using the views before retrying. |
| `Invalid CRON expression` | Check CRON syntax: 5 fields (minute, hour, day-of-month, month, day-of-week). |
| `Invalid notification format` | Verify JSON structure and that all users exist in `snowflake.trust_center.users`. |
| `Integration not found` or `does not exist` (notification integration) | Verify the integration name matches an existing notification integration. Confirm it was created with `CREATE NOTIFICATION INTEGRATION`. |
| `Insufficient privileges on integration` | Ensure `GRANT USAGE ON INTEGRATION <name> TO APPLICATION snowflake;` has been run. If the integration uses a secret, also grant `READ` on the secret and `USAGE` on its database/schema. |
| `Invalid notification integration configuration` | Verify the value is an `ARRAY_CONSTRUCT(...)::VARCHAR` containing objects with required keys `INTEGRATION_NAME` and `SEVERITY_THRESHOLD`. Check that `SEVERITY_THRESHOLD` is one of `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`. |
| Webhook delivery failures (visible in `notification_history`) | Check `snowflake.trust_center.notification_history` and `TABLE(snowflake.information_schema.notification_history())` for error details. Common causes: endpoint unreachable, authentication failure, or secret expired. |
| Unknown error | Present full error message to user and ask for guidance. |
