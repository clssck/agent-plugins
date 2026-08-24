---
name: lineage
description: >-
  Snowflake table and column lineage: impact analysis, root cause, data discovery, trust.
  Triggers: 'what depends on', 'what will break', 'blast radius', 'who uses', 'deprecate', 'before
  I change', 'downstream', 'root cause', 'trace upstream', 'where does this come from', 'feeds
  this table', column lineage ('where does [column] come from', 'what uses [column]'), 'is this
  trustworthy', 'which table should I use', 'recommend dataset', 'certify', 'verify source'. Also
  handles asks naming external systems (Power BI, Tableau, Sigma, Looker, dbt): on accounts with
  Horizon Catalog connectors (Private Preview) or a GET_LINEAGE version supporting OpenLineage
  entities, lineage results include external entities. For value-level data quality (wrong values,
  failing DMFs) use the data-quality skill first, then this skill to trace upstream. Always read
  `reference/snowflake-apis.md` before writing GET_LINEAGE SQL; for external entities see
  `reference/external-row-output.md`.
---

# Lineage & Impact Analysis

## When to Use/Load

Activate this skill for **any** of:

- **Impact analysis (downstream)**: "what depends on X", "what will break if I change X", "blast radius", "who uses X", "downstream of X", "cascade", "deprecate X", "before I modify X", "affected users".
- **Root cause (upstream)**: "root cause", "trace upstream from X", "where does X come from", "where do the numbers in X come from", "feeds X", "sources of X", "follow the data back".
- **Column-level lineage**: "what uses column Y", "where does column Y come from", "trace column Y", "column impact", "column source". (Note: "has column X changed recently?" is a **metadata** question — use `INFORMATION_SCHEMA.COLUMNS` and `ACCOUNT_USAGE.QUERY_HISTORY` directly; it does not require `GET_LINEAGE`.)
- **Data discovery / trust / provenance**: "is X trustworthy", "is X the right table", "which table should I use for Z", "recommend a dataset for Z", "verify source", "provenance", "certify X".

> **External lineage.** Gated by two independent conditions, either of which is enough on its own: **Horizon Catalog connectors** (Private Preview) enabled (Horizon-Catalog-connector-sourced entities — Power BI, Tableau, Sigma, Looker, and other BI-tool connectors), or the account's `GET_LINEAGE` being on a version new enough to support OpenLineage-sourced entities (dbt, Airflow, Databricks, and other non-Horizon-Catalog-connector producers ingested via the OpenLineage API). On accounts meeting either condition, the same `GET_LINEAGE` queries return additional rows representing external entities reachable from the Snowflake-side anchor. This is not limited to a single external hop, or to two — the traversal can chain any number of external-to-external edges of the *same* producer family in either direction (`SNOWFLAKE_OBJECT → EXTERNAL_A → EXTERNAL_B → …` downstream, the mirror image upstream), up to the query's own `DISTANCE` cap (max 5); there's no separate, lower limit on how many of those hops are external. With both gates enabled, both producer families can appear in an account's overall lineage graph — uncommon in practice, since most customers manage a given pipeline through one or the other, not both — and where it happens, they mix via a shared Snowflake object in between rather than a direct edge between them. The skill detects these rows in output and presents them — see `reference/external-row-output.md`. **Direct anchoring on an external entity** (e.g. *"what feeds this Power BI dashboard?"* as a cold question) depends on which producer family. Anchoring on a **Horizon Catalog connector** node is not supported — confirmed live against the Private Preview account: it fails with "Anchoring GET_LINEAGE on an external object is not enabled for this account." Anchoring on an **OpenLineage-sourced** node *is* supported (gated independently of Horizon Catalog connectors, by the account's `GET_LINEAGE` external read-path), but only as a **follow-up** to an existing result — pass `OBJECT_DOMAIN => 'EXTERNAL'` plus the entity's `NAMESPACE`, `OBJECT_TYPE`, and `EXTERNAL_ID` (read off a prior row's `*_NAMESPACE`/`*_DATASET_TYPE`/`*_EXTERNAL_ID`). Neither family has a cold/enumeration path — you still need those identifiers from somewhere before you can anchor. See `reference/external-row-output.md` for the exact call shape. When the user doesn't already have those identifiers, tell them to anchor on a Snowflake table or view they know is connected instead; the external entity — and anything further out — will surface in the result.

**Trigger indicators:** Any question about dependencies between Snowflake objects, where data comes from or flows to, or whether an object is the right one to use.

### CLI shortcut: `cortex lineage`

Cortex Code also exposes a one-shot CLI form that calls the same `SNOWFLAKE.CORE.GET_LINEAGE` under the hood as this skill's templates:

```bash
cortex lineage "<DB>.<SCHEMA>.<OBJECT>" --direction downstream --distance 5 --tree
```

When to prefer the CLI vs. the SQL templates in this skill:

| Use the CLI (`cortex lineage`) | Use the SQL templates here |
|---|---|
| One-shot tree view of upstream or downstream of a single object | Need **risk tiers**, **affected users**, **usage stats**, **trust scoring** |
| Simple "what depends on X" or "where does X come from" | Need **multi-source joins** (lineage + ACCESS_HISTORY + tags + contacts) |
| Quick interactive exploration | Reproducible analytics that need to be filtered, persisted, or reported |

The CLI does not currently expose a column-level mode — for column lineage use this skill's `column-lineage-get-lineage.sql` template.

**Cross-skill:** If the user reports **value-level data quality issues** (e.g. "weird data", "missing emails", "wrong numbers", "failing DMFs"), load and run the **data-quality** skill first; then use **this** skill to trace upstream to the root cause. Do not invoke `data-quality` for "which table should I use" or "where do the numbers come from" — those are **lineage** questions.

**Before writing GET_LINEAGE SQL:** Read [`reference/snowflake-apis.md`](reference/snowflake-apis.md) — it has the canonical namespace, argument order, output column names, and the `LATERAL FLATTEN` pattern for `ACCESS_HISTORY`.

## Core principles

- **ALWAYS use `GET_LINEAGE` first** for any object dependency question — downstream or upstream. Do NOT start with `ACCOUNT_USAGE.OBJECT_DEPENDENCIES`, `ACCESS_HISTORY`, `GRANTS_TO_ROLES`, or `SHOW GRANTS`. Those are auxiliary signals (usage / privileges), not lineage sources.
- **`ACCESS_HISTORY` is for usage/user attribution only**, and only **after** `GET_LINEAGE` has already returned the objects in scope.
- **Early-stop on empty `ACCESS_HISTORY`**: if `ACCESS_HISTORY` returns 0 rows for the lineage targets within the lookback window, conclude **"no user/usage data available"** and stop. Do NOT cascade through `OBJECT_DEPENDENCIES`, `GRANTS_TO_ROLES`, `GRANTS_TO_USERS`, `SHOW GRANTS` looking for a user list — those views do not capture "who would be affected" the way `ACCESS_HISTORY` does.
- **Use `OBJECT_DEPENDENCIES` only as a fallback** when `GET_LINEAGE` errors out (privilege) or returns 0 rows for an object that should clearly have lineage (e.g. a view that references other tables). Zero rows from `GET_LINEAGE` on a leaf object is a valid answer; do not chase it.

## Purpose
Navigate the web of data dependencies to ensure reliability, transparency, and rapid recovery across the data ecosystem.

## How It Works

1. **User provides DATABASE.SCHEMA.TABLE** (e.g., "ANALYTICS_DB.REPORTING.REVENUE_SUMMARY")
2. **Agent identifies workflow** based on trigger phrases and other context
3. **Agent reads workflow file** from `workflows/` directory
4. **Agent executes template** with placeholders replaced
5. **Agent presents clean results** formatted per workflow guidelines

**Execution Approach:** Lineage queries are read-only analysis operations. Execute immediately without confirmation since they don't modify data or objects. If executing a recursive SQL query, notify the user that the analysis may take a while due to the complexity of the query.

---

## The 4 Workflows

> **External lineage note.** On accounts meeting either of the two conditions in the callout above, lineage results from any of the four workflows below may include external entities (Power BI dashboards, Tableau workbooks, dbt models, etc.) as additional rows. The skill is aware of these — present them under a separate "External" header per `reference/external-row-output.md`. There is no separate "external-anchor" workflow today: Horizon Catalog connector entities cannot be anchored on directly, while OpenLineage-sourced entities can be, as a follow-up, once their identifiers are known — see stopping point 4.

### 1. Impact Analysis (Downstream)
**File:** `workflows/impact-analysis.md`
**Question:** *"If I change this, what breaks?"*
**Triggers:** "impact analysis", "what depends on this", "what will break", "downstream", "who uses this"
**Templates:** `impact-analysis.sql`, `impact-analysis-multi-level.sql`
**Output:** Downstream objects with risk tiers, usage frequency, affected users

**Snowflake APIs Used:**
- `SNOWFLAKE.CORE.GET_LINEAGE()` - **Primary:** Object and data-movement lineage (VIEW LINEAGE, no account admin)
- `SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES` - **Fallback:** Object dependency graph only (account admin)
- `SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY` - Actual usage patterns
- `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` - User attribution

### 2. Root Cause Analysis (Upstream)
**File:** `workflows/root-cause-analysis.md`
**Question:** *"Why is this number wrong?"* / *"Where does this data come from?"*
**Triggers:** "root cause", "why is this wrong", "trace upstream", "where does this come from", "debug"
**Templates:** `root-cause-analysis.sql`, `change-detection.sql`
**Output:** Upstream lineage, recent changes, divergence points

**Note:** When the user reports **data quality issues** (wrong values, missing emails, failing DMFs), use the **data_quality** skill first to identify what is wrong; then use this workflow to trace upstream to find where the bad data originated.

**Snowflake APIs Used:**
- `SNOWFLAKE.CORE.GET_LINEAGE()` - **Primary:** Upstream lineage (object + data movement)
- `SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES` - **Fallback:** Upstream object dependencies
- `SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY` - Data flow patterns
- `SNOWFLAKE.ACCOUNT_USAGE.TABLES` / `COLUMNS` - Schema change detection
- `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` - Recent modifications

### 3. Data Discovery & Trust (Provenance)
**File:** `workflows/data-discovery.md`
**Question:** *"Where did this come from and is it the right tool for the job?"*
**Triggers:** "is this trustworthy", "provenance", "recommend dataset", "which table should I use", "verify source"
**Templates:** `data-discovery.sql`, `provenance-verification.sql`
**Output:** Full lineage path, usage statistics, trust indicators

**Snowflake APIs Used:**
- `SNOWFLAKE.CORE.GET_LINEAGE()` - **Primary:** Full lineage path (object + data movement)
- `SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES` - **Fallback:** Full dependency chain
- `SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY` - Usage patterns
- `SNOWFLAKE.ACCOUNT_USAGE.TABLES` - Object metadata
- `SNOWFLAKE.ACCOUNT_USAGE.TABLE_STORAGE_METRICS` - Data freshness

### 4. Column-Level Lineage
**File:** `workflows/column-lineage.md`
**Question:** *"What uses this column?" / "Where does this column come from?"*
**Triggers:** "column lineage", "what uses [column]", "where does [column] come from", "trace column", "column impact", "column source"
**Templates:** `column-lineage-get-lineage.sql` (**primary**), `column-lineage-downstream.sql`, `column-lineage-upstream.sql`, `column-lineage-full.sql`
**Output:** Column-level dependencies, source columns, transformation paths

**Snowflake APIs Used:**
- `SNOWFLAKE.CORE.GET_LINEAGE(..., 'COLUMN', ...)` - **Primary:** column lineage with no latency, no account admin (VIEW LINEAGE on PUBLIC)
- `SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY` - **Fallback:** column-level access patterns when GET_LINEAGE is empty
- `SNOWFLAKE.ACCOUNT_USAGE.COLUMNS` - Column metadata and definitions
- `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` - DDL changes affecting columns

---

## Execution Rules

### Step 0: Verify Session Context (once per session)

Run this **once at the start of the first query**. If you have already confirmed warehouse, database, and schema are set earlier in this conversation, skip this step.

Check the current session context:

```sql
SELECT
    CURRENT_USER()      AS current_user,
    CURRENT_ROLE()      AS current_role,
    CURRENT_DATABASE()  AS current_database,
    CURRENT_SCHEMA()    AS current_schema,
    CURRENT_WAREHOUSE() AS current_warehouse;
```

Fix any NULL or mismatched values before continuing:

| Field | Fix if NULL / wrong |
|-------|---------------------|
| `current_warehouse` | `USE WAREHOUSE <name>;` |
| `current_database`  | `USE DATABASE <database>;` |
| `current_schema`    | `USE SCHEMA <database>.<schema>;` |

**⚠️ STOP if warehouse is NULL** — `SNOWFLAKE.ACCOUNT_USAGE` queries require an active warehouse.

### Core Execution Flow:
1. **Extract object identifiers** from user message:
   - Table workflows: `DATABASE.SCHEMA.TABLE`
   - Column workflows: `DATABASE.SCHEMA.TABLE.COLUMN`
2. **Identify workflow** from trigger phrases and the object identifier → read workflow file from `workflows/`
3. **Read SQL template** specified in workflow file
4. **Build dynamic scoring** from `config/schema-patterns.yaml` (for trust/risk placeholders)
5. **Replace placeholders** with actual values
6. **Execute and format** results per workflow guidelines

### Placeholder Replacements:
- `<database>`, `<schema>`, `<table>`, `<column>` → actual object names
- `/* SCHEMA_TRUST_SCORING:column */` → dynamic CASE statement from config
- `/* SCHEMA_TRUST_TIER:column */` → dynamic tier name CASE statement  
- `/* SCHEMA_RISK_SCORING:column */` → dynamic risk CASE statement

**Identifier validation:** Each name part must match `^[A-Za-z_][A-Za-z0-9_$]*$`. Reject any value containing quotes (`"`, `'`, `` ` ``), semicolons, spaces, or other SQL metacharacters — do not substitute it into SQL. Ask the user to confirm the correct object name instead.

### Key Principles:
- **Use templates exactly as written** - only replace placeholders
- **No confirmation prompts** for read-only lineage queries
- **Handle errors gracefully** - use fallback templates, provide clear messages
- **One workflow per request** - don't chain multiple analyses automatically

---

## Template Structure

All templates in `templates/` directory use these placeholders:
- `<database>` → Replace with actual database name
- `<schema>` → Replace with actual schema name
- `<table>` → Replace with actual table name
- `<column>` → Replace with actual column name (for column-level lineage)
- `/* SCHEMA_TRUST_SCORING:column_name */` → Dynamic CASE statement returning score (integer)
- `/* SCHEMA_TRUST_TIER:column_name */` → Dynamic CASE statement returning tier name (string)
- `/* SCHEMA_RISK_SCORING:column_name */` → Dynamic CASE statement returning 'CRITICAL' or NULL

**Example:**
```sql
-- Template:
WHERE REFERENCED_DATABASE = '<database>' 
  AND REFERENCED_SCHEMA = '<schema>' 
  AND REFERENCED_OBJECT_NAME = '<table>'

-- After replacement:
WHERE REFERENCED_DATABASE = 'ANALYTICS_DB' 
  AND REFERENCED_SCHEMA = 'REPORTING' 
  AND REFERENCED_OBJECT_NAME = 'SALES_SUMMARY'
```

---

## Dynamic Trust Scoring

Templates use dynamic placeholders for trust/risk scoring. See `reference/dynamic-trust-scoring.md` for complete documentation on:
- Placeholder syntax (`/* PLACEHOLDER_TYPE:column_name */`)
- Building CASE statements from `config/schema-patterns.yaml`
- Why dynamic scoring enables customer customization

---

## Error Handling & Fallback Strategy

**Lineage source order (static dependencies):**

1. **Primary:** `SNOWFLAKE.CORE.GET_LINEAGE()` — object and data-movement lineage; requires only object-resolve + VIEW LINEAGE (granted to public). Prefer for all table/column lineage.
2. **Fallback 1:** `SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES` — object dependency only; requires account admin. Use **only** when the primary query **fails** (e.g. privilege error) or when you have strong reason to expect lineage but GET_LINEAGE returned empty (e.g. object is known to have dependents).
3. **Fallback 2:** `GET_DDL()` to parse view definitions for references
4. **Fallback 3:** `INFORMATION_SCHEMA.OBJECT_DEPENDENCIES` (current DB only)

**Minimize steps:** Run the primary template once. If it **succeeds** (with or without rows), present the result and **stop**—do not run the fallback. Use fallback only when the primary **errors** or when the object clearly should have lineage (e.g. a view that references other tables) but GET_LINEAGE returned 0 rows. Zero rows from GET_LINEAGE is often a valid answer (e.g. table has no downstream).

**Why GET_LINEAGE first:** OBJECT_DEPENDENCIES captures only *object dependency* (target data depends on source). GET_LINEAGE also captures *data movement* (e.g. COPY INTO, CTAS) and avoids account admin (VIEW LINEAGE is granted to public).

**Fallback templates (use only when primary fails or expected lineage is missing):**
- `impact-analysis-object-deps-fallback.sql`, `impact-analysis-multi-level-object-deps-fallback.sql`, `impact-analysis-users-object-deps-fallback.sql`
- `root-cause-analysis-object-deps-fallback.sql`, `change-detection-object-deps-fallback.sql`
- `provenance-verification-object-deps-fallback.sql`

**Further fallbacks (DDL / INFORMATION_SCHEMA):**
- `impact-analysis-fallback.sql` — DDL/INFORMATION_SCHEMA for downstream deps
- `root-cause-ddl-fallback.sql` — DDL parsing for upstream lineage

**If template fails:**
1. Run primary (GET_LINEAGE) once. On **success** (any row count), present results and stop. On **failure** (error) or **empty when lineage is expected**, try OBJECT_DEPENDENCIES fallback, then GET_DDL/INFORMATION_SCHEMA if needed.
2. Check ACCESS_HISTORY availability: `check-access-history.sql`
3. Check object existence: `check-object-exists.sql`
4. If object doesn't exist: "Object not found. Check the name and try again."
5. If no lineage data: "No lineage data available. Object may be new or unused."

**Common Issues:**
- "No ACCESS_HISTORY data" → Data is older than 365 days or not accessed
- "GET_LINEAGE returns empty" → Use fallback only if the object should have lineage (e.g. view with references); otherwise report "No lineage found."
- "Insufficient privileges" → GET_LINEAGE needs VIEW LINEAGE (public); OBJECT_DEPENDENCIES needs account admin

---

## Output Format Rules

**Always state the depth used and offer to go deeper.** At the end of every lineage result, include a line in this form:

```
Showing X level(s) of lineage. Want me to dig deeper? (max 5)
```

Where X is the distance/level count actually used. If the user already specified the maximum (5), omit the offer.

---

## Expected User Experience

### Example 1: Impact Analysis
**User:** "What will break if I change RAW_DB.SALES.ORDERS?"

**Agent (immediately):**
```
Impact Analysis: RAW_DB.SALES.ORDERS

═══════════════════════════════════════════════════════════════
CRITICAL RISK (2 objects)
═══════════════════════════════════════════════════════════════
1. ANALYTICS_DB.REPORTING.DAILY_REVENUE (Dynamic Table)
   Risk: CRITICAL | Refresh: Every 15 min | Users: 12 in last 7 days
   → Feeds 3 downstream objects including executive dashboard

2. FINANCE_DB.REPORTS.AR_AGING (View)
   Risk: CRITICAL | Queries: 89/day | Users: 5 in last 7 days
   → Used for month-end close process

═══════════════════════════════════════════════════════════════
MODERATE RISK (1 object)
═══════════════════════════════════════════════════════════════
3. STAGING_DB.TRANSFORM.ORDERS_ENRICHED (Table)
   Risk: MODERATE | Last updated: 2024-01-15 | Users: 2 in last 7 days

Summary: 3 downstream dependencies | 2 CRITICAL | 1 MODERATE
Affected Users: 15 unique users in last 7 days
```

### Example 2: Root Cause Analysis
**User:** "Why is ANALYTICS_DB.REPORTING.REVENUE wrong?"

**Agent (immediately):**
```
Root Cause Analysis: ANALYTICS_DB.REPORTING.REVENUE

═══════════════════════════════════════════════════════════════
UPSTREAM LINEAGE (3 levels)
═══════════════════════════════════════════════════════════════
Level 1: STAGING_DB.CLEAN.ORDERS_FACT
Level 2: RAW_DB.INGEST.ORDERS, RAW_DB.INGEST.PRODUCTS
Level 3: External Stage (S3://data-lake/orders/)

═══════════════════════════════════════════════════════════════
RECENT CHANGES DETECTED
═══════════════════════════════════════════════════════════════
⚠️  RAW_DB.INGEST.ORDERS - Schema changed 2 hours ago
    Change: Column DISCOUNT_PCT type changed NUMBER(5,2) → NUMBER(10,4)
    Changed by: ETL_SERVICE_USER

⚠️  STAGING_DB.CLEAN.ORDERS_FACT - Data modified 1 hour ago
    Rows affected: 15,234 rows updated
    Query: MERGE statement by TRANSFORM_TASK

Most Likely Cause: Schema change in RAW_DB.INGEST.ORDERS
Recommendation: Verify DISCOUNT_PCT handling in downstream transforms
```

### Example 3: Data Discovery
**User:** "Which table should I use for customer revenue analysis?"

**Agent (immediately):**
```
Data Discovery: Customer Revenue Analysis

RECOMMENDED:
1. ANALYTICS_DB.CURATED.CUSTOMER_REVENUE_SUMMARY ⭐ Best Match
   Trust Score: 95% | Updated hourly | Users: 45/week
   Why: Pre-aggregated customer revenue with standard dimensions
   Provenance: RAW.ORDERS → STAGING.ORDERS_FACT → This table

Not Recommended:
- RAW_DB.ORDERS (Trust: 60%) - Raw data, requires transformation
- SANDBOX_DB.*.* - Development/test data
```

### Example 4: Column-Level Lineage
**User:** "What uses the AMOUNT column in RAW_DB.SALES.ORDERS?"

**Agent (immediately):**
```
Column Impact Analysis: RAW_DB.SALES.ORDERS.AMOUNT

═══════════════════════════════════════════════════════════════
DOWNSTREAM COLUMNS (8 columns use this data)
═══════════════════════════════════════════════════════════════

CRITICAL IMPACT:
1. ANALYTICS_DB.REPORTING.REVENUE_SUMMARY.TOTAL_REVENUE
   Impact: CRITICAL | Queries: 89/day | Confidence: HIGH
   Transformation: SUM(AMOUNT) aggregation
   
2. FINANCE_DB.REPORTS.AR_AGING.OUTSTANDING_AMOUNT
   Impact: CRITICAL | Queries: 45/day | Confidence: HIGH
   Transformation: Direct reference with filters

HIGH IMPACT:
3. STAGING_DB.TRANSFORM.ORDERS_ENRICHED.NET_AMOUNT
   Impact: HIGH | Queries: 23/day | Confidence: HIGH
   Transformation: AMOUNT * (1 - DISCOUNT_PCT/100)

MODERATE IMPACT:
4. ANALYTICS_DB.MARTS.CUSTOMER_360.LIFETIME_VALUE
   Impact: MEDIUM | Queries: 12/day | Confidence: MEDIUM

Summary: 8 downstream columns | 2 CRITICAL | 1 HIGH | 5 MEDIUM
Recommendation: Coordinate with Finance team before changing
```

### Example 5: Column Source Tracing
**User:** "Where does ANALYTICS_DB.REPORTS.REVENUE.TOTAL_SALES come from?"

**Agent (immediately):**
```
Column Source Analysis: ANALYTICS_DB.REPORTS.REVENUE.TOTAL_SALES

═══════════════════════════════════════════════════════════════
UPSTREAM SOURCES (traced 3 levels)
═══════════════════════════════════════════════════════════════

Level 1 (Direct Source):
  STAGING_DB.TRANSFORM.ORDERS_AGG.REVENUE_SUM
  Confidence: HIGH | Last seen: 2 hours ago
  Transformation: Renamed column

Level 2:
  RAW_DB.INGEST.ORDERS.AMOUNT
  Confidence: HIGH | Source tier: RAW
  Transformation: SUM() aggregation

Level 3 (Origin):
  @RAW_DB.STAGES.S3_ORDERS/orders.csv
  Confidence: MEDIUM | Source tier: EXTERNAL

Complete Path:
S3_ORDERS → ORDERS.AMOUNT → ORDERS_AGG.REVENUE_SUM → REVENUE.TOTAL_SALES
```

---

## Summary Table

| Workflow | Direction | Primary Goal | Key Stakeholder |
|:---------|:----------|:-------------|:----------------|
| **Impact Analysis** | Downstream | Risk Mitigation | Data Engineers / Ops |
| **Root Cause** | Upstream | Troubleshooting | Analysts / Analytics Engineers |
| **Trust & Discovery** | Full Path | Data Literacy | Business Users / Platform Owners |
| **Column Lineage** | Both | Field-Level Tracing | Data Engineers / Analysts |

---

## Workflow Selection Logic

| User Says | Workflow | Template |
|-----------|----------|----------|
| "What will break if I change [table]?" | Impact Analysis | `impact-analysis.sql` |
| "What depends on [table]?" | Impact Analysis | `impact-analysis.sql` |
| "Why is this number wrong?" | Root Cause Analysis | `root-cause-analysis.sql` |
| "Where does [table] come from?" | Root Cause Analysis | `root-cause-analysis.sql` |
| "Is [table] trustworthy?" | Data Discovery | `data-discovery.sql` |
| "Which table should I use for [topic]?" | Data Discovery | `data-discovery.sql` |
| "What uses the [column] column?" | Column Lineage | `column-lineage-downstream.sql` |
| "Where does [column] come from?" | Column Lineage | `column-lineage-upstream.sql` |
| "Full lineage for [column]" | Column Lineage | `column-lineage-full.sql` |

---

## Snowflake APIs Reference

See `reference/snowflake-apis.md` for complete documentation on:
- `SNOWFLAKE.CORE.GET_LINEAGE()` (primary) vs `ACCOUNT_USAGE.OBJECT_DEPENDENCIES` (fallback)
- Object dependency vs data-movement lineage and privilege requirements
- ACCOUNT_USAGE views and their latencies
- Performance optimization tips

For external rows that surface in results on Horizon Catalog connectors (Private Preview) accounts, see also:
- `reference/external-row-output.md` — how to recognize and present external entities (Power BI dashboards, Tableau workbooks, dbt models, etc.) in `GET_LINEAGE` output

---

## Success Criteria

- User gets answer in **one response**
- Risk tiers clearly communicated (Impact Analysis)
- Recent changes highlighted (Root Cause)
- Trust indicators provided (Discovery)
- No SQL errors shown
- No unnecessary questions
- Clean, actionable results

---

## Stopping Points

Lineage queries are **read-only operations** that don't modify data or schema. Execute immediately without waiting for confirmation.

### ⚠️ MANDATORY STOPPING POINTS

**STOP and ask user if:**
1. **Ambiguous object reference** - Missing or unclear database/schema/table/column name
   - Example: User says "check lineage" without specifying which table
   - Action: Ask "Which table would you like to analyze?"

2. **User explicitly requests review** - "Show me the query first" or "Let me review before running"
   - Action: Present the query and wait for confirmation

3. **Query returns no results** - No lineage data found
   - Action: Explain possible reasons (new object, no access, insufficient privileges) and ask if they want to try a different approach

4. **User asks to anchor lineage on an external entity** (e.g. "what feeds this Power BI dashboard?")
   - Action: If it's a Horizon Catalog connector entity (or its producer family is unknown), tell the user direct anchoring isn't supported and ask them to anchor on a Snowflake table or view they know is connected instead.
   - Action: If it's an OpenLineage-sourced entity **and** you (or a prior `GET_LINEAGE` result) already have its `NAMESPACE` + `OBJECT_TYPE` + `EXTERNAL_ID`, anchor directly with `OBJECT_DOMAIN => 'EXTERNAL'` — this is supported, but only on accounts where `GET_LINEAGE` has this anchor mode (a Behavior Change rolling out account-by-account; same threshold as the rest of this skill's v7 fields: `VERSION_GET_LINEAGE` **v7+**, not v7-only). On an account still on the old behavior this errors (`Unknown domain: EXTERNAL.`) instead of falling back gracefully, so don't attempt it unless you already have those identifiers from this account's own prior `GET_LINEAGE` output — if you do, the account is already past the cutover.
   - Action: If it's an OpenLineage-sourced entity but you don't yet have those identifiers, anchor on a connected Snowflake object first to surface them (`*_NAMESPACE`/`*_DATASET_TYPE`/`*_EXTERNAL_ID` in that result), then re-anchor directly as a follow-up.
   - In every case, the external entity will also surface in a native-anchored lineage result if connected. (See `reference/external-row-output.md`.)

### ✅ NO STOPPING REQUIRED

**Execute immediately without confirmation:**
- Any SELECT query on `SNOWFLAKE.ACCOUNT_USAGE` views
- Any SELECT query on `INFORMATION_SCHEMA` views
- Parsing DDL with `GET_DDL()` function
- Reading configuration files from `config/`

**Rationale:** These are read-only operations that don't modify data, schema, or access controls.

---

## Production Configuration

**Schema Pattern Configuration (Extensible):**

Trust and risk scoring patterns are defined in `config/schema-patterns.yaml`. This file is read dynamically at runtime, allowing easy customization without modifying SQL templates.

**File:** `config/schema-patterns.yaml`

```yaml
trust_tiers:
  PRODUCTION:
    score: 100
    patterns:
      - "%ANALYTICS%"
      - "%CURATED%"
      # Add your production schema patterns here
      
  STAGING:
    score: 60
    patterns:
      - "%STAG%"
      # Add your staging schema patterns here
      
  RAW:
    score: 40
    patterns:
      - "%RAW%"
      # Add your raw data schema patterns here
      
  UNTRUSTED:
    score: 20
    patterns:
      - "%SANDBOX%"
      - "%TEST%"
      # Add your dev/test schema patterns here

default:
  score: 50
  tier: "UNKNOWN"

risk_critical_patterns:
  - "%FINANCE%"
  - "%REVENUE%"
  # Add schemas that are critical to flag
```

**Customization:** Edit `config/schema-patterns.yaml` using SQL LIKE syntax (% = wildcard, case-insensitive). Example: `%ANALYTICS%` matches ANALYTICS, PROD_ANALYTICS, ANALYTICS_V2.

**Recursive Depth — defaults by workflow:**

| Workflow | Default distance | Templates |
|---|---|---|
| Impact Analysis (downstream) | 3 | `impact-analysis.sql`, `impact-analysis-users.sql` |
| Root Cause Analysis (upstream) | 3 | `root-cause-analysis.sql`, `change-detection.sql`, `root-cause-analysis-object-deps-fallback.sql` |
| Trust & Provenance | 3 | `provenance-verification.sql`, `provenance-verification-object-deps-fallback.sql` |
| Column Lineage (GET_LINEAGE) | 1 | `column-lineage-get-lineage.sql`, `column-lineage-full.sql` |
| Column Lineage (ACCESS_HISTORY fallback) | N/A — lookback days, not distance | `column-lineage-downstream.sql`, `column-lineage-upstream.sql` |

**Honoring user-specified depth:** Apply in this order:
1. **Explicit number** ("1 level", "2 hops", "3 levels deep", "just direct dependencies") → substitute that number as the distance, up to the maximum of 5.
2. **Relative "deeper"** ("go deeper", "show more", "dig deeper") with no explicit number → increment the current/default depth by 1, capped at 5.
3. **Maximum** ("show everything", "full lineage", "all levels", "maximum depth") → use 5.

In practice:
- In `GET_LINEAGE` templates: replace the `distance` argument with the resolved number.
- In recursive CTE fallback templates: replace `WHERE ul.level < N` with the resolved number.

**Retention:** ACCESS_HISTORY/QUERY_HISTORY: 365 days; GET_LINEAGE: current state; OBJECT_DEPENDENCIES: indefinite (latency on new objects).

---

## Known Limitations

| Limitation | Impact | Workaround |
|------------|--------|------------|
| GET_LINEAGE max 5 levels | Deep chains truncated at 5 | Use OBJECT_DEPENDENCIES fallback for deeper traversal |
| ACCOUNT_USAGE latency (45min-3hr) | New objects missing from OBJECT_DEPENDENCIES | Use GET_LINEAGE first (current state); then GET_DDL() fallback |
| Column lineage depends on ACCESS_HISTORY | Not all queries expose column details | Confidence scores indicate reliability |
| Single account scope | Cross-account sharing not covered | Query each account separately |
| View DDL parsing | May miss dynamic SQL references | Review complex views manually |
| OBJECT_DEPENDENCIES = object dependency only | Data movement (e.g. CTAS, COPY) not in OBJECT_DEPENDENCIES | Use GET_LINEAGE as primary |
| Column lineage 90-day lookback | Older transformations not captured | Extend time range in templates |
| External-anchor queries: unsupported for Horizon Catalog connectors, follow-up-only for OpenLineage | Customer can't ask "what feeds this Power BI dashboard?" cold via SQL, for either producer family | Anchor on a connected Snowflake object first; for OpenLineage entities, reuse the NAMESPACE/OBJECT_TYPE/EXTERNAL_ID from that result to re-anchor directly next time |
| No `account_usage` view for external entities | Customer can't enumerate Horizon Catalog connector entities directly | Browse Catalog Explorer in Snowsight, or walk outward from a known Snowflake-side object |
| No `ACCESS_HISTORY` for external entities | "Who uses this Power BI dashboard?" cannot be answered from Snowflake | Direct user to the external system |
