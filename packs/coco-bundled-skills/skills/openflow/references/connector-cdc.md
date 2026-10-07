---
name: openflow-connector-cdc
description: CDC connectors for PostgreSQL, MySQL, and MariaDB. Use for database replication to Snowflake including health monitoring and recovery procedures. MariaDB uses the MySQL connector. For SQL Server, see connector-sqlserver.md. For Oracle, see connector-oracle.md.
---

# CDC Connectors (PostgreSQL, MySQL, MariaDB)

Change Data Capture connectors replicate data from relational databases to Snowflake in near-real-time.

**MariaDB:** Use the MySQL connector for MariaDB sources. The same flow, JDBC driver (MariaDB Connector/J), and configuration apply.

**Note:** These operations modify service state. Apply the Check-Act-Check pattern from `references/core-guidelines.md`.

## Scope

This reference covers:
- PostgreSQL and MySQL CDC connectors
- CDC-specific health monitoring and table replication state
- Recovery procedures for failed tables

For SQL Server, see `references/connector-sqlserver.md`.
For other connectors, see `references/connector-main.md`.

## Workflow Summary

Complete ALL steps before starting the flow:

1. **Network Access** - EAI attached to runtime (SPCS only)
2. **Network Validate** - Test connectivity to database endpoint
3. **Deploy** - Deploy the connector flow
4. **Parameters** - Configure source, destination, and ingestion parameters
5. **Asset Uploads** - Upload JDBC driver (required, not bundled)
6. **Verify Controllers** - Run `verify_config` before enabling
7. **Enable Controllers** - Enable after verification passes
8. **Verify Processors** - Run `verify_config` after controllers enabled
9. **Start** - Start the flow
10. **Validate** - Confirm data is flowing

**Common failure:** Skipping step 5 (JDBC driver) causes controller stuck in ENABLING state.

See [Deployment Workflow](#deployment-workflow) for detailed instructions.

---

## Flow Names

| Database | Flow Name |
|----------|-----------|
| PostgreSQL | `postgresql` |
| MySQL | `mysql` |
| MariaDB | `mysql` (use the MySQL connector) |

## Collect Checklist

Gather this information from the user **before** proceeding with deployment.

### Source Database Configuration (Required)

| Item | PostgreSQL | MySQL / MariaDB | Collected |
|------|------------|-----------------|-----------|
| Connection URL | `jdbc:postgresql://host:5432/db` | `jdbc:mysql://host:3306/db` | [ ] |
| Username | Database user | Database user | [ ] |
| Password | (sensitive) | (sensitive) | [ ] |
| Tables to Replicate | Comma-separated or regex | Comma-separated or regex | [ ] |

### Database-Specific Items

| Item | PostgreSQL | MySQL / MariaDB | Collected |
|------|------------|-----------------|-----------|
| Publication Name | Required | N/A | [ ] |
| Replication Slot | Optional | N/A | [ ] |
| Server ID | N/A | Optional | [ ] |

### Snowflake Configuration (Required)

| Item | Description | Collected |
|------|-------------|-----------|
| Destination Database | Database for replicated data | [ ] |
| Snowflake Role | Role with CREATE SCHEMA privileges | [ ] |
| Snowflake Warehouse | Warehouse for processing | [ ] |

### Source Prerequisites (User Must Complete)

| Prerequisite | PostgreSQL | MySQL / MariaDB |
|--------------|------------|-----------------|
| Replication enabled | `wal_level = logical` | Binary logging, ROW format |
| Publication/CDC setup | Publication created | GTID mode (recommended) |
| User permissions | REPLICATION + SELECT | REPLICATION SLAVE/CLIENT |
| Tables have primary keys | Required | Required |

**Do not proceed until all required items are collected and prerequisites confirmed.**

**MariaDB-specific:** `binlog_legacy_event_pos` must be set to `ON`. The MariaDB Connector/J client relies on legacy binlog event positions; without this, the connector cannot track its position in the binlog correctly.

---

## Deployment Workflow

Follow the main workflow in `references/connector-main.md`. This section provides connector-specific details for each step.

### 1. Network Access (SPCS Only)

**Load** `references/platform-eai.md` for EAI setup.

### 2. Network Validate (SPCS Only)

**Load** `references/ops-network-testing.md` and test connectivity to the database endpoint.

Test targets for this connector (replace with actual values):
```python
# Example for PostgreSQL on RDS
targets = [
    {"host": "mydb.abc123.us-east-1.rds.amazonaws.com", "port": 5432, "type": "JDBC/PostgreSQL"},
]

# Example for MySQL
targets = [
    {"host": "mydb.abc123.us-east-1.rds.amazonaws.com", "port": 3306, "type": "JDBC/MySQL"},
]
```

**Important:** Network rules for databases are host:port specific. A `SocketTimeoutException` after DNS success indicates the port is not in the network rule.

**If any tests fail:** Stop and resolve EAI configuration before proceeding.

### 3. Deploy

**Load** `references/ops-flow-deploy.md`. Flow names: `postgresql` or `mysql` (use `mysql` for MariaDB).

### 4. Handle Parameters

Configure parameters in order:
1. **Source Parameters** - See [Source Parameters](#source-parameters) below
2. **Destination Parameters** - **Load** `references/ops-snowflake-auth.md`
3. **Ingestion Parameters** - See [Ingestion Parameters](#ingestion-parameters) below

Use `references/ops-parameters-main.md` for configuration commands.

### 5. Asset Uploads

**JDBC Drivers Required.** Upload the appropriate driver for your database:

| Database | Parameter Name | Driver Notes |
|----------|---------------|--------------|
| PostgreSQL | PostgreSQL JDBC Driver | Standard PostgreSQL JDBC driver |
| MySQL | MySQL JDBC Driver | **Must use MariaDB Connector/J** (not MySQL Connector/J) |
| MariaDB | MySQL JDBC Driver | Use MariaDB Connector/J (same as MySQL) |

**Maven Central URLs (validated Dec 2025):**

```
# PostgreSQL (42.7.7)
https://repo1.maven.org/maven2/org/postgresql/postgresql/42.7.7/postgresql-42.7.7.jar

# MariaDB Connector/J for MySQL (3.5.3)
https://repo1.maven.org/maven2/org/mariadb/jdbc/mariadb-java-client/3.5.3/mariadb-java-client-3.5.3.jar
```

**Check for latest version:**

```bash
# PostgreSQL
curl -s "https://search.maven.org/solrsearch/select?q=g:org.postgresql+AND+a:postgresql&rows=1&wt=json" | jq -r '.response.docs[0].latestVersion'

# MariaDB
curl -s "https://search.maven.org/solrsearch/select?q=g:org.mariadb.jdbc+AND+a:mariadb-java-client&rows=1&wt=json" | jq -r '.response.docs[0].latestVersion'
```

See `references/ops-parameters-assets.md` for upload commands.

### 6. Verify Controllers

Verify controller configuration BEFORE enabling:

```bash
nipyapi --profile <profile> ci verify_config --process_group_id "<pg-id>" --verify_processors=false
```

**If verification fails:** Fix parameter configuration (connection URL, credentials) before proceeding.

### 7. Enable Controllers

Enable controller services after verification passes.

**Load** `references/ops-flow-lifecycle.md` (Enable Controllers Only section).

After enabling, check for errors:
- All controllers show `ENABLED`
- Check bulletins for database connection or authentication errors

### 8. Verify Processors

Verify processor configuration AFTER controllers are enabled:

```bash
nipyapi --profile <profile> ci verify_config --process_group_id "<pg-id>" --verify_controllers=false
```

**If verification fails:** Check processor dependencies (controllers must be enabled).

### 9. Start

**Load** `references/ops-flow-lifecycle.md` for starting the flow.

### 10. Validate

After starting, validate data is flowing. See [Validate Data Flow](#validate-data-flow) below.

### 11. Monitor

See [CDC Health Monitoring](#cdc-health-monitoring) below for ongoing monitoring.

---

## Validate Data Flow

After starting the connector, validate data is actually flowing.

### Step 1: Check Flow Status

```bash
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
```

Expect:
- `running_processors` > 0
- `invalid_processors` = 0
- `bulletin_errors` = 0

### Step 2: Validate Target Objects Created

The connector creates schemas and tables based on the source structure. Query Snowflake to confirm:

```sql
-- Check schema exists (quote lowercase names from source)
SHOW SCHEMAS IN DATABASE <destination_database>;

-- Check tables exist
SHOW TABLES IN SCHEMA <destination_database>."<source_schema>";

-- Validate rows are appearing
SELECT COUNT(*) FROM <destination_database>."<source_schema>"."<source_table>";
```

**PostgreSQL Case Sensitivity:** PostgreSQL uses lowercase identifiers by default. When querying replicated data in Snowflake, you MUST quote lowercase schema and table names:

```sql
-- Correct (quoted lowercase identifiers)
SELECT * FROM MYDB."public"."employees";

-- Wrong (Snowflake normalizes to uppercase, table not found)
SELECT * FROM MYDB.public.employees;
```

### Step 3: Monitor Initial Replication

For large tables, the initial snapshot may take time. Check table state to monitor progress - see [CDC Health Monitoring](#cdc-health-monitoring).

---

## Prerequisites

Refer to the official Snowflake documentation for current prerequisite requirements:

- **PostgreSQL:** [Set up the Openflow Connector for PostgreSQL](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/postgres/setup)
- **MySQL:** [Set up the Openflow Connector for MySQL](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/mysql/setup)

---

## Source Parameters

**Sensitive values:** Passwords are marked (sensitive). Ask user to provide directly. Never display these values - use `[REDACTED]` in confirmations.

### PostgreSQL

| Parameter | Required | Description |
|-----------|----------|-------------|
| PostgreSQL Connection URL | Yes | `jdbc:postgresql://host:5432/db` |
| PostgreSQL Username | Yes | Database username |
| PostgreSQL Password | Yes | Database password (sensitive) |
| Publication Name | Yes | Logical replication publication |
| Replication Slot Name | No | Custom slot name |

### MySQL / MariaDB

| Parameter | Required | Description |
|-----------|----------|-------------|
| MySQL Connection URL | Yes | `jdbc:mysql://host:3306/db` (works for MariaDB too) |
| MySQL Username | Yes | Database username |
| MySQL Password | Yes | Database password (sensitive) |
| Server ID | No | Unique server ID for replication |

**Note:** The MySQL connector uses MariaDB Connector/J (not MySQL Connector/J) due to licensing, so it natively supports both MySQL and MariaDB sources.

---

## Ingestion Parameters

Common to all CDC connectors:

| Parameter | Required | Description |
|-----------|----------|-------------|
| Included Table Names | No* | Comma-separated (e.g., `public.users,public.orders`) |
| Included Table Regex | No* | Regex pattern for table selection |
| Object Identifier Resolution | No | `CASE_SENSITIVE` (default) or `CASE_INSENSITIVE` - see below |
| Ingestion Type | No | `full` or `incremental` |

*One of Included Table Names or Included Table Regex is required.

### Object Identifier Resolution

Controls how schema and table names are created in Snowflake.

| Value | Behavior | Use When |
|-------|----------|----------|
| `CASE_SENSITIVE` (default) | Preserves source casing (e.g., `"public"."users"`) | You want exact match to source; requires quoted identifiers in SQL |
| `CASE_INSENSITIVE` | Uppercases all names (e.g., `PUBLIC.USERS`) | You prefer Snowflake-native naming; allows unquoted SQL |

**IMPORTANT: Ask the user before proceeding:**
> "Do you want to preserve the original casing from your source database, or use Snowflake's default uppercase naming? 
> - **Preserve casing** (CASE_SENSITIVE): Schema/table names stay lowercase (e.g., `"public"."orders"`). You must quote identifiers in SQL.
> - **Uppercase** (CASE_INSENSITIVE): Names are uppercased (e.g., `PUBLIC.ORDERS`). Standard Snowflake convention, no quoting needed."

**WARNING:** This setting cannot be changed after replication has started without performing a full connector reset (stop flow, clear state, drop destination tables, restart). Choose carefully before initial deployment.

---

## CDC Health Monitoring

### Table Replication State

All CDC connectors track table state via `StandardTableStateService`. Use the component state operations to inspect and manage this state.

**For detailed state management commands, see `references/ops-component-state.md`.**

Quick check of table status:

```bash
# Find the TableStateService controller ID
nipyapi --profile <profile> canvas list_all_controllers "<pg-id>" | \
  jq '.[] | select(.component.type | contains("TableState")) | {id: .id, name: .component.name}'

# Get state entries
nipyapi --profile <profile> canvas get_controller_state "<table-state-service-id>"
```

Each state entry contains: `table_name` as key, `position,status,timestamp` as value.

### Replication Status Values

| Status | Meaning |
|--------|---------|
| `NEW` | Table discovered, replication not started |
| `SNAPSHOT_REPLICATION` | Capturing initial snapshot |
| `INCREMENTAL_REPLICATION` | Streaming real-time updates |
| `FAILED` | Cannot replicate (see failure reason) |

### Common Failure Causes

- Table lacks a Primary Key
- Schema changed incompatibly
- Replication slot/binlog issues
- Network connectivity problems

---

## Recovering from FAILED State

If a table enters FAILED state, recovery requires removing the table, cleaning up, and re-adding.

**WARNING:** This process includes destructive operations. Confirm each step with the user.

### Step 1: Remove Table from Replication

Update parameters to exclude the failed table. Use `references/ops-parameters-main.md` for the commands.

Ensure BOTH `Included Table Names` AND `Included Table Regex` exclude the table.

### Step 2: Verify Table Removed from State

Wait for the change to propagate, then verify using the Python code above. The failed table should no longer appear.

**Note:** Flow files for other tables continue processing. Do NOT purge flow files unless doing a full reset.

### Step 3: Delete Destination Table in Snowflake

Ask the user: "This will DROP the table from Snowflake. This is irreversible. Proceed?"

```sql
-- Use exact case if Object Identifier Resolution = CASE_SENSITIVE
DROP TABLE "schema"."failed_table";
```

### Step 4: Re-add Table to Replication

Ask the user: "Re-adding this table will trigger a full snapshot reload. Proceed?"

Update the inclusion parameters to add the table back.

### Full Reset (All Tables)

For a complete reset:

1. Remove all tables from replication (set empty inclusion parameters)
2. Wait for queues to drain or purge if necessary (see `references/ops-flow-lifecycle.md`)
3. Drop all destination tables in Snowflake
4. Re-add tables

---

## CDC Batching Behavior

CDC is near-real-time but batches updates for efficiency:
- Low-volume tables: updates batched for approximately 1 minute
- Reduces Snowflake costs from many small inserts

---

## Known Issues

### StandardPrivateKeyService INVALID on SPCS or BYOC with Managed Token

Expected — the `Snowflake Private Key Service` controller is unused unless you use `KEY_PAIR` auth, so it shows INVALID. Impact: none. See `references/known-issues-common.md`.

---

## Troubleshooting

### Check Bulletins

```bash
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
```

Check `bulletin_errors` and `bulletin_warnings` fields.

### PrivateKeyService Bulletins (SPCS Only)

On SPCS, you may see `PrivateKeyService` errors. Ignore these - this service is only used on BYOC.

---

## Next Step

After deployment and configuration, return to `references/connector-main.md` or the calling workflow.

## See Also

- `references/connector-main.md` - Connector workflow overview
- `references/connector-sqlserver.md` - SQL Server CDC connector (separate reference)
- `references/connector-oracle.md` - Oracle CDC connector (separate reference)
- `references/ops-component-state.md` - Inspect and clear table replication state
- `references/ops-snowflake-auth.md` - Snowflake destination configuration
- `references/platform-eai.md` - Network access for database connectivity
- `references/ops-parameters-main.md` - Parameter configuration
