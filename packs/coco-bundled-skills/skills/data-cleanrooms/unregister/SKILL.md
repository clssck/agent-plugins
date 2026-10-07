---
name: unregister
parent_skill: data-cleanrooms
description: "Unregister data offerings and templates from the DCR registry. Triggers: unregister data offering, unregister template, remove data offering, delete data offering, remove template, delete template."
allowed-tools: snowflake_sql_execute
---

# Unregister Data Offerings and Templates

Remove registered data offerings and templates from the account registry using `UNREGISTER_DATA_OFFERING` and `UNREGISTER_TEMPLATE`.

## When to Use

- User wants to remove a data offering from the registry
- User wants to remove a template from the registry
- User says "unregister", "remove", or "delete" a data offering or template

**WARNING:** Unregistering a data offering or template that is still linked to an active collaboration may break that collaboration. Always confirm with the user before proceeding.

## Workflow A: Unregister Data Offering

### Step 1: Get the OBJECT_ID

Ask the user for the `OBJECT_ID` of the data offering. If they don't know it, list all registered offerings first:

```sql
CALL {DB}.REGISTRY.VIEW_REGISTERED_DATA_OFFERINGS();
```

### Step 2: Confirm with User

**MANDATORY STOPPING POINT**: Before unregistering, show the user the `OBJECT_ID` and confirm:

- Ask whether the data offering is still linked to any active collaborations. Removing a linked offering may break those collaborations.
- Ask for explicit confirmation to proceed with unregistering.

NEVER proceed to Step 3 without explicit user confirmation.

### Step 3: Unregister

```sql
CALL {DB}.REGISTRY.UNREGISTER_DATA_OFFERING('<object_id>');
```

FQN: `{DB}.REGISTRY.UNREGISTER_DATA_OFFERING`

---

## Workflow B: Unregister Template

### Step 1: Get the OBJECT_ID

Ask the user for the `OBJECT_ID` of the template. If they don't know it, list all registered templates first:

```sql
CALL {DB}.REGISTRY.VIEW_REGISTERED_TEMPLATES();
```

### Step 2: Confirm with User

**MANDATORY STOPPING POINT**: Before unregistering, show the user the `OBJECT_ID` and confirm:

- Ask whether the template is still linked to any active collaborations. Removing a linked template may break those collaborations.
- Ask for explicit confirmation to proceed with unregistering.

NEVER proceed to Step 3 without explicit user confirmation.

### Step 3: Unregister

```sql
CALL {DB}.REGISTRY.UNREGISTER_TEMPLATE('<object_id>');
```

FQN: `{DB}.REGISTRY.UNREGISTER_TEMPLATE`

---

## Required Privileges

| Procedure | Privilege | Scope |
|-----------|-----------|-------|
| `UNREGISTER_DATA_OFFERING(object_id)` | `REGISTER DATA OFFERING` | Account |
| `UNREGISTER_TEMPLATE(object_id)` | `REGISTER TEMPLATE` | Account |

The same privilege that grants registration also grants unregistration for the same resource type.

Grant via:
```sql
USE ROLE ACCOUNTADMIN;
CALL {DB}.ADMIN.GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE('REGISTER DATA OFFERING', '<role_name>');
CALL {DB}.ADMIN.GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE('REGISTER TEMPLATE', '<role_name>');
```

## Stopping Points

- Before Step 3 in both workflows: confirm OBJECT_ID and user acknowledges item is not in active use.

**Resume rule:** Upon user approval, proceed directly without re-asking.

## Output

| Operation | Output |
|-----------|--------|
| Unregister Data Offering | Confirmation that the data offering was removed from the registry |
| Unregister Template | Confirmation that the template was removed from the registry |
