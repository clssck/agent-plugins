# Activate / Deactivate Account Budget

Workflow for activating or deactivating the Snowflake account-level budget.

> **See**: Parent `SKILL.md` for account vs custom decision, limitations, and reference files.

---

## Activate Account Budget

Requires `ACCOUNTADMIN` or a role with the `SNOWFLAKE.BUDGET_ADMIN` application role.

### Step 1: Collect Information

| Field | Description | Required | Default |
|-------|-------------|----------|---------|
| `spending_limit` | Credits per month | Yes | — |
| `emails` | Notification email addresses | Optional | None |

**STOP**: Confirm spending limit and emails before proceeding.

### Step 2: Review & Execute

Present the complete script:

```sql
USE ROLE ACCOUNTADMIN;

-- Activate the account budget
CALL SNOWFLAKE.LOCAL.ACCOUNT_ROOT_BUDGET!ACTIVATE();

-- Set spending limit
CALL SNOWFLAKE.LOCAL.ACCOUNT_ROOT_BUDGET!SET_SPENDING_LIMIT({spending_limit});

-- Set email notifications (if provided)
CALL SNOWFLAKE.LOCAL.ACCOUNT_ROOT_BUDGET!SET_EMAIL_NOTIFICATIONS('{emails}');
```

**STOP**: Get user approval, then execute.

### Step 3: Verify

```sql
CALL SNOWFLAKE.LOCAL.ACCOUNT_ROOT_BUDGET!GET_SPENDING_LIMIT();
```

---

## Deactivate Account Budget

> **Warning**: Deactivating the account budget **permanently deletes all historical budget data**. This cannot be undone.

### Step 1: Confirm

**STOP**: Warn the user about data loss. Get explicit confirmation before proceeding.

### Step 2: Execute

```sql
USE ROLE ACCOUNTADMIN;
CALL SNOWFLAKE.LOCAL.ACCOUNT_ROOT_BUDGET!DEACTIVATE();
```
