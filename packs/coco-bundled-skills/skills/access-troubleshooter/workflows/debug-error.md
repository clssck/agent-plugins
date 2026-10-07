---
name: debug-authorization-error-workflow
parent_skill: access-troubleshooter
---

# Workflow A: Debug Authorization Error

## When to Load

Loaded from `access-troubleshooter/SKILL.md` when user selects **Debug an authorization error**, or auto-triggered by SQL access control error patterns.

## Prerequisites

- Step 1 (intent selection) completed

---

## A1: Get the Failing SQL Statement

Ask the user for the SQL statement that failed. Store as `<SQL_STATEMENT>`.

If the user already provided it (e.g., via an error message), confirm: *"I see the failing statement is: `<SQL_STATEMENT>`. Is that correct?"*

---

## A2: Gather Context

Execute these in order:

```sql
-- 1. Get user's current primary role and username
SELECT CURRENT_ROLE() AS primary_role, CURRENT_USER() AS username;
-- Store as <PRIMARY_ROLE> and <USERNAME>

-- 2. Get ALL required privileges for the query
CALL EXPLAIN_PRIVILEGES(statement => '<SQL_STATEMENT>');
-- Store as <ALL_REQUIRED>

-- 3. Check if current session can authorize
CALL EXPLAIN_PRIVILEGES(statement => '<SQL_STATEMENT>', missing_only => true);
-- Store as <SESSION_CHECK>
```

> **On-behalf-of variant:** If analyzing for another user, store the target username as `<TARGET_USER>`. Use `<TARGET_USER>` as the `forUser` parameter in A4's `SYSTEM$ANALYZE_ROLE_ACCESS` call. If any on-behalf-of query fails with insufficient privileges, **stop analysis** (see Agent Behavior Rule #8). Steps 2–3 use the caller's session to resolve objects.

> **Error handling for EXPLAIN_PRIVILEGES:**
>
> - **"requires access on all objects in the statement"** → The current role cannot resolve one or more objects. **Stop analysis.** Do NOT attempt manual lookups (`SHOW GRANTS`, `SHOW TABLES`, etc.) — this would leak information about object existence. Tell the user: *"Your current role doesn't have sufficient privileges to analyze this statement. Please contact your system administrator. ACCOUNTADMIN role may be required to manage the privileges on the object."* Then proceed to **Step 3** in `SKILL.md`.
> - **"Unsupported feature"** → Skip to A2-Fallback below.

### Quick Resolution Check (Non-CREATE only)

After A2 step 3, if `{"authorized": true}` **AND** the statement is NOT a CREATE:

> CREATE statements need a specific role for ownership — session-level authorization alone doesn't determine which role owns the created object.

```
Good news! Your current session can already run this query.

    <SQL_STATEMENT>;
```

Then proceed to **Step 3** in `SKILL.md`.

If NOT authorized, continue to A3.

### A2-Fallback: EXPLAIN_PRIVILEGES Unavailable

If `EXPLAIN_PRIVILEGES` is not available, use `SYSTEM$ANALYZE_ROLE_ACCESS` instead:

```sql
SELECT SYSTEM$ANALYZE_ROLE_ACCESS('<SQL_STATEMENT>', false, '<USERNAME>');
```

> **On-behalf-of variant:** Use `SYSTEM$ANALYZE_ROLE_ACCESS('<SQL_STATEMENT>', false, '<TARGET_USER>')`. If this fails with insufficient privileges, **stop analysis** (see Agent Behavior Rule #8).

If this also fails with **"requires access on all objects"**, follow the same stop rule above — tell the user to contact their system administrator (ACCOUNTADMIN may be required) and do not attempt manual lookups.

Parse the `authorizingRoles` and `requiredPrivileges` from the output. Use this to skip to A5 (Resolution Options) with the information gathered.

---

## A3: Check Statement Type

**Is this a CREATE statement?** (CREATE TABLE, CREATE VIEW, CREATE SCHEMA, CREATE DATABASE, etc.)

If YES → Go to A4-CREATE
If NO → Go to A4-NON-CREATE

---

## A4-CREATE: CREATE Statement Flow

Find which of the user's roles can authorize, in a single call:

```sql
SELECT SYSTEM$ANALYZE_ROLE_ACCESS('<SQL_STATEMENT>', false, '<USERNAME>');
```

> **On-behalf-of variant:** Use `SYSTEM$ANALYZE_ROLE_ACCESS('<SQL_STATEMENT>', false, '<TARGET_USER>')`. If this fails with insufficient privileges, **stop analysis** (see Agent Behavior Rule #8).

From the results, filter to roles where `isGranted: true`.

**If an authorized + granted role exists:**

```
Your role <ROLE_NAME> has the required CREATE privilege.

To create this object, switch to that role:

    USE ROLE <ROLE_NAME>;
    <SQL_STATEMENT>;

Note: The created object will be owned by <ROLE_NAME>.
```

If multiple granted roles can authorize, prefer the one with the lowest `depth` (most specific). Then proceed to **Step 3** in `SKILL.md`.

**If NO granted role can authorize:** Go to A5 (Resolution Options).

---

## A4-NON-CREATE: Non-CREATE Statement Flow

Find which of the user's roles can authorize, in a single call:

```sql
SELECT SYSTEM$ANALYZE_ROLE_ACCESS('<SQL_STATEMENT>', false, '<USERNAME>');
```

> **On-behalf-of variant:** Use `SYSTEM$ANALYZE_ROLE_ACCESS('<SQL_STATEMENT>', false, '<TARGET_USER>')`. If this fails with insufficient privileges, **stop analysis** (see Agent Behavior Rule #8).

From the results, filter to roles where `isGranted: true`.

**If an authorized + granted role exists:**

```
Your role <ROLE_NAME> can run this query.

    USE ROLE <ROLE_NAME>;
    <SQL_STATEMENT>;
```

If multiple granted roles can authorize, prefer the one with the lowest `depth`. Then proceed to **Step 3** in `SKILL.md`.

**If NO granted role can authorize:** Go to A5 (Resolution Options).

---

## A5: Resolution Options

**First, ALWAYS show the required privileges** (translate `<ANY>` privilege to `USAGE` for DATABASE and SCHEMA objects):

```
Required Privileges for this query:

To run: <SQL_STATEMENT>

A role needs:
    GRANT <privilege1> ON <object_type1> <object_name1> TO ROLE <role>;
    GRANT <privilege2> ON <object_type2> <object_name2> TO ROLE <role>;
    ...
```

(Generate from the `<ALL_REQUIRED>` output from A2 step 3.)

**Then present resolution options:**

```python
AskUserQuestion(
    questions=[{
        "question": "None of your current roles can run this query. How would you like to proceed?",
        "header": "Resolution",
        "multiSelect": false,
        "options": [
            {"label": "Grant missing privileges to an existing role", "description": "Add the missing privileges to one of your roles"},
            {"label": "Find an existing role in the account", "description": "Search for a role that already has these privileges"},
            {"label": "Create a new least-privilege role", "description": "Create a new role with only the required privileges"}
        ]
    }]
)
```

| Selection | Action |
|-----------|--------|
| **Grant missing privileges to an existing role** | **Read and follow** `workflows/grant-permissions.md`. Pass `<SQL_STATEMENT>` and `<ALL_REQUIRED>` as context. |
| **Find an existing role in the account** | **Read and follow** `workflows/find-authorizing-roles.md`. Pass `<SQL_STATEMENT>` as context. |
| **Create a new least-privilege role** | **Read and follow** `workflows/create-role.md`. Pass `<SQL_STATEMENT>` and `<ALL_REQUIRED>` as context. |

After the selected workflow completes, proceed to A6.

---

## A6: Verify Resolution

```sql
-- Verify the fix worked
CALL EXPLAIN_PRIVILEGES(
    statement    => '<SQL_STATEMENT>',
    missing_only => true,
    for_role     => '<ROLE_USED>'
);
-- Should return {"authorized": true}
```

If authorized, confirm to the user and suggest testing:

```
Access verified! To run your query:

    USE ROLE <ROLE_USED>;
    <SQL_STATEMENT>;
```

If still not authorized, review the grants and check for deny policies or row access policies.

Then proceed to **Step 3** in `SKILL.md`.
