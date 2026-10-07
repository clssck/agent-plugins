# Function Reference

Detailed syntax, parameters, and output format for the three authorization analysis functions.

---

## When to Use Which Function

| Task | Function | Why |
|------|----------|-----|
| What privileges does a statement need? | `EXPLAIN_PRIVILEGES` | Compile-time analysis; use first |
| What is a role/session missing? | `EXPLAIN_PRIVILEGES(..., missing_only => true)` | Directly answers the question |
| Which roles can authorize a statement? | `SYSTEM$ANALYZE_ROLE_ACCESS` | Returns sorted role hierarchy with `isGranted` status |
| What grants should I add for a role/user? | `SYSTEM$SUGGEST_ROLE_GRANTS` | Per-role coverage of missing grants |

### Recommended Order

1. `EXPLAIN_PRIVILEGES(sql)` — understand all requirements
2. `EXPLAIN_PRIVILEGES(sql, missing_only => true)` — what is the session missing?
3. `EXPLAIN_PRIVILEGES(sql, missing_only => true, for_role => 'ROLE')` — what is a specific role missing?
4. `SYSTEM$ANALYZE_ROLE_ACCESS(sql)` — which roles can authorize?
5. `SYSTEM$SUGGEST_ROLE_GRANTS(sql, 'ROLE')` — what grants to add? (if needed)

---

## 1. EXPLAIN_PRIVILEGES

Returns a JSON privilege tree explaining which privileges are required to execute a SQL statement.

### Syntax

```sql
CALL EXPLAIN_PRIVILEGES(
    statement   => '<sql_statement>',
  [ missing_only => <boolean> , ]
  [ for_role     => '<role_name>' ]
);
```

### Parameters

| Parameter | Required | Type | Default | Description |
|-----------|----------|------|---------|-------------|
| `statement` | Yes | STRING | — | SQL statement to analyze |
| `missing_only` | No | BOOLEAN | `false` | `false`: return all required privileges. `true`: return only missing privileges |
| `for_role` | No | STRING | current session | Role to check against. Only used when `missing_only => true` |

### Dispatch Behavior

| `missing_only` | `for_role` | Result |
|-----------------|------------|--------|
| `false` / omitted | (ignored) | All privileges required for the statement |
| `true` | omitted | Missing privileges for current session (all active roles) |
| `true` | provided | Missing privileges for the specified role only |

### Output Format

JSON tree with four node types:

**PrivilegeNode** — single privilege requirement:
```json
{ "privilege": "SELECT", "objectType": "TABLE", "objectName": "SALES_DB.ANALYTICS.ORDERS" }
```

The `privilege` field can be a specific privilege name (e.g., `SELECT`, `INSERT`, `CREATE TABLE`) or `"<ANY>"` meaning any privilege on the object satisfies the requirement (common for DATABASE and SCHEMA access).

**AndNode** — all children required:
```json
{ "allOf": [ /* nodes */ ] }
```

**OrNode** — at least one child required:
```json
{ "oneOf": [ /* nodes */ ] }
```

**DecisionNode** — authorization verdict (returned when `missing_only => true` and the role/session is fully authorized):
```json
{ "authorized": true }
```

### Example: All Required Privileges (SELECT)

```json
{
  "allOf" : [ {
    "privilege" : "<ANY>",
    "objectType" : "DATABASE",
    "objectName" : "SALES_DB"
  }, {
    "privilege" : "SELECT",
    "objectType" : "TABLE",
    "objectName" : "SALES_DB.ANALYTICS.ORDERS"
  }, {
    "privilege" : "<ANY>",
    "objectType" : "SCHEMA",
    "objectName" : "SALES_DB.ANALYTICS"
  } ]
}
```

### Example: Missing Privileges for a Role Without Access

```json
{
  "allOf" : [ {
    "privilege" : "SELECT",
    "objectType" : "TABLE",
    "objectName" : "SALES_DB.ANALYTICS.ORDERS"
  }, {
    "privilege" : "<ANY>",
    "objectType" : "SCHEMA",
    "objectName" : "SALES_DB.ANALYTICS"
  }, {
    "privilege" : "<ANY>",
    "objectType" : "DATABASE",
    "objectName" : "SALES_DB"
  } ]
}
```

### Example: Role is Already Authorized

```json
{ "authorized" : true }
```

### Examples

```sql
-- All privileges needed for a SELECT
CALL EXPLAIN_PRIVILEGES(statement => 'SELECT * FROM sales_db.analytics.orders');

-- Only missing privileges for current session
CALL EXPLAIN_PRIVILEGES(
    statement    => 'DROP TABLE mydb.myschema.mytable',
    missing_only => true
);

-- Missing privileges for a specific role
CALL EXPLAIN_PRIVILEGES(
    statement    => 'SELECT * FROM sales_db.analytics.orders',
    missing_only => true,
    for_role     => 'FINANCE_READ'
);
```

> **Error: "requires access on all objects in the statement"** — The calling role cannot resolve one or more objects referenced in the SQL statement. This is a security boundary — do NOT attempt manual lookups (`SHOW GRANTS`, `SHOW TABLES`, etc.) as this would leak information about object existence. Tell the user: *"Your current role doesn't have sufficient privileges to analyze this statement. Please contact your system administrator. ACCOUNTADMIN role may be required to manage the privileges on the object."*
>
> **Error: "Unsupported feature"** — This function may not be available in the account. Fall back to `SYSTEM$ANALYZE_ROLE_ACCESS`.

---

## 2. SYSTEM$ANALYZE_ROLE_ACCESS

Finds all roles that can authorize a SQL statement, sorted leaf-to-root in the role hierarchy.

### Syntax

```sql
SELECT SYSTEM$ANALYZE_ROLE_ACCESS(
    '<sql_statement>',
  [ <missing_only> , ]
  [ '<for_user>' , ]
  [ '<for_role>' , ]
  [ '<candidate_roles>' ]
);
```

### Parameters

| Parameter | Position | Required | Type | Default | Description |
|-----------|----------|----------|------|---------|-------------|
| `sqlText` | 1 | Yes | STRING | — | SQL statement to analyze |
| `missingOnly` | 2 | No | BOOLEAN | `false` | `true`: only missing privileges |
| `forUser` | 3 | No | STRING | current user | User whose grants determine `isGranted` |
| `forRole` | 4 | No | STRING | — | Role whose hierarchy determines `isGranted` |
| `candidateRoles` | 5 | No | STRING | all account roles | Comma-separated role names to limit scope |

> **Constraint:** `forUser` and `forRole` are mutually exclusive — providing both raises an error. Pass empty string `''` to skip a positional parameter.

### Output Format

```json
{
  "supported" : true,
  "authorizingRoles" : [ {
    "roleName" : "SALES_ADMIN",
    "parentRoleNames" : [ "SALES_ANALYTICS_ACCESS" ],
    "depth" : 0,
    "isGranted" : false
  }, {
    "roleName" : "SALES_READ",
    "parentRoleNames" : [ "READONLY_IDENTITY", "SALES_ANALYTICS_ACCESS" ],
    "depth" : 0,
    "isGranted" : false
  }, {
    "roleName" : "SALES_ANALYTICS_ACCESS",
    "parentRoleNames" : [ "SALES_DB_ACCESS" ],
    "depth" : 1,
    "isGranted" : false
  }, {
    "roleName" : "SALES_IDENTITY",
    "parentRoleNames" : [ ],
    "depth" : 3,
    "isGranted" : true
  }, {
    "roleName" : "ACCOUNTADMIN",
    "parentRoleNames" : [ ],
    "depth" : 4,
    "isGranted" : false
  } ],
  "requiredPrivileges" : [ {
    "privilege" : "<ANY>",
    "securableType" : "DATABASE",
    "securableName" : "SALES_DB"
  }, {
    "privilege" : "<ANY>",
    "securableType" : "SCHEMA",
    "securableName" : "SALES_DB.ANALYTICS"
  }, {
    "privilege" : "SELECT",
    "securableType" : "TABLE",
    "securableName" : "SALES_DB.ANALYTICS.ORDERS"
  } ]
}
```

| Field | Description |
|-------|-------------|
| `supported` | `true` if analysis succeeded; `false` if the query can't be statically analyzed |
| `authorizingRoles` | Sorted leaf-to-root by `depth`, then alphabetically. System roles (ACCOUNTADMIN, SYSADMIN) placed at max depth + 1 |
| `authorizingRoles[].roleName` | Name of the authorizing role |
| `authorizingRoles[].parentRoleNames` | Sorted parent role names in the hierarchy (empty `[]` for top-level or isolated roles) |
| `authorizingRoles[].depth` | BFS depth (0 = leaf, higher = closer to root) |
| `authorizingRoles[].isGranted` | Whether this role is currently granted to the target user |
| `requiredPrivileges` | Resolved privileges using `securableType`/`securableName`, sorted by `securableName` then `privilege`. Uses `"<ANY>"` when any privilege on the object suffices |

### Missing Mode (`missingOnly = true`)

When `missingOnly = true` with `forRole`, if the role (including its hierarchy) can already authorize, both `authorizingRoles` and `requiredPrivileges` return as empty arrays:

```json
{ "supported" : true, "authorizingRoles" : [ ], "requiredPrivileges" : [ ] }
```

### Scoping with `candidateRoles`

Limit evaluation to specific roles. Only those roles are checked; hierarchy expansion within the candidate set still applies:

```sql
SELECT SYSTEM$ANALYZE_ROLE_ACCESS(
    'SELECT * FROM SALES_DB.ANALYTICS.ORDERS',
    false, 'U1', '', 'SALES_READ,SALES_WRITE,SALES_ADMIN'
);
```

---

## 3. SYSTEM$SUGGEST_ROLE_GRANTS

Computes the required privilege tree and per-role coverage for a statement relative to a target role or user. Shows which roles in the hierarchy already cover which missing grants.

### Syntax

```sql
SELECT SYSTEM$SUGGEST_ROLE_GRANTS(
    '<sql_statement>',
  [ '<for_role>' , ]
  [ '<for_user>' ]
);
```

### Parameters

| Parameter | Position | Required | Type | Default | Description |
|-----------|----------|----------|------|---------|-------------|
| `sqlText` | 1 | Yes | STRING | — | SQL statement to analyze |
| `forRole` | 2 | No | STRING | — | Target role. Exactly one of `forRole`/`forUser` required |
| `forUser` | 3 | No | STRING | — | Target user. Exactly one of `forRole`/`forUser` required |

> **Constraint:** Exactly one of `forRole` or `forUser` must be provided. Pass empty string `''` to skip a positional parameter.

### Output Format: Missing Privileges

When the target role/user cannot authorize (`canAuthorize: false`):

```json
{
  "supported" : true,
  "canAuthorize" : false,
  "requiredPrivileges" : {
    "allOf" : [ {
      "privilege" : "<ANY>",
      "objectType" : "DATABASE",
      "objectName" : "SALES_DB"
    }, {
      "privilege" : "SELECT",
      "objectType" : "TABLE",
      "objectName" : "SALES_DB.ANALYTICS.ORDERS"
    }, {
      "privilege" : "<ANY>",
      "objectType" : "SCHEMA",
      "objectName" : "SALES_DB.ANALYTICS"
    } ]
  },
  "roleHierarchy" : [ {
    "roleName" : "FINANCE_READ",
    "parentRoleNames" : [ ],
    "depth" : 0,
    "coveredGrantCount" : "0/3",
    "coveredGrants" : [ ]
  } ]
}
```

### Output Format: Already Authorized

When the target role/user (including its hierarchy) can already authorize (`canAuthorize: true`):

```json
{
  "supported" : true,
  "canAuthorize" : true,
  "requiredPrivileges" : { "authorized" : true },
  "roleHierarchy" : [ ]
}
```

### Field Reference

| Field | Description |
|-------|-------------|
| `supported` | `true` if analysis succeeded |
| `canAuthorize` | `true` if the target already has all required privileges (includes hierarchy — a parent role's children's grants count) |
| `requiredPrivileges` | When `canAuthorize: false`: privilege expression tree (same `allOf`/`oneOf`/PrivilegeNode format as `EXPLAIN_PRIVILEGES`, using `objectType`/`objectName`). When `canAuthorize: true`: `{"authorized": true}` |
| `roleHierarchy` | Sorted: highest coverage first, then by depth, then by name. Empty when `canAuthorize: true` |
| `roleHierarchy[].coveredGrantCount` | String like `"0/3"` — how many of the missing privileges this role covers |
| `roleHierarchy[].coveredGrants` | Specific privileges this role already holds that match the missing set |
| `roleHierarchy[].depth` | BFS depth in the role hierarchy |
| `roleHierarchy[].parentRoleNames` | Parent roles in the hierarchy (empty `[]` for top-level roles) |

---

## Cross-Reference

| Function | Question It Answers | Mode |
|----------|---------------------|------|
| `EXPLAIN_PRIVILEGES` | What privileges does this statement need? | All required / missing only |
| `SYSTEM$ANALYZE_ROLE_ACCESS` | Which roles can authorize this statement? | All / missing, with full role hierarchy |
| `SYSTEM$SUGGEST_ROLE_GRANTS` | What grants should I add for a role/user? | Missing only, with per-role coverage |

### Key Differences in Field Names

| Function | Privilege field names |
|----------|---------------------|
| `EXPLAIN_PRIVILEGES` | `objectType`, `objectName` |
| `SYSTEM$ANALYZE_ROLE_ACCESS` | `securableType`, `securableName` |
| `SYSTEM$SUGGEST_ROLE_GRANTS` (requiredPrivileges) | `objectType`, `objectName` |
| `SYSTEM$SUGGEST_ROLE_GRANTS` (coveredGrants) | `securableType`, `securableName` |

All functions use `"<ANY>"` as a privilege value for DATABASE and SCHEMA objects, meaning any privilege on that object satisfies the requirement.

---

## Helper Queries

### Get User's Directly Granted Roles

```sql
SELECT role AS directly_granted_role
FROM (SHOW GRANTS TO USER <USERNAME>)
WHERE granted_on = 'ROLE';
```

### Find Roles with a Specific Privilege

```sql
SELECT DISTINCT grantee_name
FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
WHERE privilege = 'SELECT'
  AND granted_on = 'TABLE'
  AND name = '<DB>.<SCHEMA>.<TABLE>'
  AND deleted_on IS NULL;
```

### Find Roles with ALL Required Privileges

```sql
WITH required AS (
    SELECT 'USAGE' AS priv, 'DATABASE' AS obj_type, 'MY_DB' AS obj_name
    UNION SELECT 'USAGE', 'SCHEMA', 'MY_DB.MY_SCHEMA'
    UNION SELECT 'SELECT', 'TABLE', 'MY_DB.MY_SCHEMA.MY_TABLE'
),
role_privs AS (
    SELECT grantee_name, privilege, granted_on, name
    FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
    WHERE deleted_on IS NULL
)
SELECT rp.grantee_name AS role_name
FROM role_privs rp
JOIN required r ON rp.privilege = r.priv AND rp.granted_on = r.obj_type
GROUP BY rp.grantee_name
HAVING COUNT(DISTINCT r.priv || r.obj_type || r.obj_name) =
       (SELECT COUNT(*) FROM required);
```
