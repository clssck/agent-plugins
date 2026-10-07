---
name: shared-data
description: "Share data content with consumers in a Snowflake Native App: tables inside the package, data from external databases via REFERENCE_USAGE. Triggers: share data, share table, secure view, grant data, REFERENCE_USAGE, shared content, proxy view, share database, share views, data content."
parent_skill: native-app-provider
---

# Shared Data Content

> **⚠️ MANDATORY**: If your system prompt mentions Snowsight, load [`../references/native-apps-snowsight.md`](../references/native-apps-snowsight.md) before doing anything else.

## When to Load

From the root `native-app-provider` skill when the user wants to share data with consumers.

## Overview

Providers share data with consumers through the app. Consumers **cannot** access shared content directly — the setup script must create secure views in a versioned schema and grant them to application roles.

Shared data content is **not versioned** — all versions of an app see the same underlying data. However, the views defined in versioned schemas ARE versioned, so column changes don't leak until a new version is created.

## Step 1: Identify the Data Source

**STOP**: Ask the user for the application package name and the tables/views they want to share:

```
To share data with consumers, I need:

1. Application package name (e.g., my_app_package)
2. Tables or views to share - provide fully qualified names if possible
   (e.g., my_app_package.analytics.sales, other_db.public.customers)
```

Wait for user response.

### Auto-Detection

Classify each table as inside or outside the application package:

**Fully qualified names** (`database.schema.object`): Compare the database portion (first segment) against the application package name. If they match → **Path A** (inside). If they differ → **Path B** (outside). No SQL query needed.

**Unqualified names** (e.g., `schema.table` or just `table`): Resolve using the session context:

```sql
SELECT CURRENT_DATABASE(), CURRENT_SCHEMA();
```

Use the session's current database to qualify the name, then compare against the package name as above.

**Present the result** to the user:

```
| Table/View | Database | Location |
|------------|----------|----------|
| <schema>.<name> | <app_package> | Inside package |
| <schema>.<name> | <database> | Outside package |

Does this look correct?
```

**STOP**: Wait for user confirmation. If the user corrects any classification, adjust accordingly.

If some objects are inside and others outside, handle each group separately — run Path A for inside objects first, then Path B for outside objects. **STOP** after completing each path to present results before starting the next.

## Decision Tree

- **Inside package** → Path A: Grant to package + setup script views
- **Outside package** → Path B: `GRANT REFERENCE_USAGE ON DATABASE` to the package + proxy views in the package + setup script views

All paths converge: Versioned schema → Secure views → Grant to application roles

## Step 2: Confirm Consumer-Facing Schema, View, and Columns

**STOP**: Ask the user how they want consumers to access the data:

```
What schema, view name, and columns should consumers use to access this data?

1. Schema name (e.g., core)
2. View name (e.g., products)
3. Columns to expose (e.g., id, name, price — or * for all)
```

Wait for user response, then proceed with the appropriate path below.

---

## Path A: Data Inside the Application Package

Use this when the data already exists in (or will be created in) a schema owned by the application package.

### A1. Verify Data Exists in the Package

Check whether the schema and table/view already exist:

```sql
SHOW SCHEMAS LIKE '<schema>' IN APPLICATION PACKAGE <pkg>;
SHOW TABLES LIKE '<name>' IN SCHEMA <pkg>.<schema>;
```

If both exist, proceed to A2. If not, help the user create the missing schema and table/view using the names they provided.

### A2. Grant the Data to the Application Package

```sql
-- Must grant the schema first
GRANT USAGE ON SCHEMA <pkg>.<schema>
  TO SHARE IN APPLICATION PACKAGE <pkg>;

-- Then grant the table
GRANT SELECT ON TABLE <pkg>.<schema>.<name>
  TO SHARE IN APPLICATION PACKAGE <pkg>;
```

After this, the data is part of the package but still **not visible** to consumers. The setup script must expose it.

### A3. Expose via Setup Script

Add to the setup script using the schema, view, and columns confirmed in Step 2:

```sql
CREATE APPLICATION ROLE IF NOT EXISTS <app_role>;

CREATE OR ALTER VERSIONED SCHEMA <versioned_schema>;
GRANT USAGE ON SCHEMA <versioned_schema> TO APPLICATION ROLE <app_role>;

-- View over the shared table (references the package schema)
CREATE VIEW IF NOT EXISTS <versioned_schema>.<view_name>
  AS SELECT <columns>
  FROM <schema>.<name>;

GRANT SELECT ON VIEW <versioned_schema>.<view_name> TO APPLICATION ROLE <app_role>;
```

Key points:
- The view references `<schema>.<name>` (no package prefix needed inside setup script)
- Listing specific columns in the SELECT prevents leaking new columns on schema changes
- Each version has its own view definition in the versioned schema

---

## Path B: Data Outside the Application Package

Use this when the data lives in a **different database** in the provider account. Requires a two-step proxy pattern: create proxy views in the package, then expose them in the setup script.

### B1. Grant REFERENCE_USAGE on the External Database

```sql
GRANT REFERENCE_USAGE ON DATABASE <database>
  TO SHARE IN APPLICATION PACKAGE <pkg>;
```

This allows the package to reference objects in `<database>`. You **cannot** share external objects directly — you must create proxy views.

### B2. Create Proxy Views in the Package

```sql
-- Create a schema in the package for proxy views
CREATE SCHEMA IF NOT EXISTS <pkg>.<proxy_schema>;

-- Create proxy view referencing the external data
CREATE VIEW <pkg>.<proxy_schema>.<proxy_view_name>
  AS SELECT *
  FROM <database>.<schema>.<name>;
```

### B3. Grant Proxy Views to the Package

> **Prerequisite**: Complete B2 first — the schema and views must exist before you can grant on them.

```sql
GRANT USAGE ON SCHEMA <pkg>.<proxy_schema>
  TO SHARE IN APPLICATION PACKAGE <pkg>;

GRANT SELECT ON VIEW <pkg>.<proxy_schema>.<proxy_view_name>
  TO SHARE IN APPLICATION PACKAGE <pkg>;
```

### B4. Expose via Setup Script

Add to the setup script using the schema, view, and columns confirmed in Step 2:

```sql
CREATE APPLICATION ROLE IF NOT EXISTS <app_role>;

CREATE OR ALTER VERSIONED SCHEMA <versioned_schema>;
GRANT USAGE ON SCHEMA <versioned_schema> TO APPLICATION ROLE <app_role>;

-- View over the proxy view (references the package's proxy schema)
CREATE VIEW IF NOT EXISTS <versioned_schema>.<view_name>
  AS SELECT <columns>
  FROM <proxy_schema>.<proxy_view_name>;

GRANT SELECT ON VIEW <versioned_schema>.<view_name> TO APPLICATION ROLE <app_role>;
```

Important: The setup script views reference `<proxy_schema>.<proxy_view_name>` (the proxy view in the package), **not** the external database directly. A view in the setup script that directly references an external database will cause an error.

### Restriction: Imported Databases Cannot Be Reshared

You **cannot** use `GRANT REFERENCE_USAGE` on imported databases (e.g., the `SNOWFLAKE` database or databases from data shares). This is a Snowflake restriction — re-sharing of imported data is not allowed. If you need data from an imported database, copy the data into a table owned by the package first.

---

## Policies on Shared Data

Define policies on **proxy views in the setup script**, not directly on shared tables. Policy definitions on proxy views cannot be changed after app installation. During upgrades, running code continues to use the policies from the version that was created. Some context functions (e.g., `CURRENT_USER`) behave differently in consumer accounts.

## Restrictions Summary

| Restriction | Applies To |
|-------------|-----------|
| Must share schema with shared objects | All paths |
| No temporary, volatile, or transient tables | Inside package |
| No virtual columns with Java/Python/JS policies | All paths |
| View definitions cannot call Java/Python/JS | All paths |
| Cannot directly reference external databases from setup script views | Outside package |
| Cannot reshare imported databases | Outside package |

## Output

**STOP**: Present the proposed changes to the setup script and package grants to the user. Wait for explicit approval before applying.

After approval:
- Setup script updated with secure views over shared content
- Application package grants configured for the appropriate data source path
- Application roles granted access to the versioned views
