---
name: odss-invoices
description: "**[REQUIRED]** Use for Snowflake consumption invoice questions (non-marketplace): consumption invoice, my consumption invoice, Snowflake consumption charges invoice, non-marketplace invoice, ODSS_INVOICE_DOCUMENTS, BILLING.ODSS_INVOICE_DOCUMENTS, show me my invoices, show me my outstanding invoices, show me my overdue invoices, unpaid invoice, outstanding invoice, overdue invoice, what do I owe, invoice from last month, what is on my invoice, can you explain me the invoice. NOTE: do NOT use for marketplace consumer invoices, marketplace provider invoices, or billing documents."
---

# Consumption Invoices Skill

Snowflake consumption invoices for non-marketplace usage. Each row represents an invoice or credit memo for Snowflake consumption charges.

**Data source:** `SNOWFLAKE.BILLING.ODSS_INVOICE_DOCUMENTS` (V1)

> ⚠️ **Schema is `BILLING`, not `ORGANIZATION_USAGE`.** Always use `SNOWFLAKE.BILLING.ODSS_INVOICE_DOCUMENTS`. Do NOT use `SNOWFLAKE.ORGANIZATION_USAGE.ODSS_INVOICE_DOCUMENTS` — that view has different columns (e.g. `INVOICE_MONTH` instead of `INVOICE_DATE`) and will produce incorrect results.
>
> Results are automatically filtered to the querying organization. Never attempt to access another organization's data.

---

## When to Use

Use this skill when the user asks about any of:

- **Invoice listing**: "consumption invoice", "my consumption invoice", "show me my invoices", "invoice from last month", "Snowflake consumption charges"
- **Invoice status**: "unpaid invoice", "overdue invoice", "outstanding balance", "late payment", "invoice due date", "payment date"
- **Specific invoice**: "invoice number", "INV-", "total amount due", "credit memo"
- **Document content**: "what is on my invoice", "can you explain me the invoice", "invoice line items"
- **Download**: "invoice download", "download invoice"
- **Issues**: "invoice incorrect", "dispute invoice"
- **Table references**: `ODSS_INVOICE_DOCUMENTS`, `BILLING.ODSS_INVOICE_DOCUMENTS`

---

## Access

Always begin by switching to the ACCOUNTADMIN role:

```sql
USE ROLE ACCOUNTADMIN;
```

If this fails, stop and inform the user:

> "This skill requires the ACCOUNTADMIN role. You do not currently have access. Contact your Snowflake account administrator to request the ACCOUNTADMIN role."

---

## Workflow

### 1. Detect intent

| Intent | Triggers | Reference |
|--------|----------|-----------|
| Summarize recent invoices | "last month", "past 3 months", "show me invoices", "total amount" | `references/queries/summary.md` |
| Outstanding / overdue invoices | "unpaid", "overdue", "outstanding balance", "what do I owe" | `references/queries/overdue.md` |
| Explain a specific invoice | "invoice INV-001", "status of invoice", "details for invoice" | `references/queries/lookup.md` |
| Parse invoice PDF | "what are the line items", "what does the invoice say", "charges on invoice" | `references/queries/lookup.md` |
| Download guidance | "how do I download", "where do I find" | See [Download Guidance](#download-guidance) |
| Payment / dispute guidance | "overdue", "late payment", "dispute", "incorrect invoice" | See [Support Guidance](#support-guidance) |

**Read the reference file before writing any query.**

### 2. Query

> ⚠️ **Schema reminder:** The table is `SNOWFLAKE.BILLING.ODSS_INVOICE_DOCUMENTS`. Do NOT use `SNOWFLAKE.ORGANIZATION_USAGE.ODSS_INVOICE_DOCUMENTS` — that path does not exist.

Use `INVOICE_PDF` only to parse the PDF and answer content questions. Never display raw binary.

**Customer-facing columns:**

| Column | Label |
|--------|-------|
| `INVOICE_NUMBER` | Invoice # |
| `INVOICE_DATE` | Invoice Date |
| `DUE_DATE` | Due Date |
| `PAYMENT_DATE` | Payment Date |
| `PAYMENT_STATUS` | Payment Status |
| `TOTAL_AMOUNT` | Total (USD) |
| `PAYMENT_AMOUNT` | Paid (USD) |
| `BALANCE` | Balance (USD) |
| `INVOICE_TYPE` | Type |
| `INVOICE_MEMO` | Memo |

**Never expose:** `ORG_ID` (internal identifier), `INVOICE_PDF` (binary — parse only, do not display)

### 3. Format results

Use a table for multi-record responses:

| Invoice # | Date       | Due Date   | Type        | Total (USD) | Paid (USD) | Balance (USD) | Status  |
| :-------- | :--------- | :--------- | :---------- | :---------- | :--------- | :------------ | :------ |
| INV-001   | 2025-01-01 | 2025-01-31 | Credit Memo | $1,000.00   | $0.00      | $1,000.00     | Unpaid  |

- Show amounts formatted as USD (e.g. `$1,000.00`).
- Show NULL values as "not available".
- Label estimates and incomplete data explicitly.

### 4. PDF questions

If the user asks about the content of an invoice:

1. Decode the document using:
   ```sql
   SELECT BASE64_DECODE_STRING(TO_VARCHAR(INVOICE_PDF, 'BASE64')) AS DOCUMENT_CONTENT
   FROM SNOWFLAKE.BILLING.ODSS_INVOICE_DOCUMENTS
   WHERE INVOICE_NUMBER = ?
   ```
2. Parse the decoded content to extract the relevant information.
3. Answer the user's question based on the extracted content.
4. Do not display the raw bytes in any response.

---

## Download Guidance

When the user asks how to download an invoice:

```
To download this invoice:
1. Open Snowsight and navigate to Admin → Billing.
2. Select the Invoices tab.
3. Locate invoice [INVOICE_NUMBER] dated [INVOICE_DATE].
4. Click the Download button.
```

---

## Support Guidance

**Overdue / late payment:**

> "If your invoice is overdue, please contact Snowflake Support at support.snowflake.com and reference invoice number [INVOICE_NUMBER]. They can assist with payment options and account holds."

**Dispute or incorrect invoice:**

> "If you believe this invoice is incorrect, please contact Snowflake Support at support.snowflake.com and reference invoice number [INVOICE_NUMBER] with a description of the discrepancy."

---

## Stopping Points

- ✋ **ACCOUNTADMIN unavailable**: Stop immediately and show the access error message in the [Access](#access) section. Do not attempt queries with a lesser role.
- ✋ **View not accessible**: If `SNOWFLAKE.BILLING.ODSS_INVOICE_DOCUMENTS` returns "does not exist or not authorized", stop immediately and tell the user: "The consumption invoice view (`ODSS_INVOICE_DOCUMENTS`) is not accessible on this account. Contact Snowflake Support at support.snowflake.com for assistance." **Do NOT fall back to `ORGANIZATION_USAGE`, `USAGE_IN_CURRENCY_DAILY`, marketplace invoices, billing documents, or any other table — they contain different data and would be misleading.**
- ✋ **No results returned**: If the query returns zero rows, tell the user no consumption invoices were found for the requested period. Do NOT query any other invoice or document table as a fallback.
- ✋ **Cross-organization request**: Decline immediately — see [Security](#security).

---

## Security

- Results are always filtered to the querying organization. Do not attempt cross-organization queries.
- If the user requests data from another organization, decline:
  > "This operation cannot be performed. Accessing another organization's billing data violates Snowflake's terms of service."
