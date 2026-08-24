---
name: billing
description: "Org-level Snowflake billing in dollars/currency. Use for: dollar spend by service type, monthly spend trends, which services cost the most money, remaining balance, contract termination date, contract expiration date, contract start date, contract details, rate comparison, reconciliation. Consumption invoices: ODSS_INVOICE_DOCUMENTS, outstanding invoice, overdue invoice, unpaid invoice. Not for credit-based analytics (cost-intelligence) or warehouse DDL (warehouse). Key distinction: dollars/currency → billing, credits only → cost-intelligence."
---

# Billing Skill

Router skill for all Snowflake billing questions.

## Intent Detection

Identify the user's intent and **immediately load the matching sub-skill**:

| User Intent | Load |
|-------------|------|
| Spending, charges, monthly spend, **service costs in dollars**, **which services cost the most money**, balance, contract details, rates, reconciliation | `billing-queries/SKILL.md` |
| Consumption invoices: `ODSS_INVOICE_DOCUMENTS`, outstanding invoice, overdue invoice, unpaid invoice, what do I owe | `billing/odss-invoices/SKILL.md` |

> **Dollar vs credits routing**: If the question involves money/dollars/currency (even if it mentions "services" or "cost"), this is the correct skill. `cost-intelligence` handles credit-based analysis only.

## ⚠️ DO NOT PROCEED WITHOUT LOADING A SUB-SKILL

This router provides NO implementation details. All queries, workflows, and column guidance are in the sub-skills above.

> **Never use `SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY` for any spending or cost question.** That view contains credits only — no dollar amounts. All dollar spend questions (including breakdowns by service type) use `SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY`. Load the sub-skill before writing any query.
