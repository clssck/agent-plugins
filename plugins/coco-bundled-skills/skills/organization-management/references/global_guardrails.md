# Global Guardrails & SQL Compatibility

These rules apply to ALL organization-management workflows. Follow them strictly to prevent execution errors and hallucinations.

## 1. Role Context — Check Before Switching

**Do not execute any SNOWFLAKE.ORGANIZATION_USAGE query until GLOBALORGADMIN is confirmed active.**
ORGANIZATION_USAGE views are only accessible under GLOBALORGADMIN. Queries will fail with "Schema does not exist or not authorized" if the role is not active.

However, **not all operations require GLOBALORGADMIN**.
- **Org Hub Insights & Organization Metadata:** Requires `GLOBALORGADMIN`.
- **Org Users & Groups (Create/Alter/Drop):** Requires `GLOBALORGADMIN`, `ACCOUNTADMIN`, `SECURITYADMIN`, or `USERADMIN` (in the org account).
- **Importing/Troubleshooting Org Users (in regular accounts):** Requires `ACCOUNTADMIN`.

**CRITICAL: Always check the current role BEFORE attempting to switch.** Follow this exact sequence:

```sql
SELECT CURRENT_ROLE();
```

- If the result is already `GLOBALORGADMIN` → **do NOT run USE ROLE**. Proceed directly to your queries.
- If the result is a different role → switch and confirm:
```sql
USE ROLE GLOBALORGADMIN;
SELECT CURRENT_ROLE();
```

**Never blindly run `USE ROLE GLOBALORGADMIN;` without checking first.** The role may already be active, and an unnecessary switch wastes a round-trip and can confuse the conversation context.

## 2. Warehouse Context — Auto-Detect Before Asking

Analytics queries (ORGANIZATION_USAGE views, RESULT_SCAN) require an active warehouse. **Do not ask the user which warehouse to use.** Instead, auto-detect:

```sql
SELECT CURRENT_WAREHOUSE();
```

- If `CURRENT_WAREHOUSE()` returns a warehouse name, proceed — no action needed.
- If `CURRENT_WAREHOUSE()` returns `NULL`, auto-select one:

```sql
SHOW WAREHOUSES;
```

Pick the first available warehouse from the results and activate it:

```sql
USE WAREHOUSE <first_available_warehouse>;
```

Only ask the user to specify a warehouse if `SHOW WAREHOUSES` returns zero results.

**SHOW commands** (`SHOW ACCOUNTS`, `SHOW ORGANIZATION ACCOUNTS`, `SHOW GRANTS OF ROLE ...`) do **not** require a warehouse.

## 3. SHOW Command Column Quoting
`SHOW` commands return **lowercase** column names. When using `TABLE(RESULT_SCAN(LAST_QUERY_ID()))` to query the output, you **must** double-quote column names.

```sql
SHOW ACCOUNTS;
SELECT "account_name", "edition", "region"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));
```
Writing `SELECT EDITION ...` (unquoted) will fail with `invalid identifier 'EDITION'` because Snowflake uppercases unquoted identifiers.

## 4. Account Inventory Fallback
**For any question about accounts** ("what accounts do we have", "list accounts", "account inventory"), always run `SHOW ACCOUNTS;` as the primary data source. This is the canonical command for account listing.

## 5. View Availability Rules
Only use base `SNOWFLAKE.ORGANIZATION_USAGE` views. Do not reference pre-aggregated views — they may not exist. **Only use views and columns from this exact list:**

- **ACCOUNTS** — columns (lowercase, must quote): `"account_name"`, `"edition"`, `"region"`
- **USERS**
- **ROLES**
- **GRANTS_TO_USERS** — columns: `ACCOUNT_NAME`, `GRANTEE_NAME`, `ROLE`, `DELETED_ON`
- **USAGE_IN_CURRENCY_DAILY** — columns: `USAGE_DATE`, `ACCOUNT_NAME`, `SERVICE_TYPE`, `USAGE_IN_CURRENCY`, `CURRENCY`
- **METERING_DAILY_HISTORY** — columns: `USAGE_DATE`, `SERVICE_TYPE`, `CREDITS_USED`, `CREDITS_BILLED`
- **WAREHOUSE_METERING_HISTORY** — columns: `START_TIME`, `END_TIME`, `WAREHOUSE_NAME`, `CREDITS_USED`, `CREDITS_USED_COMPUTE`, `CREDITS_USED_CLOUD_SERVICES`. **This view does NOT have `USAGE_DATE`** — use `START_TIME` for date filtering. Also does NOT have `ACCOUNT_NAME`, `ACCOUNT_LOCATOR`, or `REGION`.
- **STORAGE_DAILY_HISTORY** — columns: `USAGE_DATE`, `ACCOUNT_NAME`, `AVERAGE_BYTES`. **These are the ONLY columns.** Do NOT use `STORAGE_BYTES`, `STAGE_BYTES`, `FAILSAFE_BYTES`, `AVERAGE_STAGE_BYTES`, `AVERAGE_STORAGE_BYTES`, `AVERAGE_DATABASE_BYTES`, `AVERAGE_FAILSAFE_BYTES`, or any other column name — they do not exist and will error.
- **LOGIN_HISTORY** — columns: `EVENT_TIMESTAMP`, `USER_NAME`, `REPORTED_CLIENT_TYPE`, `FIRST_AUTHENTICATION_FACTOR`, `SECOND_AUTHENTICATION_FACTOR`, `IS_SUCCESS`, `ERROR_MESSAGE`, `EVENT_TYPE`
- **QUERY_HISTORY** — columns: `START_TIME`, `QUERY_TYPE`, `WAREHOUSE_NAME`, `EXECUTION_STATUS`, `TOTAL_ELAPSED_TIME`, `CREDITS_USED_CLOUD_SERVICES`
- **TRUST_CENTER_FINDINGS** — columns: `CREATED_ON`, `UPDATED_ON`, `ACCOUNT_NAME`, `SCANNER_ID`, `SEVERITY`, `STATE`, `AT_RISK_ENTITY_COUNT`, `FINDING_IDENTIFIER`
- **WAREHOUSE_LOAD_HISTORY** — columns: `START_TIME`, `END_TIME`, `WAREHOUSE_NAME`, `AVG_RUNNING`, `AVG_QUEUED_LOAD`
- **REMAINING_BALANCE_DAILY** — columns: `DATE`, `REMAINING_BALANCE`
- **CONTRACT_ITEMS** — columns: `CONTRACT_NUMBER`, `CURRENCY`, `AMOUNT`

## 6. Query Performance Restraints
`LOGIN_HISTORY` and `QUERY_HISTORY` are very large event tables. 
- **Never scan more than 7 days.** 
- **Always add `LIMIT`** (default 1000).

## 7. Zero Rows Handling
If queries against `TRUST_CENTER_FINDINGS`, `LOGIN_HISTORY` (failures), or `QUERY_HISTORY` (failures) return 0 rows, **treat this as a positive finding** (e.g., '0 Critical Violations found'). Do NOT apologize or assume the data is missing.

## 8. Currency Presentation — Prefer $$ Over Credits

When presenting cost or spend data, **always prefer dollar amounts over credits**:

- When querying `USAGE_IN_CURRENCY_DAILY`, use the `USAGE_IN_CURRENCY` column (dollar amount), **not** the `USAGE` column (credits). Always include the `CURRENCY` column in the SELECT and GROUP BY.
- Present monetary amounts with the currency symbol and code: e.g., `$1,234.56 USD`.
- Only fall back to credits when a view has no currency column (e.g., `WAREHOUSE_METERING_HISTORY` only has `CREDITS_USED`). In those cases, explicitly label the values as "credits" to avoid ambiguity.
- Never mix credits and dollars in the same table without clearly labeling which is which.

## 9. System Roles Definitions
- **GLOBALORGADMIN** - Preferred role for organization-level operations in multi-account organizations.
- **ORGADMIN** - Legacy role for operations at the organization level.
- **ACCOUNTADMIN** - Top-level role within a single account hierarchy.
