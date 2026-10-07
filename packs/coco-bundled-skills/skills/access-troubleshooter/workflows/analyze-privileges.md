---
name: analyze-privileges-workflow
parent_skill: access-troubleshooter
---

# Workflow B: Analyze Privileges

## When to Load

Loaded from `access-troubleshooter/SKILL.md` when user selects **Analyze what privileges a query needs**.

## Prerequisites

- Step 1 (intent selection) completed

---

## B1: Get the SQL Statement

Ask the user for the SQL statement to analyze. Store as `<SQL_STATEMENT>`.

---

## B2: Choose Analysis Type

```python
AskUserQuestion(
    questions=[{
        "question": "What kind of privilege analysis do you need?",
        "header": "Analysis Type",
        "multiSelect": false,
        "options": [
            {"label": "All required privileges", "description": "List every privilege needed to run this query"},
            {"label": "Missing privileges for current session", "description": "Show only what my current session is missing"},
            {"label": "Missing privileges for a specific role", "description": "Show what a particular role is missing"}
        ]
    }]
)
```

| Selection | Go to |
|-----------|-------|
| All required privileges | B3a |
| Missing privileges for current session | B3b |
| Missing privileges for a specific role | B3c |

---

## Error Handling (applies to B3a, B3b, B3c)

If any `EXPLAIN_PRIVILEGES` call returns **"requires access on all objects in the statement"**: the current role cannot resolve the objects. **Stop analysis.** Do NOT attempt manual lookups. Tell the user: *"Your current role doesn't have sufficient privileges to analyze this statement. Please contact your system administrator. ACCOUNTADMIN role may be required to manage the privileges on the object."* Then proceed to **Step 3** in `SKILL.md`.

---

## B3a: All Required Privileges

```sql
CALL EXPLAIN_PRIVILEGES(statement => '<SQL_STATEMENT>');
```

> See Error Handling section above if this call fails.

### Interpreting Output

| Output | Meaning |
|--------|---------|
| `{"authorized": true}` | No special privileges needed |
| `{"allOf": [...]}` | ALL listed privileges required |
| `{"oneOf": [...]}` | ONE of the listed privileges required |

Present a clear summary (translate `<ANY>` privilege to `USAGE` for DATABASE and SCHEMA objects):

```
Privileges required to run: <SQL_STATEMENT>

    GRANT <privilege> ON <objectType> <objectName> TO ROLE <role>;
    ...

All of these must be granted for the query to succeed.
```

Then proceed to **Step 3** in `SKILL.md`.

---

## B3b: Missing Privileges for Current Session

```sql
CALL EXPLAIN_PRIVILEGES(statement => '<SQL_STATEMENT>', missing_only => true);
```

> See Error Handling section above if this call fails.

> **On-behalf-of variant:** This checks the *caller's* session. To check what a different user is missing, use B3c with each of the target user's roles, or use `SYSTEM$SUGGEST_ROLE_GRANTS('<SQL_STATEMENT>', '', '<TARGET_USER>')` for a user-level summary. See Agent Behavior Rule #8.

| Result | Action |
|--------|--------|
| `{"authorized": true}` | Session has all privileges — inform user they can run the query |
| JSON with privileges | These are MISSING — present them and offer to help fix (route to grant-permissions or create-role workflow) |

Then proceed to **Step 3** in `SKILL.md`.

---

## B3c: Missing Privileges for a Specific Role

Ask the user which role to check. Store as `<ROLE_NAME>`.

```sql
CALL EXPLAIN_PRIVILEGES(
    statement    => '<SQL_STATEMENT>',
    missing_only => true,
    for_role     => '<ROLE_NAME>'
);
```

> See Error Handling section above if this call fails.

| Result | Action |
|--------|--------|
| `{"authorized": true}` | Role has all privileges |
| JSON with privileges | These are MISSING — present them |
| Error | Check that the role name is correct |

Present the results and offer next steps:

```python
AskUserQuestion(
    questions=[{
        "question": "Would you like to fix the missing privileges?",
        "header": "Next Step",
        "multiSelect": false,
        "options": [
            {"label": "Grant missing privileges to this role", "description": "Generate GRANT statements for the missing privileges"},
            {"label": "Check another role", "description": "Analyze a different role"},
            {"label": "Done", "description": "No further action needed"}
        ]
    }]
)
```

| Selection | Action |
|-----------|--------|
| **Grant missing privileges** | **Read and follow** `workflows/grant-permissions.md`, passing the role and missing privileges as context |
| **Check another role** | Return to B3c with new role name |
| **Done** | Proceed to **Step 3** in `SKILL.md` |
