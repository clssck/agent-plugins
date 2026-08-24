---
name: dcr-rbac
description: "Create custom roles and assign DCR collaboration privileges using the Collaboration API RBAC system. Supports account-level, collaboration-level, and registry-level privilege grants/revokes, and persona-based role setup. Triggers: create roles for data clean rooms, assign DCR privileges, grant collaboration privileges, revoke DCR privileges, set up DCR roles, RBAC for clean rooms, privileges for data engineers, privileges for campaign manager."
allowed-tools: snowflake_sql_execute
---

# DCR RBAC — Role & Privilege Management

Create custom Snowflake roles and assign granular privileges for DCR Collaboration API operations.

## When to Use

- User wants to create roles for DCR collaboration workflows
- User wants to grant or revoke DCR privileges (account-level or collaboration-level)
- User wants to set up persona-based access (data engineer, campaign manager, analyst, etc.)
- User says "create roles for clean rooms", "assign DCR privileges", "grant collaboration privileges", "RBAC for DCR"

## Key Concepts

| Concept | Description |
|---------|-------------|
| **SAMOOHA_APP_ROLE** | Built-in high-privilege role that can call all DCR procedures. The RBAC system lets you create more granular alternatives |
| **Account-level privileges** | Control what a role can do across the account (e.g., create collaborations, register templates) |
| **Collaboration-level privileges** | Control what a role can do within a specific collaboration (e.g., run analysis, link data) |
| **Registry-level privileges** | Control what a role can do within a custom registry (e.g., register or read items) |
| **{DB}** | The DCR database, typically `SAMOOHA_BY_SNOWFLAKE_LOCAL_DB` — discovered dynamically |

## Privilege Reference

### Account-Level Privileges

Granted via `{DB}.ADMIN.GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE('<privilege>', '<role>')`.

| Privilege | Allows |
|-----------|--------|
| `CREATE COLLABORATION` | Create new collaborations via `COLLABORATION.INITIALIZE` |
| `JOIN COLLABORATION` | Join collaborations via `COLLABORATION.JOIN` |
| `REVIEW COLLABORATION` | Review collaboration invitations via `COLLABORATION.REVIEW` |
| `VIEW COLLABORATIONS` | List collaborations via `COLLABORATION.VIEW_COLLABORATIONS` |
| `REGISTER DATA OFFERING` | Register data offerings in the default registry |
| `REGISTER TEMPLATE` | Register templates in the default registry |
| `REGISTER CODE SPEC` | Register code specs in the default registry |
| `VIEW REGISTERED DATA OFFERINGS` | View registered offerings in the default registry |
| `VIEW REGISTERED TEMPLATES` | View registered templates in the default registry |
| `VIEW REGISTERED CODE SPECS` | View registered code specs in the default registry |
| `CREATE REGISTRY` | Create custom registries |
| `VIEW REGISTRIES` | List custom registries |
| `USE DCR AGENT` | Use the DCR Agent feature |

### Collaboration-Level Privileges

Granted via `{DB}.ADMIN.GRANT_PRIVILEGE_ON_OBJECT_TO_ROLE('<privilege>', 'COLLABORATION', '<collab_name>', '<role>')`.

| Privilege | Allows |
|-----------|--------|
| `READ` | Read collaboration metadata |
| `UPDATE` | Update collaboration (link data, add/remove templates — broad permission) |
| `GET STATUS` | Check collaboration status via `COLLABORATION.GET_STATUS` |
| `VIEW DATA OFFERINGS` | View data offerings in a collaboration |
| `LINK LOCAL DATA OFFERINGS` | Link local data offerings to a collaboration |
| `UNLINK LOCAL DATA OFFERINGS` | Unlink local data offerings from a collaboration |
| `VIEW TEMPLATES` | View templates in a collaboration |
| `VIEW CODE SPECS` | View code specs in a collaboration |
| `ADD TEMPLATE REQUEST` | Request to add a template to an existing collaboration |
| `REMOVE TEMPLATE` | Remove a template from a collaboration |
| `MANAGE UPDATE REQUEST` | Approve or reject collaboration update requests |
| `MANAGE TEMPLATE AUTO APPROVAL` | Enable/disable auto-approval for template requests |
| `VIEW UPDATE REQUESTS` | View pending update requests in a collaboration |
| `VIEW ACTIVATIONS` | View activation results |
| `PROCESS ACTIVATION` | Process activation segments |
| `RUN` | Run analysis/activation templates via `COLLABORATION.RUN` |

> **Note:** `LINK DATA OFFERINGS` and `UNLINK DATA OFFERINGS` (without "LOCAL") are **not valid privileges** — the API rejects them. Only `LINK LOCAL DATA OFFERINGS` and `UNLINK LOCAL DATA OFFERINGS` are supported.

### Registry-Level Privileges

Granted via `{DB}.ADMIN.GRANT_PRIVILEGE_ON_OBJECT_TO_ROLE('<privilege>', 'REGISTRY', '<registry_name>', '<role>')`.

Used for custom registries. The default registry is accessible to anyone with the corresponding account-level privilege.

| Privilege | Allows |
|-----------|--------|
| `REGISTER` | Register data offerings, templates, or code specs in a custom registry |
| `READ` | Read/view items in a custom registry |

---

## Workflow

### Step 0: Discover DCR Database

```sql
SHOW DATABASES LIKE 'SAMOOHA_BY_SNOWFLAKE_LOCAL_DB%';
```

Use the result as `{DB}` in all subsequent calls. If no database is found, inform the user that the DCR application is not installed.

### Step 1: Determine Intent

Ask the user what they need:

| Intent | Next Step |
|--------|-----------|
| Create a new role with DCR privileges | Step 2 |
| Grant privileges to an existing role | Step 3 |
| Grant collaboration-level privileges | Step 4 |
| Grant registry-level privileges | Step 4b |
| Revoke privileges | Step 5 |
| Set up a persona-based role (data engineer, campaign manager, etc.) | Step 6 |

### Step 2: Create a New Role

Ask for the role name. Create the role and grant it to the user:

```sql
USE ROLE ACCOUNTADMIN;
CREATE ROLE IF NOT EXISTS <role_name>;
GRANT ROLE <role_name> TO USER <username>;
```

Then proceed to Step 3 to grant account-level privileges, or Step 6 for persona-based setup.

### Step 3: Grant Account-Level Privileges

Present the account-level privileges table and ask which privileges to grant.

**MANDATORY STOPPING POINT**: Show the selected privileges and ask for confirmation before executing.

> "I will grant the following account-level privileges to role `<role_name>`:
> - `<privilege_1>`
> - `<privilege_2>`
> 
> Proceed? (Yes/No/Modify)"

On confirmation, execute each grant:

```sql
USE ROLE ACCOUNTADMIN;
CALL {DB}.ADMIN.GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE('<privilege>', '<role_name>');
```

**Important — additional Snowflake grants required for some privileges:**

| DCR Privilege | Also Requires |
|---------------|---------------|
| `CREATE COLLABORATION` | `GRANT IMPORT SHARE ON ACCOUNT TO ROLE <role_name>;` + `GRANT CREATE SHARE ON ACCOUNT TO ROLE <role_name>;` + `GRANT CREATE DATABASE ON ACCOUNT TO ROLE <role_name>;` + `GRANT CREATE LISTING ON ACCOUNT TO ROLE <role_name>;` + `GRANT MANAGE SHARE TARGET ON ACCOUNT TO ROLE <role_name>;` + `GRANT APPLY ROW ACCESS POLICY ON ACCOUNT TO ROLE <role_name>;` + `GRANT CREATE APPLICATION ON ACCOUNT TO ROLE <role_name>;` |
| `VIEW COLLABORATIONS` | `GRANT IMPORT SHARE ON ACCOUNT TO ROLE <role_name>;` |
| `REGISTER DATA OFFERING` | `GRANT USAGE ON DATABASE <db> TO ROLE <role_name>;` + `GRANT USAGE ON SCHEMA <db>.<schema> TO ROLE <role_name>;` + `GRANT SELECT ON TABLE <db>.<schema>.<table> TO ROLE <role_name>;` for each dataset table |

### Step 4: Grant Collaboration-Level Privileges

Ask for:
1. The collaboration name
2. Which collaboration-level privileges to grant

**MANDATORY STOPPING POINT**: Show the selected privileges and ask for confirmation before executing.

Execute each grant:

```sql
USE ROLE ACCOUNTADMIN;
CALL {DB}.ADMIN.GRANT_PRIVILEGE_ON_OBJECT_TO_ROLE(
    '<privilege>',
    'COLLABORATION',
    '<collaboration_name>',
    '<role_name>'
);
```

### Step 4b: Grant Registry-Level Privileges

For custom registries only. Ask for:
1. The registry name
2. Which registry-level privileges to grant (`REGISTER` or `READ`)

Execute each grant:

```sql
USE ROLE ACCOUNTADMIN;
CALL {DB}.ADMIN.GRANT_PRIVILEGE_ON_OBJECT_TO_ROLE(
    '<privilege>',
    'REGISTRY',
    '<registry_name>',
    '<role_name>'
);
```

### Step 5: Revoke Privileges

Ask which privileges to revoke and at what scope (account, collaboration, or registry).

**MANDATORY STOPPING POINT**: Show the privileges to revoke and ask for confirmation.

**Account-level revoke:**

> **Note:** There is no `REVOKE_PRIVILEGE_ON_ACCOUNT_FROM_ROLE` procedure yet. To remove account-level DCR privileges, revoke the database role directly:
> ```sql
> USE ROLE ACCOUNTADMIN;
> REVOKE DATABASE ROLE {DB}.<database_role> FROM ROLE <role_name>;
> ```
> Or drop and recreate the custom role.

**Collaboration-level revoke:**

```sql
USE ROLE ACCOUNTADMIN;
CALL {DB}.ADMIN.REVOKE_PRIVILEGE_ON_OBJECT_FROM_ROLE(
    '<privilege>',
    'COLLABORATION',
    '<collaboration_name>',
    '<role_name>'
);
```

**Registry-level revoke:**

```sql
USE ROLE ACCOUNTADMIN;
CALL {DB}.ADMIN.REVOKE_PRIVILEGE_ON_OBJECT_FROM_ROLE(
    '<privilege>',
    'REGISTRY',
    '<registry_name>',
    '<role_name>'
);
```

### Step 6: Persona-Based Role Setup

Pre-defined privilege bundles for common personas. Ask which persona to set up, then confirm the privilege list before executing.

**Persona selection guidance:** Follow principle of least privilege. If the user says "create collaborations" (initiator), use `Collaboration Creator`. If "join collaborations" (joiner), use `Collaboration Joiner`. Only use `Collaboration Owner / Admin` when the user explicitly needs both sides or says "full lifecycle" / "end-to-end."

**Freshly created roles**: A newly created role has NO warehouse access. Always include `GRANT USAGE ON WAREHOUSE <warehouse> TO ROLE <role>;` when setting up a new role — without it, the role cannot execute any DCR procedures.

**MANDATORY STOPPING POINT**: Present the full privilege list for the selected persona and ask for confirmation before executing any grants.

#### Collaboration Creator

Creates new collaborations (initiator side). Includes `JOIN COLLABORATION` because after `INITIALIZE`, the creator must call `JOIN()` to join their own collaboration. Does NOT include `VIEW COLLABORATIONS` — not required to manage collaborations you created.

**Account-level:**
- `CREATE COLLABORATION`
- `JOIN COLLABORATION`
- `REGISTER DATA OFFERING`
- `REGISTER TEMPLATE`
- `VIEW REGISTERED DATA OFFERINGS`
- `VIEW REGISTERED TEMPLATES`

**Collaboration-level (per collaboration created):**
- `READ`
- `UPDATE`
- `MANAGE UPDATE REQUEST`
- `MANAGE TEMPLATE AUTO APPROVAL`

**Additional Snowflake grants:**
- `GRANT IMPORT SHARE ON ACCOUNT TO ROLE <role>;`
- `GRANT CREATE SHARE ON ACCOUNT TO ROLE <role>;`
- `GRANT CREATE DATABASE ON ACCOUNT TO ROLE <role>;`
- `GRANT CREATE LISTING ON ACCOUNT TO ROLE <role>;`
- `GRANT MANAGE SHARE TARGET ON ACCOUNT TO ROLE <role>;`
- `GRANT APPLY ROW ACCESS POLICY ON ACCOUNT TO ROLE <role>;`
- `GRANT CREATE APPLICATION ON ACCOUNT TO ROLE <role>;`

#### Collaboration Joiner

Joins existing collaborations (joiner side). Does NOT include `CREATE COLLABORATION`. Use this for standard join flows where the collaborator accepts and joins directly. For invite-based review flows that require `REVIEW COLLABORATION` before joining, use `Reviewer / Joiner` instead.

**Account-level:**
- `JOIN COLLABORATION`
- `VIEW COLLABORATIONS`
- `VIEW REGISTERED DATA OFFERINGS`
- `VIEW REGISTERED TEMPLATES`

**Collaboration-level (per collaboration joined):**
- `READ`
- `GET STATUS`

**Additional Snowflake grants:**
- `GRANT IMPORT SHARE ON ACCOUNT TO ROLE <role>;`

#### Collaboration Owner / Admin

Full lifecycle superset: creates AND joins collaborations, manages both sides end-to-end. Use this only when a single role genuinely needs to do everything. Prefer the narrower `Collaboration Creator` or `Collaboration Joiner` personas when intent is clear.

**Account-level:**
- `CREATE COLLABORATION`
- `JOIN COLLABORATION`
- `VIEW COLLABORATIONS`
- `REGISTER DATA OFFERING`
- `REGISTER TEMPLATE`
- `VIEW REGISTERED DATA OFFERINGS`
- `VIEW REGISTERED TEMPLATES`

**Collaboration-level (per collaboration):**
- `READ`
- `UPDATE`
- `MANAGE UPDATE REQUEST`
- `MANAGE TEMPLATE AUTO APPROVAL`

**Additional Snowflake grants:**
- `GRANT IMPORT SHARE ON ACCOUNT TO ROLE <role>;`
- `GRANT CREATE SHARE ON ACCOUNT TO ROLE <role>;`
- `GRANT CREATE DATABASE ON ACCOUNT TO ROLE <role>;`
- `GRANT CREATE LISTING ON ACCOUNT TO ROLE <role>;`
- `GRANT MANAGE SHARE TARGET ON ACCOUNT TO ROLE <role>;`
- `GRANT APPLY ROW ACCESS POLICY ON ACCOUNT TO ROLE <role>;`
- `GRANT CREATE APPLICATION ON ACCOUNT TO ROLE <role>;`

#### Data Engineer

Registers data offerings and templates, links data to collaborations.

**Account-level:**
- `REGISTER DATA OFFERING`
- `VIEW REGISTERED DATA OFFERINGS`
- `REGISTER TEMPLATE`
- `VIEW REGISTERED TEMPLATES`
- `VIEW COLLABORATIONS`

**Collaboration-level (per collaboration):**
- `READ`
- `VIEW DATA OFFERINGS`
- `LINK LOCAL DATA OFFERINGS`
- `UNLINK LOCAL DATA OFFERINGS`
- `UPDATE`
- `VIEW TEMPLATES`
- `VIEW UPDATE REQUESTS`
- `GET STATUS`

**Additional Snowflake grants:**
- `GRANT IMPORT SHARE ON ACCOUNT TO ROLE <role>;`
- `GRANT USAGE ON DATABASE <db> TO ROLE <role>;`
- `GRANT USAGE ON SCHEMA <db>.<schema> TO ROLE <role>;`
- `GRANT SELECT ON TABLE <db>.<schema>.<table> TO ROLE <role>;` (for each dataset)

#### Analyst / Analysis Runner

Runs analyses on existing collaborations.

**Account-level:**
- `VIEW COLLABORATIONS`
- `VIEW REGISTERED TEMPLATES`
- `VIEW REGISTERED DATA OFFERINGS`

**Collaboration-level (per collaboration):**
- `READ`
- `RUN`
- `VIEW DATA OFFERINGS`
- `VIEW TEMPLATES`
- `GET STATUS`

**Additional Snowflake grants:**
- `GRANT IMPORT SHARE ON ACCOUNT TO ROLE <role>;`

#### Campaign Manager (Activation)

Runs activation templates and processes segments.

**Account-level:**
- `VIEW COLLABORATIONS`
- `VIEW REGISTERED TEMPLATES`
- `VIEW REGISTERED DATA OFFERINGS`

**Collaboration-level (per collaboration):**
- `READ`
- `RUN`
- `VIEW DATA OFFERINGS`
- `VIEW TEMPLATES`
- `VIEW ACTIVATIONS`
- `PROCESS ACTIVATION`
- `GET STATUS`

**Additional Snowflake grants:**
- `GRANT IMPORT SHARE ON ACCOUNT TO ROLE <role>;`

#### Reviewer / Joiner

Reviews and joins collaborations created by others. Use this for invite-based flows where the collaborator must review (approve/reject) before joining. If no review step is needed, use `Collaboration Joiner` instead.

**Account-level:**
- `REVIEW COLLABORATION`
- `JOIN COLLABORATION`
- `VIEW COLLABORATIONS`

**Additional Snowflake grants:**
- `GRANT IMPORT SHARE ON ACCOUNT TO ROLE <role>;`

#### Registry Manager

Creates and manages custom registries.

**Account-level:**
- `CREATE REGISTRY`
- `VIEW REGISTRIES`

**Registry-level (per custom registry):**
- `REGISTER`
- `READ`

---

## Known Issues & Workarounds

| Issue | Workaround |
|-------|------------|
| `REGISTER DATA OFFERING` does NOT automatically grant `VIEW REGISTERED DATA OFFERINGS` | Always grant both explicitly |
| `REGISTER TEMPLATE` does NOT automatically grant `VIEW REGISTERED TEMPLATES` | Always grant both explicitly |
| `RUN` on a collaboration does NOT grant `READ` | Always grant `READ` alongside `RUN` |
| `LINK LOCAL DATA OFFERING` fails if a prior call was made by a different role on the same collaboration | Known TABLE_NAMES ownership bug — use same role for all link operations on a collaboration, or use SAMOOHA_APP_ROLE |
| `VIEW COLLABORATIONS` requires both DCR privilege AND `IMPORT SHARE` | Always grant `IMPORT SHARE ON ACCOUNT` alongside `VIEW COLLABORATIONS` |
| Data offering registration requires SELECT on underlying tables | Grant `USAGE` on database/schema and `SELECT` on tables before registering |
| Custom registry items not visible to other roles | Grant `READ` on the custom registry via `GRANT_PRIVILEGE_ON_OBJECT_TO_ROLE` |

---

## Execution Notes

- All `GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE` and `GRANT_PRIVILEGE_ON_OBJECT_TO_ROLE` calls must be made with `ACCOUNTADMIN` role (or a role with equivalent privileges)
- Collaboration-level privileges can only be granted after the collaboration exists and the granting role has access to it
- Registry-level privileges use object type `'REGISTRY'` (not `'COLLABORATION'`)

## Stopping Points

- Before granting account-level privileges: Show privilege list and get user confirmation
- Before granting collaboration-level privileges: Show privilege list and get user confirmation
- Before granting registry-level privileges: Show privilege list and get user confirmation
- Before revoking any privileges: Show revoke list and get user confirmation
- Before executing persona-based setup: Show full privilege bundle and get user confirmation

**Resume rule:** Upon user approval, proceed directly without re-asking.

## Output

| Operation | Output |
|-----------|--------|
| Create role | Role creation confirmation |
| Grant privileges | List of granted privileges with confirmation |
| Revoke privileges | List of revoked privileges with confirmation |
| Persona setup | Complete privilege bundle granted with confirmation |
