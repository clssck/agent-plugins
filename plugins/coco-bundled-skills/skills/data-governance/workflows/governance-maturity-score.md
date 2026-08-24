---
name: governance-maturity-score
parent_skill: data-governance
description: "Assess and score the data governance maturity of a Snowflake account. Use when: user asks about governance posture, governance maturity, governance score, governance readiness, governance assessment, governance health check, how well governed is my account, governance checklist, improve governance, governance recommendations."
---

# Governance Maturity Score

Assess the governance posture of a Snowflake account across three pillars — **Know**, **Protect**, and **Monitor** — and produce a maturity score (0–5) with actionable recommendations.

## When to Use

Activate when the user asks about:
- "What is my governance maturity score?", "governance posture", "governance health"
- "How well governed is my account?", "governance assessment", "governance readiness"
- "Governance checklist", "improve governance", "governance recommendations"
- "Am I following governance best practices?"

## Governance Pillars

| Pillar | Snowflake Capability | What It Means |
|--------|---------------------|---------------|
| **Know your data** | Data Classification | Continuous classification using 150+ sensitive data categories. Tagging columns where sensitive data lives. |
| **Protect the data** | Masking Policies, Row Access Policies, RBAC | Policies to mask sensitive data at query time for unauthorized users. |
| **Monitor access** | ACCESS_HISTORY | Captures all queries in a structured format to enable audit use cases. |

## Scoring Scale (0–5)

| Score | Criteria | State |
|-------|----------|-------|
| **0** | None of the three governance features are in use (no classification, no masking, no access history querying). | Ungoverned |
| **1** | One or more governance features are enabled, but coverage thresholds are not met. | Basic |
| **2** | All assessed databases are monitored with data classification. | Emerging |
| **3** | Score 2 + masking score >= 75% across assessed databases (see 4-tier masking rules). | Developing |
| **4** | Score 3 + ACCESS_HISTORY is queried at least once in the last 30 days on objects identified as sensitive. | Advanced |
| **5** | All governance features are used across ALL data: classification on all databases, all sensitive objects masked, and regular access auditing. | Mature |

## Workflow

### Step 1: Validate Role and Introduce the Assessment

Before running any governance queries, verify the current role can access ACCOUNT_USAGE views. Use `IS_ROLE_IN_SESSION` to check for known roles with ACCOUNT_USAGE access:

```sql
SELECT
    IS_ROLE_IN_SESSION('ACCOUNTADMIN') AS HAS_ACCOUNTADMIN,
    IS_ROLE_IN_SESSION('GOVERNANCE_VIEWER') AS HAS_GOVERNANCE_VIEWER;
```

This checks both primary and secondary roles and returns instantly.

If **either** returns `True`, proceed with the assessment.

If **both** return `False`, stop and inform the user:

```
Your current role does not have access to SNOWFLAKE.ACCOUNT_USAGE views,
which are required for the governance maturity assessment.

Access to governance-related ACCOUNT_USAGE views is granted through:
- The GOVERNANCE_VIEWER application role on the SNOWFLAKE database
- The ACCOUNTADMIN role
- Secondary roles that include either of the above

Please switch to a role with ACCOUNT_USAGE access (or ensure your
secondary roles include one) and try again.
```

Do NOT proceed with any further queries until access is validated.

Once the role is confirmed, explain to the user what will be assessed:

```
I'll assess your Snowflake account's governance maturity across three pillars:

1. **Know** — Is sensitive data being discovered and classified?
2. **Protect** — Is sensitive data protected with masking policies?
3. **Monitor** — Is data access being audited regularly?

I'll check each pillar and assign a maturity score from 0 (ungoverned) to 5 (mature).
Let me start by identifying your most-used databases.
```

**⚠️ MANDATORY STOPPING POINT**: Wait for the user to confirm before running queries.

### Step 2: Identify and Confirm Databases for Assessment

Run the popular databases query from [../templates/governance-maturity-score/check-popular-databases.sql](../templates/governance-maturity-score/check-popular-databases.sql) to identify the most-used databases by query volume in the last 30 days.

Present the results to the user in a clear table:

```
Here are the most active databases in your account (by query volume, last 30 days):

│ # │ Database         │ Queries │ Users │
├───┼──────────────────┼─────────┼───────┤
│ 1 │ PROD_DB          │ 12,450  │ 34    │
│ 2 │ ANALYTICS_DB     │ 8,200   │ 22    │
│ 3 │ STAGING_DB       │ 3,100   │ 15    │
│ …                                      │

Should I assess **all** of these databases, or are there any you'd like to
skip? List the names to exclude and optionally a reason for each
(e.g. "skip STAGING_DB — sandbox data, TEST_DB — not production"),
or reply "all" to assess everything.
```

**⚠️ MANDATORY STOPPING POINT**: Wait for the user to confirm the database list.

Record the user-confirmed databases as `assessed_databases` (all popular databases minus any the user asked to exclude). Use **only** these databases for all subsequent queries and scoring. If the user says "all" or confirms without exclusions, use the full popular databases list.

For each excluded database, record the user-provided reason as `exclusion_reason`. If the user did not give a reason for a specific database, default to "Excluded by user".

### Step 3: Run All Governance Checks

**🚨 CRITICAL: Execute ALL queries below autonomously without stopping.** These are read-only queries against ACCOUNT_USAGE views. Do NOT ask for confirmation between queries. Do NOT present query results individually. Collect all results silently and proceed directly to Step 4 to present the consolidated report.

Use the SQL from the following templates as reference. Execute each query, record the findings, and move to the next immediately.

**Important:** All queries below must be scoped to the `assessed_databases` list confirmed by the user in Step 2. When running the SQL templates, replace the `popular_dbs` CTE or add a filter to restrict results to only the confirmed databases. Any databases the user asked to skip must be excluded from all queries and scoring.

**Queries to run (in order):**

1. **Classification profiles** (from [../templates/governance-maturity-score/check-classification-status.sql](../templates/governance-maturity-score/check-classification-status.sql)):
   - `SHOW SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE IN ACCOUNT`
   - `SELECT SYSTEM$SHOW_SENSITIVE_DATA_MONITORED_ENTITIES('DATABASE')`
   - Query `ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST` for databases with results and category breakdown
   - Record: `classification_enabled`, `databases_classified`, `popular_dbs_covered_pct`

2. **Masking policies** (from [../templates/governance-maturity-score/check-masking-policies.sql](../templates/governance-maturity-score/check-masking-policies.sql)):
   - Query `ACCOUNT_USAGE.MASKING_POLICIES` for existing policies
   - Query `ACCOUNT_USAGE.POLICY_REFERENCES` for policy attachments by database
   - Cross-reference classified sensitive columns with policy attachments to find gaps
   - Record per assessed database: `total_sensitive_columns`, `masked_sensitive_columns`, `total_masked_columns` (including non-sensitive), `unprotected_sensitive_columns`
   - Compute `masking_score` per database using the **4-tier masking rules** (see Step 4 scoring logic)
   - Record overall: `masking_policies_exist`, `masking_score` (aggregate across assessed databases)

3. **Access history usage** (from [../templates/governance-maturity-score/check-access-history-usage.sql](../templates/governance-maturity-score/check-access-history-usage.sql)):
   - Query `ACCOUNT_USAGE.QUERY_HISTORY` for queries referencing ACCESS_HISTORY in the last 30 days
   - Record: `access_history_queried`, `last_queried_date`, `query_frequency` (weekly/monthly/rarely/never)

### Step 4: Compute and Present the Score

**Masking score — 4-tier rules (computed per assessed database):**

For each database in `assessed_databases`, determine the masking tier:

| Condition | Masking Score | Label |
|-----------|--------------|-------|
| Sensitive columns exist, but **none** have masking policies | **0%** | Unprotected |
| Sensitive columns exist, but only **some** have masking policies | **25%** | Partial |
| **No** sensitive columns found, but masking policies exist on columns in this database | **75%** | Proactive |
| Sensitive columns exist, and **all** sensitive columns have masking policies | **100%** | Full |

If a database has no sensitive columns AND no masking policies, it does not contribute to the masking score (skip it).

The **overall `masking_score`** is the average of per-database masking scores across all assessed databases that have at least one of: sensitive columns or masking policies.

**Overall scoring logic:**

```
score = 0

# Check if any features are enabled
features_enabled = 0
if classification_enabled: features_enabled += 1
if masking_policies_exist: features_enabled += 1
if access_history_queried: features_enabled += 1

if features_enabled == 0:
    score = 0    # Ungoverned
elif features_enabled >= 1:
    score = 1    # Basic — some feature adoption but coverage gaps

# Pillar-based scoring (2–4)
if popular_dbs_covered_pct >= 80%:
    score = 2    # Emerging — assessed DBs classified
if score >= 2 and masking_score >= 0.75:
    score = 3    # Developing — sensitive data protected
if score >= 3 and access_history_queried and query_frequency in (weekly, monthly):
    score = 4    # Advanced — regular auditing

# Full maturity (Score 5 = Mature)
# Require: classification on all assessed DBs, overall masking_score == 1.0,
#          and ACCESS_HISTORY queried weekly or monthly.
if popular_dbs_covered_pct >= 80 and masking_score >= 1.0 and access_history_queried and query_frequency in (weekly, monthly):
    score = 5    # Mature
```

**⚠️ MANDATORY STOPPING POINT**: Present the full report before offering recommendations.

Present the report using this format:

```
╔══════════════════════════════════════════════════════╗
║          GOVERNANCE MATURITY REPORT                  ║
║          Score: X / 5 — [State Label]                ║
╚══════════════════════════════════════════════════════╝

📊 PILLAR SUMMARY
───────────────────────────────────────────────────────
│ Pillar           │ Status │ Details                  │
├──────────────────┼────────┼──────────────────────────┤
│ Know Your Data   │ ✅/❌  │ [summary]                │
│ Protect Data     │ ✅/❌  │ [summary]                │
│ Monitor Access   │ ✅/❌  │ [summary]                │
───────────────────────────────────────────────────────

Pillar status rules (these determine ✅ vs ❌):
- **Know Your Data**: ✅ only if >= 80% of assessed databases
  (from Step 2) have a classification profile attached (i.e.,
  appear in SYSTEM$SHOW_SENSITIVE_DATA_MONITORED_ENTITIES).
  Otherwise ❌, even if classification is enabled on some
  non-assessed databases.
- **Protect Data**: ✅ only if the overall `masking_score` >= 0.75
  (i.e., assessed databases average at least "Proactive" tier).
  Otherwise ❌.
- **Monitor Access**: ✅ if ACCESS_HISTORY has been queried at
  least once in the last 30 days. Otherwise ❌.

📈 PER-DATABASE GOVERNANCE STATUS
─────────────────────────────────────────────────────────────────────────────────────────
│ Database         │ Query Vol │ Classified │ Sensitive Cols │ Masked    │ Protection │ Score │
├──────────────────┼────────────┼────────────┼────────────────┼───────────┼────────────┼───────┤
│ PROD_DB          │ 12.4K      │ ✅         │ 50             │ 50 / 50  │ Full       │ 1.00  │
│ ANALYTICS_DB     │ 8.2K       │ ✅         │ 12             │ 3 / 12   │ Partial    │ 0.25  │
│ STAGING_DB       │ 3.1K       │ ❌         │ 0              │ 0        │ Unprotected│ 0.00  │
─────────────────────────────────────────────────────────────────────────────────────────

For each database in `assessed_databases` from Step 2, show:
- Query Vol: Query volume (e.g. from Step 2 popular databases), or "N/A" if not in that list.
- Classified: Is this database monitored by auto-classification or has classification results?
- Sensitive Cols: Count of classified sensitive columns in this database.
- Masked: For DBs with sensitive columns, show "masked_count / sensitive_cols"; otherwise show count of columns with policies or "0".
- Protection: The 4-tier posture label only (Unprotected / Partial / Proactive / Full). Do not show a % — it is a tier score, not "percentage of columns masked."
- Score: The numeric masking score (0.00 / 0.25 / 0.75 / 1.00)

If the user excluded any databases in Step 2, do NOT show them
in this table. Only show the assessed databases.

🚫 DATABASES EXCLUDED FROM ASSESSMENT
───────────────────────────────────────────────────────────────
│ Database         │ Reason              │
├──────────────────┼─────────────────────┤
│ STAGING_DB       │ Sandbox data        │
│ TEST_DB          │ Not production      │
───────────────────────────────────────────────────────────────

If the user excluded databases in Step 2, list them here with
the reason they provided. If no reason was given for a database,
use "Excluded by user" as the default. If no databases were
excluded (user said "all"), omit this section entirely.

⚠️  GAPS IDENTIFIED
[List of specific gaps, e.g.:]
- ANALYTICS_DB: 12 sensitive columns without masking policies
- STAGING_DB: Not monitored by auto-classification
```

### Step 5: Provide Recommendations

Based on the score, provide prioritized recommendations:

**If Score 0 → Target Score 1:**
1. Enable Data Classification on your most-used database
2. Guide: "Would you like me to help set up auto-classification? I can use the sensitive-data-classification skill."

**If Score 1 → Target Score 2:**
1. Expand classification to cover all assessed databases
2. Provide the list of unclassified assessed databases with commands to enable

**If Score 2 → Target Score 3:**
1. Create masking policies for unprotected sensitive columns
2. Provide the list of sensitive columns without masking
3. Guide: "Would you like me to help create masking policies? I can use the data-policy skill."

**If Score 3 → Target Score 4:**
1. Set up regular ACCESS_HISTORY auditing
2. Suggest a monthly audit query for sensitive data access
3. Guide: "Would you like me to help set up access monitoring?"

**If Score 4 → Target Score 5:**
1. Expand classification to all databases (not just popular ones)
2. Ensure 100% masking coverage on sensitive columns
3. Automate ACCESS_HISTORY auditing with a Snowflake task

**If Score 5:**
Congratulate the user and suggest ongoing monitoring practices.

After presenting recommendations, also offer to export the report:

```
Would you also like me to generate a PDF version of this Governance Maturity Report?
```

**⚠️ MANDATORY STOPPING POINT**: Ask the user which recommendation they'd like to act on, and whether they want a PDF export.

When the user has finished (or declined), suggest trying the **observability maturity assessment** if they also care about data observability (quality monitoring, DMFs, lineage, BI coverage): **Load** `workflows/observability-maturity-score.md`.

### Step 6: Execute Recommendations (Optional)

Based on user's choice, route to the appropriate sub-skill:

| User Choice | Action |
|-------------|--------|
| Set up classification | **Load** `workflows/sensitive-data-classification.md` |
| Create masking policies | **Load** `workflows/data-policy.md` |
| Set up access monitoring | **Load** `workflows/horizon-catalog.md` |
| Generate PDF report | Query `SELECT CURRENT_ACCOUNT_NAME()` to get the account name. Run the PDF generation script from [../templates/governance-maturity-score/generate_report_pdf.py](../templates/governance-maturity-score/generate_report_pdf.py), substituting the actual assessment data including the account name. Populate all data fields: `EXECUTIVE_SUMMARY` (2-3 sentence summary: what's working, biggest gap, best next step), `NEXT_LEVEL_NOTE` (what's needed for the next score), `PILLARS` with `(name, passed, coverage_pct, target_pct, detail)` tuples, `DATABASES` with `(db_name, volume, classified, sensitive_cols, masked_count, masking_pct)` tuples (masking_pct is the 4-tier value 0/25/75/100 — PDF shows "Protection" column with labels Unprotected/Partial/Proactive/Full, not a %), and `EXCLUDED_DATABASES` with `(db_name, reason)` tuples for any databases the user excluded in Step 2 (using their stated reason, or "Excluded by user" if none given). Output file: `~/governance_maturity_report_<ACCOUNT_NAME>.pdf`. Inform the user of the file path. |
| Re-run assessment | Return to Step 2 |

### Step 7: Re-run and Compare (Optional)

If the user acted on recommendations and wants to re-assess, re-run Step 3 and present a before/after comparison:

```
╔══════════════════════════════════════════════════════╗
║          GOVERNANCE MATURITY — PROGRESS              ║
║          Previous: X / 5  →  Current: Y / 5          ║
╚══════════════════════════════════════════════════════╝

📊 PILLAR CHANGES
───────────────────────────────────────────────────────
│ Pillar           │ Before │ After │ Change           │
├──────────────────┼────────┼───────┼──────────────────┤
│ Know Your Data   │ ❌     │ ✅    │ +Classification  │
│ Protect Data     │ ❌     │ ❌    │ No change        │
│ Monitor Access   │ ✅     │ ✅    │ No change        │
───────────────────────────────────────────────────────

📈 DATABASE CHANGES
[Show databases that improved since last assessment]

🎯 NEXT STEPS
[Remaining recommendations to reach next score level]
```

Retain the previous run's findings from this conversation to produce the comparison. If no previous run exists in this session, skip the comparison and present the standard report.

## Stopping Points

- ✋ **Step 1**: Validate role, then present the three-pillar intro and wait for user to confirm before running queries
- ✋ **Step 2**: Present popular databases list and wait for user to confirm which databases to assess
- ✋ **Step 4**: Present full report before recommendations
- ✋ **Step 5**: Ask which recommendation to act on, and whether they want a PDF export

## Expected Outcomes

1. **Full Assessment**: User receives score and acts on recommendations
2. **Awareness Only**: User reviews score and plans to act later
3. **Immediate Action**: User picks a recommendation and we route to the appropriate skill
4. **Already Mature**: User scores 5, we confirm and suggest ongoing monitoring
5. **PDF Export**: User requests a PDF and receives the report at `~/governance_maturity_report_<ACCOUNT_NAME>.pdf`

## Output

- Maturity score (0–5) with state label (Ungoverned / Basic / Emerging / Developing / Advanced / Mature)
- Pillar summary table (Know / Protect / Monitor status)
- Per-database governance status table for all assessed databases (with 4-tier masking labels)
- Gap list identifying specific unclassified databases and unmasked sensitive columns
- Prioritized recommendations to reach the next score level
- Before/after comparison if re-running after remediation

## SQL Templates

Located in `../templates/governance-maturity-score/` (relative to this file in `workflows/`):

1. **[check-popular-databases.sql](../templates/governance-maturity-score/check-popular-databases.sql)** — Identify most-used databases by query volume
2. **[check-classification-status.sql](../templates/governance-maturity-score/check-classification-status.sql)** — Assess data classification coverage
3. **[check-masking-policies.sql](../templates/governance-maturity-score/check-masking-policies.sql)** — Assess masking policy coverage on sensitive data
4. **[check-access-history-usage.sql](../templates/governance-maturity-score/check-access-history-usage.sql)** — Assess ACCESS_HISTORY query frequency

## PDF Generation

5. **[generate_report_pdf.py](../templates/governance-maturity-score/generate_report_pdf.py)** — Python script (requires `reportlab`) to render the maturity report as a formatted PDF. Substitute the placeholder data in the script with the actual assessment findings before running. Requires `ACCOUNT_NAME` (from `SELECT CURRENT_ACCOUNT_NAME()`). Output: `~/governance_maturity_report_<ACCOUNT_NAME>.pdf`
