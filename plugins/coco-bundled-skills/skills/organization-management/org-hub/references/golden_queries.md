# Golden Query Catalog

### Cost and Spend

#### `ORG_HUB_TOTAL_COST`
- **Purpose:** Total organization spend for a window.
- **Dimensions:** none
- **SQL:**
```sql
SELECT COALESCE(SUM(USAGE_IN_CURRENCY), 0) AS total_cost, CURRENCY
FROM SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY
WHERE USAGE_DATE >= DATEADD(day, -30, CURRENT_DATE())
  AND USAGE_DATE < CURRENT_DATE()
GROUP BY CURRENCY;
```
- **Output contract:** `total_cost NUMBER, currency STRING` — present as `$X.XX <CURRENCY>`

#### `ORG_HUB_COST_BY_SERVICE_TYPE_WEEKLY`
- **Purpose:** Spend trend by service type week over week.
- **Dimensions:** `week_start_date`, `service_type`
- **SQL:**
```sql
WITH weekly_costs AS (
  SELECT
    DATE_TRUNC('WEEK', USAGE_DATE) AS week_start,
    SERVICE_TYPE,
    SUM(USAGE_IN_CURRENCY) AS total_cost,
    CURRENCY
  FROM SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY
  WHERE USAGE_DATE >= DATEADD(day, -30, CURRENT_DATE())
    AND USAGE_DATE < CURRENT_DATE()
  GROUP BY 1, 2, CURRENCY
)
SELECT
  TO_VARCHAR(week_start, 'YYYY-MM-DD') AS week_start_date,
  SERVICE_TYPE,
  total_cost,
  CURRENCY
FROM weekly_costs
ORDER BY week_start, total_cost DESC;
```
- **Output contract:** `week_start_date STRING, service_type STRING, total_cost NUMBER, currency STRING` — present costs as `$X.XX`

#### `ORG_HUB_COST_BY_SERVICE_TYPE_MONTHLY_TOP5`
- **Purpose:** Top service categories and "other" contribution by account.
- **Dimensions:** `account_name`
- **SQL:**
```sql
WITH top_service AS (
  SELECT
    SERVICE_TYPE,
    SUM(USAGE_IN_CURRENCY) AS total_cost,
    ROW_NUMBER() OVER (ORDER BY SUM(USAGE_IN_CURRENCY) DESC) AS rn
  FROM SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY
  WHERE USAGE_DATE BETWEEN DATEADD(day, -30, CURRENT_DATE()) AND CURRENT_DATE()
  GROUP BY SERVICE_TYPE
),
top_5 AS (
  SELECT SERVICE_TYPE
  FROM top_service
  WHERE rn <= 5
)
SELECT
  a.ACCOUNT_NAME,
  SUM(a.USAGE_IN_CURRENCY) AS total_cost,
  SUM(CASE WHEN t5.SERVICE_TYPE IS NULL THEN a.USAGE_IN_CURRENCY ELSE 0 END) AS other_cost,
  a.CURRENCY
FROM SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY a
LEFT JOIN top_5 t5 ON a.SERVICE_TYPE = t5.SERVICE_TYPE
WHERE a.USAGE_DATE BETWEEN DATEADD(day, -30, CURRENT_DATE()) AND CURRENT_DATE()
GROUP BY a.ACCOUNT_NAME, a.CURRENCY
ORDER BY total_cost DESC
LIMIT 20;
```
- **Output contract:** `account_name STRING, total_cost NUMBER, other_cost NUMBER, currency STRING` — present costs as `$X.XX`

### Accounts and Admin Coverage

#### `ORG_HUB_ACCOUNT_INVENTORY`
- **Purpose:** Organization account inventory, growth, and edition mix. **Do not use SHOW ACCOUNTS for org hub analytics.**
- **Dimensions:** `EDITION`
- **SQL:**
```sql
SELECT 
    EDITION,
    COUNT(DISTINCT ACCOUNT_NAME) as account_count,
    COUNT(DISTINCT CASE WHEN CREATED_ON >= DATEADD(day, -30, CURRENT_TIMESTAMP()) THEN ACCOUNT_NAME END) as new_accounts_30d
FROM SNOWFLAKE.ORGANIZATION_USAGE.ACCOUNTS
WHERE DELETED_ON IS NULL
GROUP BY EDITION
ORDER BY account_count DESC;
```
- **Output contract:** account counts by edition, plus new accounts in the last 30 days

#### `ORG_HUB_ACCOUNT_ADMINS_TOTAL`
- **Purpose:** Count distinct account-level admins across org.
- **Dimensions:** none
- **SQL:**
```sql
WITH admin_users AS (
  SELECT account_name, grantee_name AS user_name
  FROM SNOWFLAKE.ORGANIZATION_USAGE.grants_to_users
  WHERE role IN ('ACCOUNTADMIN', 'GLOBALORGADMIN')
    AND deleted_on IS NULL
  GROUP BY account_name, grantee_name
)
SELECT COUNT(*) AS admin_count
FROM admin_users;
```
- **Output contract:** `admin_count NUMBER`

#### `ORG_HUB_SECURITY_ADMINS_TOTAL`
- **Purpose:** Count distinct `SECURITYADMIN` assignees.
- **Dimensions:** none
- **SQL:**
```sql
SELECT COUNT(DISTINCT gtu.GRANTEE_NAME) AS admin_count
FROM SNOWFLAKE.ORGANIZATION_USAGE.grants_to_users gtu
WHERE gtu.ROLE = 'SECURITYADMIN'
  AND gtu.DELETED_ON IS NULL;
```
- **Output contract:** `admin_count NUMBER`

### Authentication and Login Health

#### `ORG_HUB_LOGINS_BY_AUTH_TYPE_DAILY`
- **Purpose:** Daily auth-method mix trend.
- **Dimensions:** `day`
- **Note:** Queries raw `LOGIN_HISTORY` — **limit to 7 days max** to avoid timeouts. For 30-day summaries, run this for the last 7 days only and note the limited window.
- **SQL:**
```sql
SELECT
  TO_VARCHAR(EVENT_TIMESTAMP::DATE, 'YYYY-MM-DD') AS day,
  COUNT_IF(FIRST_AUTHENTICATION_FACTOR = 'SAML_AUTHENTICATOR') AS sso_count,
  COUNT_IF(FIRST_AUTHENTICATION_FACTOR = 'PASSWORD' AND SECOND_AUTHENTICATION_FACTOR IS NULL) AS password_without_mfa_count,
  COUNT_IF(FIRST_AUTHENTICATION_FACTOR = 'PASSWORD' AND SECOND_AUTHENTICATION_FACTOR IS NOT NULL) AS password_with_mfa_count,
  COUNT_IF(FIRST_AUTHENTICATION_FACTOR ILIKE '%OAUTH%') AS oauth_count,
  COUNT(*) AS total_count
FROM SNOWFLAKE.ORGANIZATION_USAGE.LOGIN_HISTORY
WHERE EVENT_TIMESTAMP >= DATEADD(day, -7, CURRENT_DATE)
  AND EVENT_TIMESTAMP < CURRENT_DATE
  AND EVENT_TYPE = 'LOGIN'
  AND IS_SUCCESS = 'YES'
GROUP BY 1
ORDER BY 1;
```
- **Output contract:** daily counts by auth bucket (last 7 days)

#### `ORG_HUB_LOGINS_BY_USER_AND_CLIENT`
- **Purpose:** User and client-level auth-method distribution.
- **Dimensions:** `user_name`, `reported_client_type`
- **Note:** Queries raw `LOGIN_HISTORY` — **limit to 7 days max** to avoid timeouts.
- **SQL:**
```sql
SELECT
  USER_NAME,
  REPORTED_CLIENT_TYPE,
  FIRST_AUTHENTICATION_FACTOR,
  COUNT(*) AS login_count
FROM SNOWFLAKE.ORGANIZATION_USAGE.LOGIN_HISTORY
WHERE EVENT_TIMESTAMP >= DATEADD(day, -7, CURRENT_DATE)
  AND EVENT_TIMESTAMP < CURRENT_DATE
  AND EVENT_TYPE = 'LOGIN'
  AND IS_SUCCESS = 'YES'
GROUP BY 1, 2, 3
ORDER BY login_count DESC
LIMIT 50;
```
- **Output contract:** top login patterns by user/client/auth (last 7 days)

#### `ORG_HUB_LOGIN_FAILURES_BY_TYPE_TOTAL`
- **Purpose:** Most frequent login failure reasons.
- **Dimensions:** `error_message`
- **Note:** Queries raw `LOGIN_HISTORY` — **limit to 7 days max** to avoid timeouts.
- **SQL:**
```sql
SELECT
  ERROR_MESSAGE,
  COUNT(*) AS count
FROM SNOWFLAKE.ORGANIZATION_USAGE.LOGIN_HISTORY
WHERE EVENT_TYPE = 'LOGIN'
  AND IS_SUCCESS = 'NO'
  AND ERROR_MESSAGE IS NOT NULL
  AND EVENT_TIMESTAMP >= DATEADD(day, -7, CURRENT_DATE)
  AND EVENT_TIMESTAMP < CURRENT_DATE
GROUP BY ERROR_MESSAGE
ORDER BY count DESC
LIMIT 20;
```
- **Output contract:** `error_message STRING, count NUMBER`

### Reliability and Query Efficiency

#### `ORG_HUB_FAILED_QUERIES_DAILY`
- **Purpose:** Daily failed-query trend. **Only use when user explicitly asks about query failures.**
- **Dimensions:** `usage_date`
- **Note:** Uses raw `QUERY_HISTORY` — **3-day max, LIMIT 100**. Do not include in executive summaries.
- **SQL:**
```sql
SELECT
  TO_VARCHAR(START_TIME::DATE, 'YYYY-MM-DD') AS usage_date,
  COUNT(*) AS total_failures
FROM SNOWFLAKE.ORGANIZATION_USAGE.QUERY_HISTORY
WHERE START_TIME >= DATEADD(day, -3, CURRENT_DATE)
  AND START_TIME < CURRENT_DATE
  AND EXECUTION_STATUS = 'FAIL'
GROUP BY 1
ORDER BY 1
LIMIT 100;
```
- **Output contract:** one row per day with failure count (last 3 days)

#### `ORG_HUB_TOP_QUERIES_BY_TOTAL_ELAPSED_TIME`
- **Purpose:** Most expensive queries by elapsed time. **Only use when user explicitly asks about query performance.**
- **Dimensions:** `warehouse_name`, `query_type`
- **Note:** Uses raw `QUERY_HISTORY` — **3-day max, LIMIT 20**. Do not include in executive summaries.
- **SQL:**
```sql
  SELECT
  WAREHOUSE_NAME,
  QUERY_TYPE,
  COUNT(*) AS query_count,
  ROUND(SUM(TOTAL_ELAPSED_TIME) / 1000, 1) AS total_elapsed_sec,
  ROUND(SUM(CREDITS_USED_CLOUD_SERVICES), 4) AS cloud_credits
FROM SNOWFLAKE.ORGANIZATION_USAGE.QUERY_HISTORY
WHERE START_TIME >= DATEADD(day, -3, CURRENT_DATE)
  AND START_TIME < CURRENT_DATE
  AND WAREHOUSE_NAME IS NOT NULL
GROUP BY 1, 2
ORDER BY total_elapsed_sec DESC
LIMIT 20;
```
- **Output contract:** top query patterns by elapsed time (last 3 days)

#### `ORG_HUB_TOP_WAREHOUSES_BY_CREDITS`
- **Purpose:** Top warehouses by credit consumption (30-day).
- **Dimensions:** `warehouse_name`
- **Note:** `WAREHOUSE_METERING_HISTORY` does NOT have `ACCOUNT_NAME` or `USAGE_DATE`. For per-account credit breakdown, use `USAGE_IN_CURRENCY_DAILY` instead.
- **SQL:**
```sql
SELECT
  WAREHOUSE_NAME,
  ROUND(SUM(CREDITS_USED), 2) AS total_credits,
  ROUND(SUM(CREDITS_USED_COMPUTE), 2) AS compute_credits,
  ROUND(SUM(CREDITS_USED_CLOUD_SERVICES), 2) AS cloud_credits
FROM SNOWFLAKE.ORGANIZATION_USAGE.WAREHOUSE_METERING_HISTORY
WHERE START_TIME >= DATEADD(day, -30, CURRENT_DATE)
  AND START_TIME < CURRENT_DATE
GROUP BY WAREHOUSE_NAME
ORDER BY total_credits DESC
LIMIT 20;
```
- **Output contract:** top warehouses by credit spend

#### `ORG_HUB_CREDITS_BY_ACCOUNT`
- **Purpose:** Spend by account (30-day). Use this when you need per-account breakdown.
- **Dimensions:** `account_name`
- **Note:** Use `USAGE_IN_CURRENCY_DAILY` for per-account data — it has `ACCOUNT_NAME`. Do NOT use `WAREHOUSE_METERING_HISTORY` for per-account queries.
- **SQL:**
```sql
SELECT
  ACCOUNT_NAME,
  ROUND(SUM(USAGE_IN_CURRENCY), 2) AS total_cost,
  COUNT(DISTINCT SERVICE_TYPE) AS service_count,
  CURRENCY
FROM SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY
WHERE USAGE_DATE >= DATEADD(day, -30, CURRENT_DATE)
  AND USAGE_DATE < CURRENT_DATE
GROUP BY ACCOUNT_NAME, CURRENCY
ORDER BY total_cost DESC
LIMIT 20;
```
- **Output contract:** `account_name STRING, total_cost NUMBER, service_count NUMBER, currency STRING` — present costs as `$X.XX`

### Security Posture

#### `ORG_HUB_TRUST_CENTER_VIOLATIONS_DAILY`
- **Purpose:** Open trust-center findings by severity over time.
- **Dimensions:** `day`
- **Note:** Uses `TRUST_CENTER_FINDINGS`.
- **SQL:**
```sql
SELECT
  TO_VARCHAR(CREATED_ON::DATE, 'YYYY-MM-DD') AS day,
  COUNT_IF(SEVERITY = 'CRITICAL' AND STATE = 'Open') AS critical_count,
  COUNT_IF(SEVERITY = 'HIGH' AND STATE = 'Open') AS high_count,
  COUNT_IF(SEVERITY = 'MEDIUM' AND STATE = 'Open') AS medium_count,
  COUNT_IF(SEVERITY = 'LOW' AND STATE = 'Open') AS low_count,
  COUNT_IF(STATE = 'Open') AS total_count
FROM SNOWFLAKE.ORGANIZATION_USAGE.TRUST_CENTER_FINDINGS
WHERE CREATED_ON >= DATEADD(day, -30, CURRENT_DATE())
  AND CREATED_ON < CURRENT_DATE()
GROUP BY 1
ORDER BY 1;
```
- **Output contract:** one row per day with severity totals

#### `ORG_HUB_MFA_READINESS_TOTAL`
- **Purpose:** Organization-level MFA readiness coverage.
- **Dimensions:** none
- **Note:** Derives MFA posture from `TRUST_CENTER_FINDINGS` by filtering for MFA-related scanner findings.
- **SQL:**
```sql
SELECT
  COUNT(DISTINCT ACCOUNT_NAME) AS total_accounts_with_findings,
  COUNT_IF(STATE = 'Open') AS open_mfa_findings,
  COUNT_IF(STATE = 'Resolved') AS resolved_mfa_findings
FROM SNOWFLAKE.ORGANIZATION_USAGE.TRUST_CENTER_FINDINGS
WHERE SCANNER_NAME ILIKE '%MFA%';
```
- **Output contract:** `total_accounts_with_findings NUMBER, open_mfa_findings NUMBER, resolved_mfa_findings NUMBER`

### Storage and Warehouse Health

#### `ORG_HUB_STORAGE_BY_ACCOUNT_CURRENT`
- **Purpose:** Current storage footprint by account with 28-day change signal.
- **Dimensions:** `account_name`
- **Note:** Uses `STORAGE_DAILY_HISTORY` (always available). Columns: `USAGE_DATE`, `ACCOUNT_NAME`, `AVERAGE_BYTES`.
- **SQL:**
```sql
WITH current_storage AS (
  SELECT
    ACCOUNT_NAME,
    SUM(AVERAGE_BYTES) / POWER(1024, 4) AS current_tb
  FROM SNOWFLAKE.ORGANIZATION_USAGE.STORAGE_DAILY_HISTORY
  WHERE USAGE_DATE = (
    SELECT MAX(USAGE_DATE)
    FROM SNOWFLAKE.ORGANIZATION_USAGE.STORAGE_DAILY_HISTORY
  )
  GROUP BY ACCOUNT_NAME
),
previous_storage AS (
  SELECT
    ACCOUNT_NAME,
    SUM(AVERAGE_BYTES) / POWER(1024, 4) AS previous_tb
  FROM SNOWFLAKE.ORGANIZATION_USAGE.STORAGE_DAILY_HISTORY
  WHERE USAGE_DATE = (
    SELECT MAX(USAGE_DATE)
    FROM SNOWFLAKE.ORGANIZATION_USAGE.STORAGE_DAILY_HISTORY
    WHERE USAGE_DATE <= DATEADD(day, -28, CURRENT_DATE)
  )
  GROUP BY ACCOUNT_NAME
)
SELECT
  cs.ACCOUNT_NAME,
  ROUND(cs.current_tb, 3) AS current_storage_tb,
  ROUND(COALESCE(ps.previous_tb, 0), 3) AS previous_storage_tb,
  ROUND(cs.current_tb - COALESCE(ps.previous_tb, 0), 3) AS change_tb,
  CASE
    WHEN COALESCE(ps.previous_tb, 0) > 0 THEN ROUND(((cs.current_tb - ps.previous_tb) / ps.previous_tb) * 100, 2)
    WHEN cs.current_tb > 0 THEN 100
    ELSE 0
  END AS pct_change
FROM current_storage cs
LEFT JOIN previous_storage ps ON cs.ACCOUNT_NAME = ps.ACCOUNT_NAME
ORDER BY cs.current_tb DESC
LIMIT 20;
```
- **Output contract:** `account_name STRING, current_storage_tb NUMBER, previous_storage_tb NUMBER, change_tb NUMBER, pct_change NUMBER`

#### `ORG_HUB_WAREHOUSE_QUEUED_LOAD_P99_TOTAL`
- **Purpose:** P99 queued-load pressure for selected period.
- **Dimensions:** none
- **SQL:**
```sql
WITH current_period AS (
  SELECT CAST(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY avg_queued_load) AS FLOAT) AS p99_queued_load
  FROM SNOWFLAKE.ORGANIZATION_USAGE.WAREHOUSE_LOAD_HISTORY
  WHERE start_time >= DATEADD(day, -30, CURRENT_DATE())
    AND start_time < DATEADD(day, 1, CURRENT_DATE())
)
SELECT p99_queued_load
FROM current_period;
```
- **Output contract:** `p99_queued_load FLOAT`
