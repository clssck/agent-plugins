# ODSS_INVOICE_DOCUMENTS — Summary Queries

Source: `SNOWFLAKE.BILLING.ODSS_INVOICE_DOCUMENTS`

**ACCOUNTADMIN role required.**

---

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `ORG_ID` | TEXT | Organization identifier — internal, never display |
| `INVOICE_NUMBER` | TEXT | Unique identifier for the invoice |
| `INVOICE_DATE` | DATE | Date the invoice was issued |
| `DUE_DATE` | DATE | Date by which payment is due |
| `PAYMENT_DATE` | DATE | Date payment was made. NULL if unpaid |
| `PAYMENT_STATUS` | TEXT | Current payment status |
| `TOTAL_AMOUNT` | NUMBER | Total invoice amount in USD |
| `PAYMENT_AMOUNT` | NUMBER | Amount that has been paid |
| `BALANCE` | NUMBER | Remaining unpaid balance |
| `INVOICE_TYPE` | TEXT | Type of invoice (e.g. Credit Memo) |
| `INVOICE_MEMO` | TEXT | Additional notes or adjustment reason |
| `INVOICE_PDF` | BINARY | PDF content — for parsing only, never display |

---

## Queries

### Invoices from the last month

```sql
USE ROLE ACCOUNTADMIN;

SELECT
    INVOICE_NUMBER,
    INVOICE_DATE,
    DUE_DATE,
    INVOICE_TYPE,
    TOTAL_AMOUNT,
    PAYMENT_AMOUNT,
    BALANCE,
    PAYMENT_STATUS
FROM SNOWFLAKE.BILLING.ODSS_INVOICE_DOCUMENTS
WHERE INVOICE_DATE >= DATE_TRUNC('month', DATEADD('month', -1, CURRENT_DATE))
  AND INVOICE_DATE <  DATE_TRUNC('month', CURRENT_DATE)
ORDER BY INVOICE_DATE DESC;
```

### Summary: total count and amounts for last month

```sql
USE ROLE ACCOUNTADMIN;

SELECT
    COUNT(*)                    AS INVOICE_COUNT,
    SUM(TOTAL_AMOUNT)           AS TOTAL_INVOICED_USD,
    SUM(PAYMENT_AMOUNT)         AS TOTAL_PAID_USD,
    SUM(BALANCE)                AS TOTAL_OUTSTANDING_USD,
    PAYMENT_STATUS
FROM SNOWFLAKE.BILLING.ODSS_INVOICE_DOCUMENTS
WHERE INVOICE_DATE >= DATE_TRUNC('month', DATEADD('month', -1, CURRENT_DATE))
  AND INVOICE_DATE <  DATE_TRUNC('month', CURRENT_DATE)
GROUP BY PAYMENT_STATUS
ORDER BY TOTAL_INVOICED_USD DESC;
```

### Invoices over a date range

```sql
USE ROLE ACCOUNTADMIN;

SELECT
    INVOICE_NUMBER,
    INVOICE_DATE,
    DUE_DATE,
    INVOICE_TYPE,
    TOTAL_AMOUNT,
    PAYMENT_AMOUNT,
    BALANCE,
    PAYMENT_STATUS
FROM SNOWFLAKE.BILLING.ODSS_INVOICE_DOCUMENTS
WHERE INVOICE_DATE BETWEEN '<START_DATE>' AND '<END_DATE>'
ORDER BY INVOICE_DATE DESC;
```

### All invoices (all time)

```sql
USE ROLE ACCOUNTADMIN;

SELECT
    INVOICE_NUMBER,
    INVOICE_DATE,
    DUE_DATE,
    INVOICE_TYPE,
    TOTAL_AMOUNT,
    PAYMENT_AMOUNT,
    BALANCE,
    PAYMENT_STATUS
FROM SNOWFLAKE.BILLING.ODSS_INVOICE_DOCUMENTS
ORDER BY INVOICE_DATE DESC;
```
