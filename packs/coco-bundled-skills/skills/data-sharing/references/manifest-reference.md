# Organizational Listing Manifest Reference

This reference contains detailed manifest field documentation, configuration examples, and data attributes.

---

## Manifest Field Reference

### Required Fields

| Field | Description | Notes |
|-------|-------------|-------|
| `title` | Listing title | Max 110 characters |
| `organization_targets` | Who can discover/access | Must include `discovery` or `access` |
| `support_contact` | Support email | Required when `discovery` is specified |
| `approver_contact` | Approver email | **Conditional** - see below |
| `locations.access_regions` | Regional availability | **Optional** - omit for all regions, or specify to restrict |

### Approver Contact Logic

**⚠️ Important**: `approver_contact` is NOT always required:

| Discovery Setting | Access Setting | `approver_contact` |
|-------------------|----------------|-------------------|
| `all_internal_accounts: true` | `all_internal_accounts: true` | **OPTIONAL** - can omit |
| `all_internal_accounts: true` | Specific accounts | **OPTIONAL** - can omit |
| Specific accounts | Any | **REQUIRED** - must include |

```yaml
# Example: All accounts - approver_contact OPTIONAL
organization_targets:
  discovery:
    - all_internal_accounts: true
  access:
    - all_internal_accounts: true
support_contact: "support@company.com"
# approver_contact not needed!

# Example: Specific accounts in discovery - approver_contact REQUIRED
organization_targets:
  discovery:
    - account: 'finance'
    - account: 'analytics'
  access:
    - account: 'finance'
support_contact: "support@company.com"
approver_contact: "approver@company.com"  # REQUIRED
```

### Optional Fields

| Field | Description |
|-------|-------------|
| `description` | Detailed description (max 7500 chars, Markdown supported) |
| `organization_profile` | Custom profile or "INTERNAL" (default) |
| `resources` | Documentation URL and media links |
| `listing_terms` | Terms of service configuration |
| `data_dictionary` | Schema documentation for discoverability |
| `usage_examples` | Sample SQL queries |
| `data_attributes` | Refresh rate, geography, categories, time period |
| `auto_fulfillment` | Cross-region replication settings (required if targeting multiple regions) |
| `request_approval_type` | How access requests are handled |

---

## Organization Targets Configuration

### All internal accounts can discover AND access

```yaml
organization_targets:
  discovery:
    - all_internal_accounts: true
  access:
    - all_internal_accounts: true
```

### All can discover, access must be requested (no automatic access)

```yaml
organization_targets:
  discovery:
    - all_internal_accounts: true
  # NO access field — everyone must request access
```

### All can discover, specific accounts can access

```yaml
organization_targets:
  discovery:
    - all_internal_accounts: true
  access:
    - account: 'analytics_account'
    - account: 'reporting_account'
```

### Specific accounts with role restrictions

```yaml
organization_targets:
  discovery:
    - all_internal_accounts: true
  access:
    - account: 'finance_account'
      roles: ['analyst', 'manager']
    - account: 'hr_account'
      roles: ['hr_admin']
```

### Restricted discovery AND access

```yaml
organization_targets:
  discovery:
    - account: 'analytics_account'
    - account: 'finance_account'
  access:
    - account: 'analytics_account'
```

---

## Locations Configuration

The `locations` field specifies which regions can access the listing.

**⚠️ When to include `locations`**:
- **`all_internal_accounts: true`** → Use `access_regions: ALL` (requires `auto_fulfillment`)
- **Specific accounts** → Include `locations` with their specific regions

### All regions (use ALL)

When using `all_internal_accounts: true`, specify `ALL` for regions:
```yaml
organization_targets:
  discovery:
    - all_internal_accounts: true
  access:
    - all_internal_accounts: true

locations:
  access_regions:
    - name: "ALL"
auto_fulfillment:
  refresh_type: "SUB_DATABASE"
  refresh_schedule: "10 MINUTE"
```

### Specific region only

```yaml
locations:
  access_regions:
    - name: "PUBLIC.AWS_US_WEST_2"
```

### Multiple specific regions (requires auto_fulfillment)

```yaml
locations:
  access_regions:
    - name: "PUBLIC.AWS_US_WEST_2"
    - name: "PUBLIC.AWS_US_EAST_1"
auto_fulfillment:
  refresh_type: "SUB_DATABASE"
  refresh_schedule: "60 MINUTE"
```

### All regions (requires auto_fulfillment)

```yaml
locations:
  access_regions:
    - name: "ALL"
auto_fulfillment:
  refresh_type: "SUB_DATABASE"
  refresh_schedule: "60 MINUTE"
```

---

## Auto-Fulfillment Configuration

Required when target accounts are in different regions.

### Interval-based refresh

```yaml
auto_fulfillment:
  refresh_schedule: "60 MINUTE"  # min 10, max 11520 (8 days)
  refresh_type: "SUB_DATABASE"
```

### CRON-based refresh

Format: `USING CRON <minute> <hour> <day_of_month> <month> <day_of_week> <IANA_timezone>`.

```yaml
auto_fulfillment:
  refresh_schedule: "USING CRON 0 6 * * * America/New_York"
  refresh_type: "SUB_DATABASE"
```

To **set** a cron schedule on a new listing, include this in the `CREATE ORGANIZATION LISTING ... AS $$...$$` manifest. To **update** the schedule on an existing listing, use the full-manifest `ALTER LISTING <name> AS $$...$$ PUBLISH = TRUE;` form — see `sql-syntax.md` → "Update refresh schedule on existing listing". Requires `MANAGE LISTING AUTO FULFILLMENT` on ACCOUNT. Reference: [cron refresh docs](https://docs.snowflake.com/en/collaboration/provider-listings-auto-fulfillment-configure-cron-refresh-schedule).

**Invalid forms** (will fail): `ALTER LISTING ... SET refresh_schedule = ...`, `ALTER DATABASE ... SET refresh_schedule = ...`.

### For Native Apps

```yaml
auto_fulfillment:
  refresh_type: "SUB_DATABASE_WITH_REFERENCE_USAGE"
```

---

## Data Attributes Reference

**Note**: This section covers attributes for **organizational listings** (Internal Marketplace). The `categories` field is NOT applicable to organizational listings—it's only used for private/Marketplace listings.

```yaml
data_attributes:
  # How often data is refreshed
  refresh_rate: "DAILY"  
  # Options: CONTINUOUSLY, HOURLY, DAILY, WEEKLY, MONTHLY, QUARTERLY, ANNUALLY, STATIC
  
  geography:
    # Geographic granularity of data
    granularity: "COUNTRY"  
    # Options: CONTINENT, COUNTRY, REGION, STATE_PROVINCE, ZIP, OTHER
    
    # Geographic coverage
    geo_coverage:
      - "GLOBAL"
      # Or specific: "NORTH_AMERICA", "EUROPE", "ASIA_PACIFIC", etc.
  
  # Time period of data
  time_period:
    time_frame: "TIME_WINDOW"  
    # Options: TIME_WINDOW, HISTORICAL, POINT_IN_TIME
    start_date: "2020-01-01"
    end_date: "2024-12-31"  # optional

  # ⚠️ DO NOT include 'categories' - not applicable for organizational listings
```

---

## Data Dictionary Configuration

**Always include `data_dictionary`** to improve listing discoverability. You can feature up to **5 objects**.

**Documentation**: [Data Dictionary Reference](https://docs.snowflake.com/en/user-guide/collaboration/listings/organizational/org-listing-manifest-reference#data-dictionary)

**⚠️ Semantic Views Note**: 
- Semantic views CAN be shared in organizational listings (they work like regular views)
- However, semantic views should generally NOT be featured in `data_dictionary` 
- Feature tables and regular views that consumers will query directly
- Semantic views are typically used for AI/semantic layer purposes, not direct querying

### Auto-Selection Guidelines

When creating a listing, automatically select up to **5 most relevant objects** to feature:

1. **Query the share contents**:
   ```sql
   DESCRIBE SHARE <share_name>;
   ```

2. **Prioritize objects by relevance**:
   - Main fact tables (transactions, events, orders)
   - Key dimension tables (customers, products, locations)
   - Commonly queried views
   - Aggregated/summary tables

3. **Exclude from featuring**:
   - Staging tables
   - Internal/system tables
   - Rarely used lookup tables

### PII Detection and Marking

**Always scan featured objects for PII** and document in the listing description.

#### Step 1: Check column names for PII patterns

```sql
DESCRIBE TABLE <database>.<schema>.<table>;
```

**Common PII column patterns**:

| Category | Column Name Patterns |
|----------|---------------------|
| **Names** | `first_name`, `last_name`, `full_name`, `customer_name`, `user_name` |
| **Contact** | `email`, `phone`, `mobile`, `address`, `street`, `city`, `zip`, `postal_code` |
| **Government IDs** | `ssn`, `social_security`, `tax_id`, `passport`, `driver_license`, `national_id` |
| **Financial** | `credit_card`, `card_number`, `account_number`, `bank_account`, `routing_number` |
| **Health** | `dob`, `date_of_birth`, `birth_date`, `medical_id`, `patient_id`, `health_record` |
| **Location** | `latitude`, `longitude`, `ip_address`, `geo_location` |

#### Step 2: Check Snowflake classification tags (if available)

```sql
-- Check if table has semantic classification tags
SELECT *
FROM TABLE(INFORMATION_SCHEMA.TAG_REFERENCES('<database>.<schema>.<table>', 'TABLE'));

-- Check column-level tags
SELECT *
FROM TABLE(INFORMATION_SCHEMA.TAG_REFERENCES('<database>.<schema>.<table>', 'COLUMN'));
```

#### Step 3: Document PII in listing description

If PII is detected, add a section to the listing description:

```yaml
description: |
  # Data Product Name
  
  ## Overview
  ...
  
  ## ⚠️ PII Notice
  This data product contains the following PII fields:
  - **CUSTOMERS table**: `email`, `phone`, `address`
  - **TRANSACTIONS table**: `customer_name`
  
  Please ensure appropriate access controls and handle according to data governance policies.
```

#### Step 4: Consider recommending views for PII masking

If raw PII is present, suggest the provider create masked views:

```sql
-- Example: Create a masked view for sharing
CREATE VIEW CUSTOMERS_MASKED AS
SELECT 
  customer_id,
  CONCAT(LEFT(first_name, 1), '***') as first_name,
  CONCAT(LEFT(last_name, 1), '***') as last_name,
  CONCAT(LEFT(email, 3), '***@***.com') as email_masked,
  region,
  signup_date
FROM CUSTOMERS;
```

### Example

**⚠️ CRITICAL**: Use UNQUOTED identifiers for database, schema, and object names. Quoted identifiers cause validation errors.

```yaml
# ✅ CORRECT - unquoted identifiers
data_dictionary:
  featured:
    database: SALES_DB
    objects:
      - schema: PUBLIC
        name: TRANSACTIONS
        domain: TABLE
      - schema: PUBLIC
        name: CUSTOMERS
        domain: TABLE
      - schema: PUBLIC
        name: PRODUCTS
        domain: TABLE
      - schema: ANALYTICS
        name: DAILY_SUMMARY
        domain: VIEW
      - schema: ANALYTICS
        name: REVENUE_BY_REGION
        domain: VIEW

# ❌ WRONG - quoted identifiers cause "Object does not exist" errors
data_dictionary:
  featured:
    database: "SALES_DB"  # Don't quote!
```

### Valid domain values

- `TABLE`
- `VIEW`
- `EXTERNAL_TABLE`
- `MATERIALIZED_VIEW`
- `DYNAMIC_TABLE`
- `FUNCTION`
- `DATABASE`
- `SCHEMA`
- `COLUMN`

---

## Usage Examples Configuration

**Always include `usage_examples`** to help consumers understand how to query the data. Generate 2-3 examples.

**Documentation**: [Usage Examples Reference](https://docs.snowflake.com/en/user-guide/collaboration/listings/organizational/org-listing-manifest-reference#usage-examples)

### Auto-Generation Guidelines

When creating a listing, automatically generate **2-3 relevant usage examples**:

1. **Analyze the shared objects**:
   ```sql
   DESCRIBE SHARE <share_name>;
   -- Also check table columns:
   DESCRIBE TABLE <database>.<schema>.<table>;
   ```

2. **Deduce examples based on data type**:

   | Data Type | Example Use Cases |
   |-----------|-------------------|
   | Sales/Transactions | Daily totals, top products, revenue trends |
   | Customers | Segmentation, demographics, lifetime value |
   | Products | Inventory, pricing, category analysis |
   | Events/Logs | Time-series analysis, anomaly detection |
   | Financial | Period comparisons, ratios, forecasting |

3. **Check past queries** (if role has ACCOUNT_USAGE access):
   ```sql
   SELECT query_text, execution_time, start_time
   FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
   WHERE query_text ILIKE '%<table_name>%'
     AND execution_status = 'SUCCESS'
     AND query_type = 'SELECT'
   ORDER BY start_time DESC
   LIMIT 10;
   ```
   Use proven queries as inspiration for realistic examples.

4. **Create diverse examples covering**:
   - Basic SELECT with filters
   - Aggregations (COUNT, SUM, AVG)
   - JOINs between shared tables
   - Time-based analysis (if date columns exist)

### Example

```yaml
usage_examples:
  - title: "Daily Sales Summary"
    description: "Get total sales and transaction count by day"
    query: |
      SELECT 
        DATE(transaction_date) as sale_date,
        COUNT(*) as num_transactions,
        SUM(amount) as total_sales
      FROM TRANSACTIONS
      GROUP BY 1
      ORDER BY 1 DESC
      LIMIT 30
  
  - title: "Top 10 Customers by Revenue"
    description: "Find your highest-value customers"
    query: |
      SELECT 
        c.customer_name,
        c.region,
        SUM(t.amount) as total_revenue,
        COUNT(*) as num_orders
      FROM TRANSACTIONS t
      JOIN CUSTOMERS c ON t.customer_id = c.id
      GROUP BY 1, 2
      ORDER BY 3 DESC
      LIMIT 10
  
  - title: "Product Category Performance"
    description: "Analyze sales by product category"
    query: |
      SELECT 
        p.category,
        COUNT(DISTINCT t.transaction_id) as orders,
        SUM(t.quantity) as units_sold,
        SUM(t.amount) as revenue
      FROM TRANSACTIONS t
      JOIN PRODUCTS p ON t.product_id = p.id
      GROUP BY 1
      ORDER BY 4 DESC
```

### Field Limits

| Field | Max Length |
|-------|------------|
| `title` | 110 characters |
| `description` | 300 characters |
| `query` | 30,000 characters |

---

## Complete Manifest Example

```sql
CREATE ORGANIZATION LISTING sales_analytics_listing
  SHARE sales_data_share AS
$$
title: "Sales Analytics Dataset"
description: |
  # Sales Analytics Data Product
  
  This listing provides access to sales transaction data for internal analytics teams.
  
  ## Available Objects
  - **TRANSACTIONS**: Daily sales transactions with product and customer details
  - **CUSTOMERS**: Customer master data with demographics
  - **PRODUCTS**: Product catalog with categories and pricing
  
  ## Data Freshness
  Data is refreshed every 6 hours from source systems.
  
  ## Contact
  For questions, reach out to the Data Platform team.

organization_profile: "INTERNAL"

organization_targets:
  discovery:
    - all_internal_accounts: true
  access:
    - account: 'analytics_prod'
    - account: 'bi_team'
      roles: ['analyst', 'manager']

support_contact: "data-platform@company.com"
approver_contact: "data-governance@company.com"
request_approval_type: "REQUEST_AND_APPROVE_IN_SNOWFLAKE"

data_attributes:
  refresh_rate: "HOURLY"
  geography:
    granularity: "COUNTRY"
    geo_coverage:
      - "NORTH_AMERICA"
      - "EUROPE"
  time_period:
    time_frame: "TIME_WINDOW"
    start_date: "2020-01-01"

data_dictionary:
  featured:
    database: "SALES_DB"
    objects:
      - name: "TRANSACTIONS"
        schema: "PUBLIC"
        domain: "TABLE"
      - name: "CUSTOMERS"
        schema: "PUBLIC"
        domain: "TABLE"
      - name: "PRODUCTS"
        schema: "PUBLIC"
        domain: "TABLE"

usage_examples:
  - title: "Daily Sales Summary"
    description: "Get total sales by day"
    query: |
      SELECT 
        DATE(transaction_date) as sale_date,
        COUNT(*) as num_transactions,
        SUM(amount) as total_sales
      FROM TRANSACTIONS
      GROUP BY 1
      ORDER BY 1 DESC
  - title: "Top Customers"
    description: "Find top 10 customers by revenue"
    query: |
      SELECT 
        c.customer_name,
        SUM(t.amount) as total_revenue
      FROM TRANSACTIONS t
      JOIN CUSTOMERS c ON t.customer_id = c.id
      GROUP BY 1
      ORDER BY 2 DESC
      LIMIT 10

resources:
  documentation: "https://wiki.company.com/sales-data-docs"

listing_terms:
  type: "CUSTOM"
  link: "https://wiki.company.com/data-usage-policy"

locations:
  access_regions:
    - name: "PUBLIC.AWS_US_WEST_2"
$$;
```

---

## Access Control Requirements

### Privileges for Share Creation and Management

| Privilege | Object | Notes |
|-----------|--------|-------|
| `CREATE SHARE` | ACCOUNT | Required to create a share |
| `OWNERSHIP` or `USAGE` with grants option | DATABASE | Required to see and use the specified database |
| `OWNERSHIP` or `USAGE` with grants option | SCHEMA | Required to see the specified schema |
| `SELECT` | TABLE/VIEW | Required to query specified tables/views in the schema |

### Privileges to Create an Organizational Listing

| Privilege | Object | Notes |
|-----------|--------|-------|
| `CREATE ORGANIZATION LISTING` | ACCOUNT | To create and alter organizational listings |

### Privileges for Auto-Fulfillment Management

| Privilege | Object | Notes |
|-----------|--------|-------|
| `MANAGE LISTING AUTO FULFILLMENT` | ACCOUNT | Required to configure auto-fulfillment settings |

### Example: Grant Organizational Listing Privileges to a Role

```sql
-- Create a custom role for listing management
CREATE ROLE org_listing_admin;

-- Grant share creation privilege
GRANT CREATE SHARE ON ACCOUNT TO ROLE org_listing_admin;

-- Grant organizational listing creation privilege
GRANT CREATE ORGANIZATION LISTING ON ACCOUNT TO ROLE org_listing_admin;

-- Grant auto-fulfillment management (if needed for cross-region)
GRANT MANAGE LISTING AUTO FULFILLMENT ON ACCOUNT TO ROLE org_listing_admin;

-- Grant privileges on the database to share
GRANT USAGE ON DATABASE my_database TO ROLE org_listing_admin WITH GRANT OPTION;
GRANT USAGE ON SCHEMA my_database.my_schema TO ROLE org_listing_admin WITH GRANT OPTION;
GRANT SELECT ON ALL TABLES IN SCHEMA my_database.my_schema TO ROLE org_listing_admin;

-- Assign role to user
GRANT ROLE org_listing_admin TO USER my_user;
```

---

## Custom Attributes

Some organizations configure required custom attributes for listings. These must be provided at listing creation time or the listing cannot be published.

### Checking for required attributes

```sql
SHOW AVAILABLE INTERNAL MARKETPLACE CONFIGS;
```

- Filter to only rows where `props` = `custom_attribute_type` — ignore other config types such as `notification_integration_name`
- Check the `is_required` column — only attributes with `is_required: true` must be included in the manifest
- Optional attributes (`is_required: false`) can be omitted unless the user explicitly wants to include them
- Check whether each attribute has predefined options or is free-text:
  - **Predefined options**: use `ask_user_question` with `options` listing each option's `display_name`. Use `multiSelect: true` if multiple values are allowed. Write the `display_name` (not `value`) into the manifest.
  - **Free-text**: use `ask_user_question` with a text input and a sensible `defaultValue` if one can be inferred
- Present each attribute as its own individual question (up to 4 per `ask_user_question` call). Do not collapse all attributes into a single text box.

### Manifest syntax

```yaml
custom_attributes:
  - name: <attribute_name>
    values:
      - <value_1>
      - <value_2>  # include multiple values if the attribute accepts them
```

### Single-value example

```yaml
custom_attributes:
  - name: data_classification
    values:
      - INTERNAL
```

### Multi-value example

```yaml
custom_attributes:
  - name: approved_teams
    values:
      - analytics
      - finance
      - engineering
```

**⚠️ Omit the `custom_attributes` block entirely if no required attributes exist.**

---

## Known Limitations

- Each share can be attached to **one listing only**
- Each Native App can be attached to one or more listings
- Organizational listings with Native Apps do not support target roles for access or discovery
- Reader accounts are not supported with organizational listings
- Provider studio analytics are not supported
- You cannot specify specific regions in Snowsight (use SQL manifest instead)
- Before targeting an entire organization, check for external tenants and adjust target accounts accordingly

