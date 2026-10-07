# Manage Anomaly Notification Emails — Org Level

Workflow for viewing and updating the email list for organization-level cost anomaly alerts.

> **Important**: `SET_ORG_NOTIFICATION_EMAILS` **overwrites** the entire list — it does not append.
> Always GET the current list first, merge changes, then SET the full result.

> Requires `APP_ORGANIZATION_BILLING_VIEWER` or `ORGANIZATION_BILLING_VIEWER`.

> **Scope distinction**: Org notifications fire when the aggregate spend across **all accounts** is anomalous — not when a single account spikes. To manage per-account notifications, use `../notify-account-anomalies/SKILL.md`.

---

## Step 1: Verify Email Address

Before making any changes, confirm the email address is validated in Snowsight. Replace `<email>` with the address the user wants to add:

```sql
WITH raw AS (
  SELECT PARSE_JSON(SYSTEM$GET_USERS_FOR_COLLABORATION()) AS users
)
SELECT
  ARRAY_CONTAINS('<email>'::VARIANT,
    ARRAY_AGG(value:"email"::string) WITHIN GROUP (ORDER BY value:"email"::string)
  )::NUMBER AS IS_INCLUDED
FROM raw, LATERAL FLATTEN(input => users)
WHERE value:"emailValidationState"::string = 'VALIDATED'
  AND value:"email" IS NOT NULL;
```

If `IS_INCLUDED = 0`, **STOP** — the address is not verified. Inform the user they must verify the email in Snowsight before it can be added to the notification list.

---

## Step 2: Get the Current Email List

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!GET_ORG_NOTIFICATION_EMAILS();
```

Display the current list to the user. If empty, note that no notifications are configured yet.

---

## Step 3: Collect Changes

Ask what they want to do:
```
What changes would you like to make to the notification list?
1. Add one or more email addresses
2. Remove one or more email addresses
3. Replace the entire list
```

- **Add**: append new addresses to the current list.
- **Remove**: filter out the specified addresses from the current list.
- **Replace**: use the new list as-is.

> Each address must have been verified by the user in Snowsight before it can receive notifications.

Build the final comma-delimited string: `'email1@example.com, email2@example.com'`

---

## Step 4: Confirm & Execute

Present the proposed change:

```
Current notification list:  <current_emails or "empty">
Proposed notification list: <new_emails>
Scope: Org-level
```

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!SET_ORG_NOTIFICATION_EMAILS(
    '<email1>, <email2>, ...'
);
```

---

## Step 5: Verify

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!GET_ORG_NOTIFICATION_EMAILS();
```

Display the updated list and confirm success.

---

## Step 6: Next Steps

```
Would you like to:
1. Also configure account-level notifications
2. Investigate current org-level cost anomalies
3. Set up a custom budget to proactively cap spending
4. Done
```

If option 1, load `../notify-account-anomalies/SKILL.md`.
If option 2, load `../view-anomalies/SKILL.md` (scope: All accounts).
If option 3, load `../../budget/SKILL.md`.
