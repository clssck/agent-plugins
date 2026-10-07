---
name: tear-down-leave
parent_skill: data-cleanrooms
description: "Provides APIs and step-by-step guidance to tear down or leave DCR collaborations with complete cleanup of all local resources. Triggers: tear down, leave, drop, delete, clean room, DCR, collaboration"
---

# DCR Collaboration Teardown and Leave

## Overview
This skill guides users through the proper process of tearing down or leaving Data Clean Room (DCR) collaborations using Snowflake's DCR v2 Collaboration API. It ensures complete cleanup of all local resources including databases, views, and collaboration artifacts to prevent data leaks and maintain security.

**Exit paths depend on status—always interpret `GET_STATUS` together with Snowflake DCR documentation** (`snowflake_product_docs`: `https://docs.snowflake.com/en/user-guide/cleanrooms/v2/about`; if that tool is unavailable, `cortex search docs "<query>"` via bash):

- **Owner TEARDOWN** generally requires **JOINED** for your account before orderly teardown (see Step 3).
- **Invited collaborator LEAVE** is not limited to **JOINED** only: in **IN_REVIEW** / **PREVIEWING**, product behavior may perform **local cleanup** and reach **LEFT** without a full join—follow `GET_STATUS` and documentation for your scenario.
- **INSTALLATION_FAILED**, **JOINING_FAILED** (may appear as **JOIN_FAILED** on some surfaces), or similar failed setup states: use documentation-first remediation and join retry paths—do **not** treat **TEARDOWN** or **LEAVE** as the default fix for these failures.

## Prerequisites

- Active Snowflake connection with appropriate DCR collaboration permissions
- SAMOOHA_APP_ROLE, or at minimum REVIEW_COLLABORATION_ROLE (see Privilege Management Commands)
- Collaboration must be accessible to your account (either as owner or invited collaborator)

**Note**: You do not need to know the collaboration name in advance - the skill will help you identify it.

## Workflow

### Step 1: Identify Collaboration Details

**Goal:** Gather information about the collaboration to be terminated

**Actions:**

1. **Ask** user for collaboration details:
   ```
   Please provide:
   - Collaboration name: [exact name of the DCR collaboration]
   ```

2. **Verify** collaboration exists:
   ```sql
   CALL {DB}.COLLABORATION.VIEW_COLLABORATIONS();
   ```

3. **Document** collaboration resources before deletion

**Output:** Validated collaboration information and current resource inventory

### Step 2: Get Current Account and Resource Inventory

**Goal:** Identify current account and all resources that will be affected by the teardown

**Actions:**

1. **Get current account identifier:**

   **Option A: Standard SQL (recommended)**
   ```sql
   SELECT CURRENT_ORGANIZATION_NAME(), CURRENT_ACCOUNT_NAME();
   ```

   **Option B: DCR Procedure (for agents)**
   ```sql
   CALL {DB}.AGENTS.DCR$GET_CURRENT_ACCOUNT_IDENTIFIER();
   ```

   Returns: Account identifier in `ORG_NAME.ACCOUNT_NAME` format for comparison with OWNER_ACCOUNT

2. **List** all collaboration-related resources:
   ```sql
   CALL {DB}.COLLABORATION.GET_STATUS('<COLLABORATION_NAME>');
   
   CALL {DB}.COLLABORATION.VIEW_COLLABORATIONS();
   ```

3. **Determine user role** by comparing current account with OWNER_ACCOUNT:
   - **Owner**: Current account == OWNER_ACCOUNT from VIEW_COLLABORATIONS
   - **Invited Collaborator**: Current account != OWNER_ACCOUNT from VIEW_COLLABORATIONS

4. **Warn** the user that tearing down or leaving will remove all collaboration resources — they should review any downstream dependencies before proceeding.

5. **INSTALLATION_FAILED / JOINING_FAILED — documentation-first gate (do not skip):**

   If `GET_STATUS` shows **INSTALLATION_FAILED** or **JOINING_FAILED** (may appear as **JOIN_FAILED** externally—for the collaboration or your account’s state, use the exact fields returned by the procedure):

   - **Do not** recommend **TEARDOWN** or **LEAVE** as the default next step to “fix” or reset these failures.
   - **Do not** call `TEARDOWN` or `LEAVE` to escape a failed installation or join attempt without product guidance.
   - **Must** consult Snowflake Data Clean Rooms documentation using the **same tool-first pattern as the parent data-cleanrooms skill**: (`snowflake_product_docs`: `https://docs.snowflake.com/en/user-guide/cleanrooms/v2/about`; if that tool is unavailable, `cortex search docs "<query>"` via bash)—search for installation failure, joining failure, collaboration status, and remediation (including retrying **JOIN** from allowed entry states such as **PREVIEWING** or **JOINING_FAILED** per docs).
   - Tell the user clearly: orderly **TEARDOWN** / **LEAVE** in this skill assume a healthy exit path; skipping remediation can cause failed API calls or inconsistent resources.

   **Stop** the teardown/leave workflow here until documentation-backed remediation is reflected on a fresh `GET_STATUS` (often progressing toward **JOINED**), unless the user explicitly changes goal (e.g., they only want documentation pointers and are not asking you to execute teardown/leave yet).

6. **Present** impact assessment to user:

   - If Step 5 applied (failed setup: **INSTALLATION_FAILED** or **JOINING_FAILED** / **JOIN_FAILED**), use:
     ```
     Collaboration: <COLLABORATION_NAME>
     Current Account: [ORG_NAME.ACCOUNT_NAME]
     Owner Account: [OWNER_ACCOUNT from VIEW_COLLABORATIONS]
     Your Role: [Owner / Invited Collaborator]
     Current Status: [INSTALLATION_FAILED | JOINING_FAILED / JOIN_FAILED]

     Next steps: Use snowflake_product_docs / cortex search docs (see Overview) to remediate per product guidance before orderly TEARDOWN or LEAVE.
     Teardown / Leave from this skill: deferred until GET_STATUS reflects a healthy exit path (commonly JOINED after retry).

     Warning: Do not use TEARDOWN or LEAVE to recover from failed setup without documentation-backed remediation.
     ```
   - Otherwise (status is **JOINED**, **PREVIEWING** / **IN_REVIEW** where LEAVE applies, or another state that allows orderly teardown/leave per docs):
     ```
     Collaboration: <COLLABORATION_NAME>
     Current Account: [ORG_NAME.ACCOUNT_NAME]
     Owner Account: [OWNER_ACCOUNT from VIEW_COLLABORATIONS]
     Your Role: [Owner / Invited Collaborator]
     Current Status: [status from GET_STATUS]
     Available Action: [Teardown / Leave]

     Warning: This action cannot be undone. All collaboration
     resources will be removed.
     ```

**MANDATORY STOPPING POINT**: Present role determination and impact assessment to the user. If status is **INSTALLATION_FAILED** or **JOINING_FAILED** / **JOIN_FAILED**, do **not** ask for confirmation to run teardown or leave; only continue after remediation per docs is reflected on `GET_STATUS` (or the user has pivoted away from executing teardown/leave). For **JOINED**, **PREVIEWING** / **IN_REVIEW** when applicable, or other valid exit states per documentation, get explicit confirmation for teardown (owner) or leave (invited collaborator) before proceeding.

### Step 3: Execute Teardown or Leave Process

**Goal:** Safely terminate collaboration participation based on user role

**Prerequisites before running TEARDOWN / LEAVE SQL:** If Step 2’s documentation-first gate applied (**INSTALLATION_FAILED** / **JOINING_FAILED** / **JOIN_FAILED**), do **not** run the procedures below—return to Step 2. Otherwise interpret `GET_STATUS` with Snowflake DCR documentation:

- **Owner TEARDOWN:** typically requires **JOINED** before orderly teardown unless documentation specifies otherwise for your status.
- **Invited collaborator LEAVE:** if **JOINED**, use the leave flow below; if **PREVIEWING** / **IN_REVIEW**, documentation/API may allow **LEAVE** for local-only cleanup without **JOINED**—follow product guidance rather than assuming join completion.

**Actions based on role determined in Step 2:**

**For Complete Teardown (Owner Only - when current account == OWNER_ACCOUNT):**

1. **Ensure** you have joined the collaboration (owners must join before teardown):
   ```sql
   CALL {DB}.COLLABORATION.GET_STATUS('<COLLABORATION_NAME>');
   -- Status should show JOINED for your account
   ```

2. **Start** the teardown process:
   ```sql
   CALL {DB}.COLLABORATION.TEARDOWN('<COLLABORATION_NAME>');
   ```

3. **Monitor** teardown status:
   ```sql
   CALL {DB}.COLLABORATION.GET_STATUS('<COLLABORATION_NAME>');
   ```
   - If status is **DROPPING**: Teardown is in progress. Continue monitoring with GET_STATUS until it transitions.
   - If status is **DROP_FAILED**: Retry the teardown: `CALL {DB}.COLLABORATION.TEARDOWN('<COLLABORATION_NAME>');`
   - If status is **LOCAL_DROP_PENDING**: Ready for final cleanup call. Proceed to step 4.

4. **Complete** the teardown with local resource cleanup:
   ```sql
   CALL {DB}.COLLABORATION.TEARDOWN('<COLLABORATION_NAME>');
   ```

**For Leaving Collaboration (Invited Collaborator - when current account != OWNER_ACCOUNT):**

1. **Confirm status matches an exit path in documentation:**
   ```sql
   CALL {DB}.COLLABORATION.GET_STATUS('<COLLABORATION_NAME>');
   ```
   - If **JOINED**, proceed with LEAVE below.
   - If **PREVIEWING** / **IN_REVIEW**, **LEAVE** may apply for local cleanup per product behavior—confirm with documentation rather than requiring **JOINED**.

2. **Start** the leave process:
   ```sql
   CALL {DB}.COLLABORATION.LEAVE('<COLLABORATION_NAME>');
   ```

3. **Monitor** leave status:
   ```sql
   CALL {DB}.COLLABORATION.GET_STATUS('<COLLABORATION_NAME>');
   ```
   - If status is **LEAVING**: Leave is in progress. Continue monitoring with GET_STATUS until it transitions.
   - If status is **LEAVE_FAILED**: Retry the leave: `CALL {DB}.COLLABORATION.LEAVE('<COLLABORATION_NAME>');`
   - If status is **LOCAL_DROP_PENDING**: Ready for final cleanup call. Proceed to step 4.

4. **Complete** the leave process with local resource cleanup:
   ```sql
   CALL {DB}.COLLABORATION.LEAVE('<COLLABORATION_NAME>');
   ```

**Actions:**

1. **Execute** appropriate SQL commands based on user's role and choice
2. **Verify** each step completes successfully
3. **Handle** any errors gracefully with clear explanations

### Step 4: Local Resource Cleanup

**Goal:** Remove all local artifacts and references

**Actions:**

1. **Validate** cleanup is complete:
   ```sql
   CALL {DB}.COLLABORATION.VIEW_COLLABORATIONS();
   ```

**Output:** Confirmation that collaboration no longer exists in account

### Step 5: Present Summary

**Goal:** Present a clear summary of what was done

**Actions:**

1. **Present** teardown/leave summary to user:
   ```
   Collaboration Teardown Summary:
   - Collaboration: <NAME>
   - Action: [Teardown/Leave]
   - Status: [Completed/In Progress]
   - Resources Removed: [List]
   ```

**Output:** Summary of completed actions for user review

## API References

### Core DCR v2 Collaboration Commands

```sql
-- Get current account identifier
SELECT CURRENT_ORGANIZATION_NAME(), CURRENT_ACCOUNT_NAME();

-- Get current account identifier (for agents)
CALL {DB}.AGENTS.DCR$GET_CURRENT_ACCOUNT_IDENTIFIER();

-- View all collaborations
CALL {DB}.COLLABORATION.VIEW_COLLABORATIONS();

-- Get collaboration status and details
CALL {DB}.COLLABORATION.GET_STATUS('<COLLABORATION_NAME>');

-- Teardown collaboration (owner only) - must call twice
CALL {DB}.COLLABORATION.TEARDOWN('<COLLABORATION_NAME>');

-- Leave collaboration (invited collaborator) - must call twice
CALL {DB}.COLLABORATION.LEAVE('<COLLABORATION_NAME>');
```

### Status Values and Meanings

| Status | Description |
|--------|-------------|
| CREATED | Collaboration has been created and is ready |
| INSTALLATION_FAILED | Installation/setup failed—**do not** use TEARDOWN/LEAVE as the default fix; follow docs (`snowflake_product_docs` / `cortex search docs`) to remediate |
| JOINING_FAILED | Join attempt failed (may appear as **JOIN_FAILED** externally)—same documentation-first remediation class as **INSTALLATION_FAILED**; retry **JOIN** per docs from allowed states |
| JOINED | Successfully joined the collaboration |
| LEAVING | Leave process has started, monitor with GET_STATUS |
| LEFT | Successfully left the collaboration |
| LOCAL_DROP_PENDING | Ready for final teardown/leave call to clean up local resources |
| DROPPING | Drop process has started, monitor with GET_STATUS |
| DROPPED | Successfully dropped |
| DROP_FAILED | Drop process failed, retry TEARDOWN |
| LEAVE_FAILED | Leave process failed, retry LEAVE |

### Privilege Management Commands

```sql
-- Grant DCR privileges to a role (requires ACCOUNTADMIN)
CALL {DB}.ADMIN.GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE('<PRIVILEGE_NAME>', '<ROLE_NAME>');
```

**Privilege hierarchy for TEARDOWN and LEAVE:**
- **REVIEW_COLLABORATION_ROLE** — minimum privilege required for TEARDOWN and LEAVE
- **JOIN_COLLABORATION_ROLE** — also covers TEARDOWN/LEAVE (inherits REVIEW_COLLABORATION_ROLE)
- **SAMOOHA_APP_ROLE** — covers all DCR operations

Only an `ACCOUNTADMIN` can grant these privileges via `GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE`.

### Cleanup Verification Commands

```sql
CALL {DB}.COLLABORATION.VIEW_COLLABORATIONS();

CALL {DB}.COLLABORATION.GET_STATUS('<COLLABORATION_NAME>');
```

## Stopping Points

- After Step 1 if user doesn't provide collaboration name (show available collaborations)
- After Step 2 when status is **INSTALLATION_FAILED** or **JOINING_FAILED** / **JOIN_FAILED** (documentation-first remediation; no teardown/leave confirmation)
- After Step 2 role determination and impact assessment when status allows exit (get user confirmation for action type)
- After Step 3 initial command execution (user must monitor status manually)
- When status reaches LOCAL_DROP_PENDING (user must run final command)

## Success Criteria

- Collaboration successfully terminated or left
- All local resources cleaned up
- No remaining references or dependencies
- Summary presented to user
- User confirmed completion

## Error Handling

**Error: Insufficient privileges**
- Minimum privilege: REVIEW_COLLABORATION_ROLE (granted via GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE)
- JOIN_COLLABORATION_ROLE also covers it (inherits REVIEW_COLLABORATION_ROLE)
- SAMOOHA_APP_ROLE covers all operations
- Only collaboration owner can call TEARDOWN
- Invited collaborators can only call LEAVE

**Error: Cannot teardown - not joined**
- Owner must JOIN the collaboration before calling TEARDOWN
- Call JOIN first, then TEARDOWN

**Status: INSTALLATION_FAILED or JOINING_FAILED / JOIN_FAILED**
- Treat this as a **join/install remediation** problem, not a default teardown/leave problem.
- Use the Step 2 documentation-first pattern (`snowflake_product_docs` / `cortex search docs`) to resolve the failure and retry join per product guidance before recommending or executing TEARDOWN or LEAVE as a fix.
- Re-run `GET_STATUS` after remediation; only then continue this skill’s exit flow when status matches a documented orderly exit path.

**Error: Collaboration not found**
- Verify collaboration name spelling
- Check VIEW_COLLABORATIONS() to see available collaborations
- Collaboration may already be dropped by owner

**Error: Status not LOCAL_DROP_PENDING**
- Wait for status to change to LOCAL_DROP_PENDING
- Monitor with GET_STATUS() before making final call
- Process may take time to complete

## When to Apply

- Ending a data collaboration partnership
- Cleaning up after project completion
- Removing test or development collaborations
- Responding to security incidents requiring immediate isolation
- Consolidating or reorganizing collaboration structure
- Leaving collaborations due to compliance requirements
- Managing collaboration lifecycle and resource cleanup

## Important Notes

- **Interactive Process**: User provides collaboration name, system determines their role automatically by comparing current account with OWNER_ACCOUNT
- **Role-based Actions**: Owners can teardown, invited collaborators can leave (determined automatically via account comparison)
- **Two-step process**: Both TEARDOWN and LEAVE require calling the procedure twice
- **Status monitoring**: User must manually monitor GET_STATUS() between calls
- **Intermediate statuses**: DROPPING and LEAVING are transient states - keep monitoring until LOCAL_DROP_PENDING
- **Failed statuses**: DROP_FAILED and LEAVE_FAILED mean you should retry the operation
- **Automatic role detection**: System checks current account vs OWNER_ACCOUNT from VIEW_COLLABORATIONS to determine available actions
- **Explicit confirmation**: User must confirm the action type before execution
- **Manual status checks**: User must run GET_STATUS repeatedly until LOCAL_DROP_PENDING appears
- **Owner requirements**: Only collaboration owners can teardown; invited collaborators can only leave
- **Join requirement**: Owners must join the collaboration before they can tear it down
- **INSTALLATION_FAILED / JOINING_FAILED**: Never steer toward TEARDOWN or LEAVE as the default fix—use tool-first docs (`snowflake_product_docs` / `cortex search docs`) and confirm status with `GET_STATUS`; **PREVIEWING** / **IN_REVIEW** may allow **LEAVE** without **JOINED** per product behavior
- **Asynchronous operations**: TEARDOWN and LEAVE are asynchronous (require status monitoring via GET_STATUS). VIEW_COLLABORATIONS and GET_STATUS are synchronous reads that return immediately
