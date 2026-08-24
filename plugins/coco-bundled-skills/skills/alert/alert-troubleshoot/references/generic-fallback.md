# Generic Fallback Workflow

Used by [`../SKILL.md`](../SKILL.md) Step 7 in three situations:

1. The problem classification is **alert-object** (`CONDITION_FAILED`, `ACTION_FAILED`, notification `FAILURE`, or scope/time-window misconfig).
2. The detected product has no active delegation route (currently Iceberg, Snowpipe, and Error Tables — see [`product-troubleshoot-routing.md`](product-troubleshoot-routing.md)).
3. No product matched at all (custom user-table alerts, business-metric alerts).

The output is a structured findings report the user can act on directly.

---

## Inputs

All inputs come from the parent SKILL.md's earlier steps:

| From | What |
|------|------|
| Step 1 | `DESCRIBE ALERT` output (name, owner, state, schedule, warehouse, condition body, action body, comment + extracted runbook URL). |
| Step 2 | Last 24h of `ALERT_HISTORY` and `NOTIFICATION_HISTORY` for the alert. |
| Step 3 | Event-table sweep findings around `{incident_time}`. |
| Step 4 | Classification (alert-object / notification / product) and the matched detection rule (if any). |

---

## Workflow

### F1. Re-run the condition query as a bounded dry-run

**⚠️ MANDATORY STOPPING POINT:** Confirm with the user before executing. Some condition queries are expensive.

Rewrite the condition query to:

- Wrap with `SELECT … FROM ( <original> ) LIMIT 10`.
- Replace any time-window filter that uses `SNOWFLAKE.ALERT.LAST_SUCCESSFUL_SCHEDULED_TIME()` / `SNOWFLAKE.ALERT.SCHEDULED_TIME()` with a literal recent window:
  - `timestamp >= DATEADD('hour', -1, CURRENT_TIMESTAMP())`
  - `timestamp <  CURRENT_TIMESTAMP()`
- Leave object-scope filters (`snow.database.name`, `snow.executable.name`, etc.) intact.

Run it. Capture row count, the actual returned rows, and any SQL error.

Interpretation:

| Result | Meaning |
|--------|---------|
| Returns rows | Condition logic is sound; the most recent `CONDITION_FALSE` runs likely reflect the time-window filter, not a logic bug. |
| Returns zero rows | Either the issue is currently absent OR the condition's scope/filter is wrong. Compare against the event-table sweep findings — if the sweep shows relevant errors but the condition returned none, the condition's filters are too narrow. |
| Errors | Same SQL error as `CONDITION_FAILED` — confirms the bug is in the condition body. |

### F2. Classify the alert-object error (if Step 4 path A)

For `CONDITION_FAILED` and `ACTION_FAILED`, map `SQL_ERROR_MESSAGE` to one of these common patterns:

| Error pattern | Likely cause | Suggested fix |
|---------------|--------------|---------------|
| `SQL compilation error: Object '<X>' does not exist or not authorized.` | Owner role lacks `SELECT` on the event table or the referenced object was renamed/dropped. | `SHOW GRANTS TO ROLE <owner>` to confirm; either re-grant or update the condition body. Hand off `MODIFY CONDITION` to [`../../alert-create-alter/SKILL.md`](../../alert-create-alter/SKILL.md). |
| `SQL compilation error: Invalid identifier 'INFORMATION_SCHEMA.X'` | Database context not set when the alert runs (alert action ran without a `USE DATABASE`). | Either qualify with `<db>.INFORMATION_SCHEMA.X` or add `USE DATABASE <db>;` to the action block. |
| `Insufficient privileges to operate on …` | Owner role missing `EXECUTE ALERT`, `EXECUTE MANAGED ALERT`, warehouse `USAGE`, or notification integration `USAGE`. | Run `SHOW GRANTS TO ROLE <owner>` and grant the missing privilege. |
| `No active warehouse selected in the current session.` | Serverless alert created but the role lacks `EXECUTE MANAGED ALERT`, OR a non-serverless alert lost its warehouse. | Either grant `EXECUTE MANAGED ALERT` (rare in production), or `ALTER ALERT <name> SET WAREHOUSE = <wh>`. |
| `Invalid argument types for function 'SYSTEM$SEND_SNOWFLAKE_NOTIFICATION'` / unknown property names like `recipients`, `email_subject` | Path B (manual/custom): action block built with wrong notification-send syntax. | Re-load [`../../../notification/notification-send/SKILL.md`](../../../notification/notification-send/SKILL.md) for the correct property names and argument order; re-load [`../../../notification/notification-content/SKILL.md`](../../../notification/notification-content/SKILL.md) for the wrapper functions. Then `MODIFY ACTION`. |
| `NOTIFICATION integration is not configured for this alert` / missing notification integration configuration | Path A (template-managed): active notification mode/integration could not be resolved from alert config. | Validate alert config keys (`NOTIFICATION.notification_value.active`, `NOTIFICATION.EMAIL.value`, `NOTIFICATION.WEBHOOK.value`) and set the correct integration value for the active mode. |
| `Action block exceeded maximum execution time` | Action block too expensive (e.g., expensive aggregation in the action). | Move heavy work into the condition query so the action block only formats the result. |

For `NOTIFICATION_HISTORY.STATUS = FAILURE`:

Before mapping failures, determine Path A vs Path B using [`../../references/notification-dispatch-paths.md`](../../references/notification-dispatch-paths.md).

| Error pattern | Likely cause | Suggested fix |
|---------------|--------------|---------------|
| `401 Unauthorized` / `403 Forbidden` (webhook) | Webhook secret expired or rotated. | User updates the webhook integration's `SECRET` parameter. |
| `429 Too Many Requests` | Rate limit. | Reduce alert frequency or increase action-block batching. |
| `EmailRecipientNotAllowed` / `Recipient address rejected` | Email integration's `ALLOWED_RECIPIENTS` doesn't include the target address. | Update integration: `ALTER NOTIFICATION INTEGRATION <name> SET ALLOWED_RECIPIENTS = (...)`. |
| `Integration is disabled` | Integration was suspended. | `ALTER NOTIFICATION INTEGRATION <name> SET ENABLED = TRUE`. |
| Failure rows exist but action SQL has no literal integration name | Path A (template-managed) integration is config-resolved at runtime. | Use `NOTIFICATION_HISTORY.INTEGRATION_NAME` as primary runtime evidence, then validate matching alert config keys for the active mode. |

### F3. Compose the findings report

Render the report with these sections, in order:

````markdown
## Alert Troubleshooting Findings — `<alert_name>`

### Alert Summary
- Owner: `<owner>`
- State: `<STARTED|SUSPENDED>`
- Schedule: `<schedule | Alert on New Data>`
- Warehouse: `<warehouse | SERVERLESS>`
- Last triggered: `<timestamp | never>`

### Recent Execution History (last 24h)
| Scheduled Time | State | SQL Error |
|----------------|-------|-----------|
| ... | ... | ... |

(Highlight the row at `{incident_time}`.)

### Recent Notification Delivery (last 24h)
| Created | Status | Error Message |
|---------|--------|---------------|
| ... | ... | ... |

### Event-Table Sweep `[{incident_time} - 5min, +5min]`
| Time | Severity | Object | Message |
|------|----------|--------|---------|
| ... | ... | ... | ... |

(If empty, note: "No event-table activity in window. <reason from event-table-sweep.md empty-result handling>".)

### Condition Dry-Run
- Re-ran condition query with last 1 hour window: returned `<N>` rows.
- Sample rows: ...

### Classification
- Type: `<alert-object | notification | product (Tasks, no active route) | unknown>`
- Likely cause: `<one-line summary>`

### Recommended Next Steps
1. ...
2. ...
3. ...

### Runbook
- Status: `<not present | URL captured but not fetched | fetched and incorporated | declined by user>`
- URL (if any): `<url>`
- Summary (if fetched): ...

### Related Skills the User Can Manually Load
- ...
````

### F4. Hand off `ALTER ALERT` operations

Never apply an `ALTER ALERT` from this skill. When recommending a fix that requires altering the alert (`MODIFY CONDITION`, `MODIFY ACTION`, `SET WAREHOUSE`, etc.), present the proposed SQL and instruct the user to load [`../../alert-create-alter/SKILL.md`](../../alert-create-alter/SKILL.md) for the actual edit. That skill enforces the suspend → modify → resume pattern correctly.

### F5. Runbook URL handling

Carried over verbatim from [`../SKILL.md`](../SKILL.md) Step 6. The runbook prompt fires after the findings report has been presented (so the user has context before deciding to fetch). Default is **do not fetch**.

If the user approves:

- Fetch the URL.
- Summarize the runbook content.
- Cross-reference its recommended steps against the findings — call out any discrepancies (e.g., "Runbook says to restart the connector, but Openflow CDC FAILED tables do not self-heal on restart — see openflow-observability for the 5-step Restart Table Replication procedure.").
- Append a "Runbook Recommendations" section to the findings report.

If the user declines:

- Note the URL in the report's "Runbook" section so they can open it themselves.

---

## When to Loop

If F1's dry-run rows reveal information that **does** match a product detection signature (e.g., the user's "custom" alert turns out to be reading from `INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY` after all), restart at Step 4 of [`../SKILL.md`](../SKILL.md) with the new classification and route to the matched product skill instead of continuing the generic fallback.

Maximum **one** loop — if the second classification also returns "unknown", finalize the generic report and stop.
