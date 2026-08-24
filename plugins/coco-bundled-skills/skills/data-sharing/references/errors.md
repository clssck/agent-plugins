# Common Errors and Troubleshooting

Quick reference for resolving common organizational listing errors.

## Top rule: never retry a privilege error

If a `CREATE SHARE` / `CREATE EXTERNAL LISTING` / `CREATE ORGANIZATION LISTING` / `ALTER LISTING` fails with any of:

- `Insufficient privileges`
- `not authorized`
- `does not have privilege`
- error codes 3001 or 3003

**STOP.** Do not retry with alternate syntax or guesses from public docs. The error means the current role is missing a required account-level privilege and no syntax variation will fix it. Instead, run the role preflight as a discovery step and ask the user to pick a role:

**Step 1 — check current state** (for context to show the user):
```sql
SELECT CURRENT_ROLE();
SHOW GRANTS TO ROLE <current_role>;
```

**Step 2 — find candidate roles for the *specific* privilege that failed**. Query only the one privilege (`CREATE SHARE` *or* `CREATE LISTING` *or* `CREATE ORGANIZATION LISTING` *or* `MANAGE LISTING AUTO FULFILLMENT` — not a broad list):

```sql
SELECT GRANTEE_NAME
FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
WHERE PRIVILEGE = '<the privilege that failed>'
  AND GRANTED_ON = 'ACCOUNT'
  AND GRANTED_TO = 'ROLE'
  AND DELETED_ON IS NULL;
```

`ACCOUNT_USAGE.GRANTS_TO_ROLES` can lag by up to ~2h. If the result is empty or looks stale (e.g. a grant was just added), fall back to the live path:

```sql
SHOW GRANTS ON ACCOUNT;
SELECT "grantee_name"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "privilege" = '<the privilege that failed>'
  AND "granted_on" = 'ACCOUNT'
  AND "granted_to" = 'ROLE';
```

**⚠️ Degraded path — both queries fail with privilege errors.** If BOTH the `ACCOUNT_USAGE` query AND the `SHOW GRANTS ON ACCOUNT` fallback error out with `Object ... does not exist or not authorized` or `Insufficient privileges to operate on account`, the current role can't read account metadata. This is common for genuinely low-privilege roles — the exact users this remediation is meant to rescue. In that case:
- Do not loop or retry.
- Ask the user directly: "Your current role can't read account grants. Do you know a role that has `<the privilege that failed>` on ACCOUNT (e.g. `ACCOUNTADMIN`, `SYSADMIN`, `ORGADMIN`, or an internal role)?" — accept free-text input.
- Or tell them to escalate: "Ask an admin to grant `<the privilege>` to your current role."

**Step 3 — present up to 3 candidates as a pick list** (if discovery succeeded). Prefer `ACCOUNTADMIN` / `SYSADMIN` / `ORGADMIN` when they appear in the result; otherwise take the first 3 rows. Offer these options to the user:

- Switch to `<CANDIDATE_1>`
- Switch to `<CANDIDATE_2>`
- Switch to `<CANDIDATE_3>`
- Enter a different role name (free text)
- Ask an admin to grant the privilege instead

**Do NOT** print a `USE ROLE <role_with_privilege>` template for the user to run manually — treat the role change as statement-scoped: prepend `USE ROLE <picked>;` to every subsequent SQL statement for the rest of the workflow, and re-run the preflight. Do not rely on a standalone `USE ROLE` to persist across tool calls in cortex CLI.

See the per-operation privilege table in `sql-syntax.md` → "Role Preflight".

---

## Error: "Share does not currently have a database"

**Full Error**: 
```
Share '<share_name>' does not currently have a database.
Database can be added using command 'GRANT USAGE ON DATABASE <NAME> TO SHARE <share_name>'.
```

**Cause**: Attempted to grant SELECT on tables before granting USAGE on parent database and schema.

**Fix**: Grant privileges in the correct order:
```sql
-- FIRST: Grant database usage
GRANT USAGE ON DATABASE <db> TO SHARE <share>;
-- SECOND: Grant schema usage
GRANT USAGE ON SCHEMA <db>.<schema> TO SHARE <share>;
-- LAST: Grant table access
GRANT SELECT ON TABLE <db>.<schema>.<table> TO SHARE <share>;
```

---

## Error: "Property 'DISTRIBUTION' must be specified"

**Cause**: Missing required `locations.access_regions` field in the manifest.

**Fix**: Add the locations configuration with at least your current region:
```yaml
locations:
  access_regions:
    - name: "PUBLIC.AWS_US_WEST_2"
```

Get your region with: `SELECT CURRENT_REGION();`

---

## Error: "Autofulfillment must be specified for listing to be available outside current region"

**Cause**: Targeting regions other than your current region without auto-fulfillment configuration.

**Fix**: Either:

1. Limit to your current region only, OR

2. Add auto-fulfillment configuration:
```yaml
locations:
  access_regions:
    - name: "ALL"
auto_fulfillment:
  refresh_type: "SUB_DATABASE"
  refresh_schedule: "60 MINUTE"
```

---

## Error: "Object does not exist or not authorized"

**Cause**: Missing USAGE grant on database or schema.

**Fix**: Ensure you grant USAGE on the database AND schema before granting privileges on objects:
```sql
GRANT USAGE ON DATABASE <db> TO SHARE <share>;
GRANT USAGE ON SCHEMA <db>.<schema> TO SHARE <share>;
-- Then grant object privileges
```

---

## Error: "Listing requires organization_targets"

**Cause**: Missing required `organization_targets` field in manifest.

**Fix**: Add `organization_targets` with either `discovery` or `access` configuration:
```yaml
organization_targets:
  discovery:
    - all_internal_accounts: true
  access:
    - all_internal_accounts: true
```

---

## Error: "support_contact is required"

**Cause**: When `discovery` is specified, contact fields are required.

**Fix**: Add both `support_contact` and `approver_contact` fields:
```yaml
support_contact: "support@company.com"
approver_contact: "approver@company.com"
```

---

## Error: "Invalid account name"

**Cause**: Account name in `organization_targets` doesn't exist in your organization.

**Fix**: Verify account names with:
```sql
SHOW ORGANIZATION ACCOUNTS;
```

Use the exact account name from the output.

---

## Error: "Insufficient privileges on share"

**Cause**: Role doesn't have required account-level privileges.

**Fix**: follow the canonical discovery + pick flow in "Top rule: never retry a privilege error" above. Use the appropriate `PRIVILEGE` filter from the table below when building the candidate query.

**Privilege to query, by failed operation:**

| Failed operation | Query `PRIVILEGE =` |
|------------------|---------------------|
| `CREATE SHARE` | `'CREATE SHARE'` |
| `CREATE EXTERNAL LISTING` | `'CREATE LISTING'` (the privilege is `CREATE LISTING`) |
| `CREATE ORGANIZATION LISTING` | `'CREATE ORGANIZATION LISTING'` |
| `ALTER LISTING` with `auto_fulfillment` | `'MANAGE LISTING AUTO FULFILLMENT'` |

**If the user chose "ask an admin"**, the admin runs the matching GRANT:
```sql
GRANT CREATE SHARE ON ACCOUNT TO ROLE <role>;
GRANT CREATE ORGANIZATION LISTING ON ACCOUNT TO ROLE <role>;
GRANT CREATE LISTING ON ACCOUNT TO ROLE <role>;  -- covers CREATE EXTERNAL LISTING
GRANT MANAGE LISTING AUTO FULFILLMENT ON ACCOUNT TO ROLE <role>;
-- Plus, if the role also needs object-level access:
GRANT USAGE ON DATABASE <db> TO ROLE <role> WITH GRANT OPTION;
GRANT USAGE ON SCHEMA <db>.<schema> TO ROLE <role> WITH GRANT OPTION;
```

---

## Error: "Insufficient privileges" when configuring auto-fulfillment

**Full Error** (example):
```
SQL access control error: Insufficient privileges to operate on account ...
```

**Cause**: Role lacks `MANAGE LISTING AUTO FULFILLMENT` on ACCOUNT. Required when the listing targets accounts in a different region, uses `access_regions: ALL`, or uses `all_internal_accounts: true` across a multi-region org.

**Fix** — discover candidates and ask the user to pick:

```sql
-- Find roles that have the privilege
SELECT GRANTEE_NAME
FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
WHERE PRIVILEGE = 'MANAGE LISTING AUTO FULFILLMENT'
  AND GRANTED_ON = 'ACCOUNT'
  AND GRANTED_TO = 'ROLE'
  AND DELETED_ON IS NULL;
```

Present up to 3 candidates (prefer `ACCOUNTADMIN` / `SYSADMIN` / `ORGADMIN`) as a pick list:
- Switch to `<CANDIDATE_1>`
- Switch to `<CANDIDATE_2>`
- Switch to `<CANDIDATE_3>`
- Enter a different role name (free text)
- Ask an admin to grant `MANAGE LISTING AUTO FULFILLMENT`

When the user picks, **treat the role change as statement-scoped** — prepend `USE ROLE <picked>;` to every subsequent SQL statement for the rest of the operation. Do not rely on a standalone `USE ROLE` to persist across tool calls in cortex CLI. If the user chose "ask an admin":
```sql
GRANT MANAGE LISTING AUTO FULFILLMENT ON ACCOUNT TO ROLE <your_role>;
```

**Do NOT** try to work around this by removing `auto_fulfillment` from the manifest if the listing actually needs it — the create will succeed but consumers in other regions will not be able to access the listing.

---

## Pre-Flight Validation Checklist

Before creating a share and listing, validate:

### 1. Verify Role Has Required Privileges

```sql
-- Check current role
SELECT CURRENT_ROLE();

-- Check if role can create shares
SHOW GRANTS TO ROLE <your_role>;
-- Look for: CREATE SHARE ON ACCOUNT
-- Look for: CREATE ORGANIZATION LISTING ON ACCOUNT

-- Check database/schema privileges
SHOW GRANTS ON DATABASE <database_name>;
SHOW GRANTS ON SCHEMA <database_name>.<schema_name>;
-- Look for: USAGE with GRANT OPTION
```

### 2. Verify Objects Exist

```sql
-- List tables in the schema you want to share
SHOW TABLES IN SCHEMA <database_name>.<schema_name>;

-- Get row counts to confirm data exists
SELECT '<table_name>' as table_name, COUNT(*) as row_count 
FROM <database_name>.<schema_name>.<table_name>;
```

### 3. Get Current Region

```sql
SELECT CURRENT_REGION();
-- Use this value in locations.access_regions as: PUBLIC.<region>
```

### 4. List Organization Accounts (if targeting specific accounts)

```sql
SHOW ORGANIZATION ACCOUNTS;
```

---

## Best Practices Checklist

1. ✅ **Grant privileges in correct order**: DATABASE → SCHEMA → OBJECTS

2. ✅ **Name shares descriptively**: Use names like `sales_analytics_share` not `share_1`

3. ✅ **Use views for row/column filtering**: Share views instead of base tables for access control

4. ✅ **Be aware of metadata visibility**: Granting database USAGE exposes all schema names

5. ✅ **Document thoroughly**: Use Markdown in descriptions

6. ✅ **Add usage examples**: Include sample queries

7. ✅ **Configure data dictionary**: For better discoverability

8. ✅ **Set appropriate access controls**: Follow least-privilege principles

9. ✅ **Use in-Snowflake approvals**: For audit trail - use `REQUEST_AND_APPROVE_IN_SNOWFLAKE`

10. ✅ **Always include locations**: The `locations.access_regions` field is required

11. ✅ **Verify before publishing**: Run `DESCRIBE SHARE` to confirm objects

12. ✅ **Validate role privileges first**: Check CREATE SHARE and CREATE ORGANIZATION LISTING privileges

---

## Error: "Cortex agent cannot be granted to a share"

**Full Error**:
```
Cortex agent cannot be granted to a share if it contains tools in different database, 
uses custom warehouse, or has an invalid agent spec
```

**Cause**: Cortex Agent uses features incompatible with sharing:
- Custom warehouse in agent spec or tools
- Tools in different databases
- Custom `query_timeout` settings

**Fix**: Share the underlying tables instead of the agent, OR modify the agent to:
- Remove custom warehouse settings
- Keep all tools in the same database
- Remove custom query_timeout

---

## Error: "Syntax error... unexpected 'AS'" when using ALTER LISTING

**Full Error**:
```
syntax error line 1 at position 47 unexpected 'AS'
```

**Cause**: Using `SET AS` together when updating manifest.

**Incorrect**:
```sql
ALTER LISTING my_listing SET AS $$...$$
```

**Fix**: Remove `SET` when using `AS` with YAML manifest:
```sql
ALTER LISTING my_listing AS $$...$$
```

---

## Error: "Object does not exist" in data_dictionary

**Full Error**:
```
Object 'TABLE_NAME' does not exist or not authorized
```

**Cause**: Using quoted identifiers in data_dictionary YAML.

**Fix**: Use UNQUOTED identifiers:
```yaml
data_dictionary:
  featured:
    database: SUNANDA_TEST  # No quotes
    objects:
      - schema: CALL_CENTER_OPS  # No quotes
        name: CALLS  # No quotes
        domain: TABLE
```

---

## Error: "Invalid identifier" in usage_examples

**Full Error**:
```
invalid identifier 'COLUMN_NAME'
```

**Cause**: SQL in usage_examples uses column names that don't exist in the actual table schema.

**Fix**:
1. Run `DESCRIBE TABLE` to get exact column names
2. Use fully qualified table names (DATABASE.SCHEMA.TABLE)
3. Validate SQL compiles before adding to manifest

```sql
-- Always check actual columns first
DESCRIBE TABLE DATABASE.SCHEMA.TABLE;
```

---

## Error: "Bulk grant on objects of type VIEW to SHARE is restricted"

**Cause**: Attempted to use `GRANT SELECT ON ALL VIEWS` to a share.

**Fix**: Grant SELECT on views individually:
```sql
-- ❌ WRONG - bulk grant on views not supported
GRANT SELECT ON ALL VIEWS IN SCHEMA db.schema TO SHARE my_share;

-- ✅ CORRECT - grant views individually
GRANT SELECT ON VIEW db.schema.view_1 TO SHARE my_share;
GRANT SELECT ON VIEW db.schema.view_2 TO SHARE my_share;
```

---

## Error: "Unsupported feature 'CREATE OR REPLACE DATA EXCHANGE LISTING'"

**Cause**: Attempted to use `CREATE OR REPLACE` for an organizational listing.

**Fix**: Use `ALTER LISTING` for existing listings:
```sql
-- ❌ WRONG - CREATE OR REPLACE not supported
CREATE OR REPLACE ORGANIZATION LISTING my_listing ...

-- ✅ CORRECT - use ALTER for existing listings
ALTER LISTING my_listing AS $$
...manifest...
$$;
```

---

## Error: "The old apis do not support organization listings"

**Cause**: Attempted to use `SET STATE = PUBLISHED` syntax.

**Fix**: Use `ALTER LISTING ... PUBLISH` instead:
```sql
-- ❌ WRONG - old API syntax
ALTER LISTING my_listing SET STATE = PUBLISHED;

-- ✅ CORRECT - use PUBLISH command
ALTER LISTING my_listing PUBLISH;

-- To unpublish:
ALTER LISTING my_listing UNPUBLISH;
```

---

## Error: "Listing with access_regions ALL requires auto_fulfillment"

**Cause**: Using `access_regions: ALL` without specifying `auto_fulfillment` configuration.

**Fix**: Always include `auto_fulfillment` when using ALL regions:
```yaml
locations:
  access_regions:
    - name: "ALL"
auto_fulfillment:
  refresh_type: "SUB_DATABASE"
  refresh_schedule: "10 MINUTE"  # Must match other listings on same database
```

---

## Error: Syntax error when updating refresh schedule

**Full Errors** (any of):
```
syntax error line 1 at position N unexpected 'refresh_schedule'
syntax error line 1 at position N unexpected 'auto_fulfillment'
unexpected 'SET' / unexpected 'AS'
```

**Cause**: Used one of the invalid syntaxes for modifying a listing's refresh schedule. `ALTER LISTING` does not expose `refresh_schedule` or `auto_fulfillment` as `SET` properties, and refresh schedule is a property of the **listing**, not the database.

**Incorrect** (all of these will fail — do NOT generate them):
```sql
-- ❌ refresh_schedule is not a SET property
ALTER LISTING my_listing SET refresh_schedule = '60 MINUTE';

-- ❌ auto_fulfillment is not a SET property
ALTER LISTING my_listing SET auto_fulfillment = ...;

-- ❌ refresh schedule belongs to the listing, not the database
ALTER DATABASE my_db SET refresh_schedule = '60 MINUTE';

-- ❌ cannot combine SET and AS
ALTER LISTING my_listing SET AS $$...$$;
```

**Fix**: use the full-manifest `AS $$...$$` form. `ALTER LISTING` replaces the entire manifest, so read the existing manifest first, then update **only** the `auto_fulfillment` block. Do NOT hand-write placeholder values for unrelated fields — that's what caused the syntax guesses in the first place.

**Step 1 — read the existing manifest.** The YAML is in the `manifest_yaml` column of `DESCRIBE LISTING`. Use `REVISION = DRAFT` if the listing has unpublished edits; otherwise the default (`PUBLISHED`) is fine:
```sql
DESCRIBE LISTING <listing_name>;
-- If there are unpublished draft edits you want to preserve:
-- DESCRIBE LISTING <listing_name> REVISION = DRAFT;
-- Then read the "manifest_yaml" column from the returned row.
```

**Step 2 — take the manifest output as-is and change only `auto_fulfillment.refresh_schedule`** (and `refresh_type` if needed). Leave every other field untouched.

**Step 3 — submit the updated manifest:**
```sql
ALTER LISTING <listing_name> AS
$$
<complete manifest from Step 1, with ONLY auto_fulfillment.refresh_schedule updated>
$$
PUBLISH = TRUE;
```

For a cron-based schedule, the new `refresh_schedule` value looks like `"USING CRON 0 17 * * MON-FRI Europe/London"`. For interval-based, `"60 MINUTE"` (min 10, max 11520).

Requires `MANAGE LISTING AUTO FULFILLMENT` on ACCOUNT plus `OWNERSHIP`/`MODIFY` on the listing. See [cron refresh docs](https://docs.snowflake.com/en/collaboration/provider-listings-auto-fulfillment-configure-cron-refresh-schedule).

---

## Error: "Refresh schedule mismatch with existing listing"

**Cause**: The `refresh_schedule` in `auto_fulfillment` doesn't match other listings on the same database.

**Fix**: Query existing listings on the same database and use the same refresh schedule:
```sql
DESCRIBE LISTING <existing_listing_name>;
-- Check the auto_fulfillment.refresh_schedule value
```

---

## Error: "Semantic view not found" or missing from SHOW VIEWS

**Cause**: Used `SHOW VIEWS` which does NOT include semantic views.

**Fix**: Use `SHOW SEMANTIC VIEWS` to find semantic views:
```sql
-- ❌ WRONG - does not show semantic views
SHOW VIEWS IN SCHEMA <database>.<schema>;

-- ✅ CORRECT - shows semantic views
SHOW SEMANTIC VIEWS IN SCHEMA <database>.<schema>;
```

---

## Error: "Invalid privilege type for semantic view" or "USAGE not supported"

**Cause**: Used `GRANT USAGE ON SEMANTIC VIEW` instead of `GRANT SELECT`.

**Fix**: Use `SELECT` privilege for semantic views (same as tables/views):
```sql
-- ❌ WRONG
GRANT USAGE ON SEMANTIC VIEW <db>.<schema>.<sv> TO SHARE <share_name>;

-- ✅ CORRECT
GRANT SELECT ON SEMANTIC VIEW <db>.<schema>.<sv> TO SHARE <share_name>;
```

