# Publish a Native App Package via a Listing

Use this reference when the provider wants to make their application package available to consumers — either privately (targeted accounts) or publicly (Snowflake Marketplace).

## Prerequisites

Before creating a listing, the package must have:

1. **At least one registered version** (see `version-with-release-channel.md`)
2. **The version added to the DEFAULT release channel**
3. **A default release directive set** on the DEFAULT channel

Without these, `CREATE EXTERNAL LISTING` will fail with: *"No default release directive is found for application package"*.

```sql
-- Verify prerequisites
SHOW VERSIONS IN APPLICATION PACKAGE <PKG>;
SHOW RELEASE CHANNELS IN APPLICATION PACKAGE <PKG>;
SHOW RELEASE DIRECTIVES IN APPLICATION PACKAGE <PKG>;
```

## SQL Syntax

```sql
CREATE EXTERNAL LISTING [IF NOT EXISTS] <listing_name>
  APPLICATION PACKAGE <pkg_name>
  AS $$
  <yaml_manifest>
  $$ [PUBLISH = {TRUE|FALSE}] [REVIEW = {TRUE|FALSE}];
```

| PUBLISH | REVIEW | Behavior |
|---------|--------|----------|
| TRUE | TRUE | Submit for review, publish after approval (default) |
| FALSE | TRUE | Submit for review without auto-publishing |
| FALSE | FALSE | Save as draft (no review, no publish) |
| TRUE | FALSE | **Invalid** — cannot publish without review |

> **Private listings** (targeted to specific accounts) do NOT require review. Use the defaults (PUBLISH=TRUE, REVIEW=TRUE) — they will be published immediately without a manual review step.

## Listing Manifest — Required Fields

```yaml
title: "App Display Name"                    # max 110 chars, required
description: "What this app does"            # max 7500 chars, supports markdown, required
listing_terms:
  type: "OFFLINE"                            # STANDARD | OFFLINE | CUSTOM, required
targets:
  accounts: ["OrgName.AccountName"]          # for private listings, max 100 accounts
```

### Targets — Choose One Format

**Private listing** (specific accounts):
```yaml
targets:
  accounts: ["Org1.Account1", "Org1.Account2"]
```

**Public/Marketplace listing** (regions):
```yaml
targets:
  regions: ["ALL"]                           # or specific: ["PUBLIC.AWS_US_EAST_1"]
```

### listing_terms Types

| Type | Use Case |
|------|----------|
| `OFFLINE` | Terms handled outside Snowflake (most common for private) |
| `STANDARD` | Snowflake standard terms |
| `CUSTOM` | Custom terms — requires `link: "https://..."` field |

## Listing Manifest — Optional Fields

```yaml
subtitle: "Short tagline"                    # max 110 chars, required for Marketplace
profile: "PROVIDER_PROFILE_NAME"             # required for Marketplace listings

auto_fulfillment:                            # required for cross-region
  refresh_type: SUB_DATABASE_WITH_REFERENCE_USAGE

usage_examples:                              # max 10
  - title: "Basic query"
    description: "Shows how to use the app"
    query: "CALL app.core.hello('World');"

categories:                                  # max 1
  - "BUSINESS"

resources:
  documentation: "https://example.com/docs"
```

## Complete Examples

### Private Listing (Same Region)

```sql
CREATE EXTERNAL LISTING MY_APP_LISTING
APPLICATION PACKAGE MY_APP_PKG AS
$$
title: "My App"
description: "A native app that does something useful"
listing_terms:
  type: "OFFLINE"
targets:
  accounts: ["ConsumerOrg.ConsumerAccount"]
$$;
```

This publishes immediately to the targeted account. No review required for private.

### Private Listing (Cross-Region)

```sql
CREATE EXTERNAL LISTING MY_APP_LISTING
APPLICATION PACKAGE MY_APP_PKG AS
$$
title: "My App"
description: "A native app available cross-region"
listing_terms:
  type: "OFFLINE"
targets:
  accounts: ["ConsumerOrg.ConsumerAccount"]
auto_fulfillment:
  refresh_type: SUB_DATABASE_WITH_REFERENCE_USAGE
$$;
```

### Marketplace Listing (Public)

```sql
CREATE EXTERNAL LISTING MY_APP_MARKETPLACE
APPLICATION PACKAGE MY_APP_PKG AS
$$
title: "My App"
subtitle: "Concise subtitle"
description: "Full description with **markdown** support"
profile: "MY_PROVIDER_PROFILE"
listing_terms:
  type: "STANDARD"
targets:
  regions: ["ALL"]
auto_fulfillment:
  refresh_type: SUB_DATABASE_WITH_REFERENCE_USAGE
categories:
  - "BUSINESS"
resources:
  documentation: "https://docs.example.com"
usage_examples:
  - title: "Get started"
    description: "Run a simple verification"
    query: "CALL app.core.hello('World');"
$$;
```

## Manage Listings After Creation

```sql
-- View your listings
SHOW LISTINGS;
SHOW LISTINGS LIKE 'MY_APP%';

-- Describe a listing
DESC LISTING <listing_name>;

-- Update a listing's manifest
ALTER LISTING <listing_name> AS
$$
title: "Updated Title"
description: "Updated description"
listing_terms:
  type: "OFFLINE"
targets:
  accounts: ["ConsumerOrg.ConsumerAccount"]
$$;

-- Unpublish a listing
ALTER LISTING <listing_name> UNPUBLISH;

-- Re-publish
ALTER LISTING <listing_name> PUBLISH;

-- Drop a listing (must unpublish first)
ALTER LISTING <listing_name> UNPUBLISH;
DROP LISTING <listing_name>;
```

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `No default release directive is found` | Package has no release directive set | Register a version, add to DEFAULT channel, set release directive |
| `PUBLISH=TRUE REVIEW=FALSE` is invalid | Cannot skip review and publish | Use `PUBLISH=FALSE REVIEW=FALSE` for draft, or let both default to TRUE |
| `Property 'DISTRIBUTION' must be specified` | Wrong syntax (using `FOR APPLICATION PACKAGE` instead of `APPLICATION PACKAGE`) | Use correct syntax: `CREATE EXTERNAL LISTING <name> APPLICATION PACKAGE <pkg> AS ...` |
| Listing not visible to consumer | Replication delay for cross-region | Consumer runs `DESC AVAILABLE LISTING <global_name>` to check `is_ready_for_import` |

## Consumer Installation After Publishing

Once the listing is published, the consumer installs with:

```sql
-- Consumer finds the listing
SHOW AVAILABLE LISTINGS ->> SELECT "global_name", "title" FROM $1 WHERE "title" ILIKE '%<name>%';

-- Consumer installs
CREATE APPLICATION <app_name> FROM LISTING <global_name>;
```

## Organization Listings (Internal to Your Org)

For sharing an app package **within your organization** (same-org accounts), use `CREATE ORGANIZATION LISTING` instead of `CREATE EXTERNAL LISTING`. This publishes to the Internal Marketplace visible only to accounts in your org.

### SQL Syntax

```sql
CREATE ORGANIZATION LISTING [IF NOT EXISTS] <listing_name>
  APPLICATION PACKAGE <pkg_name>
  AS $$
  <yaml_manifest>
  $$ [PUBLISH = {TRUE|FALSE}];
```

### Required Manifest Fields (Organization Listings)

```yaml
title: "App Display Name"
description: "What this app does"
organization_profile: "INTERNAL"
organization_targets:
  access:
    - account: "CONSUMER_ACCOUNT_NAME"     # account name within the org
support_contact: "email@company.com"
approver_contact: "email@company.com"       # required when discovery targets are set
locations:
  access_regions:
    - name: "ALL"                           # or specific region
```

### Example — Organization Listing

```sql
CREATE ORGANIZATION LISTING MY_ORG_LISTING
APPLICATION PACKAGE MY_APP_PKG AS
$$
title: "My Internal App"
description: "Shared within our organization"
organization_profile: "INTERNAL"
organization_targets:
  access:
    - account: "CONSUMER_ACCOUNT"
support_contact: "team@company.com"
approver_contact: "team@company.com"
locations:
  access_regions:
    - name: "ALL"
$$;
```

### When to Use Organization vs External Listings

| Scenario | Use |
|----------|-----|
| Sharing with accounts **in your org** | `CREATE ORGANIZATION LISTING` |
| Sharing with accounts **outside your org** | `CREATE EXTERNAL LISTING` |
| Publishing to Snowflake Marketplace | `CREATE EXTERNAL LISTING` with `targets.regions` |
