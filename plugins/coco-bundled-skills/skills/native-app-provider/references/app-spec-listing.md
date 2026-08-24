---
name: app-spec-listing
description: "Reference for configuring Listing (data sharing) app specifications in a Snowflake Native App."
parent_skill: native-app-provider
---

# App Specification: Listing (Data Sharing)

Loaded by `request-account-privilege` when `CREATE SHARE` or `CREATE LISTING` is detected.

## When This Applies

The app needs to share data back with the provider or with third-party Snowflake accounts. Common use cases:

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

## Required Objects

### 1. Manifest privileges

All three privileges are required. `CREATE DATABASE` is needed because apps can only share data from databases they create:

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

### 2. Share (in setup script)

Create the share and grant database objects to it:

```sql
CREATE SHARE IF NOT EXISTS compliance_share;

GRANT USAGE ON DATABASE app_created_db TO SHARE compliance_share;
GRANT USAGE ON SCHEMA app_created_db.reporting TO SHARE compliance_share;
GRANT SELECT ON TABLE app_created_db.reporting.metrics TO SHARE compliance_share;
```

**Constraints on shares:**
- Apps can only share data from databases **created by the app** (the app must be the owner)
- Apps can grant privileges on objects directly or grant a database role to the share
- Apps **cannot** directly add target accounts to the share (this is controlled through the app specification)

### 3. External listing (in setup script)

```sql
CREATE EXTERNAL LISTING IF NOT EXISTS compliance_listing
  SHARE compliance_share
  AS $$
    title: "Compliance Data Share"
    subtitle: "Regulatory compliance reporting data"
    description: "Share compliance and audit data with authorized accounts"
    listing_terms:
      type: "OFFLINE"
  $$
  PUBLISH = FALSE
  REVIEW = FALSE;
```

**Constraints on listings:**
- Apps can only attach **shares** to a listing (not application packages)
- Apps **cannot** directly add target accounts or auto-fulfillment config to the listing
- The listing manifest only allows: `title`, `subtitle`, `description`, and `listing_terms`
- All new listings must be created **unpublished**: `PUBLISH = FALSE` and `REVIEW = FALSE`

### 4. App specification

```sql
ALTER APPLICATION SET SPECIFICATION shareback_spec
  TYPE = LISTING
  LABEL = 'Compliance Data Sharing'
  DESCRIPTION = 'Share compliance data with provider for regulatory reporting'
  TARGET_ACCOUNTS = 'ProviderOrg.ProviderAccount,AuditorOrg.AuditorAccount'
  LISTING = compliance_listing
  AUTO_FULFILLMENT_REFRESH_SCHEDULE = '720 MINUTE';
```

### App specification properties

| Property | Required | Description |
|----------|----------|-------------|
| `TYPE` | Yes | Must be `LISTING` |
| `LABEL` | Yes | Short display name shown to consumer |
| `DESCRIPTION` | Yes | Explains why the app shares this data |
| `TARGET_ACCOUNTS` | Yes | Comma-separated list in `OrgName.AccountName` format |
| `LISTING` | Yes | Identifier of the listing object created by the app |
| `AUTO_FULFILLMENT_REFRESH_SCHEDULE` | For cross-region | Refresh schedule: `'<num> MINUTE'` (min 10, max 11520) or `'USING CRON <expr> <tz>'` |

## Critical Validation Rules

1. **Listing must exist first**: The app specification must reference an existing listing. Create the share and listing before the app specification.
2. **One spec per listing**: Each listing can only have one associated app specification. An app cannot create multiple specs for the same listing.
3. **Listing name is immutable**: After the app specification is set, the listing name in the spec cannot be changed.
4. **TARGET_ACCOUNTS format**: Each account must use `OrgName.AccountName` format (e.g., `'ProviderOrg.ProviderAccount'`).
5. **All three privileges required**: The app needs `CREATE DATABASE`, `CREATE SHARE`, and `CREATE LISTING` in the manifest.
6. **Updating target accounts**: Changing `TARGET_ACCOUNTS` creates a new pending request for consumer approval.

## Consumer Approval Behavior

**On approval:**
- Snowflake automatically adds target accounts to the listing
- Configures auto-fulfillment refresh schedule if specified
- Listing becomes visible to target accounts
- Data can be queried from approved accounts

**On rejection:**
- All target accounts are removed (except the current account where the app is installed)
- Auto-fulfillment is disabled
- Data can no longer be queried by target accounts (other than current account)

## Validation After Approval

Apps can check if the specification was approved:

```sql
-- Check if the app specification is approved
-- Inside the app context (e.g., in a setup script or stored procedure):
SHOW APPROVED SPECIFICATIONS;
-- From outside, specify the app name:
-- SHOW APPROVED SPECIFICATIONS IN APPLICATION <app_name>;

-- Validate the listing configuration
DESC LISTING compliance_listing;
```

## Best Practices

- **Share integrity**: Snowflake does not prevent consumers from modifying shares created by the app. Implement measures to protect the integrity of shared data.
- **Error handling**: Implement handling for cases where the app specification is declined or not yet approved.
- **Cross-region costs**: Auto-fulfillment costs are billed to the consumer. Choose refresh schedules that balance data freshness with cost.
- **Listing metadata**: Customize listing title and description based on consumer info to distinguish data sources.

## Workflow Steps

When the `request-account-privilege` skill detects `CREATE SHARE` or `CREATE LISTING`:

1. **Ensure both privileges** are in the manifest (`CREATE SHARE` and `CREATE LISTING`)
2. **Check** if a share already exists in the setup script
   - If not, ask the user what data the app needs to share and with whom
   - Generate the `CREATE SHARE` and `GRANT` statements
3. **Check** if an external listing already exists
   - If not, generate the `CREATE EXTERNAL LISTING` statement (unpublished)
4. **Ask** the user for target account(s) in `OrgName.AccountName` format
5. **Ask** if cross-region sharing is needed; if yes, determine refresh schedule
6. **Check** if an app specification already exists
   - If not, generate the `ALTER APPLICATION SET SPECIFICATION` statement
   - Add it to the setup script (after share and listing creation)
7. **Validate** that the listing referenced in the spec exists in the setup script
8. **Inform** the user that the consumer must approve this specification before data sharing works

## Output

- Share, listing, and app specification SQL added to the setup script
- Manifest updated with both `CREATE SHARE` and `CREATE LISTING` privileges
- User informed about consumer approval requirement and cross-region considerations
