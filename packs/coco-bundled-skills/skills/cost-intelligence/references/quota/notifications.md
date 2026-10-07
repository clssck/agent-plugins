# Quota Notifications

Methods for configuring notification thresholds, integrations, and admin emails.

**Semantic keywords:** notification threshold, projected spend, actual spend, admin email, notification integration, notify user, daily threshold, notification cycle

---

## How notifications fire

Read this before configuring thresholds — it determines what to tell the user to expect.

- **Only the highest breached threshold fires**, per user, per spend strategy, per cycle. A user
  configured at 50/80/90 who jumps straight past 90% receives one notification, for 90 — not three.
- **Repeat notifications are rate-limited**, keyed on user, threshold, spend strategy, and cycle:

  | Cycle | Spend strategy | Re-fires |
  |-------|----------------|----------|
  | MONTHLY | ACTUAL | Once per calendar month |
  | MONTHLY | PROJECTED | After a 24-hour cooldown |
  | DAILY | ACTUAL | Once per UTC day |
  | DAILY | PROJECTED | After a 24-hour cooldown |

  Because the threshold is part of that key, crossing into a **higher** threshold notifies again even
  inside a cooldown. A user who triggered 80 and later reaches 90 gets a second notification.
- **Blocked users are skipped.** A MONTHLY block suppresses notifications for both cycles; a DAILY
  block suppresses only DAILY.
- **Evaluation is periodic, not event-driven.** Breaches are detected by a background measurement
  pass, so a notification arrives some time after the spend that caused it. The interval is not
  configurable.

---

## ADD_NOTIFICATION_THRESHOLD

```sql
CALL {quota_fqn}!ADD_NOTIFICATION_THRESHOLD({threshold}, '{spend_strategy}', {notify_user}, '{cycle}');
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.

**Parameters:**
- `threshold`: NUMBER — percentage of the per-user limit. Must be greater than 0 and no greater than
  1000; values above 100 are legal and useful for catching large overruns. Out of range fails with
  `Unsupported threshold. It must be greater than 0 and less than or equal to 1000.`
- `spend_strategy`: VARCHAR — `'PROJECTED'` or `'ACTUAL'`. Required; anything else fails with
  `Unsupported spend strategy. Must be ACTUAL or PROJECTED.`
- `notify_user`: BOOLEAN — whether to email the user. NULL is treated as TRUE. When FALSE the breach
  is still recorded and still counts toward the admin summary; only the user's own email is suppressed
- `cycle`: VARCHAR — which limit the threshold applies to. May be omitted, in which case it defaults
  to `'MONTHLY'`:
  - `'MONTHLY'` — evaluated against the monthly per-user limit
  - `'DAILY'` — evaluated against the daily per-user limit
  - `'ALL'` — creates **both** a MONTHLY and a DAILY threshold in one call

  An unrecognized value fails with `Invalid cycle. Must be MONTHLY, DAILY, or ALL.`

Re-adding an existing threshold, spend strategy, and cycle combination updates its `notify_user`
flag rather than failing.

The account has a configured maximum number of thresholds; exceeding it fails with
`Maximum number of notification thresholds reached.` A `CYCLE = 'ALL'` call consumes two of those
slots.

**Examples:**
```sql
CALL my_db.my_schema.my_quota!ADD_NOTIFICATION_THRESHOLD(50, 'PROJECTED', TRUE);
CALL my_db.my_schema.my_quota!ADD_NOTIFICATION_THRESHOLD(80, 'ACTUAL', TRUE, 'MONTHLY');
CALL my_db.my_schema.my_quota!ADD_NOTIFICATION_THRESHOLD(90, 'ACTUAL', TRUE, 'DAILY');

-- One call, both cycles
CALL my_db.my_schema.my_quota!ADD_NOTIFICATION_THRESHOLD(100, 'ACTUAL', TRUE, 'ALL');

-- Track the breach for admin reporting without emailing the user
CALL my_db.my_schema.my_quota!ADD_NOTIFICATION_THRESHOLD(120, 'ACTUAL', FALSE, 'MONTHLY');
```

---

## REMOVE_NOTIFICATION_THRESHOLD

```sql
CALL {quota_fqn}!REMOVE_NOTIFICATION_THRESHOLD({threshold}, '{spend_strategy}', '{cycle}');
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.

**Parameters:**
- `threshold`: NUMBER — the threshold to remove
- `spend_strategy`: VARCHAR — `'PROJECTED'` or `'ACTUAL'`
- `cycle`: VARCHAR — `'MONTHLY'`, `'DAILY'`, or `'ALL'` to remove both cycles in one call. May be
  omitted, in which case it defaults to `'MONTHLY'`

Removing a threshold also clears its per-user dispatch records, so a threshold re-added later starts
with clean rate-limiting state. Removing something that does not exist is not an error — the
procedure returns a "no threshold matching…" message instead.

---

## GET_NOTIFICATION_THRESHOLDS

```sql
CALL {quota_fqn}!GET_NOTIFICATION_THRESHOLDS();
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Returns:**
- `THRESHOLD` (NUMBER) — the configured threshold percentage
- `SPEND_STRATEGY` (VARCHAR) — `PROJECTED` or `ACTUAL`
- `NOTIFY_USER` (BOOLEAN) — whether the user is emailed when breached
- `CYCLE` (VARCHAR) — `MONTHLY` or `DAILY`
- `ADDED_TIMESTAMP` (TIMESTAMP_TZ) — when the threshold was configured

---

## ADD_NOTIFICATION_INTEGRATION

```sql
CALL {quota_fqn}!ADD_NOTIFICATION_INTEGRATION('{integration_name}');
```

> **Prerequisites**:
> 1. The caller must have the **ADMIN** role on the quota instance.
> 2. The integration must be granted to the Snowflake application: `GRANT USAGE ON INTEGRATION {name} TO APPLICATION SNOWFLAKE;`

**Parameters:**
- `integration_name`: STRING — name of a notification integration (SNS or webhook type only; email
  integrations are not supported here)

A name that cannot be resolved, one of an unsupported type, or one the quota cannot access all fail
with the same message: `Invalid notification integration or insufficient privileges to access it.`
The wording mentions privileges, but an **EMAIL-type integration fails this way even when the grant
is correctly in place** — check the integration type before re-granting.

The account has a configured maximum number of integrations; exceeding it fails with
`Maximum number of notification integrations reached.` Adding the same integration twice is a no-op.

**Examples:**
```sql
CALL my_db.my_schema.my_quota!ADD_NOTIFICATION_INTEGRATION('my_sns_integration');
CALL my_db.my_schema.my_quota!ADD_NOTIFICATION_INTEGRATION('my_slack_webhook');
```

## REMOVE_NOTIFICATION_INTEGRATION

```sql
CALL {quota_fqn}!REMOVE_NOTIFICATION_INTEGRATION('{integration_name}');
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.

**Parameters:**
- `integration_name`: STRING — name of the integration to remove

## GET_NOTIFICATION_INTEGRATIONS

```sql
CALL {quota_fqn}!GET_NOTIFICATION_INTEGRATIONS();
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Returns:**
- `INTEGRATION_NAME` (STRING) — name of the configured notification integration
- `LAST_NOTIFICATION_TIME` (TIMESTAMP_TZ) — last time a notification was sent via this integration
- `ADDED_TIMESTAMP` (TIMESTAMP_TZ) — when the integration was configured

---

## SET_ADMIN_EMAILS

```sql
CALL {quota_fqn}!SET_ADMIN_EMAILS('{admin_emails}');
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.

**Parameters:**
- `admin_emails`: VARCHAR — comma-separated list of email addresses (e.g., `'admin1@company.com, admin2@company.com'`)

Whitespace is stripped. **Every address must already belong to a user in the current account and be
validated there.** An address that does not fails with `Email recipients in the given list at indexes
[...] are not allowed. Either these email addresses are not yet validated or do not belong to any
user in the current account.`, where the listed index is 1-based.

Passing an empty string or NULL clears the list and stops admin summary notifications.

> A distribution list or alias that is not an account user's email will be rejected. To send
> somewhere else, use a notification integration instead.

## GET_ADMIN_EMAILS

```sql
CALL {quota_fqn}!GET_ADMIN_EMAILS();
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Returns:**
- VARCHAR — comma-separated list of configured admin email addresses, or NULL if none

---

## Admin summary behaviour

The admin summary aggregates every user who breached a threshold in a measurement pass, including
users whose thresholds have `NOTIFY_USER = FALSE`.

- It is sent only when at least one **new** breach was detected in that pass, after rate-limiting and
  block filtering. A pass where every breach is already rate-limited sends nothing, so do not
  describe admin summaries as arriving on every evaluation.
- The number of rows in a single summary is capped, so a very large breach set may be truncated.
- One summary can mix cycles, with each breach reported against its own limit.
- If both the integration list and the admin email list are empty, admin summaries are suppressed
  entirely.
