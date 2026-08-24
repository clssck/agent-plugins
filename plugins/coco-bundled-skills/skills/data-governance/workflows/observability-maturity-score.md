---
name: observability-maturity-score
parent_skill: data-governance
description: "Assess data observability maturity across quality monitoring (DMFs), BI tool coverage, external lineage integration, and lineage usage for RCA/impact analysis. Use when: user asks about data observability, pipeline monitoring, quality monitoring maturity, lineage usage, external lineage, DMF coverage, dashboard data quality, observability score, observability assessment."
---

# Data Observability Maturity Score

Assess the data observability posture of a Snowflake account across four pillars — **Quality Monitoring**, **BI Coverage**, **External Lineage**, and **Lineage Usage** — and produce a maturity score (0–5) with actionable recommendations.

## When to Use

Activate when the user asks about:
- "data observability score", "observability maturity", "observability assessment"
- "DMF coverage", "quality monitoring", "pipeline monitoring maturity"
- "dashboard data quality", "BI tool monitoring", "PowerBI/Tableau quality"
- "external lineage", "dbt lineage", "Airflow lineage integration"
- "GET_LINEAGE usage", "lineage for RCA", "impact analysis readiness"

## Observability Pillars

| Pillar | Snowflake Capability | What It Means |
|--------|---------------------|---------------|
| **Quality Monitoring** | Data Metric Functions (DMFs) | DMFs attached to pipeline tables to continuously monitor null counts, freshness, row counts, duplicates, and custom checks. |
| **BI Coverage** | DMFs on BI-consumed objects | Quality monitoring specifically on tables/views consumed by dashboards (PowerBI, Tableau, Looker, etc.). |
| **External Lineage** | OpenLineage REST API | Lineage from upstream tools (dbt, Airflow, Spark) ingested into Snowflake for end-to-end visibility. |
| **Lineage Usage** | GET_LINEAGE, OBJECT_DEPENDENCIES | Active use of lineage functions for root cause analysis and impact analysis before making changes. |

## Scoring Scale (0–5)

| Score | Criteria | State |
|-------|----------|-------|
| **0** | No DMFs are in use, no external lineage is configured, and GET_LINEAGE is never queried. | Unmonitored |
| **1** | One or more observability features are in use, but coverage is minimal (e.g., DMFs on a few tables, or sporadic lineage queries). | Basic |
| **2** | DMFs are actively monitoring tables in data pipelines with scheduled measurements. Coverage reaches popular pipeline databases. | Emerging |
| **3** | Score 2 + tables consumed by BI tools (PowerBI, Tableau) are also monitored with DMFs. | Developing |
| **4** | Score 3 + external lineage from at least one upstream tool (dbt or Airflow) is ingested into Snowflake, AND GET_LINEAGE or OBJECT_DEPENDENCIES is queried at least monthly for RCA/impact analysis. | Advanced |
| **5** | All observability features are fully adopted: DMFs on all critical pipeline and BI-consumed tables, external lineage from all major upstream tools, and regular (weekly+) lineage-based RCA/impact analysis. | Mature |

## Workflow

### Step 1: Validate Role and Introduce the Assessment

Validate role and introduce the assessment: Same as governance-maturity-score Step 1, but also check `IS_ROLE_IN_SESSION('USAGE_VIEWER')`. Proceed if ACCOUNTADMIN, GOVERNANCE_VIEWER, or USAGE_VIEWER is in session. Then present the four-pillar intro below and wait for user confirmation.

Once the role is confirmed, explain to the user what will be assessed:

```
I'll assess your Snowflake account's data observability maturity across four pillars:

1. **Quality Monitoring** — Are Data Metric Functions (DMFs) monitoring your pipeline tables?
2. **BI Coverage** — Are tables consumed by dashboards (PowerBI, Tableau) also monitored?
3. **External Lineage** — Is lineage from upstream tools (dbt, Airflow) ingested into Snowflake?
4. **Lineage Usage** — Is GET_LINEAGE used for root cause and impact analysis?

I'll check each pillar and assign a maturity score from 0 (unmonitored) to 5 (mature).
Let me start by checking your account's observability posture.
```

**⚠️ MANDATORY STOPPING POINT**: Wait for the user to confirm before running queries.

### Step 2: Run All Observability Checks

**🚨 CRITICAL: Execute ALL queries below autonomously without stopping.** These are read-only queries against ACCOUNT_USAGE views only (no LOCAL views). Do NOT ask for confirmation between queries. Do NOT present query results individually. Collect all results silently and proceed directly to Step 3 to present the consolidated report.

**Queries to run (in order):**

1. **Popular databases** (from [../templates/observability-maturity-score/check-popular-databases.sql](../templates/observability-maturity-score/check-popular-databases.sql)):
   Identify most-used databases by query volume in the last 90 days. Record the top databases as priority targets.

2. **DMF coverage** (from [../templates/observability-maturity-score/check-dmf-coverage.sql](../templates/observability-maturity-score/check-dmf-coverage.sql)):
   - Count distinct DMFs in the account (system + custom)
   - Count distinct tables/views with DMFs attached via `ACCOUNT_USAGE.DATA_METRIC_FUNCTION_REFERENCES`
   - Cross-reference DMF-monitored tables against popular databases from Step 1
   - Record: `dmfs_exist`, `dmf_count`, `tables_with_dmfs`, `popular_dbs_with_dmf_coverage_pct` (uses ACCOUNT_USAGE only; no LOCAL views)

3. **BI tool detection and coverage** (from [../templates/observability-maturity-score/check-bi-tool-usage.sql](../templates/observability-maturity-score/check-bi-tool-usage.sql)):
   - Detect BI tool queries in `QUERY_HISTORY` (last 90 days) by matching patterns:
     - **PowerBI**: `query_tag` containing `PowerBI` or `Power BI`, user/warehouse/role names containing `POWERBI` or `PBI`
     - **Tableau**: `query_tag` containing `Tableau`, user/warehouse/role names containing `TABLEAU`
     - **Looker**: `query_tag` containing `Looker`, user/warehouse/role names containing `LOOKER`
     - **dbt**: `query_tag` containing valid JSON with `dbt_version` key
   - Identify tables/views accessed by BI tools (from `database_name` in query history)
   - Cross-reference BI-consumed databases with DMF-monitored tables
   - Record: `bi_tools_detected` (list), `bi_query_count`, `bi_databases` (list), `bi_dbs_with_dmf_pct`

4. **External lineage** (from [../templates/observability-maturity-score/check-external-lineage.sql](../templates/observability-maturity-score/check-external-lineage.sql)):
   - Check if `INGEST LINEAGE` privilege is granted to any role via `ACCOUNT_USAGE.GRANTS_TO_ROLES` (no SHOW GRANTS)
   - Check `QUERY_HISTORY` for queries referencing `external-lineage` or `openlineage` (indicates API usage)
   - Check for dbt-specific query tags (JSON with `dbt_version`) as indicator of dbt integration
   - Check for Airflow-specific patterns in query tags or user names
   - Record: `ingest_lineage_granted`, `external_lineage_api_used`, `dbt_detected`, `airflow_detected`, `external_tools_with_lineage` (count of tools sending lineage)

5. **Lineage usage for RCA/impact analysis** (from [../templates/observability-maturity-score/check-lineage-usage.sql](../templates/observability-maturity-score/check-lineage-usage.sql)):
   - Query `QUERY_HISTORY` for calls to `GET_LINEAGE` or `SNOWFLAKE.CORE.GET_LINEAGE` in the last 90 days
   - Query `QUERY_HISTORY` for queries against `OBJECT_DEPENDENCIES` view
   - Query `QUERY_HISTORY` for queries against `ACCESS_HISTORY` with `OBJECTS_MODIFIED` (column-level lineage)
   - Record: `get_lineage_queried`, `get_lineage_query_count`, `get_lineage_frequency` (weekly/monthly/rarely/never), `object_dependencies_queried`, `column_lineage_queried`, `lineage_users` (distinct users)

### Step 3: Compute and Present the Score

**Scoring logic:**

```
score = 0

# Check if any observability features are in use
features_in_use = 0
if dmfs_exist: features_in_use += 1
if external_lineage_api_used or ingest_lineage_granted: features_in_use += 1
if get_lineage_queried or object_dependencies_queried: features_in_use += 1

if features_in_use == 0:
    score = 0    # Unmonitored

elif features_in_use >= 1:
    score = 1    # Basic — some observability adoption

# Pillar-based scoring (2–5)
if dmfs_exist and popular_dbs_with_dmf_coverage_pct >= 50% and recent_measurements_exist:
    score = 2    # Emerging — pipeline tables monitored with DMFs

if score >= 2 and bi_tools_detected and bi_dbs_with_dmf_pct >= 50%:
    score = 3    # Developing — BI-consumed tables also monitored

if score >= 3 and (external_lineage_api_used or (dbt_detected and ingest_lineage_granted) or (airflow_detected and ingest_lineage_granted)) and (get_lineage_queried and get_lineage_frequency in (weekly, monthly)):
    score = 4    # Advanced — external lineage + active RCA

# Full maturity
if score >= 4 and popular_dbs_with_dmf_coverage_pct >= 80% and bi_dbs_with_dmf_pct >= 80% and external_tools_with_lineage >= 2 and get_lineage_frequency == weekly:
    score = 5    # Mature — comprehensive observability
```

**⚠️ MANDATORY STOPPING POINT**: Present the full report before offering recommendations.

Present the report using this format:

```
╔══════════════════════════════════════════════════════╗
║        DATA OBSERVABILITY MATURITY REPORT             ║
║        Score: X / 5 — [State Label]                   ║
╚══════════════════════════════════════════════════════╝

PILLAR SUMMARY
───────────────────────────────────────────────────────
│ Pillar              │ Status │ Details                │
├─────────────────────┼────────┼────────────────────────┤
│ Quality Monitoring  │ ✅/❌  │ [summary]              │
│ BI Coverage         │ ✅/❌  │ [summary]              │
│ External Lineage    │ ✅/❌  │ [summary]              │
│ Lineage Usage       │ ✅/❌  │ [summary]              │
───────────────────────────────────────────────────────

Pillar status rules (these determine ✅ vs ❌):
- **Quality Monitoring**: ✅ if DMFs exist and >= 50% of popular
  databases have tables with DMF coverage. Otherwise ❌.
- **BI Coverage**: ✅ if BI tools are detected AND >= 50% of
  BI-consumed databases have DMF-monitored tables. Otherwise ❌.
  If no BI tools detected, mark as ⚠️ (N/A — no BI tools found).
- **External Lineage**: ✅ if INGEST LINEAGE is granted AND at
  least one external tool (dbt/Airflow) is sending lineage.
  Otherwise ❌.
- **Lineage Usage**: ✅ if GET_LINEAGE or OBJECT_DEPENDENCIES
  is queried at least monthly. Otherwise ❌.

DMF COVERAGE BY DATABASE
───────────────────────────────────────────────────────────────
│ Database         │ Tables w/ DMFs │ BI-Consumed │ Monitored │
├──────────────────┼────────────────┼─────────────┼───────────┤
│ PROD_DB          │ 15             │ ✅          │ ✅        │
│ ANALYTICS_DB     │ 0              │ ✅          │ ❌        │
│ STAGING_DB       │ 3              │ ❌          │ ✅        │
───────────────────────────────────────────────────────────────

For each popular database, show:
- Tables w/ DMFs: Number of tables with DMF associations
- BI-Consumed: Whether BI tools query this database
- Monitored: Whether DMFs are running on tables in this database

EXTERNAL LINEAGE STATUS
───────────────────────────────────────────
│ Tool     │ Detected │ Lineage Ingested │
├──────────┼──────────┼──────────────────┤
│ dbt      │ ✅/❌    │ ✅/❌            │
│ Airflow  │ ✅/❌    │ ✅/❌            │
│ Other    │ ✅/❌    │ ✅/❌            │
───────────────────────────────────────────

GAPS IDENTIFIED
[List of specific gaps, e.g.:]
- ANALYTICS_DB: Queried by Tableau but no DMFs attached
- dbt detected but external lineage not ingested (INGEST LINEAGE not granted)
- GET_LINEAGE never queried — no RCA/impact analysis capability
```

### Step 4: Provide Recommendations

Based on the score, provide prioritized recommendations:

**If Score 0 → Target Score 1:**
1. Start with system DMFs (NULL_COUNT, FRESHNESS, ROW_COUNT) on your most critical pipeline table
2. Set a DATA_METRIC_SCHEDULE (e.g., every 5 minutes or on DML trigger)
3. Guide: "Would you like me to help set up DMFs on your most popular tables? I can use the data-quality skill."

**If Score 1 → Target Score 2:**
1. Expand DMF coverage to tables in all popular databases
2. Add custom DMFs for business-specific quality checks
3. Set up expectations on DMFs to define pass/fail criteria
4. Provide the list of popular databases lacking DMF coverage

**If Score 2 → Target Score 3:**
1. Identify tables consumed by BI tools (PowerBI, Tableau) that lack DMFs
2. Prioritize FRESHNESS and NULL_COUNT DMFs on BI-consumed tables
3. Provide the list of BI-consumed databases/tables without quality monitoring

**If Score 3 → Target Score 4:**
1. Configure external lineage integration:
   - Grant `INGEST LINEAGE ON ACCOUNT` to the appropriate role
   - Set up dbt-ol (OpenLineage for dbt) or Airflow OpenLineage provider
   - Configure the transport to point to `https://<account>.snowflakecomputing.com/api/v2/lineage/external-lineage`
2. Start using GET_LINEAGE for impact analysis before schema changes
3. Set up a monthly lineage review process

**If Score 4 → Target Score 5:**
1. Expand DMF coverage to 80%+ of all popular and BI-consumed databases
2. Integrate lineage from all upstream tools (not just one)
3. Automate weekly GET_LINEAGE queries via Snowflake tasks for proactive monitoring
4. Build lineage-based alerting for pipeline breaks

**If Score 5:**
Congratulate the user and suggest ongoing monitoring practices:
- Regular review of DMF measurement trends
- Alerting on DMF expectation failures
- Quarterly lineage graph review for new dependencies

After presenting recommendations, also offer to export the report:

```
Would you also like me to generate a PDF version of this Data Observability Maturity Report?
```

**⚠️ MANDATORY STOPPING POINT**: Ask the user which recommendation they'd like to act on, and whether they want a PDF export.

When the user has finished (or declined), suggest trying the **governance maturity assessment** if they also care about data governance (classification, masking, access audit): **Load** `workflows/governance-maturity-score.md`.

### Step 5: Execute Recommendations (Optional)

Based on user's choice, route to the appropriate action:

| User Choice | Action |
|-------------|--------|
| Set up DMFs | **Load** the `data-quality` skill for DMF setup guidance |
| Configure external lineage | Provide step-by-step dbt-ol / Airflow OpenLineage setup |
| Set up lineage queries | Provide sample GET_LINEAGE queries for RCA and impact analysis |
| Generate PDF report | Ensure `reportlab` is installed (`pip install reportlab`). Query `SELECT CURRENT_ACCOUNT_NAME()` to get the account name. Run the PDF generation script from [../templates/observability-maturity-score/generate_report_pdf.py](../templates/observability-maturity-score/generate_report_pdf.py), substituting the actual assessment data including the account name. Output file: `~/observability_maturity_report_<ACCOUNT_NAME>.pdf`. Inform the user of the file path. |
| Re-run assessment | Return to Step 2 |

### Step 6: Re-run and Compare (Optional)

If the user acted on recommendations and wants to re-assess, re-run Step 2 and present a before/after comparison:

```
╔══════════════════════════════════════════════════════╗
║      DATA OBSERVABILITY — PROGRESS                    ║
║      Previous: X / 5  →  Current: Y / 5               ║
╚══════════════════════════════════════════════════════╝

PILLAR CHANGES
───────────────────────────────────────────────────────
│ Pillar              │ Before │ After │ Change        │
├─────────────────────┼────────┼───────┼───────────────┤
│ Quality Monitoring  │ ❌     │ ✅    │ +DMFs added   │
│ BI Coverage         │ ❌     │ ❌    │ No change     │
│ External Lineage    │ ❌     │ ✅    │ +dbt lineage  │
│ Lineage Usage       │ ✅     │ ✅    │ No change     │
───────────────────────────────────────────────────────

NEXT STEPS
[Remaining recommendations to reach next score level]
```

## Stopping Points

- ✋ **Step 1**: Validate role, then present the four-pillar intro and wait for user to confirm before running queries
- ✋ **Step 3**: Present full report before recommendations
- ✋ **Step 4**: Ask which recommendation to act on, and whether they want a PDF export

## Output

- Maturity score (0–5) with state label (Unmonitored / Basic / Emerging / Developing / Advanced / Mature)
- Pillar summary table (Quality Monitoring / BI Coverage / External Lineage / Lineage Usage status)
- DMF coverage by database table for all popular databases
- External lineage status table (dbt, Airflow, Other)
- Gap list identifying specific unmonitored databases, missing lineage integrations, and unused lineage functions
- Prioritized recommendations to reach the next score level
- Before/after comparison if re-running after remediation

## Expected Outcomes

1. **Full Assessment**: User receives score and acts on recommendations
2. **Awareness Only**: User reviews score and plans to act later
3. **Immediate Action**: User picks a recommendation and we route to the appropriate skill
4. **Already Mature**: User scores 5, we confirm and suggest ongoing monitoring
5. **PDF Export**: User requests a PDF and receives the report at `~/observability_maturity_report_<ACCOUNT_NAME>.pdf`

## SQL Templates

Located in `../templates/observability-maturity-score/` (relative to this file in `workflows/`):

1. **[check-popular-databases.sql](../templates/observability-maturity-score/check-popular-databases.sql)** — Identify most-used databases by query volume
2. **[check-dmf-coverage.sql](../templates/observability-maturity-score/check-dmf-coverage.sql)** — Assess DMF attachment and measurement coverage
3. **[check-bi-tool-usage.sql](../templates/observability-maturity-score/check-bi-tool-usage.sql)** — Detect BI tool queries and check quality monitoring on consumed objects
4. **[check-external-lineage.sql](../templates/observability-maturity-score/check-external-lineage.sql)** — Check for external lineage integration (dbt, Airflow, OpenLineage)
5. **[check-lineage-usage.sql](../templates/observability-maturity-score/check-lineage-usage.sql)** — Check GET_LINEAGE and OBJECT_DEPENDENCIES query frequency

## PDF Generation

6. **[generate_report_pdf.py](../templates/observability-maturity-score/generate_report_pdf.py)** — Python script (requires `reportlab`) to render the observability maturity report as a formatted PDF. Substitute the placeholder data in the script with the actual assessment findings before running. Requires `ACCOUNT_NAME` (from `SELECT CURRENT_ACCOUNT_NAME()`). Output: `~/observability_maturity_report_<ACCOUNT_NAME>.pdf`
