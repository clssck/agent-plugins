---
name: policy-recommendations
parent_skill: data-governance
description: "Identify policy coverage gaps within a data object (whole account, or a database / schema / table / column) across masking, projection, aggregation, and join policies — reading Snowflake's pre-computed Policy Recommendations feature (SNOWFLAKE.POLICY_RECOMMENDATIONS) when it is available, otherwise scanning ACCOUNT_USAGE live. Prioritize high-impact gaps by query volume and sensitive column surface area, explain why each gap matters and what it takes to close it, and help the user apply a chosen remediation with approval (advisory — never auto-applies). Use when: user asks about policy gaps, policy coverage, which tables need protection, where am I missing policies, improve privacy coverage, policy recommendations, suggest policies, coverage gaps, aggregation policy gaps, projection policy gaps, join policy gaps, what should I protect next, privacy posture improvement, tag-based policy coverage at scale."
---

# Policy Recommendations

Surface where a Snowflake account's sensitive data lacks policy protection (masking, projection, aggregation, join), prioritize the gaps by query volume and sensitivity, and help the user **understand and act on** them. When Snowflake's Policy Recommendations feature is enabled, this reads pre-computed, ready-to-run recommendations directly from the shared `SNOWFLAKE` database; otherwise it scans `ACCOUNT_USAGE` live. Either way the goal is the same: explain each gap — what it is, why it matters, and what it takes to close it — then apply the fix with the user's approval. It is advisory; nothing changes without confirmation.

## When to Use

This workflow is entered **only** via the UI slash-command `/data-governance Identify policy gaps and recommend remediation actions for my account [within <PATH>]` (optional object scope: `DB` / `DB.SCHEMA` / `DB.SCHEMA.TABLE` / `DB.SCHEMA.TABLE.COLUMN`) — see Step 0. The parent `SKILL.md` deliberately routes general phrasing ("policy gaps", "what should I protect", "which tables need protection") to horizon-catalog, **not** here — do not treat those as triggers for this workflow.

Once loaded via that slash-command, it runs the full gap-analysis flow: find where policy coverage is missing (masking, aggregation, projection, join), surface the highest-risk unprotected columns by query volume, and apply fixes at scale (including tag-based quick wins) on approval.

## How This Differs From Governance Maturity Score

The Governance Maturity Score measures *how broadly* policies are deployed (a 0–5 metric). This skill answers a different question: *which specific objects need a policy next, why, and what is the exact SQL to fix it?* Use this skill when the user wants concrete, understandable, actionable remediation rather than a coverage score.

## Two Ways This Runs

- **Fast path (pre-computed).** If the Policy Recommendations feature is enabled, the shared `SNOWFLAKE` database already holds recommendations refreshed on a schedule. The skill serves them with one `CALL` and shows how fresh they are. This is advisory data — it carries a plain-language rationale and ready-to-run SQL, but Snowflake never applies it for you.
- **Live scan (fallback).** If the feature is not enabled (or your role can't read it), the skill scans `ACCOUNT_USAGE` directly — the same analysis, computed on demand.

The skill checks for the fast path first (Step 2) and falls back to the live scan automatically.

## Workflow

**Output formatting.** Present every report, summary, and recommendation block as GitHub-flavored **Markdown** — `###` headings, **bold** labels, and Markdown tables (`| … |`). Never use box-drawing or ASCII-art borders (`╔ ║ ╚ │ ─ ┼`): outside a code block their lines collapse onto a single line when rendered. Put runnable SQL in triple-backtick `sql` code blocks. (The examples below are shown as Markdown for exactly this reason.)

### Step 0: UI Slash-Command Fast-Path

**If the user's first message starts with** `/data-governance Identify policy gaps and recommend remediation actions for my account` **, follow this fast-path and skip the Step 1 intake.** Go straight to finding the gaps and presenting remediation options — do not explain the plan or ask the universal intake questions.

1. **Parse the optional object scope.** The command may end with `within <PATH>`, where `<PATH>` is a dot-qualified data object. The `within …` clause is optional — the user is filtering by **data object, not policy kind**, so always look for gaps across *all* kinds (masking, tag-based masking, aggregation, projection, join) within the scope.

   | Message ends with… | `scope` |
   |---|---|
   | (no `within` clause) | whole account |
   | `within DB` | one database |
   | `within DB.SCHEMA` | one schema |
   | `within DB.SCHEMA.TABLE` | one table |
   | `within DB.SCHEMA.TABLE.COLUMN` | one column |

   Record the supplied path parts as `scope` (database / schema / table / column, whichever are present).

2. **Confirm access quietly** — run the role check from Step 1. If neither `ACCOUNTADMIN` nor `GOVERNANCE_VIEWER` is in session, show the Step 1 access message and stop. Otherwise proceed **without** the plan explanation or its stopping point.

3. **Serve — pre-computed first, scoped to `scope`.** Probe the feature (Step 2). If it is available with a completed run:
   - `CALL SNOWFLAKE.POLICY_RECOMMENDATIONS.GET_POLICY_RECOMMENDATION_SUMMARY();` — read `LAST_REFRESHED_AT` for freshness.
   - The serving procedure only filters by `database_name`, so pass it when the scope names a database, then narrow deeper levels from the returned rows:
     ```sql
     -- whole account:
     CALL SNOWFLAKE.POLICY_RECOMMENDATIONS.GET_POLICY_RECOMMENDATIONS(OBJECT_CONSTRUCT('limit', 200));
     -- within a database (then keep only rows matching the deeper path parts):
     CALL SNOWFLAKE.POLICY_RECOMMENDATIONS.GET_POLICY_RECOMMENDATIONS(
         OBJECT_CONSTRUCT('database_name', '<DB>', 'limit', 200)
     );
     ```
     Keep only rows whose `DATABASE_NAME` / `SCHEMA_NAME` / `TABLE_NAME` / `COLUMN_NAME` match every level the user supplied in `scope`. When the scope is below the database level, raise `limit` (e.g. 1000) so a deep target's gaps aren't cut off before client-side narrowing; if the page still comes back full, tell the user the results may be capped and offer a live scan (Step 3) for completeness.
   If the feature is unavailable or unauthorized, fall back to the **live scan** (Steps 3–4) using the scope's database as the assessed database, and add `SCHEMA_NAME` / `TABLE_NAME` / `COLUMN_NAME` predicates to the discovery queries for deeper paths.

4. **Present the in-scope gaps, each with its remediation options.** Order by `IMPACT_SCORE`. For every gap show what it is (which policy kind, where, why it matters) and — because **one gap can have several valid fixes** — enumerate the possible remediation actions (e.g. reuse an existing policy, create a new one, cover it via a governance tag, or use a different policy kind), then let the user choose. This is the **Step 6 (Understand Each Gap, Then Apply)** flow — run it per in-scope gap, then **Step 7 (Execute)** on approval.

5. **Apply on approval only** — the **Pre-Write Approval Rule** in Step 7 still holds: show the exact SQL and wait for confirmation before any `CREATE` / `ALTER` / `APPLY`, even on the fast-path.

If serving pre-computed data, tell the user how fresh it is and offer a live re-scan (Step 3) for up-to-the-minute results.

**If the message does not start with that slash-command, ignore this step and start at Step 1.**

### Step 1: Validate Role & Capability

Before running any queries, verify the current role can access ACCOUNT_USAGE views:

```sql
SELECT
    IS_ROLE_IN_SESSION('ACCOUNTADMIN')       AS HAS_ACCOUNTADMIN,
    IS_ROLE_IN_SESSION('GOVERNANCE_VIEWER')  AS HAS_GOVERNANCE_VIEWER;
```

If **either** returns `True`, proceed.

If **both** return `False`, stop and inform the user:

```
Your current role does not have access to SNOWFLAKE.ACCOUNT_USAGE views,
which are required for the policy recommendations analysis.

Access is granted through:
- The GOVERNANCE_VIEWER application role on the SNOWFLAKE database
- The ACCOUNTADMIN role
- Secondary roles that include either of the above

Please switch to a role with ACCOUNT_USAGE access and try again.
```

Do NOT proceed until access is validated.

> **Fast-path access note.** The pre-computed feature (Step 2) is served through the `policy_recommendations_viewer` application role, which is auto-granted to `ACCOUNTADMIN` via `PUBLIC`. A role with only `GOVERNANCE_VIEWER` may not hold it — in that case the fast-path `CALL` returns an authorization error, which is treated exactly like "feature unavailable" and falls through to the live scan.

Once ACCOUNT_USAGE access is confirmed, run the grant discovery query from [../templates/policy-recommendations/check-apply-grants.sql](../templates/policy-recommendations/check-apply-grants.sql) to determine the user's apply-policy capability. Derive `CAPABILITY_LEVEL` from the results as described in that template's interpreting section:

- **FULL_APPLY** — role is ACCOUNTADMIN/SYSADMIN, or holds `APPLY <KIND> POLICY ON ACCOUNT` for at least one policy kind
- **POLICY_OWNER** — role owns ≥1 policy (OWNERSHIP on a policy object) but has no global apply grant; record the owned policy FQNs as `OWNED_POLICY_NAMES`
- **ANALYST** — ACCOUNT_USAGE access only; no apply grants and no policy ownership

Then explain what will happen, including a capability note tailored to `CAPABILITY_LEVEL`:

```
I'll find where your policy coverage has gaps, rank them by how much risk they
carry, and walk you through the highest-impact ones — what each gap is, why it
matters, and what it takes to close it. Here's the plan:

1. **Check for pre-computed recommendations** — Snowflake may already have these ready
2. **Inventory existing policies** — masking, row access, projection, aggregation, join
3. **Find hot tables and columns** — those with the most query activity in the last 30 days
4. **Identify gaps** — sensitive columns and tables similar to protected ones that lack policies
5. **Rank by impact, then explain and help you apply** — for each top gap: why it matters,
   what privilege you need, and ready-to-run SQL (favouring tag-based policies that protect
   many columns at once). Nothing is applied without your approval.

[CAPABILITY NOTE — include the applicable line below, omit the others:]
✅ You have account-level policy apply privileges. I can generate ready-to-run SQL for every recommendation.
You own the following policies: [OWNED_POLICY_NAMES]. I'll scope executable suggestions to those policies.
   To apply them you also need APPLY [KIND] POLICY on the target table, or share the SQL with a role
   that has account-level apply.
ℹ️  Your current role cannot apply policies directly. I'll show recommendations in informational mode —
   share them with your policy admin.

Let me first check whether Snowflake already has recommendations ready for you.
```

**✋ Stopping point:** Wait for the user to confirm before running queries.

### Step 2: Check for Pre-Computed Recommendations (Fast Path)

Snowflake's Policy Recommendations feature may already have computed these gaps on a schedule and stored them in the shared `SNOWFLAKE` database. When present, reading them is far cheaper than a live scan. Run the probe from [../templates/policy-recommendations/check-precomputed-recommendations.sql](../templates/policy-recommendations/check-precomputed-recommendations.sql):

1. **Probe availability** (STEP A — `SHOW PROCEDURES IN SCHEMA SNOWFLAKE.POLICY_RECOMMENDATIONS;`):
   - **Errors / not authorized** → the feature isn't enabled for this account (or your role lacks the viewer app role). Don't alarm the user; continue to Step 3 for a live scan.
   - **Returns the two procedures** → continue.
2. **Summary + age** (STEP B — `CALL ...GET_POLICY_RECOMMENDATION_SUMMARY();`):
   - **Zero rows** → feature enabled but no completed run yet. Tell the user, then continue to Step 3 (live scan).
   - **Rows returned** → note the freshness: read `LAST_REFRESHED_AT` (all rows of a run share one value — use the oldest if they ever differ) and compute its age.
3. **Show the age and let the user choose:**

```
Snowflake has pre-computed policy recommendations for your account.
Last refreshed: <LAST_REFRESHED_AT> (about <age> ago) — <N> recommendations across
MASKING_GAP, TAG_QUICKWIN, AGGREGATION_GAP, PROJECTION_GAP, JOIN_GAP.

Would you like to:
1. Use these pre-computed recommendations (fast — recommended if recent)
2. Run a fresh live scan instead (slower; reflects the last few hours of changes)
```

**✋ Stopping point:** Wait for the user's choice.

- **Use pre-computed** → run STEP C (`CALL ...GET_POLICY_RECOMMENDATIONS(...)`, optionally filtered by `category` / `min_impact` / `database_name`) to pull the ranked detail, then go straight to **Step 5**, skipping the live-scan Steps 3–4. Each detail row already carries `IMPACT_SCORE`, `RATIONALE`, `REQUIRES_PRIVILEGE`, `EXISTING_POLICY_NAME`, and `REMEDIATION_SQL`.
- **Fresh live scan** → continue to Step 3.

Note: the generator tasks and run history live in the internal `SNOWFLAKE.POLICY_RECOMMENDATIONS_STATE` schema, which customers can't inspect directly — `LAST_REFRESHED_AT` is the freshness signal.

### Step 3: Identify and Confirm Databases for Assessment (Live Scan)

*(Live scan only — skip if the user chose pre-computed results in Step 2.)*

Run the popular databases query from [../templates/governance-maturity-score/check-popular-databases.sql](../templates/governance-maturity-score/check-popular-databases.sql) to identify the most-used databases by query volume.

<!-- Cross-skill dependency: this template is owned by the governance-maturity-score skill. If it is moved or renamed there, update this path too. -->

Present the list as a Markdown table (not ASCII art) and ask:

Here are the most active databases in your account (by query volume, last 30 days):

| # | Database | Queries | Users |
|--:|---|--:|--:|
| 1 | PROD_DB | 12,450 | 34 |
| … | | | |

Then ask: "Should I scan **all** of these for policy gaps, or are there any to exclude? (e.g. skip STAGING_DB — sandbox data) Reply 'all' to scan everything."

**✋ Stopping point:** Wait for the user to confirm the database list.

Record confirmed databases as `assessed_databases`. Excluded databases are skipped from all subsequent queries and the final report.

### Step 4: Run All Discovery Queries (Live Scan)

*(Live scan only — skip if the user chose pre-computed results in Step 2.)*

**Execute all queries below without stopping.** These are read-only queries. Do NOT ask for confirmation between steps. Collect all results silently and proceed directly to Step 5.

All queries must be scoped to the `assessed_databases` list.

**Queries to run (in order):**

1. **Existing policies inventory** (from [../templates/policy-recommendations/check-existing-policies.sql](../templates/policy-recommendations/check-existing-policies.sql)):
   - Query `ACCOUNT_USAGE.POLICY_REFERENCES` for all policy kinds
   - Record per kind: policy count, attachment count, databases covered, column names protected
   - Infer protection intent from semantic/privacy category of attached columns (via `DATA_CLASSIFICATION_LATEST`)

2. **Hot tables and columns** (from [../templates/policy-recommendations/find-hot-tables.sql](../templates/policy-recommendations/find-hot-tables.sql)):
   - `ACCOUNT_USAGE.ACCESS_HISTORY`: column-level direct access counts (last 30 days)
   - `ACCOUNT_USAGE.QUERY_HISTORY`: table-level query counts (last 30 days)
   - Cross-reference with existing policy attachments to flag hot unprotected columns

3. **Policy gap candidates** (from [../templates/policy-recommendations/find-gap-candidates.sql](../templates/policy-recommendations/find-gap-candidates.sql)):
   - Sensitive columns from `DATA_CLASSIFICATION_LATEST` with no entry in `POLICY_REFERENCES`
   - Column-name heuristics (ILIKE patterns: `%SSN%`, `%EMAIL%`, `%PHONE%`, `%CREDIT_CARD%`, `%PASSPORT%`, `%DOB%`, `%DATE_OF_BIRTH%`, `%SALARY%`, `%TAX_ID%`) for assessed databases, even if not yet classified
   - Tables sharing the same column name/category as already-protected tables but with zero policy attachments

4. **Tag-based coverage opportunities** (from [../templates/policy-recommendations/find-tag-coverage-opportunities.sql](../templates/policy-recommendations/find-tag-coverage-opportunities.sql)):
   - `ACCOUNT_USAGE.TAG_REFERENCES`: columns that have a governance tag applied
   - Anti-join against `POLICY_REFERENCES`: which of those tagged columns have NO policy
   - Group by tag to compute "one `ALTER TAG ... SET MASKING POLICY` statement covers N columns"

5. **Impact-ranked remediation list** (from [../templates/policy-recommendations/score-remediation-impact.sql](../templates/policy-recommendations/score-remediation-impact.sql)):
   - Join gap candidates with ACCESS_HISTORY access counts
   - Apply sensitivity weights: IDENTIFIER=3, QUASI_IDENTIFIER=2, SENSITIVE=1, heuristic-only=0.5
   - Sort by `impact_score = sensitivity_weight × query_volume_last_30d` descending

### Step 5: Present the Policy Gap Report

**✋ Stopping point:** Present the full report, then move into understanding the top gaps (Step 6).

**If serving pre-computed results (fast path)**, lead with freshness and the per-category summary from `GET_POLICY_RECOMMENDATION_SUMMARY()`, then the ranked detail:

Render the report as **Markdown** (a heading + a Markdown table). Do NOT wrap it in a code block and do NOT use box-drawing/ASCII-art borders — they collapse to one line when rendered. For example:

---
### 📋 Policy Recommendations (pre-computed)
_Last refreshed `<ts>` (~`<age>` ago) · `<N>` total recommendations_

**By category** — tiers by IMPACT_SCORE: High ≥ 10, Medium 1–<10, Low < 1

| Category | Total | High | Med | Low | Top Impact | Queries at Risk |
|---|--:|--:|--:|--:|--:|--:|
| MASKING_GAP | 12 | 4 | 6 | 2 | … | … |
| TAG_QUICKWIN | 7 | … | … | … | … | … |
| AGGREGATION_GAP | … | … | … | … | … | … |
---

Then present the **🔥 TOP GAPS BY IMPACT** table (below) sourced from `GET_POLICY_RECOMMENDATIONS`, ordered by `IMPACT_SCORE`.

**If serving a live scan (fallback)**, present the full inventory report as Markdown:

---
### 📋 Policy Coverage Report
_`<X>` gaps found — top `<Y>` are high impact_

**Existing policy coverage**

| Policy Kind | Policies | Attachments | Databases Covered | Notes |
|---|--:|--:|--:|---|
| Masking | N | N cols | N | |
| Row Access | N | N tables | N | |
| Projection | N | N cols | N | |
| Aggregation | N | N tables | N | |
| Join | N | N tables | N | |
---

Both paths share the ranked gap and tag-win tables (Markdown):

---
**🔥 Top gaps by impact** — ranked by IMPACT_SCORE

| # | Database.Schema.Table.Column | Sensitivity | Queries/30d | Suggested Policy |
|--:|---|---|--:|---|
| 1 | PROD_DB.PUBLIC.CUSTOMERS.SSN | IDENTIFIER | 45,200 | Masking |
| 2 | PROD_DB.PUBLIC.ORDERS.CC_NUMBER | IDENTIFIER | 31,000 | Masking |
| 3 | ANALYTICS.REPORTS.REVENUE_BY_USER | QUASI_ID | 18,500 | Aggregation |
| 4 | ANALYTICS.SHARING.PATIENT_DETAILS | SENSITIVE | 12,200 | Projection |

**🏷️ Tag-based quick wins** — single statement → many columns

| Tag | Unprotected Cols | Reusable Policy |
|---|--:|---|
| GOVERNANCE_DB.TAGS.PII | 38 | GOVERNANCE_DB.POLICIES.… |
| GOVERNANCE_DB.TAGS.CUSTOMER | 15 | No matching policy yet |
---

ℹ️ If Snowflake auto-classification tags (e.g. `SNOWFLAKE.CORE.SEMANTIC_CATEGORY:*`) are the only tags on some columns, those columns are not shown here — system tags are read-only and cannot be modified with `ALTER TAG`. Those columns appear in the Top gaps list above for direct column-level policy attachment.

In the live-path report, also add (from the fast path, this maps to categories with zero recommendations):

```
POLICY KINDS WITH ZERO COVERAGE
[List each policy kind with 0 attachments, with a one-line explanation of what it protects and why it's relevant]
```

Policy kind coverage notes to include when coverage is zero:
- **Aggregation**: prevents users from querying individual-level sensitive records by requiring minimum group sizes. Relevant when analytics queries expose user-level data.
- **Projection**: blocks specific columns from being `SELECT *`-ed or projected at all. Useful for columns that should only appear in JOIN results or aggregated views.
- **Join**: requires queries to join a fact table to a specific dimension table, preventing isolated column lookups. Used in data clean room and privacy-sensitive analytics scenarios.

### Step 6: Understand Each Gap, Then Apply

The goal here is not to click through fixes — it's to help the user *understand* each governance gap and decide how to close it. Work through the gaps in impact order, **starting with the single highest-impact one**, and only move to the next once the user is done with the current one.

For every recommendation, present an **understanding block first**, then the ready-to-run SQL, then the capability-aware apply footer. Lead with the tag-based quick win if one exists (it closes the most columns at once).

**A single gap usually has more than one valid remediation** — e.g. reuse an existing policy, create a new one, cover it via a governance tag, or apply a different policy kind. Surface the viable options for the gap and let the user choose, rather than pushing one fixed SQL; `REMEDIATION_SQL` (fast path) is the suggested default, not the only path.

**Where the fields come from:** in the fast path, `RATIONALE`, `REQUIRES_PRIVILEGE`, `EXISTING_POLICY_NAME`, `IMPACT_SCORE`, and `REMEDIATION_SQL` come straight from `GET_POLICY_RECOMMENDATIONS`. In the live path, derive them from the discovery queries (rationale = sensitivity + query volume + what the policy prevents; required privilege = `APPLY <KIND> POLICY` on the target).

**Understanding block (present before any SQL):**

```
🎯 GAP #N — [HIGH / MEDIUM / LOW] impact
Where:    [DB.SCHEMA.TABLE.COLUMN]   ([CATEGORY])
Exposure: [SENSITIVITY_LABEL] · [QUERIES_LAST_30D] queries/30d · impact [IMPACT_SCORE]
Why it matters: [RATIONALE — plain-language reason this is a risk right now]
To close it you need: [REQUIRES_PRIVILEGE]  (e.g. APPLY MASKING POLICY on the table)
Your options:
  • Lowest effort — reuse an existing policy: [EXISTING_POLICY_NAME]   (if one exists)
  • Create a new policy tailored to this column  (routes to data-policy.md)
  • Consider a different policy kind if it fits better (e.g. projection vs masking,
    aggregation min-group-size, join governing table)
```

**Capability-aware apply footer** — end every recommendation with the line matching the user's `CAPABILITY_LEVEL` from Step 1. This keeps the flow apply-on-approval, never one-click:

- **FULL_APPLY** → "I can apply this on your confirmation, or explain it further first — nothing runs until you say so."
- **POLICY_OWNER** *(owns the referenced policy)* → "You own this policy. Applying it also needs `APPLY <KIND> POLICY` on the target (or an account-level grant). I can run it once you confirm you have that, or prepare it to share with an admin."
- **POLICY_OWNER** *(does not own it)* **or ANALYST** → "Your role can't apply this directly. I'll explain the gap and hand you copy-ready SQL to share with your policy admin."

**Tag-based win (show first if available):**

```
🏷️  TAG-BASED QUICK WIN — closes N columns at once
Tag: [TAG_FULLY_QUALIFIED_NAME]
Why it matters: N unprotected sensitive columns share this tag (~X total queries/30d).
    One statement protects all of them.
To close it you need: APPLY MASKING POLICY on the tag (or account-level).

────────────────────────────────────────────────────────────────
ALTER TAG [TAG_FULLY_QUALIFIED_NAME]
  SET MASKING POLICY [POLICY_FULLY_QUALIFIED_NAME];
────────────────────────────────────────────────────────────────
→ capability-aware apply footer
```

Note: Never show a tag-based quick win for a Snowflake system tag (TAG_DATABASE = 'SNOWFLAKE'). If no user-defined tags have unprotected columns, omit this and state: "No user-defined tag-based quick wins found. Snowflake system tags are read-only and cannot be used for bulk policy attachment."

**Column-level masking gap:**

```
Why it matters: [COLUMN] holds [SEMANTIC_CATEGORY] ([SENSITIVITY_LABEL]) and is read
    [N] times/30d with no masking — every one of those reads exposes raw values.
Similar protection already on: [DB.SCHEMA.TABLE2.COLUMN2] (uses [POLICY_NAME])
To close it you need: APPLY MASKING POLICY on [DB.SCHEMA.TABLE]

Reuse existing policy (lowest effort):
────────────────────────────────────────────────────────────────
ALTER TABLE [DB.SCHEMA.TABLE]
  MODIFY COLUMN [COLUMN]
  SET MASKING POLICY [POLICY_FULLY_QUALIFIED_NAME];
────────────────────────────────────────────────────────────────
→ capability-aware apply footer
(If no reusable policy exists — fast-path `REMEDIATION_SQL` shows a `<your_masking_policy>`
 placeholder, or the live path found no similar existing policy — offer to create one via
 data-policy.md instead.)
```

**Aggregation policy gap** (tables with user-level identifiers and no aggregation policy):

```
Why it matters: [DB.SCHEMA.TABLE] contains [user_id / customer_id / patient_id]
    (QUASI_IDENTIFIER) and is queried [N] times/30d with no aggregation policy —
    individual-level records can be reverse-engineered from GROUP BY queries.
To close it you need: APPLY AGGREGATION POLICY on [DB.SCHEMA.TABLE]
Trade-off: MIN_GROUP_SIZE too high can break legitimate dashboards; 5 is a common start.

────────────────────────────────────────────────────────────────
CREATE AGGREGATION POLICY [DB.SCHEMA.AGG_POLICY_MIN5]
  AS () RETURNS AGGREGATION_CONSTRAINT ->
  AGGREGATION_CONSTRAINT(MIN_GROUP_SIZE => 5);

ALTER TABLE [DB.SCHEMA.TABLE]
  SET AGGREGATION POLICY [DB.SCHEMA.AGG_POLICY_MIN5];
────────────────────────────────────────────────────────────────
→ capability-aware apply footer  (offer to customize MIN_GROUP_SIZE first)
```

**Projection policy gap** (columns in high-volume SELECT * patterns):

```
Why it matters: [DB.SCHEMA.TABLE.COLUMN] is accessed [N] times/30d and appears in broad
    SELECT queries. A projection policy stops it being projected unless explicitly named
    or only returned in aggregated form.
To close it you need: APPLY PROJECTION POLICY on [DB.SCHEMA.TABLE]
Trade-off: full block vs NULLIFY mode — use data-policy.md if the user wants NULLIFY.

────────────────────────────────────────────────────────────────
CREATE PROJECTION POLICY [DB.SCHEMA.PROJ_POLICY_BLOCK]
  AS () RETURNS PROJECTION_CONSTRAINT ->
  PROJECTION_CONSTRAINT(ALLOW => FALSE);

ALTER TABLE [DB.SCHEMA.TABLE]
  MODIFY COLUMN [COLUMN]
  SET PROJECTION POLICY [DB.SCHEMA.PROJ_POLICY_BLOCK];
────────────────────────────────────────────────────────────────
→ capability-aware apply footer
```

**Join policy gap** (a sensitive table queried in isolation without a required join to a consent/dimension table):

```
Why it matters: [DB.SCHEMA.TABLE] holds sensitive personal data and is queried [N] times/30d
    without requiring a join to a consent or access-control table. A join policy enforces
    that queries must join it to a specific governing table (e.g. USER_CONSENT) first.
To close it you need: APPLY JOIN POLICY on [DB.SCHEMA.TABLE]
Confirm first: the governing table name for ALLOWED_JOIN_KEYS.

────────────────────────────────────────────────────────────────
CREATE JOIN POLICY [DB.SCHEMA.JOIN_POLICY_CONSENT]
  AS () RETURNS JOIN_CONSTRAINT ->
  BUILD_JOIN_CONSTRAINT(
    JOIN_REQUIRED => TRUE,
    ALLOWED_JOIN_KEYS => ALLOWED_JOIN_KEYS(TABLES => ('[DB.SCHEMA.CONSENT_TABLE]'))
  );

ALTER TABLE [DB.SCHEMA.TABLE]
  SET JOIN POLICY [DB.SCHEMA.JOIN_POLICY_CONSENT];
────────────────────────────────────────────────────────────────
→ capability-aware apply footer
```

**⚠️ MANDATORY STOPPING POINT**: Present the understanding block(s) and ask which gap the user wants to act on. Do not apply anything yet.

### Step 7: Execute the Chosen Remediation

Once the user has understood a gap and chosen to act on it:

| User Choice | Action |
|-------------|--------|
| Apply tag-based quick win | Show the `ALTER TAG ... SET MASKING POLICY` statement. Wait for approval per **Pre-Write Approval Rule**. Execute on confirmation. |
| Apply column masking (reuse existing policy) | Show the `ALTER TABLE ... MODIFY COLUMN ... SET MASKING POLICY` statement. Wait for approval. Execute on confirmation. |
| Create a new masking policy | **Load** `workflows/data-policy.md` and pass context: target column, data type, who should see real values. (Use this whenever `REMEDIATION_SQL` has a `<your_masking_policy>` placeholder.) |
| Apply aggregation policy | Show the `CREATE AGGREGATION POLICY` + `ALTER TABLE SET AGGREGATION POLICY` pair. Offer to customize the minimum group size first. Load `workflows/data-policy.md` if the user wants to configure parameters. |
| Apply projection policy | Show the SQL. If user wants `NULLIFY` enforcement mode instead of full block, load `workflows/data-policy.md`. |
| Apply join policy | Show the SQL. Confirm the governing table name (`ALLOWED_JOIN_KEYS`) with the user before executing. Load `workflows/data-policy.md` for complex configurations. |
| Explain further | Expand on the risk, the alternatives, or how the policy behaves at query time, then re-offer the SQL. |
| Re-scan after remediation | Re-run the scan — Step 4 for a live scan, or re-call the pre-computed procedures (Step 2) if the feature is in use — and present a before/after comparison (Step 8). |
| "share with admin" | Format the SQL as a clean, self-contained block with a plain-language summary (what it does, why it was recommended, which column/table it affects). Offer to include the full gap report as context for the admin. |
| "yes — I have table-level apply" | Run `SHOW GRANTS ON TABLE [target]` first to verify the current role has `APPLY MASKING POLICY` (or the relevant policy kind) on that table. If confirmed, execute. If not confirmed, surface a clear message with the grant command needed: `GRANT APPLY MASKING POLICY ON TABLE [target] TO ROLE [current_role]` (requires ACCOUNTADMIN or SECURITYADMIN to run). |

**⚠️ MANDATORY STOPPING POINT — Pre-Write Approval Rule (enforced for every state-changing SQL in this skill):**

Before executing any `CREATE`, `ALTER`, `DROP`, or `APPLY`:
1. Show the exact SQL.
2. Wait for explicit user approval.
3. Execute only after approval.

Snowflake's Policy Recommendations feature is advisory and never applies anything itself — this skill only executes on the user's explicit confirmation.

After a remediation, loop back to the next-highest gap (Step 6) until the user is done.

### Step 8: Before/After Comparison (Optional)

If the user acted on recommendations and wants to re-assess, re-run the scan (Step 4, or re-call the pre-computed procedures) and present:

Present the comparison as Markdown (heading + table), not ASCII art:

---
### 📊 Policy Coverage — Progress
_Gaps: `<Before>` → `<After>`_

| Policy Kind | Before | After | Delta |
|---|---|---|---|
| Masking | N attachments | N attachments | +N columns |
| Aggregation | 0 tables | N tables | +N tables |

**🔥 Remaining top gaps:** [updated top-N impact list]
---

> Note: if the feature is in fast-path mode, the pre-computed results only refresh on the feature's schedule — a re-call may still show the pre-remediation snapshot. Say so, and offer a live scan (Step 3) for an immediate up-to-date picture.

When the user is satisfied, suggest running the **Governance Maturity Score** assessment to see how the remediations improved the overall governance posture score:

```
Would you like me to run a Governance Maturity Score assessment to see
how these changes improved your overall governance posture?
```

If yes, **Load** `workflows/governance-maturity-score.md`.

## Stopping Points

> **UI slash-command entry (Step 0)** skips the Step 1 plan-confirm and Step 3 scope stops — the categories were already chosen in the UI. The Step 7 pre-write approval gate still applies before any change.

- ✋ **Step 1**: Role validated → explain plan, wait for user to confirm before running queries
- ✋ **Step 2**: Pre-computed recommendations found → show their age, wait for the user to choose pre-computed vs. live scan
- ✋ **Step 3**: Present popular databases (live scan) → wait for user to confirm scope
- ✋ **Step 5**: Present full gap report before moving into per-gap understanding
- ✋ **Step 6**: Present the understanding block(s) → wait for the user to pick which gap to act on
- ✋ **Step 7**: Before every `CREATE`, `ALTER`, or `APPLY` → show SQL, wait for approval

## Expected Outcomes

- **Fast when possible** — pre-computed feature serves recommendations from one `CALL` with a visible freshness age; otherwise a live `ACCOUNT_USAGE` scan.
- **Ranked gap discovery** — columns/tables lacking coverage, ranked by real query traffic, across masking, aggregation, projection, and join.
- **Understanding + tag-scale** — each top gap explains what / why / which privilege before any change; tag-based wins close many columns with one `ALTER TAG`.
- **Guided, approved remediation** — fixes apply only on explicit approval, routing into data-policy.md for complex creation; a before/after comparison links back to governance-maturity-score.

## SQL Templates

All under `../templates/policy-recommendations/`, linked inline where each is used (Steps 1–4): `check-precomputed-recommendations.sql` (probe the pre-computed feature + freshness), `check-existing-policies.sql` (policy inventory), `find-hot-tables.sql` (ACCESS_HISTORY / QUERY_HISTORY volume), `find-gap-candidates.sql` (sensitive + heuristic gaps), `find-tag-coverage-opportunities.sql` (tag-based bulk opportunities; system tags excluded), `score-remediation-impact.sql` (impact ranking), `check-apply-grants.sql` (apply-policy capability, Step 1).
