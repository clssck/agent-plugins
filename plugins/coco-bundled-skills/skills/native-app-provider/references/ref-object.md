---
name: ref-object
description: "Reference for configuring Snowflake Native App references to access consumer-owned objects (tables, views, warehouses, secrets, etc.)."
parent_skill: native-app-provider
---

# Object References Reference

Reference document for configuring a Snowflake Native App to access existing objects in the consumer account (tables, views, warehouses, secrets, etc.) using the references mechanism.

## Object Types and Allowed Privileges

| Object Type | Allowed Privileges |
|-------------|-------------------|
| `TABLE` | `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `REFERENCES` |
| `VIEW` | `SELECT`, `REFERENCES` |
| `EXTERNAL TABLE` | `SELECT`, `REFERENCES` |
| `FUNCTION` | `USAGE` |
| `PROCEDURE` | `USAGE` |
| `WAREHOUSE` | `MODIFY`, `MONITOR`, `USAGE`, `OPERATE` |
| `API INTEGRATION` | `USAGE` |
| `EXTERNAL ACCESS INTEGRATION` | `USAGE` |
| `SECRET` | `USAGE`, `READ` |

## Manifest Reference Definition

Each reference is defined in the `references` block of `manifest.yml`:

```yaml
references:
  - <reference_name>:
      label: "Display name shown to consumer"
      description: "Why the app needs access to this object"
      privileges:
        - SELECT
        - INSERT
      object_type: TABLE
      multi_valued: false
      register_callback: <schema>.<callback_proc>
```

### Required Fields

| Field | Description |
|-------|-------------|
| `label` | Human-readable name displayed to the consumer in Snowsight |
| `description` | Explanation of why the app needs this object — shown to consumer |
| `privileges` | List of privileges the app needs on the object. Must be valid for the `object_type` (see table above) |
| `object_type` | One of: `TABLE`, `VIEW`, `EXTERNAL TABLE`, `FUNCTION`, `PROCEDURE`, `WAREHOUSE`, `API INTEGRATION`, `EXTERNAL ACCESS INTEGRATION`, `SECRET` |
| `register_callback` | Schema-qualified stored procedure that handles binding. Called when the consumer associates an object |

### Optional Fields

| Field | Default | Description |
|-------|---------|-------------|
| `multi_valued` | `false` | Set to `true` to allow binding multiple consumer objects to the same reference |
| `configuration` | — | Additional configuration metadata for the reference |
| `configuration_callback` | — | **Required for `EXTERNAL ACCESS INTEGRATION` and `SECRET` types.** Schema-qualified procedure that returns configuration JSON when the consumer binds the reference via Snowsight. Without it, Snowflake raises `Missing field 'configuration_callback'`. See `references/ref-eai.md` and `references/ref-secret.md` for templates. |

## Register Callback Procedure (Single-Value)

For references where `multi_valued` is `false` (or omitted). Uses `SYSTEM$SET_REFERENCE` to bind exactly one object:

```sql
CREATE OR REPLACE PROCEDURE <schema>.register_single_reference(
  ref_name STRING, operation STRING, ref_or_alias STRING
)
  RETURNS STRING
  LANGUAGE SQL
AS $$
BEGIN
  CASE (operation)
    WHEN 'ADD' THEN
      SELECT SYSTEM$SET_REFERENCE(:ref_name, :ref_or_alias);
    WHEN 'REMOVE' THEN
      SELECT SYSTEM$REMOVE_REFERENCE(:ref_name, :ref_or_alias);
    WHEN 'CLEAR' THEN
      SELECT SYSTEM$REMOVE_ALL_REFERENCES(:ref_name);
    ELSE
      RETURN 'unknown operation: ' || operation;
  END CASE;
  RETURN NULL;
END;
$$;

GRANT USAGE ON PROCEDURE <schema>.register_single_reference(STRING, STRING, STRING)
  TO APPLICATION ROLE <app_role>;
```

## Register Callback Procedure (Multi-Value)

For references where `multi_valued` is `true`. Uses `SYSTEM$ADD_REFERENCE` to allow multiple objects:

```sql
CREATE OR REPLACE PROCEDURE <schema>.register_multi_reference(
  ref_name STRING, operation STRING, ref_or_alias STRING
)
  RETURNS STRING
  LANGUAGE SQL
AS $$
BEGIN
  CASE (operation)
    WHEN 'ADD' THEN
      SELECT SYSTEM$ADD_REFERENCE(:ref_name, :ref_or_alias);
    WHEN 'REMOVE' THEN
      SELECT SYSTEM$REMOVE_REFERENCE(:ref_name, :ref_or_alias);
    WHEN 'CLEAR' THEN
      SELECT SYSTEM$REMOVE_ALL_REFERENCES(:ref_name);
    ELSE
      RETURN 'unknown operation: ' || operation;
  END CASE;
  RETURN NULL;
END;
$$;

GRANT USAGE ON PROCEDURE <schema>.register_multi_reference(STRING, STRING, STRING)
  TO APPLICATION ROLE <app_role>;
```

## Configuration Callback (EXTERNAL ACCESS INTEGRATION and SECRET only)

References of type `EXTERNAL ACCESS INTEGRATION` and `SECRET` **require** an additional configuration callback procedure named `GET_CONFIGURATION_FOR_REFERENCE`. This callback is used when consumers bind references via Snowsight.

- For EXTERNAL ACCESS INTEGRATION references, load `references/ref-eai.md` for the callback template and payload format.
- For SECRET references, load `references/ref-secret.md` for the callback template and payload format.

## Using References in App Code

After a consumer binds an object to a reference, the app accesses it using the `reference()` function. The reference must be bound before it can be used — for example, you cannot create a task until the warehouse reference is bound.

### Queries

```sql
-- Select from a consumer table
SELECT * FROM reference('consumer_table') WHERE status = 'active';

-- Insert into a consumer table
INSERT INTO reference('data_export')(C1, C2)
  SELECT T.C1, T.C2 FROM reference('other_table') AS T;

-- Describe a consumer object
DESCRIBE reference('consumer_table');
```

### Tasks

```sql
CREATE TASK app_task
  WAREHOUSE = reference('consumer_warehouse')
  ...;

ALTER TASK app_task SET WAREHOUSE = reference('consumer_warehouse');
```

### Views

```sql
CREATE VIEW app_view
  AS SELECT reference('consumer_function')(T.C1) FROM reference('consumer_table') AS T;
```

### External Functions

```sql
CREATE EXTERNAL FUNCTION app.func(x INT)
  RETURNS STRING
  ...
  API_INTEGRATION = reference('app_integration');
```

### Row Access Policies

```sql
CREATE ROW ACCESS POLICY app_policy
  AS (sales_region VARCHAR) RETURNS BOOLEAN ->
  'sales_executive_role' = reference('get_sales_team')
    OR EXISTS (
      SELECT 1 FROM reference('sales_table')
        WHERE sales_manager = reference('get_sales_team')()
        AND region = sales_region
    );
```

> **Note:** For examples of using EAI and secret references in functions/procedures, see `references/ref-eai.md` and `references/ref-secret.md`.

## Important Rules

1. **Do not remove reference definitions** in new versions without also updating all code that uses the removed reference. Consumers will get errors if code references a deleted definition.
2. **Callback proc must be granted** to an application role — otherwise Snowflake raises a warning: `Reference register_callback '<PROC>' does not exist or is not granted to an application role.`
3. **Privileges must be valid** for the object type. Using an invalid privilege (e.g., `INSERT` on a `VIEW`) causes an error.
4. **`SYSTEM$SET_REFERENCE`** replaces any existing binding. Use `SYSTEM$ADD_REFERENCE` for multi-valued references.
5. **Configuration callback is required** for `EXTERNAL ACCESS INTEGRATION` and `SECRET` object types. Without it, Snowsight cannot build the reference binding UI.

## Workflow

This is a reference document. Load it from `request-object-access/SKILL.md` when generating reference configurations. No workflow steps apply.
