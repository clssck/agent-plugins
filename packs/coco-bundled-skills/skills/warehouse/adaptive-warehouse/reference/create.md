# Create Adaptive Warehouse

## Eligibility Gate

⚠️ **MANDATORY before executing CREATE or ALTER** — Run both checks and validate automatically.

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

If either check fails — unsupported region or insufficient edition — **stop and inform the user**. Do NOT generate CREATE or ALTER SQL.

**Note:** For the most up-to-date regional availability, refer to the [Adaptive Warehouse documentation](https://docs.snowflake.com/en/user-guide/warehouses-adaptive).

> **Note:** For parameter or tuning questions ("what settings do you recommend?") you do NOT need to run these checks first — just answer directly.

## Gather Requirements

Ask the user for:
- Warehouse name
- `MAX_QUERY_PERFORMANCE_LEVEL` (optional)
- `QUERY_THROUGHPUT_MULTIPLIER` (optional)

**Parameter starting points:**

- **Migrating from a classic warehouse (ALTER):** Do not set these manually — Snowflake automatically derives both from your existing warehouse configuration (size, cluster count, QAS settings). Run the ALTER and tune afterward if needed.
- **Greenfield (CREATE):** Start with `MAX_QUERY_PERFORMANCE_LEVEL = XLARGE` and `QUERY_THROUGHPUT_MULTIPLIER = 2`.

**Tuning guidance:**
- Increase `QUERY_THROUGHPUT_MULTIPLIER` if you observe undesirable queueing
- Decrease `QUERY_THROUGHPUT_MULTIPLIER` to reduce costs, accepting increased queueing

## Generate CREATE Statement

Adaptive warehouses can be created via **Snowsight** or **SQL**.

**Snowsight:** Navigate to **Compute » Warehouses » +Warehouse**, select **Adaptive** in the Type dropdown. Optionally expand **Advanced** to configure parameters.

**SQL — Minimal (all defaults):**
```sql
CREATE ADAPTIVE WAREHOUSE {{warehouse_name}};
```

**SQL — With parameters:**
```sql
CREATE ADAPTIVE WAREHOUSE {{warehouse_name}}
  WITH MAX_QUERY_PERFORMANCE_LEVEL = {{level}}
       QUERY_THROUGHPUT_MULTIPLIER = {{multiplier}};
```

**SQL — Equivalent `CREATE WAREHOUSE` syntax:**
```sql
CREATE WAREHOUSE {{warehouse_name}}
  WITH WAREHOUSE_TYPE = 'ADAPTIVE'
       MAX_QUERY_PERFORMANCE_LEVEL = {{level}}
       QUERY_THROUGHPUT_MULTIPLIER = {{multiplier}};
```

**Note:** Standard warehouse properties (`WAREHOUSE_SIZE`, `MIN_CLUSTER_COUNT`, `MAX_CLUSTER_COUNT`, `SCALING_POLICY`) cannot be set on an adaptive warehouse.

**⚠️ MANDATORY STOPPING POINT**: Present CREATE statement for approval before executing.

## Execute and Verify

1. Execute the approved CREATE statement
2. Verify:
   ```sql
   SHOW WAREHOUSES LIKE '{{warehouse_name}}';
   ```
   Confirm `type` column shows `ADAPTIVE`.