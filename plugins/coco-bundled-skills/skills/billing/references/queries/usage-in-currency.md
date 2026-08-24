# USAGE_IN_CURRENCY_DAILY

Source: `SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY`

**ORGADMIN role required.** If the user lacks access, defer to the **organization-management** skill for role troubleshooting.

## Schema

| Column | Type | Meaning |
|--------|------|---------|
| `USAGE_DATE` | DATE | Date of usage |
| `ACCOUNT_NAME` | TEXT | Account that consumed the credits |
| `ACCOUNT_LOCATOR` | TEXT | Account locator identifier |
| `SERVICE_TYPE` | TEXT | Service (COMPUTE, STORAGE, SERVERLESS_TASK, CORTEX, etc.) |
| `USAGE_TYPE` | TEXT | Sub-type within the service |
| `USAGE` | NUMBER | Credits used |
| `USAGE_IN_CURRENCY` | NUMBER | Dollar value of the usage |
| `CURRENCY` | TEXT | Currency code (e.g., USD) |
| `BALANCE_SOURCE` | TEXT | Which contract bucket paid for this usage: `capacity`, `rollover`, `free usage`, `overage`, `rebate` |
| `BILLING_TYPE` | TEXT | `USAGE`, `REBATE`, or `ADJUSTMENT` |
| `IS_ADJUSTMENT` | BOOLEAN | `TRUE` = billing correction row. Include by default; only exclude if user asks for raw usage without corrections |
| `CONTRACT_NUMBER` | TEXT | Contract identifier |
| `SERVICE_LEVEL` | TEXT | Account edition (STANDARD, ENTERPRISE, BUSINESS_CRITICAL) |
| `REGION` | TEXT | Cloud region of the account |

---

## Queries

### How much am I spending? (total org spend, last 30 days)

```sql
-- Dollar spend query: use USAGE_IN_CURRENCY_DAILY (not METERING_HISTORY)
SELECT
    SUM(USAGE_IN_CURRENCY) AS TOTAL_SPEND,  -- dollar amount, not credits
    CURRENCY
FROM SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY
WHERE USAGE_DATE >= DATEADD('day', -30, CURRENT_DATE)
GROUP BY CURRENCY;
```

### Which accounts cost the most? (last 30 days)

```sql
SELECT
    ACCOUNT_NAME,
    SUM(USAGE_IN_CURRENCY) AS TOTAL_SPEND,
    CURRENCY
FROM SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY
WHERE USAGE_DATE >= DATEADD('day', -30, CURRENT_DATE)

GROUP BY ACCOUNT_NAME, CURRENCY
ORDER BY TOTAL_SPEND DESC;
```

### Top accounts as percentage of total org spend

```sql
WITH total AS (
    SELECT SUM(USAGE_IN_CURRENCY) AS ORG_TOTAL, CURRENCY
    FROM SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY
    WHERE USAGE_DATE >= DATEADD('day', -30, CURRENT_DATE)
    
    GROUP BY CURRENCY
)
SELECT
    u.ACCOUNT_NAME,
    SUM(u.USAGE_IN_CURRENCY) AS ACCOUNT_SPEND,
    t.ORG_TOTAL,
    ROUND(100.0 * SUM(u.USAGE_IN_CURRENCY) / NULLIF(t.ORG_TOTAL, 0), 1) AS PCT_OF_ORG,
    u.CURRENCY
FROM SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY u
JOIN total t ON u.CURRENCY = t.CURRENCY
WHERE u.USAGE_DATE >= DATEADD('day', -30, CURRENT_DATE)

GROUP BY u.ACCOUNT_NAME, t.ORG_TOTAL, u.CURRENCY
ORDER BY ACCOUNT_SPEND DESC;
```

### What services cost the most? (by service type, last 30 days)

```sql
-- Dollar spend by service type: use USAGE_IN_CURRENCY_DAILY (not METERING_HISTORY)
SELECT
    SERVICE_TYPE,
    SUM(USAGE_IN_CURRENCY) AS TOTAL_SPEND,  -- dollar amount, not credits
    CURRENCY
FROM SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY
WHERE USAGE_DATE >= DATEADD('day', -30, CURRENT_DATE)
GROUP BY SERVICE_TYPE, CURRENCY
ORDER BY TOTAL_SPEND DESC;
```

### Spend by account and service type

```sql
SELECT
    ACCOUNT_NAME,
    SERVICE_TYPE,
    SUM(USAGE_IN_CURRENCY) AS TOTAL_SPEND,
    CURRENCY
FROM SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY
WHERE USAGE_DATE >= DATEADD('day', -30, CURRENT_DATE)

GROUP BY ACCOUNT_NAME, SERVICE_TYPE, CURRENCY
ORDER BY ACCOUNT_NAME, TOTAL_SPEND DESC;
```

### Am I on-demand or capacity? (by BALANCE_SOURCE)

```sql
SELECT
    BALANCE_SOURCE,
    SUM(USAGE) AS TOTAL_CREDITS,
    SUM(USAGE_IN_CURRENCY) AS TOTAL_SPEND,
    CURRENCY
FROM SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY
WHERE USAGE_DATE >= DATEADD('day', -30, CURRENT_DATE)

GROUP BY BALANCE_SOURCE, CURRENCY
ORDER BY TOTAL_SPEND DESC;
```

### On-demand overage detail (what is being billed at on-demand rates)

```sql
SELECT
    ACCOUNT_NAME,
    SERVICE_TYPE,
    SUM(USAGE) AS CREDITS,
    SUM(USAGE_IN_CURRENCY) AS SPEND,
    CURRENCY
FROM SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY
WHERE USAGE_DATE >= DATEADD('day', -30, CURRENT_DATE)

  AND LOWER(BALANCE_SOURCE) = 'overage'
GROUP BY ACCOUNT_NAME, SERVICE_TYPE, CURRENCY
ORDER BY SPEND DESC;
```

### How is my spend trending? (month-over-month)

```sql
-- Monthly dollar spend trend: use USAGE_IN_CURRENCY_DAILY (not METERING_HISTORY)
SELECT
    DATE_TRUNC('month', USAGE_DATE) AS MONTH,
    SUM(USAGE_IN_CURRENCY) AS MONTHLY_SPEND,  -- dollar amount, not credits
    CURRENCY
FROM SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY
WHERE USAGE_DATE >= DATEADD('month', -6, CURRENT_DATE)
GROUP BY 1, CURRENCY
ORDER BY MONTH DESC;
```

### Month-over-month by account

```sql
SELECT
    DATE_TRUNC('month', USAGE_DATE) AS MONTH,
    ACCOUNT_NAME,
    SUM(USAGE_IN_CURRENCY) AS MONTHLY_SPEND,
    CURRENCY
FROM SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY
WHERE USAGE_DATE >= DATEADD('month', -6, CURRENT_DATE)

GROUP BY 1, 2, CURRENCY
ORDER BY MONTH DESC, MONTHLY_SPEND DESC;
```

### What's on my bill this month? (current month breakdown)

```sql
SELECT
    ACCOUNT_NAME,
    SERVICE_TYPE,
    BALANCE_SOURCE,
    BILLING_TYPE,
    SUM(USAGE) AS TOTAL_CREDITS,
    SUM(USAGE_IN_CURRENCY) AS TOTAL_CHARGES,
    CURRENCY
FROM SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY
WHERE DATE_TRUNC('month', USAGE_DATE) = DATE_TRUNC('month', CURRENT_DATE)
GROUP BY 1, 2, 3, 4, CURRENCY
ORDER BY TOTAL_CHARGES DESC;
```

---

## Billing Statement Reconciliation

Use these queries to reconcile figures on a Snowflake billing usage statement against actual data. Small rounding differences (a few cents to less than $10) are normal.

### Reconcile "Total Consumed" from billing statement

The statement's **Total Consumed** is **cumulative** from contract start through the statement month end — NOT just a single month. Overage is billed separately and must be excluded.

Replace the date with the last day of the statement month.

```sql
SELECT
    CONTRACT_NUMBER,
    SUM(USAGE_IN_CURRENCY) AS TOTAL_CONSUMED
FROM SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY
WHERE USAGE_DATE <= LAST_DAY(TO_DATE('2024-01-01'))
  AND LOWER(BALANCE_SOURCE) != 'overage'
GROUP BY CONTRACT_NUMBER
ORDER BY CONTRACT_NUMBER;
```

**Critical**: The date range is `<= LAST_DAY(...)` with no lower bound — "Total Consumed" accumulates from when the contract started. Also group by `CONTRACT_NUMBER` since an org may have multiple contracts.

### Reconcile monthly usage by account

Accounts on the statement use `account_locator-region` format, not `ACCOUNT_NAME`.

```sql
SELECT
    CONTRACT_NUMBER,
    DATE_TRUNC('month', USAGE_DATE) AS USAGE_MONTH,
    CONCAT(ACCOUNT_LOCATOR, '-', REGION) AS ACCOUNT_NAME,
    SUM(USAGE_IN_CURRENCY) AS TOTAL_CONSUMED
FROM SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY
WHERE DATE_TRUNC('month', USAGE_DATE) = DATE_TRUNC('month', TO_DATE('2024-01-01'))
  AND LOWER(BALANCE_SOURCE) != 'overage'
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;
```
