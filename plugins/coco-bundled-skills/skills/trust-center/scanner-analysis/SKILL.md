---
name: trust-center-scanner-analysis
description: "Analyze Trust Center scanners and scanner packages in Snowflake. Use when users ask about: scanners, scanner packages, scanner coverage, disabled scanners, scanner schedules, scanner categories, CIS benchmarks, Security Essentials, Threat Intelligence, AI Security, or want to understand their Trust Center scanner configuration."
---

# Trust Center Scanner Analysis

Helps users understand, categorize, and optimize the Trust Center scanners configured in their Snowflake account.

## When to Use

- User asks about Trust Center scanners or scanner packages
- User wants to know which scanners are enabled or disabled
- User asks about scanner schedules or frequency
- User wants to categorize scanners by security domain
- User asks "what scanners do I have?" or "what security checks are running?"
- User wants to identify gaps in scanner coverage
- User asks about CIS Benchmarks, Security Essentials, Threat Intelligence, or AI Security
- User wants to optimize scanner schedules or notifications

## When NOT to Use

- User asks about specific findings from scanners (use findings-analysis skill)
- User wants to enable/disable scanners or change schedules/notifications (use api-management skill)

## Prerequisites

**MANDATORY: Load** [references/trust-center-api.md](../references/trust-center-api.md) — contains all Trust Center views, columns, stored procedures, and scanner mappings.

**Key data sources for this skill:**
- `snowflake.trust_center.scanners` — metadata about each installed scanner
- `snowflake.trust_center.scanner_packages` — metadata about each installed scanner package

See the reference for full column details, scanner execution types, required roles, and the first-party scanner ID mapping.

## Workflow

### Step 1: Understand User Intent

Determine what the user wants to know:

1. **Scanner inventory** - What scanners exist and their status?
2. **Category analysis** - Group scanners by security domain
3. **Disabled scanner review** - Important scanners that aren't enabled
4. **Frequency analysis** - Scanners that run too infrequently
5. **Coverage gap analysis** - Security domains with no scanner coverage
6. **Notification recipients audit** - Scanners without notification recipients
7. **Scanner health check** - Enabled scanners that haven't run recently

**Ask if unclear:**
```
What would you like to know about your Trust Center scanners?
1. Scanner inventory and status overview
2. Categorize scanners by security domain
3. Find important scanners that aren't enabled
4. Find scanners that run too infrequently
5. Identify coverage gaps
6. Audit notification recipients
7. Scanner health check (enabled but not running)
8. All of the above
```

### Step 2: Query Scanner Data

Based on user intent, run the appropriate query.

**Full scanner inventory with package info:**

```sql
SELECT
    s.NAME,
    s.ID,
    s.SHORT_DESCRIPTION,
    s.DESCRIPTION,
    s.SCANNER_PACKAGE_ID,
    sp.NAME AS PACKAGE_NAME,
    s.STATE,
    s.SCHEDULE,
    s.NOTIFICATION,
    s.LAST_SCAN_TIMESTAMP
FROM snowflake.trust_center.scanners s
LEFT JOIN snowflake.trust_center.scanner_packages sp
    ON s.SCANNER_PACKAGE_ID = sp.ID
ORDER BY sp.NAME, s.NAME;
```

**Scanner status summary by package:**

```sql
SELECT
    sp.NAME AS PACKAGE_NAME,
    s.STATE AS SCANNER_STATE,
    s.SCHEDULE AS SCANNER_SCHEDULE,
    COUNT(*) AS scanner_count
FROM snowflake.trust_center.scanners s
LEFT JOIN snowflake.trust_center.scanner_packages sp
    ON s.SCANNER_PACKAGE_ID = sp.ID
GROUP BY ALL
ORDER BY 1,2,3;
```

**Disabled scanners (candidates to enable):**

```sql
SELECT
    s.NAME,
    s.ID,
    s.SHORT_DESCRIPTION,
    s.DESCRIPTION,
    sp.NAME AS PACKAGE_NAME,
    sp.STATE AS PACKAGE_STATE
FROM snowflake.trust_center.scanners s
LEFT JOIN snowflake.trust_center.scanner_packages sp
    ON s.SCANNER_PACKAGE_ID = sp.ID
WHERE (s.STATE IS NULL OR UPPER(s.STATE) != 'TRUE') -- scanner state can be TRUE/FALSE/null, only TRUE indicates scanner enabled
ORDER BY sp.NAME, s.NAME;
```

When presenting disabled scanners, **always show the parent package state** so users know if the package must be enabled first. Group results by package state:

- **Package enabled (TRUE):** These scanners can be enabled directly.
- **Package disabled (FALSE/NULL):** The parent package must be enabled first before these scanners can be enabled.

**Scheduled scanners that ran too infrequently (last scan older than 30 days):**

```sql
SELECT
    s.NAME,
    s.ID,
    s.SHORT_DESCRIPTION,
    sp.NAME AS PACKAGE_NAME,
    s.STATE,
    s.SCHEDULE,
    s.LAST_SCAN_TIMESTAMP,
    DATEDIFF('day', s.LAST_SCAN_TIMESTAMP, CURRENT_TIMESTAMP()) AS days_since_last_scan
FROM snowflake.trust_center.scanners s
LEFT JOIN snowflake.trust_center.scanner_packages sp
    ON s.SCANNER_PACKAGE_ID = sp.ID
WHERE UPPER(s.STATE) = 'TRUE'
  AND s.SCHEDULE IS NOT NULL        -- Exclude event-driven scanners
  AND s.LAST_SCAN_TIMESTAMP IS NOT NULL
  AND DATEDIFF('day', s.LAST_SCAN_TIMESTAMP, CURRENT_TIMESTAMP()) > 30
ORDER BY days_since_last_scan DESC;
```

**Enabled scheduled scanners that have NEVER run (potential health issue):**

```sql
SELECT
    s.NAME,
    s.ID,
    s.SHORT_DESCRIPTION,
    sp.NAME AS PACKAGE_NAME,
    s.STATE,
    s.SCHEDULE
FROM snowflake.trust_center.scanners s
LEFT JOIN snowflake.trust_center.scanner_packages sp
    ON s.SCANNER_PACKAGE_ID = sp.ID
WHERE UPPER(s.STATE) = 'TRUE'
  AND s.SCHEDULE IS NOT NULL        -- Exclude event-driven scanners (NULL schedule + NULL last_scan is normal)
  AND s.LAST_SCAN_TIMESTAMP IS NULL
ORDER BY sp.NAME, s.NAME;
```

**Enabled scanners without notification recipients configured:**

A notification has recipients if it notifies admins OR specifies custom users:
- **Notify admins:** `{"NOTIFY_ADMINS":"TRUE","SEVERITY_THRESHOLD":"CRITICAL","USERS":[]}`
- **Notify custom users:** `{"NOTIFY_ADMINS":"FALSE","SEVERITY_THRESHOLD":"MEDIUM","USERS":["\"snow@flake.com\"","SNOWFLAKE","ADMIN_ABC"]}`

A notification has NO recipients if it is NULL, empty `{}`, or has `NOTIFY_ADMINS=FALSE` with an empty `USERS` array.

```sql
SELECT
    s.NAME,
    s.ID,
    s.SHORT_DESCRIPTION,
    sp.NAME AS PACKAGE_NAME,
    s.STATE,
    s.NOTIFICATION
FROM snowflake.trust_center.scanners s
LEFT JOIN snowflake.trust_center.scanner_packages sp
    ON s.SCANNER_PACKAGE_ID = sp.ID
WHERE UPPER(s.STATE) = 'TRUE'
  AND (
    s.NOTIFICATION IS NULL
    OR s.NOTIFICATION = '{}'
    OR (
      UPPER(PARSE_JSON(s.NOTIFICATION):NOTIFY_ADMINS::STRING) = 'FALSE'
      AND ARRAY_SIZE(PARSE_JSON(s.NOTIFICATION):USERS) = 0
    )
  )
ORDER BY sp.NAME, s.NAME;
```

**All scanner descriptions for categorization:**

```sql
SELECT
    s.NAME,
    s.ID,
    s.SHORT_DESCRIPTION,
    s.DESCRIPTION,
    sp.NAME AS PACKAGE_NAME,
    s.STATE
FROM snowflake.trust_center.scanners s
LEFT JOIN snowflake.trust_center.scanner_packages sp
    ON s.SCANNER_PACKAGE_ID = sp.ID
ORDER BY sp.NAME, s.NAME;
```

After running the query above, use the `DESCRIPTION` and `SHORT_DESCRIPTION` text to classify each scanner into security domains. This is an LLM classification task — read the description and assign the most appropriate domain. The list below is not exhaustive; derive domains from the actual scanner descriptions. Example domains:
- **Network Security** - Network policies, IP allow-lists, connectivity restrictions
- **Identity & Access Management** - Authentication, MFA, passwords, roles, privileges
- **Data Protection** - Encryption, masking, data sharing, data access controls
- **Configuration Management** - Account settings, parameters, best practices
- **Monitoring & Logging** - Audit logging, activity monitoring, alerting
- **Compliance** - Regulatory requirements, CIS benchmark adherence

Present the categorization as a table grouped by domain, noting which scanners are enabled vs disabled in each category.

### Step 3: Present Results

Format results based on the analysis type.

**Example: Scanner Inventory**

```
## Trust Center Scanner Overview

### Scanner Packages
| Package | Total Scanners | TRUE (enabled) | FALSE (disabled) | Default Schedule |
|---------|---------------|----------------|------------------|-----------------|
| Security Essentials | 5 | 5 | 0 | Monthly |
| CIS Benchmarks | 30 | 27 | 3 | Daily |
| Threat Intelligence | 10 | 8 | 2 | Varies (scheduled/event-driven) |

### Summary
- **Total scanners:** 45
- **Enabled (TRUE):** 40 (89%)
- **Disabled (FALSE):** 5 (11%)
```

**Example: Category Analysis**

```
## Scanners by Security Domain

### Network Security (8 scanners)
| Scanner | Package | Type | State | Last Scan |
|---------|---------|------|-------|-----------|
| 3.1 Account-level network policy | CIS Benchmarks | Violation | TRUE | 3 days ago |
| 3.1 Account-level network policy | Security Essentials | Violation | TRUE | 24 days ago |
| ... | ... | ... | ... | ... |

### Identity & Access Management (15 scanners)
| Scanner | Package | Type | State | Last Scan |
|---------|---------|------|-------|-----------|
| 1.4 MFA for human users | Security Essentials | Violation | TRUE | 24 days ago |
| 1.5 Minimum password length | CIS Benchmarks | Violation | FALSE | 31 days ago |
| Dormant User Login | Threat Intelligence | Detection | TRUE | event-driven |
| ... | ... | ... | ... | ... |

### Coverage Summary
| Domain | Total | Enabled (TRUE) | Violations | Detections | Gap? |
|--------|-------|----------------|------------|------------|------|
| Network Security | 8 | 6 | 7 | 1 | No |
| Identity & Access Management | 15 | 13 | 10 | 5 | Partial |
| Data Protection | 5 | 5 | 5 | 0 | No |
| Monitoring & Logging | 3 | 1 | 1 | 2 | Yes - review |
```

**Example: Disabled Scanner Review**

```
## Important Disabled Scanners

These scanners are currently disabled but may provide valuable security coverage:

### Package Enabled — Can enable these scanners directly
| Scanner | Package | Type | What It Checks |
|---------|---------|------|---------------|
| MFA Policy Scanner | CIS Benchmarks | Violation | Ensures MFA is enforced for all users |
| Network Policy Scanner | CIS Benchmarks | Violation | Validates network access restrictions |

### Package Disabled — Must enable package first
| Scanner | Package | Type | What It Checks |
|---------|---------|------|---------------|
| ACCOUNTADMIN grants | Roles | Detection | Detects grants of full admin access |
| Stale users | Secrets & Privileged Access | Violation | Detects inactive user accounts |

⚠️ Scanners in the "Package Disabled" group require their parent package
to be enabled first. Enabling a package is free, but once enabled, its
scanners will run periodically on their default schedule — each scanner
run incurs credit costs.

Note: All scanners are pre-installed for free. Enabling them incurs credit
costs per scan run. Security Essentials' default monthly run is free (covered
by Snowflake), but ad-hoc runs incur credits. CIS Benchmark and Threat
Intelligence scanner runs always consume credits.
```

**Example: Scanner Health Check**

```
## Scanner Health Check

### Scheduled Scanners That Haven't Run Recently (STATE=TRUE)
| Scanner | Package | Type | Days Since Last Scan | Schedule |
|---------|---------|------|---------------------|----------|
| 4.9 Tri-Secret Secure | CIS Benchmarks | Violation | 80 | Weekly |
| 1.5 Minimum password length | CIS Benchmarks | Violation | 31 | Weekly |

### Scheduled Scanners That Have Never Run (STATE=TRUE)
| Scanner | Package | Type | Schedule |
|---------|---------|------|----------|
| 1.18 PAT network policy | CIS Benchmarks | Violation | Weekly |

### Event-Driven Scanners (no schedule — this is normal)
| Scanner | Package | Type | State |
|---------|---------|------|-------|
| Sensitive Parameter Protection | Threat Intelligence | Detection | TRUE |
| Dormant User Login | Threat Intelligence | Detection | TRUE |
| Authentication Policy Changes | Threat Intelligence | Detection | TRUE |

Note: Event-driven scanners have no schedule and no LAST_SCAN_TIMESTAMP.
They trigger on relevant account events. This is expected behavior.

Recommendation: Investigate why scheduled scanners above are not executing
as configured.
```

### Step 4: Offer Next Steps

After presenting the analysis, offer actionable next steps:

**After scanner inventory:**
```
Would you like to:
1. Categorize scanners by security domain?
2. Review disabled scanners that should be enabled?
3. Check scanner health and run frequency?
4. Audit notification recipients?
```

**After category analysis:**
```
Would you like to:
1. See recommendations for coverage gaps?
2. Review disabled scanners in a specific category?
3. Analyze scanner run frequency?
```

**After disabled scanner review:**
```
Would you like to:
1. Understand the cost implications of enabling more scanners?
2. See which security domains would benefit most from enabling scanners?
3. Check the findings from currently enabled scanners?
```

**After scanner health check:**
```
Would you like to:
1. Investigate specific scanners that aren't running?
2. Review scanner schedule configuration?
3. Check if scanners without notifications should have them?
```

**STOP**: Wait for user to indicate next action.

## Stopping Points

- Step 1: If user intent is unclear, ask for clarification
- Step 4: After presenting any analysis, wait for user's next action

## Output

- Summary of scanner packages and their status
- Optional: Scanner categorization by security domain
- Optional: List of important disabled scanners with recommendations
- Optional: Scanners running too infrequently with schedule recommendations
- Optional: Coverage gap analysis across security domains
- Optional: Notification recipients audit results
- Optional: Scanner health check (enabled but not running)

## Troubleshooting

**No results returned:**
- Trust Center may not be enabled on the account
- Check if the view is accessible: `DESCRIBE VIEW snowflake.trust_center.scanners;`

**Permission denied:**
- User needs `trust_center_admin` or `trust_center_viewer` application role to view scanners and scanner packages

**Scanner shows STATE=TRUE but LAST_SCAN_TIMESTAMP is NULL:**
- If `SCHEDULE` is also NULL: this is an **event-driven scanner** — no schedule and no last scan is normal. It triggers on relevant account events.
- If `SCHEDULE` has a value: the scanner was recently enabled and hasn't had its first scheduled run yet. Check the cron schedule to determine when the next run is expected.
