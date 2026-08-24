---
name: manage-maintenance-policy
description: "Create, apply, and manage consumer-controlled maintenance policies for Snowflake Native Apps: define maintenance windows with cron schedules to control when app upgrades happen. Triggers: maintenance policy, maintenance window, upgrade schedule, control upgrades, upgrade timing, app maintenance, manage upgrades, set maintenance window, create maintenance policy, change maintenance schedule, when upgrades happen."
parent_skill: native-app-consumer
---

# Manage Maintenance Policies for Native Apps (Consumer)

## When to Load

From the root `native-app-consumer` skill when the user wants to control when Native App upgrades happen by creating, applying, or managing maintenance policies.

## Prerequisites

- Access to a Snowflake consumer account
- A role with sufficient privileges (checked before each action)

---

## Workflow

### Step 1: Identify Role

**Ask** the user:
```
Which role will you use? (e.g., ACCOUNTADMIN, SYSADMIN, or a custom role)
```

**⚠️ MANDATORY STOPPING POINT**: Wait for user response.

This role is used for all privilege checks in subsequent steps.

---

### Step 2: Create a Maintenance Policy

**Ask** the user:
```
Do you already have a maintenance policy, or would you like to create a new one?
1. Create a new maintenance policy
2. I already have one
```

**⚠️ MANDATORY STOPPING POINT**: Wait for user response.

**If the user already has a policy:**

Ask for the policy name (fully qualified, e.g., `MY_DB.MY_SCHEMA.MY_POLICY`).

**Ask** the user:
```
Would you like to change the schedule on this policy?
1. Yes — update the schedule
2. No — keep the current schedule
```

**⚠️ MANDATORY STOPPING POINT**: Wait for user response.

**If the user wants to change the schedule:**

Ask for the new schedule in natural language, convert to cron syntax, and confirm with the user (same flow as creating a new policy schedule above).

Run:
```sql
ALTER MAINTENANCE POLICY IF EXISTS <policy_name> SET
  SCHEDULE = 'USING CRON <cron_expression> <timezone>';
```

If successful, inform the user the schedule has been updated.

Proceed to Step 3.

**If creating a new policy:**

**Ask** the user:
```
Which database and schema should the maintenance policy be created in? (e.g., MY_DB.MY_SCHEMA)
```

**⚠️ MANDATORY STOPPING POINT**: Wait for user response.

Check whether the role has the required privilege:

```sql
SHOW GRANTS TO ROLE <role_name>;
```

Verify the role has `CREATE MAINTENANCE POLICY` on `<db_name>.<schema_name>`.

If missing, **stop immediately** and inform the user:

> "Your role `<role_name>` is missing the `CREATE MAINTENANCE POLICY` privilege on `<db_name>.<schema_name>`. Please have an admin grant this privilege, then try again."

Do NOT proceed until the user confirms the privilege has been granted.

**Ask** the user:
```
Let's set up your maintenance policy. I need:
1. A name for the policy (e.g., weekend_maintenance)
2. When should maintenance happen? You can describe it naturally (e.g., "every Saturday at 2 AM UTC", "Friday evenings at 7 PM Eastern") and I'll convert it to cron syntax.
3. (Optional) A comment describing the policy.
```

**⚠️ MANDATORY STOPPING POINT**: Wait for user response.

Convert the user's schedule description to cron syntax. Present the cron expression back to the user for confirmation:

> "I'll create a policy with this schedule:
> - Cron: `<cron_expression>`
> - Timezone: `<timezone>`
> - Meaning: [human-readable description, e.g., 'Every Saturday at 2:00 AM UTC']
>
> Does this look right?"

**⚠️ MANDATORY STOPPING POINT**: Wait for user confirmation.

Run:
```sql
CREATE MAINTENANCE POLICY <db_name>.<schema_name>.<name>
  SCHEDULE = 'USING CRON <cron_expression> <timezone>'
  [ COMMENT = '<comment>' ];
```

If successful, inform the user:
> "Maintenance policy `<name>` created. This policy is not active yet — it needs to be applied to an application or your account."

---

### Step 3: Apply the Policy

**Ask** the user:
```
Would you like to apply this maintenance policy? If so, where?
1. Account-wide — applies to all Native Apps in your account
2. Specific application — applies to a single app
3. Skip — don't apply it now
```

**⚠️ MANDATORY STOPPING POINT**: Wait for user response.

If the user chooses to skip, go to Step 4.

**If account-wide:**

The ACCOUNTADMIN role is required for account-level apply. If the user's role is not ACCOUNTADMIN, inform them and stop.

```sql
ALTER ACCOUNT SET MAINTENANCE POLICY <policy_name> FOR ALL APPLICATIONS [ FORCE ];
```

**If specific application:**

Check whether the role has `APPLY MAINTENANCE POLICY` on the account and `OWNERSHIP` or `APPLY` on the maintenance policy:

```sql
SHOW GRANTS TO ROLE <role_name>;
```

If missing, **stop immediately** and inform the user:

> "Your role `<role_name>` is missing the required privileges. You need `APPLY MAINTENANCE POLICY` on the account and `OWNERSHIP` or `APPLY` on the maintenance policy. Please have an admin grant these privileges, then try again."

Do NOT proceed until the user confirms the privilege has been granted.

Ask for the app name.

```sql
ALTER APPLICATION <app_name> SET MAINTENANCE POLICY <policy_name> [ FORCE ];
```

Use `FORCE` if the user confirms they want to replace an existing policy. If the command fails because a policy is already set, inform the user:

> "A maintenance policy is already applied. Would you like to replace it? (This will use FORCE to override the existing policy.)"

After successful application, inform the user:

> "Maintenance policy `<policy_name>` is now active. Future upgrades with maintenance window support will wait until your scheduled window: [human-readable schedule].
>
> Note: Only one maintenance policy can be active per app (or account). Applying a new policy replaces any existing one. If a provider sets an upgrade deadline, the upgrade will proceed at whichever comes sooner — your maintenance window or the provider's deadline."

---

### Step 4: Show the Policy

Show the policy details and where it is applied:

```sql
DESCRIBE MAINTENANCE POLICY <policy_name>;
```

If the policy was applied to the account in Step 3:
```sql
SHOW MAINTENANCE POLICIES ON ACCOUNT;
```

If the policy was applied to a specific application in Step 3:
```sql
SHOW MAINTENANCE POLICIES ON APPLICATION <app_name>;
```

Present the results to the user in a clear summary.

---

## Stopping Points

- ✋ Step 1: Confirm role selection
- ✋ Step 2: Confirm create vs. existing policy
- ✋ Step 2: Confirm whether to change schedule (existing policy)
- ✋ Step 2: Confirm database and schema location
- ✋ Step 2: Confirm policy name, schedule, and comment
- ✋ Step 2: Confirm cron expression before creation
- ✋ Step 3: Confirm where to apply policy

## Output

- Maintenance policy created (or existing policy identified) and optionally applied
- User informed of the active maintenance schedule and its implications
