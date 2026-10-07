---
name: request-object-access
description: "Configure a Snowflake Native App to request access to consumer-owned objects (tables, views, warehouses, secrets, etc.) using the references mechanism. Generates manifest reference definitions and register callback procedures. Triggers: object reference, consumer table, consumer object, access consumer, register_callback, SYSTEM$REFERENCE, request reference, bind object, reference definition, consumer warehouse, consumer secret, consumer view, access existing object."
parent_skill: native-app-provider
---

# Object Access Request Configuration

> **⚠️ MANDATORY**: If your system prompt mentions Snowsight, load [`../references/native-apps-snowsight.md`](../references/native-apps-snowsight.md) before doing anything else.

## When to Load

From the root `native-app-provider` skill when the user wants to configure an app to access objects that exist in the consumer account outside the app (tables, views, warehouses, secrets, etc.).

## Prerequisites

- A project directory with `manifest.yml` and a setup script (typically `scripts/setup.sql`)

## Key Concept

A **reference** is the mechanism by which a Snowflake Native App requests access to a consumer-owned object. The provider defines reference definitions in the manifest, and the consumer binds their actual objects to those references after installing the app.

This is distinct from **privileges** (account-level permissions like `CREATE WAREHOUSE`) — references are about accessing specific existing objects in the consumer account.

## EAI and Secret — Dedicated Skill

For **External Access Integrations** and paired **Secrets**, load `request-external-access-integration/SKILL.md` instead. That skill handles both approaches (consumer-owned EAI via references, and app-created EAI via privileges + app specifications) in a single comprehensive workflow.

For **Security Integrations** created by the app, use `request-security-integration/SKILL.md`.

## Workflow

### Step 1: Gather Project Files

**Ask** the user for the following (skip any items already known from a prior skill):

```
To configure object access, I need:
1. **Project directory**: Where are your app files? (e.g., /Users/you/projects/my_app)
2. **Application package name**: What is the application package name? (e.g., MY_APP_PKG)
```

Read `manifest.yml` and the setup script (path from `artifacts.setup_script`, default: `setup.sql`).

**STOP** if either file is missing: suggest loading `setup-app/SKILL.md` to create it.

### Step 2: Collect References and Analyze

Read existing references from the manifest. **Load** `../references/ref-object.md` for object types and allowed privileges.

Ask the user what consumer objects the app needs to access. For each, collect: object type, privileges, reference name, label, description, and whether multi-valued.

Compare against existing references — skip duplicates, warn on name conflicts, present new references to add. **STOP** for user confirmation.

For each approved reference, add it to the `references` block in `manifest.yml`:

```yaml
references:
  - consumer_table:
      label: "Consumer Data Table"
      description: "Source table containing data for analysis"
      privileges:
        - SELECT
        - INSERT
      object_type: TABLE
      multi_valued: false
      register_callback: <schema>.register_single_reference
```

**Rules:**
- Reference names must be unique within the manifest
- Privileges must be valid for the object type (see `../references/ref-object.md`)
- Every reference needs a `register_callback`
- **For `EXTERNAL ACCESS INTEGRATION` and `SECRET` types**: add `configuration_callback: <schema>.get_configuration_for_reference` — **required**, without it Snowflake raises `Missing field 'configuration_callback'`
- Set `multi_valued: true` only when the user confirms the app needs multiple objects per reference
- Preserve existing references — don't remove any without user approval

### Step 3: Generate Callback Procedures

Add the register callback stored procedure(s) to the setup script.

**If no register callback exists yet**, generate one using templates from `../references/ref-object.md`:

- For single-valued references: use the **Register Callback Procedure (Single-Value)** template
- For multi-valued references: use the **Register Callback Procedure (Multi-Value)** template

**If a register callback already exists** in the setup script, reuse it — multiple references can share the same callback procedure. Only create a new one if the user needs both single-valued and multi-valued callbacks.

**Important**: The callback procedure should be:
- Created in a versioned schema (`CREATE OR ALTER VERSIONED SCHEMA`) — this is a best practice for stateless code so it upgrades cleanly across versions
- Granted `USAGE` to an application role

### Step 4: Handle Special Types (EXTERNAL ACCESS INTEGRATION and SECRET)

If any reference has `object_type` of `EXTERNAL ACCESS INTEGRATION` or `SECRET`:

**Load `request-external-access-integration/SKILL.md`** and follow its Approach B workflow. That skill handles all EAI and SECRET reference configuration, including the configuration callback, paired secret setup, and the wrapper pattern.

Pass along the project directory, manifest, and setup script context so the user doesn't need to re-provide them.

### Step 5: Validate

Re-read the updated manifest and setup script. Confirm:
- [ ] Each reference has all required fields: `label`, `description`, `privileges`, `object_type`, `register_callback`
- [ ] For `EXTERNAL ACCESS INTEGRATION` and `SECRET` types: `configuration_callback` field is present
- [ ] All privileges are valid for their object type
- [ ] No duplicate reference names
- [ ] The `register_callback` procedure exists in the setup script and is granted to an application role
- [ ] For EAI/SECRET types: `GET_CONFIGURATION_FOR_REFERENCE` procedure exists with a `WHEN` case for the reference name
- [ ] Multi-valued references use `SYSTEM$ADD_REFERENCE` (not `SYSTEM$SET_REFERENCE`)

Present final summary to user.

### Step 6: Document Consumer Binding Command

After installation, consumers bind objects to references by calling the register callback with a `SYSTEM$REFERENCE` handle. No separate `GRANT ... TO APPLICATION` is needed — `SYSTEM$REFERENCE` encapsulates the privilege grant.

**General pattern:**

```sql
CALL <app>.<schema>.register_single_reference(
  '<REFERENCE_NAME>', 'ADD',
  SYSTEM$REFERENCE('<OBJECT_TYPE>', '<object_name>', 'PERSISTENT', '<privilege_1>'[, '<privilege_2>', ...]));
```

**Examples:**

```sql
-- Table reference
CALL app.config.register_single_reference(
  'CONSUMER_TABLE', 'ADD',
  SYSTEM$REFERENCE('TABLE', 'db.schema.my_table', 'PERSISTENT', 'SELECT', 'INSERT'));

-- EAI + SECRET references (see ref-eai.md / ref-secret.md)
CALL app.config.register_single_reference(
  'CONSUMER_EXTERNAL_ACCESS', 'ADD',
  SYSTEM$REFERENCE('EXTERNAL ACCESS INTEGRATION', 'my_eai', 'PERSISTENT', 'USAGE'));

CALL app.config.register_single_reference(
  'CONSUMER_SECRET', 'ADD',
  SYSTEM$REFERENCE('SECRET', 'db.schema.my_secret', 'PERSISTENT', 'USAGE', 'READ'));
```

The privileges in `SYSTEM$REFERENCE` must match what is declared in the manifest `references` block. Include this binding command in the app's README.
