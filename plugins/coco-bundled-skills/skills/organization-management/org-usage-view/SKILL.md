---
name: organization-management-org-usage-view
description: "ORGANIZATION_USAGE view discovery, access troubleshooting, and feature mapping. Use when the user asks about: which org usage views are available, which view should I use for billing, which view for security, why can't I query this view, what role do I need for org usage, organization usage views, org telemetry views, view access troubleshooting, feature to view mapping, what views are enabled."
parent_skill: organization-management
---

# Org Usage View

Resolve organization-level telemetry questions using `SNOWFLAKE.ORGANIZATION_USAGE`.

## When to Use

Use this skill when users ask:
- "Which ORGANIZATION_USAGE views are available to me?"
- "Which view should I use for org-wide billing/cost/security usage?"
- "Why can’t I query a specific ORGANIZATION_USAGE view?"
- "Which Snowflake database role do I need for this view?"

## When NOT to Use

- **Account-local telemetry questions** — If the user asks for data about a SINGLE account or their CURRENT account, advise them to use `SNOWFLAKE.ACCOUNT_USAGE` locally. `SNOWFLAKE.ORGANIZATION_USAGE` is ONLY for cross-account or org-level queries.
- Control-plane mutations (create/alter/drop)
- Org Hub executive synthesis (use `org-hub/SKILL.md`)

## Setup

1. **Load** `../references/global_guardrails.md`: Required context for all organization management operations.

## Workflow

### Step 1: Set Role Context

Follow the Role Context rules in `global_guardrails.md`.

### Step 2: Clarify Ask and Scope

Identify:
- requested business domain (`billing`, `usage`, `security`, `objects`, `governance`)
- specific view(s) requested (if any)
- whether user needs access troubleshooting, mapping guidance, or both

### Step 3: Validate Access Context

Organization usage data is in shared database/schema:
- `SNOWFLAKE.ORGANIZATION_USAGE`

Run minimal discovery first:

```sql
SHOW VIEWS IN SCHEMA SNOWFLAKE.ORGANIZATION_USAGE;
```

If user asks for account inventory context:

```sql
SELECT ACCOUNT_NAME
FROM SNOWFLAKE.ORGANIZATION_USAGE.ACCOUNTS
ORDER BY ACCOUNT_NAME;
```

### Step 4: Map Domain -> Recommended Views

Use these defaults before suggesting alternatives:

- **Billing/Spend**
  - `USAGE_IN_CURRENCY_DAILY`
  - `METERING_DAILY_HISTORY`
  - `METERING_HISTORY`
  - `WAREHOUSE_METERING_HISTORY`
  - `CONTRACT_ITEMS`
  - `REMAINING_BALANCE_DAILY`
- **Storage**
  - `STORAGE_DAILY_HISTORY`
  - `DATABASE_STORAGE_USAGE_HISTORY`
  - `STAGE_STORAGE_USAGE_HISTORY`
  - `TABLE_STORAGE_METRICS`
- **Security/Auth**
  - `TRUST_CENTER_FINDINGS`
  - `USERS`
  - `LOGIN_HISTORY`
  - `SESSIONS`
- **Operations/Reliability**
  - `QUERY_HISTORY`
  - `QUERY_ATTRIBUTION_HISTORY`
  - `TASK_HISTORY`
  - `WAREHOUSE_LOAD_HISTORY`
  - `WAREHOUSE_EVENTS_HISTORY`
- **Object Inventory/Governance**
  - `DATABASES`, `SCHEMATA`, `TABLES`, `VIEWS`, `COLUMNS`
  - `TAGS`, `TAG_REFERENCES`, `POLICY_REFERENCES`

### Step 5: Provide Access Role Mapping

When users lack access, map requested view to expected SNOWFLAKE database role:

- `ORGANIZATION_BILLING_VIEWER` for billing-focused views (for example `USAGE_IN_CURRENCY_DAILY`)
- `ORGANIZATION_USAGE_VIEWER` for operational usage views
- `ORGANIZATION_SECURITY_VIEWER` for security-focused views (for example `TRUST_CENTER_FINDINGS`, `USERS`, `SESSIONS`)
- `ORGANIZATION_OBJECT_VIEWER` for object metadata views
- `ORGANIZATION_GOVERNANCE_VIEWER` for governance/tag/policy views
- `ORGANIZATION_ACCOUNTS_VIEWER` for account-scoped org visibility use cases

For ORGADMIN-enabled regular accounts, remind users that access to the shared `SNOWFLAKE` database privileges may still require explicit grants.

### Step 6: Return Actionable Mapping + Caveats

Always return:
- recommended view(s)
- why each view is chosen
- expected latency/freshness caveat
- required role hints for missing access
- unknowns requiring owner confirmation

## SQL Construction Rules

- Use fully qualified names: `SNOWFLAKE.ORGANIZATION_USAGE.<VIEW_NAME>`.
- Avoid `SELECT *`; select only needed columns.
- Bound time ranges for historical views.
- Prefer daily aggregate views when user asks for trend summaries.
- Include account dimension (`ACCOUNT_NAME`) when cross-account output is expected.

## Latency and Freshness Guidance

- Many ORGANIZATION_USAGE views have non-zero latency (commonly hours, often up to 24h depending on view class).
- If near-real-time precision is requested, explicitly state freshness limitations.
- For each answer, include one caveat line indicating expected lag impact.

## Troubleshooting Playbook

If query fails due to access:
1. Confirm schema visibility:
```sql
SHOW VIEWS IN SCHEMA SNOWFLAKE.ORGANIZATION_USAGE;
```
2. Confirm role context:
```sql
SELECT CURRENT_ROLE();
```
3. Report likely missing SNOWFLAKE database role and required owner follow-up.

If view exists but data appears empty:
- verify time window
- check latency expectations
- confirm organization account vs regular account context

## Output Contract

Return in this order:
- `Requested Capability`
- `Recommended ORGANIZATION_USAGE Views`
- `Why These Views`
- `Access and Role Requirements`
- `Latency/Freshness Caveats`
- `Open Gaps / Owner Follow-up`
