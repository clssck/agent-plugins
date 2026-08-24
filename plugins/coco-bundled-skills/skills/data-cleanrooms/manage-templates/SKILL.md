---
name: manage-templates
parent_skill: data-cleanrooms
description: "Manage templates in existing DCR collaborations: add, remove, view templates, approve/reject template update requests, and toggle auto-approval. Triggers: add template to collaboration, add template, share template, remove template, view templates, manage templates in collaboration, approve template request, reject template request, view template requests, view update requests, enable template auto approval, disable template auto approval, manage update requests."
---

# Manage Templates

Manage templates in existing DCR collaborations: add and remove templates, view and approve/reject template update requests, and toggle auto-approval.

## When to Use

**IMPORTANT:** Always use CALL procedures, not SELECT FROM. Never query or modify DCR internal tables directly. Only use procedures documented in this skill.

- User wants to add a template to an existing collaboration
- User wants to remove a template from a collaboration
- User wants to view templates in a collaboration or the account's registry
- User wants to view update requests in a collaboration (pending, approved, rejected, completed, or failed)
- User wants to approve or reject a template update request
- User wants to enable or disable automatic template approval

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Template Request** | Adding a template is request-based: the sender submits a request, and all affected collaborators must approve before it takes effect |
| **Sender Auto-Approval** | If the sender is affected by the request, they automatically approve it |
| **Auto-Approval** | When enabled, all future template update requests from other collaborators are approved automatically. Existing pending requests are not affected |
| **Template ID** | The ID returned when registering a template via `REGISTRY.REGISTER_TEMPLATE`. Format: `<name>_<version>` |
| **share_with** | Array of analysis runner aliases that should be able to use the template |
| **remove_for** | Array of analysis runner aliases that should no longer see or use the template |
| **Request Statuses** | PENDING, AWAITING_PARTNER_APPROVAL, APPROVED, COMPLETED, REJECTED, FAILED |

## Prerequisites

- The collaboration must already exist and be joined by the current account
- The template must be registered in the account's registry (via `REGISTRY.REGISTER_TEMPLATE`)
- If the template is in a custom registry, the user must have READ privilege on that registry

---

## Workflow A: Add Template to Collaboration

### Step 0: Verify Collaboration Exists and Is Joined

```sql
CALL {DB}.COLLABORATION.VIEW_COLLABORATIONS();
```

Confirm the target collaboration appears in the result and its status is `JOINED`. If not found or not joined, inform the user before proceeding.

### Step 1: Identify Collaboration and View Current State

Ask the user for the collaboration name. Then view what templates are already in the collaboration and what templates are available in the registry:

```sql
CALL {DB}.COLLABORATION.VIEW_TEMPLATES('<collaboration_name>');
CALL {DB}.REGISTRY.VIEW_REGISTERED_TEMPLATES();
```

Present both results to the user so they can see what is currently in the collaboration and what is available to add.

### Step 2: Gather Template Details

Ask:
- **Template ID**: Which registered template to add? (from the registry results)
- **Share with**: Which analysis runner aliases should be able to use this template? (must be valid analysis runner aliases in the collaboration)

### Step 3: Confirm with User

**MANDATORY STOPPING POINT**: Display the proposed `ADD_TEMPLATE_REQUEST` call to the user.

Ask: "Does this look correct? (Yes/No/Modify)"

NEVER proceed to Step 4 without explicit user approval.

### Step 4: Submit Request

```sql
CALL {DB}.COLLABORATION.ADD_TEMPLATE_REQUEST(
  '<collaboration_name>',
  '<template_id>',
  ['<runner_alias_1>', '<runner_alias_2>']
);
```

**Note on share_with**: To add additional template sharers later, call `ADD_TEMPLATE_REQUEST` again with the new aliases. Each call adds the users listed in `share_with`.

### Step 5: Monitor Request Status

After submitting, check the request status with `VIEW_UPDATE_REQUESTS` (see Workflow C). Key statuses: PENDING, AWAITING_PARTNER_APPROVAL, APPROVED, COMPLETED, REJECTED, FAILED.

---

## Workflow B: Remove Template from Collaboration

Only the collaborator that registered the template can remove it. No approval is needed from other collaborators.

### Step 1: Verify Ownership and Gather Information

First, view the templates in the collaboration and check the `SHARED_BY` column to confirm the current account registered the template:

```sql
CALL {DB}.COLLABORATION.VIEW_TEMPLATES('<collaboration_name>');
```

If the current account is not listed in `SHARED_BY` for the target template, inform the user that only the registerer can remove it.

Ask:
- **Template ID**: Which template to remove?
- **Remove for**: Which analysis runner aliases should no longer see or use this template?

### Step 2: Confirm with User

**MANDATORY STOPPING POINT**: Display the proposed `REMOVE_TEMPLATE` call.

Ask: "This will remove the template for the specified runners. Proceed? (Yes/No/Modify)"

NEVER proceed without explicit user approval.

### Step 3: Execute Removal

```sql
CALL {DB}.COLLABORATION.REMOVE_TEMPLATE(
  '<collaboration_name>',
  '<template_id>',
  ['<runner_alias_1>']
);
```

To verify removal, view the collaboration specification or call `VIEW_TEMPLATES`.

---

## Workflow C: View and Manage Update Requests

### Step 0: Verify Collaboration Exists and Is Joined

```sql
CALL {DB}.COLLABORATION.VIEW_COLLABORATIONS();
```

Confirm the target collaboration appears in the result and its status is `JOINED`. If not found or not joined, inform the user before proceeding.

### View Update Requests

```sql
CALL {DB}.COLLABORATION.VIEW_UPDATE_REQUESTS('<collaboration_name>');
```

The result includes: ID, TYPE, STATUS, APPROVAL_LOG, DETAILS, SPEC, UPDATED_ON.

Request statuses:

| Status | Meaning |
|--------|---------|
| `PENDING` | Awaiting your approval or rejection |
| `AWAITING_PARTNER_APPROVAL` | You approved, but other collaborators still need to approve |
| `APPROVED` | All required approvers have approved |
| `COMPLETED` | Changes applied to the collaboration |
| `REJECTED` | Someone rejected the request |
| `FAILED` | The update action failed (see DETAILS column) |

### Approve a Request

**MANDATORY STOPPING POINT**: Display the proposed `APPROVE_UPDATE_REQUEST` call to the user.

Ask: "Approve this request? (Yes/No)"

NEVER proceed without explicit user approval.

```sql
CALL {DB}.COLLABORATION.APPROVE_UPDATE_REQUEST(
  '<collaboration_name>',
  '<request_id>'
);
```

All affected collaborators must approve before the change is applied. The requestor (the person who submitted the original ADD_TEMPLATE_REQUEST) can also use this to approve a request they previously rejected, as long as the request hasn't reached a terminal state (COMPLETED or FAILED). For all other collaborators, approval is irreversible.

### Reject a Request

**MANDATORY STOPPING POINT**: Display the proposed `REJECT_UPDATE_REQUEST` call to the user.

Ask: "Reject this request with the given reason? (Yes/No)"

NEVER proceed without explicit user approval.

```sql
CALL {DB}.COLLABORATION.REJECT_UPDATE_REQUEST(
  '<collaboration_name>',
  '<request_id>',
  '<reason>'
);
```

A single rejection prevents the change from being applied. The reason argument is required (but can be an empty string). The requestor can also use this to reject a request they previously approved, as long as it hasn't been fully approved by all parties or reached a terminal state. For all other collaborators, rejection is irreversible.

---

## Workflow D: Toggle Template Auto-Approval

Auto-approval causes all future template update requests from other collaborators to be approved automatically. Existing pending requests are not affected.

### Enable Auto-Approval

**MANDATORY STOPPING POINT**: Display the proposed call. Warn that enabling auto-approval means all future template requests will be approved without manual review.

Ask: "Enable auto-approval for all future template requests? (Yes/No)"

NEVER proceed without explicit user approval.

```sql
CALL {DB}.COLLABORATION.ENABLE_TEMPLATE_AUTO_APPROVAL('<collaboration_name>');
```

### Disable Auto-Approval

**MANDATORY STOPPING POINT**: Display the proposed call. Confirm the user wants to revert to manual approval.

Ask: "Disable auto-approval? Future requests will require manual approval. (Yes/No)"

NEVER proceed without explicit user approval.

```sql
CALL {DB}.COLLABORATION.DISABLE_TEMPLATE_AUTO_APPROVAL('<collaboration_name>');
```

After disabling, all future requests must be approved manually via `APPROVE_UPDATE_REQUEST`.

---

## Required Privileges

If operations fail with "Insufficient privileges", see the parent data-cleanrooms SKILL.md "Required Privileges" section for how to grant privileges using `{DB}.ADMIN.GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE` or `{DB}.ADMIN.GRANT_PRIVILEGE_ON_OBJECT_TO_ROLE`.

| Procedure | Privilege | Scope |
|-----------|-----------|-------|
| `ADD_TEMPLATE_REQUEST` | `ADD TEMPLATE REQUEST` | Collaboration |
| `REMOVE_TEMPLATE` | `REMOVE TEMPLATE` | Collaboration |
| `VIEW_TEMPLATES` | `VIEW TEMPLATES` | Collaboration |
| `VIEW_REGISTERED_TEMPLATES` | `VIEW REGISTERED TEMPLATES` | Account |
| `VIEW_UPDATE_REQUESTS` | `VIEW UPDATE REQUESTS` | Collaboration |
| `APPROVE_UPDATE_REQUEST` | `MANAGE UPDATE REQUEST` | Collaboration |
| `REJECT_UPDATE_REQUEST` | `MANAGE UPDATE REQUEST` | Collaboration |
| `ENABLE_TEMPLATE_AUTO_APPROVAL` | `MANAGE TEMPLATE AUTO APPROVAL` | Collaboration |
| `DISABLE_TEMPLATE_AUTO_APPROVAL` | `MANAGE TEMPLATE AUTO APPROVAL` | Collaboration |

**Example: Grant ADD TEMPLATE REQUEST privilege on a collaboration**

```sql
USE ROLE ACCOUNTADMIN;
CALL {DB}.ADMIN.GRANT_PRIVILEGE_ON_OBJECT_TO_ROLE(
    'ADD TEMPLATE REQUEST',
    'COLLABORATION',
    '<collaboration_name>',
    '<user_role>'
);
```

**Example: Grant VIEW REGISTERED TEMPLATES privilege (account-level)**

```sql
USE ROLE ACCOUNTADMIN;
CALL {DB}.ADMIN.GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE(
    'VIEW REGISTERED TEMPLATES',
    '<user_role>'
);
```

**Example: Grant MANAGE UPDATE REQUEST privilege on a collaboration**

```sql
USE ROLE ACCOUNTADMIN;
CALL {DB}.ADMIN.GRANT_PRIVILEGE_ON_OBJECT_TO_ROLE(
    'MANAGE UPDATE REQUEST',
    'COLLABORATION',
    '<collaboration_name>',
    '<user_role>'
);
```

**Example: Grant MANAGE TEMPLATE AUTO APPROVAL privilege on a collaboration**

```sql
USE ROLE ACCOUNTADMIN;
CALL {DB}.ADMIN.GRANT_PRIVILEGE_ON_OBJECT_TO_ROLE(
    'MANAGE TEMPLATE AUTO APPROVAL',
    'COLLABORATION',
    '<collaboration_name>',
    '<user_role>'
);
```

---

## Stopping Points

- Before ADD_TEMPLATE_REQUEST: Confirm template details and share_with list
- Before REMOVE_TEMPLATE: Confirm removal targets
- Before APPROVE_UPDATE_REQUEST: Confirm which request to approve (irreversible for non-requestors)
- Before REJECT_UPDATE_REQUEST: Confirm which request to reject and get reason (irreversible for non-requestors)
- Before ENABLE_TEMPLATE_AUTO_APPROVAL: Confirm enabling auto-approval
- Before DISABLE_TEMPLATE_AUTO_APPROVAL: Confirm disabling auto-approval

**Resume rule:** Upon user approval, proceed directly without re-asking.

## Output

| Operation | Output |
|-----------|--------|
| Add Template | Proposed ADD_TEMPLATE_REQUEST call -> user approval -> submission confirmation -> request status |
| Remove Template | Proposed REMOVE_TEMPLATE call -> user approval -> removal confirmation |
| View Requests | List of update requests with ID, status, type, approval log |
| Approve | Approval confirmation |
| Reject | Rejection confirmation |
| Auto-Approval | Enable/disable confirmation |
