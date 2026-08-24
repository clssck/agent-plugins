# Budgets Queries

Queries for monitoring and analyzing Snowflake budget status, including over-limit and at-risk budgets.

**Semantic keywords:** budgets, budget limit, over budget, budget exceeded, projected overspend, budget risk, spending limit, credit limit, budget alerts, recently created budgets

---

### Budgets Over Spending Limit

**Triggered by:** "Are any of my Budgets over their spending limit?", "over budget", "budget exceeded"

```sql
SELECT 
    budget_name, 
    database_name, 
    schema_name, 
    ROUND(current_month_spending, 2) AS current_month_spending, 
    credit_limit, 
    ROUND(current_month_spending - credit_limit, 2) AS over_by, 
    ROUND((current_month_spending - credit_limit) / NULLIF(credit_limit, 0) * 100, 2) AS percent_over 
FROM SNOWFLAKE.ACCOUNT_USAGE.BUDGET_DETAILS 
WHERE current_month_spending > credit_limit 
ORDER BY over_by DESC;
```

---

### Budgets at Risk of Exceeding Limit (Projected)

**Triggered by:** "Which Budgets are at risk of going over their spending limit?", "projected overspend", "budget risk"

```sql
WITH m AS (
    SELECT DATE_TRUNC('month', CURRENT_TIMESTAMP()) AS month_start, 
        DATEADD('month', 1, DATE_TRUNC('month', CURRENT_TIMESTAMP())) AS next_month_start
), 
r AS (
    SELECT DATEDIFF('second', m.month_start, CURRENT_TIMESTAMP())::FLOAT / 
        NULLIF(DATEDIFF('second', m.month_start, m.next_month_start), 0) AS ratio 
    FROM m
) 
SELECT 
    bd.budget_name, 
    bd.database_name, 
    bd.schema_name, 
    bd.credit_limit, 
    ROUND(bd.current_month_spending, 2) AS current_month_spending, 
    ROUND(r.ratio * bd.credit_limit, 2) AS expected_spend_to_date, 
    ROUND(CASE WHEN r.ratio > 0 THEN bd.current_month_spending / r.ratio ELSE NULL END, 2) AS projected_month_end_spend, 
    ROUND((CASE WHEN r.ratio > 0 THEN bd.current_month_spending / r.ratio ELSE NULL END) - bd.credit_limit, 2) AS projected_over_by 
FROM SNOWFLAKE.ACCOUNT_USAGE.BUDGET_DETAILS bd 
CROSS JOIN r 
WHERE r.ratio > 0 
    AND (bd.current_month_spending / r.ratio) > bd.credit_limit 
ORDER BY projected_over_by DESC;
```

---

### Recently Created Budgets

**Triggered by:** "What Budgets were created in the past 3 months?", "new budgets", "recently created budgets"

```sql
SELECT 
    budget_name, 
    database_name, 
    schema_name, 
    created_on 
FROM SNOWFLAKE.ACCOUNT_USAGE.BUDGET_DETAILS 
WHERE created_on >= DATEADD('month', -3, CURRENT_TIMESTAMP()) 
ORDER BY created_on DESC;
```
