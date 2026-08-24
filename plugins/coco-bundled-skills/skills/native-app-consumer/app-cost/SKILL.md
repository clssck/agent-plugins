---
name: native-app-cost
parent_skill: native-app-consumer
---

# Understand & Manage Native App Cost (Consumer)

## When to Load

From the root `native-app-consumer` skill when the user wants to understand how much an installed native app costs, review its credit/storage usage, add/remove the app from a budget, or manage budget monitoring.

## Prerequisites

- An installed native app in the consumer account
- ACCOUNTADMIN role (or a role with access to `SNOWFLAKE.ACCOUNT_USAGE` and budget management privileges)

## Workflow

### Step 0: Identify the Application

If the app name is already known from a parent skill, skip to Step 1.

If the user is vague ("my apps", "all my native apps"), list installed apps first:
```sql
SHOW APPLICATIONS;
```
Let the user pick which app(s) to review. For multiple apps, repeat Steps 1–2 for each.

Otherwise, **Ask** the user:
```
What is the name of the installed application you want to review costs for?
```

**⚠️ MANDATORY STOPPING POINT**: Do NOT proceed until user responds.

Verify the app exists:
```sql
SHOW APPLICATIONS LIKE '<app_name>';
```

If no results, inform the user the application was not found.

---

### Step 1: Review App Cost History

**Goal:** Show the consumer how many credits and storage bytes the app has used.

Query `APPLICATION_DAILY_USAGE_HISTORY` for the last 30 days:

```sql
SELECT
  USAGE_DATE,
  CREDITS_USED,
  CREDITS_USED_BREAKDOWN,
  STORAGE_BYTES,
  STORAGE_BYTES_BREAKDOWN
FROM SNOWFLAKE.ACCOUNT_USAGE.APPLICATION_DAILY_USAGE_HISTORY
WHERE APPLICATION_NAME = '<app_name>'
  AND USAGE_DATE >= DATEADD(day, -30, CURRENT_DATE())
ORDER BY USAGE_DATE DESC;
```

Present a summary to the user:
- **Total credits** over the period
- **Average daily credits**
- **Credit breakdown by service type** — flatten `CREDITS_USED_BREAKDOWN` to show per-service totals (e.g., `WAREHOUSE_METERING`, `SERVERLESS_TASK`, `SNOWPARK_CONTAINER_SERVICES`, `AUTO_CLUSTERING`)
- **Current storage** (latest day's `STORAGE_BYTES`, converted to MB/GB)
- **Trend** — note if credits are increasing/decreasing week-over-week and highlight the dominant cost driver

If no rows are returned:
> "No usage data found for this app in the last 30 days. The APPLICATION_DAILY_USAGE_HISTORY view has up to one day of latency — if the app was just installed, check back tomorrow."

---

### Step 2: Identify App-Owned vs Shared Resources

**Goal:** Help the consumer understand which compute resources are owned by the app (auto-tracked by budgets) vs shared (must be manually added).

**Warehouses owned by the app:**
```sql
SHOW WAREHOUSES;
```
Filter results where `owner_role_type = 'APPLICATION'` and the owning application matches `<app_name>`.

**Compute pools owned by the app:**
```sql
SHOW COMPUTE POOLS;
```
Filter results where the `application` column matches `<app_name>`.

Present the results:
- **App-owned**: Tracking depends on budget method (see Step 3).
- **Shared** (used by app but not owned): Must be added to a budget separately.

If the app owns no warehouses or compute pools, its costs come from serverless features or shared resources.

---

### Step 3: Set Up Cost Monitoring with a Budget

**Goal:** Help the user add the app to a budget for ongoing monitoring.

**⚠️ MANDATORY STOPPING POINT — Budget choice**: First check for existing budgets:

```sql
SHOW SNOWFLAKE.CORE.BUDGET INSTANCES IN ACCOUNT;
```

If custom budgets exist, present them and ask:
> "You already have these budgets: [list]. Would you like to add this app to an existing budget, or create a new one?"

If no custom budgets exist, ask:
> "Would you like me to create a budget to monitor this app's ongoing credit usage?"

Do NOT proceed until user responds. If the user declines, skip to the **Output** section.

**⚠️ MANDATORY STOPPING POINT — Role choice** (only if creating a new budget):
> "Which role should own the new budget? Should I create a dedicated role (e.g. `BUDGET_ADMIN`), or use the current role?"

Do NOT proceed until user responds. Then create the role and grant it the necessary privileges before creating the budget.

If the user needs a **new budget**, load the `cost-intelligence` budget skill (`cost-intelligence/skills/budget/SKILL.md`) to create one.

#### Native App Budget Methods

There are two ways to add a native app to a budget:

| | Direct inclusion (`ADD_RESOURCE`) | Tag-based (`ADD_RESOURCE_TAG`) |
|---|---|---|
| **App-owned resources** | Automatically tracked | Only if they have the matching tag/value |
| **Shared resources** | Must add separately | Only if they have the matching tag/value |
| **Backfill** | No — from add date only | Yes — from start of current month |
| **Multi-budget** | One budget per app | Multiple budgets via tags |

Present both options to the user and let them choose, unless they've already indicated a preference.

> **⚠️ CRITICAL — Native App Reference Type**
> - Always use `'DATABASE'` as the SYSTEM$REFERENCE domain for native apps — `'APPLICATION'` is not a valid domain and will fail.
> - You cannot `GRANT APPLYBUDGET` directly on a native app. For other resource types (warehouses, tags, etc.), an explicit `GRANT APPLYBUDGET` is required before creating the reference.

#### Method 1: Direct Inclusion

Add the app using `'DATABASE'` as the object type:

```sql
-- IMPORTANT: Use 'DATABASE', not 'APPLICATION' — 'APPLICATION' is not a valid domain
CALL <budget_fqn>!ADD_RESOURCE(
  SYSTEM$REFERENCE('DATABASE', '<app_name>', 'SESSION', 'APPLYBUDGET')
);
```

All objects owned by the app (warehouses, compute pools) are automatically tracked. To also track shared resources identified in Step 2:

```sql
GRANT APPLYBUDGET ON WAREHOUSE <shared_wh> TO ROLE <role>;
CALL <budget_fqn>!ADD_RESOURCE(
  SYSTEM$REFERENCE('WAREHOUSE', '<shared_wh>', 'SESSION', 'APPLYBUDGET')
);
```

#### Method 2: Tag-Based

Tag the app, then add the tag to the budget. App-owned resources are NOT automatically included unless they also carry the tag.

```sql
ALTER APPLICATION <app_name> SET TAG <tag_fqn> = '<tag_value>';
GRANT APPLYBUDGET ON TAG <tag_fqn> TO ROLE <role>;
CALL <budget_fqn>!ADD_RESOURCE_TAG(
  SYSTEM$REFERENCE('TAG', '<tag_fqn>', 'SESSION', 'APPLYBUDGET'),
  '<tag_value>'
);
```

If the app owns warehouses or compute pools, tag them individually with the same tag/value.

#### Verify & Next Steps

Confirm the app is tracked: `CALL <budget_fqn>!GET_BUDGET_SCOPE();`

Mention that budget **email notifications** can be configured to alert when spending approaches the limit (see `cost-intelligence` budget skill). To **remove** an app later, use `REMOVE_RESOURCE` (direct) or `REMOVE_RESOURCE_TAG` (tag-based) with the same reference used to add it.

---

## Stopping Points

- ✋ After Step 0: User provides application name (if not already known)
- ✋ After Step 3 budget prompt: User decides whether to set up budget monitoring and which budget to use
- ✋ After Step 3 role prompt: User decides which role should own the new budget

**Resume rule:** Upon user approval, proceed directly to next step without re-asking.

## Output

- App cost history presented (credits, storage, service-type breakdown, trend)
- App-owned vs shared resources identified
- App added to a budget (existing or new, if user requested), verified with `GET_BUDGET_SCOPE`
