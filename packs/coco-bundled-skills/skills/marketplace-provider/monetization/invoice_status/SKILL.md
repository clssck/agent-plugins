---
name: marketplace-provider-invoice-status
description: "Query Marketplace invoice status and billing information for paid listings. Use when: checking invoice status, reviewing unpaid invoices, analyzing Marketplace billing, tracking consumer payments, viewing provider payout history. Triggers: marketplace invoice, invoice status, unpaid invoices, billing status, payout history, marketplace billing, paid listings revenue."
---

# Marketplace Invoice Status

Query the `SNOWFLAKE.DATA_SHARING_USAGE.MARKETPLACE_LISTING_INVOICE_STATUS` view to analyze invoice and billing information for paid Marketplace listings.

## When to Use

Use this skill when providers need to:
- Check the status of invoices (open, closed, void, rebilled)
- Review unpaid or outstanding invoices by consumer
- Analyze billing history for paid listings
- Track expected payouts and fee
- Export billing information

## Prerequisites

- Access to `SNOWFLAKE.DATA_SHARING_USAGE.MARKETPLACE_LISTING_INVOICE_STATUS` view
- User must be a provider of paid Marketplace listings
- Data latency: up to 48 hours; retention: 365 days

## Workflow

### Step 1: Identify Query Intent

**Ask user** (if not clear from request):
```
What would you like to analyze?

1. View all invoice history
2. Check unpaid/open invoices
3. Summarize invoices by listing
4. Summarize invoices by consumer
5. Look up a specific invoice
```

### Step 2: Execute Query Based on Intent

#### Option 1: View All Invoice History

```sql
SELECT
    stripe_display_number AS invoice_number,
    invoice_date,
    usage_month AS billing_month,
    invoice_status,
    listing_display_name,
    consumer_company_name,
    consumer_account_name,
    total_billed_amount,
    sales_tax_amount,
    fee,
    expected_payout_amount,
    po_number
FROM snowflake.data_sharing_usage.marketplace_listing_invoice_status
ORDER BY invoice_date DESC
LIMIT 100;
```

#### Option 2: Check Unpaid/Open Invoices

```sql
SELECT
    consumer_account_name,
    consumer_company_name,
    consumer_account_locator,
    consumer_billing_email_address,
    COUNT(*) AS open_invoice_count,
    SUM(total_billed_amount) AS total_outstanding,
    LISTAGG(DISTINCT listing_display_name, ', ') AS listings_affected
FROM snowflake.data_sharing_usage.marketplace_listing_invoice_status
WHERE invoice_status = 'open'
GROUP BY 1, 2, 3, 4
ORDER BY total_outstanding DESC;
```

#### Option 3: Summarize by Listing

```sql
SELECT
    listing_display_name,
    listing_global_name,
    COUNT(*) AS total_invoices,
    SUM(CASE WHEN invoice_status = 'closed' THEN 1 ELSE 0 END) AS paid_invoices,
    SUM(CASE WHEN invoice_status = 'open' THEN 1 ELSE 0 END) AS open_invoices,
    SUM(total_billed_amount) AS total_billed,
    SUM(expected_payout_amount) AS total_expected_payout,
    SUM(CASE WHEN invoice_status = 'open' THEN total_billed_amount ELSE 0 END) AS outstanding_amount,
    MIN(invoice_date) AS first_invoice_date,
    MAX(invoice_date) AS last_invoice_date
FROM snowflake.data_sharing_usage.marketplace_listing_invoice_status
WHERE invoice_status NOT IN ('void')
GROUP BY 1, 2
ORDER BY total_billed DESC;
```

#### Option 4: Summarize by Consumer

```sql
SELECT
    consumer_organization_name,
    consumer_company_name,
    consumer_account_name,
    consumer_account_locator,
    COUNT(*) AS total_invoices,
    SUM(CASE WHEN invoice_status = 'closed' THEN 1 ELSE 0 END) AS paid_invoices,
    SUM(CASE WHEN invoice_status = 'open' THEN 1 ELSE 0 END) AS open_invoices,
    SUM(total_billed_amount) AS total_billed,
    SUM(CASE WHEN invoice_status = 'open' THEN total_billed_amount ELSE 0 END) AS outstanding_amount,
    MAX(invoice_date) AS last_invoice_date
FROM snowflake.data_sharing_usage.marketplace_listing_invoice_status
WHERE invoice_status NOT IN ('void')
GROUP BY 1, 2, 3, 4
ORDER BY total_billed DESC;
```

#### Option 5: Look Up Specific Invoice

**Ask for invoice number**, then:

```sql
SELECT
    stripe_display_number AS invoice_number,
    invoice_date,
    usage_month AS billing_month,
    invoice_status,
    po_number,
    currency,
    total_billed_amount,
    sales_tax_amount,
    fee,
    expected_payout_amount,
    listing_display_name,
    listing_global_name,
    consumer_organization_name,
    consumer_account_name,
    consumer_account_locator,
    consumer_company_name,
    consumer_billing_email_address
FROM snowflake.data_sharing_usage.marketplace_listing_invoice_status
WHERE stripe_display_number = '<INVOICE_NUMBER>';
```

### Step 3: Present Results

**Format output** based on query type:

For invoice listings:
```
MARKETPLACE INVOICE STATUS
════════════════════════════════════════════════════════════════════

Invoice: <invoice_number>
Date: <invoice_date> | Status: <invoice_status>
Listing: <listing_display_name>

CONSUMER
─────────────────────────────────────────────────────────────────────
Company: <consumer_company_name>
Account: <consumer_account_name> (<consumer_account_locator>)
Billing Email: <consumer_billing_email_address>

FINANCIALS
─────────────────────────────────────────────────────────────────────
Total Billed:      $<total_billed_amount>
Sales Tax:         $<sales_tax_amount>
Fees:              $<fee>
Expected Payout:   $<expected_payout_amount>
PO Number:         <po_number>
```

For summaries:
```
INVOICE SUMMARY BY <GROUPING>
════════════════════════════════════════════════════════════════════

| <Group> | Invoices | Paid | Open | Total Billed | Outstanding |
|---------|----------|------|------|--------------|-------------|
| ...     | ...      | ...  | ...  | $...         | $...        |
```

## Invoice Status Reference

| Status | Description |
|--------|-------------|
| `closed` | Paid to Snowflake; paid to provider within 30 days |
| `open` | Not yet paid |
| `void` | Canceled |
| `rebilled` | Voided invoice was rebilled with adjustments |

**Note:** If an invoice is canceled and rebilled, there are two rows: one `void` and one `rebilled`. The new invoice has a new number and starts as `open`.

## Additional Queries

### Monthly Revenue Trend

```sql
SELECT
    usage_month,
    COUNT(*) AS invoice_count,
    SUM(CASE WHEN invoice_status = 'closed' THEN total_billed_amount ELSE 0 END) AS collected_revenue,
    SUM(CASE WHEN invoice_status = 'open' THEN total_billed_amount ELSE 0 END) AS pending_revenue,
    SUM(expected_payout_amount) AS expected_payout
FROM snowflake.data_sharing_usage.marketplace_listing_invoice_status
WHERE invoice_status NOT IN ('void')
GROUP BY 1
ORDER BY 1 DESC
LIMIT 12;
```

### Export Billing Information

```sql
SELECT
    stripe_display_number AS snowflake_mp_invoice_number,
    invoice_date,
    usage_month AS first_billing_month,
    invoice_status,
    po_number,
    currency,
    total_billed_amount,
    listing_display_name,
    listing_global_name,
    consumer_organization_name,
    consumer_account_name,
    consumer_account_locator,
    consumer_company_name,
    consumer_billing_email_address
FROM snowflake.data_sharing_usage.marketplace_listing_invoice_status;
```

## Stopping Points

- **Step 1**: Confirm query intent before executing
- **Step 3**: After presenting results, ask if user needs additional analysis

## Output

- Invoice status and billing details
- Summary by listing or consumer
- Outstanding balance reports
- Revenue trend analysis

## Notes

- All amounts are in USD (alternate currencies not supported)
- Data latency: up to 48 hours (2 days)
- Data retention: 365 days (1 year)
- Only visible to providers of paid listings

## Reference

[Snowflake Documentation: MARKETPLACE_LISTING_INVOICE_STATUS](https://docs.snowflake.com/en/collaboration/views/marketplace_listing_invoice_status)