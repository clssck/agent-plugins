---
name: review-join
parent_skill: data-cleanrooms
description: "Review and Join Collaborations - review invitations, check status, and join collaborations. Triggers: join collaboration, review invitation, accept invitation."
---

# Review and Join Collaboration

Review collaboration invitations and join collaborations as owner or non-owner.

## When to Use

- User has been invited to a collaboration and wants to join
- User wants to review a collaboration before joining
- User wants to check the status of their join process
- User asks to "join collaboration", "review invitation", or "accept invitation"

## Prerequisites

Before joining, the user must have:
1. A pending collaboration invitation (visible in VIEW_COLLABORATIONS)
2. Appropriate role (SAMOOHA_APP_ROLE or custom role with join privileges)

## Key Concepts

### Ownership Determination

Compare current account with OWNER_ACCOUNT from VIEW_COLLABORATIONS:
- **Owner**: Current account == OWNER_ACCOUNT - Skip REVIEW, go directly to JOIN
- **Non-Owner**: Current account != OWNER_ACCOUNT - Must REVIEW first, then JOIN

### Collaboration Status Flow

| Status | Meaning | Next Action |
|--------|---------|-------------|
| (NULL COLLABORATION_NAME) | Not yet reviewed | REVIEW first |
| INVITED | Review done, ready to join | JOIN |
| JOINING | Join in progress | Do NOT retry or proceed — wait for join to complete, then re-check status |
| JOIN_FAILED | Join failed | Check error details, then retry JOIN |
| JOINED | Successfully joined | Done |

## Workflow

> **CRITICAL**: Steps 1-3 are MANDATORY before any join or review action. You MUST determine ownership first — NEVER skip directly to JOIN or REVIEW.

### Step 1: View Available Collaborations

```sql
CALL {DB}.COLLABORATION.VIEW_COLLABORATIONS();
```

Check for:
- `COLLABORATION_NAME` - If NULL, not yet reviewed
- `OWNER_ACCOUNT` - Compare with current account to determine ownership
- `SOURCE_NAME` - Original collaboration name from owner

### Step 2: Get Current Account

**Option A: Standard SQL (recommended)**
```sql
SELECT CURRENT_ORGANIZATION_NAME(), CURRENT_ACCOUNT_NAME();
```

**Option B: DCR Procedure (for agents)**
```sql
CALL {DB}.AGENTS.DCR$GET_CURRENT_ACCOUNT_IDENTIFIER();
```

Returns: Account identifier in `ORGNAME.ACCOUNT_NAME` format for comparison with OWNER_ACCOUNT

### Step 3: Determine Ownership (MANDATORY before proceeding)

Compare the current account identifier (from Step 2) with `OWNER_ACCOUNT` (from Step 1):

- **If current account == OWNER_ACCOUNT** → This is the **owner**. Skip REVIEW, go to Step 4 (Check Status) and then Step 6 (Join).
- **If current account != OWNER_ACCOUNT** → This is a **non-owner**. Proceed to Step 4

**NEVER call JOIN without first completing this ownership check.** Even if the user says "just join it", you must verify ownership because non-owners who skip REVIEW will get an error.

### Step 4: Check Status (if COLLABORATION_NAME exists)

If `COLLABORATION_NAME` is not NULL in the VIEW_COLLABORATIONS output, check the current status:

```sql
CALL {DB}.COLLABORATION.GET_STATUS('collaboration_name');
```

Use the status to determine the next action (see Collaboration Status Flow above).

### Step 5: Review (Non-Owners Only)

**Skip this step if current account is the owner (determined in Step 3).**

Non-owners must review before joining to see the collaboration spec:

**MANDATORY STOPPING POINT**: Before calling REVIEW, ask the user for a **local name** for this collaboration.

> Propose: "I'll use the same name as the source (`<SOURCE_NAME>`). Would you like a different local name?"
>
> - If the user provides a name, use it as `local_name`
> - If the user agrees or doesn't specify, use `SOURCE_NAME` as the default `local_name`

```sql
CALL {DB}.COLLABORATION.REVIEW('source_name', 'owner_account', 'local_name');
```

Parameters:
- `source_name` - SOURCE_NAME from VIEW_COLLABORATIONS
- `owner_account` - OWNER_ACCOUNT from VIEW_COLLABORATIONS
- `local_name` - User's chosen local name, or SOURCE_NAME as default

Returns: Full collaboration YAML spec for user review

### Step 6: Join

**MANDATORY STOPPING POINT**: Present the collaboration details to the user before joining.

Ask: "Do you want to join this collaboration? (Yes/No). Note: Secondary roles will be temporarily disabled during this operation."

NEVER proceed without explicit user confirmation.

> **CRITICAL: Disable Secondary Roles Before JOIN**
>
> The JOIN procedure **requires** secondary roles to be disabled. If secondary roles are active, JOIN will fail with: *"Secondary roles must be disabled before calling this procedure."*

```sql
-- Step 6a: Disable secondary roles (REQUIRED before JOIN)
USE SECONDARY ROLES NONE;

-- Step 6b: Join the collaboration
CALL {DB}.COLLABORATION.JOIN('collaboration_name');

-- Step 6c: Restore secondary roles after JOIN completes
USE SECONDARY ROLES ALL;
```

**If JOIN is canceled unexpectedly**: Inform the user: "The join operation was canceled. Please run `USE SECONDARY ROLES ALL` (or start a new session) to restore your secondary roles."

Parameters:
- `collaboration_name` - For owners: the SOURCE_NAME. For non-owners: the local_name chosen in Step 5.

## Procedures Reference

| Procedure/Function | Purpose | Parameters |
|--------------------|---------|------------|
| `COLLABORATION.VIEW_COLLABORATIONS()` | List all collaborations | None |
| `SELECT CURRENT_ORGANIZATION_NAME(), CURRENT_ACCOUNT_NAME()` | Get current account (standard SQL) | None |
| `AGENTS.DCR$GET_CURRENT_ACCOUNT_IDENTIFIER()` | Get current account (for agents) | None |
| `COLLABORATION.GET_STATUS(name)` | Check collaboration status | String |
| `COLLABORATION.REVIEW(source, owner, name)` | Review invitation (non-owners) | 3 strings |
| `COLLABORATION.JOIN(name)` | Join collaboration | String |

## Examples

### Non-Owner Join Flow

```sql
-- Step 1: View collaborations
CALL {DB}.COLLABORATION.VIEW_COLLABORATIONS();
-- Result shows: SOURCE_NAME='PARTNER_COLLAB', OWNER_ACCOUNT='ORG.PARTNER', COLLABORATION_NAME=NULL

-- Step 2: Get current account
SELECT CURRENT_ORGANIZATION_NAME(), CURRENT_ACCOUNT_NAME();
-- Result: 'MYORG', 'MY_ACCOUNT' -> combine as MYORG.MY_ACCOUNT

-- Step 3: Determine ownership
-- MYORG.MY_ACCOUNT != ORG.PARTNER -> Non-owner. Must REVIEW first.

-- Step 5: Review (ask user for local name first)
-- Agent: "I'll use 'PARTNER_COLLAB' as the local name. Would you like a different name?"
-- User: "Use 'my_local_collab'"
CALL {DB}.COLLABORATION.REVIEW('PARTNER_COLLAB', 'ORG.PARTNER', 'my_local_collab');
-- Returns: YAML spec for review

-- Step 6: Join (after user confirms)
USE SECONDARY ROLES NONE;
CALL {DB}.COLLABORATION.JOIN('my_local_collab');
USE SECONDARY ROLES ALL;
```

### Owner Join Flow

```sql
-- Step 1: View collaborations
CALL {DB}.COLLABORATION.VIEW_COLLABORATIONS();
-- Result shows: SOURCE_NAME='MY_COLLAB', OWNER_ACCOUNT='MYORG.MY_ACCOUNT'

-- Step 2: Get current account
SELECT CURRENT_ORGANIZATION_NAME(), CURRENT_ACCOUNT_NAME();
-- Result: 'MYORG', 'MY_ACCOUNT' -> MYORG.MY_ACCOUNT

-- Step 3: Determine ownership
-- MYORG.MY_ACCOUNT == MYORG.MY_ACCOUNT -> Owner. Skip REVIEW.

-- Step 6: Join directly (owners skip REVIEW — but still must disable secondary roles)
USE SECONDARY ROLES NONE;
CALL {DB}.COLLABORATION.JOIN('MY_COLLAB');
USE SECONDARY ROLES ALL;
```

---

## Required Privileges

If operations fail with "Insufficient privileges", see the parent data-cleanrooms SKILL.md "Required Privileges" section for how to grant privileges using `{DB}.ADMIN.GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE` or `{DB}.ADMIN.GRANT_PRIVILEGE_ON_OBJECT_TO_ROLE`.

| Procedure | Privilege | Scope |
|-----------|-----------|-------|
| `VIEW_COLLABORATIONS()` | `VIEW COLLABORATIONS` | Account |
| `REVIEW(source, owner, name)` | `REVIEW COLLABORATION` | Account |
| `JOIN(name)` | `JOIN COLLABORATION` | Account |
| `GET_STATUS(name)` | `GET STATUS` | Collaboration |

**Example: Grant REVIEW COLLABORATION privilege**

```sql
-- Use ACCOUNTADMIN role
USE ROLE ACCOUNTADMIN;

-- Grant privilege to a user role
CALL {DB}.ADMIN.GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE(
    'REVIEW COLLABORATION',
    '<user_role>'
);
```

**Example: Grant JOIN COLLABORATION privilege**

```sql
-- Use ACCOUNTADMIN role
USE ROLE ACCOUNTADMIN;

-- Grant privilege to a user role
CALL {DB}.ADMIN.GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE(
    'JOIN COLLABORATION',
    '<user_role>'
);
```

---

## Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| "Secondary roles must be disabled" | Procedure requires Secondary roles to be disabled | Run `USE SECONDARY ROLES NONE` before JOIN and run `USE SECONDARY ROLES ALL` to restore after join |
| "Insufficient privileges" | Missing DCR privilege | See Required Privileges above |

---

## Stopping Points

- Before Step 5 (REVIEW): Ask the user for a local name (propose SOURCE_NAME as default)
- After Step 5 (REVIEW): Present collaboration spec for user review
- Before Step 6 (JOIN): Get explicit user confirmation before joining

**Resume rule:** Upon user approval, proceed directly without re-asking.

## Output

| Operation | Output |
|-----------|--------|
| Review | Collaboration YAML spec displayed for user approval |
| Join | Confirmation that collaboration was joined successfully |

## Important Notes

- **ALWAYS determine ownership (Steps 1-3) before any action** — even if the user says "just join", you must check whether they are the owner or non-owner first
- **ALWAYS run `USE SECONDARY ROLES NONE` before calling JOIN** — the procedure may fail if secondary roles are active. Restore with `USE SECONDARY ROLES ALL` after JOIN completes.
- Non-owners who call JOIN without first calling REVIEW will get an error
- When reviewing, always ask the user for a local name or propose using SOURCE_NAME as the default
- REVIEW and JOIN are synchronous operations (may take a few minutes)
- Owners skip REVIEW and go directly to JOIN
- Non-owners must REVIEW first to see the collaboration spec
- After successful JOIN, status should be JOINED
- If JOIN_FAILED, check error details and retry
- If JOIN is canceled or interrupted, the user should run `USE SECONDARY ROLES ALL` or start a new session to restore their roles
