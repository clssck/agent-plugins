# View & Investigate Anomalies

Surface cost anomalies and let the user drive the investigation. Supports this account, all accounts (org-wide), or a specific account.

> **Prerequisites:** The parent router (`../SKILL.md`) has already resolved the user's access flags.
> If the scope changes mid-conversation (e.g., user switches from org-wide to this-account),
> you MUST re-apply the procedure selection rule below — do not guess from procedure names.

> **Anomaly Monitors are handled elsewhere.** This skill covers **account-level and org-level** anomalies only. Any request about a specific **Anomaly Monitor** (a named tag/team/cost-center monitor) — creating, editing, or investigating its anomalies — is the **Manage anomaly monitors** intent: load `../manage-monitors/SKILL.md`.

---

## Phase 1: Fetch & Summarize (always run)

> **Snap & Ask context:** If the parent router routed here from a Snap & Ask block (Step 0), the **scope, unit, account, and time-range are already provided** — use them directly. Use the block's Time-range as `start_date`/`end_date` (instead of the default lookback), and honor the given Usage-Unit (`CREDITS` → `GET_ACCOUNT_ANOMALIES_IN_CREDITS`, `CURRENCY` → `GET_DAILY_CONSUMPTION_ANOMALY_DATA`) and Account-Name. Do not re-ask for scope or dates.

### Step 1: Select Source

Use the source selection table from the parent router's Step 4. Key rules:
- If `has_org_access` → always use `GET_DAILY_CONSUMPTION_ANOMALY_DATA`
- If only `has_account_access` → use `GET_ACCOUNT_ANOMALIES_IN_CREDITS`
- If `fallback_view_only` → use `ANOMALIES_DAILY` view (last resort, credits only)

### Step 2: Fetch Anomaly Data

**If procedure is `GET_DAILY_CONSUMPTION_ANOMALY_DATA`** (currency — the default when user has org access):

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!GET_DAILY_CONSUMPTION_ANOMALY_DATA(
    '<start_date>',
    '<end_date>',
    <account_name>
);
```

Where `<3rd_argument>` is `NULL` (all accounts), `'<account_name>'` (specific account), or `'<current_account>'` (this account in currency). Resolve current account name with `SELECT CURRENT_ACCOUNT_NAME()` if needed.

**If procedure is `GET_ACCOUNT_ANOMALIES_IN_CREDITS`** (credits — only when user lacks org access):

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!GET_ACCOUNT_ANOMALIES_IN_CREDITS(
    '<start_date>',
    '<end_date>',
);
```

**If `fallback_view_only` is true** (last resort — user lacks access to both procedures):

Use the "Fallback: ANOMALIES_DAILY View" query from `references/queries/anomalies.md`. Account-level, credits only, up to 8 hours latency. Procedure-based drill-downs are unavailable — use SQL-based drill-downs (Leading Contributors, top queries, user breakdown) instead.

### Step 3: Present the Summary

Determine the unit label from the source used:
- `GET_ACCOUNT_ANOMALIES_IN_CREDITS` → unit is **credits**
- `GET_DAILY_CONSUMPTION_ANOMALY_DATA` → unit is the `CURRENCY_TYPE` value from the results (e.g. USD)
- `ANOMALIES_DAILY` view (fallback) → unit is **credits**

Filter results to rows where `IS_ANOMALY = TRUE`. Present all anomaly days in a table sorted by variance descending, showing date, consumption, forecasted, and variance (both absolute and percentage).

```
Cost Anomaly Summary
====================
Scope:            <This account | All accounts | Account: <name>>
Period analyzed:  <start> to <end>
Unit:             <credits | currency>
Anomalies detected: <count>

| Date | Consumption | Forecasted | Variance |
|------|-------------|------------|----------|
| ...  | ...         | ...        | +... (+...%) |
```

Highlight the day with the largest positive variance as the **biggest spike**.

**If no anomalies are found**: tell the user, then show the day with the highest consumption instead.
> "No anomalies were detected in the past 90 days. Showing the highest-cost day instead."

**If the user's question already asks about causes or contributors** (e.g., "what caused it", "what contributed most", "why did costs spike", "which accounts"): skip the pause and proceed directly to the matching Phase 2 drill-down below.

**Otherwise, stop here.** Do not automatically drill into contributors, warehouses, or accounts. Let the user ask what they want to know next. If the user seems unsure or doesn't have a follow-up, you may briefly suggest:

> "I can dig into what caused a specific spike, show warehouse consumption breakdowns, or set up notifications for future anomalies."

---

## Phase 2: Drill-Down Reference (user-driven)

Use the table below to match the user's follow-up questions — or drill-down intent detected in the original question — to the right query or procedure. The user may ask multiple follow-ups in sequence — keep the conversation going.

> **Date scoping:** Many reference queries default to "last 7 days" or "last month" time windows. When using them during an anomaly investigation, **adjust the date filter** to target the anomaly date the user is asking about. For example, replace `DATEADD(DAY, -7, CURRENT_DATE())` with the specific anomaly date or a narrow range around it.

> **Current-account limitation:** Queries using `SNOWFLAKE.ACCOUNT_USAGE` views only work for the current account. Additionally, the procedures `GET_HOURLY_CONSUMPTION_BY_SERVICE_TYPE` and `GET_TOP_QUERIES_FROM_WAREHOUSE` also return data for the **current account only** — do NOT call them when investigating a different account or org-wide anomalies. When investigating a different account, use only the cross-account procedures (`GET_TOP_WAREHOUSES_ON_DATE`, `GET_TOP_ACCOUNTS_BY_CONSUMPTION`, `GET_DAILY_CONSUMPTION_ANOMALY_DATA`).

> **Fallback view limitation:** When `fallback_view_only` is true, the `ANOMALY_INSIGHTS` stored procedures (`GET_TOP_WAREHOUSES_ON_DATE`, `GET_HOURLY_CONSUMPTION_BY_SERVICE_TYPE`, `GET_TOP_ACCOUNTS_BY_CONSUMPTION`) are **not available**. Only SQL-based drill-downs using `ACCOUNT_USAGE` views (Leading Contributors, top queries, user breakdown, serverless) will work. If the user asks for a procedure-only drill-down, inform them that it requires higher privileges.

### What caused the spike / top contributors

**Triggered by:** "what caused it", "why did costs spike", "top contributors", "what resources drove this", "explain the anomaly"

**If scope is This account** (or the target account is the current account):

Run the "Leading Contributors to Each Anomaly" query from `references/queries/anomalies.md`.

**If the target account is NOT the current account:**

Fall back to `GET_TOP_WAREHOUSES_ON_DATE` (see "Top warehouses" below).

### Top warehouses

**Triggered by:** "which warehouses", "warehouse breakdown", "top warehouses on that day"

Use `GET_TOP_WAREHOUSES_ON_DATE` from `references/queries/anomalies.md`. Pass `NULL` for this account, or the target account name for org/specific scope.

### Top accounts

**Triggered by:** "which accounts", "top accounts", "account breakdown", "which account spent the most"

> **Only applicable for org-wide scope.** If scope is This account or Specific account, this drill-down is unnecessary — tell the user.

Use `GET_TOP_ACCOUNTS_BY_CONSUMPTION` — `CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!GET_TOP_ACCOUNTS_BY_CONSUMPTION('<target_date>', 10)`.

### Hourly breakdown

**Triggered by:** "hourly breakdown", "what time did the spike happen", "when during the day"

> **Current-account only:** `GET_HOURLY_CONSUMPTION_BY_SERVICE_TYPE` returns data for the **current account only**. It cannot return data for other accounts or the entire organization.

**If scope is This account** (or the target account is the current account):

Use `GET_HOURLY_CONSUMPTION_BY_SERVICE_TYPE` from `references/queries/anomalies.md`.

**If the target account is NOT the current account (specific other account or org-wide):**

Inform the user that the hourly breakdown by service type is **not available** for other accounts — this procedure only supports the current account. Suggest the **top warehouses** drill-down (`GET_TOP_WAREHOUSES_ON_DATE`) as an alternative, since it does support cross-account queries.

### Top queries / expensive queries

**Triggered by:** "which queries", "expensive queries", "what queries ran", "query breakdown"

> **Current-account only:** `GET_TOP_QUERIES_FROM_WAREHOUSE` returns data for the **current account only**. It cannot return data for other accounts or the entire organization. The `ACCOUNT_USAGE`-based queries below are also current-account only.

**If scope is This account** (or the target account is the current account):

1. **If the user identified a specific warehouse** (from a previous drill-down): use `GET_TOP_QUERIES_FROM_WAREHOUSE` for that warehouse (see `references/queries/anomalies.md`).

2. **If no specific warehouse**: use the "Most Expensive Individual Queries" query from `references/queries/users-queries.md`, but **scope the date filter** to the anomaly date.

**If the target account is NOT the current account (specific other account or org-wide):**

Inform the user that query-level drill-downs are **not available** for other accounts — both `GET_TOP_QUERIES_FROM_WAREHOUSE` and the `ACCOUNT_USAGE`-based query views only support the current account. Suggest the **top warehouses** drill-down (`GET_TOP_WAREHOUSES_ON_DATE`) as the deepest available breakdown for remote accounts.

### Who ran the queries / user breakdown

**Triggered by:** "who ran those queries", "which users", "top users", "user breakdown"

Use the "Top Users by Query Costs" query from `references/queries/users-queries.md`, scoped to the anomaly date.

### Serverless / tasks

**Triggered by:** "serverless", "tasks", "snowpipe", "was it serverless"

Use the "Serverless Task Credits" query from `references/queries/serverless.md`, scoped to the anomaly date.

### Trend / pattern around the spike

**Triggered by:** "trend leading up to this", "pattern before the spike", "show the days around it", "context"

No extra query needed — use the anomaly data already fetched in Phase 1. Present the daily consumption values for the 7-14 days surrounding the target date to show the ramp-up and cool-down pattern.

### Different anomaly date

**Triggered by:** "different date", "what about <date>", "investigate <other date>"

Set the new date as the target and let the user ask their next question about it. No need to re-fetch Phase 1 data — it's already available.

### Different account

**Triggered by:** "different account", "what about account X" (org-wide scope only)

Update the target account and let the user ask their next drill-down question.

### Anomaly monitor (tag/team/cost-center scoped)

**Triggered by:** "did the FINANCE monitor spike", "anomalies for monitor X", "show my cost-center monitor's anomaly history", "team anomaly monitor"

This is the **Manage anomaly monitors** intent, not account/org investigation — load `../manage-monitors/SKILL.md`, which handles viewing a monitor's anomalies (`GET_MONITOR_ANOMALIES`) and all monitor operations. Do not investigate monitors from this skill.

### Notifications

**Triggered by:** "set up notifications", "alert me", "email when anomalies happen"

Route based on scope:
- Scope is **All accounts** or **Specific account** → load `../notify-org-anomalies/SKILL.md`
- Scope is **This account** → load `../notify-account-anomalies/SKILL.md`

---

## Reference Files

| Topic | File |
|-------|------|
| Anomaly drill-down queries (top warehouses, hourly, contributors) | `references/queries/anomalies.md` |
| Warehouse queries (top warehouses, comparisons, resize events) | `references/queries/warehouse.md` |
| User and query cost queries | `references/queries/users-queries.md` |
| Serverless task queries | `references/queries/serverless.md` |
| Trend and comparison queries | `references/queries/trends.md` |
