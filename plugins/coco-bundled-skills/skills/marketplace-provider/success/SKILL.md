---
name: marketplace-provider-success
description: "Provider success and best practices for Snowflake Marketplace. Use when: provider wants to improve discoverability, understand analytics, manage consumers, optimize listings, or improve listing performance. Triggers: provider success, best practices, improve listing, discoverability, analytics, telemetry, consumer management, listing performance, optimize, listing metrics."
---

# Provider Success & Best Practices — Mode 5

Helps providers get more out of their Marketplace listings — improve discoverability, understand analytics, manage consumers, and keep listings healthy.

---

## Step 1: What Would You Like to Improve?

Use `ask_user_question` to identify the focus area:

- **Listing discoverability** — improve how consumers find my listing
- **Analytics & telemetry** — understand who's using my listing and how
- **Consumer management** — handle requests, approvals, private offers
- **Listing health & maintenance** — keep metadata fresh, update data, retire listings
- **Paid listing performance** — trial conversion, offer management, revenue tracking

Jump to the relevant section below.

---

## Listing Discoverability

Strong metadata is the primary driver of discoverability on Snowflake Marketplace.

### Title & Description
- **Title**: Be specific — include the data type, geography, and frequency (e.g. "US Retail Foot Traffic — Daily, ZIP Code Level" vs "Foot Traffic Data")
- **Short description**: Lead with the core value to the consumer, not what the data is
- **Full description**: Follow the 4-paragraph structure — what it is → use cases → quality signals → getting started

### Categories & Business Needs
- Choose the **most precise category** — `LOCAL` beats `BUSINESS` for POI data
- Add **2–3 business needs** from the official list — these surface your listing in filtered searches. Refer to the business needs table in Mode 3 (Listings) for valid values.

### Keywords & Search
- Use specific, technical terms consumers would actually search (e.g. "NAICS codes", "Census FIPS", "ISO 3166")
- Avoid generic filler words ("data", "analytics", "insights")
- Include alternate names for the same concept (e.g. "ZIP code" and "postal code")

### Data Attributes
- Fill in `data_attributes` accurately — `refresh_rate`, `geography`, and `time_range` appear as filters in Marketplace search
- Consumers often filter by geography and recency — incomplete attributes mean your listing won't surface in those filtered views

### Documentation & Usage Examples
- A documentation URL is required for Marketplace listings — make it genuinely useful (schema docs, methodology, FAQ)
- Include **2–3 usage examples** with real SQL that consumers can run immediately after installing the listing

### Getting Featured & Co-Marketing
- **Featured sections:** Snowflake curates featured listing sections on the Marketplace homepage — providers cannot self-nominate, but strong consumer adoption and a complete, high-quality listing improve chances. Talk to your PDM about featured placement opportunities.
- **Co-marketing:** High-performing providers may be featured in Snowflake blog posts, case studies, or partner spotlights. Contact your PDM to explore co-marketing opportunities.
- **Partner enablement:** The [GTM Partner Readiness track on SPN Learn](https://training.snowflake.com/lmt/xlr8login.login?site=sf&in_redirecturl=deeplinkLP%3D199178706) covers go-to-market planning, field collaboration, and launch preparation.
- **Discoverability tip:** A complete description, accurate business needs tags, and correct categories directly affect search ranking on the Marketplace.

---

## Analytics & Telemetry

Track listing performance using the `DATA_SHARING_USAGE` schema, available in your Snowflake account.

### Key Views

| View | What it shows | Consumer identity? |
|------|--------------|--------------------|
| `SNOWFLAKE.DATA_SHARING_USAGE.LISTING_EVENTS_DAILY` | GET, REQUEST, TRIAL, PURCHASE, CANCEL actions | ✅ Revealed on action |
| `SNOWFLAKE.DATA_SHARING_USAGE.LISTING_TELEMETRY_DAILY` | Aggregate views, clicks, events by region | ❌ Aggregate only |
| `SNOWFLAKE.DATA_SHARING_USAGE.LISTING_CONSUMPTION_DAILY` | Active consumers running queries on the listing | ✅ Company + account |
| `SNOWFLAKE.DATA_SHARING_USAGE.LISTING_ACCESS_HISTORY` | Which specific objects/columns consumers queried | ✅ Per query event |
| `SNOWFLAKE.DATA_SHARING_USAGE.MONETIZED_USAGE_DAILY` | Daily consumer usage for paid listings | ✅ Revealed |
| `SNOWFLAKE.DATA_SHARING_USAGE.MARKETPLACE_LISTING_INVOICE_STATUS` | Invoice status for paid listings | ✅ Revealed |
| `SNOWFLAKE.DATA_SHARING_USAGE.MARKETPLACE_DISBURSEMENT_REPORT` | Stripe payouts disbursed to your bank account | N/A |
| `SNOWFLAKE.ACCOUNT_USAGE.APPLICATION_STATE` | Consumer instances of your Native App | ✅ Revealed |
| `SNOWFLAKE.ACCOUNT_USAGE.APPLICATION_DAILY_USAGE_HISTORY` | Compute credits consumed by consumers of your Native App | ✅ Revealed |

> ℹ️ **Consumer identity privacy model:** Individual consumer identity (name, org, account) is only revealed when they take an explicit action — GET, REQUEST, TRIAL, or PURCHASE. For listing **views and clicks**, only aggregate counts are available. Providers cannot see who browsed their listing without converting.

> ⏱️ **Data latency:** Views in `DATA_SHARING_USAGE` are typically refreshed every 4–6 hours, with a maximum latency of 48 hours. If data appears stale beyond 2 days, this may indicate a pipeline issue — ask the provider to open a support case.

> 🔐 **Access:** All views require `ACCOUNTADMIN` by default. Privileges can be granted to other roles — this requires ACCOUNTADMIN approval. Do NOT run this without first confirming with the provider: `GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE <role>;`

---

### Top 20 Provider Analytics Questions

> **Before answering:** Use `ask_user_question` to identify which specific analytics question the provider wants answered. Then run only the relevant query below. **Do not present the full list unprompted.**

#### Q1: Who is actively querying my data? (best lead signal)
```sql
SELECT
    listing_name,
    consumer_account_name,
    consumer_organization,
    SUM(JOBS)          AS total_queries,
    MAX(EVENT_DATE)    AS last_query_date
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_CONSUMPTION_DAILY
WHERE EVENT_DATE >= DATEADD('day', -30, CURRENT_DATE)
GROUP BY 1, 2, 3
ORDER BY total_queries DESC;
```

#### Q2: How do I get a leads list with consumer contact info (name, email)?
SQL views don't expose first/last name or email. Use:
- **Provider Studio → [Listing] → Analytics → Detailed Metrics → Listings Installed** — shows company name, account name, first/last name, email, and region.
- `LISTING_CONSUMPTION_DAILY` — active query users (company + account, no email).

#### Q3: Can I see who *viewed* my listing page?
No. `LISTING_TELEMETRY_DAILY` shows **aggregate** view/click counts only. Individual consumer identity is **not** exposed for views or clicks — only for GET, REQUEST, TRIAL, PURCHASE actions.

#### Q4: What regions are my viewers coming from?
```sql
SELECT
    listing_name,
    snowflake_region,
    region_group,
    event_type,
    SUM(event_count) AS event_count
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_TELEMETRY_DAILY
WHERE event_date >= DATEADD('day', -30, CURRENT_DATE)
  AND event_type IN ('LISTING VIEW', 'LISTING CLICK')
GROUP BY 1, 2, 3, 4
ORDER BY listing_name, event_count DESC;
```
Useful for building a business case to expand to additional regions.

#### Q5: How do I confirm a consumer successfully received access?
```sql
SELECT listing_name, event_date, event_type, action,
       consumer_account_name, consumer_organization
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_EVENTS_DAILY
WHERE event_type = 'GET' AND action = 'COMPLETED'
  AND event_date >= DATEADD('day', -30, CURRENT_DATE)
ORDER BY event_date DESC;
```
Also check `LISTING_CONSUMPTION_DAILY` — if the consumer appears there, they have successfully mounted and queried.

#### Q6: What specific tables and columns is my consumer accessing?
You **cannot** see the SQL query text, but you can see which objects (tables, views, columns, functions, procedures) were accessed:
```sql
SELECT
    lah.QUERY_DATE,
    lah.consumer_account_name,
    lah.consumer_name,
    los.value:"objectDomain"::STRING AS object_type,
    los.value:"objectName"::STRING   AS object_name
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_ACCESS_HISTORY AS lah
JOIN LATERAL FLATTEN(input => lah.SHARE_OBJECTS_ACCESSED) AS los
ORDER BY lah.consumer_account_name, lah.QUERY_DATE;
```

#### Q7: What is my view-to-install conversion rate?
```sql
WITH views AS (
    SELECT listing_name, SUM(event_count) AS total_views
    FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_TELEMETRY_DAILY
    WHERE event_date >= DATEADD('day', -30, CURRENT_DATE)
      AND event_type = 'LISTING VIEW'
    GROUP BY listing_name
),
gets AS (
    SELECT listing_name, SUM(event_count) AS total_gets
    FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_TELEMETRY_DAILY
    WHERE event_date >= DATEADD('day', -30, CURRENT_DATE)
      AND event_type = 'GET' AND action = 'COMPLETED'
    GROUP BY listing_name
)
SELECT v.listing_name, v.total_views,
    COALESCE(g.total_gets, 0) AS total_gets,
    ROUND(COALESCE(g.total_gets, 0) / NULLIF(v.total_views, 0) * 100, 2) AS conversion_pct
FROM views v
LEFT JOIN gets g ON v.listing_name = g.listing_name
ORDER BY conversion_pct DESC;
```

#### Q8: How do I see all consumer actions across my listings (last 30 days)?
```sql
SELECT listing_name, event_date, event_type,
       consumer_account_name, consumer_organization
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_EVENTS_DAILY
WHERE event_date >= DATEADD('day', -30, CURRENT_DATE)
ORDER BY event_date DESC;
```

#### Q9: How do I get a summary of all action types per listing?
```sql
SELECT listing_name, event_type, COUNT(*) AS event_count
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_EVENTS_DAILY
WHERE event_date >= DATEADD('day', -90, CURRENT_DATE)
GROUP BY listing_name, event_type
ORDER BY listing_name, event_count DESC;
```

#### Q10: Can I see what search keywords led users to my listing?
No — keyword-level search data is **not available** to providers. Only aggregate view/click counts are available via `LISTING_TELEMETRY_DAILY`.

#### Q11: My telemetry looks stale — is there a pipeline issue?
Normal latency is up to **48 hours**. If data has been missing for longer than 2 days:
1. Check Provider Studio Analytics — if it's also stale, it's a pipeline issue (not just a view lag)
2. Open a support case referencing the deployment region and the last date data was seen

#### Q12: How do I check invoice status for my paid consumers?
```sql
SELECT listing_display_name, consumer_account_name,
       total_billed_amount, invoice_status,
       stripe_display_number, invoice_date
FROM SNOWFLAKE.DATA_SHARING_USAGE.MARKETPLACE_LISTING_INVOICE_STATUS
ORDER BY invoice_date DESC;
```
> Latency up to 48 hours. Requires `ACCOUNTADMIN`.

#### Q13: How do I reconcile which Stripe payout maps to which deal?
```sql
SELECT i.listing_display_name, i.consumer_account_name,
       i.total_billed_amount, i.invoice_status,
       i.stripe_display_number,
       d.disbursement_amount, d.disbursement_date
FROM SNOWFLAKE.DATA_SHARING_USAGE.MARKETPLACE_LISTING_INVOICE_STATUS i
LEFT JOIN SNOWFLAKE.DATA_SHARING_USAGE.MARKETPLACE_DISBURSEMENT_REPORT d
  ON i.stripe_display_number = d.stripe_display_number
ORDER BY i.invoice_date DESC;
```
> Snowflake pays out weekly — multiple deals may be batched into one payout. Payments arrive up to **30 days** after the consumer pays.

#### Q14: How do I monitor daily paid consumer usage?
```sql
-- Account-level:
SELECT * FROM SNOWFLAKE.DATA_SHARING_USAGE.MONETIZED_USAGE_DAILY
ORDER BY usage_date DESC;

-- Or org-level (broader view):
SELECT * FROM SNOWFLAKE.ORGANIZATION_USAGE.MONETIZED_USAGE_DAILY
ORDER BY usage_date DESC;
```
Includes the `PRICING_PLAN` field to confirm which pricing plan applies per consumer.

#### Q15: How do I track trial-to-paid conversion?
```sql
SELECT consumer_account_name, listing_name, event_type, event_date
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_EVENTS_DAILY
WHERE event_type IN ('TRIAL', 'PURCHASE', 'GET')
ORDER BY consumer_account_name, listing_name, event_date;
```
Look for consumers with a `TRIAL` event followed by a `PURCHASE` event.

#### Q16: How do I see the status of consumer instances of my Native App?
```sql
SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.APPLICATION_STATE
ORDER BY created_on DESC;
```
Shows all consumer accounts where your Native App is installed, including install state and version.

#### Q17: How do I track compute credit usage from my Native App consumers?
```sql
SELECT application_name, listing_global_name,
       usage_date, credits_used, credits_used_breakdown
FROM SNOWFLAKE.ACCOUNT_USAGE.APPLICATION_DAILY_USAGE_HISTORY
WHERE listing_global_name = '<YOUR_LISTING_GLOBAL_NAME>'
ORDER BY usage_date DESC;
```
> This is in `ACCOUNT_USAGE`, not `DATA_SHARING_USAGE`. Useful when consumers see compute charges separate from listing fees.

#### Q18: How do I get notified when someone installs my app or starts a trial?
There is **no built-in email notification** for installs or trial starts. Two options:

**Option A — Snowflake Alert (up to 2-day latency):**
Create a Snowflake Alert on `LISTING_EVENTS_DAILY` to send an email notification when new GETs appear.
Reference: [Snowflake Notification Integrations](https://docs.snowflake.com/en/user-guide/notifications/about-notifications)

**Option B — External Access Integration in Native App:**
Add an EAI to your app that pings a provider-controlled endpoint when the app is installed. Note: requires the consumer to grant EAI usage — not guaranteed for all installs.

#### Q19: How do I automate reporting to my finance team?
Options (no Snowflake login required for recipients):
- **Download CSV** from a Snowsight worksheet
- **Streamlit in Snowflake** — use the `telemetry_streamlit_app/streamlit_app.py` in this skill package
- **Power BI / Tableau** — connect directly to `DATA_SHARING_USAGE` views
- **Snowflake Notebooks** — build scheduled reports that email results

#### Q20: What does "Queries Executed" in Provider Studio mean?
"Queries Executed" pulls from `LISTING_CONSUMPTION_DAILY` — it counts **jobs** (query executions) that resolve objects in the data share or Native App. One Streamlit interaction may trigger multiple backend jobs, so the count may exceed the number of visible user actions.

---

### Telemetry Policy Reminders
- Usage metrics shared by Snowflake are **Confidential Information** per [Provider & Consumer Policies](https://docs.snowflake.com/en/collaboration/provider-consumer-policies)
- Providers may **not** publish benchmarks or reveal adoption figures derived from these metrics
- Consumer personal data from telemetry may only be used for marketing of the provider's own products, with required consents

### Streamlit Telemetry Dashboard

> ⚠️ **STOP BEFORE RUNNING ANY SQL — MANDATORY CONFIRMATION REQUIRED**
> Do not execute any DDL in this section without first presenting the full resolved SQL (with the provider's actual database, schema, and warehouse filled in) and receiving explicit confirmation ("Yes, proceed").

For a fully interactive dashboard built on these views, a ready-to-deploy **Streamlit in Snowflake** app is available in this skill package at `success/telemetry_streamlit_app/` (`streamlit_app.py`, `pyproject.toml`, `environment.yml`).

**Dependencies (do not assume these are pre-installed):** the app imports `streamlit`, `pandas`, and `matplotlib`. Only `streamlit` and `pandas` ship pre-installed on SiS; **`matplotlib` does not**. The Consumption heatmap calls pandas `Styler.background_gradient()`, which imports matplotlib at runtime, so the app **will crash on the Consumption tab** unless matplotlib is declared. The correct dependency file depends on the runtime (see below): container runtime uses `pyproject.toml`, warehouse runtime uses `environment.yml`. Both are shipped in the package.

**What it includes:**
- Overview tab: jobs, users, GETs, views, conversion rate, period-over-period deltas
- Consumption tab: daily trends, listing breakdown, query volume by region, heatmap
- Consumers tab: top consumers table, usage by region
- Events & Funnel tab: daily event chart, GET/REQUEST/TRIAL/PURCHASE funnel, recent event log
- Leads tab: active trial consumers, converted trials, active non-trial orgs

#### Step 0: Choose the runtime (container is the default)

Streamlit in Snowflake apps run on one of two runtimes, and this determines the entire deploy path:

| Runtime | App runs on | Packages from | Extra prerequisites |
|---|---|---|---|
| **Container (default)** | a compute pool | PyPI via `pyproject.toml` | a compute pool + a PyPI External Access Integration (EAI) |
| **Warehouse (fallback)** | a warehouse | Anaconda via `environment.yml` | none |

> **Default to container runtime.** On modern accounts, creating a new warehouse-runtime Streamlit is **rejected**: `SYSTEM$WAREHOUSE_RUNTIME is unsupported for new Streamlit apps. Please use SYSTEM$ST_CONTAINER_RUNTIME_PY3_11 instead.` Container runtime (`SYSTEM$ST_CONTAINER_RUNTIME_PY3_11`, Python 3.11) is the path that works everywhere it is GA. Use the **warehouse fallback (Option C)** only if the provider's account cannot provision a compute pool or a PyPI EAI, or if the account still permits warehouse-runtime apps and they prefer the simpler setup.
>
> Note: even on container runtime, a `QUERY_WAREHOUSE` is still required. The compute pool runs the app; the warehouse runs the app's SQL queries.

Use `ask_user_question` to let the provider choose their deployment method: **Option A** (Snowsight UI, quickest), **Option B** (container-runtime SQL, reproducible), or **Option C** (warehouse-runtime SQL, fallback).

#### Step 1: Container prerequisites (discover, do not assume)

Run these to find (or create) the two container-runtime prerequisites in the **provider's own account**.

**Compute pool** (the container runs here):
```sql
-- Preferred: the account default for Streamlit
SHOW PARAMETERS LIKE 'DEFAULT_STREAMLIT_COMPUTE_POOL' IN ACCOUNT;
-- Otherwise, list pools the provider can use and pick an ACTIVE one:
SHOW COMPUTE POOLS;
```
The app owner needs `USAGE` on the chosen pool. If none exists and the provider has privileges:
```sql
CREATE COMPUTE POOL IF NOT EXISTS streamlit_pool
  MIN_NODES = 1 MAX_NODES = 1 INSTANCE_FAMILY = CPU_X64_XS AUTO_RESUME = TRUE;
```

**PyPI External Access Integration** (lets the container install packages from PyPI):
```sql
SHOW EXTERNAL ACCESS INTEGRATIONS;  -- look for PYPI_ACCESS_INTEGRATION or similar
```
If none exists and the provider has `CREATE INTEGRATION`:

> ⚠️ **MANDATORY CHECKPOINT — requires admin-level privileges.** Present the SQL below, confirm the provider approves running account-level DDL, and wait for explicit confirmation before executing.

```sql
CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION pypi_access_integration
  ALLOWED_NETWORK_RULES = (snowflake.external_access.pypi_rule)
  ENABLED = true;
```
`snowflake.external_access.pypi_rule` is a Snowflake-managed rule present in every account. If the provider's role lacks `CREATE INTEGRATION`, give them this for an admin to run — **do NOT execute without their explicit approval:**
```sql
CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION pypi_access_integration
  ALLOWED_NETWORK_RULES = (snowflake.external_access.pypi_rule) ENABLED = true;
GRANT USAGE ON INTEGRATION pypi_access_integration TO ROLE <provider_role>;
```

**Option A: Quick preview (Snowsight UI, no CLI needed):**
1. In Snowsight, go to **Projects -> Streamlit -> + Streamlit App** (not Workspace; must use the Projects path to create a named STREAMLIT object)
2. Name the app, choose a database and schema, select a warehouse
3. In **App settings**, set **Python environment -> Run on container**, then choose your compute pool (this is the default on modern accounts)
4. Replace all default code in the editor with the contents of `streamlit_app.py`
5. Open the **Packages** dropdown and add `matplotlib` (confirm `pandas` and `streamlit` are present). **Skipping this is what breaks the Consumption tab**: matplotlib is not pre-installed
6. Click **Run**

> Note: Do NOT use "My Workspace" for this. Workspace Streamlits do not reliably pick up dependency files and lack the Packages picker.

**Option B: Container-runtime SQL deployment (recommended, reproducible):**

Use `ask_user_question` to collect database, schema, warehouse, compute pool, and EAI (resolved in Step 1).

> MANDATORY CHECKPOINT: Before executing, present the resolved SQL below with the provider's actual database, schema, warehouse, compute pool, and EAI filled in, and wait for explicit confirmation ("Yes, proceed") before running any DDL.

```sql
-- Step 1: Create stage
CREATE STAGE IF NOT EXISTS <DATABASE>.<SCHEMA>.streamlit_stage;

-- Step 2: Upload BOTH files from a terminal (SnowSQL or snow CLI).
--         pyproject.toml is REQUIRED on container runtime: it declares matplotlib
--         (and pins streamlit>=1.50, required by container runtime). Without it the
--         Consumption tab crashes with ModuleNotFoundError: matplotlib.
-- PUT file://path/to/streamlit_app.py @<DATABASE>.<SCHEMA>.streamlit_stage AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
-- PUT file://path/to/pyproject.toml   @<DATABASE>.<SCHEMA>.streamlit_stage AUTO_COMPRESS=FALSE OVERWRITE=TRUE;

-- Step 3: Create the Streamlit object on container runtime.
--         Packages are resolved from PyPI at build time via the EAI.
CREATE OR REPLACE STREAMLIT <DATABASE>.<SCHEMA>.PROVIDER_TELEMETRY_DASHBOARD
  FROM '@<DATABASE>.<SCHEMA>.streamlit_stage'
  MAIN_FILE = 'streamlit_app.py'
  QUERY_WAREHOUSE = <WAREHOUSE>
  RUNTIME_NAME = 'SYSTEM$ST_CONTAINER_RUNTIME_PY3_11'
  COMPUTE_POOL = <COMPUTE_POOL>
  EXTERNAL_ACCESS_INTEGRATIONS = (<PYPI_EAI>)
  TITLE = 'Provider Telemetry Dashboard';

-- Step 4: Make it live
ALTER STREAMLIT <DATABASE>.<SCHEMA>.PROVIDER_TELEMETRY_DASHBOARD
  ADD LIVE VERSION FROM LAST;
```

> Verify packages resolved: open the app and click the **Consumption** tab. The container builds on first load (pulls matplotlib/pandas/streamlit from PyPI, ~1-2 minutes). If the heatmap renders, matplotlib installed correctly. A `ModuleNotFoundError: matplotlib` means `pyproject.toml` was not staged, or the EAI was not attached (re-check Steps 1-2).

> Note: `snow streamlit deploy` (Snowflake CLI >= 3.14.0) also deploys container-runtime apps using the `snowflake.yml` manifest in the package. The SQL path above is equivalent and needs no CLI.

**Option C: Warehouse-runtime SQL deployment (fallback only):**

Use this **only** when the account cannot provision a compute pool or PyPI EAI, or still permits warehouse-runtime apps and the provider prefers the simpler setup. On many modern accounts this `CREATE` is rejected (see Step 0).

> MANDATORY CHECKPOINT: present the resolved SQL with the provider's actual database, schema, and warehouse filled in, and wait for explicit confirmation ("Yes, proceed") before running any DDL.

```sql
CREATE STAGE IF NOT EXISTS <DATABASE>.<SCHEMA>.streamlit_stage;

-- Upload the app + environment.yml (warehouse runtime reads packages from environment.yml).
-- PUT file://path/to/streamlit_app.py @<DATABASE>.<SCHEMA>.streamlit_stage AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
-- PUT file://path/to/environment.yml  @<DATABASE>.<SCHEMA>.streamlit_stage AUTO_COMPRESS=FALSE OVERWRITE=TRUE;

CREATE OR REPLACE STREAMLIT <DATABASE>.<SCHEMA>.PROVIDER_TELEMETRY_DASHBOARD
  FROM '@<DATABASE>.<SCHEMA>.streamlit_stage'
  MAIN_FILE = 'streamlit_app.py'
  QUERY_WAREHOUSE = <WAREHOUSE>
  TITLE = 'Provider Telemetry Dashboard';

ALTER STREAMLIT <DATABASE>.<SCHEMA>.PROVIDER_TELEMETRY_DASHBOARD
  ADD LIVE VERSION FROM LAST;
```

> The shipped `environment.yml` lists package **names only** (`streamlit`, `pandas`, `matplotlib`) so Snowflake's Anaconda channel resolves a compatible version for whatever Python the warehouse app uses. Do not hardcode exact conda pins: the available versions differ by Python runtime, so a pinned version can fail with "package not found". If you need reproducible pins, run `SELECT package_name, version, runtime_version FROM INFORMATION_SCHEMA.PACKAGES WHERE language='python' AND package_name IN ('streamlit','pandas','matplotlib')` and pin versions confirmed present for the app's Python runtime.

#### Troubleshooting deployment & runtime errors (the provider can self-serve)

This app is the provider's own object: they can edit `streamlit_app.py` and redeploy it themselves at any time. When a deploy fails or the app shows an error, do not just escalate. Run this loop:

1. **Ask the provider to copy and paste the full error text** (the red Streamlit traceback, or the SQL error). Say plainly: "Paste the entire error here and I'll tell you what it means and fix it."
2. **Summarize the error in one or two plain-language sentences** so the provider understands what went wrong (not just the stack trace).
3. **Identify the fix** using the table below. The fix is one of: (a) an app-code change to `streamlit_app.py`, (b) a dependency change (`pyproject.toml` / `environment.yml`), or (c) a deploy-parameter change (compute pool, EAI, warehouse).
4. **Apply it.** If it is an app-code or dependency change, edit the file directly, then redeploy with the loop below. If it is a deploy-parameter change, present the corrected SQL.
5. **Redeploy and re-verify** (open the app, check the Consumption tab).

> MANDATORY CHECKPOINT: before running any fix DDL, present the resolved SQL and wait for explicit confirmation ("Yes, proceed").

**Redeploy loop after editing `streamlit_app.py` or a dependency file** (container runtime; files are copied at CREATE time, so you must re-stage and re-create):
```sql
-- PUT the changed file(s) again (overwrites the staged copy):
-- PUT file://path/to/streamlit_app.py @<DATABASE>.<SCHEMA>.streamlit_stage AUTO_COMPRESS=FALSE OVERWRITE=TRUE;

CREATE OR REPLACE STREAMLIT <DATABASE>.<SCHEMA>.PROVIDER_TELEMETRY_DASHBOARD
  FROM '@<DATABASE>.<SCHEMA>.streamlit_stage'
  MAIN_FILE = 'streamlit_app.py'
  QUERY_WAREHOUSE = <WAREHOUSE>
  RUNTIME_NAME = 'SYSTEM$ST_CONTAINER_RUNTIME_PY3_11'
  COMPUTE_POOL = <COMPUTE_POOL>
  EXTERNAL_ACCESS_INTEGRATIONS = (<PYPI_EAI>)
  TITLE = 'Provider Telemetry Dashboard';

ALTER STREAMLIT <DATABASE>.<SCHEMA>.PROVIDER_TELEMETRY_DASHBOARD ADD LIVE VERSION FROM LAST;
```

**Common errors and fixes:**

| Error text (or symptom) | What it means | Fix |
|---|---|---|
| `SYSTEM$WAREHOUSE_RUNTIME is unsupported for new Streamlit apps...` | The account blocks warehouse-runtime apps | Use the container-runtime deploy (Option B), not Option C |
| `ModuleNotFoundError: matplotlib` (on the Consumption tab) | matplotlib was not installed | Container: confirm `pyproject.toml` was staged and the EAI is attached. Warehouse: confirm `environment.yml` was staged |
| `Failed to retrieve packages from the package server. Have you enabled External Access Integration (EAI)?` | Container runtime cannot reach PyPI | Attach a PyPI EAI: `ALTER STREAMLIT ... SET EXTERNAL_ACCESS_INTEGRATIONS = (<PYPI_EAI>)`, or add it in the CREATE (Step 1) |
| `invalid property 'COMPUTE_POOL'` / compute pool not found / no USAGE | The compute pool is missing or not granted | Re-run the Step 1 pool discovery; pick an ACTIVE pool the provider has `USAGE` on, or create one |
| `'<' not supported between instances of 'datetime.date' and 'str'` | A date column is being compared to a string | App-code fix: compare dates to dates, not to `.isoformat()` strings (already fixed in the shipped app) |
| `package ... not found` / version not available | A pinned package version does not exist for this runtime | Use names-only in `environment.yml`, or pin a version confirmed present via `INFORMATION_SCHEMA.PACKAGES` |
| A specific view/column error (e.g. `invalid identifier`) | A `DATA_SHARING_USAGE` column differs in this account | App-code fix: adjust the affected query in `streamlit_app.py`; the views are stable but confirm column names with `DESCRIBE` |

If the error is not in this table, summarize it for the provider, make your best-effort fix to `streamlit_app.py` or the deploy parameters, redeploy, and iterate. Reassure the provider that the app is fully editable on their side and that small changes (a column name, a chart, a filter) are safe for them to make and redeploy.

### Provider Studio Analytics Tab
In addition to SQL queries, navigate to **Marketplace → Provider Studio → [Listing] → Analytics** for a visual dashboard of views, installs, and requests over time.

---

## Consumer Management

### Private Listings & Offers
- To add a new consumer to a private listing, navigate to **Provider Studio → [Listing] → Share → Add consumer**
- Consumer account identifier format: `orgname.accountname`
  ```sql
  -- Find a consumer's org and account name:
  -- Ask the consumer to run: SELECT CURRENT_ORGANIZATION_NAME(), CURRENT_ACCOUNT_NAME();
  ```
- For private paid offers, navigate to **Provider Studio → [Listing] → Offers → Create offer**

### Handling Consumer Questions
- Consumers can contact providers through the listing's support contact
- Expected response time: **3 business days** per Provider Policies
- For disputes, submit a case: [Provider Onboarding Case Form](https://snowforce.my.site.com/s/provider-onboarding-case)

### Consumer Billing & Payment

When a consumer (or prospect) asks how to pay for a Marketplace listing:

**Payment methods:**
| Method | How it works |
|--------|-------------|
| **MCD (Marketplace Capacity Drawdown)** | Prepaid committed capacity reserved for Marketplace purchases. Applied automatically when the listing is MCD-compatible. Consumer must be enrolled; provider does not. |
| **Credit card** | Charged automatically per payment schedule. No transaction fees. Set up via Admin → Billing → Marketplace billing → Consumer billing → Activate account. |
| **Bank transfer (ACH / wire)** | Consumer pays via a virtual bank account number (VBAN) attached to each invoice. Must include invoice number (format `SM-XXXXX`) in the memo/reference line. |

**Billing basics:**
- All purchases are billed in **USD**
- Marketplace invoices are **separate** from regular Snowflake usage invoices
- Usage-based plans: billed monthly, only for months with usage
- Flat-fee plans: billed upfront for the term
- Invoices visible in **Admin → Billing → Marketplace billing → Consumer billing**

**Prerequisites for consumers:**
- ACCOUNTADMIN role or `PURCHASE DATA EXCHANGE LISTING` privilege
- Billing address must be in a [supported country](https://docs.snowflake.com/en/collaboration/consumer-listings-paying#confirm-your-billing-location-is-supported) (~32 countries including US, UK, EU, Japan, Canada, Australia)
- ORGADMIN must accept the Snowflake Provider and Consumer Terms (**Admin → Terms**)

**MCD details:**
- Consumer's organization must have a committed capacity contract and be enrolled (contact their Snowflake AE to enroll)
- Geographic restrictions: US (excluding Florida), Japan, UK (private preview), Mexico (private preview), Switzerland (private preview)
- NOT available to: resellers, GovCloud, Google Cloud Marketplace contracts, monthly billing accounts, On Demand accounts
- Off-platform listings are NOT MCD-compatible
- MCD-eligible listings show a "Pay with MCD" label on the Marketplace

**For a provider to be MCD-eligible**, four things are required:
1. **Provider billing and shipping address in an eligible country** — providers do not need to enroll in MCD, but must be located in a supported geography: US (excluding Florida), Japan, UK (private preview), Mexico (private preview), or Switzerland (private preview). Japan requires both provider and consumer to have Japanese billing and shipping addresses. If the provider is not in a supported country, they cannot accept MCD payments — direct them to their Snowflake AE.
2. **Create a provider profile** — see [Manage your provider profile](https://docs.snowflake.com/collaboration/provider-profiles-managing) and [Provider Playbook, page 46](https://www.snowflake.com/wp-content/uploads/2023/08/sm-provider-playbook-extended-ver.pdf#page=46)
3. **Set up provider payouts (Stripe)** — see [Set up Stripe to get paid for listings](https://docs.snowflake.com/en/collaboration/provider-becoming#label-set-up-stripe-listings)
4. **Create a paid listing** — see [Create and publish a listing](https://docs.snowflake.com/collaboration/provider-listings-creating-publishing)

**MCD deal execution (provider workflow):**

When a provider asks how to transact with MCD, walk them through this process:

*Provider prerequisites (do these first):*
1. Align with the consumer's Snowflake AE to confirm MCD eligibility and the eligible amount
2. Consumer opt-in is handled by the AE: AE creates an amendment → consumer signs it → AE uploads to Snowflake system → AE confirms "closed won" in Salesforce
3. Ensure Provider Payout Method is set up (Provider Playbook → 5) Paid Listings >> Set Up Payout Method)
4. Ensure Marketplace Profile is created if not already done

*Step 1 — Calculate offer amount:*
- Snowflake calculates and adds sales tax to the consumer's invoice — **do NOT include sales tax in the offer amount**
- Coordinate with the consumer's AE to confirm whether sales tax applies to this transaction
- Direct all tax questions to: tax@snowflake.com

*Step 2 — Create and publish the paid listing:*
- **Confirm with the consumer's AE that funds are "closed won" in Salesforce before proceeding**
- If the provider **already has a paid listing** for this product → skip to the private offer step below
- If not → Navigate to Provider Studio → click "+ Create listing" → set "Access Type" to "Paid"
- For private offers: insert the consumer's account identifier (format: `orgname.accountname`)
  - To get the identifier, send the consumer: *"I need your Data Sharing Account Identifier (format `orgname.accountname`). To find it, follow these [instructions](https://docs.snowflake.com/en/user-guide/admin-account-identifier)."*
- MCD funds are at the **organization level** — consumer can use any account within the enrolled org to purchase
- After publishing: copy the offer URL and send it to the consumer

*Step 3 — Consumer purchases (share with your consumer):*
- Consumer verifies their MCD balance: query `MARKETPLACE_CAPACITY_DRAWDOWN_BALANCE` column in `SNOWFLAKE.ORGANIZATION_USAGE.REMAINING_BALANCE_DAILY` view (requires ORGADMIN role)
- Consumer must use the ACCOUNTADMIN role or have the `PURCHASE DATA EXCHANGE LISTING` privilege
- MCD funds are deducted **within 24 hours** of purchase
- If MCD doesn't cover the full amount: consumer receives a Snowflake invoice; remaining balance paid via ACH or credit card

*Provider FAQs:*

| Question | Answer |
|----------|--------|
| When will I get paid? | 30 days after consumer pays in full. If fully covered by MCD: 30 days after order. If partially covered: 30 days after remaining balance is paid. |
| Who issues invoices? | **Snowflake Marketplace** — not the provider and not Stripe |
| How do I check if my consumer purchased and if I've been paid? | Query `SNOWFLAKE.DATA_SHARING_USAGE.MARKETPLACE_LISTING_INVOICE_STATUS` (invoices) joined to `MARKETPLACE_DISBURSEMENT_REPORT` (payouts) on `STRIPE_DISPLAY_NUMBER` |
| How are multi-year deals handled? | Snowflake supports 1–60 months. Options: full upfront payment, fixed installments (equal intervals), or variable installments (custom amounts) |
| How do I request an invoice adjustment or cancellation? | Submit a [Marketplace Provider Case](https://snowflakecommunity.force.com/s/) with: Invoice # (SM-XXXX), adjustment request type (e.g., add PO #, apply MCD funds), and justification |
| Provider billing tab is greyed out | See Stripe setup troubleshooting in `monetization/SKILL.md` |
| Dispute or refund | Reference: https://www.snowflake.com/marketplace-dispute-and-refund-policies/ |

**Subscription renewals:**
- **Recurring subscriptions** auto-renew at the end of each term — consumers are billed automatically at the start of the next period
- **Non-recurring subscriptions** expire at term end and cannot be repurchased; the consumer would need to start a new subscription
- Consumers view and manage their subscriptions in **Admin → Billing → Marketplace billing → Consumer billing**
- **Providers cannot directly cancel a consumer's active subscription** — the consumer cancels from their billing dashboard
- To stop renewal for a specific consumer (e.g. churned customer), submit a [Marketplace Provider Case](https://snowforce.my.site.com/s/provider-onboarding-case) with the relevant invoice number

**Refunds:** Consumer should contact the provider first (support email on the listing). If unresolved, file a case: [Report an issue with a listing](https://snowflakecommunity.force.com/s/consumer-reporting)

**References:**
- [Pay for Snowflake Marketplace listings](https://docs.snowflake.com/en/collaboration/consumer-listings-paying)
- [Marketplace Capacity Drawdown](https://docs.snowflake.com/en/collaboration/marketplace-capacity-drawdown)
- [MCD limitations](https://docs.snowflake.com/en/collaboration/marketplace-capacity-drawdown#mcd-limitations) — full list of restrictions (geographic eligibility, resellers, GovCloud, Google Cloud Marketplace, monthly billing, On Demand accounts)
- [Provider Guide to Transacting with MCD](https://www.snowflake.com/Provider-Guide-to-transacting-with-MCD) — live guide, kept updated

---

## Listing Health & Maintenance

### Keeping Metadata Current
- Update listing title, description, or metadata anytime via **Provider Studio → [Listing] → Edit**
  - Or programmatically:
    ```sql
    ALTER LISTING <listing_name> AS
    $$
    title: "Updated Title"
    description: "Updated description..."
    -- include all other existing fields
    $$;
    ```
- **Important:** Do not materially change core listing content after approval (e.g. removing key data fields, significantly reducing update frequency) without re-submitting for review

### Data Refresh
- Ensure your underlying share or app package is refreshed on the schedule declared in the listing
- If refresh cadence changes, update `data_attributes.refresh_rate` in the listing manifest and notify consumers via the listing description

### Retiring a Listing
- Unpublish the listing to stop new consumers from finding it:
  ```sql
  ALTER LISTING <listing_name> UNPUBLISH;
  ```
- Existing consumers retain access until you drop the listing or revoke share access
- Per Snowflake policy, providers must allow existing consumers continued access per listing retirement requirements before dropping
- To fully remove:

> ⚠️ MANDATORY CHECKPOINT: `DROP LISTING` is irreversible and immediately terminates all existing consumer access to this listing. Present the following to the provider and wait for explicit confirmation before proceeding:
> - Listing to be dropped: `<listing_name>`
> - All existing consumers will lose access immediately
> - This action cannot be undone
> Ask: "Please confirm you want to permanently drop this listing and remove all consumer access. Type YES to proceed."

  ```sql
  ALTER LISTING <listing_name> UNPUBLISH;
  DROP LISTING IF EXISTS <listing_name>;
  ```

### Compliance Badges
Providers with SOC 2, HIPAA, ISO 27001, FedRAMP, GDPR, or PCI DSS certifications can add compliance badges to listings — this increases consumer trust and is especially relevant for health and financial data. For the full step-by-step process, see the **Compliance Badges** section in `listings/SKILL.md`.

---

## Paid Listing Performance

### Trial Conversion
- Monitor trial-to-paid conversion via `LISTING_EVENTS_DAILY` — look for `TRIAL` events followed by `PURCHASE` events from the same consumer account
  ```sql
  SELECT
      consumer_account_name,
      listing_name,
      event_type,
      event_date
  FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_EVENTS_DAILY
  WHERE event_type IN ('TRIAL', 'PURCHASE')
  ORDER BY consumer_account_name, listing_name, event_date;
  ```
- Consider following up with trial users — contact via the support email they provided at signup

### Reconcile invoices with Stripe payouts
See **Q13** in the Analytics section above for the reconciliation query (JOIN of `MARKETPLACE_LISTING_INVOICE_STATUS` and `MARKETPLACE_DISBURSEMENT_REPORT` on `stripe_display_number`).

### Managing Offers
- Create, edit, or expire offers via **Provider Studio → [Listing] → Offers**
- For programmatic offer management (V2 listings), refer to the offer and pricing plan manifest fields in the listing YAML

### Payout Status
- Check payout status and invoice history in **Admin → Billing → Marketplace billing → Provider billing**
- For billing issues or invoice disputes: [Provider Onboarding Case Form](https://snowforce.my.site.com/s/provider-onboarding-case)

---

## Key References

| Resource | Link |
|----------|------|
| Provider Studio | https://app.snowflake.com/#/provider-studio |
| Provider Workflows | https://docs.snowflake.com/en/collaboration/provider-listings-workflows |
| Provider & Consumer Policies | https://docs.snowflake.com/en/collaboration/provider-consumer-policies |
| DATA_SHARING_USAGE schema | https://docs.snowflake.com/en/sql-reference/account-usage/data-sharing-usage |
| Listing compliance badges | https://docs.snowflake.com/en/collaboration/provider-becoming#label-listing-compliance-badges |
| Paid listings overview | https://docs.snowflake.com/en/collaboration/provider-listings-paid |
| Retiring listings | https://docs.snowflake.com/en/collaboration/provider-listings-removing |
| Provider Playbook (PDF) | https://www.snowflake.com/wp-content/uploads/2022/12/Create-a-Profile-and-Listing.pdf |
| Provider Playbook (Extended) | https://www.snowflake.com/wp-content/uploads/2023/08/sm-provider-playbook-extended-ver.pdf |
| GTM Partner Readiness (SPN Learn) | https://training.snowflake.com/lmt/xlr8login.login?site=sf&in_redirecturl=deeplinkLP%3D199178706 |

**GTM Partner Readiness learning track:** A 5-course video series on SPN Learn designed to help Data Cloud Product (DCP) partners achieve go-to-market readiness. Covers GTM planning and the Maturity Curve, strategic alignment with Snowflake verticals, collaborating with the Snowflake field team, partner involvement in deals, and launch preparation. Requires SPN enrollment to access. If a provider asks about partner training, GTM readiness, or how to grow their Marketplace business, point them to this track.
