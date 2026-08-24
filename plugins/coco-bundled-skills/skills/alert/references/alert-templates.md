# Alert Templates API Reference

Snowflake provides built-in alert templates for common monitoring scenarios. Templates generate complete `CREATE ALERT` statements with best-practice condition queries, notification content, and action blocks.

This reference is the **discovery layer**: the function reference for listing and
inspecting templates, and the catalog of available templates with their variables.

- **To construct and execute the native `CREATE … FROM TEMPLATE` statement**
  (statement shape, DDL-clause vs `TEMPLATE_PARAMS` split, both JSON shapes,
  escaping, pre-existence check, worked example), see
  `alert-templates-native-create.md`.
- **To fall back to render + manual create** when the native clause is not enabled
  on the account, see `alert-templates-render-fallback.md`.

## Functions

The functions below back template discovery and the internal
render/preview/fallback path — not the primary create (see
`alert-templates-native-create.md`).

### SYSTEM$LIST_ALERT_TEMPLATES()

Returns a JSON catalog of all available alert templates grouped by product.

```sql
SELECT SYSTEM$LIST_ALERT_TEMPLATES();
```

**Returns:** JSON with `catalog_version` and `template_groups` array. Each template entry includes:

| Field | Description |
|-------|-------------|
| `template_id` | Unique identifier used with GET and RENDER functions |
| `template_version` | Semantic version (e.g., `"2.0.0"`) |
| `display_name` | Human-readable name |
| `alert_description` | What the alert monitors |
| `product` | Product group (`DATA_QUALITY`, `OPENFLOW`, `TASKS`) |
| `supports_new_data_schedule` | Whether the template supports "alert on new data" (no schedule) |
| `default_schedule` | Recommended schedule interval |
| `scope` | Array of supported scopes (e.g., `["Account", "Database", "Schema"]`) |

### SYSTEM$GET_ALERT_TEMPLATE(template_id)

Returns the full template definition including configurable variables and the alert definition template.

```sql
SELECT SYSTEM$GET_ALERT_TEMPLATE('<template_id>');
```

**Parameters:**
- `template_id` (STRING) — Template ID from the catalog (e.g., `'TASKS_ERROR_RATE'`)

**Returns:** JSON with a `template` object containing all fields from LIST plus:
- `template_variables` — Array of configurable parameters with `name`, `display_name`, `description`, `data_type`, `semantic_type`, and `default_value`
- `alert_definition_template` — The FreeMarker template used to generate the SQL

### SYSTEM$RENDER_ALERT_TEMPLATE(template_id, template_params)

Renders a template into a complete, executable `CREATE ALERT` statement, returned as text.

> **Internal preview / fallback primitive.** The primary create path is the
> native `CREATE … FROM TEMPLATE` clause (see `./alert-templates-native-create.md`),
> which renders in-process. Use
> `SYSTEM$RENDER_ALERT_TEMPLATE` only to (a) preview the SQL before creating, or
> (b) fall back to render + manual create on accounts where the native clause
> is not enabled (the `CREATE … FROM TEMPLATE` statement fails with a SQL
> compilation `unexpected 'FROM'` syntax error). Its `template_params` schema below is distinct
> from the native `TEMPLATE_PARAMS` clause: here `alert_name` / `schedule` /
> `warehouse` are JSON fields, whereas on the native clause they are DDL clauses.

```sql
SELECT SYSTEM$RENDER_ALERT_TEMPLATE('<template_id>', '<template_params_json>');
```

**Parameters:**
- `template_id` (STRING) — Template ID from the catalog
- `template_params_json` (STRING) — JSON object with alert configuration

**Template params JSON schema:**

```json
{
  "alert_name": "<name for the alert>",
  "schedule": "<schedule interval, e.g. '30 MINUTE'>",
  "warehouse": "<optional: warehouse name (warehouse-backed alerts only)>",
  "template_variables": {
    "<variable_name>": <value>,
    ...
  }
}
```

The `template_variables` keys and types come from the `template_variables` array in `SYSTEM$GET_ALERT_TEMPLATE` output. Use the `default_value` from the template definition if the user does not specify a custom value.

**Returns:** JSON with:
- `catalog_version` — Catalog version
- `template_id` — Template used
- `template_version` — Template version
- `rendered_sql` — Complete `CREATE ALERT` SQL statement ready to execute
- `warnings` — Array of any rendering warnings

**Example:**

```sql
SELECT SYSTEM$RENDER_ALERT_TEMPLATE(
  'TASKS_ERROR_RATE',
  '{
    "alert_name": "my_task_error_alert",
    "schedule": "30 MINUTE",
    "template_variables": {
      "ERROR_RATE_THRESHOLD": 0.15,
      "TASK_NAME_FILTER": "",
      "SCOPE_ACTIVE": "ACCOUNT",
      "SCOPE_DATABASE": "",
      "SCOPE_SCHEMA": "",
      "NOTIFICATION_MODE": "EMAIL",
      "EMAIL_NOTIFICATION_INTEGRATION": "my_email_integration",
      "WEBHOOK_NOTIFICATION_INTEGRATION": ""
    }
  }'
);
```

## Available Templates

### DATA_QUALITY

| Template ID | Display Name | Default Schedule | Scope | New Data |
|-------------|-------------|------------------|-------|----------|
| `DQ_ANOMALY_DETECTION` | Anomaly detection alert | 1 HOUR | Account, Database, Schema, Table | Yes |
| `DQ_EXPECTATION_VIOLATIONS` | Expectation violations alert | 1 HOUR | Account, Database, Schema, Table | Yes |

**DQ_ANOMALY_DETECTION variables:**

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `METRIC_NAME` | STRING | `""` | Metric name to monitor (empty = all metrics) |
| `SCOPE_ACTIVE` | STRING | `"ACCOUNT"` | Monitoring scope: `ACCOUNT`, `DATABASE`, `SCHEMA`, or `TABLE` |
| `SCOPE_DATABASE` | STRING | `""` | Database to monitor when scope is DATABASE, SCHEMA, or TABLE |
| `SCOPE_SCHEMA` | STRING | `""` | Schema to monitor when scope is SCHEMA or TABLE |
| `SCOPE_TABLE` | STRING | `""` | Table to monitor when scope is TABLE |
| `NOTIFICATION_MODE` | STRING | `"EMAIL"` | `EMAIL` or `WEBHOOK` |
| `EMAIL_NOTIFICATION_INTEGRATION` | STRING | `""` | Email integration name |
| `WEBHOOK_NOTIFICATION_INTEGRATION` | STRING | `""` | Webhook integration name |

**DQ_EXPECTATION_VIOLATIONS variables:**

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `EXPECTATION_NAMES` | STRING | `""` | Comma-separated list of expectations to monitor (e.g., `"DATA_FRESH_TODAY,NO_DUPLICATE_IDS"`). Empty = all expectations |
| `SCOPE_ACTIVE` | STRING | `"ACCOUNT"` | Monitoring scope: `ACCOUNT`, `DATABASE`, `SCHEMA`, or `TABLE` |
| `SCOPE_DATABASE` | STRING | `""` | Database to monitor when scope is DATABASE, SCHEMA, or TABLE |
| `SCOPE_SCHEMA` | STRING | `""` | Schema to monitor when scope is SCHEMA or TABLE |
| `SCOPE_TABLE` | STRING | `""` | Table to monitor when scope is TABLE |
| `NOTIFICATION_MODE` | STRING | `"EMAIL"` | `EMAIL` or `WEBHOOK` |
| `EMAIL_NOTIFICATION_INTEGRATION` | STRING | `""` | Email integration name |
| `WEBHOOK_NOTIFICATION_INTEGRATION` | STRING | `""` | Webhook integration name |

### OPENFLOW

| Template ID | Display Name | Default Schedule | Scope |
|-------------|-------------|------------------|-------|
| `OPENFLOW_CONNECTOR_BACKPRESSURE_BYTES` | Connector backpressure (bytes) | 5 MINUTES | Account |
| `OPENFLOW_CONNECTOR_BACKPRESSURE` | Connector backpressure (object count) | 5 MINUTES | Account |
| `OPENFLOW_RUNTIME_HIGH_ERROR_RATE` | Runtime high error rate alert | 5 MINUTES | Account |
| `OPENFLOW_HIGH_QUEUED_COUNT` | High queued count alert | 5 MINUTES | Account |
| `OPENFLOW_NO_DATA` | No data alert | 5 MINUTES | Account |
| `OPENFLOW_HIGH_QUEUED_BYTES` | High queued bytes alert | 5 MINUTES | Account |
| `OPENFLOW_TABLE_REPLICATION_FAILURE` | Table replication failure alert | 5 MINUTES | Account |
| `OPENFLOW_HIGH_CPU` | High CPU alert | 5 MINUTES | Account |

All OpenFlow templates share these notification variables:

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `NOTIFICATION_MODE` | STRING | `"EMAIL"` | `EMAIL` or `WEBHOOK` |
| `EMAIL_NOTIFICATION_INTEGRATION` | STRING | `""` | Email integration name |
| `WEBHOOK_NOTIFICATION_INTEGRATION` | STRING | `""` | Webhook integration name |

**OPENFLOW_CONNECTOR_BACKPRESSURE variables:**

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ALERT_THRESHOLD` | NUMBER | `0.1` | Fraction of time window that must exceed backpressure to trigger (0.0-1.0) |

**OPENFLOW_CONNECTOR_BACKPRESSURE_BYTES variables:**

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ALERT_THRESHOLD` | NUMBER | `0.1` | Fraction of time window that must exceed backpressure to trigger (0.0-1.0) |

**OPENFLOW_RUNTIME_HIGH_ERROR_RATE variables:**

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ALERT_THRESHOLD` | INTEGER | `10` | Number of errors that triggers the alert |

**OPENFLOW_HIGH_QUEUED_COUNT variables:**

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `HIGH_THRESHOLD` | NUMBER | `0.8` | Fraction of backpressure threshold to trigger early warning (0.0-1.0) |
| `ALERT_THRESHOLD` | NUMBER | `0.1` | Fraction of time window that must exceed high threshold to trigger (0.0-1.0) |

**OPENFLOW_HIGH_QUEUED_BYTES variables:**

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `HIGH_THRESHOLD` | NUMBER | `0.8` | Fraction of backpressure threshold to trigger early warning (0.0-1.0) |
| `ALERT_THRESHOLD` | NUMBER | `0.1` | Fraction of time window that must exceed high threshold to trigger (0.0-1.0) |

**OPENFLOW_NO_DATA variables:**

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `LOOKBACK_WINDOW` | INTEGER | `4` | Number of hours to look back for data flow |

**OPENFLOW_TABLE_REPLICATION_FAILURE variables:**

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `LOOKBACK_WINDOW` | INTEGER | `4` | Number of hours to look back for replication failures |

**OPENFLOW_HIGH_CPU variables:**

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `CPU_THRESHOLD` | NUMBER | `0.9` | Trigger when CPU load exceeds this fraction (0.0-1.0) |
| `ALERT_THRESHOLD` | NUMBER | `0.1` | Fraction of time window that must exceed CPU threshold to trigger (0.0-1.0) |

### TASKS

| Template ID | Display Name | Default Schedule | Scope |
|-------------|-------------|------------------|-------|
| `TASKS_ERROR_RATE` | Error rate alert | 30 MINUTES | Account, Database, Schema |

**TASKS_ERROR_RATE variables:**

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ERROR_RATE_THRESHOLD` | NUMBER | `0.15` | Error rate threshold (0.0-1.0) |
| `TASK_NAME_FILTER` | STRING | `""` | Filter pattern for task names (e.g., `"ETL_"`) |
| `SCOPE_ACTIVE` | STRING | `"ACCOUNT"` | `ACCOUNT`, `DATABASE`, or `SCHEMA` |
| `SCOPE_DATABASE` | STRING | `""` | Database scope filter |
| `SCOPE_SCHEMA` | STRING | `""` | Schema scope filter |
| `NOTIFICATION_MODE` | STRING | `"EMAIL"` | `EMAIL` or `WEBHOOK` |
| `EMAIL_NOTIFICATION_INTEGRATION` | STRING | `""` | Email integration name |
| `WEBHOOK_NOTIFICATION_INTEGRATION` | STRING | `""` | Webhook integration name |

## Unknown / Unavailable Template

> **⛔ Unknown / unavailable template — STOP, never substitute.** If the template
> the user named does not exist — whether you learn this from
> `LIST_ALERT_TEMPLATES` **or** from a `CREATE … FROM TEMPLATE` that fails because
> the template is unknown — do **NOT** pick a different template and build the
> alert, and do **NOT** generate or execute any replacement `CREATE`, even if
> another template looks like a close match for the user's intent. Instead: stop,
> tell the user the template they named does not exist, list the available
> templates, and (optionally) suggest the closest fit — then **wait for the user
> to explicitly choose** before generating any `CREATE`. Creating an alert from a
> template the user did not explicitly pick is a hard error, not a helpful
> shortcut.

## Notes

- The template supplies the full condition query, notification content generation (HTML email with Snowflake branding), and action block — whether created via the native `CREATE … FROM TEMPLATE` clause (rendered in-process) or previewed via `SYSTEM$RENDER_ALERT_TEMPLATE`. No additional steps are needed for condition or notification content.
- Templates auto-discover the event table using `SHOW PARAMETERS LIKE 'EVENT_TABLE' IN DATABASE`. If the default is `SNOWFLAKE.TELEMETRY.EVENTS`, the template uses `SNOWFLAKE.TELEMETRY.EVENTS_VIEW` instead.
- OpenFlow templates additionally discover per-deployment event tables via `SHOW OPENFLOW DATA PLANE INTEGRATIONS` and `DESCRIBE OPENFLOW DATA PLANE INTEGRATION`.
- For serverless alerts, omit the warehouse entirely — the `WAREHOUSE` clause on the native statement, or the `warehouse` field in the render `template_params`. Include it only for warehouse-backed alerts.
- Templates support both email and webhook notifications. Set `NOTIFICATION_MODE` to `"WEBHOOK"` and provide `WEBHOOK_NOTIFICATION_INTEGRATION` for Slack, Teams, or PagerDuty.
- For notification dispatch behavior, load `notification-dispatch-paths.md` to distinguish Path A template-managed dispatch (`SYSTEM$SEND_NOTIFICATION_FROM_ALERT`) from Path B manual/custom dispatch (`SYSTEM$SEND_SNOWFLAKE_NOTIFICATION`).
