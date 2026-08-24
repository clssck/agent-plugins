---
name: organization-management-org-hub
description: "Executive organization summaries, org-wide spending, reliability, and security insights. Use when the user asks about: 30 day summary of my organization, executive summary of my org, summarize my organization, org overview, org health, what's happening in my org, how much are we spending, org cost breakdown, cost drivers, spending trends, week over week changes, month over month, biggest spend, which accounts cost the most, reliability risks, security posture, auth posture, trust center violations, MFA readiness, login failure trends, warehouse credits, storage trends, account growth, edition mix, what needs attention, org hub, top insights, org analytics, cost trends, cost spikes, cost optimizations, compare service costs, fastest growing costs, service optimizations, contract utilization, forecast contract, violation trends, trust center coverage, MFA adoption, login failure patterns, auth method distribution, admin distribution, over-provisioned accounts, admin governance, security admin coverage, dormant users, dormant user risk, dormant user cleanup, query failure patterns, most failing queries, warehouse queued load, queue bottlenecks, peak queue times, warehouse load distribution, peak load periods, capacity planning, storage growth, storage consumers, storage optimization, top queries by cost, expensive queries, Organization Hub."
parent_skill: organization-management
---

# Org Hub

## When to Use

Use this skill when users ask for top-level organization insights, such as:
- "Give me an executive summary for the last 30 days"
- "Where are we spending the most and why?"
- "What are the biggest reliability risks right now?"
- "How is our security posture trending?"
- "Which accounts or warehouses need attention?"

## CRITICAL: ORGANIZATION Context Only

This skill operates at the **ORGANIZATION** level. Follow these rules strictly:

- **Always** use `SNOWFLAKE.ORGANIZATION_USAGE` views. **Never** use `SNOWFLAKE.ACCOUNT_USAGE` views.
- If a user question could be answered by either `ACCOUNT_USAGE` or `ORGANIZATION_USAGE`, always choose `ORGANIZATION_USAGE`.
- Common mapping from ACCOUNT_USAGE to ORGANIZATION_USAGE equivalents:

| ACCOUNT_USAGE View | ORGANIZATION_USAGE Equivalent |
|---|---|
| `SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY` | `SNOWFLAKE.ORGANIZATION_USAGE.METERING_DAILY_HISTORY` |
| `SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY` | `SNOWFLAKE.ORGANIZATION_USAGE.WAREHOUSE_METERING_HISTORY` |
| `SNOWFLAKE.ACCOUNT_USAGE.STORAGE_USAGE` | `SNOWFLAKE.ORGANIZATION_USAGE.STORAGE_DAILY_HISTORY` |
| `SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY` | `SNOWFLAKE.ORGANIZATION_USAGE.LOGIN_HISTORY` |
| `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` | `SNOWFLAKE.ORGANIZATION_USAGE.QUERY_HISTORY` |
| `SNOWFLAKE.ACCOUNT_USAGE.DATABASES` | `SNOWFLAKE.ORGANIZATION_USAGE.DATABASES` |
| `SNOWFLAKE.ACCOUNT_USAGE.USERS` | `SNOWFLAKE.ORGANIZATION_USAGE.USERS` |
| `SNOWFLAKE.ACCOUNT_USAGE.ROLES` | `SNOWFLAKE.ORGANIZATION_USAGE.ROLES` |

## When NOT to Use

Do not use this skill for:
- Account or organization mutations (create/alter/drop)
- Replication/failover setup changes
- IAM implementation work
- Deep troubleshooting in non-org-hub domains where another skill is more specific

## Setup

1. **Load** `../references/global_guardrails.md`: Required context for all organization management operations.
2. **Load** `references/golden_queries.md` for SQL templates.

## Workflow

### Step 1: Set Role and Warehouse Context

**Do not execute any SNOWFLAKE.ORGANIZATION_USAGE query until the role is confirmed.**

First, check the current role:

```sql
SELECT CURRENT_ROLE();
```

- If the result is already `GLOBALORGADMIN` → **skip the role switch** and proceed to Step 2.
- If the result is a different role → switch and confirm:

```sql
USE ROLE GLOBALORGADMIN;
SELECT CURRENT_ROLE();
```

Only proceed if `CURRENT_ROLE()` returns `GLOBALORGADMIN`.

**After the role is confirmed**, ensure a warehouse is active. Follow the Warehouse Context rules in `global_guardrails.md`: check `CURRENT_WAREHOUSE()`, auto-select if null, only ask if none available.

### Step 2: Parse the Question

Extract:
- Time window (default `last 30 days` if not provided)
- Primary domain (`cost`, `security`, `reliability`, `auth`, `storage`, `accounts`)
- Required dimensions (`account`, `service_type`, `warehouse`, `severity`)
- Output depth (`executive summary` vs `drilldown`)

### Step 3: Check Verified Queries FIRST

Always choose from the golden query set first. Do not generate net-new SQL when a verified query ID already answers the ask.

If user asks a broad executive question, run this baseline bundle:
- `ORG_HUB_TOTAL_COST`
- `ORG_HUB_COST_BY_SERVICE_TYPE_WEEKLY`
- `ORG_HUB_TRUST_CENTER_VIOLATIONS_DAILY`
- `ORG_HUB_STORAGE_BY_ACCOUNT_CURRENT`
- `ORG_HUB_WAREHOUSE_QUEUED_LOAD_P99_TOTAL`
- `ORG_HUB_ACCOUNT_INVENTORY`

Do **not** include `QUERY_HISTORY`-based queries in the executive bundle — they are too slow. Only use them if the user specifically asks about query failures or performance.

### Step 4: Build Query Plan

- Pick 1-3 verified queries for targeted asks, 4-6 for executive bundles.
- Bind parameters (`:start_date`, `:end_date`, `:limit`) consistently.
- Prefer pre-aggregated org usage tables before raw history tables.
- Apply explicit ordering and limits for rank outputs.

### Step 5: SQL Construction Guidelines

- Keep everything read-only.
- Keep date windows bounded; default to last 30 days when unspecified.
- For trend charts, return daily/weekly buckets with stable ordering.
- For top-N analysis, always include `ORDER BY` + `LIMIT :limit`.
- For account drilldowns, include `account_name` explicitly in output.

### Step 6: Execute Read-Only Queries

**Performance is critical.** Some ORGANIZATION_USAGE views contain billions of rows and will time out without tight constraints.

Rules:
- **Fast views (30-day windows OK):** `USAGE_IN_CURRENCY_DAILY`, `STORAGE_DAILY_HISTORY`, `WAREHOUSE_METERING_HISTORY`, `METERING_DAILY_HISTORY`, `TRUST_CENTER_FINDINGS`, `GRANTS_TO_USERS`. These are already daily-granularity and return quickly.
- **Slow views:** `LOGIN_HISTORY` (7-day max, always LIMIT) and `QUERY_HISTORY` (3-day max, always LIMIT 100, **only when user explicitly asks**).
- **Always add LIMIT** to any query against slow views.
- **Avoid COUNT(*) on slow views** without a tight date range (≤7 days).
- When the user asks for "last 30 days", use fast views for cost/storage/compute trends. For login and query failure analysis, query only the last 7 days and note the reduced window in caveats.

### Step 7: Synthesize Findings

Return:
- What changed and why it matters
- Top outliers and likely drivers
- Risks with severity
- Clear next follow-ups (read-only unless user requests actions)

**Zero Rows Handling:** If security, failed query, or login anomaly queries return 0 rows, treat this as a positive finding (e.g., '0 Critical Violations found'). Do NOT apologize or assume the data is missing.

## Key Notes

- Use verified query IDs as the source of truth for repeatability.
- Do not extrapolate missing metrics; report unknowns explicitly.
- Favor organization-level aggregate tables for performance.
- Use account-level drilldown queries only when user asks for detail.

## Verified Query Routing

Use this quick map before scanning the full catalog:

- **Executive overview**
  - `ORG_HUB_TOTAL_COST`
  - `ORG_HUB_COST_BY_SERVICE_TYPE_WEEKLY`
  - `ORG_HUB_ACCOUNT_INVENTORY`
  - `ORG_HUB_TRUST_CENTER_VIOLATIONS_DAILY`
  - `ORG_HUB_STORAGE_BY_ACCOUNT_CURRENT`
- **Cost drivers**
  - `ORG_HUB_COST_BY_SERVICE_TYPE_WEEKLY`
  - `ORG_HUB_COST_BY_SERVICE_TYPE_MONTHLY_TOP5`
  - `ORG_HUB_TOP_QUERIES_BY_TOTAL_ELAPSED_TIME`
- **Authentication and access risk**
  - `ORG_HUB_LOGINS_BY_AUTH_TYPE_DAILY`
  - `ORG_HUB_LOGINS_BY_USER_AND_CLIENT`
  - `ORG_HUB_LOGIN_FAILURES_BY_TYPE_TOTAL`
  - `ORG_HUB_ACCOUNT_ADMINS_TOTAL`
  - `ORG_HUB_SECURITY_ADMINS_TOTAL`
- **Security posture**
  - `ORG_HUB_TRUST_CENTER_VIOLATIONS_DAILY`
  - `ORG_HUB_MFA_READINESS_TOTAL`
- **Capacity and performance**
  - `ORG_HUB_WAREHOUSE_QUEUED_LOAD_P99_TOTAL`
  - `ORG_HUB_FAILED_QUERIES_DAILY`
  - `ORG_HUB_STORAGE_BY_ACCOUNT_CURRENT`

If no verified query fully matches:
- Choose the closest verified query as a base.
- Modify only filters/groupings/limits to match user intent.
- Call out any assumptions in the caveats section.

**Load** `references/golden_queries.md` for SQL templates.

## Intent to Query Mapping

Use this map when user intent is ambiguous:

- **"Executive summary"** -> `ORG_HUB_TOTAL_COST`, `ORG_HUB_COST_BY_SERVICE_TYPE_WEEKLY`, `ORG_HUB_ACCOUNT_INVENTORY`, `ORG_HUB_TRUST_CENTER_VIOLATIONS_DAILY`, `ORG_HUB_STORAGE_BY_ACCOUNT_CURRENT`
- **"Cost drivers"** -> `ORG_HUB_COST_BY_SERVICE_TYPE_WEEKLY`, `ORG_HUB_TOP_QUERIES_BY_TOTAL_ELAPSED_TIME`, `ORG_HUB_TOP_WAREHOUSES_BY_CREDITS`
- **"Authentication posture"** -> `ORG_HUB_LOGINS_BY_AUTH_TYPE_DAILY`, `ORG_HUB_LOGINS_BY_USER_AND_CLIENT`, `ORG_HUB_LOGIN_FAILURES_BY_TYPE_TOTAL`
- **"Security posture"** -> `ORG_HUB_TRUST_CENTER_VIOLATIONS_DAILY`, `ORG_HUB_MFA_READINESS_TOTAL`, `ORG_HUB_SECURITY_ADMINS_TOTAL`
- **"Capacity/performance risk"** -> `ORG_HUB_WAREHOUSE_QUEUED_LOAD_P99_TOTAL`, `ORG_HUB_STORAGE_BY_ACCOUNT_CURRENT`
- **"Failed queries" or "slow queries"** (only if user explicitly asks) -> `ORG_HUB_FAILED_QUERIES_DAILY`, `ORG_HUB_TOP_QUERIES_BY_TOTAL_ELAPSED_TIME`

## Output Format

Use this exact structure for every Org Hub response. The format is designed for executive readability.

### Header

Start with a one-line summary of the time window and scope:

> 📊 **Org Hub Summary — Last 30 Days** (as of YYYY-MM-DD)

### Headline Metrics

Show 3–5 top-line numbers in a compact block:

> | Metric | Value | Trend |
> |---|---|---|
> | Total Spend | $X.XM USD | ▲ +X% WoW |
> | Failed Queries (7d) | X,XXX | ▼ -X% |
> | Open Critical Findings | XX | ━ flat |
> | Total Storage | X.X PB | ▲ +X% |

Use ▲ for increase, ▼ for decrease, ━ for flat.

**Currency rule:** Always present spend/cost values in dollars (`$`) using the `USAGE_IN_CURRENCY` column and include the `CURRENCY` code. Only use raw credits when the underlying view has no currency column (e.g., `WAREHOUSE_METERING_HISTORY`), and label them explicitly as "credits".

### Highlights

Summarize the most important findings grouped by signal type:

> 🔴 **Needs Attention**
>
> 1. **Finding title** — one-line explanation with concrete numbers.
> 2. ...
>
> 🟡 **Worth Watching**
>
> 1. **Finding title** — explanation with numbers.
> 2. ...
>
> 🟢 **Looking Good**
>
> - Positive finding with numbers.
> - ...

Rules:
- Every bullet must include **concrete numbers** from query results — no vague statements.
- Lead with the most important finding in each group.
- Keep each bullet to one or two sentences.

### Cost Breakdown

If cost data is available, include a service-type or account breakdown:

> 💰 **Spend by Service Type (WoW)**
>
> | Service | This Week | Last Week | Change |
> |---|---|---|---|
> | WAREHOUSE_METERING | $XXK | $XXK | ▲ +X% |
> | ... | ... | ... | ... |

### Recommended Next Steps

Numbered, actionable items tied to findings above:

> 📋 **Recommended Next Steps**
>
> 1. **Action title** — specific what/why/where.
> 2. ...
> 3. ...

### Suggested Follow-Up Questions

Always end with 3–5 follow-up questions the user can ask next. These should be natural continuations of the current analysis — deeper drilldowns, adjacent domains, or time comparisons.

> 💬 **Want to dig deeper? Try asking:**
>
> 1. "Which warehouses are driving the compute spend increase?"
> 2. "Show me the login failure breakdown by account for the last week."
> 3. "What are the top 10 most expensive query patterns?"
> 4. "How has our storage footprint changed month over month?"
> 5. "Which accounts have the most unresolved critical findings?"

Rules:
- Tailor follow-ups to what the data actually showed — don't use generic questions.
- If a finding was surprising (spike, anomaly, new risk), suggest a drilldown into that specific area.
- If a domain was not covered (e.g. exec summary didn't include auth detail), suggest it.
- Phrase them exactly as a user would type them — short, natural language.

### Caveats

> ⚠️ **Caveats**
>
> - Login and query failure data covers last 7 days only (raw tables limited for performance).
> - Any other freshness, coverage, or inference limitations.

### Optional Sections

Include these when relevant to the user's question:

> 🔐 **Security & Auth Posture** — for security-focused asks
>
> 🏗️ **Storage & Capacity** — for storage/warehouse asks
>
> 👥 **Admin Coverage** — for governance/access asks

Each optional section follows the same pattern: a compact table or numbered list with concrete data.

### Formatting Rules

- Always use emoji section headers for visual scanning.
- Use tables for comparative data (WoW, account-level breakdowns).
- Use numbered lists for risks and action items (priority order).
- Use bullet lists for positive trends and caveats.
- Bold key numbers and account/service names inline.
- Keep the total response concise — aim for one screen of content for executive summaries.

## Guardrails

- This skill is read-only.
- Assume `GLOBALORGADMIN` role before executing golden queries.
- Do not create/alter/drop objects in Org Hub workflows.
- If required data is unavailable, say so directly and provide best-effort alternatives.
- If a metric cannot be derived from available org usage sources, state `unknown` instead of estimating.
