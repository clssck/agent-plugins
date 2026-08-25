---
name: data-cleanrooms
description: "Use for ALL requests related to Snowflake Data Clean Rooms (DCR): clean room, cleanroom, DCR, collaboration(s), view/list collaborations, join/review collaboration, invitation, data offering(s), template(s), register, share table, run analysis, run activation, audience overlap, activation, export segment, create collaboration, create cleanroom, measure overlap, manage templates, add template, remove template, approve template, reject template, auto-approval, link data offering, unlink data offering, share data with runner, revoke data access, link local data offering, unlink local data offering, tear down, leave, drop collaboration, delete collaboration, RBAC, DCR roles, DCR privileges, create roles for clean rooms, assign DCR privileges, grant collaboration privileges, revoke DCR privileges, set up DCR roles, privileges for data engineers, privileges for campaign manager, create registry, custom registry, new registry, list registries, view registries, manage registries, create template, write template, build template, template spec, create DCR template, author template, Jinja template, template logic, incrementality measurement, multi-touch attribution, attribution analysis, convert PnC template, migrate template. Covers browsing, joining, registering, running analysis/activation, creating collaborations, managing templates, managing data offerings, RBAC/role setup, leaving/tearing down collaborations, creating/authoring template specs, and creating/listing custom registries via the DCR Collaboration API."
allowed-tools:
  - snowflake_sql_execute
  - bash
---

# Snowflake Data Clean Room (DCR) Collaboration API

This skill helps you work with the Snowflake DCR Collaboration API (`snowflake_product_docs`: `https://docs.snowflake.com/en/user-guide/cleanrooms/v2/about`; if that tool is unavailable, `cortex search docs "<query>"` via bash) — a fully symmetric, multi-party collaboration environment for secure data analysis without sharing raw data.

## When to Use

- View collaborations, data offerings, or templates
- Review and join collaborations
- Register data offerings (datasets) for collaborations
- Register templates (analysis queries) for collaborations
- Run analysis templates (standard audience overlap, standard audience overlap activation, custom)
- Create a new collaboration with other parties
- Manage templates in collaborations (add, remove, approve/reject requests, auto-approval)
- Link or unlink data offerings in collaborations (share with runners, revoke access, local linking)
- Leave or tear down collaborations
- Create roles and assign DCR privileges (account-level, collaboration-level, registry-level, persona-based)
- Understand DCR concepts (data mapping, collaboration roles)

## Prerequisites

### 1. DCR Must Be Installed

Verify DCR is available in your account:

```sql
SHOW DATABASES LIKE 'SAMOOHA_BY_SNOWFLAKE_LOCAL_DB%';
```
If no results, DCR is not installed. Contact your administrator.


## Collaboration Roles

The DCR Collaboration API supports flexible multi-party roles:

| Role | Description |
|------|-------------|
| **Owner** | Creates and owns the collaboration, defines invited parties and their roles |
| **Data Provider** | Provides data offerings (datasets) |
| **Analysis Runner** | Runs permitted templates on allowed data offerings |

One account can have multiple roles (e.g., owner + data provider + analysis runner) within the same collaboration.

## Workflow

```
Start
  |
Database Discovery (MANDATORY)
  |
  +-- ONE DB --> use as {DB}
  +-- MULTIPLE --> STOP, ask user
  +-- NONE --> STOP, not installed
  |
Intent Detection
  +---> VIEW --> Load browse/SKILL.md
  +---> JOIN/REVIEW --> Load review-join/SKILL.md
  +---> REGISTER --> Load register/SKILL.md
  +---> UNREGISTER --> Load unregister/SKILL.md
  +---> RUN --> Load run/SKILL.md
  +---> CREATE TEMPLATE --> Load create-template/SKILL.md
  +---> CREATE --> Load create/SKILL.md
  +---> MANAGE TEMPLATES --> Load manage-templates/SKILL.md
  +---> LINK/UNLINK DATA OFFERINGS --> Load manage-data-offerings/SKILL.md
  +---> RBAC --> Load rbac/SKILL.md
  +---> MANAGE REGISTRIES --> Load manage-registries/SKILL.md
  +---> LEAVE/TEARDOWN --> Load teardown-leave/SKILL.md
```

1. **Database Discovery (MANDATORY)** - See [Database Discovery](#database-discovery-first-step---mandatory) below.

2. **Route to Sub-Skill** — Detect intent from user request and **use the `read` tool** to load the matching sub-skill:

   **VIEW** — "view collaborations", "show collaborations", "list collaborations", "view offerings", "view templates"
   → Load `browse/SKILL.md`

   **JOIN/REVIEW** — "join collaboration", "review collaboration", "accept invitation", "review invitation"
   → Load `review-join/SKILL.md`

   **REGISTER** — "register data offering", "register template", "register table", "share table"
   → Load `register/SKILL.md`

   **UNREGISTER** — "unregister data offering", "unregister template", "remove data offering", "delete data offering", "remove template", "delete template"
   → Load `unregister/SKILL.md`

   **CREATE TEMPLATE** — "create template", "write template", "build template", "template spec", "audience overlap template", "activation template", "incrementality template", "attribution template", "convert PnC template", "migrate template"
   → Load `create-template/SKILL.md`

   **RUN** — "run analysis", "run template", "audience overlap", "standard audience overlap", "measure overlap", "activation", "run activation", "compare audiences", "activate", "export segment"
   → Load `run/SKILL.md`

   **CREATE** — "create collaboration", "create cleanroom", "create dcr", "new collaboration", "set up clean room", "initiate collaboration"
   → Load `create/SKILL.md`

   **MANAGE TEMPLATES** — "add template", "remove template", "manage templates", "approve template", "reject template", "template request", "auto-approval", "view update requests"
   → Load `manage-templates/SKILL.md`

   **LINK/UNLINK DATA OFFERINGS** — "link data offering", "unlink data offering", "share data with runner", "revoke data access", "link offering", "unlink offering", "make offering available", "remove offering access", "link local data offering", "unlink local data offering", "add my data locally"
   → Load `manage-data-offerings/SKILL.md`

   **RBAC** — "create roles for data clean rooms", "assign DCR privileges", "grant collaboration privileges", "revoke DCR privileges", "set up DCR roles", "RBAC for clean rooms", "privileges for data engineers", "privileges for campaign manager"
   → Load `rbac/SKILL.md`

   **MANAGE REGISTRIES** — "create registry", "custom registry", "new registry", "list registries", "view registries", "manage registries"
   → Load `manage-registries/SKILL.md`

   **LEAVE/TEARDOWN** — "leave collaboration", "tear down", "teardown", "drop collaboration", "delete collaboration", "leave cleanroom", "exit collaboration"
   → Load `teardown-leave/SKILL.md`

3. **Execute Sub-Skill Workflow & Present Results**

## Database Discovery (FIRST STEP - MANDATORY)

Before any DCR operation, discover the DCR database:

```sql
SHOW DATABASES LIKE 'SAMOOHA_BY_SNOWFLAKE_LOCAL_DB%';
```

| Result | Action |
|--------|--------|
| ONE database | Use that database name as `{DB}` |
| MULTIPLE databases | **STOP** - Ask user which one to use |
| NO database | **STOP** - DCR is not installed. Ask user to install DCR first. |

**If user provides a database name directly**, skip discovery and use that database.

**DO NOT PROCEED until database is confirmed.**

### Using the Database

Once discovered, **replace `{DB}` with the actual database name** in ALL procedure calls:

```sql
-- Example: If discovered database is SAMOOHA_BY_SNOWFLAKE_LOCAL_DB
CALL SAMOOHA_BY_SNOWFLAKE_LOCAL_DB.COLLABORATION.VIEW_COLLABORATIONS();
```

**IMPORTANT:** Sub-skills use `{DB}` as a placeholder. You MUST substitute it with the discovered database name when executing procedures.

## Reading Results from DCR Procedures

DCR procedures return table results. Call them normally — `CALL` renders fine in most environments.

If a `CALL` fails with a client-side render error (e.g. `undefined is not an object`, "can't be parsed", "unexpected format"), **the procedure already ran on Snowflake**. Read its result from the query cache:

```sql
SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));
```

A real SQL error ("Insufficient privileges", "Collaboration not found") means the procedure failed; `RESULT_SCAN` is not the fix there.

## Important: Only Use Documented Procedures

**ALWAYS use CALL procedures to interact with DCR. NEVER query or modify DCR internal tables directly.**

**Rules:**
1. **Only use procedures documented in this skill or its sub-skills.** If a procedure is not listed in any SKILL.md file, do NOT invent or guess it. Refer the user to Snowflake documentation instead.
2. **NEVER modify DCR internal tables.** No `INSERT`, `UPDATE`, or `DELETE` on any DCR table. All interaction must go through `CALL` procedures.
3. **NEVER fabricate API names.** If you are unsure whether a procedure exists (e.g., `UNREGISTER_TEMPLATE`, `DELETE_DATA_OFFERING`, `MODIFY_COLLABORATION`), assume it does NOT exist. Do not propose it.

**Why:** DCR internal table structures are not part of the public API and may change. Only the documented procedures are stable and supported.

**Examples:**
- ❌ `SELECT * FROM {DB}.COLLABORATION.DATA_OFFERINGS`
- ❌ `SELECT * FROM {DB}.COLLABORATION.TEMPLATE_SPECS`
- ❌ `SELECT * FROM {DB}.COLLABORATION.COLLABORATION_STATE`
- ❌ `DELETE FROM {DB}.REGISTRY.REGISTERED_TEMPLATES WHERE ...`
- ❌ `INSERT INTO {DB}.COLLABORATION.DATA_OFFERINGS ...`
- ✓ `CALL {DB}.COLLABORATION.VIEW_DATA_OFFERINGS('<collaboration_name>')`
- ✓ `CALL {DB}.REGISTRY.VIEW_REGISTERED_TEMPLATES()`

## Sub-Skills

| Task | Load | Stopping Point? |
|------|------|-----------------|
| View collaborations, offerings, templates | `browse/SKILL.md` | No |
| Review and join collaborations | `review-join/SKILL.md` | Yes (confirm before join) |
| Register data offerings and templates | `register/SKILL.md` | Yes |
| Unregister data offerings and templates | `unregister/SKILL.md` | Yes (confirm before unregister) |
|| Create or convert a template spec | `create-template/SKILL.md` | Yes (confirm spec before register) |
| Run analysis templates | `run/SKILL.md` | Yes |
| Create a new collaboration (single or multi-party) | `create/SKILL.md` | Yes (confirm spec before initialize) |
| Manage templates (add, remove, approve/reject) | `manage-templates/SKILL.md` | Yes (confirm before add/remove) |
| Link or unlink data offerings | `manage-data-offerings/SKILL.md` | Yes (confirm before link/unlink) |
| Create roles and assign DCR privileges | `rbac/SKILL.md` | Yes (confirm before grant/revoke) |
| Create and list custom registries | `manage-registries/SKILL.md` | Yes (confirm before create) |
| Leave or tear down collaborations | `teardown-leave/SKILL.md` | Yes (confirm before teardown/leave) |

## Stopping Points

- **Database Discovery**: If multiple DBs found, ask user to choose
- **Review-Join**: Confirm before joining a collaboration
- **Register**: Confirm specification before registration
- **Unregister**: Confirm OBJECT_ID and active-use check before unregistering
- **Run**: Collaboration selection, template selection, parameter confirmation before execution
- **Create**: Confirm collaboration spec before initializing
- **Manage Templates**: Confirm before adding/removing templates, confirm before approving/rejecting requests
- **RBAC**: Confirm before granting or revoking account-level, collaboration-level, or registry-level privileges; confirm persona-based setup before executing
- **Manage Registries**: Confirm registry name + type before creating (a separate confirmation for every registry)
- **Leave/Teardown**: Confirm before leaving or tearing down a collaboration

**Resume rule:** Upon user approval, proceed directly without re-asking.

## Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| "Object does not exist" | Wrong database name | Re-run database discovery |
| "Insufficient privileges" | Missing DCR privilege | See "Required Privileges" below |
| "Unknown user-defined function" | Missing DCR privilege | See "Required Privileges" below |
| "Collaboration not found" | Wrong name or not joined | Check `VIEW_COLLABORATIONS()` |
| `ActivationDestinationsNotFoundException` | Missing `activation_destinations` on the runner with the activation template | See `create/SKILL.md` Step 6 |
| "Secondary roles must be disabled" | Procedure requires Secondary roles to be disabled | Run `USE SECONDARY ROLES NONE` before executing procedure and `USE SECONDARY ROLES ALL` to restore after |
| `undefined is not an object`, "can't be parsed", "unexpected format" after a `CALL` | Client-side render bug — procedure succeeded on Snowflake | Read result from cache: `SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))` |

## Required Privileges

DCR operations require specific privileges. If you get "Insufficient privileges" or "Unknown user-defined function" errors, an ACCOUNTADMIN must grant the appropriate privilege using the DCR Admin APIs.

### Granting Account-Level Privileges

```sql
-- Use ACCOUNTADMIN role
USE ROLE ACCOUNTADMIN;

-- Grant an account-level privilege
CALL {DB}.ADMIN.GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE(
    '<privilege_name>',
    '<user_role>'
);

-- Example: Grant ability to view collaborations
CALL SAMOOHA_BY_SNOWFLAKE_LOCAL_DB.ADMIN.GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE(
    'VIEW COLLABORATIONS',
    'ANALYST_ROLE'
);
```

### Granting Collaboration-Level Privileges

```sql
-- Use ACCOUNTADMIN role
USE ROLE ACCOUNTADMIN;

-- Grant privilege on a specific collaboration
CALL {DB}.ADMIN.GRANT_PRIVILEGE_ON_OBJECT_TO_ROLE(
    '<privilege_name>',
    'COLLABORATION',
    '<collaboration_name>',
    '<user_role>'
);

-- Example: Grant ability to view data offerings on a collaboration
CALL SAMOOHA_BY_SNOWFLAKE_LOCAL_DB.ADMIN.GRANT_PRIVILEGE_ON_OBJECT_TO_ROLE(
    'VIEW DATA OFFERINGS',
    'COLLABORATION',
    'my_collaboration',
    'ANALYST_ROLE'
);
```

For full privilege management details, look up Snowflake docs for `https://docs.snowflake.com/en/user-guide/cleanrooms/v2/roles` (`snowflake_product_docs`, else `cortex search docs "<query>"` via bash).

**Note:** Each sub-skill documents its specific required privileges.

## Output

This skill routes to sub-skills, each of which produces its own output:

| Sub-Skill | Output |
|-----------|--------|
| browse | Tables of collaborations, data offerings, or templates |
| review-join | Confirmation of join action |
| register | Confirmation of registration |
| run | Analysis result rows or activation segment export status |
| create | Confirmation of collaboration creation |
| rbac | Role creation and privilege grant/revoke confirmation |

## Tools

### `snowflake_sql_execute`

Used to execute SQL `CALL` procedures against the DCR Collaboration API. All DCR operations go through stored procedures (not direct table queries). This tool is required because every sub-skill relies on procedure calls like `{DB}.COLLABORATION.VIEW_COLLABORATIONS()`.

### Documentation lookups

**`snowflake_product_docs`**, else **`cortex search docs "<query>"`** via **`bash`**. Use `bash` only for that fallback (not for shell file operations).

## Out of Scope / Unknown Requests

If a user asks about DCR functionality not covered in this skill:

1. **First**, search Snowflake product documentation for the relevant DCR topic (e.g., `https://docs.snowflake.com/en/user-guide/cleanrooms/v2/using`) — `snowflake_product_docs`, else `cortex search docs "<query>"` via bash.

2. **If not found**, respond:
   > "This functionality will be added in future updates to this skill. You may want to check with Snowflake support or the latest documentation for updates."

## References

For additional details, search Snowflake product documentation for these topics (`snowflake_product_docs`, else `cortex search docs "<query>"` via bash):
- `https://docs.snowflake.com/en/user-guide/cleanrooms/v2/about`
- `https://docs.snowflake.com/en/user-guide/cleanrooms/v2/roles`
- `https://docs.snowflake.com/en/user-guide/cleanrooms/v2/using`
- `https://docs.snowflake.com/en/user-guide/cleanrooms/v2/v2-api-reference`
- `https://docs.snowflake.com/en/user-guide/cleanrooms/v2/spec-reference`
- `https://docs.snowflake.com/en/user-guide/cleanrooms/v2/registries`
- `https://docs.snowflake.com/en/user-guide/cleanrooms/v2/troubleshooting`

## Sub-Skill Files

- `browse/SKILL.md` - View operations
- `review-join/SKILL.md` - Review and join operations
- `register/SKILL.md` - Register operations
- `unregister/SKILL.md` - Unregister operations
- `create-template/SKILL.md` - Create and convert template specs
- `run/SKILL.md` - Run analysis templates
- `create/SKILL.md` - Create collaboration operations
- `manage-templates/SKILL.md` - Manage templates (add, remove, approve/reject, auto-approval)
- `manage-data-offerings/SKILL.md` - Link or unlink data offerings in collaborations
- `rbac/SKILL.md` - Create roles and assign DCR privileges
- `manage-registries/SKILL.md` - Create and list custom registries
- `teardown-leave/SKILL.md` - Leave or tear down collaborations
