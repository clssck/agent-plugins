---
name: grant-permissions-workflow
parent_skill: access-troubleshooter
---

# Workflow E: Grant Missing Privileges

## When to Load

Loaded from `access-troubleshooter/SKILL.md` when user selects **Grant missing privileges to a role**, or from `workflows/debug-error.md` A5 / `workflows/analyze-privileges.md` B3c when user chooses to grant missing privileges. Also handles user-level grant suggestions (e.g., "suggest grants for user X").

## Prerequisites

- Step 1 (intent selection) completed

---

## E1: Get the SQL Statement and Target

Ask the user for:
1. The SQL statement to analyze (store as `<SQL_STATEMENT>`)
2. Whether they want to grant to a **specific role** or analyze grants needed for a **user**

If the user specifies a **user** (e.g., "suggest grants for user AUTH_TEST_USER"), store as `<TARGET_USER>` and go to **E2-USER**.

If the user specifies a **role** (e.g., "grant missing privileges to TEST_SALES_READER_ROLE"), store as `<TARGET_ROLE>` and go to **E2-ROLE**.

If arriving from another workflow with a role already known, go to **E2-ROLE**.

If unclear, ask:

```python
AskUserQuestion(
    questions=[{
        "question": "Do you want to analyze grants for a specific role or for a user (across all their roles)?",
        "header": "Grant Target",
        "multiSelect": false,
        "options": [
            {"label": "For a user", "description": "Analyze all roles granted to a user and suggest the best role to grant to"},
            {"label": "For a specific role", "description": "Check what a single role is missing and grant to it"}
        ]
    }]
)
```

If **"For a user"**: ask for the username, store as `<TARGET_USER>`, go to **E2-USER**.
If **"For a specific role"**: ask for the role name (suggest roles from `SHOW GRANTS TO USER`), store as `<TARGET_ROLE>`, go to **E2-ROLE**.

---

## E2-USER: Identify Missing Privileges for a User

Use `SYSTEM$SUGGEST_ROLE_GRANTS` with the `forUser` parameter to analyze all the user's roles in a single call:

```sql
SELECT SYSTEM$SUGGEST_ROLE_GRANTS('<SQL_STATEMENT>', '', '<TARGET_USER>');
```

| Result | Action |
|--------|--------|
| `canAuthorize: true` | User already has a role that can authorize — inform user which role(s), proceed to **Step 3** in `SKILL.md` |
| `canAuthorize: false` | Continue below |
| **"requires access on all objects"** | Current role cannot resolve objects. **Stop.** Do NOT attempt manual lookups. Tell user: *"Your current role doesn't have sufficient privileges to analyze this statement. Please contact your system administrator. ACCOUNTADMIN role may be required to manage the privileges on the object."* Proceed to **Step 3** in `SKILL.md` |

When `canAuthorize: false`, present the `requiredPrivileges` and `roleHierarchy` with per-role coverage:

```
Required privileges for: <SQL_STATEMENT>

Role coverage for <TARGET_USER>:

| Role                  | Coverage | Covered Grants           |
|-----------------------|----------|--------------------------|
| <role1>               | 2/3      | USAGE on DB, USAGE on SCHEMA |
| <role2>               | 0/3      | (none)                   |

Recommendation: Grant the missing privileges to <best_role> (highest coverage).
```

Pick the role with the highest `coveredGrantCount` as the recommended target. Store as `<TARGET_ROLE>`. Present the recommendation and ask for approval before proceeding to **E3**.

---

## E2-ROLE: Identify Missing Privileges for a Role

```sql
CALL EXPLAIN_PRIVILEGES(
    statement    => '<SQL_STATEMENT>',
    missing_only => true,
    for_role     => '<TARGET_ROLE>'
);
```

| Result | Action |
|--------|--------|
| `{"authorized": true}` | Role already has all privileges — inform user, proceed to **Step 3** in `SKILL.md` |
| JSON with privileges | These are MISSING — continue to E3 |
| **"requires access on all objects"** | Current role cannot resolve objects. **Stop.** Do NOT attempt manual lookups. Tell user: *"Your current role doesn't have sufficient privileges to analyze this statement. Please contact your system administrator. ACCOUNTADMIN role may be required to manage the privileges on the object."* Proceed to **Step 3** in `SKILL.md` |

---

## E3: Generate GRANT Statements

From the missing privileges output, generate GRANT statements (translate `<ANY>` privilege to `USAGE` for DATABASE and SCHEMA objects):

```sql
GRANT <privilege> ON <object_type> <object_name> TO ROLE <TARGET_ROLE>;
```

### Common Patterns

```sql
GRANT USAGE ON DATABASE <db> TO ROLE <role>;
GRANT USAGE ON SCHEMA <db>.<schema> TO ROLE <role>;
GRANT SELECT ON TABLE <db>.<schema>.<table> TO ROLE <role>;
GRANT INSERT, UPDATE, DELETE ON TABLE <db>.<schema>.<table> TO ROLE <role>;
GRANT SELECT ON ALL TABLES IN SCHEMA <db>.<schema> TO ROLE <role>;
GRANT SELECT ON FUTURE TABLES IN SCHEMA <db>.<schema> TO ROLE <role>;
```

---

## E4: Approve and Execute

**CHECKPOINT**: Present all GRANT statements for approval.

```
To grant the missing privileges to <TARGET_ROLE>, run:

    GRANT USAGE ON DATABASE MY_DB TO ROLE <TARGET_ROLE>;
    GRANT USAGE ON SCHEMA MY_DB.MY_SCHEMA TO ROLE <TARGET_ROLE>;
    GRANT SELECT ON TABLE MY_DB.MY_SCHEMA.MY_TABLE TO ROLE <TARGET_ROLE>;

Would you like me to execute these grants?
```

Wait for explicit approval. NEVER proceed without user confirmation.

---

## E5: Execute and Verify

Execute the approved GRANT statements.

Verify the grants were applied:

```sql
SHOW GRANTS TO ROLE <TARGET_ROLE>;
CALL EXPLAIN_PRIVILEGES(
    statement    => '<SQL_STATEMENT>',
    missing_only => true,
    for_role     => '<TARGET_ROLE>'
);
-- Should return {"authorized": true}
```

| Result | Action |
|--------|--------|
| `{"authorized": true}` | Fixed — confirm to user |
| Still shows missing | Review grants, check for deny policies or row access policies |

Present confirmation:

```
Privileges granted to <TARGET_ROLE>.

To run your query:

    USE ROLE <TARGET_ROLE>;
    <SQL_STATEMENT>;
```

Then proceed to **Step 3** in `SKILL.md`.
