# Finding Database and Schema

You may need to find a database and schema to which you can deploy apps.

The most important criteria is a schema for which the user's role has "CREATE STAGE", "CREATE ARTIFACT REPOSITORY" and "CREATE APPLICATION SERVICE".

Finding a schema with these exact privileges can be difficult and time consuming. Instead, try to find a database or schema owned by the user's role.

**Important** - Do not run "SHOW GRANTS" or "SHOW SCHEMAS" since these queries can be very slow and do not effectively determine whether the user's role has permissions. Use the approaches below only.

## Database and Schema ownership
First, look for database + schema where both are owned by the current role.
```sql
 SELECT s.schema_name, s.catalog_name AS database_name
    FROM SNOWFLAKE.ACCOUNT_USAGE.SCHEMATA s
    JOIN SNOWFLAKE.ACCOUNT_USAGE.DATABASES d
      ON s.catalog_name = d.database_name
    WHERE (s.schema_owner = CURRENT_ROLE() AND d.database_owner = CURRENT_ROLE())
      AND s.deleted IS NULL
      AND d.deleted IS NULL
    ORDER BY s.catalog_name, s.schema_name
```

## Database or Schema ownership
If you can't find database + schema that are both owned by the current role, look for either schema that is owned by the role, or database owned by the role which you could create an "APPS" schema in.
```sql
 SELECT s.schema_name, s.catalog_name AS database_name
    FROM SNOWFLAKE.ACCOUNT_USAGE.SCHEMATA s
    JOIN SNOWFLAKE.ACCOUNT_USAGE.DATABASES d
      ON s.catalog_name = d.database_name
    WHERE (s.schema_owner = CURRENT_ROLE() OR d.database_owner = CURRENT_ROLE())
      AND s.deleted IS NULL
      AND d.deleted IS NULL
    ORDER BY s.catalog_name, s.schema_name
```

## Personal Database fallback
If you cannot find a database and schema with the previous methods, ask the user if it's okay to use personal database and schema, with an explanation of how the app behaves differently as outlined in `personal-databases.md`.
