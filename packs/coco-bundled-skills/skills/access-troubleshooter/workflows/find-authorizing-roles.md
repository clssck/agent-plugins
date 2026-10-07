---
name: find-authorizing-roles-workflow
parent_skill: access-troubleshooter
---

# Workflow C: Find Authorizing Roles

## When to Load

Loaded from `access-troubleshooter/SKILL.md` when user selects **Find which roles can run a query**, or from `workflows/debug-error.md` A5 when user selects **Find an existing role**.

## Prerequisites

- Step 1 (intent selection) completed

---

## C1: Get the SQL Statement

Ask the user for the SQL statement. Store as `<SQL_STATEMENT>`.

If arriving from `debug-error.md`, the statement and `<USERNAME>` are already known — skip what's available.

If `<USERNAME>` is not yet known, run `SELECT CURRENT_USER();` and store as `<USERNAME>` (needed for scoped search in C3a and for granting roles).

---

## C2: Choose Search Scope

```python
AskUserQuestion(
    questions=[{
        "question": "Which roles should I search?",
        "header": "Search Scope",
        "multiSelect": false,
        "options": [
            {"label": "My roles only", "description": "Search only roles already granted to me (fast)"},
            {"label": "All account roles", "description": "Search all roles in the account (slower, may find roles I don't have yet)"}
        ]
    }]
)
```

| Selection | Go to |
|-----------|-------|
| My roles only | C3a |
| All account roles | C3b |

---

## C3a: Search User's Roles

Pass `<USERNAME>` as the `forUser` parameter so `isGranted` accurately reflects the user's granted roles:

```sql
SELECT SYSTEM$ANALYZE_ROLE_ACCESS('<SQL_STATEMENT>', false, '<USERNAME>');
```

> If the call returns **"requires access on all objects in the statement"**: **Stop analysis.** Do NOT attempt manual lookups. Tell user: *"Your current role doesn't have sufficient privileges to analyze this statement. Please contact your system administrator. ACCOUNTADMIN role may be required to manage the privileges on the object."* Proceed to **Step 3** in `SKILL.md`.

> **On-behalf-of variant:** Use `SYSTEM$ANALYZE_ROLE_ACCESS('<SQL_STATEMENT>', false, '<TARGET_USER>')` so `isGranted` reflects the target user's grants. If this fails with insufficient privileges, **stop analysis** (see Agent Behavior Rule #8).

From the results, **only present roles where `isGranted: true`** — these are the roles the user actually has. Go to C4.

---

## C3b: Search All Account Roles

```sql
SELECT SYSTEM$ANALYZE_ROLE_ACCESS('<SQL_STATEMENT>', false, '<USERNAME>');
```

> If the call returns **"requires access on all objects in the statement"**: **Stop analysis.** Do NOT attempt manual lookups. Tell user: *"Your current role doesn't have sufficient privileges to analyze this statement. Please contact your system administrator. ACCOUNTADMIN role may be required to manage the privileges on the object."* Proceed to **Step 3** in `SKILL.md`.

> **On-behalf-of variant:** Use `SYSTEM$ANALYZE_ROLE_ACCESS('<SQL_STATEMENT>', false, '<TARGET_USER>')` so `isGranted` reflects the target user's grants. If this fails with insufficient privileges, **stop analysis** (see Agent Behavior Rule #8).

Present all `authorizingRoles` results (both `isGranted: true` and `isGranted: false`). The output is sorted leaf-to-root by `depth`, then alphabetically — prefer roles with lower depth (more specific, fewer inherited privileges).

Parse and present results. Go to C4.

---

## C4: Present Results

### If `supported: false`

The query uses runtime authorization (row access policies, masking policies, dynamic data masking) that can't be statically analyzed. Inform the user and suggest using `EXPLAIN_PRIVILEGES` instead or testing with actual execution.

### If `authorizingRoles` is non-empty

Present a table:

```
Roles that can authorize this query:

| Role Name           | Granted to You? |
|---------------------|-----------------|
| <role1>             | Yes / No        |
| <role2>             | Yes / No        |
| ...                 | ...             |
```

**If a role with `isGranted: true` exists:**

```
You already have <ROLE_NAME>. To use it:

    USE ROLE <ROLE_NAME>;
    <SQL_STATEMENT>;
```

Then proceed to **Step 3** in `SKILL.md`.

**If only `isGranted: false` roles exist:**

```python
AskUserQuestion(
    questions=[{
        "question": "Found roles that can authorize, but none are granted to you. What would you like to do?",
        "header": "Next Step",
        "multiSelect": false,
        "options": [
            {"label": "Grant an existing role to me", "description": "Request one of the found roles be granted to my user"},
            {"label": "Create a new role instead", "description": "Create a new least-privilege role"},
            {"label": "Done", "description": "No further action needed"}
        ]
    }]
)
```

| Selection | Action |
|-----------|--------|
| **Grant an existing role** | Generate `GRANT ROLE <FOUND_ROLE> TO USER <USERNAME>;` — present for approval, execute, then proceed to **Step 3** in `SKILL.md` |
| **Create a new role** | **Read and follow** `workflows/create-role.md` |
| **Done** | Proceed to **Step 3** in `SKILL.md` |

### FALLBACK: Only ACCOUNTADMIN Returned

> This fallback only applies when `SYSTEM$ANALYZE_ROLE_ACCESS` returned successfully (i.e., the current role can resolve the objects). Do NOT use this if the call failed with "requires access on all objects."

`SYSTEM$ANALYZE_ROLE_ACCESS` may not return all roles. Verify with `SHOW GRANTS`:

```sql
SHOW GRANTS ON TABLE <DB>.<SCHEMA>.<TABLE>;
-- Or for CREATE: SHOW GRANTS ON SCHEMA <DB>.<SCHEMA>;
```

Compare with `SYSTEM$ANALYZE_ROLE_ACCESS` output. If additional roles are found, present them.

### If `authorizingRoles` is empty

No existing role can authorize. Offer to create one:

```python
AskUserQuestion(
    questions=[{
        "question": "No existing role can authorize this query. Would you like to create one?",
        "header": "No Roles Found",
        "multiSelect": false,
        "options": [
            {"label": "Create a new role", "description": "Create a least-privilege role for this query"},
            {"label": "Done", "description": "No further action needed"}
        ]
    }]
)
```

| Selection | Action |
|-----------|--------|
| **Create a new role** | **Read and follow** `workflows/create-role.md` |
| **Done** | Proceed to **Step 3** in `SKILL.md` |
