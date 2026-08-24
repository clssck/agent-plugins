# View Budget Status & Usage

Workflow for inspecting budget configuration, spending, and health.

> **See**: Parent `SKILL.md` for account vs custom decision, method reference, reference files, verification queries, and summary table format.

---

## Workflow

### Step 1: Identify Target

If the user asks about a specific budget, use that. Otherwise, list all budgets:

```sql
SHOW SNOWFLAKE.CORE.BUDGET INSTANCES IN ACCOUNT;
```

If no budgets exist, inform the user and offer to create one (route to `create/SKILL.md`).

If the user asks about the account budget, use `SNOWFLAKE.LOCAL.ACCOUNT_ROOT_BUDGET` as the target.

---

### Step 2: Show Configuration

For **custom budgets**, run the shared verification queries from parent `SKILL.md` and present the summary table. Apply graceful failure handling per parent `SKILL.md` if the user-level sharing calls fail.

```sql
CALL {budget_fqn}!GET_SPENDING_LIMIT();
CALL {budget_fqn}!GET_BUDGET_SCOPE();
CALL {budget_fqn}!GET_SHARED_RESOURCES();
```

For **account budget**, scope/resources are not applicable — only the spending limit and usage methods are available. Always call both:

```sql
-- Spending limit
CALL SNOWFLAKE.LOCAL.ACCOUNT_ROOT_BUDGET!GET_SPENDING_LIMIT();

-- Current month spending by service type — prefer this over SNOWFLAKE.ACCOUNT_USAGE views (budget-scoped, more accurate)
SELECT SERVICE_TYPE, ROUND(SUM(CREDITS_USED), 2) AS CREDITS_USED
FROM TABLE(SNOWFLAKE.LOCAL.ACCOUNT_ROOT_BUDGET!GET_SERVICE_TYPE_USAGE_V2(
    '<current_year_month>', '<next_month>'
))
GROUP BY SERVICE_TYPE
ORDER BY CREDITS_USED DESC;
```

---

### Step 3: Show Usage (additional detail, if requested)

> **Prefer `GET_SERVICE_TYPE_USAGE_V2`** over `SNOWFLAKE.ACCOUNT_USAGE` views (e.g. `METERING_HISTORY`, `BUDGET_DETAILS`) for spending data — it returns budget-scoped attribution rather than account-wide aggregates.

> **Important**: `GET_SERVICE_TYPE_USAGE` is **deprecated**. Always use `GET_SERVICE_TYPE_USAGE_V2` instead.
> - It is a **table function** — use `SELECT ... FROM TABLE(...)`, not `CALL`.
> - It takes two string arguments: start month (`'YYYY-MM'`) and end month (`'YYYY-MM'`), where end month is **exclusive**.
> - Columns returned: `SERVICE_TYPE`, `ENTITY_TYPE`, `ENTITY_ID`, `NAME`, `CREDITS_USED`, `CREDITS_COMPUTE`, `CREDITS_CLOUD`.

```sql
-- Current month spending by service type
SELECT SERVICE_TYPE, ROUND(SUM(CREDITS_USED), 2) AS CREDITS_USED
FROM TABLE({budget_fqn}!GET_SERVICE_TYPE_USAGE_V2(
    '{start_month}', '{end_month}'
))
GROUP BY SERVICE_TYPE
ORDER BY CREDITS_USED DESC;
```

For example, to get February 2026 usage:

```sql
SELECT SERVICE_TYPE, ROUND(SUM(CREDITS_USED), 2) AS CREDITS_USED
FROM TABLE({budget_fqn}!GET_SERVICE_TYPE_USAGE_V2(
    '2026-02', '2026-03'
))
GROUP BY SERVICE_TYPE
ORDER BY CREDITS_USED DESC;
```

To get total spending:

```sql
SELECT ROUND(SUM(CREDITS_USED), 2) AS TOTAL_CREDITS_SPENT
FROM TABLE({budget_fqn}!GET_SERVICE_TYPE_USAGE_V2(
    '{start_month}', '{end_month}'
));
```

To get a multi-month trend (e.g., last 3 months):

```sql
SELECT SERVICE_TYPE, ROUND(SUM(CREDITS_USED), 2) AS CREDITS_USED
FROM TABLE({budget_fqn}!GET_SERVICE_TYPE_USAGE_V2(
    '2025-12', '2026-03'
))
GROUP BY SERVICE_TYPE
ORDER BY CREDITS_USED DESC;
```

---

### Step 4: Next Steps

After presenting status, offer:

```
What would you like to do?
1. Modify this budget (change limits, add/remove resources)
2. View another budget
3. Done
```

If option 1, route to `modify/SKILL.md`.
