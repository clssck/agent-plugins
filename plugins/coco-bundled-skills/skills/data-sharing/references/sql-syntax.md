# Share SQL Syntax Reference

Complete SQL command reference for Snowflake share operations.

**Official Documentation:** [Snowflake Secure Data Sharing](https://docs.snowflake.com/en/user-guide/data-sharing-intro)

---

## Role Preflight

Before running any `CREATE SHARE` / `CREATE EXTERNAL LISTING` / `CREATE ORGANIZATION LISTING` / `ALTER LISTING` that touches auto-fulfillment, verify the current role holds the required privilege. Attempting the `CREATE` with an under-privileged role produces "Insufficient privileges" errors that look like they can be fixed by alternate syntax — they cannot.

**Privilege requirements by operation** — note that the privilege string is not always the same as the SQL command (notably, `CREATE EXTERNAL LISTING` requires the `CREATE LISTING` privilege; there is no `CREATE EXTERNAL LISTING` privilege):

| Operation | Required privilege(s) on ACCOUNT | Also needed |
|-----------|----------------------------------|-------------|
| `CREATE SHARE` | `CREATE SHARE` | — |
| `CREATE EXTERNAL LISTING` | `CREATE LISTING` | `CREATE SHARE` if the share is new |
| `CREATE ORGANIZATION LISTING` | `CREATE ORGANIZATION LISTING` | `CREATE SHARE` if the share is new |
| `ALTER LISTING` with `auto_fulfillment` | `MANAGE LISTING AUTO FULFILLMENT` | `OWNERSHIP` or `MODIFY` on the listing |
| `ALTER SHARE ... ADD/REMOVE ACCOUNTS` | — | `OWNERSHIP` or `MODIFY` on the share |

When granting, use `GRANT CREATE LISTING ON ACCOUNT ...` — that is the documented privilege name. When querying `ACCOUNT_USAGE.GRANTS_TO_ROLES`, filter on `PRIVILEGE = 'CREATE LISTING'`.

```sql
-- Current role and its grants (two statements; substitute the literal role name
-- from the first query into the second — IDENTIFIER(CURRENT_ROLE()) is not valid here)
SELECT CURRENT_ROLE();
SHOW GRANTS TO ROLE <current_role>;

-- Find roles that already hold a specific privilege.
-- Primary: ACCOUNT_USAGE (authoritative, may lag up to ~2h). Use the SHOW GRANTS block below as a freshness fallback.
SELECT GRANTEE_NAME
FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
WHERE PRIVILEGE = 'CREATE LISTING'   -- or CREATE SHARE / CREATE ORGANIZATION LISTING / MANAGE LISTING AUTO FULFILLMENT
  AND GRANTED_ON = 'ACCOUNT'
  AND GRANTED_TO = 'ROLE'
  AND DELETED_ON IS NULL;

-- No-latency alternative: SHOW GRANTS ON ACCOUNT + RESULT_SCAN filter
SHOW GRANTS ON ACCOUNT;
SELECT "grantee_name"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "privilege" = 'CREATE LISTING'
  AND "granted_on" = 'ACCOUNT'
  AND "granted_to" = 'ROLE';
```

---

## CREATE SHARE

```sql
CREATE [ OR REPLACE ] SHARE [ IF NOT EXISTS ] <share_name>
  [ SECURE_OBJECTS_ONLY = { TRUE | FALSE } ]
  [ COMMENT = '<string>' ]
```

| `SECURE_OBJECTS_ONLY` | Behavior |
|-----------------------|----------|
| `TRUE` (default) | `GRANT SELECT ON VIEW` only on **secure** views. `GRANT USAGE ON FUNCTION` only on **secure** SQL/JavaScript UDFs. Tables, Iceberg tables, and other shareable types are unaffected. |
| `FALSE` | `GRANT SELECT ON VIEW` on **regular (non-secure)** views and `GRANT USAGE ON FUNCTION` on **non-secure** SQL/JavaScript UDFs are allowed. **Cannot be changed back to `TRUE` after set to `FALSE`.** See [Share data in non-secured views](https://docs.snowflake.com/en/user-guide/data-sharing-views). |

**Example (secure views only — default):**
```sql
CREATE SHARE sales_data_share
  COMMENT = 'Monthly sales data for partner analytics';
```

**Example (non-secure views allowed):**
```sql
CREATE SHARE allow_non_secure_views
  SECURE_OBJECTS_ONLY = FALSE
  COMMENT = 'Share views that require query optimization';
```

> **Note:** `SHOW SHARES` does not display `SECURE_OBJECTS_ONLY`. Record the value in the share `COMMENT` if you need to remember it later. See [Share data in non-secured views](https://docs.snowflake.com/en/user-guide/data-sharing-views).

---

## Shareable objects (Secure Data Sharing)

Per [About Secure Data Sharing](https://docs.snowflake.com/en/user-guide/data-sharing-intro), you can share the following Snowflake objects in a direct share:

- Databases
- Tables
- Dynamic tables
- External tables
- Externally managed and managed Iceberg tables
- Externally managed Delta Lake tables (with Delta Direct and catalog-linked databases)
- **Views**
  - Regular views
  - Secure views
  - Secure materialized views
  - Semantic views
- Cortex Search services
- **User-defined functions (UDFs)** (secure and non-secure)
- Models of type `USER_MODEL`, `CORTEX_FINETUNED`, or `DOC_AI`

All shared objects are **read-only** for consumers. No data is copied — sharing uses Snowflake's services layer.

Snowflake’s default for new shares is `SECURE_OBJECTS_ONLY = TRUE` (implicit): only secure views and secure SQL/JavaScript UDFs receive the usual grants until the share allows non-secure objects. **Secure views and secure UDFs are not required** — regular views and non-secure UDFs are supported after relaxing the share. The product docs describe when teams often choose secure objects versus non-secure sharing ([Use secure objects to control data access](https://docs.snowflake.com/en/user-guide/data-sharing-secure-views), [Share data in non-secured views](https://docs.snowflake.com/en/user-guide/data-sharing-views)). Do not apply `ALTER VIEW` / `ALTER FUNCTION ... SET SECURE` without the user’s explicit approval.

## How to grant views and UDFs

The shareable-object list above is from the product overview. **Grant syntax** has additional rules ([GRANT … TO SHARE](https://docs.snowflake.com/en/sql-reference/sql/grant-privilege-share)):

| Object | Option A (default share) | Option B (non-secure object) |
|--------|--------------------------|------------------------------|
| Views | `ALTER VIEW ... SET SECURE`, then `GRANT SELECT ON VIEW` on a default share (e.g. `sales_data_share`) | `SECURE_OBJECTS_ONLY = FALSE` on the share (create or `ALTER SHARE`), then `GRANT SELECT ON VIEW` — see [Share data in non-secured views](https://docs.snowflake.com/en/user-guide/data-sharing-views) |
| UDFs (SQL/JavaScript) | `ALTER FUNCTION ...(<arg_types>) SET SECURE`, then `GRANT USAGE ON FUNCTION` on a default share | Same as views: relax the share, then `GRANT USAGE ON FUNCTION` (full signature). Each overload needs its own `GRANT`. Python, Java, and Scala UDFs cannot be shared. |

When `GRANT SELECT ON VIEW` or `GRANT USAGE ON FUNCTION` fails because the object is not secure, present both options below. Do not run `ALTER VIEW` / `ALTER FUNCTION ... SET SECURE` unless the user explicitly approves changing the object.

**Option A:** Convert to secure (recommended)

```sql
-- View (default share from CREATE SHARE example above)
ALTER VIEW analytics_db.public.partner_summary SET SECURE;
GRANT SELECT ON VIEW analytics_db.public.partner_summary TO SHARE sales_data_share;

-- UDF (SQL/JavaScript — include full argument signature)
ALTER FUNCTION analytics_db.public.normalize_name(VARCHAR) SET SECURE;
GRANT USAGE ON FUNCTION analytics_db.public.normalize_name(VARCHAR) TO SHARE sales_data_share;
```

**Option B:** Allow non-secure objects (⚠️ cannot be undone)

At `CREATE SHARE` (matches the `allow_non_secure_views` example above):

```sql
CREATE OR REPLACE SHARE allow_non_secure_views
  SECURE_OBJECTS_ONLY = FALSE
  COMMENT = 'Share views that require query optimization';

GRANT USAGE ON DATABASE analytics_db TO SHARE allow_non_secure_views;
GRANT USAGE ON SCHEMA analytics_db.public TO SHARE allow_non_secure_views;
GRANT SELECT ON VIEW analytics_db.public.partner_summary TO SHARE allow_non_secure_views;
GRANT USAGE ON FUNCTION analytics_db.public.normalize_name(VARCHAR) TO SHARE allow_non_secure_views;
```

**Convert an existing default share**, then retry grant(s) — same `ALTER SHARE` covers views and UDFs on that share:

```sql
ALTER SHARE sales_data_share SET SECURE_OBJECTS_ONLY = FALSE;
GRANT SELECT ON VIEW analytics_db.public.partner_summary TO SHARE sales_data_share;
GRANT USAGE ON FUNCTION analytics_db.public.normalize_name(VARCHAR) TO SHARE sales_data_share;
```

---

## GRANT to SHARE

### Database Access (MUST be first)

```sql
GRANT USAGE ON DATABASE <database_name> TO SHARE <share_name>;
```

### Cross-Database References (REFERENCE_USAGE)

When a view references objects from another database (including through nested views), grant `REFERENCE_USAGE`:

```sql
-- Required when view in DB_A references tables/views/policies in DB_B
GRANT REFERENCE_USAGE ON DATABASE <other_database> TO SHARE <share_name>;
```

**Recursive Dependency Analysis:**

```sql
-- Get ALL dependencies recursively (nested views, tables, functions)
SELECT DISTINCT REFERENCED_DATABASE, REFERENCED_OBJECT_NAME, REFERENCED_OBJECT_DOMAIN
FROM TABLE(
  SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES(
    '<database>.<schema>.<view_name>',
    'VIEW'
  )
)
ORDER BY REFERENCED_DATABASE;

-- Find all databases needing REFERENCE_USAGE
SELECT DISTINCT REFERENCED_DATABASE
FROM TABLE(
  SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES(
    '<database>.<schema>.<view_name>',
    'VIEW'
  )
)
WHERE REFERENCED_DATABASE != '<primary_share_database>';

-- Alternative: Get direct references only (one level)
SELECT * FROM TABLE(GET_OBJECT_REFERENCES(
  DATABASE_NAME => '<database>',
  SCHEMA_NAME => '<schema>',
  OBJECT_NAME => '<view_name>'
));

-- Check for policies on referenced objects
SELECT DISTINCT POLICY_DB
FROM SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES
WHERE REF_DATABASE_NAME = '<database>'
  AND REF_SCHEMA_NAME = '<schema>';
```

**When to use:**
- View references tables from another database
- View references other views from another database (nested views)
- Any object in dependency chain has policies from another database
- Object has row access policies defined in another database
- Object has masking policies defined in another database

**Note:** `REFERENCE_USAGE` allows the share to reference objects but does NOT expose them directly to consumers.

### Schema Access (MUST be second)

```sql
GRANT USAGE ON SCHEMA <database_name>.<schema_name> TO SHARE <share_name>;
```

### Object Access (MUST be last)

**Tables:**
```sql
-- Single table
GRANT SELECT ON TABLE <db>.<schema>.<table> TO SHARE <share_name>;

-- All tables in schema
GRANT SELECT ON ALL TABLES IN SCHEMA <db>.<schema> TO SHARE <share_name>;
```

**Dynamic Tables:**
```sql
GRANT SELECT ON DYNAMIC TABLE <db>.<schema>.<dt_name> TO SHARE <share_name>;
```

**External Tables:**
```sql
GRANT SELECT ON EXTERNAL TABLE <db>.<schema>.<ext_table> TO SHARE <share_name>;
```

**Iceberg Tables:**
```sql
GRANT SELECT ON ICEBERG TABLE <db>.<schema>.<iceberg_table> TO SHARE <share_name>;
```

**Views:**
```sql
-- Option A: secure view on default share. Option B: non-secure view after SECURE_OBJECTS_ONLY = FALSE (see "How to grant views and UDFs")
GRANT SELECT ON VIEW <db>.<schema>.<view> TO SHARE <share_name>;

-- Bulk grant all views in a schema (non-secure views require Option B on the share)
GRANT SELECT ON ALL VIEWS IN SCHEMA <db>.<schema> TO SHARE <share_name>;

-- Materialized views
GRANT SELECT ON MATERIALIZED VIEW <db>.<schema>.<mv> TO SHARE <share_name>;
```

**Semantic Views:**
```sql
GRANT SELECT ON SEMANTIC VIEW <db>.<schema>.<semantic_view> TO SHARE <share_name>;
```

**Functions (SQL/JavaScript UDFs):**
```sql
-- Option A: secure UDF on default share. Option B: non-secure UDF after SECURE_OBJECTS_ONLY = FALSE (see "How to grant views and UDFs")
-- Include the full argument signature; each overload needs its own GRANT
GRANT USAGE ON FUNCTION <db>.<schema>.<func_name>(<arg_types>) TO SHARE <share_name>;
```

**Cortex Search Services:**
```sql
GRANT USAGE ON CORTEX SEARCH SERVICE <db>.<schema>.<service_name> TO SHARE <share_name>;
```

**Models:**
```sql
-- Supported types: USER_MODEL, CORTEX_FINETUNED, DOC_AI
GRANT USAGE ON MODEL <db>.<schema>.<model_name> TO SHARE <share_name>;
```

---

## ALTER SHARE

### Add Consumer Accounts

```sql
-- Single account
ALTER SHARE <share_name> ADD ACCOUNTS = <account_identifier>;

-- Multiple accounts
ALTER SHARE <share_name> ADD ACCOUNTS = <account1>, <account2>, <account3>;

-- With share restrictions override (for Business Critical → Standard)
ALTER SHARE <share_name> ADD ACCOUNTS = <account_identifier> 
  SHARE_RESTRICTIONS = FALSE;
```

### Remove Consumer Accounts

```sql
ALTER SHARE <share_name> REMOVE ACCOUNTS = <account_identifier>;
```

### Modify Share Properties

```sql
-- Allow non-secure objects (cannot be reversed)
ALTER SHARE <share_name> SET SECURE_OBJECTS_ONLY = FALSE;

-- Update comment
ALTER SHARE <share_name> SET COMMENT = '<new_comment>';
```

---

## REVOKE from SHARE

```sql
-- Revoke table access
REVOKE SELECT ON TABLE <db>.<schema>.<table> FROM SHARE <share_name>;

-- Revoke schema access (removes all object grants in schema)
REVOKE USAGE ON SCHEMA <db>.<schema> FROM SHARE <share_name>;

-- Revoke database access (removes entire share contents)
REVOKE USAGE ON DATABASE <db> FROM SHARE <share_name>;
```

---

## DESCRIBE SHARE

```sql
-- As provider (shows objects and consumers)
DESCRIBE SHARE <share_name>;

-- As consumer (shows available shares)
DESCRIBE SHARE <provider_account>.<share_name>;
```

---

## SHOW Commands

```sql
-- Show all shares you've created (as provider)
SHOW SHARES;

-- Show shares available to you (as consumer)
SHOW SHARES;

-- Show grants to a specific share
SHOW GRANTS TO SHARE <share_name>;

-- Show grants on a specific share
SHOW GRANTS OF SHARE <share_name>;
```

---

## DROP SHARE

```sql
DROP SHARE [ IF EXISTS ] <share_name>;
```

---

## Consumer Commands

**Create database from share:**
```sql
CREATE DATABASE <database_name> FROM SHARE <provider_account>.<share_name>;
```

**View shared databases:**
```sql
SHOW DATABASES;
-- Look for 'origin' column showing the share source
```

---

## Account Identifier Formats

| Format | Example | Notes |
|--------|---------|-------|
| Organization.Account | `MYORG.MYACCOUNT` | Preferred format |
| Account Locator | `ABC12345` | Legacy format |
| Full Locator | `ABC12345.us-west-2.aws` | Region-specific |

---

## Common Grant Patterns

### Share Single Table

```sql
CREATE SHARE customer_share COMMENT = 'Customer data for partner';
GRANT USAGE ON DATABASE SALES_DB TO SHARE customer_share;
GRANT USAGE ON SCHEMA SALES_DB.PUBLIC TO SHARE customer_share;
GRANT SELECT ON TABLE SALES_DB.PUBLIC.CUSTOMERS TO SHARE customer_share;
ALTER SHARE customer_share ADD ACCOUNTS = PARTNER_ORG.PARTNER_ACCOUNT;
```

### Share Entire Schema

```sql
CREATE SHARE analytics_share COMMENT = 'Analytics tables';
GRANT USAGE ON DATABASE ANALYTICS_DB TO SHARE analytics_share;
GRANT USAGE ON SCHEMA ANALYTICS_DB.REPORTS TO SHARE analytics_share;
GRANT SELECT ON ALL TABLES IN SCHEMA ANALYTICS_DB.REPORTS TO SHARE analytics_share;
-- Note: Future tables won't be automatically added
```

### Share Filtered Data via Secure View

```sql
-- Create secure view for filtered access
CREATE OR REPLACE SECURE VIEW SALES_DB.PUBLIC.PARTNER_CUSTOMERS AS
SELECT customer_id, name, region
FROM SALES_DB.PUBLIC.CUSTOMERS
WHERE region = 'WEST';

-- Share the secure view
CREATE SHARE filtered_share;
GRANT USAGE ON DATABASE SALES_DB TO SHARE filtered_share;
GRANT USAGE ON SCHEMA SALES_DB.PUBLIC TO SHARE filtered_share;
GRANT SELECT ON VIEW SALES_DB.PUBLIC.PARTNER_CUSTOMERS TO SHARE filtered_share;
```

### Share Regular (Non-Secure) Views and UDFs (Option B)

See **Option B** under [How to grant views and UDFs](#how-to-grant-views-and-udfs). After grants, add consumers if needed:

```sql
ALTER SHARE allow_non_secure_views ADD ACCOUNTS = PARTNER_ORG.PARTNER_ACCOUNT;
```

### Share Multiple Schemas

```sql
CREATE SHARE multi_schema_share COMMENT = 'Multiple schemas';
GRANT USAGE ON DATABASE MY_DB TO SHARE multi_schema_share;

-- Schema 1
GRANT USAGE ON SCHEMA MY_DB.SCHEMA_1 TO SHARE multi_schema_share;
GRANT SELECT ON ALL TABLES IN SCHEMA MY_DB.SCHEMA_1 TO SHARE multi_schema_share;

-- Schema 2
GRANT USAGE ON SCHEMA MY_DB.SCHEMA_2 TO SHARE multi_schema_share;
GRANT SELECT ON ALL TABLES IN SCHEMA MY_DB.SCHEMA_2 TO SHARE multi_schema_share;
```

---

## Resharing Imported Data / ULL

Reshare data the user **received** (from a marketplace listing, org listing, or direct share) by wrapping the source object in a `SECURE VIEW` in a database the user owns, then adding that view to a new share. Source can be either an imported database (`CREATE DATABASE imp_db FROM LISTING ...` / `FROM SHARE ...`) or a ULL referenced directly without mounting (e.g. `ORGDATACLOUD$INTERNAL$DAILY_REVENUE_RESHARE`). Detailed workflow: [reshare-imported.md](../workflows/reshare-imported.md).

**Documentation:** [Reshare incoming data as a resharer](https://docs.snowflake.com/en/collaboration/resharing-as-resharer), [Tutorial: resharing](https://docs.snowflake.com/en/collaboration/tutorial-resharing).

### Reshare a single object (imported DB source)

```sql
CREATE DATABASE reshared_db;
CREATE SCHEMA reshared_db.public;

CREATE OR REPLACE SECURE VIEW reshared_db.public.reshared_view AS
  SELECT * FROM imp_db.public.provider_table;

CREATE SHARE my_reshare COMMENT = 'Reshare of imp_db';
GRANT USAGE ON DATABASE reshared_db TO SHARE my_reshare;
GRANT USAGE ON SCHEMA reshared_db.public TO SHARE my_reshare;
GRANT SELECT ON VIEW reshared_db.public.reshared_view TO SHARE my_reshare;
```

### Reshare via ULL (mountless source)

```sql
-- Assumes reshared_db already exists (see the imported-DB pattern above for CREATE DATABASE / SCHEMA)
CREATE OR REPLACE SECURE VIEW reshared_db.public.daily_revenue AS
  SELECT * FROM ORGDATACLOUD$INTERNAL$DAILY_REVENUE_RESHARE.public.daily_revenue_table;
```

The ULL identifier is documented unquoted (the form Snowflake's tutorial uses); the quoted form `"ORGDATACLOUD$INTERNAL$DAILY_REVENUE_RESHARE"` is also valid. The rest of the share + grant statements are identical to the imported-DB pattern above.

### Discover all objects in an imported DB or ULL

```sql
SHOW TABLES IN DATABASE <source>;
SHOW VIEWS IN DATABASE <source>;
```

Both work against an imported database and against a ULL.

### Do NOT grant `REFERENCE_USAGE` on imported sources

Resharing differs from the cross-database view path documented under [GRANT to SHARE → Cross-Database References (REFERENCE_USAGE)](#cross-database-references-reference_usage):

| Path | Source database | Grant on source DB |
|---|---|---|
| Cross-DB view (you own both DBs) | A second database **you own** | `REFERENCE_USAGE` required |
| Reshare imported / ULL | An **imported** DB or ULL (you don't own it) | No — `REFERENCE_USAGE` cannot be granted on an imported database to a share. It is also not required for imported databases that allow resharing. |

For the reshare path, the share only needs `USAGE` on the user's target DB/schema and `SELECT` on the user's secure view.

---

## External Listing Commands

**Documentation:** [Managing listings using SQL](https://docs.snowflake.com/en/progaccess/listing-progaccess-about)

**For detailed workflow**, see: [external-listing.md](../workflows/external-listing.md)

> **For Organization Listings (Internal Marketplace)**, see the [org-listing](../workflows/org-listing.md) skill.

### CREATE EXTERNAL LISTING (Snowflake Marketplace)

```sql
CREATE EXTERNAL LISTING <listing_name>
  SHARE <share_name> AS
$$
title: "<title>"
subtitle: "<optional subtitle>"
description: |
  <description>

listing_terms:
  type: "OFFLINE"

targets:
  accounts: ["Org1.Account1", "Org2.Account2"]
  
usage_examples:
  - title: "Example Query"
    description: "How to use"
    query: "SELECT * FROM table"
$$ PUBLISH = FALSE REVIEW = FALSE;
```

### ALTER LISTING

```sql
-- Update listing manifest (replaces the FULL manifest - pass complete YAML)
ALTER LISTING <listing_name> AS $$
  title: "Updated Title"
  description: "Updated description"
$$;

-- Publish a draft listing
ALTER LISTING <listing_name> PUBLISH;

-- Unpublish a listing
ALTER LISTING <listing_name> UNPUBLISH;

-- Rename a listing
ALTER LISTING <listing_name> RENAME TO <new_listing_name>;
```

### Update refresh schedule on existing listing

**Required privilege:** `MANAGE LISTING AUTO FULFILLMENT` on ACCOUNT (in addition to `OWNERSHIP` or `MODIFY` on the listing).

**⚠️ `ALTER LISTING ... AS $$...$$` replaces the ENTIRE manifest.** You must pass the complete YAML — you cannot patch a single field. The correct pattern is: read the existing manifest with `DESCRIBE LISTING`, update only the `auto_fulfillment` block, then submit. Do not hand-write placeholder values for unrelated fields.

**Step 1 — read the existing manifest.** The YAML is in the `manifest_yaml` column of `DESCRIBE LISTING`. Use `REVISION = DRAFT` if you want to preserve unpublished draft edits:
```sql
DESCRIBE LISTING <listing_name>;
-- or, to include unpublished draft edits:
-- DESCRIBE LISTING <listing_name> REVISION = DRAFT;
-- Read the "manifest_yaml" column from the returned row.
```

**Step 2 — update only `auto_fulfillment.refresh_schedule` in the manifest YAML** (leave title, description, targets, locations, contacts, etc. exactly as returned).

**Step 3 — submit:**
```sql
ALTER LISTING <listing_name> AS
$$
<manifest from Step 1, with ONLY auto_fulfillment.refresh_schedule changed>
$$
PUBLISH = TRUE;
```

**New `refresh_schedule` values:**

| Schedule type | Value |
|---------------|-------|
| Interval | `"10 MINUTE"` … `"11520 MINUTE"` (max 8 days) |
| Cron | `"USING CRON <minute> <hour> <day_of_month> <month> <day_of_week> <IANA_timezone>"` — e.g. `"USING CRON 0 17 * * MON-FRI Europe/London"` |

**Documentation:** [Cron refresh schedule](https://docs.snowflake.com/en/collaboration/provider-listings-auto-fulfillment-configure-cron-refresh-schedule)

### ⚠️ Invalid ALTER syntaxes (do NOT generate)

These look plausible but are **not valid Snowflake syntax** and will fail. They are the most common trap when trying to update a refresh schedule:

```sql
-- ❌ WRONG - SET does not take refresh_schedule as a property
ALTER LISTING my_listing SET refresh_schedule = '60 MINUTE';

-- ❌ WRONG - SET does not take auto_fulfillment as a property
ALTER LISTING my_listing SET auto_fulfillment = ...;

-- ❌ WRONG - refresh schedule is a listing property, not a database property
ALTER DATABASE my_db SET refresh_schedule = '60 MINUTE';

-- ❌ WRONG - old API, see errors.md
ALTER LISTING my_listing SET STATE = PUBLISHED;

-- ❌ WRONG - cannot use SET and AS together
ALTER LISTING my_listing SET AS $$...$$;
```

**Recovery:** use the full-manifest `ALTER LISTING <name> AS $$...$$ PUBLISH = TRUE;` form shown above.

### SHOW / DESCRIBE LISTING

```sql
-- Show all listings
SHOW LISTINGS;

-- Show specific listing by pattern
SHOW LISTINGS LIKE '<listing_name>';

-- Describe listing details
DESCRIBE LISTING <listing_name>;
```

### DROP LISTING

```sql
-- Must unpublish first
ALTER LISTING <listing_name> UNPUBLISH;

-- Then drop
DROP LISTING IF EXISTS <listing_name>;
```

---

## External Listing Manifest Fields

**Required:**
- `title` - Listing title (max 110 characters)
- `description` - Full description

**Common Optional:**
- `subtitle` - Additional context
- `listing_terms` - OFFLINE or STANDARD
- `targets` - accounts or regions
- `usage_examples` - Sample queries
- `data_dictionary` - Object documentation
- `business_needs` - Use cases
- `support_contact` - Support email

> **For Organization Listing manifest fields**, see the [org-listing](../workflows/org-listing.md) skill.

