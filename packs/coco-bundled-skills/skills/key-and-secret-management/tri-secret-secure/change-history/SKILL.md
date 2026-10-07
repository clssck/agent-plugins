---
parent_skill: tri-secret-secure
---

# Tri-Secret Secure Change History

View the history of Tri-Secret Secure (TSS) changes in your Snowflake account using the `SNOWFLAKE.ACCOUNT_USAGE.TRI_SECRET_SECURE_HISTORY` view.

## Prerequisites

### Role Verification (REQUIRED)

This view requires the **ACCOUNTADMIN** role or a role that has been granted the **SNOWFLAKE.SECURITY_VIEWER** database role.

**Execute:**

```sql
SELECT CURRENT_ROLE();
```

**If the current role is ACCOUNTADMIN**, proceed to the query step.

**If the current role is not ACCOUNTADMIN**, check whether the user has access to ACCOUNTADMIN or the SECURITY_VIEWER database role:

```sql
SHOW ROLES;
```

- If ACCOUNTADMIN appears, switch to it:
  ```sql
  USE ROLE ACCOUNTADMIN;
  ```
- If ACCOUNTADMIN does not appear, check for the SECURITY_VIEWER database role:
  ```sql
  SHOW GRANTS TO ROLE IDENTIFIER(CURRENT_ROLE());
  ```
  Look for a grant of `SNOWFLAKE.SECURITY_VIEWER`. If found, the current role can query the view — proceed.

- If neither ACCOUNTADMIN nor SECURITY_VIEWER access is available, **STOP** and inform the user:

> Your current role is `<role>` and you do not have access to the ACCOUNTADMIN role or the SNOWFLAKE.SECURITY_VIEWER database role.
> Viewing Tri-Secret Secure change history requires one of these roles.
> Please contact your Snowflake administrator to be granted the appropriate access.

## Workflow

### Step 1: Query Change History

**Execute:**

```sql
SELECT
    ID,
    REGISTERED_BY_USER_ID,
    CMK_ACTIVATION_STATUS,
    CMK_IDENTIFIER,
    IS_REGISTERED,
    REGISTERED_ON,
    ACTIVATED_ON,
    DISABLED_ON,
    UPDATED_ON
FROM SNOWFLAKE.ACCOUNT_USAGE.TRI_SECRET_SECURE_HISTORY
ORDER BY UPDATED_ON DESC NULLS LAST, REGISTERED_ON DESC NULLS LAST;
```

### Step 2: Present Results

**Present** the results to the user, interpreting each row:

| Column | Meaning |
|--------|---------|
| `ID` | Internal identifier for the TSS record |
| `REGISTERED_BY_USER_ID` | The user ID who registered the CMK |
| `CMK_ACTIVATION_STATUS` | Current status of the CMK (e.g., registered, activated, disabled) |
| `CMK_IDENTIFIER` | The CMK identifier (e.g., AWS KMS ARN, Azure Key Vault URI, or GCP Key Resource ID) |
| `IS_REGISTERED` | Whether the CMK is currently registered |
| `REGISTERED_ON` | Timestamp when the CMK was registered |
| `ACTIVATED_ON` | Timestamp when TSS was activated with this CMK |
| `DISABLED_ON` | Timestamp when TSS was deactivated for this CMK (NULL if still active) |
| `UPDATED_ON` | Timestamp of the most recent change to this record |

**If no rows are returned**, inform the user:

> No Tri-Secret Secure change history was found for this account. This means no CMK has been registered or activated in your account's history.

**Done.** Ask if the user needs further action.
