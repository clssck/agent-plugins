---
name: request-listing
description: "Configure a Listing (data sharing) app specification for a Snowflake Native App. Handles the CREATE DATABASE, CREATE SHARE, and CREATE LISTING privileges, share creation, external listing setup, and app specification generation for sharing data back with provider or third-party accounts. Triggers: listing, share data back, CREATE SHARE, CREATE LISTING, data sharing, compliance reporting, telemetry, shareback, target accounts, cross-region sharing, auto-fulfillment."
parent_skill: native-app-provider
---

# Listing Configuration (Data Sharing)

> **⚠️ MANDATORY**: If your system prompt mentions Snowsight, load [`../references/native-apps-snowsight.md`](../references/native-apps-snowsight.md) before doing anything else.

## When to Load

From the root `native-app-provider` skill when the user needs to configure a Snowflake Native App to share data back with the provider or with third-party Snowflake accounts.

This skill can also be loaded from `request-account-privilege/SKILL.md` when `CREATE SHARE` or `CREATE LISTING` is detected as a Tier 2 privilege.

## Prerequisites

- A project directory with `manifest.yml` and a setup script (typically `scripts/setup.sql`)
- `CREATE DATABASE`, `CREATE SHARE`, and `CREATE LISTING` privileges should be declared in `manifest.yml`. If not yet configured, load `request-account-privilege/SKILL.md` first to add them to the manifest. `CREATE DATABASE` is required because apps can only share data from databases they create.

## Key Concept

A **Listing** allows a Snowflake Native App to share data back with the provider or with third-party accounts. Common use cases:

- Compliance reporting (audit logs to regulatory accounts)
- Telemetry and analytics (usage metrics back to provider)
- Data preprocessing (transformed data to partner accounts)
- Support and troubleshooting (diagnostic data to support teams)

This requires:
1. `CREATE DATABASE`, `CREATE SHARE`, and `CREATE LISTING` privileges in the manifest
2. A **share** with database objects granted to it
3. An **external listing** attached to the share
4. An **app specification** of type `LISTING` declaring target accounts

The privileges are auto-granted at install, but data is not shared until the consumer approves the app specification.

## Workflow

### Step 1: Gather Project Files

**Ask** the user:

```
To configure data sharing, I need:
1. **Project directory**: Where are your app files? (e.g., /Users/you/projects/my_app)
2. **Application package name**: What is the application package name? (e.g., MY_APP_PKG)
```

If the user has already provided the project directory in a prior skill, skip the prompt.

**Locate files:**
- Read `manifest.yml` from the project root
- Determine the setup script path from `artifacts.setup_script` in the manifest (default: `setup.sql`)
- Read the setup script

**STOP** if either file is missing: tell the user which file is missing and suggest loading `setup-app/SKILL.md` to create it.

### Step 2: Collect Sharing Details

**Ask** the user:

```
What data does the app need to share, and with whom?

1. **What data**: Which tables/views will be shared? (must be from databases created by the app)
2. **Target accounts**: Who receives the data? (in OrgName.AccountName format, e.g., ProviderOrg.ProviderAccount)
3. **Purpose**: Why is this data being shared? (e.g., compliance, telemetry, partner data)
4. **Cross-region?**: Will target accounts be in different regions?
   If yes: what refresh schedule? (minimum 10 minutes, maximum 11520 minutes / 8 days)
```

### Step 3: Add Manifest Privileges

Both sharing privileges are always required together. Since apps can only share data from databases **created by the app**, the app also needs `CREATE DATABASE` to create the database that holds the shared objects. Add all three to the `privileges` block in `manifest.yml`:

```yaml
manifest_version: 2

privileges:
  - CREATE DATABASE:
      description: "Create a database to store <data_type> data for sharing"
  - CREATE SHARE:
      description: "Create a share for sharing <data_type> data with <recipient>"
  - CREATE LISTING:
      description: "Create a listing for cross-region sharing of <data_type> data"
```

If `CREATE DATABASE` is already in the manifest, skip adding it. If `manifest_version` is not `2`, update it (warn the user this requires a major version upgrade, not a patch).

### Step 4: Generate Setup Script SQL

> **REQUIRED**: You MUST read the file `../references/app-spec-listing.md` before generating any SQL. It contains the exact syntax templates, constraints, and property tables. Do NOT generate SQL from memory.

**Read `../references/app-spec-listing.md`** and follow its SQL templates to generate:

1. **Share** — `CREATE SHARE IF NOT EXISTS` with `GRANT` statements for the shared database objects
2. **External listing** — `CREATE EXTERNAL LISTING IF NOT EXISTS` attached to the share, with `PUBLISH = FALSE` and `REVIEW = FALSE`
3. **App specification** — `ALTER APPLICATION SET SPECIFICATION` with `TYPE = LISTING`, target accounts, listing reference, and auto-fulfillment schedule if cross-region

The reference doc contains the full SQL templates, constraints on each object, and the app specification property table.

### Step 5: Validate

- [ ] `manifest_version` is `2`
- [ ] `CREATE DATABASE`, `CREATE SHARE`, and `CREATE LISTING` privileges are in the manifest with descriptions
- [ ] Share exists in setup script with `GRANT` statements for the shared objects
- [ ] External listing exists in setup script with `PUBLISH = FALSE` and `REVIEW = FALSE`
- [ ] App specification exists with `TYPE = LISTING`
- [ ] `TARGET_ACCOUNTS` uses `OrgName.AccountName` format
- [ ] `LISTING` in the app specification references the listing created in the setup script
- [ ] If cross-region: `AUTO_FULFILLMENT_REFRESH_SCHEDULE` is set (min 10, max 11520 minutes)
- [ ] Listing must exist before the app specification (create share and listing first)
- [ ] Each listing can only have one associated app specification
- [ ] Inform user: data is not shared until the consumer approves the app specification
- [ ] Inform user: changing `TARGET_ACCOUNTS` later creates a new pending approval request

## Best Practices

- **Share integrity**: Snowflake does not prevent consumers from modifying shares created by the app. Implement measures to protect the integrity of shared data.
- **Error handling**: Implement handling for cases where the app specification is declined or not yet approved.
- **Cross-region costs**: Auto-fulfillment costs are billed to the consumer. Choose refresh schedules that balance data freshness with cost.
- **Listing metadata**: Customize listing title and description based on consumer info to distinguish data sources.

## Stopping Points

- Step 1: If files are missing
- Step 2: While collecting sharing details from user
- Step 5: Present validation results

## Output

- Updated `manifest.yml` with `CREATE DATABASE`, `CREATE SHARE`, and `CREATE LISTING` privileges
- Share, external listing, and app specification SQL added to setup script
- User informed about consumer approval requirement and cross-region considerations
