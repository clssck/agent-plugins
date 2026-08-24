---
name: access-troubleshooter
description: >-
  Debug authorization and permission issues in Snowflake.
  Use when: access denied, insufficient privileges, permission errors, 
  role issues, missing grants, privilege analysis,
  least-privilege role creation, find authorizing roles.
  Triggers: access denied, insufficient privileges, permission error,
  authorization failed, can't access, missing permission, grant needed,
  role recommendation, SQL access control error, does not exist or not authorized,
  EXPLAIN_PRIVILEGES, SYSTEM$ANALYZE_ROLE_ACCESS, SYSTEM$SUGGEST_ROLE_GRANTS.
---

# Access Troubleshooter

Debug authorization failures, analyze required privileges, and manage role-based access in Snowflake.

## When to Use

- User gets "Insufficient privileges" or "Access denied" errors
- User wants to know what privileges are needed for a query
- User wants to find which role can run a specific query
- User needs to create a least-privilege role for a task
- User asks "Why can't [person/role] access [object]?"
- User wants to grant missing privileges to an existing role

## Auto-Trigger Error Patterns

When you detect these error message patterns, AUTOMATICALLY offer to help:

**Pattern 1:** `SQL access control error:\nInsufficient privileges to operate on`

**Pattern 2:** `SQL compilation error:.*does not exist or not authorized`

**When detected, respond with:**

```
Would you like me to debug this using the access-troubleshooter skill? I can:

1. Find what privileges are missing for this query
2. Find which roles can run this query
3. Generate GRANT statements to fix the access
```

If user agrees, proceed to the Main Workflow below.

## Workflows

| Workflow | Description |
|----------|-------------|
| `workflows/debug-error.md` | Full diagnostic flow for authorization errors (Steps A1–A6) |
| `workflows/analyze-privileges.md` | List all required or missing privileges for a query |
| `workflows/find-authorizing-roles.md` | Find which roles can authorize a query |
| `workflows/create-role.md` | Create a new least-privilege role for a query |
| `workflows/grant-permissions.md` | Grant missing privileges to an existing role |

## References

Load [references/function-reference.md](references/function-reference.md) on-demand for detailed syntax, parameters, and output format for `EXPLAIN_PRIVILEGES`, `SYSTEM$ANALYZE_ROLE_ACCESS`, and `SYSTEM$SUGGEST_ROLE_GRANTS`.

---

## Agent Behavior Rules (Apply to ALL Workflows)

1. **Safety protocols** — Never run GRANT or CREATE ROLE without explicit user approval. Present all SQL statements for review before execution. Provide revert instructions after changes.

2. **Fresh data only** — Do NOT use cached results from previous authorization analyses. Roles, grants, and privileges can change at any time. Always re-query the current state.

3. **Follow step order** — Execute steps sequentially as defined. Do not skip steps, pre-select options, or jump ahead based on the user's opening message. Route based on AskUserQuestion selections, not inferred intent.

4. **Hard stops are mandatory** — Steps marked with a checkpoint are gates. Do not proceed until the required user input is received. Once approved, proceed directly without re-asking.

5. **Choices vs. free text** — When the user must choose between options (routing, resolution strategy, role selection), use AskUserQuestion with a selectable list. Only collect as plain free text when creating new names (role name).

6. **EXPLAIN_PRIVILEGES first for diagnostics** — In the initial diagnostic phase, always use `EXPLAIN_PRIVILEGES` first to understand requirements and check session authorization. Subsequent steps (e.g., finding which roles can authorize, suggesting grants) may use `SYSTEM$ANALYZE_ROLE_ACCESS` or `SYSTEM$SUGGEST_ROLE_GRANTS` directly.

7. **`<ANY>` translation** — When generating GRANT statements from `EXPLAIN_PRIVILEGES` output, translate `"<ANY>"` to `USAGE` for DATABASE and SCHEMA objects.

8. **On-behalf-of analysis** — If the user is analyzing for a different user (e.g., "check what USER_X is missing," "debug this for BOB," "what roles can run this for ALICE"), collect the target username (store as `<TARGET_USER>`) and use it throughout:
   - `SYSTEM$ANALYZE_ROLE_ACCESS(sql, false, '<TARGET_USER>')` so `isGranted` reflects the target user's grants
   - `SYSTEM$SUGGEST_ROLE_GRANTS(sql, '', '<TARGET_USER>')` for user-scoped grant suggestions
   - `EXPLAIN_PRIVILEGES(..., for_role => '<role>')` when checking a specific role of the target user
   - `GRANT ROLE ... TO USER <TARGET_USER>` when granting roles

   **If on-behalf-of queries fail with insufficient privileges** (e.g., `SHOW GRANTS TO USER <TARGET_USER>` or `SYSTEM$ANALYZE_ROLE_ACCESS` with `forUser` returns a permission error): **Stop analysis.** Tell the user: *"You don't have sufficient privileges to analyze this statement on behalf of another user. Please contact your system administrator. ACCOUNTADMIN role may be required to manage the privileges on the object."* Proceed to **Step 3** in the Main Workflow.

---

## Main Workflow

### Step 1: Determine Intent

Ask what the user wants to do. **Do NOT load any workflow file yet** — just record the selection for Step 2.

```python
AskUserQuestion(
    questions=[{
        "question": "What would you like to do?",
        "header": "Privilege Analysis",
        "multiSelect": false,
        "options": [
            {"label": "Debug an authorization error", "description": "I got a permission error and need to diagnose and fix it"},
            {"label": "Analyze what privileges a query needs", "description": "Show all required or missing privileges for a SQL statement"},
            {"label": "Find which roles can run a query", "description": "Search for existing roles that can authorize a SQL statement"},
            {"label": "Create a least-privilege role", "description": "Create a new role with minimum privileges for a SQL statement"},
            {"label": "Grant missing privileges to a role", "description": "Add missing privileges to an existing role"}
        ]
    }]
)
```

Record the selection, then proceed to **Step 2**.

---

### Step 2: Load and Execute Workflow

**YOU MUST read the relevant workflow file below and then follow it step by step.** The workflow files contain the full procedure.

| Step 1 Selection | File to read (use Read tool) |
|-----------|--------|
| **Debug an authorization error** | `workflows/debug-error.md` |
| **Analyze what privileges a query needs** | `workflows/analyze-privileges.md` |
| **Find which roles can run a query** | `workflows/find-authorizing-roles.md` |
| **Create a least-privilege role** | `workflows/create-role.md` |
| **Grant missing privileges to a role** | `workflows/grant-permissions.md` |

**If you proceed without reading the file, the workflow will be wrong.**

Once the workflow completes its final step, proceed to **Step 3**.

---

### Step 3: Repeat or Done

```python
AskUserQuestion(
    questions=[{
        "question": "What would you like to do next?",
        "header": "Next Step",
        "multiSelect": false,
        "options": [
            {"label": "Start another operation", "description": "Return to the privilege analysis main menu"},
            {"label": "Done", "description": "Exit"}
        ]
    }]
)
```

| Selection | Action |
|-----------|--------|
| **Start another operation** | Go back to **Step 1** and present its exact AskUserQuestion again. Do NOT infer the next operation. |
| **Done** | Workflow complete — stop. Do not suggest further actions. |

---

## Quick Reference

### Function Quick Reference

| Question | Function | Notes |
|----------|----------|-------|
| What privileges needed? | `EXPLAIN_PRIVILEGES(sql)` | Use first |
| What am I missing? | `EXPLAIN_PRIVILEGES(sql, missing_only => true)` | Session check |
| What is role missing? | `EXPLAIN_PRIVILEGES(sql, missing_only => true, for_role => 'ROLE')` | Per-role check |
| Which roles can authorize? | `SYSTEM$ANALYZE_ROLE_ACCESS(sql)` | Sorted role hierarchy |
| What grants to add for a role? | `SYSTEM$SUGGEST_ROLE_GRANTS(sql, 'ROLE')` | Per-role coverage of missing grants |

### Recommended Order

1. `EXPLAIN_PRIVILEGES(sql)` — understand requirements
2. `EXPLAIN_PRIVILEGES(sql, missing_only => true)` — can session authorize?
3. `EXPLAIN_PRIVILEGES(sql, missing_only => true, for_role => 'ROLE')` — check each user role
4. `SYSTEM$ANALYZE_ROLE_ACCESS(sql)` — which roles can authorize?
5. `SYSTEM$SUGGEST_ROLE_GRANTS(sql, 'ROLE')` — what grants to add? (if needed)

---

## Common Error Messages

- "SQL access control error: Insufficient privileges to operate on schema"
- "SQL access control error: Insufficient privileges to operate on table"
- "SQL compilation error: Object 'X' does not exist or not authorized"
- "SQL compilation error: Database 'X' does not exist or not authorized"
- "SQL compilation error: Schema 'X' does not exist or not authorized"

---

## Troubleshooting

| Issue | Possible Cause | Action |
|-------|---------------|--------|
| `supported: false` from ANALYZE_ROLE_ACCESS | Runtime authorization (row access, masking policies) | Use EXPLAIN_PRIVILEGES or test with execution |
| "requires access on all objects in the statement" | Role cannot resolve one or more objects in the query | **Stop analysis.** Do NOT attempt manual lookups (SHOW GRANTS, SHOW TABLES, etc.) — this would leak object existence. Tell user: *"Please contact your system administrator. ACCOUNTADMIN role may be required to manage the privileges on the object."* |
| User has role but still can't access | Wrong active role, row-level security, masking policy | Check `CURRENT_ROLE()`, `SHOW ROW ACCESS POLICIES`, `SHOW MASKING POLICIES` |
| Privilege exists but query fails | Object doesn't exist, wrong DB/schema context, future grant needed | Verify object exists and context is correct |
| EXPLAIN_PRIVILEGES "Unsupported feature" | Function not available in this account | Fall back to `SYSTEM$ANALYZE_ROLE_ACCESS` |

---

## Stopping Points

- Step 1: always wait for user selection before routing
- Step 2: must load the workflow file — do not skip
- `workflows/debug-error.md`: checkpoint before executing GRANT or CREATE ROLE statements
- `workflows/create-role.md`: checkpoint before creating role and executing grants
- `workflows/grant-permissions.md`: checkpoint before executing grant statements
- Any time resolution SQL is generated: present for approval before executing

**Resume rule:** Upon user approval, proceed directly to the next step without re-asking.

---

## Output

- Identified missing privileges with specific details
- Generated appropriate GRANT statements
- Created least-privilege role if requested
- Verified access restored
