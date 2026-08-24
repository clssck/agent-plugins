---
name: openflow-connector-mysql-gen2
description: Gen2 MySQL CDC connector deployed via SQL API. Covers creation, configuration, lifecycle management, and troubleshooting for connectors created from the OPENFLOW_MYSQL_CDC definition.
---

# Gen2 MySQL CDC Connector

Deploy and manage MySQL CDC connectors using the Openflow SQL API. This reference covers connectors created from the `OPENFLOW_MYSQL_CDC` definition. MariaDB is also supported as a source — use the same connector definition.

**Note:** This reference is for Gen2 (SQL API) connectors only. For Gen1 (nipyapi/registry) MySQL connectors, see `references/connector-cdc.md`.

**Requires:** SOM-enabled account (SQL surface: the SOM probe `SHOW OPENFLOW CONNECTOR DEFINITIONS` returns rows; CLI: `som_enabled: true` in cache). This workflow uses SQL only — no Python/nipyapi required. If the account uses the legacy model, this reference does not apply.

---

## Prerequisites

If any prerequisite Snowflake objects are missing — roles, destination DB, secret, network rule, EAI — load `references/connector-prereqs-gen2.md` first. It covers infrastructure discovery and creation with safe SQL patterns.

Source-side MySQL prerequisites (binary logging, replication user, server ID) are documented in the [Source-Side Prerequisites](#source-side-prerequisites) section below.

If all prerequisites are in place, verify the following before proceeding:

| Object | Verification |
|--------|-------------|
| Runtime (ACTIVE, MEDIUM+, max 1 node) | `DESCRIBE OPENFLOW RUNTIME <db>.<schema>.<name>` — confirm `status = ACTIVE` |
| EAI attached to runtime (SPCS only) | `SHOW PARAMETERS LIKE 'EXTERNAL_ACCESS_INTEGRATIONS' IN OPENFLOW RUNTIME <fqn>` |
| Network rule covers MySQL host:port (SPCS only) | `DESCRIBE NETWORK RULE <db>.<schema>.<rule>` — confirm `value_list` includes `<host>:<port>` |
| Secret type = GENERIC_STRING | `DESCRIBE SECRET <db>.<schema>.<secret>` — confirm `secret_type = GENERIC_STRING` |
| `CREATE OPENFLOW CONNECTOR` privilege on schema | `SHOW GRANTS ON SCHEMA <db>.<schema>` |
| Execute-as role has READ on secret | `SHOW GRANTS ON SECRET <db>.<schema>.<secret>` |

---

## MySQL CDC Constraints

Surface these to the user before proceeding — they affect runtime selection and table eligibility:

- Runtime must be at least **MEDIUM**. Choose Large for high-throughput sources or wide rows.
- Multi-node runtimes are not supported — configure with Min nodes and Max nodes set to `1`.
- Only tables with a primary key or a NOT NULL unique index can be replicated. MySQL's InnoDB storage engine automatically promotes the first NOT NULL unique index to act as the primary key if no explicit primary key is defined.
- JDBC driver (MariaDB Connector/J) must be uploaded — used for both MySQL and MariaDB sources.
- Only username/password authentication with MySQL or MariaDB is supported.
- Unsupported column types: `GEOMETRY`, `GEOMETRYCOLLECTION`, `LINESTRING`, `MULTILINESTRING`, `MULTIPOINT`, `MULTIPOLYGON`, `POINT`, `POLYGON`.
- Cascade deletes (`ON DELETE CASCADE`) are not captured — InnoDB executes these internally without writing to the binary log.
- Schema changes are supported **except**: changing primary key definitions, and changing the precision or scale of a numeric column.
- Aurora reader instances are not supported — they do not maintain their own binary logs.

---

## Source-Side Prerequisites

These steps must be performed on the source MySQL or MariaDB instance. **Present them to the user as instructions — do not execute them yourself.** Ask the user to confirm each item before proceeding to connector creation.

### Binary Logging Configuration

All settings must be applied in `my.cnf` (or the equivalent parameter group for managed services):

| Setting | Required value | Notes |
|---------|---------------|-------|
| `log_bin` | `on` | Enables binary logging |
| `binlog_format` | `row` | Connector supports row-based replication only |
| `binlog_row_metadata` | `full` | Required for column names and primary key information |
| `binlog_row_image` | `full` | Required for all columns to be written to the binary log |
| `binlog_row_value_options` | _(empty/unset)_ | Must be empty — partial JSON documents are not supported |
| `binlog_expire_logs_seconds` | Several hours minimum | Must exceed any expected maintenance window or scheduled replication gap |
| `sort_buffer_size` | `4194304` | Prevents "Out of sort memory" errors |

Example `my.cnf` block:
```ini
log_bin = on
binlog_format = row
binlog_row_metadata = full
binlog_row_image = full
binlog_row_value_options =
sort_buffer_size = 4194304
```

**After changing `log_bin` or `binlog_format`: a MySQL/MariaDB restart is required.**

Managed service equivalents:
- **AWS RDS:** Set parameters in the parameter group. Use `mysql.rds_set_configuration('binlog retention hours', N)` for retention.
- **Amazon Aurora:** `binlog_row_image` is fixed at `full` — no change needed.
- **GCP Cloud SQL:** `binlog_format` is fixed at `row` — no change needed.
- **Azure Database for MySQL:** `binlog_row_metadata` is not user-modifiable — raise a Microsoft support ticket to change it.

**Read replica:** If connecting to a read replica, also set:
```ini
log_replica_updates = ON
```

**MariaDB only:** Also set:
```ini
binlog_legacy_event_pos = ON
```
Required for the MariaDB Connector/J driver to track binlog positions correctly during replication.

### Replication User Privileges

```sql
GRANT REPLICATION SLAVE ON *.* TO '<username>'@'%';
GRANT REPLICATION CLIENT ON *.* TO '<username>'@'%';
-- Grant SELECT on every schema/table to be replicated:
GRANT SELECT ON <database>.* TO '<username>'@'%';
-- Or for specific tables:
GRANT SELECT ON <database>.<table> TO '<username>'@'%';
```

### Server ID

The MySQL/MariaDB server must have a unique `server_id` configured. This is required for binary log replication to function.

Verify:
```sql
SHOW VARIABLES LIKE 'server_id';
-- Must return a non-zero integer unique across the replication topology
```

If zero or missing, add to `my.cnf` and restart:
```ini
server-id = <unique_integer>
```

### Source Network Access

The MySQL/MariaDB instance must be reachable from the Openflow runtime. Ask the user to confirm that connectivity is in place. If using an SPCS deployment, load `references/platform-eai.md` for network rule and EAI setup. If connectivity fails later, load `references/ops-network-testing.md` to validate.

### Confirm Source-Side Readiness

Ask the user to confirm all source-side items before proceeding:

- Binary logging enabled with all required settings (restarted if changed)
- `binlog_row_metadata = full` confirmed (or Microsoft support ticket filed for Azure)
- Replication user has REPLICATION SLAVE, REPLICATION CLIENT, SELECT
- All target tables have a primary key or NOT NULL unique index
- Server ID is a non-zero integer unique in the replication topology
- MariaDB: `binlog_legacy_event_pos = ON`
- Source firewall allows Snowflake egress IPs

---

## Connector State Machine

```
CREATING → STOPPED → STARTING → RUNNING
                ↑         ↓         ↓
                ←── STOPPING ←──┘   │
                ↑                   ↓
                ←───────── START_FAILED

STOPPED → TERMINATE → DELETED → DROP (removes object)
```

**Transitional states** (CREATING, STARTING, STOPPING): Do not issue commands while in these states — wait for a stable state first.

**Stable states:** STOPPED, RUNNING, START_FAILED, DELETED

---

## Collect Checklist

Gather before starting. Items correspond to config.json sections.

### Source (Required)

| Item | Config property | Example |
|------|----------------|---------|
| MySQL JDBC URL | `Source Database Connection URL` | `jdbc:mariadb://host:3306/database` |
| MySQL username | `Source Database User` | `replication_user` |
| MySQL password secret | `Source Database Password` | `<db>.<schema>.<secret_name>` |
| MariaDB driver JAR | `Source Database Driver` (asset) | `mariadb-java-client-3.5.3.jar` |

URL notes:
- The connector uses the MariaDB Connector/J driver for both MySQL and MariaDB sources — use the `jdbc:mariadb://` prefix.
- If SSL is disabled on the source, append `?allowPublicKeyRetrieval=true`.
- Including a database name in the URL is optional — tables are selected via Ingestion parameters.

Driver download (Maven Central):
```
https://repo1.maven.org/maven2/org/mariadb/jdbc/mariadb-java-client/3.5.3/mariadb-java-client-3.5.3.jar
```

Check for the latest version:
```bash
curl -s "https://search.maven.org/solrsearch/select?q=g:org.mariadb.jdbc+AND+a:mariadb-java-client&rows=1&wt=json" | jq -r '.response.docs[0].latestVersion'
```

### Table Selection (at least one required)

| Item | Config property | Example |
|------|----------------|---------|
| Table names (explicit) | `Included Comma Separated Source Table Names` | `"my_database"."users","my_database"."orders"` |
| Table regex (alternative) | `Included Source Table Pattern` | `my_database\.auto_.*` |
| Column filter (optional) | `Column Filter JSON` | per-table include/exclude syntax |

Table format: MySQL uses `"database"."table"` — the source database name maps to a destination Snowflake schema. Both parts must be double-quoted. Tables can be selected by explicit name, regex, or both (union of matches).

### Destination (Required)

| Item | Config property | Value |
|------|----------------|-------|
| Destination database | `Snowflake Destination Database` | `<destination_db>` |
| Warehouse | `Snowflake Warehouse` | `<warehouse>` |
| Auth strategy | `Snowflake Authentication Strategy` | `SNOWFLAKE_MANAGED` (recommended) |
| Schema strategy | `Destination Schema Strategy` | `SOURCE_SCHEMA` (each MySQL database → one Snowflake schema) |
| Object identifier resolution | `Object Identifier Resolution` | `CASE_INSENSITIVE` (recommended) or `CASE_SENSITIVE` |
| Oversized value strategy (optional) | `Oversized Value Strategy` | `Set Null` |
| Schema pattern (optional) | `Destination Schema Pattern` | Custom pattern, e.g. `prefix_${source.schema.name}` |
| Schema prefix / suffix (optional) | `Destination Schema Prefix` / `Destination Schema Suffix` | Modifiers applied to schema names derived by `SOURCE_SCHEMA` |

For KEY_PAIR authentication (BYOC alternative to SNOWFLAKE_MANAGED), load `references/ops-snowflake-auth.md` for additional required parameters.

### Tuning (Optional)

| Item | Config property | Default |
|------|----------------|---------|
| Merge schedule | `Merge Task Schedule CRON` | `* * * * * ?` (every second) |
| Concurrent snapshots | `Concurrent Snapshot Queries` | `2` |

### Migration (Required)

| Item | Config property | Options |
|------|----------------|---------|
| Ingestion type | `Ingestion Type` | `full` (snapshot + CDC) or `incremental` (CDC only, for reinstalls) |
| Starting binlog position (optional) | `Starting Binlog Position` | Specific binlog filename + offset for advanced migration scenarios |
| Re-read tables in state (optional) | `Re-read Tables in State` | Comma-separated list of fully qualified table names whose state should be re-read on next start. Use to force the connector to refresh table metadata that may have changed at the source. |

Do not proceed until all required items are collected.

---

## Deployment Workflow

### 1. Create Connector

Before executing, present the resolved values to the user and get confirmation:

> "I'll create connector `<connector_name>` in runtime `<runtime_name>` using the `OPENFLOW_MYSQL_CDC` definition. Proceed?"

```sql
CREATE OPENFLOW CONNECTOR <db>.<schema>.<connector_name>
  IN RUNTIME <db>.<schema>.<runtime_name>
  FROM DEFINITION OPENFLOW_MYSQL_CDC
  DISPLAY_NAME = '<display name>';
```

Wait for creation to complete:

```sql
SELECT SYSTEM$WAIT_FOR_OPENFLOW_CONNECTORS(600, 'STOPPED', '<db>.<schema>.<connector_name>');
```

New connectors are created with a live version automatically — no need to call `ADD LIVE VERSION FROM LAST`.

### 2. Upload MariaDB Driver

Find the live version stage URI:

```sql
DESCRIBE OPENFLOW CONNECTOR <db>.<schema>.<connector_name>;
-- Read the live_version_location_uri field
```

Upload the driver:

```sql
PUT 'file:///path/to/mariadb-java-client-3.5.3.jar' '<live_version_location_uri>' AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
```

### 3. Configure config.json

Download the template config, edit it, and re-upload:

```sql
GET '<live_version_location_uri>/config.json' 'file:///path/to/local/dir/';
```

Edit the config.json locally (see Config Structure below), then upload:

```sql
PUT 'file:///path/to/config.json' '<live_version_location_uri>' AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
```

### 4. Commit Configuration

```sql
ALTER OPENFLOW CONNECTOR <db>.<schema>.<connector_name> COMMIT;
SELECT SYSTEM$WAIT_FOR_OPENFLOW_CONNECTORS(600, 'STOPPED', '<db>.<schema>.<connector_name>');
```

### 5. Start Connector

```sql
ALTER OPENFLOW CONNECTOR <db>.<schema>.<connector_name> START;
SELECT SYSTEM$WAIT_FOR_OPENFLOW_CONNECTORS(600, 'RUNNING', '<db>.<schema>.<connector_name>');
```

### 6. Validate

```sql
DESCRIBE OPENFLOW CONNECTOR <db>.<schema>.<connector_name>;
-- Confirm status = RUNNING
```

Check the destination database for replicated schemas and tables.

---

## Config Structure

The config.json has this format:

```json
{
  "configFormatVersion": 1,
  "connectorDefinitionId": "OPENFLOW_MYSQL_CDC",
  "configuration": [
    {"name": "Source", "properties": {...}},
    {"name": "Replication table schema", "properties": {...}},
    {"name": "Replication columns", "properties": {...}},
    {"name": "Destination authentication", "properties": {...}},
    {"name": "Destination details", "properties": {...}},
    {"name": "Tuning", "properties": {...}},
    {"name": "Migration", "properties": {...}}
  ]
}
```

### Property Value Types

| Type | Format | Example |
|------|--------|---------|
| STRING_LITERAL | `{"valueType": "STRING_LITERAL", "value": "..."}` | Connection URL, username |
| SECRET_REFERENCE | `{"valueType": "SECRET_REFERENCE", "fullyQualifiedSecretName": "..."}` | Password |
| ASSET_REFERENCE | `{"valueType": "ASSET_REFERENCE", "assetIds": ["filename.jar"]}` | JDBC driver |

### SECRET_REFERENCE Format

Use the direct `database.schema.secret_name` path:

```json
"Source Database Password": {
  "valueType": "SECRET_REFERENCE",
  "fullyQualifiedSecretName": "<db>.<schema>.<secret_name>"
}
```

### ASSET_REFERENCE Binding

Set `assetIds` to the uploaded filename:

```json
"Source Database Driver": {
  "valueType": "ASSET_REFERENCE",
  "assetIds": ["mariadb-java-client-3.5.3.jar"]
}
```

### Configuration Sections

| Section | Key properties |
|---------|---------------|
| Source | `Source Database Connection URL`, `Source Database User`, `Source Database Password` (secret), `Source Database Driver` (asset) |
| Replication table schema | `Included Comma Separated Source Table Names` (`"db"."table"` format), `Included Source Table Pattern` (regex) |
| Replication columns | `Column Filter JSON` |
| Destination authentication | `Snowflake Authentication Strategy` (`SNOWFLAKE_MANAGED` recommended), key pair fields |
| Destination details | `Snowflake Destination Database`, `Snowflake Warehouse`, `Destination Schema Strategy`, `Destination Schema Pattern/Prefix/Suffix`, `Object Identifier Resolution`, `Table Storage Format`, `Oversized Value Strategy` |
| Tuning | `Merge Task Schedule CRON`, `Concurrent Snapshot Queries` |
| Migration | `Ingestion Type` (`full`/`incremental`), `Starting Binlog Position`, `Re-read Tables in State` |

---

## Lifecycle Operations

### Stop Connector

```sql
ALTER OPENFLOW CONNECTOR <fqn> STOP;
SELECT SYSTEM$WAIT_FOR_OPENFLOW_CONNECTORS(600, 'STOPPED', '<fqn>');
```

### Edit Running Connector

A connector must be STOPPED before editing. The workflow is:

1. Stop and wait until fully stopped:
```sql
ALTER OPENFLOW CONNECTOR <fqn> STOP;
SELECT SYSTEM$WAIT_FOR_OPENFLOW_CONNECTORS(600, 'STOPPED', '<fqn>');
```
`ADD LIVE VERSION FROM LAST` fails if the connector is still in STOPPING, so do not skip the wait.

2. Create live version: `ALTER OPENFLOW CONNECTOR <fqn> ADD LIVE VERSION FROM LAST;`
3. Edit: GET config → modify → PUT config (with OVERWRITE=TRUE)
4. Commit: `ALTER OPENFLOW CONNECTOR <fqn> COMMIT;`
5. Restart: `ALTER OPENFLOW CONNECTOR <fqn> START;`

**Note:** New connectors already have a live version. Only previously committed connectors need `ADD LIVE VERSION FROM LAST`.

**Replication continuity:** Stopping the connector pauses replication, but the binary log position is persisted in connector state. On restart, the connector resumes from the stored position — provided the binary log files have not expired or been purged on the source. Configure `binlog_expire_logs_seconds` to be longer than any expected downtime window.

### Abort Pending Changes

Discard a live version without applying:

```sql
ALTER OPENFLOW CONNECTOR <fqn> ABORT;
```

### Rollback to Previous Version

```sql
SHOW VERSIONS IN OPENFLOW CONNECTOR <fqn>;
-- Find the version name to rollback to
ALTER OPENFLOW CONNECTOR <fqn> SET DEFAULT_VERSION = 'VERSION$N';
```

### Delete Connector

**WARNING:** This is irreversible. Present the connector name and current state to the user and get explicit confirmation before running any of these commands:

> "This will permanently delete connector `<fqn>` and all its configuration. Are you sure?"

Do not proceed without a clear "yes" from the user.

Three-step process: stop → terminate → drop.

```sql
ALTER OPENFLOW CONNECTOR <fqn> STOP;
SELECT SYSTEM$WAIT_FOR_OPENFLOW_CONNECTORS(600, 'STOPPED', '<fqn>');

ALTER OPENFLOW CONNECTOR <fqn> TERMINATE;
SELECT SYSTEM$WAIT_FOR_OPENFLOW_CONNECTORS(600, 'DELETED', '<fqn>');

DROP OPENFLOW CONNECTOR <fqn>;
```

---

## Wait Functions

| Function | Args | Use Case |
|----------|------|----------|
| `SYSTEM$WAIT_FOR_STABLE_OPENFLOW_CONNECTORS(timeout, 'fqn')` | 2 | Wait for any stable state |
| `SYSTEM$WAIT_FOR_OPENFLOW_CONNECTORS(timeout, 'target_status', 'fqn')` | 3 | Wait for a specific status |

Use the 3-arg form when you know the expected state. Follow up with a DESCRIBE to confirm:

```sql
DESCRIBE OPENFLOW CONNECTOR <fqn>;
-- Check the status field
```

---

## Discovery Commands

| Operation | SQL |
|-----------|-----|
| List all connectors | `SHOW OPENFLOW CONNECTORS IN ACCOUNT` |
| Filter by name | `SHOW OPENFLOW CONNECTORS LIKE '%MYSQL%' IN ACCOUNT` |
| Connector details | `DESCRIBE OPENFLOW CONNECTOR <fqn>` |
| Available definitions | `SHOW OPENFLOW CONNECTOR DEFINITIONS` |
| List versions | `SHOW VERSIONS IN OPENFLOW CONNECTOR <fqn>` |
| List stage files | `LS '<version_location_uri>'` |

---

## Git Integration

Push connector config to a Git repository:

```sql
ALTER OPENFLOW CONNECTOR <fqn> PUSH TO '@GIT_REPO/branches/main/path/'
  USERNAME = '<git-user>'
  PASSWORD = '<git-token>'
  NAME = '<committer-name>'
  EMAIL = '<committer-email>'
  COMMENT = '<commit-message>';
```

Create a connector from a Git-stored config:

```sql
CREATE OPENFLOW CONNECTOR <fqn>
  IN RUNTIME <runtime_fqn>
  FROM '@GIT_REPO/branches/main/path/'
  COMMENT = 'Created from git';
```

---

## Security Model

Connector privileges are inherited from the parent runtime:

| Operation | Required Privilege |
|-----------|-------------------|
| CREATE | Schema: `CREATE OPENFLOW CONNECTOR` + Runtime: `USAGE` |
| SHOW, DESCRIBE | Runtime: `USAGE`, or Connector: `OWNERSHIP` |
| START, STOP, TERMINATE | Runtime: `USAGE` |
| PUT, COMMIT, ABORT | Runtime: `USAGE` |
| SET metadata, RENAME | Connector: `OWNERSHIP` |
| DROP | Connector: `OWNERSHIP` |

---

## Troubleshooting

For generic Gen2 connector diagnostics (event table queries, state machine issues, versioning problems), see the Gen2 section in `references/core-troubleshooting.md`.

This section covers MySQL-specific error patterns.

### Common Error Patterns

| Error | Cause | Fix |
|-------|-------|-----|
| `Access denied for user ... (using password: YES)` | Wrong credentials | Verify secret value and username |
| `Access denied for user ... REPLICATION SLAVE` | Missing replication privilege | Grant `REPLICATION SLAVE` and `REPLICATION CLIENT` |
| `Could not find first log file name in binary log index file` | Binary logging not enabled or log files expired | Enable `log_bin = on`; increase `binlog_expire_logs_seconds` |
| `Communications link failure` | Network unreachable or wrong host:port | Check EAI network rule covers host:3306 |
| `The binary log format is not ROW` | `binlog_format != row` | Set `binlog_format = row` and restart MySQL |
| `Column metadata is not available` | `binlog_row_metadata != full` | Set `binlog_row_metadata = full` (Azure: raise support ticket) |
| `Out of sort memory, consider increasing server sort buffer size` | `sort_buffer_size` too small | Increase `sort_buffer_size` to at least `4194304` |
| `No primary key defined` | Table lacks PK or NOT NULL unique index | Add primary key or appropriate unique index on source |
| `server_id is 0` | MySQL server has no server ID configured | Add `server-id = <n>` to `my.cnf` and restart |

**MariaDB-specific:**

| Error | Cause | Fix |
|-------|-------|-----|
| Connector cannot track binlog position correctly | `binlog_legacy_event_pos` not set | Set `binlog_legacy_event_pos = ON` on MariaDB and restart |

### START_FAILED

Common MySQL-specific causes:

- Missing MariaDB driver asset (must be uploaded to live version stage before commit)
- `binlog_format` is not `row` on the source
- Network rule does not include MySQL host:3306
- Replication user missing REPLICATION SLAVE or REPLICATION CLIENT privilege
- Source server has `server_id = 0`

Use the event table query from `references/core-troubleshooting.md` to get the specific error message.

---

## Guided Wizard Alternative

For first-time setup, the Openflow UI provides a Guided Wizard for the MySQL CDC connector. See `references/connector-wizard.md` for the wizard workflow.

The wizard produces a config.json that can be used as a template for subsequent SQL-based deployments.

---

## See Also

- `references/connector-main.md` — Connector routing and Gen1/Gen2 detection
- `references/connector-cdc.md` — Gen1 MySQL/MariaDB CDC (nipyapi)
- `references/connector-wizard.md` — Guided Wizard workflow
- `references/platform-eai.md` — External Access Integration for SPCS
- `references/core-guidelines.md` — SOM operations table
