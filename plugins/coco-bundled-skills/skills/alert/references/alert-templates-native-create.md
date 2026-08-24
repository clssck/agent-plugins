# Native `CREATE … FROM TEMPLATE` — Statement Construction

## Statement shape

```sql
CREATE OR REPLACE ALERT <alert_name>
  FROM TEMPLATE <template_id>
  [ WAREHOUSE = <wh> ]              -- omit entirely for serverless
  [ SCHEDULE  = '<interval>' ]
  [ COMMENT   = '<comment>' ]
  [ TEMPLATE_PARAMS = '{ "<VARIABLE>": <value>, … }' ];  -- omit only when all variables keep their defaults; otherwise include only the variables to override
```

`CREATE OR REPLACE` is the recommended form (retry-safe, and consistent with the
fallback path); pair it with the pre-existence check below. `CREATE ALERT IF NOT EXISTS`
is a valid non-destructive alternative when you must not overwrite an existing alert.

## DDL clauses vs TEMPLATE_PARAMS

| Input | Goes into | Notes |
|-------|-----------|-------|
| Alert name | DDL `<alert_name>` | |
| `WAREHOUSE` | DDL clause | **Omit entirely** for serverless; add only for warehouse-backed alerts (see Constraints) |
| `SCHEDULE` | DDL clause | Omit to use the template's `default_schedule` (see Constraints) |
| `COMMENT` | DDL clause | Optional free-text; escape `'` as `''` (see Escaping below) |
| `RUNBOOK`, `SUSPEND_ALERT_AFTER_NUM_FAILURES`, `[WITH] TAG (…)` | DDL clauses | Optional pass-through clauses, same as a normal `CREATE ALERT` |
| Thresholds, filters, scope, notification mode/integration | `TEMPLATE_PARAMS` JSON | The notification integration name rides here (`EMAIL_NOTIFICATION_INTEGRATION` / `WEBHOOK_NOTIFICATION_INTEGRATION`, selected by `NOTIFICATION_MODE`, default `EMAIL`) |


## Constraints

| Constraint | Description |
|------------|-------------|
| `WAREHOUSE = ''` | For serverless alerts, omit the `WAREHOUSE` clause entirely |
| `SCHEDULE = NULL` | Rejected on non-streaming templates; omit the clause to use the template default, or provide an interval |

The alert runs natively in the caller's session (authorized against the caller's role).

## Escaping

Inside `TEMPLATE_PARAMS` and `COMMENT` string values, escape `'` as `''` (or use dollar-quoting).

## Pre-existence check

Before executing the `CREATE OR REPLACE`, run:
```sql
SHOW ALERTS LIKE '<alert_name>';
```
If an alert with that name is found, tell the user — `CREATE OR REPLACE` will silently overwrite the existing alert including its schedule, condition, and notification settings — and ask whether to proceed.

## Worked example

Serverless task error-rate alert emailing an existing integration `"my_email_integration"`:

```sql
CREATE OR REPLACE ALERT alert_task_errors
  FROM TEMPLATE TASKS_ERROR_RATE
  SCHEDULE = '30 MINUTE'
  TEMPLATE_PARAMS = '{
    "ERROR_RATE_THRESHOLD": 0.15,
    "NOTIFICATION_MODE": "EMAIL",
    "EMAIL_NOTIFICATION_INTEGRATION": "my_email_integration"
  }';
```

## Execution

After user approval, execute the statement directly — one DDL, no render round-trip. The template is rendered and the alert built in-process; no attribution argument is passed (creation-surface attribution is derived downstream from query history).

## Optional preview (display only)

If the user wants to see the rendered `CREATE ALERT` SQL before creating, you may call `SYSTEM$RENDER_ALERT_TEMPLATE` for display only — this does not create anything. The returned JSON includes a `rendered_sql` field containing the full executable `CREATE [OR REPLACE] ALERT …` statement. See `./alert-templates.md` for the exact render call and its parameter schema. Note that the render function uses its own nested shape (`alert_name` / `schedule` / `warehouse` / `template_variables`), not the flat native `TEMPLATE_PARAMS` clause.

Then still create via the native `CREATE … FROM TEMPLATE` statement above. This is an optional UX step, not a required round-trip.

## Related Skills

- **`alert-templates.md`** - Template discovery: the available templates catalog, per-template variable tables, and the `LIST` / `GET` / `RENDER` function reference
- **`alert-templates-render-fallback.md`** - Legacy render + execute fallback, used when the native clause is not enabled on the account (`unexpected 'FROM'` syntax error)
