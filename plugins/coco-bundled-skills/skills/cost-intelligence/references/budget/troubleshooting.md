# Budget Troubleshooting Reference

Monitoring, debugging, limits, and common error resolution.

---

## View Usage Data

### Get Service Type Usage

> **Important**: `GET_SERVICE_TYPE_USAGE` is **deprecated**. Always use `GET_SERVICE_TYPE_USAGE_V2` instead.

`GET_SERVICE_TYPE_USAGE_V2` is a **table function** (use `SELECT ... FROM TABLE(...)`, not `CALL`).
It takes two string arguments: start month (`'YYYY-MM'`) and end month (`'YYYY-MM'`), where end month is **exclusive**.

```sql
-- Example: get usage for February 2026
SELECT SERVICE_TYPE, ROUND(SUM(CREDITS_USED), 2) AS CREDITS_USED
FROM TABLE(my_budget!GET_SERVICE_TYPE_USAGE_V2(
    '2026-02', '2026-03'
))
GROUP BY SERVICE_TYPE
ORDER BY CREDITS_USED DESC;
```

Columns returned: `SERVICE_TYPE`, `ENTITY_TYPE`, `ENTITY_ID`, `NAME`, `CREDITS_USED`, `CREDITS_COMPUTE`, `CREDITS_CLOUD`.

### Supported Service Types

| Service Type | Account Budget | Custom Budget |
|--------------|----------------|---------------|
| WAREHOUSE_METERING | Yes | Yes |
| SNOWPARK_CONTAINER_SERVICES | Yes | Yes |
| AI_SERVICES | Yes | **No** |
| DATA_QUALITY_MONITORING | Yes | Yes |
| SERVERLESS_TASK | Yes | Yes |
| AUTO_CLUSTERING | Yes | Yes |
| MATERIALIZED_VIEW | Yes | Yes |
| SEARCH_OPTIMIZATION | Yes | Yes |
| PIPE | Yes | Yes |
| QUERY_ACCELERATION | Yes | Yes |
| REPLICATION | Yes | Yes |
| HYBRID_TABLE_REQUESTS | Yes | **No** |
| SNOWPIPE_STREAMING | Yes | Yes |
| SERVERLESS_ALERTS | Yes | Yes |

---

## Budget Inspection Methods

> See `skills/budget/SKILL.md` section 6 ("View Budget Status") for the full list of inspection methods (`GET_CONFIG`, `GET_SPENDING_LIMIT`, `GET_LINKED_RESOURCES`, `GET_BUDGET_SCOPE`, `REFRESH_USAGE`, etc.)

---

## Event Telemetry

### Enable Budget Event Logging

```sql
-- Enable at account level
ALTER ACCOUNT SET ENABLE_BUDGET_EVENT_LOGGING = TRUE;
```

### Query Budget Events

```sql
SELECT *
FROM SNOWFLAKE.TELEMETRY.EVENTS
WHERE SCOPE = 'snow.cost.budget'
    AND TIMESTAMP >= DATEADD('day', -7, CURRENT_TIMESTAMP())
ORDER BY TIMESTAMP DESC;
```

### Event Names

| Event | Description |
|-------|-------------|
| `BUDGET_UNVERIFIED_RECIPIENTS` | Email recipients not verified |
| `BUDGET_INVALID_INTEGRATION` | Notification integration error |
| `BUDGET_THRESHOLD_EXCEEDED` | Spending exceeded threshold |
| `BUDGET_CUSTOM_ACTION_FAILED` | Custom action procedure failed |
| `BUDGET_CYCLE_START_ACTION_FAILED` | Cycle-start action failed |

---

## Limits & Guardrails

### Global Limits

| Limit | Value |
|-------|-------|
| Max custom budgets per account | 100 |
| Max notification integrations per budget | 10 (queue/webhook) |
| Budget instance replication | Not supported |
| Hybrid tables in custom budgets | Not supported |
| Max tags per SET_RESOURCE_TAGS call | 20 |
| Cycle-start action timeout | 30 minutes |

### Required Account Parameters

Budgets may malfunction if these parameters are changed:

```sql
-- Check current values
SHOW PARAMETERS LIKE 'AUTOCOMMIT' IN ACCOUNT;
SHOW PARAMETERS LIKE 'TIMESTAMP_INPUT_FORMAT' IN ACCOUNT;
SHOW PARAMETERS LIKE 'DATE_INPUT_FORMAT' IN ACCOUNT;

-- Required values
-- AUTOCOMMIT: TRUE (or unset)
-- TIMESTAMP_INPUT_FORMAT: AUTO (or unset)
-- DATE_INPUT_FORMAT: AUTO (or unset)
```

### Tag Latency

- `ACCOUNT_USAGE.TAG_REFERENCES` has up to **2 hour latency**
- Newly tagged objects may not appear in budget immediately
- Budget refresh interval adds additional delay (default 6.5h)

### Regional Availability

- Budgets feature may not be available in Government regions
- Some behaviors may differ by region

---

## Common Errors & Solutions

### Activation Errors

**"Account budget is not activated"**
```sql
CALL SNOWFLAKE.LOCAL.ACCOUNT_ROOT_BUDGET!ACTIVATE();
```

**"Activation failed - AUTOCOMMIT is FALSE"**
```sql
ALTER ACCOUNT SET AUTOCOMMIT = TRUE;
-- Then retry activation
```

### Permission Errors

**"Insufficient privileges to activate account budget"**
```sql
USE ROLE ACCOUNTADMIN;
-- Or grant to custom role:
GRANT APPLICATION ROLE SNOWFLAKE.BUDGET_ADMIN TO ROLE my_role;
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE my_role;
```

**"Cannot create budget"**
```sql
-- Ensure all required grants:
GRANT DATABASE ROLE SNOWFLAKE.BUDGET_CREATOR TO ROLE my_role;
GRANT USAGE ON DATABASE budgets_db TO ROLE my_role;
GRANT USAGE ON SCHEMA budgets_db.budgets_schema TO ROLE my_role;
GRANT CREATE SNOWFLAKE.CORE.BUDGET ON SCHEMA budgets_db.budgets_schema TO ROLE my_role;
```

**"Cannot add resource to budget"**
```sql
GRANT APPLYBUDGET ON WAREHOUSE my_wh TO ROLE budget_owner;
```

### Resource Errors

**"Object already in another budget"**
- Direct-added objects can only be in ONE budget
- Adding to a second budget removes from first (no warning)
- **Solution**: Use tags for multi-budget membership

**"ADD_RESOURCE not supported"**
- Account budget cannot use ADD_RESOURCE
- It automatically monitors all usage
- **Solution**: Create a custom budget for specific object tracking

**"Tag not found"**
```sql
-- Verify tag exists (never use SHOW TAGS ... IN ACCOUNT — it is extremely slow)
SELECT DISTINCT TAG_DATABASE, TAG_SCHEMA, TAG_NAME
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
WHERE TAG_NAME = '<tag_name>';
-- Use fully qualified name
SYSTEM$REFERENCE('TAG', 'mydb.tags.cost_center', 'SESSION', 'applybudget')
```

**"Failure to add specific resources"**
- When adding all resources of a type, some individual resources may fail
- The error message enumerates which specific resources failed

**"Shared attribution not reflecting expected costs"**
1. Check resources are added:
   ```sql
   CALL my_budget!GET_BUDGET_SCOPE();
   ```
2. Verify resource tags are correct (tag propagation has up to 2h latency):
   ```sql
   SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
   WHERE DOMAIN = 'USER' AND TAG_NAME = 'COST_CENTER';
   ```
4. Trigger a recalculation:
   ```sql
   CALL my_budget!REFRESH_USAGE();
   ```

### Notification Errors

**"Email address not verified"**
- Each recipient must verify email in Snowsight
- Profile → Email → Verify

**"Integration not found"**
```sql
-- Verify integration exists
SHOW NOTIFICATION INTEGRATIONS;
-- Grant to Snowflake
GRANT USAGE ON INTEGRATION my_integration TO APPLICATION SNOWFLAKE;
```

**"Maximum integrations reached"**
- Limit: 10 queue/webhook integrations per budget
- Remove unused first:
```sql
CALL my_budget!REMOVE_NOTIFICATION_INTEGRATION('old_integration');
```

### Action Errors

**"Custom action not firing"**
1. Check spending limit is set:
   ```sql
   CALL my_budget!GET_SPENDING_LIMIT();
   ```
2. Verify procedure grant:
   ```sql
   SHOW GRANTS ON PROCEDURE mydb.myschema.my_action();
   ```
3. Check procedure compiles:
   ```sql
   CALL mydb.myschema.my_action();
   ```

**"Cycle-start action timeout"**
- Procedure must complete within 30 minutes
- Optimize or break into smaller operations

### Query Errors

---

## Debugging Checklist

1. **Budget activated/created?**
   ```sql
   SELECT SYSTEM$SHOW_BUDGETS_IN_ACCOUNT();
   ```

2. **Spending limit set?**
   ```sql
   CALL my_budget!GET_SPENDING_LIMIT();
   ```

3. **Resources added?** (custom budget)
   ```sql
   CALL my_budget!GET_BUDGET_SCOPE();
   ```

4. **Notifications configured?**
   ```sql
   CALL my_budget!GET_NOTIFICATION_INTEGRATION_NAME();
   CALL my_budget!GET_NOTIFICATION_INTEGRATIONS();
   ```

6. **Correct privileges?**
   ```sql
   SHOW GRANTS TO ROLE my_role;
   ```

7. **Account parameters OK?**
   ```sql
   SHOW PARAMETERS LIKE 'AUTOCOMMIT' IN ACCOUNT;
   ```
