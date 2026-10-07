---
name: login-ip-anomaly
description: "Detect IP address anomalies in Snowflake LOGIN_HISTORY. Use when: login anomalies, suspicious IPs, brute force detection, impossible travel, IP sharing, failed login analysis, security audit of logins. Supports both ACCOUNT_USAGE and ORGANIZATION_USAGE."
---

# Login IP Anomaly Detection

## When to Use
- Detect suspicious login patterns
- Find brute force attempts
- Identify impossible travel (rapid IP changes)
- Audit failed logins
- Find shared IPs across users

## Workflow

### Step 1: Select Detection Scope

**Ask user (Question 1 - Timeframe):**
```
What timeframe should I analyze?
1. Last 24 hours
2. Last 7 days
3. Last 30 days
4. Custom date range
```

**Ask user (Question 2 - Scope):**
```
What scope should I analyze?
1. ACCOUNT_USAGE (current account only)
2. ORGANIZATION_USAGE (all accounts in organization - requires ORGADMIN)
```

**⚠️ STOP**: Wait for user response.

**Requirements:**
- ACCOUNT_USAGE: Requires `IMPORTED PRIVILEGES` on SNOWFLAKE database
- ORGANIZATION_USAGE: Requires `ORGADMIN` role or `USAGE` on `SNOWFLAKE.ORGANIZATION_USAGE`

### Step 2: Run Anomaly Detection

Execute the following query, replacing:
- `{{DAYS}}` with the selected timeframe
- `{{SCHEMA}}` with either `ACCOUNT_USAGE` or `ORGANIZATION_USAGE`

**For ACCOUNT_USAGE:**

```sql
WITH user_ip_baseline AS (
  SELECT 
    user_name, client_ip,
    COUNT(*) AS login_count,
    MIN(event_timestamp) AS first_seen,
    MAX(event_timestamp) AS last_seen
  FROM SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY
  WHERE event_timestamp >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
    AND client_ip != '0.0.0.0'
    AND NOT client_ip LIKE '10.%'
  GROUP BY user_name, client_ip
),

recent_logins AS (
  SELECT 
    event_timestamp, user_name, client_ip, reported_client_type,
    is_success, error_message,
    LAG(event_timestamp) OVER (PARTITION BY user_name ORDER BY event_timestamp) AS prev_login_time,
    LAG(client_ip) OVER (PARTITION BY user_name ORDER BY event_timestamp) AS prev_ip
  FROM SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY
  WHERE event_timestamp >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
    AND client_ip != '0.0.0.0'
    AND NOT client_ip LIKE '10.%'
),

anomalies AS (
  SELECT r.*,
    CASE WHEN b.client_ip IS NULL THEN TRUE ELSE FALSE END AS is_new_ip,
    CASE WHEN r.prev_ip IS NOT NULL AND r.prev_ip != r.client_ip 
         AND DATEDIFF('minute', r.prev_login_time, r.event_timestamp) < 10 
         THEN TRUE ELSE FALSE END AS is_rapid_ip_change,
    CASE WHEN r.is_success = 'NO' THEN TRUE ELSE FALSE END AS is_failed_login,
    b.login_count AS historical_login_count
  FROM recent_logins r
  LEFT JOIN user_ip_baseline b ON r.user_name = b.user_name AND r.client_ip = b.client_ip
),

ip_sharing AS (
  SELECT client_ip, COUNT(DISTINCT user_name) AS user_count
  FROM SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY
  WHERE event_timestamp >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
    AND client_ip != '0.0.0.0'
    AND NOT client_ip LIKE '10.%'
  GROUP BY client_ip HAVING COUNT(DISTINCT user_name) > 3
),

brute_force AS (
  SELECT client_ip, COUNT(*) AS failed_attempts
  FROM SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY
  WHERE event_timestamp >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP()) 
    AND is_success = 'NO'
    AND client_ip != '0.0.0.0'
    AND NOT client_ip LIKE '10.%'
  GROUP BY client_ip HAVING COUNT(*) >= 5
)

SELECT 
  a.event_timestamp, a.user_name, a.client_ip, a.is_success, a.error_message,
  a.is_new_ip, a.is_rapid_ip_change, a.is_failed_login,
  s.client_ip IS NOT NULL AS is_shared_ip,
  bf.client_ip IS NOT NULL AS is_brute_force_ip,
  (IFF(a.is_new_ip, 2, 0) + IFF(a.is_rapid_ip_change, 3, 0) + IFF(a.is_failed_login, 1, 0) +
   IFF(s.client_ip IS NOT NULL, 2, 0) + IFF(bf.client_ip IS NOT NULL, 4, 0)) AS risk_score
FROM anomalies a
LEFT JOIN ip_sharing s ON a.client_ip = s.client_ip
LEFT JOIN brute_force bf ON a.client_ip = bf.client_ip
WHERE a.is_new_ip OR a.is_rapid_ip_change OR a.is_failed_login 
   OR s.client_ip IS NOT NULL OR bf.client_ip IS NOT NULL
ORDER BY risk_score DESC, event_timestamp DESC;
```

**For ORGANIZATION_USAGE (includes account_name):**

```sql
WITH user_ip_baseline AS (
  SELECT 
    account_name, user_name, client_ip,
    COUNT(*) AS login_count,
    MIN(event_timestamp) AS first_seen,
    MAX(event_timestamp) AS last_seen
  FROM SNOWFLAKE.ORGANIZATION_USAGE.LOGIN_HISTORY
  WHERE event_timestamp >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
    AND client_ip != '0.0.0.0'
  GROUP BY account_name, user_name, client_ip
),

recent_logins AS (
  SELECT 
    account_name, event_timestamp, user_name, client_ip, reported_client_type,
    is_success, error_message,
    LAG(event_timestamp) OVER (PARTITION BY account_name, user_name ORDER BY event_timestamp) AS prev_login_time,
    LAG(client_ip) OVER (PARTITION BY account_name, user_name ORDER BY event_timestamp) AS prev_ip
  FROM SNOWFLAKE.ORGANIZATION_USAGE.LOGIN_HISTORY
  WHERE event_timestamp >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
    AND client_ip != '0.0.0.0'
),

anomalies AS (
  SELECT r.*,
    CASE WHEN b.client_ip IS NULL THEN TRUE ELSE FALSE END AS is_new_ip,
    CASE WHEN r.prev_ip IS NOT NULL AND r.prev_ip != r.client_ip 
         AND DATEDIFF('minute', r.prev_login_time, r.event_timestamp) < 10 
         THEN TRUE ELSE FALSE END AS is_rapid_ip_change,
    CASE WHEN r.is_success = 'NO' THEN TRUE ELSE FALSE END AS is_failed_login,
    b.login_count AS historical_login_count
  FROM recent_logins r
  LEFT JOIN user_ip_baseline b ON r.account_name = b.account_name AND r.user_name = b.user_name AND r.client_ip = b.client_ip
),

ip_sharing AS (
  SELECT account_name, client_ip, COUNT(DISTINCT user_name) AS user_count
  FROM SNOWFLAKE.ORGANIZATION_USAGE.LOGIN_HISTORY
  WHERE event_timestamp >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
    AND client_ip != '0.0.0.0'
  GROUP BY account_name, client_ip HAVING COUNT(DISTINCT user_name) > 3
),

brute_force AS (
  SELECT account_name, client_ip, COUNT(*) AS failed_attempts
  FROM SNOWFLAKE.ORGANIZATION_USAGE.LOGIN_HISTORY
  WHERE event_timestamp >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP()) 
    AND is_success = 'NO'
    AND client_ip != '0.0.0.0'
  GROUP BY account_name, client_ip HAVING COUNT(*) >= 5
)

SELECT 
  a.account_name, a.event_timestamp, a.user_name, a.client_ip, a.is_success, a.error_message,
  a.is_new_ip, a.is_rapid_ip_change, a.is_failed_login,
  s.client_ip IS NOT NULL AS is_shared_ip,
  bf.client_ip IS NOT NULL AS is_brute_force_ip,
  (IFF(a.is_new_ip, 2, 0) + IFF(a.is_rapid_ip_change, 3, 0) + IFF(a.is_failed_login, 1, 0) +
   IFF(s.client_ip IS NOT NULL, 2, 0) + IFF(bf.client_ip IS NOT NULL, 4, 0)) AS risk_score
FROM anomalies a
LEFT JOIN ip_sharing s ON a.account_name = s.account_name AND a.client_ip = s.client_ip
LEFT JOIN brute_force bf ON a.account_name = bf.account_name AND a.client_ip = bf.client_ip
WHERE a.is_new_ip OR a.is_rapid_ip_change OR a.is_failed_login 
   OR s.client_ip IS NOT NULL OR bf.client_ip IS NOT NULL
ORDER BY risk_score DESC, event_timestamp DESC;
```

### Step 3: Summarize Findings

Present results grouped by:

| Risk Score | Anomaly Type |
|------------|--------------|
| **8+** | Critical - Multiple flags (investigate immediately) |
| **5-7** | High - Brute force or rapid IP change with failures |
| **3-4** | Medium - New IP or shared IP |
| **1-2** | Low - Failed login only |

### Step 4: Present Findings

**⚠️ MANDATORY CHECKPOINT**: Present summary before recommendations.

**For ACCOUNT_USAGE:**
```
## Login IP Anomaly Detection Summary

**Timeframe**: [date range]
**Scope**: Current Account
**Total anomalous events**: [count]

### Critical Findings (Risk 8+)
[Events with multiple risk flags]

### High-Risk Findings (Risk 5-7)
[Brute force IPs, rapid IP changes]

### Medium-Risk Findings (Risk 3-4)
[New IPs, shared IPs]

### Users with Multiple Anomalies
[Aggregate by user_name]
```

**For ORGANIZATION_USAGE:**
```
## Login IP Anomaly Detection Summary

**Timeframe**: [date range]
**Scope**: Organization (all accounts)
**Total anomalous events**: [count]

### Critical Findings (Risk 8+)
[Events with multiple risk flags - include account_name]

### High-Risk Findings (Risk 5-7)
[Brute force IPs, rapid IP changes - include account_name]

### Findings by Account
[Aggregate by account_name]

### Users with Multiple Anomalies
[Aggregate by account_name, user_name]
```

### Step 5: Recommend Actions

Based on findings, suggest:
- IPs to block via network policy
- Users to investigate or contact
- MFA enforcement for affected users
- Session policies to implement
- Failed login patterns to monitor
- (For ORGANIZATION_USAGE) Accounts requiring immediate attention

**⚠️ STOP**: Wait for user to decide on next steps.

## Stopping Points

- ✋ Step 1: After scope selection
- ✋ Step 4: After presenting findings
- ✋ Step 5: After recommendations

## Configurable Thresholds

| Parameter | Default | Description |
|-----------|---------|-------------|
| Baseline window | Same as detection | History for known IPs |
| Detection window | User selected | Recent activity to scan |
| Rapid IP change | 10 min | Max time between different IPs |
| Shared IP threshold | 3+ users | IPs flagged as shared |
| Brute force failure threshold | 5+ failures | Login events from an IP are considered as a single Brute Force attempt if the number of failures within the Brute force time window exceed the threshold |
| Brute force time window | 30 seconds | Time window to determine whether a login failure was a brute force attempt|
| Brute force trigger threshold | 5+ triggers | IP considered as a Brute Force IP if at least the specified number of failures are observed in the Brute force time window |

## Output

- Table of anomalous login events with risk scores
- (ORGANIZATION_USAGE) Account name included in all outputs
- Summary by risk level
- Recommendations for high-risk findings
