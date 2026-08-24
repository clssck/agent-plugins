---
name: billing-billing-queries
description: "Org-level spend in dollars/currency via SNOWFLAKE.ORGANIZATION_USAGE. Use for: dollar spend by service type (which services cost the most money), monthly spend trends, top accounts by spend, on-demand vs capacity balance, contract start/end/termination dates, effective rates, billing reconciliation. Views: USAGE_IN_CURRENCY_DAILY, REMAINING_BALANCE_DAILY, CONTRACT_ITEMS, RATE_SHEET_DAILY. Key: any question about cost/spend in money (not credits) routes here, including service type breakdowns."
parent_skill: billing
---

# Billing Queries Skill

> **Do NOT search for semantic views for billing questions.**
> Billing data lives in `SNOWFLAKE.ORGANIZATION_USAGE` views: `USAGE_IN_CURRENCY_DAILY`, `REMAINING_BALANCE_DAILY`, `CONTRACT_ITEMS`, and `RATE_SHEET_DAILY`.
> Skip `cortex semantic-views search/discover` and `SHOW DATABASES` — go directly to the reference files below.
>
> **Never use `SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY` for spending or cost questions.** That view contains credits only — no dollar amounts. Always use `SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY` for any monetary spending question.

---

## When to Use

Use this skill for org-level billing queries:

- **Spend analysis**: "How much am I spending?", "Which accounts cost the most?", "Monthly spend trend", "Spending by service type"
- **Balance tracking**: "What is my remaining balance?", "On-demand vs capacity usage", "Free usage balance"
- **Contract details**: "When does my contract expire?", "Contract utilization", "Contract start/end dates", "Contract value", "How long is my contract?"
- **Rates and pricing**: "What is my effective compute rate?", "Rate comparison across accounts", "Pricing per service"
- **Reconciliation**: "Reconcile my billing statement", "Total consumed", "What is on my bill?"

## When NOT to Use

| Question type | Use instead |
|--------------|-------------|
| Single-account credit usage, per-warehouse costs, per-feature credits | **cost-intelligence** skill |
| "How much is my warehouse costing?" or "Top users by credits" | **cost-intelligence** skill |
| Invoices (marketplace, billing documents, consumption invoices) | Parent skill routes to the appropriate invoice sub-skill |

In short: **dollars/currency** → this skill, **credits only** → cost-intelligence. This includes service type breakdowns — "which services cost the most money" is a dollar question that belongs here, even though cost-intelligence also has service data in credits.

---

## Access Requirements

This skill requires the `ORGADMIN` role. If the user gets an access error or lacks the role, defer to the **organization-management** skill (`organization-management/org-usage-view/SKILL.md`) for role troubleshooting, access grants, and SNOWFLAKE database role mapping.

---

## References

Read the appropriate reference file before writing any billing query.

| User intent | Reference file |
|-------------|---------------|
| Spend queries (total, by account, by service, trends, what's on my bill), reconcile billing statement / total consumed | `../references/queries/usage-in-currency.md` |
| Remaining balance, capacity balance, on-demand accrual, balance trend | `../references/queries/remaining-balance-daily.md` |
| Contract details, contract value, utilization, expiration, contract start (effective) date, termination date, contract duration/length, renewal window, contract modified date | `../references/queries/contract-items.md` |
| Effective rates, pricing per service, rate history, rate comparison | `../references/queries/rate-sheet-daily.md` |

**Never write ad-hoc queries when a verified query exists in a reference file.**

---

## Stopping Points

- ✋ **Access denied / missing ORGADMIN**: Direct user to `organization-management/org-usage-view/SKILL.md`.
- ✋ **METERING_HISTORY is the wrong table**: If you are about to write `FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY` for any spend, cost, trend, or service-type question — STOP. Replace it with `FROM SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY`. METERING_HISTORY has no `USAGE_IN_CURRENCY` column and cannot answer dollar questions. This applies to: monthly spend trend, spend by service type, total org spend, and any question involving dollar amounts.
- ✋ **Missing 30-day renewal explanation**: Before finalizing your answer for any contract termination, expiration, or days remaining question — verify your answer to the user includes the sentence: "If the contract is not renewed within 30 days of the expiration date, the Snowflake relationship terminates." If it does not, add it.

---

## Critical Non-Obvious Details

Always explain these when they appear in queries or results:

**USAGE_IN_CURRENCY_DAILY**

| Column | Meaning |
|--------|---------|
| `BALANCE_SOURCE` | Which contract bucket paid for this usage: `capacity`, `rollover`, `free usage`, `overage` (on-demand, all balances exhausted), `rebate` |
| `BILLING_TYPE` | Charge category: `CONSUMPTION` (normal consumption), `REBATE` (credit back), `ADJUSTMENT` (correction) |
| `IS_ADJUSTMENT` | `TRUE` = billing correction row. Include by default; only exclude if user explicitly asks for raw usage without corrections |

**REMAINING_BALANCE_DAILY**

| Column | Meaning |
|--------|---------|
| `ON_DEMAND_CONSUMPTION_BALANCE` | **Negative value** (e.g. -250) representing on-demand charges accrued. Resets after month-close (~3rd–4th of next month) |
| `ROLLOVER_BALANCE` | Unused credits rolled over from prior contract term |

**CONTRACT_ITEMS**

| Column | Meaning |
|--------|---------|
| `CONTRACT_ITEM` | One of: `capacity`, `additional capacity`, `free usage` |
| `AMOUNT` | In **currency** (e.g. USD), not credits |
| `START_DATE` | The date the contract item went into effect (the contract effective/start date) |
| `EXPIRATION_DATE` | May be `NULL` — see below |

> **Always explain what START_DATE means** when responding about contract start date, effective date, or any query that returns `START_DATE` values. Include this sentence in your **answer to the user**: "`START_DATE` is the date the contract item went into effect — this is the contract effective (start) date."

> **Contract effective (start) date — use this exact query** (never `SELECT *`):
>
> ```sql
> SELECT
>     CONTRACT_NUMBER,
>     MIN(START_DATE) AS CONTRACT_EFFECTIVE_DATE
> FROM SNOWFLAKE.ORGANIZATION_USAGE.CONTRACT_ITEMS
> WHERE START_DATE IS NOT NULL
> GROUP BY CONTRACT_NUMBER
> ORDER BY CONTRACT_NUMBER;
> ```
>
> Your **answer to the user** must include: the contract number, the date, and the START_DATE explanation above.

> **Contract termination date — use this exact query** (use `EXPIRATION_DATE`, NOT `END_DATE`):
>
> ```sql
> SELECT
>     CONTRACT_NUMBER,
>     MAX(EXPIRATION_DATE) AS TERMINATION_DATE,
>     DATEDIFF('day', CURRENT_DATE, MAX(EXPIRATION_DATE)) AS DAYS_UNTIL_TERMINATION
> FROM SNOWFLAKE.ORGANIZATION_USAGE.CONTRACT_ITEMS
> GROUP BY CONTRACT_NUMBER
> ORDER BY CONTRACT_NUMBER;
> ```
>
> `EXPIRATION_DATE` governs the Snowflake relationship termination. `END_DATE` is the date a contract line item stops being used — these are **not the same**. Always query `EXPIRATION_DATE` for termination questions.
>
> If `EXPIRATION_DATE` returns `NULL`, tell the user: "Your contract does not have a termination date recorded in Snowflake. Contact your Snowflake account team for contract term details."

> **Always explain the 30-day renewal window** when responding about contract termination, expiration, or days remaining. Include this sentence in your **answer to the user**: "If the contract is not renewed within 30 days of the expiration date, the Snowflake relationship terminates." This applies even when `EXPIRATION_DATE` is `NULL`.
>
> **Contracts with no termination date:** Not all contracts have an `EXPIRATION_DATE` set. When a user asks about contract termination, expiration, renewal, or days remaining and the query returns `NULL` for `EXPIRATION_DATE`, you **must** explicitly tell the user: "Your contract does not have a termination date recorded in Snowflake. Contact your Snowflake account team for contract term details." Never silently omit contracts with no termination date or present results as if all contracts have one.

**Reconciliation — "Total Consumed" on billing statement**:
> ⚠️ **Critical**: "Total Consumed" is **cumulative from contract start** — not a single month. Use this exact query (replace the date with the last day of the statement month):
>
> ```sql
> SELECT
>     CONTRACT_NUMBER,
>     SUM(USAGE_IN_CURRENCY) AS TOTAL_CONSUMED
> FROM SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY
> WHERE USAGE_DATE <= LAST_DAY(TO_DATE('YYYY-MM-01'))
>   AND LOWER(BALANCE_SOURCE) != 'overage'
> GROUP BY CONTRACT_NUMBER
> ORDER BY CONTRACT_NUMBER;
> ```
>
> Rules you **must not break**:
> 1. **No lower bound on the date** — `USAGE_DATE <= LAST_DAY(...)` only, never `USAGE_DATE >= ...`
> 2. **Exclude overage** — `AND LOWER(BALANCE_SOURCE) != 'overage'`. Overage is billed separately.
> 3. **Group by CONTRACT_NUMBER** — an org may have multiple contracts.
> 4. Small rounding differences (a few cents to <$10) are normal.
>
> The billing statement's "Remaining Balance" = `CAPACITY_BALANCE + FREE_USAGE_BALANCE + ROLLOVER_BALANCE` (excludes `ON_DEMAND_CONSUMPTION_BALANCE`).
