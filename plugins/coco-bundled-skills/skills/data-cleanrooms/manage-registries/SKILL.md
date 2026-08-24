---
name: manage-registries
parent_skill: data-cleanrooms
description: "Create and list custom registries that store DCR resources (templates, data offerings, and code specs) at the account level. Triggers: create registry, custom registry, new registry, list registries, view registries, manage registries."
allowed-tools: snowflake_sql_execute
---

# Manage Custom Registries

Create and list custom registries used to store and organize DCR resources (templates, data offerings, and code specs) at the account level.

## When to Use

- User wants to create a custom registry (e.g., "create a registry for sales templates")
- User wants to list/see the registries they have access to
- User wants to group or separate resources (templates, data offerings, code specs) into their own containers
- User says "create registry", "custom registry", "new registry", "list registries", "view registries"

**IMPORTANT:** Always use CALL procedures, never query or modify DCR internal tables directly. Only use procedures documented in this skill.

**CRITICAL — Confirmation is required for EVERY registry creation.** You MUST stop and get explicit user approval before *each* `CREATE_REGISTRY` call, including the second, third, and every subsequent registry in the same conversation. Approval for one registry NEVER carries over to another. Never assume "Yes", never answer the confirmation prompt on the user's behalf, and never batch-create registries without confirming each one individually.

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Registry** | An account-level container that stores DCR resources (templates, data offerings, and code specs) |
| **Default registry** | Every account has one. It holds **any** resource type and is accessible to all users in the account |
| **Custom registry** | A registry you create. Holds a **single** resource type — `TEMPLATE`, `DATA OFFERING`, or `CODE SPEC` (set at creation). Initially **private to the creator** until access is granted |
| **Resource name uniqueness** | A resource name must be unique across **all** registries of that type in the account (e.g., you cannot have two templates with the same name and version e.g. `sales_v1` anywhere in the account) |

### Registry Rules

- Registries are account-scoped — users only see registries in their own account.
- Once a resource is **linked into a collaboration**, it is visible per the collaboration spec; access to the containing registry is **not** required to use the linked resource.
- A custom registry supports exactly **one** resource type (`TEMPLATE`, `DATA OFFERING`, or `CODE SPEC`), designated at creation.
- The creator of a custom registry automatically has read + write access to it. Other users must be granted `READ` or `REGISTER` explicitly.
- There is **no limit** on the number of custom registries or the resources they hold.

For related operations, see the sibling sub-skills:
- Granting other users `READ`/`REGISTER` access to a registry → the `rbac` sub-skill (registry-level privileges)
- Registering data offerings/templates/code specs into a registry → the `register` sub-skill
- Listing registries and registered resources → the `browse` sub-skill

## Workflow A: Create a Custom Registry

### Step 1: Gather Information

Ask the user explicitly — do NOT invent values:
- **Name** for the registry? (Required. Must be unique across all registries in the account. `default` is a **reserved keyword** for the built-in registry and cannot be used as a custom registry name.)
- **Resource type** the registry will hold? Ask the user to choose one:
  - `TEMPLATE` — registry holds templates
  - `DATA OFFERING` — registry holds data offerings
  - `CODE SPEC` — registry holds code specs

A custom registry holds a **single** resource type. If the user needs to store multiple resource types in separate containers, create one registry per type.

### Step 2: Confirm with User (MANDATORY STOPPING POINT)

**You MUST stop here and wait for the user's explicit reply before doing anything else.** Show the registry name and type and ask for confirmation:

> "I will create a custom registry `<name>` that holds `<type>` resources. Proceed? (Yes/No/Modify)"

Do not emit the `CREATE_REGISTRY` call, do not continue the turn, and do not answer the prompt yourself. Wait for the user's next message.

Handle the reply:
- **Yes** (or clear approval) → proceed to Step 3 for this registry only.
- **No** → do not create anything; ask what they'd like to change or cancel.
- **Modify** (e.g., "change the name to ANALYTICS") → apply the change, then **re-display the updated name + type and ask "Proceed? (Yes/No/Modify)" again.** Repeat this loop until the user explicitly approves. Never create the registry off a "Modify" reply.

**This stopping point applies to EVERY registry, every time.** If the user asks to create another registry later in the conversation (Task 2, 2b, etc.), repeat Steps 1–2 and get a fresh confirmation for that registry. A prior "Yes" NEVER authorizes a different registry. When a request implies multiple registries (e.g., "create registries for templates and data offerings"), confirm and create them one at a time — one stopping point per registry.

NEVER proceed to Step 3 without explicit user approval for that specific registry.

### Step 3: Create the Registry

```sql
CALL {DB}.REGISTRY.CREATE_REGISTRY('<registry_name>', '<TEMPLATE | DATA OFFERING | CODE SPEC>');
```

**Examples:**

```sql
CALL {DB}.REGISTRY.CREATE_REGISTRY('SALES', 'TEMPLATE');
CALL {DB}.REGISTRY.CREATE_REGISTRY('ML_SPECS', 'CODE SPEC');
```

### Step 4: Verify

Confirm the new registry appears by listing registries — see the `browse` sub-skill, Section G: View Registries (`{DB}.REGISTRY.VIEW_REGISTRIES()`).

## Listing Registries

To list all registries (default + custom) you have access to, see the `browse` sub-skill, Section G: View Registries. A custom registry created by another user only appears if you have `READ` or `REGISTER` access to it.

## Scoping Registry Reads

`VIEW_REGISTERED_TEMPLATES`, `VIEW_REGISTERED_DATA_OFFERINGS`, and `VIEW_REGISTERED_CODE_SPECS` (documented in the `browse` sub-skill) accept an **optional ARRAY of registry names** to scope the read. Use `'default'` (case-insensitive) to include the built-in registry alongside custom ones. Inaccessible or non-existent registries in the array are silently skipped. If omitted, results include all registries you have access to.

```sql
-- Only the default registry and a custom 'SALES' registry
CALL {DB}.REGISTRY.VIEW_REGISTERED_TEMPLATES(['default', 'SALES']);

-- Only a specific custom registry
CALL {DB}.REGISTRY.VIEW_REGISTERED_DATA_OFFERINGS(['SALES']);
```

## Workflow B: Register Resources into a Custom Registry

`REGISTER_DATA_OFFERING` and `REGISTER_TEMPLATE` accept an **optional leading `'<registry_name>'`** argument. If omitted, the resource is registered in the account's default registry. To target a custom registry instead, pass its name as the **first** argument. The custom registry must already exist and hold the matching resource type.

The full data offering / template spec format, policies, and confirmation steps are owned by the `register` sub-skill — only the optional leading registry-name argument is shown here.

**Data offering into a custom registry:**

```sql
USE SECONDARY ROLES NONE;
CALL {DB}.REGISTRY.REGISTER_DATA_OFFERING('<registry_name>', $$
api_version: 2.0.0
spec_type: data_offering
name: my_customers
version: v1
...
$$);
USE SECONDARY ROLES ALL;
```

**Template into a custom registry:**

```sql
CALL {DB}.REGISTRY.REGISTER_TEMPLATE('<registry_name>', $$
api_version: 2.0.0
spec_type: template
name: my_overlap_analysis
version: v1
type: sql_analysis
...
$$);
```

The resource `name` must be unique across **all** registries of that type in the account (a new release uses a new `version`, e.g. `v1` → `v2`).

## No Delete API

There is **no `DROP_REGISTRY` or `DELETE_REGISTRY` procedure**. Do NOT fabricate one or attempt to manipulate internal tables. If a user wants to stop using a registry, simply stop registering resources into it; access can be revoked (see the `rbac` sub-skill).

## Required Privileges

If operations fail with "Insufficient privileges", see the parent data-cleanrooms SKILL.md "Required Privileges" section for how to grant privileges using `{DB}.ADMIN.GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE` or `{DB}.ADMIN.GRANT_PRIVILEGE_ON_OBJECT_TO_ROLE`.

| Procedure | Privilege | Scope |
|-----------|-----------|-------|
| `CREATE_REGISTRY(name, type)` | `CREATE REGISTRY` | Account |
| `VIEW_REGISTRIES()` | `VIEW REGISTRIES` | Account |


## Output

| Operation | Output |
|-----------|--------|
| Create Custom Registry | Creation confirmation + verification via VIEW_REGISTRIES (see the `browse` sub-skill) |
