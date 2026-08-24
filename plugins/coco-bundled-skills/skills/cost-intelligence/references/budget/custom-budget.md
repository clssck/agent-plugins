# Custom Budget Reference

Custom budgets monitor credit usage for a specific group of objects or tags you define.

---

## Create Custom Budget

### Prerequisites

```sql
-- 1. Create schema to store budgets
CREATE DATABASE IF NOT EXISTS budgets_db;
CREATE SCHEMA IF NOT EXISTS budgets_db.budgets_schema;

-- 2. Create role with required privileges
USE ROLE ACCOUNTADMIN;
CREATE ROLE budget_owner;

-- Account-wide privilege: allows this role to create budgets anywhere in the account
GRANT DATABASE ROLE SNOWFLAKE.BUDGET_CREATOR TO ROLE budget_owner;

-- Schema-specific privileges: required to create and manage budgets in this particular schema
GRANT USAGE ON DATABASE budgets_db TO ROLE budget_owner;
GRANT USAGE ON SCHEMA budgets_db.budgets_schema TO ROLE budget_owner;
GRANT CREATE SNOWFLAKE.CORE.BUDGET ON SCHEMA budgets_db.budgets_schema TO ROLE budget_owner;
```

### Create the Budget

```sql
USE ROLE budget_owner;
USE SCHEMA budgets_db.budgets_schema;

CREATE SNOWFLAKE.CORE.BUDGET my_project_budget();

-- With comment
CREATE SNOWFLAKE.CORE.BUDGET my_project_budget()
    COMMENT = 'Budget for Analytics team Q1 2024';
```

**Via Snowsight**: Admin → Cost Management → Budgets → + Budget

---

## Drop Custom Budget

```sql
DROP SNOWFLAKE.CORE.BUDGET budgets_db.budgets_schema.my_project_budget;
```

Unlike deactivating the account budget, dropping a custom budget:
- Removes the budget object
- Does NOT affect the underlying objects being tracked
- Historical data is removed

---

## Time Behavior

### Monthly Cycle

- **Start**: 12:00 AM UTC on the 1st of each month
- **End**: 11:59 PM UTC on the last day of the month
- **Reset**: Spending resets to zero at cycle start

### Mid-Month Creation

If you create/activate a budget after the 1st:
- The first billing cycle is shorter than a full month — it covers only the days from creation until the end of the current month
- From the 2nd month onwards, cycles run normally from the 1st to the last day of the month
- For directly-added resources (`ADD_RESOURCE`): cost tracking starts from the creation date, not the 1st
- For tag-based resources (`ADD_RESOURCE_TAG`): data is backfilled from the 1st regardless of when the budget was created

### Backfill Behavior

| How Resource Added | Historical Data Backfilled? |
|--------------------|----------------------------|
| Via tag (`ADD_RESOURCE_TAG`) | Yes - full month |
| Directly (`ADD_RESOURCE`) | No - only from add date |

**Implication**: First month forecasting may be inaccurate for directly-added resources.

---

## Refresh Interval

Budgets must refresh to calculate if spending will exceed limits.

### Default Refresh (6 hours)

- Budget refreshes every 6 hours
- Underlying metering latency means data visible to customers can appear up to ~6.5 hours delayed
- Lower cost
- Suitable for most use cases

### Low Latency Refresh (1 hour)

- Budget refreshes every 30 minutes, providing ~1 hour data freshness
- **Higher cost** than the default refresh tier
- Use when closer monitoring is needed

### Configure Refresh Interval

```sql
-- Enable low latency (1 hour refresh)
CALL my_budget!SET_REFRESH_TIER('TIER_1H');

-- Return to default (6 hour refresh)  
CALL my_budget!SET_REFRESH_TIER('TIER_6H');

-- Check current setting
CALL my_budget!GET_REFRESH_TIER();
```

**Valid values:** `TIER_1H` (1 hour) or `TIER_6H` (6 hours, default)

**Via Snowsight**: Edit budget → Enable low latency budget checkbox

> **Budgets only.** Refresh tier is supported on budgets, as documented above. It is **deprecated on
> quotas**, where `SET_REFRESH_TIER` / `GET_REFRESH_TIER` raise `-20015`. Never apply this section to
> a quota instance — see `references/quota/lifecycle.md`.

---

## Spending Limit

```sql
-- Set limit (credits per month)
CALL my_budget!SET_SPENDING_LIMIT(500);

-- Get current limit
CALL my_budget!GET_SPENDING_LIMIT();
```

**Note**: Spending limit is for alerting only. It does NOT enforce or block usage on its own. To take action when a threshold is reached (e.g., suspend or resize a warehouse), use the Custom Actions framework.

---

## List All Budgets

### Using SHOW Command (Recommended)

```sql
-- List all budgets in account (with details: owner, created_on, etc.)
SHOW SNOWFLAKE.CORE.BUDGET IN ACCOUNT;

-- List budgets in a specific schema
SHOW SNOWFLAKE.CORE.BUDGET IN SCHEMA budgets_db.budgets_schema;

-- Filter by name pattern
SHOW SNOWFLAKE.CORE.BUDGET LIKE '%project%' IN ACCOUNT;

-- Limit results
SHOW SNOWFLAKE.CORE.BUDGET IN ACCOUNT LIMIT 10;
```

**Output columns**: `created_on`, `name`, `database_name`, `schema_name`, `current_version`, `comment`, `owner`, `owner_role_type`

### Using System Function

```sql
-- Returns JSON array (faster, but less detail - no owner fields)
SELECT SYSTEM$SHOW_BUDGETS_IN_ACCOUNT();

-- Only ACCOUNTADMIN sees all budgets
```

**Note**: `SHOW SNOWFLAKE.CORE.BUDGET` provides more detail (owner, timestamps) but `SYSTEM$SHOW_BUDGETS_IN_ACCOUNT()` may execute faster for large numbers of budgets.

---

## Budget Configuration

```sql
-- Get all configuration settings
CALL my_budget!GET_CONFIG();
```

Returns: spending limit, notification settings, refresh tier, etc.

---

## Supported Objects for Custom Budgets

> **`ADD_RESOURCE` vs `ADD_RESOURCE_TAG` scope differs.** The table below reflects objects supported by direct `ADD_RESOURCE` (the traditional resources onboarded in 2024). `ADD_RESOURCE_TAG` supports a broader and growing set of object types — prefer tag-based tracking to future-proof your budgets.

### Direct Resource Addition (`ADD_RESOURCE`)

| Object Type | Service Type |
|-------------|--------------|
| Warehouse | WAREHOUSE_METERING |
| Table | AUTO_CLUSTERING, SEARCH_OPTIMIZATION, SNOWPIPE_STREAMING |
| Database | COPY_FILES, REPLICATION |
| Materialized View | MATERIALIZED_VIEW |
| Pipe | PIPE |
| Task | SERVERLESS_TASK |
| Alert | SERVERLESS_ALERTS |
| Compute Pool | SNOWPARK_CONTAINER_SERVICES |
| Replication Group | REPLICATION |

**Not supported via `ADD_RESOURCE`:**
- Hybrid tables (tracked by account budget only)
- AI_SERVICES objects (e.g., Snowflake Intelligence, Cortex Agent)

---

## Limits

- Maximum **1000 custom budgets** per account
- Budget instances **cannot be replicated** to other accounts
- Each object can only be in **one** custom budget via direct ADD_RESOURCE
  - Adding to a second budget removes from the first (no warning)
  - Objects CAN be in multiple budgets if added via tags
