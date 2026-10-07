---
name: privilege-escalation
description: "Detect privilege escalation attempts in Snowflake. Use when: investigating unauthorized access, role changes, suspicious grants, ACCOUNTADMIN abuse, self-grants, new users, backdoor accounts, or RBAC violations. Supports both ACCOUNT_USAGE and ORGANIZATION_USAGE. Triggers: privilege escalation, role grant, ACCOUNTADMIN, SECURITYADMIN, SYSADMIN, grant to self, create user, alter user, create role, suspicious grant, backdoor, unauthorized access, RBAC audit, who granted, privilege abuse."
---

# Privilege Escalation Detection

Analyze Snowflake activity for privilege escalation patterns and unauthorized access changes.

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

- **ACCOUNT_USAGE:** Requires SELECT on `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`, `SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_USERS`, and `SNOWFLAKE.ACCOUNT_USAGE.USERS`. Access is granted through any of the following:
  - `IMPORTED PRIVILEGES` on the SNOWFLAKE database
  - Both database roles: `SNOWFLAKE.GOVERNANCE_VIEWER` and `SNOWFLAKE.SECURITY_VIEWER`
  - `ACCOUNTADMIN` role

- **ORGANIZATION_USAGE:** Requires SELECT to `SNOWFLAKE.ORGANIZATION_USAGE` views. Access is granted through any of the following:
  - `ORGADMIN` role
  - `ORG_USAGE_ADMIN` role
  - Any role granted both `ORGANIZATION_GOVERNANCE_VIEWER` and `ORGANIZATION_SECURITY_VIEWER`
  - `USAGE` privilege on `SNOWFLAKE.ORGANIZATION_USAGE`


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

### Known Limitations

**Indirect Execution via Stored Procedures / UDFs / Tasks:**
GRANT/REVOKE statements executed inside stored procedures, tasks, or UDFs may not appear
in QUERY_HISTORY with their actual SQL text. The `query_text` column may show only the
procedure call (e.g., `CALL manage_access()`) rather than the underlying GRANT statement.
To partially mitigate this, audit stored procedure definitions separately.

**Role Hierarchy Not Traversed:**
Current-state audit queries (2q–2t) show only users directly assigned privileged roles.
They do not walk the role hierarchy. A user who holds `CUSTOM_ROLE`, which in turn inherits
`ACCOUNTADMIN`, will NOT appear in these results.
Full hierarchy traversal requires recursive queries or `SHOW GRANTS`.

**Indirect Self-Grants:**
Self-grant detection (2l) only catches direct `GRANT ROLE X TO USER <self>` patterns.
It does not detect a user granting a privileged role to an intermediate role they already
hold (e.g., `GRANT ROLE ACCOUNTADMIN TO ROLE my_role` where the user already has `my_role`).

---

### User Account Changes

#### 2a: New User Creation

```sql
SELECT
    query_id,
    user_name as created_by,
    role_name,
    LEFT(query_text, 300) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_type = 'CREATE_USER'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2b: User Modifications (Password, Properties, Defaults)

```sql
SELECT
    query_id,
    user_name as modified_by,
    role_name,
    LEFT(query_text, 300) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_type like 'ALTER_USER%'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2c: User Deletions (Potential Cover-Up)

```sql
SELECT
    query_id,
    user_name as deleted_by,
    role_name,
    LEFT(query_text, 300) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_type = 'DROP_USER'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

---

### Role Changes

**⚠️ Volume Warning:** Role creation (2d) is routine in most accounts (CI/CD, provisioning
automation, dbt, etc.). This query may return hundreds of benign results. Prioritize
results where the `using_role` is unusual or the role name resembles a privileged role.
Cross-reference with 2k to identify cases where a newly created role was subsequently
granted privileged access.

#### 2d: New Role Creation

```sql
SELECT
    query_id,
    user_name as created_by,
    role_name as using_role,
    LEFT(query_text, 300) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_type = 'CREATE_ROLE'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

**⚠️ Volume Warning:** ALTER_ROLE captures all modifications including comment changes,
tag assignments, and other non-security-relevant changes. Snowflake does not provide a
`query_type` subtype to distinguish these. This query is best used for targeted
investigation when other queries (2g–2k) surface suspicious role activity, not as a
broad alerting query.

#### 2e: Role Modifications

```sql
SELECT
    query_id,
    user_name as modified_by,
    role_name as using_role,
    LEFT(query_text, 300) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_type = 'ALTER_ROLE'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2f: Role Deletions

```sql
SELECT
    query_id,
    user_name as deleted_by,
    role_name as using_role,
    LEFT(query_text, 300) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_type = 'DROP_ROLE'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

---

### Privileged Role Grants (CRITICAL)

#### 2g: ACCOUNTADMIN Grants

```sql
SELECT
    query_id,
    user_name as granted_by,
    role_name as using_role,
    LEFT(query_text, 300) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE LOWER(query_text) LIKE '%grant%role%accountadmin%'
  AND query_type = 'GRANT'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2h: SECURITYADMIN Grants

```sql
SELECT
    query_id,
    user_name as granted_by,
    role_name as using_role,
    LEFT(query_text, 300) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE LOWER(query_text) LIKE '%grant%role%securityadmin%'
  AND query_type = 'GRANT'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2i: SYSADMIN Grants

```sql
SELECT
    query_id,
    user_name as granted_by,
    role_name as using_role,
    LEFT(query_text, 300) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE LOWER(query_text) LIKE '%grant%role%sysadmin%'
  AND query_type = 'GRANT'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2j: USERADMIN Grants

```sql
SELECT
    query_id,
    user_name as granted_by,
    role_name as using_role,
    LEFT(query_text, 300) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE LOWER(query_text) LIKE '%grant%role%useradmin%'
  AND query_type = 'GRANT'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2k: All Privileged Role Grants Combined

**Note:** Below query is based on pattern matching with role name which could include customer created roles that matches the pattern. There are the roles we should be limiting to ACCOUNTADMIN, GLOBALORGADMIN, SECURITYADMIN, USERADMIN, SYSADMIN, ORGADMIN, APPADMIN, AUTO_FULFILLMENT_EXECUTOR, COMPUTE_SERVICE_ADMIN and BILLINGADMIN

```sql
SELECT
    query_id,
    user_name as granted_by,
    role_name as using_role,
    LEFT(query_text, 300) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_type = 'GRANT'
  AND (
    LOWER(query_text) LIKE '%grant%role%accountadmin%'
    OR LOWER(query_text) LIKE '%grant%role%securityadmin%'
    OR LOWER(query_text) LIKE '%grant%role%sysadmin%'
    OR LOWER(query_text) LIKE '%grant%role%useradmin%'
    OR LOWER(query_text) LIKE '%grant%role%appadmin%'
    OR LOWER(query_text) LIKE '%grant%role%auto_fulfillment_executor%'
    OR LOWER(query_text) LIKE '%grant%role%compute_service_admin%'
    OR LOWER(query_text) LIKE '%grant%role%billingadmin%'
    OR LOWER(query_text) LIKE '%grant%role%orgadmin%' -- GLOBALORGADMIN, ORGADMIN
  )
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

---

### Self-Grants (Suspicious Pattern)

**⚠️ Limitation:** This query detects direct self-grants only (`GRANT ... TO USER <self>`).
It has blind spots:
1. A user grants a privileged role to a role they already hold (indirect escalation)
2. A user creates a new role, grants it to themselves, then grants privileges to that role

#### 2l: Grants Where User Grants to Themselves

```sql
SELECT
    query_id,
    user_name AS granted_by,
    role_name AS using_role,
    LEFT(query_text, 300) AS query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_type = 'GRANT'
  AND REGEXP_LIKE(
      query_text,
      '.*TO\\s+USER\\s+"?' || user_name || '"?\\b.*',
      'i'
  )
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

---

### All Grant Activity

#### 2m: All GRANT Statements

```sql
SELECT
    query_id,
    user_name as granted_by,
    role_name as using_role,
    LEFT(query_text, 300) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_type = 'GRANT'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2n: All REVOKE Statements

```sql
SELECT
    query_id,
    user_name as revoked_by,
    role_name as using_role,
    LEFT(query_text, 300) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_type = 'REVOKE'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```
**⚠️ Volume Warning:** `WITH GRANT OPTION` is used in routine provisioning workflows.
This query is best used for targeted investigation when other findings indicate
suspicious grant activity, not as part of the default detection scan.

#### 2o: Grants with GRANT OPTION (Can Re-Grant)

```sql
SELECT
    query_id,
    user_name as granted_by,
    role_name as using_role,
    LEFT(query_text, 300) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_type = 'GRANT'
  AND LOWER(query_text) LIKE '%with grant option%'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

---

### Ownership Changes

#### 2p: Ownership Transfers

```sql
SELECT
    query_id,
    user_name as transferred_by,
    role_name as using_role,
    LEFT(query_text, 300) as query_preview,
    start_time,
    execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE LOWER(query_text) LIKE '%grant ownership%'
  AND query_type = 'GRANT'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

---

### Current State Audit

**⚠️ Limitation:** Queries 2q–2t show only direct role assignments to users. They do not
traverse the role hierarchy. See 2s2 below for roles that inherit privileged roles.

#### 2q: Current ACCOUNTADMIN Users

```sql
SELECT DISTINCT
    grantee_name as user_name
FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_USERS
WHERE role = 'ACCOUNTADMIN'
  AND deleted_on IS NULL
ORDER BY created_on DESC;
```

#### 2r: Current SECURITYADMIN Users

```sql
SELECT DISTINCT
    grantee_name as user_name
FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_USERS
WHERE role = 'SECURITYADMIN'
  AND deleted_on IS NULL
ORDER BY created_on DESC;
```

#### 2s: Users with Privileged Roles

```sql
SELECT
    grantee_name AS user_name,
    LISTAGG(DISTINCT role, ', ') AS privileged_roles,
    COUNT(DISTINCT role) AS role_count
FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_USERS
WHERE role IN ('ACCOUNTADMIN', 'GLOBALORGADMIN', 'SECURITYADMIN', 'USERADMIN', 'SYSADMIN', 'ORGADMIN', 'APPADMIN', 'AUTO_FULFILLMENT_EXECUTOR', 'COMPUTE_SERVICE_ADMIN', 'BILLINGADMIN')
  AND deleted_on IS NULL
GROUP BY grantee_name
ORDER BY role_count DESC;
```

#### 2t: Users with Multiple Privileged Roles

```sql
SELECT
    grantee_name as user_name,
    LISTAGG(DISTINCT role, ', ') as privileged_roles,
    COUNT(DISTINCT role) AS role_count
FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_USERS
WHERE role IN ('ACCOUNTADMIN', 'GLOBALORGADMIN', 'SECURITYADMIN', 'USERADMIN', 'SYSADMIN', 'ORGADMIN', 'APPADMIN', 'AUTO_FULFILLMENT_EXECUTOR', 'COMPUTE_SERVICE_ADMIN', 'BILLINGADMIN')
  AND deleted_on IS NULL
GROUP BY grantee_name
HAVING COUNT(DISTINCT role) > 1
ORDER BY role_count DESC;
```

#### 2u: Recently Created Users (Potential Backdoors)

```sql
SELECT
    name,
    login_name,
    created_on,
    default_role,
    has_password,
    has_rsa_public_key,
    disabled,
    ext_authn_uid
FROM SNOWFLAKE.ACCOUNT_USAGE.USERS
WHERE created_on >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
  AND deleted_on IS NULL
ORDER BY created_on DESC;
```

#### 2v: Service Accounts (Non-Human Identities)

```sql
SELECT
    name,
    login_name,
    created_on,
    default_role,
    has_password,
    has_rsa_public_key,
    last_success_login,
    disabled
FROM SNOWFLAKE.ACCOUNT_USAGE.USERS
WHERE created_on >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
  AND deleted_on IS NULL
  AND type != 'PERSON'
ORDER BY created_on DESC;
```

---

### Future Enhancement: High-Impact Privilege Grants

Tracking grants of specific system-level privileges (`MANAGE GRANTS`, `CREATE USER`,
`EXECUTE TASK`, `IMPORT SHARE`, `CREATE INTEGRATION`, etc.) to any role. Granting these
privileges to a non-admin role can be an escalation vector. Currently out of scope for
this skill.

---

### Failed Privilege Operations (Blocked Attempts)

#### 2w: Failed GRANT Attempts

```sql
SELECT
    query_id,
    user_name as attempted_by,
    role_name as using_role,
    LEFT(query_text, 300) as query_preview,
    error_message,
    start_time
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_type = 'GRANT'
  AND execution_status = 'FAIL'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2x: Failed REVOKE Attempts

```sql
SELECT
    query_id,
    user_name as attempted_by,
    role_name as using_role,
    LEFT(query_text, 300) as query_preview,
    error_message,
    start_time
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_type = 'REVOKE'
  AND execution_status = 'FAIL'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

#### 2y: Failed User/Role Creation Attempts

```sql
SELECT
    query_id,
    user_name as attempted_by,
    role_name as using_role,
    query_type,
    LEFT(query_text, 300) as query_preview,
    error_message,
    start_time
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_type IN ('CREATE_USER', 'CREATE_ROLE', 'ALTER_USER', 'ALTER_ROLE')
  AND execution_status = 'FAIL'
  AND start_time >= DATEADD('day', -{{DAYS}}, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

---

### Step 3: Analyze Results

For each finding, evaluate:

| Risk Factor | High Risk Indicator | Relevant Queries |
|-------------|---------------------|------------------|
| Privileged Role | ACCOUNTADMIN, SECURITYADMIN, ORGADMIN grants | 2g–2k |
| Self-Grant | User grants privileges to themselves | 2l |
| After Hours | Changes outside business hours | All QUERY_HISTORY queries |
| Unusual Actor | Non-admin user making grants | 2g–2k, 2m |
| GRANT OPTION | Grant includes WITH GRANT OPTION | 2o |
| Ownership | Ownership transferred to suspicious role | 2p |
| New User | User created with privileged default role | 2u |
| Service Account | New service account with broad access | 2v |
| Failed Attempts | Multiple failed grant attempts (probing) | 2w–2y |
| Rapid Changes | Many grants in short timeframe | 2m, 2n |
| Backdoor Pattern | New user + privileged grant + no MFA | 2u + 2k |
| Query Redaction | Detection gaps due to redacted query text | Prerequisites Check |

---

### Step 4: Present Findings

**⚠️ MANDATORY CHECKPOINT**: Present summary before recommendations.

**For ACCOUNT_USAGE:**
```
## Privilege Escalation Detection Summary

**Timeframe**: [date range]
**Scope**: Current Account
**Total suspicious events**: [count]

### Critical Findings (Privileged Role Grants)
[ACCOUNTADMIN, SECURITYADMIN, SYSADMIN grants]

### High-Risk Findings (Self-Grants, Ownership Changes)
[Self-grants, ownership transfers]

### Medium-Risk Findings (User/Role Changes)
[New users, role modifications]

### Failed Attempts (Potential Probing)
[Failed grants, blocked operations]

### Users with Excessive Privileges
[Users with multiple admin roles]
```

**For ORGANIZATION_USAGE:**
```
## Privilege Escalation Detection Summary

**Timeframe**: [date range]
**Scope**: Organization (all accounts)
**Total suspicious events**: [count]

### Critical Findings (Privileged Role Grants)
[ACCOUNTADMIN, SECURITYADMIN, SYSADMIN grants - include account_name]

### High-Risk Findings (Self-Grants, Ownership Changes)
[Self-grants, ownership transfers - include account_name]

### Findings by Account
[Aggregate by account_name]

### Medium-Risk Findings (User/Role Changes)
[New users, role modifications - include account_name]

### Failed Attempts (Potential Probing)
[Failed grants, blocked operations - include account_name]

### Users with Excessive Privileges
[Users with multiple admin roles - include account_name]
```

---

### Step 5: Recommend Actions

Based on findings, suggest:
- Privileged role grants to review and potentially revoke
- Self-grants to investigate and remove
- Service accounts to audit
- Ownership transfers to validate
- Failed attempts to correlate with other activity
- Access reviews to schedule
- (For ORGANIZATION_USAGE) Accounts requiring immediate attention

**⚠️ STOP**: Wait for user to decide on next steps.

---

## Stopping Points

- ✋ Step 1: After scope selection
- ✋ Step 4: After presenting findings
- ✋ Step 5: After recommendations

---

## Output

Summary report of privilege escalation activity with risk-ranked findings and remediation recommendations.

**ORGANIZATION_USAGE outputs include:**
- Account name in all findings
- Cross-account analysis
- Account-level aggregations