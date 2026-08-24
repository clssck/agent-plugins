# REMAINING_BALANCE_DAILY

Source: `SNOWFLAKE.ORGANIZATION_USAGE.REMAINING_BALANCE_DAILY`

**ORGADMIN role required.** If the user lacks access, defer to the **organization-management** skill for role troubleshooting.

## Schema

| Column | Type | Meaning |
|--------|------|---------|
| `ORGANIZATION_NAME` | VARCHAR | Name of the organization |
| `CONTRACT_NUMBER` | VARCHAR | Contract number for the organization |
| `DATE` | DATE | Date of the balance snapshot (UTC). This is the **end-of-day** balance |
| `CURRENCY` | VARCHAR | Currency of the balance amounts |
| `FREE_USAGE_BALANCE` | NUMBER(38,2) | Remaining free-usage credits in currency (end-of-day) |
| `CAPACITY_BALANCE` | NUMBER(38,2) | Remaining capacity commitment in currency (end-of-day) |
| `ON_DEMAND_CONSUMPTION_BALANCE` | NUMBER(38,2) | On-demand charges accrued — **negative value** (e.g. -250) until the invoice is paid. Resets after month-close (typically 3rd–4th of next month) |
| `ROLLOVER_BALANCE` | NUMBER(38,2) | Unused credits rolled over from a prior contract term. Calculated as `SUM(AMOUNT)` from CONTRACT_ITEMS minus `SUM(USAGE_IN_CURRENCY)` from USAGE_IN_CURRENCY_DAILY at end of prior term |
| `MARKETPLACE_CAPACITY_DRAWDOWN_BALANCE` | NUMBER(38,2) | Portion of CAPACITY_BALANCE available for Snowflake Marketplace purchases |

---

## Important behavior

- Data available from June 2020 onward; contact Snowflake Support for earlier data.
- **Latency**: up to **72 hours**.
- Until month-close, values for a given day can change due to end-of-month adjustments, credits, or contract amendments.
- `ON_DEMAND_CONSUMPTION_BALANCE` resets after month-close once invoiced and paid.
- Reseller customers **cannot** access this view.
- If multiple organizations share a capacity contract, only the **primary (funding) organization** can access this view.

---

## Queries

### Current remaining balance (latest snapshot)

```sql
SELECT
    DATE,
    CONTRACT_NUMBER,
    CAPACITY_BALANCE,
    FREE_USAGE_BALANCE,
    ROLLOVER_BALANCE,
    ON_DEMAND_CONSUMPTION_BALANCE,
    CURRENCY
FROM SNOWFLAKE.ORGANIZATION_USAGE.REMAINING_BALANCE_DAILY
WHERE DATE = (SELECT MAX(DATE) FROM SNOWFLAKE.ORGANIZATION_USAGE.REMAINING_BALANCE_DAILY)
ORDER BY CONTRACT_NUMBER;
```

### Remaining balance matching a billing statement

The statement's **Remaining Balance** equals `CAPACITY_BALANCE + FREE_USAGE_BALANCE + ROLLOVER_BALANCE`. Do **not** include `ON_DEMAND_CONSUMPTION_BALANCE` or `MARKETPLACE_CAPACITY_DRAWDOWN_BALANCE`.

Replace the date with the last day of the statement month.

```sql
SELECT
    DATE,
    CONTRACT_NUMBER,
    (CAPACITY_BALANCE + FREE_USAGE_BALANCE + ROLLOVER_BALANCE) AS REMAINING_BALANCE,
    CURRENCY
FROM SNOWFLAKE.ORGANIZATION_USAGE.REMAINING_BALANCE_DAILY
WHERE DATE = LAST_DAY(TO_DATE('2024-01-01'));
```

### Balance trend over time (daily)

```sql
SELECT
    DATE,
    CAPACITY_BALANCE,
    FREE_USAGE_BALANCE,
    ROLLOVER_BALANCE,
    (CAPACITY_BALANCE + FREE_USAGE_BALANCE + ROLLOVER_BALANCE) AS TOTAL_REMAINING,
    ON_DEMAND_CONSUMPTION_BALANCE,
    CURRENCY
FROM SNOWFLAKE.ORGANIZATION_USAGE.REMAINING_BALANCE_DAILY
WHERE DATE >= DATEADD('day', -90, CURRENT_DATE)
ORDER BY DATE;
```

### On-demand accrual this month

```sql
SELECT
    DATE,
    ON_DEMAND_CONSUMPTION_BALANCE,
    CURRENCY
FROM SNOWFLAKE.ORGANIZATION_USAGE.REMAINING_BALANCE_DAILY
WHERE DATE_TRUNC('month', DATE) = DATE_TRUNC('month', CURRENT_DATE)
ORDER BY DATE;
```
