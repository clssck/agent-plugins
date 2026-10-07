---
parent_skill: data-quality
---

# Workflow: Data Quality Notifications

Enable Snowflake's **native Data Quality Notifications** so recipients are emailed (or notified via webhook/Slack) when a DMF **expectation is violated** or an **anomaly is detected**. Prefer this over creating a custom Snowflake `ALERT` that polls health percentages.

**Docs:** [Sending notifications for data quality issues](https://docs.snowflake.com/en/user-guide/data-quality-notifications)

## Trigger Phrases
- "data quality notifications"
- "notify me on expectation violations"
- "email me when DMF fails"
- "turn on DQ notifications"
- "Slack when quality fails"
- "notify me next time quality fails"
- "send email when expectations fail"
- "webhook notifications for data quality"
- "enable DATA_QUALITY_MONITORING_SETTINGS"
- "quality alerts" / "notify on drops" (prefer this workflow first; see vs SLA alerting below)

## When to Load
- User wants to be notified when expectations fail or anomalies fire
- RCA / investigation follow-up: "set up alerts so I'm notified next time"
- Generic "quality alerts" / "notify me" intent — **prefer this workflow** over `sla-alerting`

## Prefer This Over `sla-alerting`

| | **DQ Notifications** (this workflow) | **SLA Alerting** (`sla-alerting.md`) |
|---|---|---|
| Mechanism | Native `DATA_QUALITY_MONITORING_SETTINGS` on the database | Custom Snowflake `CREATE ALERT` polling health % |
| Trigger | Expectation violation **or** anomaly detection | Schema health drops below a threshold |
| Scope | All DMF associations in the database (opt out per association) | One alert object + optional log table |
| When to use | "Notify me next time" / email / Slack on DQ issues | Advanced/custom health-threshold monitoring |

Do **not** create a native `ALERT` for a simple "notify me when quality fails" request. Use `sla-alerting` only when the user explicitly wants a custom health-% threshold poll.

## Template to Use
**Primary:** `templates/dq-notifications-enable.sql`
- Optional `CREATE NOTIFICATION INTEGRATION` (EMAIL or WEBHOOK)
- Grants: `MANAGE DATA QUALITY` + `USAGE` on integration
- `ALTER DATABASE ... SET DATA_QUALITY_MONITORING_SETTINGS` YAML
- Optional per-association `SET DATA_QUALITY_NOTIFICATION = FALSE`
- Status check via `data_quality_notification_status`

---

## Execution Steps

### Step 1: Gather Database + Recipients / Channel

Extract from the user message:
- **Database** to enable (notifications are database-scoped)
- **Recipients**: email addresses and/or notification integration (EMAIL / WEBHOOK → Slack, etc.)
- Optional: `cooldown_hours`, `metadata_included` (default TRUE)

If missing, ask:
> "To enable Data Quality Notifications I need:
> 1. The **database** name
> 2. How to notify you: **email addresses**, an existing **notification integration**, or both (e.g. Slack webhook)
>
> Notifications fire on **expectation violations** and **anomaly detection** — not a custom health-% poll."

---

### Step 2: Check / Plan Notification Integration

If the user wants email via an integration (or Slack/webhook):
- Plan `CREATE NOTIFICATION INTEGRATION ... TYPE=EMAIL` with `ALLOWED_RECIPIENTS`, **or**
- Plan webhook secret + `TYPE=WEBHOOK` integration (Slack, etc.)

Email addresses can also be listed directly in the YAML `email_recipients` without an integration.

If using an integration, the database owner role needs:
- `MANAGE DATA QUALITY ON ACCOUNT`
- `USAGE ON INTEGRATION <integration_name>`

---

### Step 3: Present Grants + ALTER DATABASE YAML for Approval

**⚠️ MANDATORY CHECKPOINT**: This workflow performs WRITE operations (`CREATE NOTIFICATION INTEGRATION`, `GRANT`, `ALTER DATABASE`). Present the full plan and wait for explicit approval before executing.

Present to user (customize from the template):

```
## Data Quality Notifications Plan

### Trigger
- Expectation violation OR anomaly detection on DMF associations in <database>
- (Not a custom CREATE ALERT health-% poll)

### Recipients / channel
- Email: <emails> and/or integration: <integration_name>

### Privileges (database owner role)
- GRANT MANAGE DATA QUALITY ON ACCOUNT TO ROLE <role>;
- GRANT USAGE ON INTEGRATION <integration_name> TO ROLE <role>;  (if using integration)

### Enable on database
ALTER DATABASE <database> SET DATA_QUALITY_MONITORING_SETTINGS =
  $$
  notification:
    enabled: TRUE
    email_recipients: [ '<email>' ]
    integrations:
      - <INTEGRATION_NAME>
    cooldown_hours: <N>
    metadata_included: TRUE
  $$;

### Optional
- Opt out specific associations with SET DATA_QUALITY_NOTIFICATION = FALSE

Do you approve? (Yes / No / Modify)
```

**NEVER execute CREATE / GRANT / ALTER DATABASE without explicit user confirmation** (e.g. "yes", "approved", "looks good"), unless pre-approval was given in the request.

---

### Step 4: Execute (On Approval Only)

Read `templates/dq-notifications-enable.sql`, replace placeholders, and run approved statements in order:
1. Create notification integration (if needed)
2. Grants
3. `ALTER DATABASE ... SET DATA_QUALITY_MONITORING_SETTINGS`
4. Optional per-association disable

---

### Step 5: Optional Per-Association Opt-Out

If the user wants to silence a specific object↔DMF pair inside an enabled database:

```sql
ALTER <TABLE|VIEW> <fqn>
  MODIFY DATA METRIC FUNCTION <metric_fqn> ON (<args>)
    SET DATA_QUALITY_NOTIFICATION = FALSE;
```

---

### Step 6: Verify Status

Run the status query from the template (READ-only):

```sql
SELECT
  ref_entity_name,
  metric_name,
  data_quality_notification_status
FROM TABLE(<database>.INFORMATION_SCHEMA.DATA_METRIC_FUNCTION_REFERENCES(
  REF_ENTITY_NAME => '<database>.<schema>.<table>',
  REF_ENTITY_DOMAIN => 'TABLE'
));
```

Confirm `data_quality_notification_status` reflects notifications enabled (or disabled for opted-out associations).

---

### Step 7: Present Results

```
Data Quality Notifications enabled for database: <database>

Triggers: expectation violation OR anomaly detection
Recipients / integrations: <summary>
Cooldown: <N> hours
Metadata included: <TRUE|FALSE>

Verify associations with data_quality_notification_status on
INFORMATION_SCHEMA.DATA_METRIC_FUNCTION_REFERENCES.

To disable a specific association:
  ALTER ... MODIFY DATA METRIC FUNCTION ... SET DATA_QUALITY_NOTIFICATION = FALSE;
```

**STOP** after enabling and verifying. Do not auto-chain into `sla-alerting` or circuit-breaker unless the user asks.

---

## Error Handling

| Error | Action |
|---|---|
| Missing `MANAGE DATA QUALITY` | Tell user the account-level grant is required for the database owner role |
| Integration USAGE denied | Grant `USAGE ON INTEGRATION` to the database owner role |
| Unverified email | Email recipients must be verified Snowflake user emails (or use ALLOWED_RECIPIENTS on EMAIL integration) |
| User wants health-% threshold | Redirect to `workflows/sla-alerting.md` (advanced custom ALERT path) |
| User declined approval | Do not run any WRITE statements |

## Notes
- Requires Enterprise Edition (Data Quality Monitoring)
- Database-level enable applies to all DMF associations unless opted out
- Fires on **expectation violation** or **anomaly detection** — not a custom health-% poll
- This is a **WRITE** workflow — approval checkpoint is mandatory
- Docs: https://docs.snowflake.com/en/user-guide/data-quality-notifications

## Halting States
- **Success**: Settings applied; status verified — present summary and STOP
- **User declined**: No WRITE statements executed
- **Permission error**: Report which privilege is missing
