# Convert to Adaptive

## Eligibility Gate

⚠️ **MANDATORY before executing any ALTER** — Run both checks and validate automatically. See `create.md` for full details.

**Check 1 — Region:**

First, query the current region:
```sql
SELECT CURRENT_REGION();
```

Then, check the Adaptive Warehouse documentation for the current list of supported regions:
```bash
cortex search docs "adaptive warehouse region availability" --max-results 1
```

Or fetch the documentation page directly:
```bash
web_fetch "https://docs.snowflake.com/en/user-guide/warehouses-adaptive#region-availability"
```

**If both documentation fetches fail:** Tell the user "Unable to retrieve documentation automatically. Please verify your region is supported by checking the [Adaptive Warehouse documentation](https://docs.snowflake.com/en/user-guide/warehouses-adaptive#region-availability)" and wait for their confirmation before proceeding.

**Validation logic:**
- Extract the region from `CURRENT_REGION()` and normalize the format:
  - AWS: `AWS_US_WEST_2` → `us-west-2`
  - Azure: `AZURE_EASTUS2` → `east-us-2`
  - GCP: `GCP_US_EAST4` → `us-east4`
- Find the "Region availability" section in the documentation
- Check if the normalized region appears in the documented supported regions list
- Show result to user: "✓ Your region (AWS_US_WEST_2) is supported for Adaptive Warehouses" OR "✗ Your region (AWS_AP_SOUTH_1) is NOT supported for Adaptive Warehouses"

**Note:** Always reference the live documentation as the source of truth for regional availability. The supported region list may expand over time.

**Check 2 — Account edition:**

Try the following approaches in order until one succeeds:

**Approach 1** - Try `SHOW ORGANIZATION ACCOUNTS`:
```sql
SHOW ORGANIZATION ACCOUNTS;
```
- Filter the result to the current account by matching `account_locator` or `account_name` against `CURRENT_ACCOUNT()` and `CURRENT_ACCOUNT_NAME()`
- Extract the `edition` column value

**Approach 2** - If Approach 1 fails with "Insufficient privileges", try `SHOW ACCOUNTS`:
```sql
SHOW ACCOUNTS LIKE CURRENT_ACCOUNT();
```
- Look for the `edition` column in the result
- Note: This typically requires ORGADMIN or ACCOUNTADMIN role

**Approach 3** - If both SQL approaches fail, use manual fallback:
- Tell the user: "I don't have privileges to check your account edition automatically."
- Ask: "Please check your edition in **Snowsight → Admin → Account** (look for the 'Edition' field) and tell me what it shows."
- Wait for user response before proceeding

**Supported editions:** Enterprise, Business Critical, VPS

**Validation logic:**
- Extract the `edition` value from whichever approach succeeded
- Normalize the value (handle both `ENTERPRISE` and `Enterprise`, `BUSINESS_CRITICAL` and `Business Critical`)
- Check if it matches one of: `Enterprise`, `Business Critical`, or `VPS` (case-insensitive)
- Show result: "✓ Your account edition (Enterprise) supports Adaptive Warehouses" OR "✗ Your account edition (Standard) does NOT support Adaptive Warehouses. Adaptive requires Enterprise edition or above."

If either check fails, stop and inform the user. Do NOT generate ALTER SQL.

**Note:** For the most up-to-date regional availability, refer to the [Adaptive Warehouse documentation](https://docs.snowflake.com/en/user-guide/warehouses-adaptive).

## How Snowflake Sets Parameters on Migration

When converting an existing standard warehouse to adaptive, **you do not need to set `MAX_QUERY_PERFORMANCE_LEVEL` or `QUERY_THROUGHPUT_MULTIPLIER` yourself**. Both Gen1 and Gen2 standard warehouses can be migrated to adaptive. Snowflake automatically determines the recommended values by inspecting your current warehouse configuration — including warehouse size, multi-cluster count, and QAS settings.

Simply run the ALTER and Snowflake handles the parameter mapping. Adjust afterward if needed.

## Live Migration (No Downtime)

Converting to adaptive — and reverting back to standard — is a **zero-downtime, live operation**. Running queries are not interrupted. You do not need to suspend the warehouse before converting.

Warehouses can be converted via **Snowsight** or **SQL**.

**Snowsight:** Navigate to **Compute » Warehouses » `<warehouse_name>`**, select the **…** menu, then **Convert to Adaptive**, and confirm.

**SQL — Convert to adaptive:**
```sql
ALTER WAREHOUSE {{warehouse_name}} SET WAREHOUSE_TYPE = 'ADAPTIVE';
```

You may also set parameters at conversion time (only if you want to override Snowflake's auto-derived values):
```sql
ALTER WAREHOUSE {{warehouse_name}}
  SET WAREHOUSE_TYPE = 'ADAPTIVE'
      MAX_QUERY_PERFORMANCE_LEVEL = {{level}}
      QUERY_THROUGHPUT_MULTIPLIER = {{multiplier}};
```

**⚠️ MANDATORY STOPPING POINT**: Present ALTER statement for approval before executing.

## Rollback

Any adaptive warehouse can be converted back to standard. Zero-downtime operation.

```sql
ALTER WAREHOUSE {{warehouse_name}} SET WAREHOUSE_TYPE = 'STANDARD';
```

**⚠️ MANDATORY STOPPING POINT**: Present ALTER statement for approval before executing.

## Enable and Disable

Adaptive warehouses can be disabled to block all new query submissions without deleting the warehouse.

```sql
-- Disallow any queries from being submitted to this adaptive warehouse
ALTER WAREHOUSE {{warehouse_name}} DISABLE;

-- Re-allow query submissions
ALTER WAREHOUSE {{warehouse_name}} ENABLE;
```

The `STATE` column in `SHOW WAREHOUSES` reflects the current state: `ENABLED` or `DISABLED`. If `STATE = DISABLED`, check the `DISABLED_REASONS` column for context on why it was disabled.

**⚠️ MANDATORY STOPPING POINT**: Present DISABLE statement for approval before executing — a disabled warehouse blocks all queries on that warehouse.

## Bulk Migration

For migrating many warehouses at once, use `SYSTEM$BULK_UPDATE_WH`. Always run the dry run first.

| Parameter | Description | Example |
|-----------|-------------|---------|
| `property_name` | Warehouse property to update | `'WAREHOUSE_TYPE'` |
| `new_value` | New value for the property | `'ADAPTIVE'` or `'STANDARD'` |
| `property_filter` | JSON filter on warehouse properties | `'{"WAREHOUSE_TYPE": "STANDARD"}'` |
| `tag_filter` | JSON filter on tags | `'{"cost-centre": "sales"}'` |
| `execution_mode` | `'DRY_RUN'` or `'ACTIVE'` | `'DRY_RUN'` |

**Dry run (no changes made):**
```sql
SELECT SYSTEM$BULK_UPDATE_WH(
  'WAREHOUSE_TYPE',
  'ADAPTIVE',
  '{"WAREHOUSE_TYPE": "STANDARD"}',
  'DRY_RUN'
);
```

**Execute migration:**
```sql
SELECT SYSTEM$BULK_UPDATE_WH(
  'WAREHOUSE_TYPE',
  'ADAPTIVE',
  '{"WAREHOUSE_TYPE": "STANDARD"}',
  'ACTIVE'
);
```

**⚠️ MANDATORY STOPPING POINT**: Always show dry run results to the user and get explicit approval before running the ACTIVE migration.