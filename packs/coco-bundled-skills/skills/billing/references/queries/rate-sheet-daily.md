# RATE_SHEET_DAILY

Source: `SNOWFLAKE.ORGANIZATION_USAGE.RATE_SHEET_DAILY`

**ORGADMIN role required.** If the user lacks access, defer to the **organization-management** skill for role troubleshooting.

## Schema

| Column | Type | Meaning |
|--------|------|---------|
| `DATE` | DATE | Date (UTC) for the effective price |
| `ORGANIZATION_NAME` | VARCHAR | Name of the organization |
| `CONTRACT_NUMBER` | VARCHAR | Snowflake contract number |
| `ACCOUNT_NAME` | VARCHAR | Name of the account |
| `ACCOUNT_LOCATOR` | VARCHAR | Locator for the account |
| `REGION` | VARCHAR | Cloud region of the account |
| `SERVICE_LEVEL` | VARCHAR | Account edition: Standard, Enterprise, Business Critical, etc. |
| `USAGE_TYPE` | VARCHAR | Corresponds to Usage Category on a billing statement (backward compatibility). Prefer `SERVICE_TYPE`, `BILLING_TYPE`, `RATING_TYPE`, and `IS_ADJUSTMENT` for reconciliation |
| `CURRENCY` | VARCHAR | Currency of the effective rate |
| `EFFECTIVE_RATE` | NUMBER(38,2) | Rate after applying contract discounts |
| `SERVICE_TYPE` | VARCHAR | Type of usage, e.g. `snowpipe`, `warehouse_metering`, `automatic_clustering`, etc. |
| `RATING_TYPE` | VARCHAR | How usage is priced: `compute`, `storage`, or `other` |
| `BILLING_TYPE` | VARCHAR | What is being charged or credited: `consumption` (compute/storage/transfer), `rebate` (data sharing credits), `priority support`, `vps_deployment_fee`, `support_credit` (Snowflake-issued reversal) |
| `IS_ADJUSTMENT` | BOOLEAN | Whether the record is an adjustment to usage |

---

## Important behavior

- Data available from June 2020 onward; contact Snowflake Support for earlier data.
- **Latency**: up to **24 hours**.
- Until month-close, rates for a given day can change due to end-of-month adjustments, mid-month contract amendments, or account transfers between organizations.
- Reseller customers **cannot** access this view.
- `EFFECTIVE_RATE` reflects contractual discounts — it is the actual price per credit (or per unit for storage/transfer) the organization pays.

---

## Queries

### Current effective rates by service type

```sql
SELECT
    ACCOUNT_NAME,
    SERVICE_TYPE,
    RATING_TYPE,
    EFFECTIVE_RATE,
    CURRENCY
FROM SNOWFLAKE.ORGANIZATION_USAGE.RATE_SHEET_DAILY
WHERE DATE = (SELECT MAX(DATE) FROM SNOWFLAKE.ORGANIZATION_USAGE.RATE_SHEET_DAILY)
ORDER BY ACCOUNT_NAME, SERVICE_TYPE;
```

### Compare rates across accounts

```sql
SELECT
    ACCOUNT_NAME,
    SERVICE_LEVEL,
    SERVICE_TYPE,
    EFFECTIVE_RATE,
    CURRENCY
FROM SNOWFLAKE.ORGANIZATION_USAGE.RATE_SHEET_DAILY
WHERE DATE = (SELECT MAX(DATE) FROM SNOWFLAKE.ORGANIZATION_USAGE.RATE_SHEET_DAILY)
  AND RATING_TYPE = 'compute'
ORDER BY EFFECTIVE_RATE DESC;
```

### Rate history for a specific service (how rates changed over time)

```sql
SELECT DISTINCT
    DATE,
    EFFECTIVE_RATE,
    SERVICE_TYPE,
    CURRENCY
FROM SNOWFLAKE.ORGANIZATION_USAGE.RATE_SHEET_DAILY
WHERE SERVICE_TYPE = 'warehouse_metering'
  AND DATE >= DATEADD('month', -12, CURRENT_DATE)
ORDER BY DATE;
```

### All billing types and their rates

```sql
SELECT DISTINCT
    BILLING_TYPE,
    SERVICE_TYPE,
    RATING_TYPE,
    EFFECTIVE_RATE,
    CURRENCY
FROM SNOWFLAKE.ORGANIZATION_USAGE.RATE_SHEET_DAILY
WHERE DATE = (SELECT MAX(DATE) FROM SNOWFLAKE.ORGANIZATION_USAGE.RATE_SHEET_DAILY)
ORDER BY BILLING_TYPE, SERVICE_TYPE;
```
