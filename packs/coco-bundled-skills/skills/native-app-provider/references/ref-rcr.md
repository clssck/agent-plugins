---
name: ref-rcr
description: "Reference for Restricted Caller Rights (RCR) in Snowflake Native Apps: templates, split pattern, consumer grant syntax, limitations."
parent_skill: native-app-provider
---

# Reference: Restricted Caller Rights (RCR) in Native Apps

## Manifest Configuration

Declare RCR usage in `manifest.yml`:

```yaml
restricted_callers_rights:
  enabled: true
  description: >
    This app uses restricted caller's rights to access consumer data
    for enrichment and analysis purposes.
```

Both fields are required. The `description` is displayed to consumers in Snowsight.

### Supported Account-Level Caller Grants

These account-level privileges can be granted to an application via caller grants:

`CREATE DATABASE`, `EXECUTE ALERT`, `EXECUTE MANAGED TASK`, `EXECUTE TASK`, `READ SESSION`, `VIEW LINEAGE`

## Consumer Grant Syntax (Native App)

All forms use `TO APPLICATION <app>` (not `TO ROLE`):

```sql
-- Grant specific privilege on a specific object
GRANT CALLER SELECT ON TABLE consumer_db.schema.my_table TO APPLICATION my_app;

-- Grant all privileges on a specific object
GRANT ALL CALLER PRIVILEGES ON DATABASE consumer_db TO APPLICATION my_app;

-- Grant specific privilege on all current and future objects in a scope
GRANT INHERITED CALLER SELECT ON ALL TABLES IN SCHEMA consumer_db.my_schema TO APPLICATION my_app;

-- Grant all privileges on all current and future objects in account
GRANT ALL INHERITED CALLER PRIVILEGES ON ALL DATABASES IN ACCOUNT TO APPLICATION my_app;
```

Revoke with the corresponding `REVOKE CALLER` / `REVOKE ALL CALLER PRIVILEGES` / `REVOKE INHERITED CALLER` / `REVOKE ALL INHERITED CALLER PRIVILEGES` forms.

List grants:

```sql
-- Caller grants currently held by an application
SHOW CALLER GRANTS TO APPLICATION my_app;

-- Caller grants currently held by an account role (dev-mode superset held by app owner)
SHOW CALLER GRANTS TO ROLE app_owner_role;
```

## High-Level Caller Grants

High-level caller privileges authorize a **broad category of operations** without enumerating individual objects. They serve several purposes:

- **Simpler intent-based management** — express what the app needs ("read data") rather than listing every object it will touch
- **Unknown objects** — use when the specific objects are not known at install time (e.g., consumer passes table names at runtime)
- **Exclusive operations** — some capabilities such as creating references, managing grants, or accessing sensitive objects can only be authorized via high-level privileges; fine-grained grants cannot cover them

See also: [Snowflake docs — High-level caller grants](https://docs.snowflake.com/en/developer-guide/native-apps/requesting-caller-grants)

**Available privileges:**

| Privilege | Scope | Covers |
|-----------|-------|--------|
| `DATA READ` | account / database / schema | READ operations on tables, views, streams, stages, and Cortex Search Services |
| `DATA WRITE` | account / database / schema | DML to tables; implicitly covers DATA READ |
| `COMPUTE USAGE` | account only | Warehouses and compute pools |
| `PROGRAM USAGE` | account / database / schema | USAGE on UDFs, stored procedures, Streamlit apps, SPCS services and service endpoints, Cortex Agents, MCP servers |
| `GRANT MANAGEMENT` | account / database / schema | GRANT/REVOKE statements; create references |
| `OBJECT MANAGEMENT` | account / database / schema | Full non-sensitive object control; implicitly covers DATA READ, DATA WRITE, COMPUTE USAGE |
| `FULL MANAGEMENT` | account only | All operations; implicitly covers everything above |

**Hierarchy (ancestor covers all descendants):**
```
FULL MANAGEMENT
└── OBJECT MANAGEMENT
│    ├── DATA WRITE
│    │     └── DATA READ
│    └── COMPUTE USAGE
├── GRANT MANAGEMENT
└── PROGRAM USAGE
```

**Syntax — grant to application:**
```sql
-- Read any table in a consumer database (objects unknown at install time)
GRANT CALLER DATA READ ON DATABASE consumer_db TO APPLICATION my_app;

-- Use the consumer's warehouse
GRANT CALLER COMPUTE USAGE ON ACCOUNT TO APPLICATION my_app;

-- Invoke consumer UDFs/procedures in a specific schema
GRANT CALLER PROGRAM USAGE ON SCHEMA consumer_db.analytics TO APPLICATION my_app;

-- Scoped to schema instead of full database
GRANT CALLER DATA READ ON SCHEMA consumer_db.public TO APPLICATION my_app;
```

**Note — `GRANT ALL CALLER PRIVILEGES` does NOT cover high-level privileges, and caller ownership does not include them either:**
```sql
-- Neither of these grants DATA READ, COMPUTE USAGE, or any high-level privilege:
GRANT ALL CALLER PRIVILEGES ON DATABASE consumer_db TO APPLICATION my_app;  -- fine-grained only
-- (caller ownership also does not include high-level privileges)

-- High-level privileges must be granted explicitly:
GRANT CALLER DATA READ ON DATABASE consumer_db TO APPLICATION my_app;
```

**When to use high-level vs fine-grained:**

| Scenario | Recommended grant form |
|----------|----------------------|
| App accesses specific known tables | Fine-grained: `GRANT CALLER SELECT ON TABLE` |
| App accesses tables passed by consumer at runtime | High-level: `GRANT CALLER DATA READ ON DATABASE/SCHEMA` |
| App needs a specific named warehouse | Fine-grained: `GRANT CALLER USAGE ON WAREHOUSE <name>` |
| App needs a warehouse but name is unknown at install time | High-level: `GRANT CALLER COMPUTE USAGE ON ACCOUNT` — covers any warehouse |
| App invokes consumer UDFs/procedures | High-level: `GRANT CALLER PROGRAM USAGE ON SCHEMA/DATABASE` |

**Dev-mode superset for high-level grants** — the same dev-mode bypass applies. Grant the same privilege to the owner role first:
```sql
GRANT CALLER DATA READ     ON DATABASE consumer_db TO ROLE app_owner_role;
GRANT CALLER COMPUTE USAGE ON ACCOUNT              TO ROLE app_owner_role;

GRANT CALLER DATA READ     ON DATABASE consumer_db TO APPLICATION my_app;
GRANT CALLER COMPUTE USAGE ON ACCOUNT              TO APPLICATION my_app;
```

## RCR Procedure Templates

**Rules:**
- Always use `IDENTIFIER()` for dynamic object names to prevent SQL injection
- Grant to `APPLICATION ROLE`, not account roles
- Place in a versioned schema (`CREATE OR ALTER VERSIONED SCHEMA core`)
- Do NOT add a `COMMENT` clause after `EXECUTE AS` in procedure definitions

### SQL — Static Query

Use when the query shape is fixed and only the object name is dynamic:

```sql
CREATE OR REPLACE PROCEDURE core.read_consumer_data(table_name VARCHAR)
  RETURNS TABLE()
  LANGUAGE SQL
  EXECUTE AS RESTRICTED CALLER
AS
$$
DECLARE
  rs RESULTSET DEFAULT (SELECT * FROM IDENTIFIER(:table_name) LIMIT 1000);
BEGIN
  RETURN TABLE(rs);
END;
$$;

GRANT USAGE ON PROCEDURE core.read_consumer_data(VARCHAR)
  TO APPLICATION ROLE app_user;
```

### SQL — Dynamic Query (EXECUTE IMMEDIATE)

Use when the query itself must be built at runtime (e.g., querying `INFORMATION_SCHEMA`):

```sql
CREATE OR REPLACE PROCEDURE core.count_rows(table_fqn VARCHAR)
  RETURNS TABLE(row_count NUMBER)
  LANGUAGE SQL
  EXECUTE AS RESTRICTED CALLER
AS
$$
DECLARE
  query VARCHAR;
  rs RESULTSET;
BEGIN
  query := 'SELECT COUNT(*) AS row_count FROM IDENTIFIER(:1)';
  rs := (EXECUTE IMMEDIATE :query USING (table_fqn));
  RETURN TABLE(rs);
END;
$$;

GRANT USAGE ON PROCEDURE core.count_rows(VARCHAR)
  TO APPLICATION ROLE app_user;
```

**EXECUTE IMMEDIATE rules:**
- Use `IDENTIFIER(:1)` with positional bind variables (`:1`, `:2`, …) inside the SQL string
- In the `USING` clause, pass variables **without** the `:` prefix: `USING (table_fqn)` — NOT `USING (:table_fqn)`
- Always capture the result in a `RESULTSET` and `RETURN TABLE(rs)` — do NOT assign an `EXECUTE IMMEDIATE` result to a scalar variable (`NUMBER`, `VARCHAR`)

### Python (Snowpark)

```sql
CREATE OR REPLACE PROCEDURE core.analyze_consumer_data(table_name VARCHAR)
  RETURNS VARIANT
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.8'
  PACKAGES = ('snowflake-snowpark-python')
  HANDLER = 'run'
  EXECUTE AS RESTRICTED CALLER
AS
$$
def run(session, table_name):
    df = session.table(table_name)
    return {"row_count": df.count(), "columns": df.columns}
$$;

GRANT USAGE ON PROCEDURE core.analyze_consumer_data(VARCHAR)
  TO APPLICATION ROLE app_user;
```

## Split Pattern

**When to use:** A procedure needs both consumer data AND app-internal data (e.g., joining consumer tables with app config/models).

**Why:** RCR procedures execute with the caller's privileges. Since the consumer does not have direct access to the app's internal objects, the RCR procedure cannot reach them either.

**Pattern:** Use an RCR procedure to fetch consumer data, then an owner's rights procedure to process it with app internals.

```sql
-- Step 1: RCR procedure fetches consumer data
CREATE OR REPLACE PROCEDURE core.fetch_consumer_records(table_name VARCHAR)
  RETURNS TABLE()
  LANGUAGE SQL
  EXECUTE AS RESTRICTED CALLER
AS
$$
DECLARE
  rs RESULTSET DEFAULT (SELECT * FROM IDENTIFIER(:table_name));
BEGIN
  RETURN TABLE(rs);
END;
$$;

GRANT USAGE ON PROCEDURE core.fetch_consumer_records(VARCHAR)
  TO APPLICATION ROLE app_user;

-- Step 2: Owner's rights procedure orchestrates (can access app internals)
CREATE OR REPLACE PROCEDURE core.enrich_with_model(table_name VARCHAR)
  RETURNS TABLE()
  LANGUAGE SQL
AS
$$
DECLARE
  rs RESULTSET DEFAULT (
    SELECT c.*, m.score
    FROM TABLE(RESULT_SCAN(LAST_QUERY_ID())) c
    JOIN core.model_scores m ON c.id = m.id
  );
BEGIN
  -- First, call the RCR proc to fetch consumer data
  CALL core.fetch_consumer_records(:table_name);
  -- Then join with internal model data
  RETURN TABLE(rs);
END;
$$;

GRANT USAGE ON PROCEDURE core.enrich_with_model(VARCHAR)
  TO APPLICATION ROLE app_user;
```

**Alternative:** Pass consumer data as a temporary table or variant parameter between the two procedures if RESULT_SCAN is not suitable.

## Native App Limitations

RCR procedures in Native Apps have additional restrictions beyond standard RCR:

**Blocked operations:**
- `SHOW ROLES`, `SHOW USERS`, `SHOW GRANTS`, `SHOW AVAILABLE LISTINGS`
- `CURRENT_AVAILABLE_ROLES()`, `CURRENT_SECONDARY_ROLES()`, `ALL_USER_NAMES()`
- `CURRENT_IP_ADDRESS()`, `SYSTEM$ALLOWLIST()`
- App-internal objects (tables, views, functions in the app database) are not accessible — the procedure runs with the caller's privileges, and the caller does not have access to these objects
- No secondary roles support (`USE SECONDARY ROLES` is blocked)

**Requires owner's rights wrapper:**
- `SYSTEM$CREATE_BILLING_EVENT` — wrap in an owner's rights procedure, call from RCR if needed

## IP Protection

| What | Redacted? |
|------|-----------|
| `DESCRIBE PROCEDURE`, `GET_DDL` | Yes — procedure body hidden from consumers |
| Information Schema `PROCEDURES` view | Yes — body column redacted |
| Query history (`QUERY_HISTORY`) | No — query text visible |
| Query profiles | No — execution plan visible |

**Implication:** Keep proprietary algorithms and business logic in owner's rights procedures. Use RCR only for the consumer data access layer.

## Authority to Issue Caller Grants

A role may issue `GRANT CALLER ... TO APPLICATION` only if **one** of the following is true:

1. **`MANAGE CALLER GRANTS ON ACCOUNT`** — a top-level account privilege. A role holding this privilege can issue any caller grant to any application without needing its own superset. This is the production path.

   ```sql
   GRANT MANAGE CALLER GRANTS ON ACCOUNT TO ROLE app_owner_role;
   ```

2. **Dev-mode superset** — the role owns a dev-mode (unversioned) application AND the role itself holds a superset of the specific caller privileges it is about to grant.

The second path is verified per object and per privilege. Broad `INHERITED` forms on the role do **not** satisfy the superset check for specific object grants.

## Dev Mode Testing

Use dev-mode caller grants to test RCR without `MANAGE CALLER GRANTS ON ACCOUNT`. The app owner role must hold — on each concrete object — a superset of the caller grant it then issues to the application.

**Verified recipes (both work):**

```sql
-- Option A: fine-grained superset on role, then mirror to application.
-- Must cover every database/schema/table touched by the RCR procs.
GRANT CALLER USAGE  ON DATABASE consumer_db                       TO ROLE app_owner_role;
GRANT CALLER USAGE  ON SCHEMA   consumer_db.my_schema             TO ROLE app_owner_role;
GRANT CALLER SELECT ON TABLE    consumer_db.my_schema.my_table    TO ROLE app_owner_role;

GRANT CALLER USAGE  ON DATABASE consumer_db                       TO APPLICATION my_app;
GRANT CALLER USAGE  ON SCHEMA   consumer_db.my_schema             TO APPLICATION my_app;
GRANT CALLER SELECT ON TABLE    consumer_db.my_schema.my_table    TO APPLICATION my_app;
```

```sql
-- Option B: ALL CALLER PRIVILEGES superset on role, fine-grained to application.
GRANT ALL CALLER PRIVILEGES ON DATABASE consumer_db                    TO ROLE app_owner_role;
GRANT ALL CALLER PRIVILEGES ON SCHEMA   consumer_db.my_schema          TO ROLE app_owner_role;
GRANT ALL CALLER PRIVILEGES ON TABLE    consumer_db.my_schema.my_table TO ROLE app_owner_role;

GRANT CALLER USAGE  ON DATABASE consumer_db                       TO APPLICATION my_app;
GRANT CALLER USAGE  ON SCHEMA   consumer_db.my_schema             TO APPLICATION my_app;
GRANT CALLER SELECT ON TABLE    consumer_db.my_schema.my_table    TO APPLICATION my_app;
```

**Does NOT work as a dev-mode superset:**

```sql
-- INHERITED forms do not satisfy the per-object superset check
-- when issuing specific (non-inherited) caller grants to the application.
GRANT ALL INHERITED CALLER PRIVILEGES ON ALL DATABASES IN ACCOUNT TO ROLE app_owner_role;
```

**Requirements:**
- Application must be in development mode (`CREATE APPLICATION ... USING '@stage'`)
- The current role must be (or inherit) the application owner role
- The owner role must hold a concrete superset on every object the caller grant targets

**Notes:**
- This only authorizes issuing caller grants — it does not change what data the developer can read directly.
- The bypass does not work for versioned (published) applications; those require `MANAGE CALLER GRANTS ON ACCOUNT`.
- Verify with `SHOW CALLER GRANTS TO ROLE app_owner_role;` and `SHOW CALLER GRANTS TO APPLICATION my_app;`.

## Consumer Setup Template

**Grant hierarchy:** Consumer grants follow the Snowflake object hierarchy. All three levels are required to reach a table — omitting database or schema `USAGE` causes table grants to silently fail at runtime:

1. `GRANT CALLER USAGE ON DATABASE ...`
2. `GRANT CALLER USAGE ON SCHEMA ...`
3. `GRANT CALLER SELECT ON TABLE ...` (or `ON ALL TABLES IN SCHEMA`)

Complete SQL for consumer documentation:

```sql
-- 1. Install the application
CREATE APPLICATION my_app
  FROM APPLICATION PACKAGE my_app_pkg
  USING VERSION v1;

-- 2. Grant caller privileges to the app (all 3 levels required)
GRANT CALLER USAGE ON DATABASE consumer_db TO APPLICATION my_app;
GRANT CALLER USAGE ON SCHEMA consumer_db.my_schema TO APPLICATION my_app;
GRANT CALLER SELECT ON ALL TABLES IN SCHEMA consumer_db.my_schema TO APPLICATION my_app;

-- 3. Bind references (if manifest defines references)
-- Via Snowsight UI, or programmatically:
CALL my_app.config_code.register_reference('consumer_table', 'ADD', 'consumer_db.my_schema.my_table');

-- 4. Map application roles to account roles
GRANT APPLICATION ROLE my_app.app_user TO ROLE analyst_role;
GRANT APPLICATION ROLE my_app.app_admin TO ROLE sysadmin;

-- 5. Use the app
USE ROLE analyst_role;
CALL my_app.core.read_consumer_data('consumer_db.my_schema.my_table');
```

## Workflow

This is a reference document. Load it from `use-rcr/SKILL.md` when generating RCR configurations. No workflow steps apply.
