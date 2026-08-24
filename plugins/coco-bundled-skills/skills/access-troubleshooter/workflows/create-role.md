---
name: create-role-workflow
parent_skill: access-troubleshooter
---

# Workflow D: Create Least-Privilege Role

## When to Load

Loaded from `access-troubleshooter/SKILL.md` when user selects **Create a least-privilege role**, or from `workflows/debug-error.md` A5 / `workflows/find-authorizing-roles.md` C4 when user chooses to create a new role.

## Prerequisites

- Step 1 (intent selection) completed

---

## D1: Get the SQL Statement

Ask the user for the SQL statement. Store as `<SQL_STATEMENT>`.

If arriving from another workflow, the statement and `<USERNAME>` may already be known — skip what's available.

If `<USERNAME>` is not yet known, run `SELECT CURRENT_USER();` and store as `<USERNAME>` (needed later for granting the role to the user).

> **On-behalf-of variant:** If creating a role for a different user, store the target username as `<TARGET_USER>`. Use `<TARGET_USER>` in `GRANT ROLE ... TO USER` (D3 Step 3) and when checking "missing from primary role" scope (D2). See Agent Behavior Rule #8.

---

## D2: Role Name and Scope

Ask the user:

1. *"What should the new role be named?"*
   - Default suggestion: `<OBJECT_NAME>_ACCESS_ROLE`

2. Choose privilege scope:

```python
AskUserQuestion(
    questions=[{
        "question": "Should the role have ALL required privileges or only the ones MISSING from your current primary role?",
        "header": "Privilege Scope",
        "multiSelect": false,
        "options": [
            {"label": "All required privileges", "description": "Complete access for this query (standalone role)"},
            {"label": "Only missing privileges", "description": "Minimal addition to complement your current access"}
        ]
    }]
)
```

Store role name as `<NEW_ROLE_NAME>` and scope choice.

---

## D3: Generate Role Creation SQL

### Step 1: Get the Required Privileges

```sql
-- For ALL required:
CALL EXPLAIN_PRIVILEGES(statement => '<SQL_STATEMENT>');

-- For MISSING only:
CALL EXPLAIN_PRIVILEGES(
    statement    => '<SQL_STATEMENT>',
    missing_only => true,
    for_role     => '<USER_PRIMARY_ROLE>'
);
```

If `EXPLAIN_PRIVILEGES` returns **"requires access on all objects in the statement"**: the current role cannot resolve the objects. **Stop.** Do NOT attempt manual lookups. Tell the user: *"Your current role doesn't have sufficient privileges to analyze this statement. Please contact your system administrator. ACCOUNTADMIN role may be required to manage the privileges on the object."* Then proceed to **Step 3** in `SKILL.md`.

### Step 2 (optional): Check Existing Role Coverage

Use `SYSTEM$SUGGEST_ROLE_GRANTS` to see if existing roles already cover some of the required grants. This helps decide whether to create a new role or grant an existing one:

```sql
SELECT SYSTEM$SUGGEST_ROLE_GRANTS('<SQL_STATEMENT>', '<USER_PRIMARY_ROLE>');
```

If `canAuthorize: true`, the target already has all privileges — no new role needed.

If `roleHierarchy` shows a role with high `coveredGrantCount`, consider granting that existing role instead of creating a new one.

### Step 3: Generate SQL

From the EXPLAIN_PRIVILEGES output, generate (translate `<ANY>` privilege to `USAGE` for DATABASE and SCHEMA objects):

```sql
CREATE ROLE <NEW_ROLE_NAME>;

-- For each privilege in the output:
GRANT <privilege> ON <objectType> <objectName> TO ROLE <NEW_ROLE_NAME>;

-- Grant the new role to the user:
GRANT ROLE <NEW_ROLE_NAME> TO USER <USERNAME>;
```

---

## D4: Approve and Execute

**CHECKPOINT**: Present all SQL statements for approval.

```
I'll create a new role called <NEW_ROLE_NAME> with the required privileges:

    CREATE ROLE <NEW_ROLE_NAME>;
    GRANT USAGE ON DATABASE MY_DB TO ROLE <NEW_ROLE_NAME>;
    GRANT USAGE ON SCHEMA MY_DB.MY_SCHEMA TO ROLE <NEW_ROLE_NAME>;
    GRANT SELECT ON TABLE MY_DB.MY_SCHEMA.MY_TABLE TO ROLE <NEW_ROLE_NAME>;
    GRANT ROLE <NEW_ROLE_NAME> TO USER <USERNAME>;

Would you like me to execute these statements?
```

Wait for explicit approval. NEVER proceed without user confirmation.

---

## D5: Execute and Verify

Execute the approved SQL statements in order.

Verify the role was created and has the correct privileges:

```sql
SHOW GRANTS TO ROLE <NEW_ROLE_NAME>;
CALL EXPLAIN_PRIVILEGES(
    statement    => '<SQL_STATEMENT>',
    missing_only => true,
    for_role     => '<NEW_ROLE_NAME>'
);
-- Should return {"authorized": true}
```

Present confirmation:

```
Role <NEW_ROLE_NAME> created and granted to you.

To use it:

    USE ROLE <NEW_ROLE_NAME>;
    <SQL_STATEMENT>;
```

Then proceed to **Step 3** in `SKILL.md`.
