---
name: consumer-share-migration
description: "Help a consumer migrate from a traditional data share database to a declarative sharing native application with zero downtime and no query changes"
parent_skill: declarative-sharing
---

# Consumer Migration: Data Share to Declarative App

Guide a consumer through migrating from a traditional data share database to a new declarative sharing native application. The goal is a "drop-in replacement" — existing queries, dashboards, and reports continue working without modification because the new app takes the original database name.

## When to Load

Parent skill routes here when:
- Consumer has a database created from a traditional data share and the provider has published a new declarative app
- Consumer wants to upgrade/migrate from a share to a native application
- Consumer asks about replacing a data share with an app
- Consumer mentions a listing name or app package and wants to switch from their existing share database

## Prerequisites

The migration requires:
1. **Old share database name** — the database created from the existing traditional share (e.g., `DATA_SHARE`)
2. **New app source** — either:
   - A **listing name** for cross-account install (e.g., `g_provider_org.g_provider_acct.my_app_listing`)
   - An **application package name** for same-account install (e.g., `MY_APP_PACKAGE`)
3. **Role with sufficient privileges** — needs `OWNERSHIP` on the shared database (to rename it) and `CREATE APPLICATION` on the account. `ACCOUNTADMIN` is the simplest approach.

## Workflow

### Step 1: Gather Information & Inspect Current State

**Ask** the user for the old share database name and the new app listing/package name. **Skip** if already provided or user said to proceed end-to-end.

Once you have both values, establish naming:
- `OLD_DB` = the current share database name
- `TEMP_APP` = `OLD_DB` + `_APP` (temporary name during migration)
- `DEPRECATED_DB` = `OLD_DB` + `_DEPRECATED` (name for old DB after swap)

**Inspect the old share database** to understand what needs migrating:

1. **Check schemas and tables** — understand the data footprint:
```sql
SHOW SCHEMAS IN DATABASE <OLD_DB>;
```
For each user schema (skip INFORMATION_SCHEMA):
```sql
SHOW TABLES IN SCHEMA <OLD_DB>.<SCHEMA>;
SHOW VIEWS IN SCHEMA <OLD_DB>.<SCHEMA>;
```

2. **Check imported privilege grants** — find roles with all-access:
```sql
SHOW GRANTS ON DATABASE <OLD_DB>;
```
Look for rows where `privilege` = `USAGE` and `granted_to` = `ROLE` (this is how IMPORTED PRIVILEGES appear). Ignore `OWNERSHIP` grants.

3. **Check database roles** — find granular role assignments:
```sql
SHOW DATABASE ROLES IN DATABASE <OLD_DB>;
```
For each database role found, discover which account roles it's granted to:
```sql
SHOW GRANTS ON DATABASE ROLE <OLD_DB>.<DB_ROLE_NAME>;
```
Look for rows where `privilege` = `USAGE` and `granted_to` = `ROLE`.

Record everything you find — you will present a summary later.

### Step 2: Install the New App with a Temporary Name

Install the new application using the temporary name. The original database remains active during this step — no disruption.

**From a listing** (cross-account):
```sql
CREATE APPLICATION <TEMP_APP> FROM LISTING '<LISTING_NAME>';
```

**From an application package** (same-account):
```sql
CREATE APPLICATION <TEMP_APP> FROM APPLICATION PACKAGE <PACKAGE_NAME>;
```

### Step 3: Migrate Grants

Copy all permissions from the old share database to the new application.

**Imported privileges** — for each role found in Step 1 with USAGE on the database:
```sql
GRANT IMPORTED PRIVILEGES ON APPLICATION <TEMP_APP> TO ROLE <ROLE_NAME>;
```

**Database roles → Application roles** — for each database role and its grantees found in Step 1:
```sql
GRANT APPLICATION ROLE <TEMP_APP>.<DB_ROLE_NAME> TO ROLE <GRANTEE_ROLE>;
```

**Note**: If a `GRANT APPLICATION ROLE` fails because the application role doesn't exist, the provider may not have created an equivalent app role for every database role. Record the failure and report it in the summary — do not stop the migration.

### Step 4: Validate & Present Summary

**Before any destructive action**, validate the new app and present a clear summary to the user.

**Validate the new app:**
1. Check that the app was created and has the expected schemas:
```sql
SHOW SCHEMAS IN APPLICATION <TEMP_APP>;
```
2. Verify grants were applied:
```sql
SHOW GRANTS ON APPLICATION <TEMP_APP>;
```
3. If the app has application roles, verify they were granted correctly:
```sql
SHOW APPLICATION ROLES IN APPLICATION <TEMP_APP>;
```

**Present a migration summary** to the user. Include:
- **Old database**: name, schemas, tables/views found
- **New application**: name, schemas available, source (listing or package)
- **Grants migrated**: list each role and what was granted (imported privileges and/or application roles)
- **Any issues**: roles that couldn't be migrated, missing application roles, etc.
- **What happens next**: explain the rename swap — old DB becomes `_DEPRECATED`, app takes the original name, then deprecated DB is dropped
- **Streams warning**: if applicable — streams on old share tables will become stale after migration and need to be recreated (streams are bound to internal object IDs, not names)

**STOP**: Wait for user confirmation before proceeding with the rename swap.

**Skip stopping point** if user said to proceed end-to-end or skip confirmations.

### Step 5: Rename Swap

Execute both renames back-to-back for minimal downtime:

```sql
ALTER DATABASE <OLD_DB> RENAME TO <DEPRECATED_DB>;
```
```sql
ALTER APPLICATION <TEMP_APP> RENAME TO <OLD_DB>;
```

Between these two statements, queries using the old database name will fail. Execute them as quickly as possible.

### Step 6: Post-Swap Validation

Validate that the migration is live and working:

1. **Confirm the application has the correct name:**
```sql
SHOW APPLICATIONS LIKE '<OLD_DB>';
```

2. **Verify grants survived the rename:**
```sql
SHOW GRANTS ON APPLICATION <OLD_DB>;
```

3. **Spot-check data access** — pick a schema/table from Step 1 and query it:
```sql
SELECT * FROM <OLD_DB>.<SCHEMA>.<TABLE> LIMIT 5;
```

If anything looks wrong, report it and **do not** drop the deprecated database — the user can rename things back.

### Step 7: Drop Deprecated Database

If validation passes:

```sql
DROP DATABASE <DEPRECATED_DB>;
```

Report the migration as complete.

## Streams Warning

If the consumer has streams on tables from the old share, those streams will become stale after migration. Streams are bound to internal object IDs, not names — the new application's tables are new objects.

**Fix**: Recreate affected streams after migration:
```sql
CREATE OR REPLACE STREAM <STREAM_NAME> ON TABLE <OLD_DB>.<SCHEMA>.<TABLE>;
```

Mention this in the Step 4 summary if the user has mentioned streams, or proactively check:
```sql
SHOW STREAMS IN ACCOUNT;
```

## Stopping Points

- After Step 1: Confirm share DB name and listing/package name (skip if already provided)
- After Step 4: Present migration summary and get confirmation before rename swap
- After Step 6: If validation fails, stop and report — do not drop deprecated DB

**Skip all stopping points** when user says to proceed end-to-end or skip confirmations. When skipping, still present the summary (Step 4) as informational output — just don't wait for confirmation.

## Output

A fully migrated consumer environment where:
- The new declarative app runs under the original database name
- All existing queries, dashboards, and reports work without modification
- All role-based permissions are preserved (imported privileges and application roles)
- The old deprecated database is cleaned up
- A migration summary was presented showing what was migrated and any issues

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `Database '...' does not exist` | The old database name is wrong. Run `SHOW DATABASES;` to find the exact name |
| `Not authorized` | Need `ACCOUNTADMIN` or a role with `OWNERSHIP` on the database and `CREATE APPLICATION` privilege |
| `Application '...' does not exist` | The listing name or package name is incorrect. Check with the provider |
| `Application role '...' does not exist` | The provider may not have created equivalent app roles for all database roles. Report this to the user — they may need to contact their provider |
| Queries fail after rename | Verify Step 5 completed both renames. Check `SHOW APPLICATIONS;` to confirm the app has the correct name |
| Streams are stale | Expected — see Streams Warning above. Recreate affected streams |
| Need to rollback | If the deprecated DB still exists: `ALTER APPLICATION <OLD_DB> RENAME TO <TEMP_APP>; ALTER DATABASE <DEPRECATED_DB> RENAME TO <OLD_DB>;` |
