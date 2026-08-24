# CONTRACT_ITEMS

Source: `SNOWFLAKE.ORGANIZATION_USAGE.CONTRACT_ITEMS`

**ORGADMIN role required.** If the user lacks access, defer to the **organization-management** skill for role troubleshooting.

## Schema

| Column | Type | Meaning |
|--------|------|---------|
| `ORGANIZATION_NAME` | VARCHAR | Name of the organization |
| `CONTRACT_NUMBER` | VARCHAR | Snowflake contract number |
| `START_DATE` | DATE | Start date of the contract or the date the contract item goes into effect |
| `END_DATE` | DATE | End date of the contract or the date the contract item stops being used |
| `EXPIRATION_DATE` | DATE | Date after which either the renewal contract goes into effect (if signed within 30 days) or the Snowflake relationship is terminated |
| `CONTRACT_ITEM` | VARCHAR | Type of line item: `capacity`, `additional capacity`, or `free usage` |
| `CURRENCY` | VARCHAR | Currency for the contract item |
| `AMOUNT` | NUMBER(38,2) | Dollar amount for the contract item (in CURRENCY, **not credits**) |
| `CONTRACT_MODIFIED_DATE` | DATE | Date (UTC) the contract item was last modified |

---

## Important behavior

- Only the **active contract** is shown.
- Data available from June 2020 onward; contact Snowflake Support for earlier data.
- **Latency**: up to **24 hours**.
- Reseller customers **cannot** access this view.
- If multiple organizations share a capacity contract, only the **primary (funding) organization** can access this view.
- `AMOUNT` is in **currency** (e.g. USD), not credits.
- `START_DATE` is the contract effective (start) date per line item; `END_DATE` is the date that contract item stops being used; `EXPIRATION_DATE` is the overall contract termination date (the Snowflake relationship terminates if not renewed within 30 days of `EXPIRATION_DATE`). These are distinct: `END_DATE` tracks individual line-item lifecycle, while `EXPIRATION_DATE` governs the entire relationship.
- **NULL dates**: Not all contracts have `EXPIRATION_DATE` or `END_DATE` set. Do **not** filter these contracts out with `WHERE … IS NOT NULL` — include them and tell the user when no termination/expiration date is recorded. Suggest they contact their Snowflake account team for clarification.

---

## Handling contracts with no termination date

When a user asks about contract **termination**, **expiration**, **renewal**, or **days remaining** and the results contain `NULL` for `EXPIRATION_DATE` (or derived columns like `TERMINATION_DATE`, `DAYS_REMAINING`, `RENEWAL_STATUS`):

1. **Do not silently omit** those contracts from the results.
2. **Explicitly tell the user** that their contract does not have a termination/expiration date recorded in Snowflake.
3. **Recommend** they contact their Snowflake account team for contract term details.

Example response when `EXPIRATION_DATE` is `NULL`:

> Your contract (CONTRACT_NUMBER: X) does not have a termination date recorded. This means no expiration date is set in Snowflake's CONTRACT_ITEMS view. Please contact your Snowflake account team for details about your contract terms and renewal timeline.

---

## Queries

### View current contract details

```sql
SELECT
    CONTRACT_NUMBER,
    CONTRACT_ITEM,
    AMOUNT,
    CURRENCY,
    START_DATE,
    END_DATE,
    EXPIRATION_DATE
FROM SNOWFLAKE.ORGANIZATION_USAGE.CONTRACT_ITEMS
ORDER BY CONTRACT_NUMBER, START_DATE;
```

### Total contract value

```sql
SELECT
    CONTRACT_NUMBER,
    SUM(AMOUNT) AS TOTAL_CONTRACT_VALUE,
    CURRENCY,
    MIN(START_DATE) AS CONTRACT_START,
    MAX(END_DATE) AS CONTRACT_END,
    MAX(EXPIRATION_DATE) AS EXPIRATION
FROM SNOWFLAKE.ORGANIZATION_USAGE.CONTRACT_ITEMS
GROUP BY CONTRACT_NUMBER, CURRENCY
ORDER BY CONTRACT_NUMBER;
```

### Contract utilization (how much of the contract has been consumed)

Joins with `USAGE_IN_CURRENCY_DAILY` to compare total consumed against total contract amount. Excludes overage since overage is billed separately.

```sql
WITH contract AS (
    SELECT
        CONTRACT_NUMBER,
        SUM(AMOUNT) AS TOTAL_CONTRACT_VALUE,
        CURRENCY
    FROM SNOWFLAKE.ORGANIZATION_USAGE.CONTRACT_ITEMS
    GROUP BY CONTRACT_NUMBER, CURRENCY
),
consumed AS (
    SELECT
        CONTRACT_NUMBER,
        SUM(USAGE_IN_CURRENCY) AS TOTAL_CONSUMED,
        CURRENCY
    FROM SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY
    WHERE LOWER(BALANCE_SOURCE) != 'overage'
    GROUP BY CONTRACT_NUMBER, CURRENCY
)
SELECT
    c.CONTRACT_NUMBER,
    c.TOTAL_CONTRACT_VALUE,
    COALESCE(u.TOTAL_CONSUMED, 0) AS TOTAL_CONSUMED,
    c.TOTAL_CONTRACT_VALUE - COALESCE(u.TOTAL_CONSUMED, 0) AS REMAINING,
    ROUND(100.0 * COALESCE(u.TOTAL_CONSUMED, 0) / NULLIF(c.TOTAL_CONTRACT_VALUE, 0), 1) AS PCT_UTILIZED,
    c.CURRENCY
FROM contract c
LEFT JOIN consumed u ON c.CONTRACT_NUMBER = u.CONTRACT_NUMBER AND c.CURRENCY = u.CURRENCY
ORDER BY c.CONTRACT_NUMBER;
```

### Days until contract expiration

```sql
SELECT
    CONTRACT_NUMBER,
    MAX(EXPIRATION_DATE) AS EXPIRATION_DATE,
    DATEDIFF('day', CURRENT_DATE, MAX(EXPIRATION_DATE)) AS DAYS_REMAINING
FROM SNOWFLAKE.ORGANIZATION_USAGE.CONTRACT_ITEMS
GROUP BY CONTRACT_NUMBER
ORDER BY CONTRACT_NUMBER;
```

> **Note:** Contracts with no `EXPIRATION_DATE` will show `NULL` for both `EXPIRATION_DATE` and `DAYS_REMAINING`. This typically means the contract has no fixed expiration — inform the user rather than silently omitting those contracts.

### Contract effective (start) date

`START_DATE` is when each contract item goes into effect. `MIN(START_DATE)` across all items gives the overall contract start date.

**Always include this explanation in your response:** "`START_DATE` is the date the contract item went into effect — this is the contract effective (start) date."

```sql
SELECT
    CONTRACT_NUMBER,
    MIN(START_DATE) AS CONTRACT_EFFECTIVE_DATE,
    MAX(END_DATE) AS CONTRACT_END_DATE
FROM SNOWFLAKE.ORGANIZATION_USAGE.CONTRACT_ITEMS
WHERE START_DATE IS NOT NULL
GROUP BY CONTRACT_NUMBER
ORDER BY CONTRACT_NUMBER;
```

### Contract termination date

If the contract is not renewed within 30 days of `EXPIRATION_DATE`, the Snowflake relationship is terminated. This is the effective termination date for the contract.

```sql
SELECT
    CONTRACT_NUMBER,
    MAX(EXPIRATION_DATE) AS TERMINATION_DATE,
    DATEDIFF('day', CURRENT_DATE, MAX(EXPIRATION_DATE)) AS DAYS_UNTIL_TERMINATION
FROM SNOWFLAKE.ORGANIZATION_USAGE.CONTRACT_ITEMS
GROUP BY CONTRACT_NUMBER
ORDER BY CONTRACT_NUMBER;
```

> **Note:** If `TERMINATION_DATE` is `NULL`, the contract has no termination date set. Tell the user that no termination date is recorded for that contract and suggest they contact their Snowflake account team for details.

### Contract duration

Total span of the contract from earliest start to latest end, in both days and months.

```sql
SELECT
    CONTRACT_NUMBER,
    MIN(START_DATE) AS CONTRACT_START,
    MAX(END_DATE) AS CONTRACT_END,
    MAX(EXPIRATION_DATE) AS CONTRACT_EXPIRATION,
    DATEDIFF('day', MIN(START_DATE), COALESCE(MAX(END_DATE), MAX(EXPIRATION_DATE))) AS DURATION_DAYS,
    DATEDIFF('month', MIN(START_DATE), COALESCE(MAX(END_DATE), MAX(EXPIRATION_DATE))) AS DURATION_MONTHS
FROM SNOWFLAKE.ORGANIZATION_USAGE.CONTRACT_ITEMS
WHERE START_DATE IS NOT NULL
GROUP BY CONTRACT_NUMBER
ORDER BY CONTRACT_NUMBER;
```

### Contract renewal window

The 30-day renewal window starts at `EXPIRATION_DATE`. If the contract is not renewed within 30 days, the Snowflake relationship terminates.

```sql
SELECT
    CONTRACT_NUMBER,
    MAX(EXPIRATION_DATE) AS RENEWAL_WINDOW_OPENS,
    DATEADD('day', 30, MAX(EXPIRATION_DATE)) AS RENEWAL_DEADLINE,
    DATEDIFF('day', CURRENT_DATE, MAX(EXPIRATION_DATE)) AS DAYS_UNTIL_RENEWAL_WINDOW,
    CASE
        WHEN MAX(EXPIRATION_DATE) IS NULL THEN 'No Expiration Date Set'
        WHEN CURRENT_DATE < MAX(EXPIRATION_DATE) THEN 'Active'
        WHEN CURRENT_DATE BETWEEN MAX(EXPIRATION_DATE) AND DATEADD('day', 30, MAX(EXPIRATION_DATE)) THEN 'In Renewal Window'
        ELSE 'Past Renewal Deadline'
    END AS RENEWAL_STATUS
FROM SNOWFLAKE.ORGANIZATION_USAGE.CONTRACT_ITEMS
GROUP BY CONTRACT_NUMBER
ORDER BY CONTRACT_NUMBER;
```

### Contract last modified date

Shows when each contract item was last modified. Useful for tracking recent contract changes or amendments.

```sql
SELECT
    CONTRACT_NUMBER,
    CONTRACT_ITEM,
    AMOUNT,
    CURRENCY,
    CONTRACT_MODIFIED_DATE,
    START_DATE,
    END_DATE
FROM SNOWFLAKE.ORGANIZATION_USAGE.CONTRACT_ITEMS
WHERE CONTRACT_MODIFIED_DATE IS NOT NULL
ORDER BY CONTRACT_MODIFIED_DATE DESC;
```
