---
name: manage-data-offerings
parent_skill: data-cleanrooms
description: "Link and unlink data offerings in DCR collaborations - make registered data available to analysis runners or revoke access, or link/unlink local data offerings for Standard edition accounts. Triggers: link_data_offering, unlink_data_offering, link_local_data_offering, unlink_local_data_offering"
---

# Link and Unlink Data Offerings

Link registered data offerings to make them available to analysis runners in a collaboration, or unlink to revoke access. Also supports local data offerings for Standard edition accounts.

## When to Use

- User wants to share their data in a collaboration. If the data is not registered as a data offering, reroute to register data offering to register it first.
- User wants to make a registered data offering available to specific analysis runners in a collaboration
- User wants to revoke access to a data offering from analysis runners in a collaboration
- User says "link data offering", "unlink data offering", "share data with partner", "revoke data access"
- User wants to link a data offering **locally** (without sharing it with other collaborators)
- User is on **Snowflake Standard edition** and needs to use their own data in a collaboration
- User says "link local data offering", "unlink local data offering", "add my data locally", "use my own data in the collaboration"

## Workflow Routing

**Default: Use Workflow A (`LINK_DATA_OFFERING`) unless the user explicitly requests local linking or the account is Standard edition.**

| Condition | Workflow |
|-----------|----------|
| User wants to share data with **other collaborators** (analysis runners) | → **Workflow A** (Link) |
| User wants to share/use their **own data** in a collaboration (self-share), without explicitly requesting local linking | → **Workflow A** (Link) — include the user's own collaborator alias in the `share_with` array |
| User wants to revoke access from **other collaborators** | → **Workflow B** (Unlink) |
| User explicitly asks to link/add data offering **locally** | → **Workflow C** (Link Local) |
| User is on a **Snowflake Standard edition** account | → **Workflow C** (Link Local) |
| User explicitly asks to unlink a **local** data offering | → **Workflow D** (Unlink Local) |

**Self-share note:** When a user wants to use their own data in a collaboration (e.g., "I want to share my data with myself", "add my data to the collaboration") but has **not** explicitly asked for local linking, use **Workflow A** (`LINK_DATA_OFFERING`) on Enterprise/Business Critical accounts. The user's own collaborator alias goes into the `share_with` array. Only fall back to **Workflow C** (`LINK_LOCAL_DATA_OFFERING`) if the account is Standard edition or the user explicitly requests local linking.

## Prerequisites

1. The collaboration must exist and be JOINED (check via `VIEW_COLLABORATIONS` / `GET_STATUS`)
2. The data offering must already be registered (check via `VIEW_REGISTERED_DATA_OFFERINGS`)
3. The user must be a **data provider** for the collaboration
4. The user must have `REFERENCE_USAGE` privilege on the shared data

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Link** | Makes a registered data offering available to specified analysis runners in a collaboration |
| **Unlink** | Revokes access to a previously linked data offering from specified analysis runners |
| **Data Offering ID** | Unique identifier generated at registration time (visible in `VIEW_REGISTERED_DATA_OFFERINGS` and `VIEW_DATA_OFFERINGS`) |
| **Analysis Runner** | A collaborator alias that has the analysis runner role in the collaboration |
| **Update Request** | An async tracking record created by LINK/UNLINK operations. Data offering changes are auto-approved, so use `VIEW_UPDATE_REQUESTS` to check status (`COMPLETED`, `FAILED`) |

## Important Behavior

- **LINK is additive**: calling LINK again with new runners appends to existing sharers (does not replace)
- **LINK is atomic**: if any one collaborator in the `share_with` array fails, the entire operation fails for all
- **LINK is asynchronous**: after calling LINK, runners should call `VIEW_UPDATE_REQUESTS` to confirm if the request COMPLETED or FAILED. Runners can also call `VIEW_DATA_OFFERINGS` to confirm.
- **UNLINK is asynchronous**: after calling UNLINK, runners should call `VIEW_UPDATE_REQUESTS` to confirm if the removal request COMPLETED or FAILED. Runners can also call `VIEW_DATA_OFFERINGS` to confirm.

## Workflow A: Link Data Offering

### Step 1: Gather Information

Collect the following from the user or discover via procedures:

1. **Collaboration name** — which collaboration to link the offering in
2. **Data offering ID** — which registered offering to link
3. **Analysis runners** — which collaborator aliases to share with

### Step 2: Discover Collaboration and Offerings

If the user hasn't provided all details, help them discover:

```sql
CALL {DB}.COLLABORATION.VIEW_COLLABORATIONS();
```

```sql
CALL {DB}.COLLABORATION.VIEW_DATA_OFFERINGS('<collaboration_name>');
```

```sql
CALL {DB}.REGISTRY.VIEW_REGISTERED_DATA_OFFERINGS();
```

Use `VIEW_DATA_OFFERINGS` to see which offerings are already linked and to whom (`SHARE_WITH` column).
Use `VIEW_REGISTERED_DATA_OFFERINGS` to find the data offering ID.
If the data offering is already linked to the analysis runner, let the user know that the data offering is already shared to the requested analysis runner.

### Step 3: Confirm with User

**MANDATORY STOPPING POINT**: Present the link details to the user.

Display:
- Collaboration name
- Data offering ID
- Analysis runners to share with

Ask: "Do you want to share this data offering to these analysis runners? (Yes/No)"

NEVER proceed to Step 4 without explicit user confirmation.

### Step 4: Link Data Offering

Disable secondary roles before LINK_DATA_OFFERING and restore after:

```sql
USE SECONDARY ROLES NONE;

CALL {DB}.COLLABORATION.LINK_DATA_OFFERING(
  '<collaboration_name>',
  '<data_offering_id>',
  ['<runner_alias_1>', '<runner_alias_2>']
);

USE SECONDARY ROLES ALL;
```

**If LINK_DATA_OFFERING is canceled unexpectedly**: Inform the user: "The link operation was canceled. Please run `USE SECONDARY ROLES ALL` (or start a new session) to restore your secondary roles."

**If LINK_DATA_OFFERING fails**, inspect the error message and follow the appropriate recovery path:

**Error 1 — `Unsupported feature 'ROW ACCESS POLICY'`**

This means the account is on **Snowflake Standard edition**, which does not support row access policies required by `LINK_DATA_OFFERING`. Confirm the edition:

```sql
SELECT SYSTEM$BOOTSTRAP_DATA_REQUEST('ACCOUNT');
```

If the returned JSON has `"serviceLevelName":"STANDARD"`, switch to **Workflow C** (`LINK_LOCAL_DATA_OFFERING`). Explain to the user:
- Standard edition accounts must use `LINK_LOCAL_DATA_OFFERING` instead
- Locally linked offerings are **not visible** to other collaborators and are **not shared**
- Template data sharing policies are **not enforced** on locally linked offerings

**Error 2 — `ProviderNotServingAnalysisRunner: A data provider can link data offerings only for their analysis runners`**

This means the current account is not listed as a data provider for the target analysis runner in the collaboration spec. This can happen on **any edition** (Standard or Enterprise). Suggest using **Workflow C** (`LINK_LOCAL_DATA_OFFERING`) to link the offering locally instead. Explain to the user:
- Locally linked offerings bypass the data provider requirement
- Locally linked offerings are **not visible** to other collaborators and are **not shared**
- Template data sharing policies are **not enforced** on locally linked offerings

### Step 5: Check Update Request Status

Since LINK is asynchronous, check the status of the operation:

```sql
CALL {DB}.COLLABORATION.VIEW_UPDATE_REQUESTS('<collaboration_name>');
```

Look for your request and check the `STATUS` column:

| Status | Meaning | Action |
|--------|---------|--------|
| `APPROVED` | Change approved, being applied | Wait |
| `COMPLETED` | Link applied successfully | Proceed to verify |
| `FAILED` | Operation failed | Check `DETAILS` column for error |

**Note:** It can take a few seconds for an update request to appear after calling LINK.

### Step 6: Verify Data Availability

Once the update request status is `COMPLETED`:

```sql
CALL {DB}.COLLABORATION.VIEW_DATA_OFFERINGS('<collaboration_name>');
```

Check the `SHARE_WITH` column to confirm the offering is now shared with the specified runners.

---

## Workflow B: Unlink Data Offering

### Step 1: Gather Information

Collect the following from the user or discover via procedures:

1. **Collaboration name** — which collaboration to unlink the offering from
2. **Data offering ID** — which offering to unlink
3. **Analysis runners** — which collaborator aliases to revoke access for

### Step 2: Discover Current Links

Help the user see what is currently linked:

```sql
CALL {DB}.COLLABORATION.VIEW_COLLABORATIONS();
```

```sql
CALL {DB}.COLLABORATION.VIEW_DATA_OFFERINGS('<collaboration_name>');
```

Use `VIEW_DATA_OFFERINGS` to see the `SHARE_WITH` column — this shows which runners currently have access. All runners specified in the unlink call must currently have access.

**⚠️ IMPORTANT**: Check the `SHARED_BY` column for the target offering. Only the data provider who originally linked the offering (the `SHARED_BY` party) can unlink it. If `SHARED_BY` is a different collaborator (not the current user's alias), **stop immediately** and inform the user:

> "You cannot unlink `<offering_id>` because it was shared by `<SHARED_BY>`, not by your account. Only the data provider who linked this offering can unlink it. Please contact `<SHARED_BY>` to revoke access."

Do **not** attempt `UNLINK_DATA_OFFERING` in this case — it will fail, and retrying will not help.

### Step 3: Confirm with User

**MANDATORY STOPPING POINT**: Present the unlink details to the user.

Display:
- Collaboration name
- Data offering ID
- Analysis runners to revoke access from

Ask: "Do you want to unlink this data offering from these analysis runners? This will revoke their access. (Yes/No)"

NEVER proceed to Step 4 without explicit user confirmation.

### Step 4: Unlink Data Offering

```sql
CALL {DB}.COLLABORATION.UNLINK_DATA_OFFERING(
  '<collaboration_name>',
  '<data_offering_id>',
  ['<runner_alias_1>', '<runner_alias_2>']
);
```

### Step 5: Check Update Request Status

Since UNLINK is asynchronous, check the status of the operation:

```sql
CALL {DB}.COLLABORATION.VIEW_UPDATE_REQUESTS('<collaboration_name>');
```

Look for your request and check the `STATUS` column (see status table in Workflow A, Step 5).

### Step 6: Verify Data Removal

Once the update request status is `COMPLETED`:

```sql
CALL {DB}.COLLABORATION.VIEW_DATA_OFFERINGS('<collaboration_name>');
```

Confirm the `SHARE_WITH` column no longer includes the revoked runners.

---

## Workflow C: Link Local Data Offering

Use this workflow when:
1. The user explicitly asks to link or add a data offering **locally** (without sharing it with other collaborators)
2. The account is a **Snowflake Standard edition** account, which has restrictions on data sharing policy enforcement

Local data offerings are **not visible** to other collaborators and are **not shared** with anyone — they are only available to your account. Template policies are **not enforced** on local data offerings. Tables linked locally propagate the `my_table` array in the template.

When explaining local data offerings to the user, always mention:
1. The offering will **not be visible** to other collaborators and is **not shared** — it is only available to your current account
2. Template policies are **not enforced** on locally linked offerings

### Step 1: Gather Information

Collect the following from the user or discover via procedures:

1. **Collaboration name** — which collaboration to link the local offering in
2. **Data offering ID** — which registered offering to link locally

### Step 2: Discover Collaboration and Offerings

If the user hasn't provided all details, help them discover:

```sql
CALL {DB}.COLLABORATION.VIEW_COLLABORATIONS();
```

```sql
CALL {DB}.REGISTRY.VIEW_REGISTERED_DATA_OFFERINGS();
```

```sql
CALL {DB}.COLLABORATION.VIEW_DATA_OFFERINGS('<collaboration_name>');
```

Use `VIEW_DATA_OFFERINGS` to check if the offering is already linked. Local offerings show `SHARE_WITH = 'LOCAL'`.

### Step 3: Confirm with User

**MANDATORY STOPPING POINT**: Present the local link details to the user.

Display:
- Collaboration name
- Data offering ID
- Note: "This will link the data offering locally — it will **not be visible** to other collaborators and will **not be shared** with other parties. Template policies will NOT be enforced."

Ask: "Do you want to link this data offering locally? (Yes/No)"

NEVER proceed to Step 4 without explicit user confirmation.

### Step 4: Link Local Data Offering

```sql
CALL {DB}.COLLABORATION.LINK_LOCAL_DATA_OFFERING(
  '<collaboration_name>',
  '<data_offering_id>'
);
```

**Note:** Unlike `LINK_DATA_OFFERING`, this procedure takes only 2 arguments (no `share_with` array) because local offerings are **not shared** with other collaborators — they are **not visible** to anyone else.

### Step 5: Verify

```sql
CALL {DB}.COLLABORATION.VIEW_DATA_OFFERINGS('<collaboration_name>');
```

Confirm the offering appears with `SHARE_WITH = 'LOCAL'`.

---

## Workflow D: Unlink Local Data Offering

Use this workflow to remove a locally linked data offering from a collaboration. After unlinking, the data offering will no longer be available for analyses in this collaboration.

### Step 1: Gather Information

Collect the following from the user or discover via procedures:

1. **Collaboration name** — which collaboration to unlink the local offering from
2. **Data offering ID** — which local offering to unlink

### Step 2: Discover Current Local Links

Help the user see what is currently linked locally:

```sql
CALL {DB}.COLLABORATION.VIEW_COLLABORATIONS();
```

```sql
CALL {DB}.COLLABORATION.VIEW_DATA_OFFERINGS('<collaboration_name>');
```

Look for offerings where `SHARE_WITH = 'LOCAL'` — these are the locally linked offerings that can be unlinked with this workflow.

### Step 3: Confirm with User

**MANDATORY STOPPING POINT**: Present the unlink details to the user.

Display:
- Collaboration name
- Data offering ID
- Note: "This will remove the local data offering from the collaboration. It will no longer be available for analyses."

Ask: "Do you want to unlink this local data offering? (Yes/No)"

NEVER proceed to Step 4 without explicit user confirmation.

### Step 4: Unlink Local Data Offering

```sql
CALL {DB}.COLLABORATION.UNLINK_LOCAL_DATA_OFFERING(
  '<collaboration_name>',
  '<data_offering_id>'
);
```

**Note:** Unlike `UNLINK_DATA_OFFERING`, this procedure takes only 2 arguments (no `share_with` array) because local offerings are not shared with other collaborators.

### Step 5: Verify

```sql
CALL {DB}.COLLABORATION.VIEW_DATA_OFFERINGS('<collaboration_name>');
```

Confirm the local offering no longer appears.

---

## Procedures Reference

| Procedure | Purpose | Parameters |
|-----------|---------|------------|
| `COLLABORATION.VIEW_COLLABORATIONS()` | List all collaborations | None |
| `COLLABORATION.VIEW_DATA_OFFERINGS(name)` | List data offerings and their share status | Collaboration name |
| `REGISTRY.VIEW_REGISTERED_DATA_OFFERINGS()` | List all registered data offerings | None |
| `COLLABORATION.LINK_DATA_OFFERING(name, id, runners)` | Link offering to analysis runners | Collaboration name, data offering ID, array of runner aliases |
| `COLLABORATION.UNLINK_DATA_OFFERING(name, id, runners)` | Unlink offering from analysis runners | Collaboration name, data offering ID, array of runner aliases |
| `COLLABORATION.LINK_LOCAL_DATA_OFFERING(name, id)` | Link offering locally (not shared with others) | Collaboration name, data offering ID |
| `COLLABORATION.UNLINK_LOCAL_DATA_OFFERING(name, id)` | Unlink a local offering | Collaboration name, data offering ID |
| `COLLABORATION.VIEW_UPDATE_REQUESTS(name)` | Check status of async link/unlink operations | Collaboration name |

## Required Privileges

If operations fail with "Insufficient privileges", see the parent data-cleanrooms SKILL.md "Required Privileges" section for how to grant privileges using `{DB}.ADMIN.GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE` or `{DB}.ADMIN.GRANT_PRIVILEGE_ON_OBJECT_TO_ROLE`.

| Procedure | Privilege | Scope |
|-----------|-----------|-------|
| `LINK_DATA_OFFERING(name, id, runners)` | `JOIN COLLABORATION` or `CREATE COLLABORATION` | Account |
| `UNLINK_DATA_OFFERING(name, id, runners)` | `JOIN COLLABORATION` or `CREATE COLLABORATION` | Account |
| `LINK_LOCAL_DATA_OFFERING(name, id)` | `UPDATE` on collaboration, OR `JOIN COLLABORATION` / `CREATE COLLABORATION` on account | Collaboration or Account |
| `UNLINK_LOCAL_DATA_OFFERING(name, id)` | `UPDATE` on collaboration, OR `JOIN COLLABORATION` / `CREATE COLLABORATION` on account | Collaboration or Account |
| `VIEW_DATA_OFFERINGS(name)` | `VIEW DATA OFFERINGS` | Collaboration |
| `VIEW_REGISTERED_DATA_OFFERINGS()` | `VIEW REGISTERED DATA OFFERINGS` | Account |
| `VIEW_UPDATE_REQUESTS(name)` | `UPDATE` or `READ` | Collaboration |

If the data offering is in a custom registry, also requires:
- `READ` on the registry object

**Example: Grant UPDATE privilege on a collaboration**

```sql
USE ROLE ACCOUNTADMIN;

CALL {DB}.ADMIN.GRANT_PRIVILEGE_ON_OBJECT_TO_ROLE(
    'UPDATE',
    'COLLABORATION',
    '<collaboration_name>',
    '<user_role>'
);
```

---

## Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| "Secondary roles must be disabled" | `LINK_DATA_OFFERING` requires secondary roles off | Run `USE SECONDARY ROLES NONE` before the LINK_DATA_OFFERING call and `USE SECONDARY ROLES ALL` after (only applies to Workflow A) |
| "Insufficient privileges" | Missing DCR privilege | See Required Privileges above |
| "Data offering not found" | Wrong offering ID or not registered | Check `VIEW_REGISTERED_DATA_OFFERINGS()` |
| "Collaborator is not an analysis runner" | Runner alias not assigned analysis runner role | Check collaboration spec for runner assignments |
| "Collaborator does not have access" (unlink) | Runner alias not currently linked | Check `VIEW_DATA_OFFERINGS()` for current `SHARE_WITH` |
| Cannot unlink — not the data provider | `SHARED_BY` column shows a different collaborator | Tell the user only the original data provider (`SHARED_BY`) can unlink this offering. Do not retry. |
| "Unsupported feature 'ROW ACCESS POLICY'" in `LINK_DATA_OFFERING` | Account is Snowflake Standard edition | Confirm via `SELECT SYSTEM$BOOTSTRAP_DATA_REQUEST('ACCOUNT')` — if `serviceLevelName` is `STANDARD`, switch to Workflow C (`LINK_LOCAL_DATA_OFFERING`) |
| "ProviderNotServingAnalysisRunner" in `LINK_DATA_OFFERING` | Current account is not a data provider for the target analysis runner | Switch to Workflow C (`LINK_LOCAL_DATA_OFFERING`) to link locally — works on any edition |

---

## Stopping Points

- Before Step 4 in Workflow A (LINK): Confirm data offering, collaboration, and runners with user
- Before Step 4 in Workflow B (UNLINK): Confirm revocation details with user
- Before Step 4 in Workflow C (LINK LOCAL): Confirm local link details with user
- Before Step 4 in Workflow D (UNLINK LOCAL): Confirm local unlink details with user

**Resume rule:** Upon user approval, proceed directly without re-asking.

## Output

| Operation | Output |
|-----------|--------|
| Link | Success confirmation + update request status via VIEW_UPDATE_REQUESTS + verification via VIEW_DATA_OFFERINGS |
| Unlink | Success confirmation + update request status via VIEW_UPDATE_REQUESTS + verification via VIEW_DATA_OFFERINGS |
