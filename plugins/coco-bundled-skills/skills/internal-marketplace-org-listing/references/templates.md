# Quick Reference Templates

Copy-paste templates for common organizational listing scenarios.

---

## Template: Share Specific Tables and Create Listing (All Accounts)

**Use when**: Sharing to all internal accounts (approver_contact NOT needed)

```sql
-- Step 1: Create share (grant in correct order!)
CREATE SHARE my_data_share COMMENT = 'Description of shared data';
GRANT USAGE ON DATABASE MY_DB TO SHARE my_data_share;        -- FIRST
GRANT USAGE ON SCHEMA MY_DB.MY_SCHEMA TO SHARE my_data_share; -- SECOND
GRANT SELECT ON TABLE MY_DB.MY_SCHEMA.TABLE_1 TO SHARE my_data_share; -- LAST
GRANT SELECT ON TABLE MY_DB.MY_SCHEMA.TABLE_2 TO SHARE my_data_share;

-- Verify share contents
DESCRIBE SHARE my_data_share;

-- Step 2: Create listing (use CREATE ORGANIZATION LISTING)
CREATE ORGANIZATION LISTING my_listing
  SHARE my_data_share AS
$$
title: "My Data Product"
description: "Description of the data product"
organization_targets:
  discovery:
    - all_internal_accounts: true
  access:
    - all_internal_accounts: true
support_contact: "support@company.com"
# approver_contact NOT required for all_internal_accounts
locations:
  access_regions:
    - name: "PUBLIC.AWS_US_WEST_2"
$$;

-- Note: Organizational listings are automatically published upon creation
-- View at: https://app.snowflake.com/#/provider-studio/listings/MY_LISTING
```

---

## Template: Share All Tables in Schema (All Accounts)

**Use when**: Sharing entire schema to all internal accounts

```sql
-- Step 1: Create share with all tables (correct order!)
CREATE SHARE schema_share COMMENT = 'All tables in schema';
GRANT USAGE ON DATABASE MY_DB TO SHARE schema_share;         -- FIRST
GRANT USAGE ON SCHEMA MY_DB.PUBLIC TO SHARE schema_share;    -- SECOND
GRANT SELECT ON ALL TABLES IN SCHEMA MY_DB.PUBLIC TO SHARE schema_share; -- LAST
GRANT SELECT ON ALL VIEWS IN SCHEMA MY_DB.PUBLIC TO SHARE schema_share;

-- Verify share contents
DESCRIBE SHARE schema_share;

-- Step 2: Create listing
CREATE ORGANIZATION LISTING schema_listing
  SHARE schema_share AS
$$
title: "Complete Schema Dataset"
organization_targets:
  discovery:
    - all_internal_accounts: true
  access:
    - all_internal_accounts: true
support_contact: "data-team@company.com"
# approver_contact NOT required for all_internal_accounts
locations:
  access_regions:
    - name: "PUBLIC.AWS_US_WEST_2"
$$;

-- View at: https://app.snowflake.com/#/provider-studio/listings/SCHEMA_LISTING
```

---

## Template: Restricted Access Listing (Specific Accounts)

**Use when**: Limiting discovery or access to specific accounts (approver_contact may be required)

```sql
CREATE ORGANIZATION LISTING restricted_listing
  SHARE my_share AS
$$
title: "Restricted Data Product"
description: "Access limited to specific teams"
organization_targets:
  discovery:
    - all_internal_accounts: true  # All can see, but only specific can access
  access:
    - account: 'team_a_account'
    - account: 'team_b_account'
      roles: ['analyst', 'manager']
support_contact: "data-team@company.com"
# approver_contact optional here since discovery is all_internal_accounts
request_approval_type: "REQUEST_AND_APPROVE_IN_SNOWFLAKE"
locations:
  access_regions:
    - name: "PUBLIC.AWS_US_WEST_2"
$$;

-- View at: https://app.snowflake.com/#/provider-studio/listings/RESTRICTED_LISTING
```

---

## Template: Targeted Discovery Listing (Approver Required)

**Use when**: Limiting DISCOVERY to specific accounts (approver_contact IS REQUIRED)

```sql
CREATE ORGANIZATION LISTING targeted_listing
  SHARE my_share AS
$$
title: "Targeted Data Product"
description: "Only visible to specific teams"
organization_targets:
  discovery:
    - account: 'finance'      # Specific accounts in discovery
    - account: 'analytics'
  access:
    - account: 'finance'
support_contact: "data-team@company.com"
approver_contact: "data-governance@company.com"  # REQUIRED for specific discovery
request_approval_type: "REQUEST_AND_APPROVE_IN_SNOWFLAKE"
locations:
  access_regions:
    - name: "PUBLIC.AWS_US_WEST_2"
$$;
```

---

## Template: Multi-Region Listing with Auto-Fulfillment

```sql
CREATE ORGANIZATION LISTING global_listing
  SHARE my_share AS
$$
title: "Global Data Product"
description: "Available across all regions"
organization_targets:
  discovery:
    - all_internal_accounts: true
  access:
    - all_internal_accounts: true
support_contact: "data-team@company.com"
approver_contact: "governance@company.com"
locations:
  access_regions:
    - name: "ALL"
auto_fulfillment:
  refresh_type: "SUB_DATABASE"
  refresh_schedule: "60 MINUTE"
$$;
```

---

## Template: Share Multiple Schemas

```sql
CREATE SHARE multi_schema_share COMMENT = 'Multiple schemas';

GRANT USAGE ON DATABASE MY_DB TO SHARE multi_schema_share;

-- Schema 1
GRANT USAGE ON SCHEMA MY_DB.SCHEMA_1 TO SHARE multi_schema_share;
GRANT SELECT ON ALL TABLES IN SCHEMA MY_DB.SCHEMA_1 TO SHARE multi_schema_share;

-- Schema 2
GRANT USAGE ON SCHEMA MY_DB.SCHEMA_2 TO SHARE multi_schema_share;
GRANT SELECT ON ALL TABLES IN SCHEMA MY_DB.SCHEMA_2 TO SHARE multi_schema_share;

-- Verify
DESCRIBE SHARE multi_schema_share;
```

---

## Template: Share Views (for filtered/secure access)

```sql
CREATE SHARE secure_views_share COMMENT = 'Anonymized views for analytics';

GRANT USAGE ON DATABASE ANALYTICS_DB TO SHARE secure_views_share;
GRANT USAGE ON SCHEMA ANALYTICS_DB.CURATED TO SHARE secure_views_share;

-- Grant SELECT on views (same syntax as tables)
GRANT SELECT ON VIEW ANALYTICS_DB.CURATED.CUSTOMER_SUMMARY TO SHARE secure_views_share;
GRANT SELECT ON VIEW ANALYTICS_DB.CURATED.REVENUE_BY_REGION TO SHARE secure_views_share;
```

---

## Template: Share Functions

```sql
CREATE SHARE utility_functions_share COMMENT = 'Shared utility functions';

GRANT USAGE ON DATABASE UTILS_DB TO SHARE utility_functions_share;
GRANT USAGE ON SCHEMA UTILS_DB.FUNCTIONS TO SHARE utility_functions_share;

-- Functions require USAGE privilege (not SELECT)
GRANT USAGE ON FUNCTION UTILS_DB.FUNCTIONS.PARSE_JSON(VARCHAR) TO SHARE utility_functions_share;
GRANT USAGE ON FUNCTION UTILS_DB.FUNCTIONS.CALCULATE_TAX(NUMBER, VARCHAR) TO SHARE utility_functions_share;
```

---

## Template: Share Dynamic Tables

```sql
CREATE SHARE dynamic_tables_share COMMENT = 'Dynamic tables share';

GRANT USAGE ON DATABASE MY_DB TO SHARE dynamic_tables_share;
GRANT USAGE ON SCHEMA MY_DB.DYNAMIC TO SHARE dynamic_tables_share;

-- Dynamic tables use SELECT privilege (like regular tables)
GRANT SELECT ON DYNAMIC TABLE MY_DB.DYNAMIC.AGGREGATED_SALES TO SHARE dynamic_tables_share;
```

---

## Common Management Commands

### Update a Listing Manifest

```sql
ALTER LISTING my_listing SET AS $$
title: "Updated Title"
description: "Updated description with new information"
organization_targets:
  discovery:
    - all_internal_accounts: true
  access:
    - all_internal_accounts: true
support_contact: "new-support@company.com"
approver_contact: "new-approver@company.com"
locations:
  access_regions:
    - name: "PUBLIC.AWS_US_WEST_2"
$$;
```

### Add Objects to Existing Share

```sql
GRANT SELECT ON TABLE MY_DB.MY_SCHEMA.NEW_TABLE TO SHARE my_share;
GRANT SELECT ON VIEW MY_DB.MY_SCHEMA.NEW_VIEW TO SHARE my_share;

-- Verify
DESCRIBE SHARE my_share;
```

### Remove Objects from Share

```sql
REVOKE SELECT ON TABLE MY_DB.MY_SCHEMA.OLD_TABLE FROM SHARE my_share;
```

### Unpublish/Delete Listing

```sql
-- Temporarily hide
ALTER LISTING my_listing SET STATE = UNPUBLISHED;

-- Permanently remove
DROP LISTING my_listing;
DROP SHARE my_share;  -- Optional: also remove share
```

### View Listing Details

```sql
SHOW LISTINGS;
DESCRIBE LISTING my_listing;
SELECT SYSTEM$GET_LISTING_MANIFEST('my_listing');
```

