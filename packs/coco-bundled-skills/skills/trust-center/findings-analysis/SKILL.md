---
name: trust-center-findings-analysis
description: "Analyze Trust Center security findings in Snowflake. Use when users ask about: new findings, finding counts, severity distribution, scanner results, resolved findings, scanner frequency optimization, security categories, or want to understand their Trust Center findings."
---

# Trust Center Findings Analysis

Helps users understand and analyze security findings detected by Trust Center scanners in their Snowflake account.

## When to Use

- User asks about Trust Center findings or security issues
- User wants to know how many new findings were detected recently
- User asks about severity distribution of findings
- User wants to filter findings by scanner or time period
- User asks "what security issues do I have?"
- User asks about resolved findings or security improvements
- User wants to know which scanners run too frequently or not often enough
- User wants to categorize findings by security domain
- User asks about the security posture trends

## When NOT to Use

- User wants to configure Trust Center scanners (use api-management skill)
- User wants to remediate/fix specific findings (use finding-remediation skill)
- User wants to enable/disable scanners or change schedules/notifications (use api-management skill)

## Prerequisites

**MANDATORY: Load** [references/trust-center-api.md](../references/trust-center-api.md) — contains all Trust Center views, columns, stored procedures, and scanner mappings.

**Key data sources for this skill:**
- `snowflake.trust_center.findings` — current finding details, entity-level drill-downs
- `snowflake.trust_center.time_series_daily_findings` — pre-aggregated daily snapshots for trend analysis (queries can be slow — warn the user)

See the reference for full column details, finding types, finding states, and AT_RISK_ENTITIES structure. Every scanner run creates a finding record even if no issues are detected (`TOTAL_AT_RISK_COUNT = 0`), which allows analyzing scanner run frequency.

## Workflow

### Step 1: Understand User Intent

Determine what the user wants to know:

1. **Count of new findings** - How many findings in last N days? (default: 7 days)
2. **Severity distribution** - Breakdown by Critical/High/Medium/Low
3. **Scanner breakdown** - Which scanners are detecting issues?
4. **Finding details** - Specific findings and remediation guidance
5. **Category analysis** - Group findings by security domain (derived from scanner descriptions)
6. **Resolved findings** - Which findings were resolved, security improvements
7. **Scanner frequency - too often** - Scanners running frequently with no findings
8. **Scanner frequency - not enough** - Critical scanners that should run more often
9. **Trend analysis** - How are findings trending over time? Is security posture improving or degrading?

**Ask if unclear:**
```
What would you like to know about your Trust Center findings?
1. Count of new findings (specify time period)
2. Severity distribution
3. Findings by scanner
4. Findings by category/security domain
5. Resolved findings and improvements
6. Scanner frequency optimization
7. Trend analysis (findings over time)
8. All of the above
```

### Step 2: Query Findings

Based on user intent, run the appropriate query. **Default time period is 7 days** unless the user specifies otherwise.

**New findings in last N days with severity distribution (default N=7):**

```sql
SELECT 
    SEVERITY,
    COUNT(*) AS finding_count
FROM snowflake.trust_center.findings
WHERE CREATED_ON >= DATEADD('day', -7, CURRENT_TIMESTAMP())  -- default 7 days; adjust per user request
  AND (STATE IS NULL OR UPPER(STATE) = 'OPEN')
GROUP BY SEVERITY
ORDER BY 
    CASE UPPER(SEVERITY) 
        WHEN 'CRITICAL' THEN 1 
        WHEN 'HIGH' THEN 2 
        WHEN 'MEDIUM' THEN 3 
        WHEN 'LOW' THEN 4 
        ELSE 5 
    END;
```

**Total count of new findings:**

```sql
SELECT COUNT(*) AS total_new_findings
FROM snowflake.trust_center.findings
WHERE CREATED_ON >= DATEADD('day', -7, CURRENT_TIMESTAMP())  -- default 7 days
  AND (STATE IS NULL OR UPPER(STATE) = 'OPEN');
```

**Findings by scanner (most recent per finding only):**

```sql
WITH latest_findings AS (
    SELECT 
        SCANNER_PACKAGE_NAME,
        SCANNER_NAME,
        SCANNER_TYPE,
        SEVERITY
    FROM snowflake.trust_center.findings
    WHERE CREATED_ON >= DATEADD('day', -7, CURRENT_TIMESTAMP())  -- default 7 days
      AND (STATE IS NULL OR UPPER(STATE) = 'OPEN')
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY FINDING_IDENTIFIER, SCANNER_NAME
        ORDER BY CREATED_ON DESC
    ) = 1
)
SELECT 
    SCANNER_PACKAGE_NAME,
    SCANNER_NAME,
    SCANNER_TYPE,
    SEVERITY,
    COUNT(*) AS finding_count
FROM latest_findings
GROUP BY SCANNER_PACKAGE_NAME, SCANNER_NAME, SCANNER_TYPE, SEVERITY
ORDER BY SCANNER_PACKAGE_NAME, SCANNER_NAME, 
    CASE UPPER(SEVERITY) 
        WHEN 'CRITICAL' THEN 1 
        WHEN 'HIGH' THEN 2 
        WHEN 'MEDIUM' THEN 3 
        WHEN 'LOW' THEN 4 
        ELSE 5 
    END;
```

**Detailed findings (for drilling down):**

```sql
SELECT 
    FINDING_IDENTIFIER,
    SCANNER_PACKAGE_NAME,
    SCANNER_NAME,
    SCANNER_TYPE,
    SEVERITY,
    SUGGESTED_ACTION,
    TOTAL_AT_RISK_COUNT,
    CREATED_ON
FROM snowflake.trust_center.findings
WHERE CREATED_ON >= DATEADD('day', -7, CURRENT_TIMESTAMP())  -- default 7 days
  AND (STATE IS NULL OR UPPER(STATE) = 'OPEN')
  -- AND UPPER(SEVERITY) = '<SEVERITY_FILTER>'  -- Optional: uncomment to filter by severity
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY FINDING_IDENTIFIER, SCANNER_NAME
    ORDER BY CREATED_ON DESC
) = 1
ORDER BY 
    CASE UPPER(SEVERITY) 
        WHEN 'CRITICAL' THEN 1 
        WHEN 'HIGH' THEN 2 
        WHEN 'MEDIUM' THEN 3 
        WHEN 'LOW' THEN 4 
        ELSE 5 
    END,
    TOTAL_AT_RISK_COUNT DESC
LIMIT 50;
```

**Findings by category (derived from scanner descriptions):**

```sql
-- First, get distinct scanners with their descriptions
SELECT 
    SCANNER_PACKAGE_ID,
    SCANNER_PACKAGE_NAME,
    SCANNER_ID,
    SCANNER_NAME,
    SCANNER_SHORT_DESCRIPTION,
    SCANNER_DESCRIPTION,
    COUNT(*) AS finding_count,
    SUM(CASE WHEN UPPER(SEVERITY) = 'CRITICAL' THEN 1 ELSE 0 END) AS critical_count,
    SUM(CASE WHEN UPPER(SEVERITY) = 'HIGH' THEN 1 ELSE 0 END) AS high_count
FROM snowflake.trust_center.findings
WHERE (STATE IS NULL OR UPPER(STATE) = 'OPEN')
  AND TOTAL_AT_RISK_COUNT > 0
GROUP BY SCANNER_PACKAGE_ID, SCANNER_PACKAGE_NAME, SCANNER_ID, SCANNER_NAME, SCANNER_SHORT_DESCRIPTION, SCANNER_DESCRIPTION
ORDER BY critical_count DESC, high_count DESC, finding_count DESC;
```

After running this query, analyze the `SCANNER_DESCRIPTION` and `SCANNER_SHORT_DESCRIPTION` columns to categorize scanners into security domains. The list below is not exhaustive; derive domains from the actual scanner descriptions. Example domains:
- **Access Control** - Authentication, authorization, privileges
- **Network Security** - Network policies, connectivity
- **Data Protection** - Encryption, masking, data access
- **Compliance** - Regulatory requirements, audit
- **Configuration** - Settings, best practices

**Resolved findings (recently resolved):**

```sql
SELECT 
    SCANNER_PACKAGE_ID,
    SCANNER_PACKAGE_NAME,
    SCANNER_ID,
    SCANNER_NAME,
    SEVERITY,
    FINDING_IDENTIFIER,
    CREATED_ON,
    STATE,
    STATE_LAST_MODIFIED_ON
FROM snowflake.trust_center.findings
WHERE UPPER(STATE) = 'RESOLVED'
  AND STATE_LAST_MODIFIED_ON >= DATEADD('day', -7, CURRENT_TIMESTAMP())  -- default 7 days
ORDER BY STATE_LAST_MODIFIED_ON DESC
LIMIT 50;
```

**Scanners that stopped detecting issues (improvement analysis):**

```sql
-- Scanners with resolved findings but no recent active findings
WITH resolved_scanners AS (
    SELECT DISTINCT 
        SCANNER_PACKAGE_ID,
        SCANNER_PACKAGE_NAME,
        SCANNER_ID,
        SCANNER_NAME
    FROM snowflake.trust_center.findings
    WHERE UPPER(STATE) = 'RESOLVED'
      AND STATE_LAST_MODIFIED_ON >= DATEADD('day', -30, CURRENT_TIMESTAMP())
),
active_scanners AS (
    SELECT DISTINCT SCANNER_ID
    FROM snowflake.trust_center.findings
    WHERE (STATE IS NULL OR UPPER(STATE) = 'OPEN')
      AND TOTAL_AT_RISK_COUNT > 0
      AND CREATED_ON >= DATEADD('day', -30, CURRENT_TIMESTAMP())
)
SELECT 
    r.SCANNER_PACKAGE_ID,
    r.SCANNER_PACKAGE_NAME,
    r.SCANNER_ID,
    r.SCANNER_NAME,
    'Improved - no recent active findings' AS status
FROM resolved_scanners r
LEFT JOIN active_scanners a ON r.SCANNER_ID = a.SCANNER_ID
WHERE a.SCANNER_ID IS NULL;
```

**Scanners running TOO FREQUENTLY (wasting resources):**

```sql
-- Scanners that run frequently but consistently find nothing
WITH scanner_runs AS (
    SELECT 
        SCANNER_PACKAGE_ID,
        SCANNER_PACKAGE_NAME,
        SCANNER_ID,
        SCANNER_NAME,
        COUNT(*) AS run_count,
        COUNT(CASE WHEN TOTAL_AT_RISK_COUNT > 0 THEN 1 END) AS runs_with_findings,
        MIN(START_TIMESTAMP) AS first_run,
        MAX(START_TIMESTAMP) AS last_run,
        DATEDIFF('day', MIN(START_TIMESTAMP), MAX(START_TIMESTAMP)) AS days_span
    FROM snowflake.trust_center.findings
    WHERE START_TIMESTAMP >= DATEADD('day', -30, CURRENT_TIMESTAMP())
    GROUP BY SCANNER_PACKAGE_ID, SCANNER_PACKAGE_NAME, SCANNER_ID, SCANNER_NAME
)
SELECT 
    SCANNER_PACKAGE_ID,
    SCANNER_PACKAGE_NAME,
    SCANNER_ID,
    SCANNER_NAME,
    run_count,
    runs_with_findings,
    ROUND(run_count / NULLIF(days_span, 0), 2) AS runs_per_day,
    CASE 
        WHEN runs_with_findings = 0 THEN 'No findings in 30 days'
        ELSE ROUND(100.0 * runs_with_findings / run_count, 1) || '% runs have findings'
    END AS effectiveness
FROM scanner_runs
WHERE run_count >= 7  -- Runs at least weekly
  AND runs_with_findings = 0  -- Never finds anything
ORDER BY run_count DESC;
```

**Scanners that SHOULD RUN MORE FREQUENTLY:**

```sql
-- Scanners finding Critical/High issues but running infrequently
WITH scanner_activity AS (
    SELECT 
        SCANNER_PACKAGE_ID,
        SCANNER_PACKAGE_NAME,
        SCANNER_ID,
        SCANNER_NAME,
        COUNT(*) AS total_runs,
        COUNT(CASE WHEN UPPER(SEVERITY) IN ('CRITICAL', 'HIGH') AND TOTAL_AT_RISK_COUNT > 0 THEN 1 END) AS critical_high_findings,
        MAX(START_TIMESTAMP) AS last_run,
        DATEDIFF('day', MAX(START_TIMESTAMP), CURRENT_TIMESTAMP()) AS days_since_last_run
    FROM snowflake.trust_center.findings
    WHERE START_TIMESTAMP >= DATEADD('day', -90, CURRENT_TIMESTAMP())
    GROUP BY SCANNER_PACKAGE_ID, SCANNER_PACKAGE_NAME, SCANNER_ID, SCANNER_NAME
)
SELECT 
    SCANNER_PACKAGE_ID,
    SCANNER_PACKAGE_NAME,
    SCANNER_ID,
    SCANNER_NAME,
    critical_high_findings,
    total_runs,
    last_run,
    days_since_last_run,
    CASE 
        WHEN days_since_last_run > 30 THEN 'Has not run in over a month'
        WHEN total_runs < 3 THEN 'Runs less than monthly'
        ELSE 'Review frequency'
    END AS recommendation
FROM scanner_activity
WHERE critical_high_findings > 0  -- Finds important issues
  AND (days_since_last_run > 30 OR total_runs < 3)  -- But runs infrequently
ORDER BY critical_high_findings DESC, days_since_last_run DESC;
```

**Daily findings trend (security posture over time):**
Show user two kinds of trends, Vulnerability/Violation and Alerts/Detections
Use the `time_series_daily_findings` view for pre-aggregated daily data:

```sql
SELECT
    DAY_PARTITION,
    SCANNER_TYPE,
    SUM(CRITICAL_RISK_COUNT) AS critical,
    SUM(HIGH_RISK_COUNT) AS high,
    SUM(MEDIUM_RISK_COUNT) AS medium,
    SUM(LOW_RISK_COUNT) AS low,
    SUM(NONE_RISK_COUNT) AS compliant
FROM snowflake.trust_center.time_series_daily_findings
WHERE UPPER(COMPLETION_STATUS) = 'SUCCEEDED'
  AND UPPER(SCANNER_TYPE) IN ('VULNERABILITY', 'DETECTION')
  AND DAY_PARTITION >= DATEADD('day', -7, CURRENT_TIMESTAMP())  -- default 7 days
GROUP BY DAY_PARTITION, SCANNER_TYPE
ORDER BY DAY_PARTITION DESC;
```


**Daily findings trend by scanner package:**

```sql
SELECT
    DAY_PARTITION,
    SCANNER_PACKAGE_NAME,
    SUM(CRITICAL_RISK_COUNT) AS critical,
    SUM(HIGH_RISK_COUNT) AS high,
    SUM(MEDIUM_RISK_COUNT) AS medium,
    SUM(LOW_RISK_COUNT) AS low
FROM snowflake.trust_center.time_series_daily_findings
WHERE UPPER(COMPLETION_STATUS) = 'SUCCEEDED'
  AND DAY_PARTITION >= DATEADD('day', -7, CURRENT_TIMESTAMP())  -- default 7 days
GROUP BY DAY_PARTITION, SCANNER_PACKAGE_NAME
ORDER BY DAY_PARTITION DESC, SCANNER_PACKAGE_NAME;
```

**Week-over-week comparison:**

```sql
WITH weekly AS (
    SELECT
        DATE_TRUNC('week', DAY_PARTITION::DATE) AS week_start,
        SUM(CRITICAL_RISK_COUNT + HIGH_RISK_COUNT) AS critical_high,
        SUM(MEDIUM_RISK_COUNT + LOW_RISK_COUNT) AS medium_low
    FROM snowflake.trust_center.time_series_daily_findings
    WHERE UPPER(COMPLETION_STATUS) = 'SUCCEEDED'
    GROUP BY week_start
)
SELECT
    week_start,
    critical_high,
    medium_low,
    critical_high - LAG(critical_high) OVER (ORDER BY week_start) AS critical_high_change,
    medium_low - LAG(medium_low) OVER (ORDER BY week_start) AS medium_low_change
FROM weekly
ORDER BY week_start DESC
LIMIT 8;  -- last 8 weeks
```

### Step 3: Present Results and Insights

Present query results as tables, then add a brief analytical summary. The goal is insight, not just data.

**For findings summaries:** Lead with total count and severity table. Call out anything notable (e.g., "2 Critical findings need immediate attention" or "all findings are Medium/Low — no urgent action needed").

**For category analysis:** Group scanners into security domains derived from their descriptions (Access Control, Network Security, Data Protection, Compliance, Configuration, etc.). Highlight which category has the most Critical/High findings.

**For resolved findings:** Summarize improvements (e.g., "12 findings resolved this week. MFA and Password Policy scanners now report clean."). Highlight scanners that went from findings to clean.

**For scanner frequency analysis:** Flag scanners that run frequently with zero findings (candidates to reduce frequency) and scanners with Critical/High findings that run infrequently (candidates to increase). Include a concrete recommendation per scanner.

**For trend analysis:** Show the data table, then summarize the direction in 1–2 sentences (e.g., "Critical+High findings dropped from 9 to 7 over the past 3 weeks — posture is improving."). Do not narrate each row.

**General formatting rules:**
- Do not repeat information the user can already see in the table.
- Do not add speculative caveats or "common issues" lists.

### Step 4: Offer Next Steps

After presenting results, suggest 1–2 natural follow-ups in a single sentence (e.g., "Want to drill into the Critical findings or get remediation guidance?"). Do not present a numbered menu unless the user's next intent is genuinely unclear.

**⚠️ STOP**: Wait for user to indicate next action.

## Stopping Points

- ✋ Step 1: If user intent is unclear, ask for clarification
- ✋ Step 4: After presenting any analysis, wait for user's next action

## Output

- Summary of findings count and severity distribution
- Optional: Detailed breakdown by scanner
- Optional: Findings grouped by security category
- Optional: Resolved findings and security improvements
- Optional: Scanner frequency optimization recommendations
- Optional: Specific finding details with remediation guidance
- Optional: Findings trend over time (daily/weekly) with posture assessment

## Troubleshooting

**No results returned:**
- The account may have no Trust Center findings
- Trust Center scanners may not be enabled
- Check if the view is accessible: `DESCRIBE VIEW snowflake.trust_center.findings;`

**Permission denied:**
- User needs `trust_center_admin` or `trust_center_viewer` application role to view findings
