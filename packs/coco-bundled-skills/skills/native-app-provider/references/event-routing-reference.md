# Event Routing Table Reference (CET)

Centralized Event Sharing (CET) allows providers to route consumer telemetry from **any region** to a central destination account using an **event routing table**. This eliminates the need to maintain separate event accounts in every consumer region.

> **Status**: Public Preview.

> **Limitation**: VPS/GOV/Sovereign regions and Private Link accounts are NOT supported. Use legacy event accounts (`SYSTEM$SET_EVENT_SHARING_ACCOUNT_FOR_REGION`) for those regions.

## Creating an Event Routing Table

Each rule maps source regions to a destination account. Rules with specific regions take precedence over the `ALL` catch-all rule.

```sql
-- Requires ORGADMIN (or GLOBALORGADMIN in Orgs 2.0)
USE ROLE ORGADMIN;

CREATE EVENT ROUTING TABLE <table_name>
  WITH RULES
    DEFAULT = (
      REGION_GROUP = 'PUBLIC',
      REGIONS = ('ALL'),
      DESTINATION_ACCOUNT = <org>.<account_name>
    );
```

> **Naming constraint**: A rule with `REGIONS = ('ALL')` **must** be named `DEFAULT` (case-insensitive — `default` also works). Any other name for the catch-all rule will be rejected.

**Example** — centralized routing with a GDPR override:

```sql
USE ROLE ORGADMIN;

CREATE EVENT ROUTING TABLE app_events
  WITH RULES
    DEFAULT = (
      REGION_GROUP = 'PUBLIC',
      REGIONS = ('ALL'),
      DESTINATION_ACCOUNT = myorg.events_central
    )
    eu_gdpr = (
      REGION_GROUP = 'PUBLIC',
      REGIONS = ('AWS_EU_WEST_1', 'AWS_EU_WEST_2', 'AWS_EU_CENTRAL_1'),
      DESTINATION_ACCOUNT = myorg.events_eu
    );
```

## Rule Parameters

| Parameter | Description | Examples |
|-----------|-------------|---------|
| `rule_name` | Unique name for the rule. Must be `DEFAULT` for the catch-all rule with `REGIONS = ('ALL')`. | `DEFAULT`, `eu_gdpr`, `aws_us` |
| `REGION_GROUP` | Region group (optional, defaults to `PUBLIC`). Only `PUBLIC` is currently supported. | `PUBLIC` |
| `REGIONS` | Snowflake region IDs, or `ALL`. Same region cannot appear in multiple rules. | `('ALL')`, `('AWS_US_EAST_1', 'AWS_US_WEST_2')` |
| `DESTINATION_ACCOUNT` | Destination account. Format: `account_name` or `org.account_name` (org is optional). | `events_central`, `myorg.events_central` |

## Constraints

- Each organization can have only **one** event routing table activated at a time.
- Maximum **200 rules** per event routing table.
- The destination account must exist and belong to the organization.

## Activating for the Organization

After creating the table, activate it for all application listings:

```sql
ALTER ORGANIZATION SET EVENT ROUTING TABLE <table_name> FOR ALL APPLICATION LISTINGS;
```

> **⚠ STOP**: This activates the routing table for the **entire organization**. All consumer telemetry will be routed according to these rules. Double confirm with the provider before executing this command.

## Updating Rules

To replace all rules in an active routing table, use `FORCE`:

```sql
ALTER EVENT ROUTING TABLE <table_name> FORCE SET RULES
  DEFAULT = (REGIONS = ('ALL'), DESTINATION_ACCOUNT = <org>.<account1>)
  <rule2> = (REGIONS = ('AWS_EU_WEST_1', 'AWS_EU_WEST_2'), DESTINATION_ACCOUNT = <org>.<account2>);
```

> The `FORCE` keyword is required when altering an active routing table.

## Deactivating and Dropping

```sql
-- Deactivate the routing table (falls back to legacy)
ALTER ORGANIZATION UNSET EVENT ROUTING TABLE FOR ALL APPLICATION LISTINGS;

-- Drop the routing table (must be deactivated first)
DROP EVENT ROUTING TABLE <table_name>;
```

> **Note**: `DROP EVENT ROUTING TABLE` does not support `IF EXISTS`. Verify the table exists with `SHOW EVENT ROUTING TABLES` before dropping.

## Migration from Legacy Event Accounts

If the provider already has event accounts configured via `SYSTEM$SET_EVENT_SHARING_ACCOUNT_FOR_REGION`, they can migrate to CET:

```sql
USE ROLE ORGADMIN;

-- Auto-create a routing table from existing event account configuration
CALL SYSTEM$MIGRATE_LEGACY_EVENT_ROUTING_CONFIGURATION('<new_table_name>');

-- Activate the migrated routing table
ALTER ORGANIZATION SET EVENT ROUTING TABLE <new_table_name> FOR ALL APPLICATION LISTINGS;
```

> **Note**: Migration will fail if the provider uses non-public region groups or Private Links. Those regions must remain on the legacy system.

## Inspection Commands

```sql
-- List all routing tables in the org (plural TABLES)
SHOW EVENT ROUTING TABLES;

-- Show rules in a specific routing table
SHOW RULES IN EVENT ROUTING TABLE <table_name>;

-- Show which routing table is currently active for the org (singular TABLE)
SHOW EVENT ROUTING TABLE ON ORGANIZATION FOR ALL APPLICATION LISTINGS;
```

> **Note**: `SHOW EVENT ROUTING TABLES` (plural) lists all routing tables in the org. `SHOW EVENT ROUTING TABLE ON ORGANIZATION ...` (singular) shows which table is currently activated.

## Backward Compatibility

- If no routing table is assigned to the org, the system uses legacy event accounts.
- If a routing table is active but no rule matches the consumer's region, the system falls back to the legacy event account for that region.
- CET routing table rules take precedence over legacy event accounts for PUBLIC regions.
- Legacy `SYSTEM$SET/UNSET_EVENT_SHARING_ACCOUNT_FOR_REGION` functions remain available.

## Legacy Event Account Teardown

To unset an event account for a region:

```sql
USE ROLE ORGADMIN;

SELECT SYSTEM$UNSET_EVENT_SHARING_ACCOUNT_FOR_REGION(
  '<snowflake_region>',
  '<region_group>',
  '<account_name>'
);
```

## All CET SQL Commands

| Command | Purpose |
|---------|---------|
| `CREATE EVENT ROUTING TABLE` | Create a new routing table with rules |
| `ALTER EVENT ROUTING TABLE ... [FORCE] SET RULES` | Replace rules in an existing table |
| `DROP EVENT ROUTING TABLE` | Drop a routing table (must be deactivated first) |
| `ALTER ORGANIZATION SET EVENT ROUTING TABLE ... FOR ALL APPLICATION LISTINGS` | Activate a routing table for the org |
| `ALTER ORGANIZATION UNSET EVENT ROUTING TABLE FOR ALL APPLICATION LISTINGS` | Deactivate the routing table |
| `SHOW EVENT ROUTING TABLES` | List all routing tables in the org |
| `SHOW RULES IN EVENT ROUTING TABLE` | List rules in a specific routing table |
| `SHOW EVENT ROUTING TABLE ON ORGANIZATION FOR ALL APPLICATION LISTINGS` | Show the active routing table |
| `SYSTEM$MIGRATE_LEGACY_EVENT_ROUTING_CONFIGURATION` | Migrate legacy config to a routing table |
