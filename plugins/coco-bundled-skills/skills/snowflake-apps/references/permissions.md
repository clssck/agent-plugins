# Snowflake Apps Role Permissions

Required grants for a role to deploy and run Snowflake Apps. Run these as `SYSADMIN` or `SECURITYADMIN`.

The admin experience (`/settings/account/apps` in Snowsight) provisions infrastructure and sets account parameters that the CLI reads during setup. The platform defaults are:
- **Database**: `SNOWFLAKE_APPS`
- **Schema**: `PUBLIC`
- **Query warehouse**: `SNOWFLAKE_APPS_QUERY_WH`

Admins can change any of these defaults by setting account parameters (`DEFAULT_SNOWFLAKE_APPS_DESTINATION_DATABASE`, `DEFAULT_SNOWFLAKE_APPS_DESTINATION_SCHEMA`, `DEFAULT_SNOWFLAKE_APPS_QUERY_WAREHOUSE`, and others). See the parameter table in `references/debugging.md` for the full list.

After running `snow app setup`, all resolved values are written into `snowflake.yml`. That file is the source of truth for which database, schema, and warehouse the app is actually using. Before granting permissions, check `snowflake.yml` (specifically `identifier.database`, `identifier.schema`, and `query_warehouse`) to confirm the actual values, especially if the account has non-default configuration.

Compute pools, external access integrations, and image repositories are managed automatically by the platform. Replace `<ROLE>` with the target role name.

## Full Grant List

```sql
-- Replace <database>, <schema>, <warehouse> with values from snowflake.yml
-- (identifier.database, identifier.schema, query_warehouse).
-- Platform defaults: SNOWFLAKE_APPS / PUBLIC / SNOWFLAKE_APPS_QUERY_WH

-- Database and schema
GRANT USAGE ON DATABASE <database> TO ROLE <ROLE>;
GRANT USAGE ON SCHEMA <database>.<schema> TO ROLE <ROLE>;
GRANT CREATE APPLICATION SERVICE ON SCHEMA <database>.<schema> TO ROLE <ROLE>;
GRANT CREATE ARTIFACT REPOSITORY ON SCHEMA <database>.<schema> TO ROLE <ROLE>;
GRANT CREATE STAGE ON SCHEMA <database>.<schema> TO ROLE <ROLE>;

-- Warehouse
GRANT USAGE ON WAREHOUSE <warehouse> TO ROLE <ROLE>;
```

## Object Reference

| Object | Type | Privilege | Purpose |
|--------|------|-----------|---------|
| `<database>` | Database | `USAGE` | Access the apps database |
| `<database>.<schema>` | Schema | `USAGE` | Access the deployment schema |
| `<database>.<schema>` | Schema | `CREATE APPLICATION SERVICE` | Create app services during deploy |
| `<database>.<schema>` | Schema | `CREATE ARTIFACT REPOSITORY` | Create the artifact repository during deploy |
| `<database>.<schema>` | Schema | `CREATE STAGE` | Create and own the per-app code stage during deploy |
| `<warehouse>` | Warehouse | `USAGE` | Run queries during deployment |

## Post-Deploy Privileges

Grant these on a deployed application service to share access or delegate operations:

```sql
-- Allow another role to view the service in SHOW APPLICATION SERVICES and access its endpoint
GRANT USAGE ON APPLICATION SERVICE <database>.<schema>.<app_name> TO ROLE <ROLE>;

-- Allow another role to view logs and DESCRIBE
GRANT MONITOR ON APPLICATION SERVICE <database>.<schema>.<app_name> TO ROLE <ROLE>;

-- Allow another role to suspend, resume, upgrade, and alter properties
GRANT OPERATE ON APPLICATION SERVICE <database>.<schema>.<app_name> TO ROLE <ROLE>;

-- Allow another role to read/write the artifact repository (deploying role already has access as owner)
GRANT READ, WRITE ON ARTIFACT REPOSITORY <database>.<schema>.<repo_name> TO ROLE <ROLE>;
```

Privilege summary:

| Privilege | Enables |
|-----------|---------|
| `USAGE` | Visibility in `SHOW APPLICATION SERVICES`; access to the public endpoint URL |
| `MONITOR` | `DESCRIBE`, `SYSTEM$GET_APPLICATION_SERVICE_LOGS`, `SYSTEM$GET_APPLICATION_SERVICE_EVENT_TABLE_DATA` |
| `OPERATE` | `SUSPEND`, `RESUME`, `UPGRADE`, `ALTER SET/UNSET` |
| `OWNERSHIP` | All of the above plus `DROP` and `RENAME TO` |

## Caller Grants (required for caller's rights)

Caller's rights itself needs no configuration — Snowflake enables it for every App Runtime app. But a caller's-rights session is still restricted to what the app's **owning role** has been authorized to do on the caller's behalf. Without caller grants, queries fail even though the calling user has access to the data directly.

Grant these to the role that owns the application service, not to the end users. Requires `ACCOUNTADMIN` or a role with `MANAGE CALLER GRANTS`:

```sql
GRANT CALLER USAGE ON DATABASE <data_db> TO ROLE <app_owner_role>;
GRANT INHERITED CALLER USAGE ON ALL SCHEMAS IN DATABASE <data_db> TO ROLE <app_owner_role>;
GRANT INHERITED CALLER SELECT ON ALL TABLES IN DATABASE <data_db> TO ROLE <app_owner_role>;
GRANT CALLER USAGE ON WAREHOUSE <query_warehouse> TO ROLE <app_owner_role>;

-- Verify
SHOW CALLER GRANTS TO ROLE <app_owner_role>;
```

Grant at the database or schema level rather than per-object where you can. `INHERITED` variants cover current and future objects under the container.

The warehouse grant is easy to miss: without it, any caller's-rights query that needs compute fails even when the table grants are correct.

For diagnosing caller's-rights failures, see `references/debugging.md`.

## Notes

- `DATABASE` and `WAREHOUSE` grants require `SYSADMIN` or `SECURITYADMIN`. Schema and stage privileges can be granted by the role that owns the database/schema.
- The deploying role automatically owns any artifact repository it creates. `GRANT READ, WRITE ON ARTIFACT REPOSITORY` is for delegating access to other roles post-deploy; see Post-Deploy Privileges above.
- `CREATE STAGE` is required so the deploying role creates and owns the per-app code stage. If a code stage was previously created by a different role, drop it before redeploying so the publisher role can recreate it with correct ownership.
- **Role design:** `<ROLE>` should be a dedicated publisher role (e.g. `APP_PUBLISHER`). User roles should have `APP_PUBLISHER` granted as a secondary role rather than receiving these grants directly. Deploy using a connection with `APP_PUBLISHER` as the primary role and secondary roles disabled. This ensures all created objects (stages, services) are owned by `APP_PUBLISHER`, and SPCS owner's rights tokens in the running service resolve to that role.
