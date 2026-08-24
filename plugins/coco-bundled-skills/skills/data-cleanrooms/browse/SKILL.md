---
name: browse
parent_skill: data-cleanrooms
description: "Browse Clean Room Environment - explore collaborations, data offerings, and templates. Triggers: view collaborations, show clean rooms, view templates, registered offerings."
---

# Browse Clean Room Environment

Explore and view collaborations, data offerings, and templates in your DCR environment.

## When to Use

- User wants to see available collaborations
- User wants to check a collaboration's status
- User wants to view data offerings for a collaboration
- User wants to view templates for a collaboration
- User wants to see registered templates, data offerings, or code specs at account level
- User wants to see all custom registries in the account
- User wants to see code specs attached to a specific collaboration
- User wants to see activity or audit history for a collaboration

**IMPORTANT:** Always use CALL procedures, not SELECT FROM. Never query or modify DCR internal tables directly. Only use procedures documented in this skill.

## Workflow

1. Determine which browse operation the user needs (collaborations, status, offerings, templates, or registered items)
2. Execute the appropriate procedure from the sections below
3. Present results to user in a clear format

## Collaboration-Level Operations (COLLABORATION Schema)

### A) View Collaborations
- **When**: User asks to see available collaborations
- **Call**: `{DB}.COLLABORATION.VIEW_COLLABORATIONS()`
- **Params**: None
- **Display**: collaboration name, ID, owner, and status

```sql
CALL {DB}.COLLABORATION.VIEW_COLLABORATIONS();
```

### B) Get Collaboration Status
- **When**: User asks to check the status of a specific collaboration
- **Call**: `{DB}.COLLABORATION.GET_STATUS(collaboration_name)`
- **Params**: collaboration_name (required, string)
- **Display**: detailed status information for the collaboration

```sql
CALL {DB}.COLLABORATION.GET_STATUS('<collaboration_name>');
```

### C) View Data Offerings
- **When**: User asks to see data offerings for a specific collaboration
- **Call**: `{DB}.COLLABORATION.VIEW_DATA_OFFERINGS(collaboration_name)`
- **Params**: collaboration_name (required, string)
- **Display**: table names, column information, SHARED_WITH status

```sql
CALL {DB}.COLLABORATION.VIEW_DATA_OFFERINGS('<collaboration_name>');
```

### D) View Templates
- **When**: User asks to see templates for a specific collaboration
- **Call**: `{DB}.COLLABORATION.VIEW_TEMPLATES(collaboration_name)`
- **Params**: collaboration_name (required, string)
- **Display**: template names, IDs, and descriptions

```sql
CALL {DB}.COLLABORATION.VIEW_TEMPLATES('<collaboration_name>');
```

### H) View Code Specs
- **When**: User asks to see code specs for a specific collaboration
- **Call**: `{DB}.COLLABORATION.VIEW_CODE_SPECS(collaboration_name)`
- **Params**: collaboration_name (required, string)
- **Display**: code specs attached to the collaboration

```sql
CALL {DB}.COLLABORATION.VIEW_CODE_SPECS('<collaboration_name>');
```

### I) View Activity History
- **When**: User asks to see activity or audit history for a specific collaboration
- **Call**: `{DB}.COLLABORATION.VIEW_ACTIVITY_HISTORY(collaboration_name)`
- **Params**: collaboration_name (required, string)
- **Display**: activity history for the collaboration

```sql
CALL {DB}.COLLABORATION.VIEW_ACTIVITY_HISTORY('<collaboration_name>');
```

---

## Account-Level Operations (REGISTRY Schema)

**IMPORTANT:** The following operations use the **REGISTRY schema**, NOT COLLABORATION schema. These are account-wide operations that don't require a collaboration name.

### E) View Registered Templates
- **When**: User asks to see all registered templates in the account
- **Call**: `{DB}.REGISTRY.VIEW_REGISTERED_TEMPLATES()`
- **Params**: None
- **Display**: all templates registered in the account

```sql
CALL {DB}.REGISTRY.VIEW_REGISTERED_TEMPLATES();
```

### F) View Registered Data Offerings
- **When**: User asks to see all registered data offerings in the account
- **Call**: `{DB}.REGISTRY.VIEW_REGISTERED_DATA_OFFERINGS()`
- **Params**: None
- **Display**: all data offerings registered in the account

```sql
CALL {DB}.REGISTRY.VIEW_REGISTERED_DATA_OFFERINGS();
```

### F2) View Registered Code Specs
- **When**: User asks to see all registered code specs in the account
- **Call**: `{DB}.REGISTRY.VIEW_REGISTERED_CODE_SPECS()`
- **Params**: None
- **Display**: all code specs registered in the account

```sql
CALL {DB}.REGISTRY.VIEW_REGISTERED_CODE_SPECS();
```

### G) View Registries
- **When**: User asks to see all custom registries in the account
- **Call**: `{DB}.REGISTRY.VIEW_REGISTRIES()`
- **Params**: None
- **Display**: all custom registries in the account

```sql
CALL {DB}.REGISTRY.VIEW_REGISTRIES();
```

## Required Privileges

If operations fail with "Insufficient privileges", see the parent data-cleanrooms SKILL.md "Required Privileges" section for how to grant privileges using `{DB}.ADMIN.GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE` or `{DB}.ADMIN.GRANT_PRIVILEGE_ON_OBJECT_TO_ROLE`.

| Procedure | Privilege | Scope |
|-----------|-----------|-------|
| `VIEW_COLLABORATIONS()` | `VIEW COLLABORATIONS` | Account |
| `VIEW_REGISTERED_TEMPLATES()` | `VIEW REGISTERED TEMPLATES` | Account |
| `VIEW_REGISTERED_DATA_OFFERINGS()` | `VIEW REGISTERED DATA OFFERINGS` | Account |
| `VIEW_REGISTERED_CODE_SPECS()` | `VIEW REGISTERED CODE SPECS` | Account |
| `VIEW_REGISTRIES()` | `VIEW REGISTRIES` | Account |
| `GET_STATUS(collab)` | `GET STATUS` | Collaboration |
| `VIEW_DATA_OFFERINGS(collab)` | `VIEW DATA OFFERINGS` | Collaboration |
| `VIEW_TEMPLATES(collab)` | `VIEW TEMPLATES` | Collaboration |
| `VIEW_CODE_SPECS(collab)` | `VIEW CODE SPECS` | Collaboration |
| `VIEW_ACTIVITY_HISTORY(collab)` | `VIEW ACTIVITY HISTORY` | Collaboration |

## Stopping Points

None - all browse operations are read-only.

## Output

| Operation | Output |
|-----------|--------|
| View Collaborations | Table of collaboration names, IDs, owners, status |
| Get Status | Detailed status for one collaboration |
| View Data Offerings | Table of offerings with columns and sharing status |
| View Templates | Table of template names, IDs, descriptions |
| View Registered Templates | Account-wide registered templates |
| View Registered Data Offerings | Account-wide registered offerings |
| View Registered Code Specs | Account-wide registered code specs |
| View Registries | All custom registries in the account |
| View Code Specs | Code specs for a specific collaboration |
| View Activity History | Activity history for a specific collaboration |
