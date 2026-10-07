---
name: storage-lifecycle-policy
description: "Create, manage, and monitor Snowflake storage lifecycle policies. Use when: creating expiration or archival policies, attaching policies to tables, monitoring policy execution, retrieving archived data, managing data retention, reducing storage costs, saving on table storage. Triggers: storage lifecycle, lifecycle policy, archive data, expire data, COOL tier, COLD tier, data retention, archival storage, CREATE STORAGE LIFECYCLE POLICY, FROM ARCHIVE OF, ARCHIVE_FOR_DAYS, storage cost optimization, table is large, table is expensive, save on storage."
---

# Storage Lifecycle Policy

## When to Use

Use this skill when the user wants to:
- Create a storage lifecycle policy (expiration or archival)
- Attach or detach a policy from a table
- Monitor policy execution history
- Retrieve data from archive storage
- Understand archive tiers (COOL vs COLD)
- Optimize storage costs via automated data lifecycle management

## Key Concepts

- **Expiration policy**: Permanently deletes rows matching a condition. No `ARCHIVE_TIER`. Available on AWS, Azure, and GCP.
- **Archival policy**: Moves rows to cheaper storage (COOL or COLD tier), then expires after `ARCHIVE_FOR_DAYS`. COOL and COLD are archive tiers that only apply to archival policies.
  - **COOL tier**: Min 90-day archive period. Available on AWS, GCP, and Azure. Retrieval is fast but still requires `CREATE TABLE ... FROM ARCHIVE OF` — archived rows cannot be queried directly.
  - **COLD tier**: Cheapest storage, min 180-day archive period. Available on AWS and GCP. Retrieval can take up to 48 hours and also requires `CREATE TABLE ... FROM ARCHIVE OF`.
- **One policy per table**: A table can have only one storage lifecycle policy attached.
- **Tier is permanent**: Once a table is assigned an archive tier, it cannot be changed.
- **Daily execution**: Policies run automatically ~once every 24 hours using Snowflake-managed compute.

## Discovering Candidate Tables

Load `cost-intelligence/skills/cost-insights/SKILL.md` with intent drill-down and insight type `COLD_FILE_STORAGE` to identify candidate tables before applying a lifecycle policy.

```sql
CALL SNOWFLAKE.LOCAL.COST_INSIGHTS!GET_TOP_TABLE_WAREHOUSE_INSIGHTS_BY_INSIGHT_TYPE_PROCEDURE(10, 'COLD_FILE_STORAGE');
```

If the call fails due to missing permissions, ask the user to have an admin grant the `APP_USAGE_VIEWER` or `APP_USAGE_ADMIN` application role. If they cannot, proceed directly to the next section.

Once you have the candidate list, proceed to the workflow below to create and attach a policy.

## Workflow

### Step 1: Determine Policy Type

Determine from the user's request:

- **Expire only** (user says "delete", "remove", "purge" old rows): No `ARCHIVE_TIER` needed
- **Archive then expire** (user says "archive", "move to cheaper storage", "retain"): Requires `ARCHIVE_TIER` and `ARCHIVE_FOR_DAYS`

### Step 2: Create the Policy and Attach to Table

**IMPORTANT**: A policy has no effect until attached to a table. Always create the policy AND attach it in the same step.

**Expiration policy** (deletes rows permanently):

```sql
CREATE STORAGE LIFECYCLE POLICY <policy_name>
  AS (<col_name> TIMESTAMP)
  RETURNS BOOLEAN ->
    TO_DATE(<col_name>) < TO_DATE(DATEADD(DAY, -<retention_days>, CURRENT_TIMESTAMP()));

ALTER TABLE <table_name> ADD STORAGE LIFECYCLE POLICY <policy_name>
  ON (<column_name>);
```

**Archival policy** (archive first, then expire):

```sql
CREATE STORAGE LIFECYCLE POLICY <policy_name>
  AS (<col_name> TIMESTAMP)
  RETURNS BOOLEAN ->
    TO_DATE(<col_name>) < TO_DATE(DATEADD(DAY, -<threshold_days>, CURRENT_TIMESTAMP()))
  ARCHIVE_TIER = COOL  -- or COLD (AWS and GCP only)
  ARCHIVE_FOR_DAYS = <archive_days>;

ALTER TABLE <table_name> ADD STORAGE LIFECYCLE POLICY <policy_name>
  ON (<column_name>);
```

**Best practice**: Always use `TO_DATE()` conversions in policy expressions for consistent execution regardless of time of day.

Requirements for attaching:
- Column count and types must match the policy signature
- The table must not already have a storage lifecycle policy attached
- If ALTER TABLE ADD fails because the table already has a policy, inform the user and ask if they want to drop the existing policy first using `ALTER TABLE <table_name> DROP STORAGE LIFECYCLE POLICY`

**Important**: A policy has no effect until attached. Always follow through with both CREATE and ALTER TABLE ... ADD — do not stop after creating the policy.

### Step 3: Verify Attachment

```sql
-- Check which policies are attached to a table
SELECT * FROM TABLE(
  INFORMATION_SCHEMA.POLICY_REFERENCES(
    REF_ENTITY_NAME => '<db.schema.table>',
    REF_ENTITY_DOMAIN => 'TABLE'
  )
) WHERE POLICY_KIND = 'STORAGE_LIFECYCLE_POLICY';
```

### Step 4: Monitor Execution

```sql
-- View execution history (last 14 days)
SELECT * FROM TABLE(
  INFORMATION_SCHEMA.STORAGE_LIFECYCLE_POLICY_HISTORY(
    REF_ENTITY_NAME => '<db.schema.table>',
    REF_ENTITY_DOMAIN => 'TABLE',
    TIME_RANGE_START => DATEADD('DAY', -7, CURRENT_TIMESTAMP()),
    RESULT_LIMIT => 100
  )
);

-- Or via ACCOUNT_USAGE (up to 365 days)
SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.STORAGE_LIFECYCLE_POLICY_HISTORY
  WHERE SCHEDULED_TIME > DATEADD('DAY', -7, CURRENT_TIMESTAMP())
  ORDER BY SCHEDULED_TIME DESC;

-- List all policies in a schema
SHOW STORAGE LIFECYCLE POLICIES IN SCHEMA <db.schema>;

-- View a policy definition
DESCRIBE STORAGE LIFECYCLE POLICY <policy_name>;
```

## Retrieving Archived Data

**IMPORTANT**: Archived rows cannot be queried directly regardless of archive tier (COOL or COLD). You must use `CREATE TABLE ... FROM ARCHIVE OF` to create a new table containing the archived data before you can query it.

To view metadata about archived data (row count, column min/max values) without incurring retrieval costs:

```sql
SELECT SYSTEM$GET_TABLE_ARCHIVE_METADATA('<db.schema.table>');
```

To retrieve archived data, use `CREATE TABLE ... FROM ARCHIVE OF`:

```sql
CREATE TABLE <new_table>
  FROM ARCHIVE OF <source_table> AS st
  WHERE st.<column> BETWEEN '<start_date>' AND '<end_date>';
```

### Estimating Retrieval Cost Before Executing

Always run `EXPLAIN` before the actual retrieval to understand the cost and plan accordingly:

```sql
EXPLAIN
CREATE TABLE <new_table>
  FROM ARCHIVE OF <source_table> AS st
  WHERE st.<column> BETWEEN '<start_date>' AND '<end_date>';
```

The `EXPLAIN` output includes:

- A `createTableFromArchiveData` operation in the `operation` column
- `ARCHIVE OF <table>` in the `objects` column for the `TableScan` operation
- `assignedPartitions` — the number of partitions Snowflake will restore from archive to retrieve the data
- `bytesAssigned` — the number of bytes that will be retrieved

**After reviewing the EXPLAIN output, help the customer estimate the retrieval storage cost:**

#### Retrieval Storage Cost Estimate

Retrieval is charged as a one-time per-TB fee based on the archive tier, cloud provider, and region. Use `bytesAssigned` from the EXPLAIN output to calculate:

**Calculation**: `bytesAssigned` ÷ 1,099,511,627,776 × retrieval rate per TB = estimated retrieval storage cost

**Example**: Retrieving 500 GB from COOL tier on AWS US-East:
`500 GB ÷ 1024 = 0.488 TB × $30/TB = ~$14.65`

**Note**: This estimate covers retrieval storage cost only. The actual total cost will be higher due to warehouse compute charges incurred while running the retrieval query. For COLD tier, Snowflake also temporarily copies restored data into normal storage during retrieval, so you will pay additional storage charges for that temporary data until it is removed.

**AWS — COOL Tier Retrieval:** $30.00/TB (all regions)

**AWS — COLD Tier Retrieval (per TB data processed):**

| Region | $/TB |
|--------|------|
| US East (N. Virginia), US West (Oregon), US East 2 (Ohio), US East 1 Commercial Gov, US West (Commercial Gov - Oregon) | $2.50 |
| EU Dublin, Europe (Stockholm) | $3.00 |
| US Gov West 1, US Gov West 1 (Fedramp High Plus), US Gov East 1 (Fedramp High Plus), US Gov West 1 (DoD) | $3.40 |
| Middle East (UAE) | $3.30 |
| Asia Pacific (Malaysia), Asia Pacific (Thailand) | $4.50 |
| EU Frankfurt, Europe (London), Asia Pacific (Seoul, Osaka, Jakarta, Sydney, Singapore, Mumbai), Canada Central, EU (Paris), EU (Zurich), Africa (Cape Town) | $5.00 |
| South America East 1 (São Paulo) | $8.00 |

**Azure — COOL Tier Retrieval (per TB data processed):** (COLD tier not available on Azure)

| Region | $/TB |
|--------|------|
| East US 2 (Virginia), West US 2 (Washington), North Europe (Ireland), Sweden Central, East US (Virginia) | $30.00 |
| West Europe (Netherlands), Australia East, Canada Central (Toronto), Southeast Asia (Singapore), Japan East (Tokyo), UAE North (Dubai), Central India (Pune), UK South (London), Korea Central | $30.00 |
| US Gov Virginia, US Gov Virginia (Fed Ramp High Plus) | $30.00 |
| Mexico Central | $33.00 |
| South Central US (Texas) | $36.00 |
| US Central (Iowa) | $36.90 |
| Switzerland North | $42.90 |

**GCP — COOL Tier Retrieval:** $20.00/TB (all regions)

**GCP — COLD Tier Retrieval:** $50.00/TB (all regions)

**If the region cannot be found in the tables above**, fetch `https://www.snowflake.com/legal-files/CreditConsumptionTable.pdf`, locate tables 3(e) and 5, and use the listed rate.

**After estimating cost, recommend the user adjust these settings before running the actual retrieval:**

1. **Warehouse size** — Choose the smallest warehouse size that can complete the retrieval in ~30 minutes. Archive retrieval insert throughput is approximately **25 MB/s per node** (observed range in production: 11–50 MB/s). Use the following formula:

   ```
   nodes_per_size = { XSMALL: 1, SMALL: 2, MEDIUM: 4, LARGE: 8, XLARGE: 16, 2XLARGE: 32 }
   megaBytesAssigned = bytesAssigned / 1048576
   required_nodes = ceil(megaBytesAssigned / 1800 / 25)
   recommended_size = smallest size where nodes >= required_nodes
   ```

   **Example**: `bytesAssigned` = 200 GB (204,800 MB):
   ```
   required_nodes = ceil(204800 / 1800 / 25) = ceil(4.55) = 5
   → Recommended size: LARGE (8 nodes)
   ```

   If `required_nodes` exceeds 32 (the largest standard warehouse), recommend 2XLARGE and note that the retrieval will take longer than 30 minutes — the statement timeout below must be increased accordingly.

   Only scale up — never lower the warehouse size. If the current size already meets or exceeds the recommendation, leave it unchanged. Before scaling up, record the current size so it can be restored after:
   ```sql
   -- Check current warehouse size first
   SHOW WAREHOUSES LIKE '<wh_name>';
   -- Note the current "size" value (e.g., 'MEDIUM')

   -- Only scale up if current size is smaller than recommended
   ALTER WAREHOUSE <wh_name> SET WAREHOUSE_SIZE = 'LARGE';
   -- Run the retrieval
   CREATE TABLE <new_table>
     FROM ARCHIVE OF <source_table> AS st
     WHERE st.<column> BETWEEN '<start_date>' AND '<end_date>';
   -- Restore to original size (not necessarily XSMALL — use whatever it was before)
   ALTER WAREHOUSE <wh_name> SET WAREHOUSE_SIZE = '<original_size>';
   ```

2. **Statement timeout** — Set based on the archive tier and estimated execution time. The lowest non-zero value between session and warehouse wins, so set both:

   Calculate the estimated execution time for the actual chosen warehouse:
   ```
   estimated_seconds = megaBytesAssigned / (nodes_in_chosen_size × 25)
   ```

   Note: if `required_nodes` exceeds 32, the recommended size is still 2XLARGE (32 nodes) but `estimated_seconds` will be longer than 1800. Use the actual `estimated_seconds` for timeout calculation regardless.

   Then set the timeout with a 2.5× buffer:
   - **COOL tier**: `timeout = estimated_seconds × 2.5`
   - **COLD tier**: COLD retrievals on AWS require up to 48 hours for file restoration from deep archive before the insert begins. `timeout = (48 × 3600) + (estimated_seconds × 2.5)`

   **Only increase the timeout — never lower it.** Check the current session and warehouse timeout values first. If the existing value is already >= the calculated timeout, leave it unchanged. Reducing the timeout could fail other long-running queries on the warehouse. The default `STATEMENT_TIMEOUT_IN_SECONDS` is 172800 (2 days), so only override if the calculated timeout exceeds the current value.

   ```sql
   -- Check current timeout values before changing
   SHOW PARAMETERS LIKE 'STATEMENT_TIMEOUT_IN_SECONDS' IN WAREHOUSE <wh_name>;
   SHOW PARAMETERS LIKE 'STATEMENT_TIMEOUT_IN_SECONDS' IN SESSION;

   -- Only set if calculated_timeout > current value
   ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = <calculated_timeout>;
   ALTER WAREHOUSE <wh_name> SET STATEMENT_TIMEOUT_IN_SECONDS = <calculated_timeout>;
   ```

3. **Abort detached query** — Must be FALSE so the retrieval continues if the session disconnects:
   ```sql
   ALTER SESSION SET ABORT_DETACHED_QUERY = FALSE;
   ```

## Removing a Policy

```sql
ALTER TABLE <table_name> DROP STORAGE LIFECYCLE POLICY;
```

Archived data remains accessible after policy removal.

## One-Time Operations

For one-time data cleanup (not ongoing):
1. Create and attach the policy
2. Wait for execution (~24 hours)
3. Monitor via `STORAGE_LIFECYCLE_POLICY_HISTORY`
4. Remove the policy to avoid recurring charges

## Important Constraints

- **Not supported on Iceberg tables**: Storage lifecycle policies cannot be applied to Iceberg tables. Only standard Snowflake-managed tables including dynamic tables are supported.
- Cannot change archive tier (COOL/COLD) once assigned to a table
- Subqueries in policy body may cause errors — keep expressions simple
- Policy signature cannot be changed while attached — drop and recreate
- Snowflake bypasses governance policies during evaluation
- Truncating a table does not affect archived data
- Replication: policies replicate but don't execute on secondary accounts

## Stopping Points

- Before removing a policy: Confirm with user

## Output

- Storage lifecycle policy created and attached to specified table(s)
- Monitoring queries provided for ongoing observation
- Archived data retrieved to new table when requested
