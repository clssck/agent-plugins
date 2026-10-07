---
name: exfiltration-detection
description: "Detect data exfiltration attempts in Snowflake. Use when: investigating bulk data exports, suspicious UNLOAD/COPY activity, external stage transfers, GET commands, presigned URL generation, unusual stage creation, data sharing activity, new applications, OAuth integrations, security integration changes, external functions, or native apps. Supports both ACCOUNT_USAGE and ORGANIZATION_USAGE. Triggers: exfiltration, data theft, bulk export, UNLOAD, COPY INTO, GET command, presigned URL, external stage, data leak, data sharing, CREATE SHARE, listing, marketplace, OAuth, integration, native app, external function, connector, application installed, app changed."
---

# Exfiltration Detection

Analyze Snowflake activity for potential data exfiltration patterns.

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

### Step 2: Run Detection Queries

Execute these queries replacing:
- `{{DAYS}}` with the selected timeframe
- `{{SCHEMA}}` with either `ACCOUNT_USAGE` or `ORGANIZATION_USAGE`

**For ORGANIZATION_USAGE queries:**
- Add `account_name` to SELECT columns
- Add `account_name` to GROUP BY clauses where applicable
- Include `account_name` in output reports

**Note:** All queries below show ACCOUNT_USAGE syntax. For ORGANIZATION_USAGE:
- Replace `SNOWFLAKE.ACCOUNT_USAGE` with `SNOWFLAKE.ORGANIZATION_USAGE`
- Add `account_name` as the first column in SELECT statements

#### 2a: UNLOAD Operations (Data Export to Stages/External Locations)

```sql
SELECT
    query_id,
    user_name,
    role_name,
    query_type,
    query_text,
    rows_produced,
    bytes_scanned,
    start_time,
    end_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_type = 'UNLOAD'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
  AND NOT is_client_generated_statement
ORDER BY bytes_scanned DESC;
```

#### 2b: COPY INTO with External URLs or User Stages

```sql
SELECT
    query_id,
    user_name,
    role_name,
    query_text,
    rows_produced,
    bytes_scanned,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_type = 'COPY'
  AND (
    LOWER(query_text) LIKE '%s3://%'
    OR LOWER(query_text) LIKE '%azure://%'
    OR LOWER(query_text) LIKE '%gcs://%'
    OR LOWER(query_text) LIKE '%@~%'
  )
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
  AND NOT is_client_generated_statement
ORDER BY bytes_scanned DESC;
```

#### 2c: GET Commands (Download from Stages)

```sql
SELECT
    query_id,
    user_name,
    role_name,
    query_text,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_type = 'GET_FILES'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2d: GET_PRESIGNED_URL Function Calls

```sql
SELECT
    query_id,
    user_name,
    role_name,
    query_text,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE LOWER(query_text) LIKE '%get_presigned_url%'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
  AND NOT is_client_generated_statement
ORDER BY start_time DESC;
```

#### 2e: Stage Creation Events

```sql
SELECT
    query_id,
    user_name,
    role_name,
    query_text,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_type = 'CREATE_STAGE'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2f: COPY FILES Commands

```sql
SELECT
    query_id,
    user_name,
    role_name,
    query_text,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE LOWER(query_text) LIKE '%copy files%'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
  AND NOT is_client_generated_statement
ORDER BY start_time DESC;
```

#### 2g: Data Sharing - CREATE/ALTER SHARE

```sql
SELECT
    query_id,
    user_name,
    role_name,
    query_type,
    query_text,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_type IN ('CREATE_SHARE', 'ALTER_SHARE')
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2h: Data Sharing - Listing Activity

```sql
SELECT
    query_id,
    user_name,
    role_name,
    query_type,
    query_text,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_type LIKE '%LISTING%'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2i: Active Shares and Their Contents

```sql
SELECT
    share_name,
    database_name,
    created_on,
    owner,
    comment
FROM SNOWFLAKE.ACCOUNT_USAGE.SHARES
WHERE deleted IS NULL
ORDER BY created_on DESC;
```

#### 2j: Share Grants to External Accounts

```sql
SELECT
    share_name,
    granted_to,
    grantee_name,
    created_on
FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_SHARES
WHERE deleted_on IS NULL
ORDER BY created_on DESC;
```

#### 2k: Large Result Set Downloads (UI Exfiltration)

```sql
SELECT
    query_id,
    user_name,
    role_name,
    LEFT(query_text, 150) as query_preview,
    rows_produced,
    bytes_scanned,
    start_time
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE rows_produced > 10000
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
  AND query_type = 'SELECT'
  AND user_name != 'SYSTEM'
  AND NOT is_client_generated_statement
ORDER BY rows_produced DESC;
```

#### 2l: RESULT_SCAN Usage (Indicates Result Re-download)

```sql
SELECT
    query_id,
    user_name,
    role_name,
    query_text,
    rows_produced,
    start_time
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE LOWER(query_text) LIKE '%result_scan%'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
  AND user_name != 'SYSTEM'
  AND NOT is_client_generated_statement
ORDER BY rows_produced DESC;
```

---

### Application & Integration Monitoring

#### 2m: New/Modified OAuth Integrations (Snowflake Connectors, 3rd Party Apps)

```sql
SELECT
    query_id,
    user_name,
    role_name,
    query_type,
    LEFT(query_text, 300) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE (
    query_type IN ('CREATE_INTEGRATION', 'ALTER_INTEGRATION', 'DROP_INTEGRATION')
    OR LOWER(query_text) LIKE '%security integration%'
    OR LOWER(query_text) LIKE '%api integration%'
    OR LOWER(query_text) LIKE '%external_oauth%'
    OR LOWER(query_text) LIKE '%oauth%'
  )
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2n: Security Integration Changes (SCIM, SSO, SAML)

```sql
SELECT
    query_id,
    user_name,
    role_name,
    LEFT(query_text, 300) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE (
    LOWER(query_text) LIKE '%scim%'
    OR LOWER(query_text) LIKE '%saml%'
    OR LOWER(query_text) LIKE '%type = saml2%'
    OR LOWER(query_text) LIKE '%type = scim%'
  )
  AND query_type IN ('CREATE_INTEGRATION', 'ALTER_INTEGRATION', 'DROP_INTEGRATION')
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2o: External Functions (Potential Data Egress via API)

```sql
SELECT
    query_id,
    user_name,
    role_name,
    query_type,
    LEFT(query_text, 300) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE (
    LOWER(query_text) LIKE '%external function%'
    OR LOWER(query_text) LIKE '%create function%api_integration%'
    OR LOWER(query_text) LIKE '%external access integration%'
  )
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2p: Native Apps Installed/Modified

```sql
SELECT
    query_id,
    user_name,
    role_name,
    query_type,
    LEFT(query_text, 300) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE (
    query_type LIKE '%APPLICATION%'
    OR LOWER(query_text) LIKE '%create application%'
    OR LOWER(query_text) LIKE '%alter application%'
    OR LOWER(query_text) LIKE '%drop application%'
    OR LOWER(query_text) LIKE '%application package%'
  )
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2q: Current Integrations Inventory

```sql
SHOW INTEGRATIONS;
```

#### 2r: External Access Integrations (Network Egress Points)

```sql
SELECT
    query_id,
    user_name,
    role_name,
    LEFT(query_text, 300) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE (
    LOWER(query_text) LIKE '%external access%'
    OR LOWER(query_text) LIKE '%network rule%'
    OR LOWER(query_text) LIKE '%secret%type%generic%'
  )
  AND query_type LIKE 'CREATE%'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2s: Grants to Applications (Data Access by Apps)

```sql
SELECT
    query_id,
    user_name,
    role_name,
    LEFT(query_text, 300) as query_preview,
    start_time
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE LOWER(query_text) LIKE '%grant%to application%'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2t: Replication Configuration Changes

```sql
SELECT
    query_id,
    user_name,
    role_name,
    query_type,
    LEFT(query_text, 300) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE (
    query_type LIKE '%REPLICATION%'
    OR query_type LIKE '%FAILOVER%'
    OR LOWER(query_text) LIKE '%enable_replication%'
    OR LOWER(query_text) LIKE '%alter database%enable replication%'
  )
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2u: New Client Apps Observed Against Users

```sql
WITH user_client_baseline AS (
  SELECT
    user_name,
    PARSE_JSON(client_environment):"APPLICATION"::string AS client_app,
FROM
    snowflake.account_usage.sessions
WHERE TRUE
    AND created_on BETWEEN CURRENT_TIMESTAMP() - INTERVAL '60 days' AND CURRENT_TIMESTAMP() - INTERVAL '{{DAYS}} days'
    AND client_app IS NOT null
    AND NOT STARTSWITH(client_app, 'Snowflake Web App')
    AND NOT STARTSWITH(user_name, 'STPLAT')
GROUP BY user_name, client_app
),

recent_clients AS (
  SELECT
    user_name,
    MIN(created_on) AS first_seen,
    MAX(created_on) AS last_seen,
    PARSE_JSON(client_environment):"APPLICATION"::string AS client_app,
    COUNT(DISTINCT session_id) AS unique_sessions
  FROM
    snowflake.account_usage.sessions
  WHERE TRUE
    AND created_on > CURRENT_TIMESTAMP() - INTERVAL '{{DAYS}} days'
    AND client_app IS NOT null
    AND NOT STARTSWITH(client_app, 'Snowflake Web App')
    AND NOT STARTSWITH(user_name, 'STPLAT')
GROUP BY user_name, client_app
),

anomalies AS (
  SELECT
    r.user_name,
    r.first_seen,
    r.last_seen,
    r.client_app,
    r.unique_sessions,
  CASE WHEN b.client_app IS NULL THEN true ELSE false END AS is_new_app,
  CASE
    WHEN STARTSWITH(r.client_app, 'SNOWCLI.') THEN true
    WHEN STARTSWITH(r.client_app, 'streamlit:Snow') THEN true
    WHEN r.client_app IN (
        'cortex_code_desktop', 'CORTEX_CODE', 'cortex_code_cli', 'COCO_CLI',
        'streamlit', 'SNOWFLAKE_CLI', 'SnowSQL', 'spcs_system_connection',
        'Snowflake.SnowConvertDesktop', 'SnowparkML', 'snowflake_dbt',
        'PythonSnowpark', 'notebook_health_check'
        ) THEN true
    ELSE false
  END AS is_snowflake_app,
  CASE WHEN r.client_app IN ('PythonConnector', 'Go') THEN true ELSE false END AS connector_used_without_providing_app_name
  FROM
    recent_clients r
    LEFT JOIN user_client_baseline b
      ON r.user_name = b.user_name AND r.client_app = b.client_app
)
SELECT * FROM anomalies
WHERE TRUE
  AND is_new_app
  AND NOT is_snowflake_app
ORDER BY first_seen DESC, unique_sessions DESC
;
```

Note that new client applications against a user indicates new, potentially unusual behavior but it does not imply data exfiltration attempts.
Inspecting query history from suspicious client apps will provide more context to the account administrators.

---

### External & Iceberg Tables (Data Egress to External Storage)

#### 2v: External Table Creation (Potential Attacker-Controlled Storage)

```sql
SELECT
    query_id,
    user_name,
    role_name,
    LEFT(query_text, 400) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE (
    LOWER(query_text) LIKE '%create%external table%'
    OR LOWER(query_text) LIKE '%create or replace external table%'
  )
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2w: Iceberg Table Creation (External Catalog/Storage)

```sql
SELECT
    query_id,
    user_name,
    role_name,
    LEFT(query_text, 400) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE (
    LOWER(query_text) LIKE '%create%iceberg table%'
    OR LOWER(query_text) LIKE '%create or replace iceberg table%'
    OR LOWER(query_text) LIKE '%catalog_sync%'
  )
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2x: External Volume Creation (S3/Azure/GCS Storage Targets)

```sql
SELECT
    query_id,
    user_name,
    role_name,
    LEFT(query_text, 400) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE (
    LOWER(query_text) LIKE '%create%external volume%'
    OR LOWER(query_text) LIKE '%alter external volume%'
  )
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2y: Catalog Integration Changes (External Iceberg Catalogs)

```sql
SELECT
    query_id,
    user_name,
    role_name,
    LEFT(query_text, 400) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE (
    LOWER(query_text) LIKE '%catalog integration%'
    OR LOWER(query_text) LIKE '%create%integration%type%glue%'
    OR LOWER(query_text) LIKE '%create%integration%type%object_store%'
  )
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2z: Current External Tables Inventory

```sql
SELECT
    table_catalog as database_name,
    table_schema as schema_name,
    table_name,
    table_owner,
    created,
    last_altered,
    comment
FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES
WHERE table_type = 'EXTERNAL TABLE'
  AND deleted IS NULL
ORDER BY created DESC;
```

#### 2aa: Current Iceberg Tables Inventory

```sql
SELECT
    table_catalog as database_name,
    table_schema as schema_name,
    table_name,
    table_owner,
    created,
    last_altered,
    comment
FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES
WHERE is_iceberg = 'YES'
  AND deleted IS NULL
ORDER BY created DESC;
```

---

### Step 3: Analyze Results

For each finding, evaluate:

| Risk Factor | High Risk Indicator |
|-------------|---------------------|
| Volume | Bytes scanned > 1GB or rows > 1M |
| Destination | External cloud URLs (s3://, azure://, gcs://) |
| User stage | @~ prefix (user's personal stage) |
| Timing | Outside business hours or weekends |
| User | Service accounts or inactive users |
| Frequency | Multiple exports in short timeframe |
| Sharing | New shares to unknown accounts |
| Sharing | Shares with broad object grants |
| Listing | New marketplace listings |
| UI Download | Large result sets (>10K rows) from SELECT |
| UI Download | RESULT_SCAN usage to re-fetch results |
| **Apps/Integrations** | **New OAuth integrations created** |
| **Apps/Integrations** | **Security integrations modified (SCIM/SAML)** |
| **Apps/Integrations** | **External functions with API access** |
| **Apps/Integrations** | **Native apps installed from unknown sources** |
| **Apps/Integrations** | **External access integrations (network egress)** |
| **Apps/Integrations** | **Grants to applications on sensitive data** |
| **Apps/Integrations** | **New Client Applications Used by a User** |
| **Replication** | **Replication enabled to external accounts** |
| **External Tables** | **External tables pointing to unknown storage** |
| **External Tables** | **Iceberg tables with external catalog/volume** |
| **External Tables** | **New external volumes (S3/Azure/GCS)** |
| **External Tables** | **Catalog integrations (Glue, Unity, etc.)** |

### Step 4: Present Findings

**⚠️ MANDATORY CHECKPOINT**: Present summary before recommendations.

**For ACCOUNT_USAGE:**
```
## Exfiltration Detection Summary

**Timeframe**: [date range]
**Scope**: Current Account
**Total suspicious events**: [count]

### High-Risk Findings
[List events with high-risk indicators]

### Medium-Risk Findings
[List events with some risk indicators]

### Users with Multiple Export Events
[Aggregate by user_name]
```

**For ORGANIZATION_USAGE:**
```
## Exfiltration Detection Summary

**Timeframe**: [date range]
**Scope**: Organization (all accounts)
**Total suspicious events**: [count]

### High-Risk Findings
[List events with high-risk indicators - include account_name]

### Medium-Risk Findings
[List events with some risk indicators - include account_name]

### Findings by Account
[Aggregate by account_name]

### Users with Multiple Export Events
[Aggregate by account_name, user_name]
```

### Step 5: Recommend Actions

Based on findings, suggest:
- Users to investigate further
- Stages to audit or remove
- Network policies to implement
- Access grants to revoke
- Shares to review or drop
- Listings to unpublish
- **Integrations to disable or audit**
- **Review queries from new client applications observed against users**
- **Applications to review permissions or remove**
- **External functions to restrict or drop**
- **Replication configurations to review**
- **External tables pointing to suspicious storage locations**
- **Iceberg tables with unauthorized external volumes**
- **Catalog integrations to audit or remove**
- (For ORGANIZATION_USAGE) Accounts requiring immediate attention

**⚠️ STOP**: Wait for user to decide on next steps.

## Stopping Points

- ✋ Step 1: After scope selection
- ✋ Step 4: After presenting findings
- ✋ Step 5: After recommendations

## Output

Summary report of potential exfiltration activity with risk-ranked findings and remediation recommendations.

**ORGANIZATION_USAGE outputs include:**
- Account name in all findings
- Cross-account analysis
- Account-level aggregations
