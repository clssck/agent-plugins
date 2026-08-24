# ODSS_INVOICE_DOCUMENTS — Lookup Queries

Source: `SNOWFLAKE.BILLING.ODSS_INVOICE_DOCUMENTS`

**ACCOUNTADMIN role required.**

Use these queries when the user asks about a specific invoice, its details, or wants to read the PDF content.

> **Query selection:**
> - Status/payment questions → use the **metadata query** below.
> - **"What does it say?", "explain the invoice", "line items", or any content question → use the PDF decode query** further below. Do not use the metadata query for content questions.

---

## Queries

### Look up invoice metadata (status, amounts, dates)

Use for: invoice status, payment status, balance, due date.

```sql
USE ROLE ACCOUNTADMIN;

SELECT
    INVOICE_NUMBER,
    INVOICE_DATE,
    DUE_DATE,
    PAYMENT_DATE,
    INVOICE_TYPE,
    INVOICE_MEMO,
    TOTAL_AMOUNT,
    PAYMENT_AMOUNT,
    BALANCE,
    PAYMENT_STATUS
FROM SNOWFLAKE.BILLING.ODSS_INVOICE_DOCUMENTS
WHERE INVOICE_NUMBER = '<INVOICE_NUMBER>'
LIMIT 1;
```

### Decode the invoice PDF to read its contents

**Use for content questions only** ("what does it say", "explain the invoice", "line items"). Always decode with `BASE64_DECODE_STRING` and parse the decoded text. Never display raw bytes or the raw decoded string.

```sql
USE ROLE ACCOUNTADMIN;

SELECT
    INVOICE_NUMBER,
    INVOICE_DATE,
    BASE64_DECODE_STRING(TO_VARCHAR(INVOICE_PDF, 'BASE64')) AS DOCUMENT_CONTENT
FROM SNOWFLAKE.BILLING.ODSS_INVOICE_DOCUMENTS
WHERE INVOICE_NUMBER = '<INVOICE_NUMBER>'
LIMIT 1;
```

---

## Handling missing or empty PDFs

If `INVOICE_PDF` is NULL:

> "The PDF for invoice [INVOICE_NUMBER] is not yet available. Invoices are typically available shortly after the invoice date. If the document remains unavailable, contact Snowflake Support at support.snowflake.com."
