---
name: request-account-privilege
description: "Configure the account-level privileges a Snowflake Native App requests from consumers. Collects user intent, updates the manifest file, and handles auto-granted vs manual-grant privileges. Always enforces manifest_version: 2. Triggers: privilege, auto-grant, manifest privileges, app permissions, privilege configuration, consumer privileges, missing privileges, request privileges, configure privileges."
parent_skill: native-app-provider
---

# Privilege Request Configuration

> **⚠️ MANDATORY**: If your system prompt mentions Snowsight, load [`../references/native-apps-snowsight.md`](../references/native-apps-snowsight.md) before doing anything else.

## When to Load

From the root `native-app-provider` skill when the user wants to configure the account-level privileges an app requests from consumers.

This is distinct from **object references** (accessing consumer-owned tables, views, warehouses, etc.) — for that, load `request-object-access/SKILL.md`.

## Prerequisites

- A project directory with `manifest.yml`

## Privilege Classification Reference

All account-level privileges fall into one of three tiers:

### Tier 1: Auto-granted (no extra consumer approval)

These are automatically granted to the app at install/upgrade when declared in the manifest `privileges` block with `manifest_version: 2`.

| Privilege | Typical Use Case |
|-----------|-----------------|
| `CREATE WAREHOUSE` | App creates/manages its own warehouse |
| `CREATE COMPUTE POOL` | SPCS: app creates compute pools |
| `CREATE DATABASE` | App creates databases in consumer account |
| `BIND SERVICE ENDPOINT` | SPCS: expose service endpoints externally |
| `EXECUTE TASK` | App creates and runs tasks |
| `EXECUTE MANAGED TASK` | App runs serverless tasks |

### Tier 2: Auto-granted + App Specification required

The privilege itself is auto-granted, but the consumer must **also approve an app specification** before the external connection or data sharing actually works.

| Privilege | Requires App Spec For | App Spec Type |
|-----------|----------------------|---------------|
| `CREATE EXTERNAL ACCESS INTEGRATION` | Connecting to external endpoints | `EXTERNAL_ACCESS` |
| `CREATE SECURITY INTEGRATION` | OAuth / third-party auth | `SECURITY_INTEGRATION` |
| `CREATE SHARE` | Sharing data back to provider / third parties | `LISTING` |
| `CREATE LISTING` | Cross-region data sharing via listings | `LISTING` |

**Important**: Do NOT use `grant_callback` for Tier 1 or Tier 2 privileges — they are auto-granted via `manifest_version: 2` and do not need a callback.

### Tier 3: NOT auto-granted (consumer must manually grant)

These **cannot** be auto-granted. The consumer must explicitly grant them using SQL or Snowsight after installation.

| Privilege | Note |
|-----------|------|
| `MANAGE WAREHOUSES` | Control over all warehouses in account |
| `IMPORTED PRIVILEGES ON SNOWFLAKE DB` | Access to SNOWFLAKE shared database |
| `READ SESSION` | Read session-level parameters |
| `EXECUTE ALERT` | Create and execute alerts |

## Workflow

### Step 1: Gather Project Files

**Ask** the user for the following (skip any items already known from a prior skill):

```
To configure account privileges, I need:
1. **Project directory**: Where are your app files? (e.g., /Users/you/projects/my_app)
2. **Application package name**: What is the application package name? (e.g., MY_APP_PKG)
```

Read `manifest.yml` from the project root.

**STOP** if the manifest is missing: suggest loading `setup-app/SKILL.md` to create it.

### Step 2: Validate Manifest Version

If `manifest_version` is not `2`, warn the user that auto-granting requires version 2 and that changing it requires a major version upgrade (not a patch). **STOP** for approval before updating.

### Step 3: Collect Privileges and Analyze

**Best Practice — Principle of Least Privilege**: Apps should only request the specific privileges they actually need. Do not blanket-request all privileges in a tier. Unnecessary privileges increase consumer friction (Tier 2 requires app spec approval, Tier 3 requires manual grant), may slow marketplace listing review, and erode consumer trust.

Read existing privileges from the manifest. Present the privilege tiers (Tier 1, 2, 3) and ask the user which privileges the app needs and why.

Compare against existing privileges and present:
- **Already configured** — no changes needed
- **New to add** — with tier and any additional actions (Tier 2 needs app spec, Tier 3 needs manual grant)

**STOP**: Wait for user to confirm which privileges to add.

### Step 4: Update Manifest

For each approved privilege, add it to the `privileges` block in `manifest.yml`:

```yaml
manifest_version: 2

privileges:
  - CREATE WAREHOUSE:
      description: "Required to create a warehouse for query processing"
  - EXECUTE TASK:
      description: "Required to create and run scheduled tasks"
```

**Rules:**
- Always use `manifest_version: 2`
- Each privilege must have a meaningful `description` explaining why the app needs it
- Privilege names must be in UPPER CASE
- Preserve existing privileges and their descriptions (don't remove anything without user approval)
- Privileges cannot be changed in a patch release — only in major version upgrades

### Step 5: Inform Next Steps

After updating the manifest, inform the user:

- **Tier 2 privileges** require additional app specification configuration:

| Privilege | Next Step |
|-----------|-----------|
| `CREATE EXTERNAL ACCESS INTEGRATION` | Configure via `request-external-access-integration` skill |
| `CREATE SECURITY INTEGRATION` | Configure via `request-security-integration` skill |
| `CREATE SHARE` / `CREATE LISTING` | Configure via `request-listing` skill |

- **Tier 3 privileges** cannot be auto-granted — the consumer must grant them manually. Suggest using a `grant_callback` in the manifest or documenting the requirement.

### Step 6: Validate

Re-read the updated manifest. Confirm:
- [ ] `manifest_version` is `2`
- [ ] All approved privileges are in the `privileges` block with descriptions
- [ ] No duplicate privileges
- [ ] Privilege names are UPPER CASE

Present final summary to user.

## Upgrade Considerations

- Adding new privileges to the manifest requires a **new version** (not a patch)
- Changing `manifest_version` from `1` to `2` requires a major version upgrade
- Removing a privilege from the manifest revokes it during upgrade
- The setup script of a new version runs with both old and new privileges during upgrade; excess privileges are revoked after upgrade completes