# Account Budget Reference

The account budget monitors **all** credit usage in the account. There is exactly one account budget per Snowflake account. It is created by default in every Snowflake account as `SNOWFLAKE.LOCAL.ACCOUNT_ROOT_BUDGET` — it just needs to be **activated** before it starts tracking spending.

---

## Account vs Custom Budget Scope

| Aspect | Account Budget | Custom Budget |
|--------|----------------|---------------|
| **Scope** | All supported services | Only objects/tags you add |
| **Object** | `SNOWFLAKE.LOCAL.ACCOUNT_ROOT_BUDGET` | User-created in a schema |
| **ADD_RESOURCE** | Not supported | Optional — prefer `ADD_RESOURCE_TAG` to track objects by tag |
| **Creation** | Activate (pre-exists) | CREATE SNOWFLAKE.CORE.BUDGET |
| **Deletion** | Deactivate (wipes data) | DROP BUDGET |

---

## Activate Account Budget

```sql
USE ROLE ACCOUNTADMIN;

-- Activate
CALL SNOWFLAKE.LOCAL.ACCOUNT_ROOT_BUDGET!ACTIVATE();

-- Set spending limit
CALL SNOWFLAKE.LOCAL.ACCOUNT_ROOT_BUDGET!SET_SPENDING_LIMIT(1000);

-- Configure notifications (simplest: just provide email addresses)
CALL SNOWFLAKE.LOCAL.ACCOUNT_ROOT_BUDGET!SET_EMAIL_NOTIFICATIONS(
    'admin@company.com,finance@company.com'
);
```

**Via Snowsight**: Admin → Cost Management → Budgets → Set up Account Budget

---

## Deactivate Account Budget

**Warning**: Deactivating **wipes all historical data and settings**. Custom budgets remain unaffected.

```sql
USE ROLE ACCOUNTADMIN;
CALL SNOWFLAKE.LOCAL.ACCOUNT_ROOT_BUDGET!DEACTIVATE();
```

**Impact**:
- All account budget settings (limit, notifications) are removed
- Historical usage data for the account budget is deleted
- Custom budgets continue operating normally
- Some Snowsight UI flows require account budget to be active

---

## Backfill Behavior

When you activate the account budget **after** the first day of the month:
- Historical data from the beginning of the current month is **backfilled**
- This data is used to calculate if you'll exceed your spending limit

This is different from custom budgets where:
- Resources added via **tag**: Historical data IS backfilled
- Resources added **directly** (ADD_RESOURCE): Historical data is NOT backfilled

---

## Required Roles

**ACCOUNTADMIN** can always manage the account budget. For custom role setup (BUDGET_ADMIN, BUDGET_VIEWER):

> **See**: `references/budget/roles-privileges.md` for full RBAC patterns and examples.

---

## Supported Services (Account Budget)

The account budget tracks all services reported in `SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY`.

> **Note**: Hybrid table requests are tracked at the account level but are **not** supported in custom budgets.

---

> **Common Errors**: See `references/budget/troubleshooting.md` for activation and permission error messages and solutions.
