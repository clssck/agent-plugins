---
name: openflow-connector-postgres-gen2
description: Gen2 PostgreSQL CDC connector deployed via SQL API. Covers creation, configuration, lifecycle management, and troubleshooting for connectors created from the OPENFLOW_POSTGRES_CDC definition.
---

# Gen2 PostgreSQL CDC Connector

Deploy and manage PostgreSQL CDC connectors using the Openflow SQL API. This reference covers connectors created from the `OPENFLOW_POSTGRES_CDC` definition.

**Note:** This reference is for Gen2 (SQL API) connectors only. For Gen1 (nipyapi/registry) PostgreSQL connectors, see `references/connector-cdc.md`.

**Requires:** SOM-enabled account (SQL surface: the SOM probe `SHOW OPENFLOW CONNECTOR DEFINITIONS` returns rows; CLI: `som_enabled: true` in cache). This workflow uses SQL only — no Python/nipyapi required. If the account uses the legacy model, this reference does not apply.

---

## Prerequisites

If any prerequisite Snowflake objects are missing — roles, destination DB, secret,
network rule, EAI — load `references/connector-prereqs-gen2.md` first. It covers
infrastructure discovery and creation with safe SQL patterns.

Source-side Postgres prerequisites (WAL, publication, replication user, PKs) are
documented in the [Source-Side Prerequisites](#source-side-prerequisites) section below.

If all prerequisites are in place, verify the following before proceeding:

| Object | Verification |
|--------|-------------|
| Runtime (ACTIVE, MEDIUM+, max 1 node) | `DESCRIBE OPENFLOW RUNTIME <db>.<schema>.<name>` — confirm `status = ACTIVE` |
| EAI attached to runtime (SPCS only) | `SHOW PARAMETERS LIKE 'EXTERNAL_ACCESS_INTEGRATIONS' IN OPENFLOW RUNTIME <fqn>` |
| Network rule covers Postgres host:port (SPCS only) | `DESCRIBE NETWORK RULE <db>.<schema>.<rule>` — confirm `value_list` includes `<host>:<port>` |
| Secret type = GENERIC_STRING | `DESCRIBE SECRET <db>.<schema>.<secret>` — confirm `secret_type = GENERIC_STRING` |
| `CREATE OPENFLOW CONNECTOR` privilege on schema | `SHOW GRANTS ON SCHEMA <db>.<schema>` |
| Execute-as role has READ on secret | `SHOW GRANTS ON SECRET <db>.<schema>.<secret>` |

---

## Postgres CDC Constraints

Surface these to the user before proceeding — they affect runtime selection
and table eligibility:

- Runtime must be at least **MEDIUM** — see [Runtime sizing](https://docs.snowflake.com/user-guide/data-integration/openflow/connectors/postgres/setup#label-postgres-runtime-sizing)
- Multi-node runtimes are not supported — configure with Min nodes and Max nodes set to `1`
- Tables need a supported identity key (primary key with `REPLICA IDENTITY DEFAULT`, or a unique index with `REPLICA IDENTITY USING INDEX`) for UPDATE and DELETE replication. Tables without either can replicate INSERT operations only.
- JDBC driver must be available for upload during wizard or PUT
- Only username/password authentication with PostgreSQL is supported

---

## Source-Side Prerequisites

These steps must be performed on the source PostgreSQL instance. **Present
them to the user as instructions — do not execute them yourself.** Ask the
user to confirm each item before proceeding to connector creation.

### WAL Level = Logical

> ```sql
> SHOW wal_level;
> ```
> Required value: `logical`. If it shows `replica` or `minimal`:
> ```sql
> ALTER SYSTEM SET wal_level = 'logical';
> -- Then restart PostgreSQL.
> ```
> Managed service equivalents:
> - **AWS RDS / Aurora:** Parameter group → `rds.logical_replication = 1` → reboot
> - **GCP Cloud SQL:** `cloudsql.logical_decoding = on` → restart
> - **Azure:** Server parameters → `wal_level = logical` → restart

### Replication Privileges

> ```sql
> SELECT rolreplication, rolcanlogin FROM pg_roles WHERE rolname = '<username>';
> ```
> Both must return `t`. If not:
> ```sql
> ALTER ROLE <username> WITH REPLICATION LOGIN;
> GRANT SELECT ON ALL TABLES IN SCHEMA <schema> TO <username>;
> ALTER DEFAULT PRIVILEGES IN SCHEMA <schema> GRANT SELECT ON TABLES TO <username>;
> ```

### Publication

> ```sql
> SELECT pubname, puballtables FROM pg_publication;
> ```
> If none exists:
> ```sql
> CREATE PUBLICATION openflow_pub FOR ALL TABLES
>   WITH (publish_via_partition_root = true);
> -- Or for specific tables:
> CREATE PUBLICATION openflow_pub FOR TABLE public.customers, public.orders
>   WITH (publish_via_partition_root = true);
> ```
> `publish_via_partition_root = true` is required for partitioned tables.

### Identity Key Configuration

> Tables need a supported identity key for UPDATE and DELETE replication:
> - **Option A:** Primary key with `REPLICA IDENTITY DEFAULT` (most common)
> - **Option B:** Unique index with `REPLICA IDENTITY USING INDEX`
>
> Tables with neither can still replicate INSERT operations, but UPDATEs and
> DELETEs will not be captured.
>
> Check current configuration:
> ```sql
> -- Tables with primary keys:
> SELECT tc.table_schema, tc.table_name
> FROM information_schema.table_constraints tc
> WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = '<schema>';
>
> -- Replica identity setting (d=default, i=index, f=full, n=nothing):
> SELECT c.relname, c.relreplident
> FROM pg_catalog.pg_class c
> JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
> WHERE n.nspname = '<schema>' AND c.relkind = 'r';
> ```
>
> For tables without a primary key, see [Configure replica identity for tables
> without a primary key](https://docs.snowflake.com/user-guide/data-integration/openflow/connectors/postgres/setup#label-postgres-configure-replica-identity-using-index).

### Source Network Access

> The PostgreSQL instance must be reachable from the Openflow runtime.
> Ask the user to confirm that connectivity between the runtime and the
> source database is in place. Network configuration varies by deployment
> type (SPCS vs BYOC) and customer environment — do not prescribe specific
> firewall rules. If connectivity fails later, load `references/platform-eai.md`
> for SPCS network troubleshooting or `references/ops-network-testing.md`
> to validate.

### Confirm Source-Side Readiness

Ask the user to confirm all source-side items before proceeding:
- WAL level = logical (restarted if changed)
- Replication user has correct privileges
- Publication created
- All target tables have primary keys
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

**Transitional states** (`CREATING`, `STARTING`, `STOPPING`): Do not issue commands while in these states — wait for a stable state first.

**Stable states:** `STOPPED`, `RUNNING`, `START_FAILED`, `DELETED`

---

## Collect Checklist

Gather before starting. Items correspond to config.json sections:

### Source (Required)

| Item | Config Property | Example |
|------|----------------|---------|
| Postgres JDBC URL | `Source Database Connection URL` | `jdbc:postgresql://host:5432/db?sslmode=require` |
| Postgres username | `Source Database User` | `replication_user` |
| Postgres password secret | `Source Database Password` | `<db>.<schema>.<secret_name>` |
| Publication name | `Source Database Publication Name` | `my_publication` |
| JDBC driver JAR | `Source Database Driver` (asset) | `postgresql-42.7.10.jar` |
| Replication slot (optional) | `Replication Slot Name` | `my_slot` (auto-created if omitted) |

### Table Selection (at least one required)

| Item | Config Property | Example |
|------|----------------|---------|
| Table names (explicit) | `Included Comma Separated Source Table Names` | `"schema"."table1","schema"."table2"` |
| Table regex (alternative) | `Included Table Regex` | `public\.auto_.*` |
| Column filter (optional) | `Column Filter JSON` | `[{"schema":"public","table":"orders","excluded":["internal_note"]}]` |

Tables can be selected by explicit name, regex, or both (union of matches).

### Destination (Required)

| Item | Config Property | Example |
|------|----------------|---------|
| Destination database | `Snowflake Destination Database` | `<destination_database>` |
| Warehouse | `Snowflake Warehouse` | `<warehouse>` |
| Auth strategy | `Snowflake Authentication Strategy` | `SNOWFLAKE_MANAGED` (recommended) |
| Object Identifier Resolution | `Object Identifier Resolution` | `CASE_INSENSITIVE` or `CASE_SENSITIVE` |
| Oversized Value Strategy (optional) | `Oversized Value Strategy` | `Set Null` |
| Destination Schema Pattern (optional) | `Destination Schema Pattern` | `${source.schema.name}` (default) |

For KEY_PAIR authentication (BYOC alternative to SNOWFLAKE_MANAGED), **load** `references/ops-snowflake-auth.md` for additional required parameters.

### Tuning (Optional)

| Item | Config Property | Default |
|------|----------------|---------|
| Merge schedule | `Merge Task Schedule CRON` | `* * * * * ?` (every second) |
| Concurrent snapshots | `Concurrent Snapshot Queries` | `2` |

### Migration (Required)

| Item | Config Property | Options |
|------|----------------|---------|
| Ingestion type | `Ingestion Type` | `full` (snapshot + CDC) or `incremental` (CDC only, for reinstalls) |

**Do not proceed until all required items are collected.**

---

## Deployment Workflow

### 1. Create Connector

Before executing, present the resolved values to the user and get confirmation:
> "I'll create connector `<connector_name>` in runtime `<runtime_name>` using the OPENFLOW_POSTGRES_CDC definition. Proceed?"

```sql
CREATE OPENFLOW CONNECTOR <db>.<schema>.<connector_name>
  IN RUNTIME <db>.<schema>.<runtime_name>
  FROM DEFINITION OPENFLOW_POSTGRES_CDC
  DISPLAY_NAME = '<display name>';
```

Wait for creation to complete:

```sql
SELECT SYSTEM$WAIT_FOR_OPENFLOW_CONNECTORS(600, 'STOPPED', '<db>.<schema>.<connector_name>');
```

New connectors are created with a live version automatically — no need to call `ADD LIVE VERSION FROM LAST`.

### 2. Upload JDBC Driver

The Postgres CDC connector requires the PostgreSQL JDBC driver JAR.

First, find the live version stage URI:

```sql
DESCRIBE OPENFLOW CONNECTOR <db>.<schema>.<connector_name>;
-- Read the live_version_location_uri field
```

Upload the driver (requires SnowSQL or Snow CLI session for file operations):

```sql
PUT 'file:///path/to/postgresql-42.7.10.jar' '<live_version_location_uri>' AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
```

### 3. Configure config.json

Download the template config, edit it, and re-upload:

```sql
GET '<live_version_location_uri>/config.json' 'file:///path/to/local/dir/';
```

Edit the config.json locally (see [Config Structure](#config-structure) below), then upload:

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

Check ingestion database for replicated tables.

---

## Config Structure

The config.json has this format:

```json
{
  "configFormatVersion": 1,
  "connectorDefinitionId": "OPENFLOW_POSTGRES_CDC",
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
| `STRING_LITERAL` | `{"valueType": "STRING_LITERAL", "value": "..."}` | Connection URL, username |
| `SECRET_REFERENCE` | `{"valueType": "SECRET_REFERENCE", "fullyQualifiedSecretName": "..."}` | Password |
| `ASSET_REFERENCE` | `{"valueType": "ASSET_REFERENCE", "assetIds": ["filename.jar"]}` | JDBC driver |

### SECRET_REFERENCE Format

Use the direct `database.schema.secret_name` path:

```json
"Source Database Password": {
  "valueType": "SECRET_REFERENCE",
  "fullyQualifiedSecretName": "<db>.<schema>.<secret_name>"
}
```

### ASSET_REFERENCE Binding

When uploading an asset file (like the JDBC driver), set the corresponding `ASSET_REFERENCE` property's `assetIds` to the uploaded filename:

```json
"Source Database Driver": {
  "valueType": "ASSET_REFERENCE",
  "assetIds": ["postgresql-42.7.10.jar"]
}
```

### Configuration Sections

| Section | Key Properties |
|---------|---------------|
| **Source** | Connection URL, User, Password (secret), Driver (asset), Publication Name |
| **Replication table schema** | Included table names (comma-separated `"schema"."table"` format) |
| **Replication columns** | Column Filter JSON (optional, exclude specific columns) |
| **Destination authentication** | Snowflake Authentication Strategy (`SNOWFLAKE_MANAGED` recommended) |
| **Destination details** | Destination Database, Warehouse, Object Identifier Resolution, Oversized Value Strategy |
| **Tuning** | Merge Task Schedule CRON, Concurrent Snapshot Queries |
| **Migration** | Ingestion Type (`full` or `incremental`), Replication Slot Name (optional) |

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
   `ADD LIVE VERSION FROM LAST` fails if the connector is still in `STOPPING`, so do not skip the wait.
2. Create live version: `ALTER OPENFLOW CONNECTOR <fqn> ADD LIVE VERSION FROM LAST;`
3. Edit: GET config → modify → PUT config (with `OVERWRITE=TRUE`)
4. Commit: `ALTER OPENFLOW CONNECTOR <fqn> COMMIT;`
5. Restart: `ALTER OPENFLOW CONNECTOR <fqn> START;`

**Note:** New connectors already have a live version. Only existing (previously committed) connectors need `ADD LIVE VERSION FROM LAST`.

**Replication continuity:** Stopping a Postgres CDC connector pauses replication, but the PostgreSQL replication slot preserves the stream position — on restart the connector resumes from where it left off with no data gap, provided the slot was not dropped or allowed to expire on the source side.

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

**WARNING:** This is irreversible. Present the connector name and current state
to the user and get explicit confirmation before running any of these commands:
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

Two variants are available:

| Function | Args | Use Case |
|----------|------|----------|
| `SYSTEM$WAIT_FOR_STABLE_OPENFLOW_CONNECTORS(timeout, 'fqn')` | 2 | Wait for any stable state |
| `SYSTEM$WAIT_FOR_OPENFLOW_CONNECTORS(timeout, 'target_status', 'fqn')` | 3 | Wait for a specific status |

**Recommendation:** Use the 3-arg form when you know the expected state (START → RUNNING, STOP → STOPPED). Use the 2-arg STABLE form for generic "wait until not transitional" scenarios.

As defence-in-depth, follow up with a DESCRIBE to confirm the actual status:

```sql
DESCRIBE OPENFLOW CONNECTOR <fqn>;
-- Check the status field
```

---

## Discovery Commands

| Operation | SQL |
|-----------|-----|
| List all connectors | `SHOW OPENFLOW CONNECTORS IN ACCOUNT` |
| Filter connectors | `SHOW OPENFLOW CONNECTORS LIKE '%POSTGRES%' IN ACCOUNT` |
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
|-----------|--------------------|
| CREATE | Schema: `CREATE OPENFLOW CONNECTOR` + Runtime: `USAGE` |
| SHOW, DESCRIBE | Runtime: `USAGE`, or Connector: `OWNERSHIP` |
| START, STOP, TERMINATE | Runtime: `USAGE` |
| PUT, COMMIT, ABORT | Runtime: `USAGE` |
| SET metadata, RENAME | Connector: `OWNERSHIP` |
| DROP | Connector: `OWNERSHIP` |

---

## Troubleshooting

For generic Gen2 connector diagnostics (event table queries, state machine issues, versioning problems), see the Gen2 section in `references/core-troubleshooting.md`.

This section covers **Postgres-specific** error patterns.

### Common Error Patterns

| Error in `formattedMessage` | Cause | Fix |
|-----------------------------|-------|-----|
| `FATAL: database "X" does not exist` | Wrong database in JDBC URL | Edit config: fix `Source Database Connection URL` |
| `FATAL: password authentication failed` | Wrong credentials | Edit config: fix secret reference or secret value |
| `PSQLException: Connection refused` | Network issue or wrong host | Check EAI network rules include host:port |
| `No publication exists` | Publication not created on source | Create publication on Postgres source |
| `Cannot create PoolableConnectionFactory` | JDBC driver issue or connection failure | Verify driver JAR uploaded and connection URL correct |
| `FATAL: no pg_hba.conf entry` | Source doesn't allow connections from runtime IP | Update Postgres pg_hba.conf or security group |

### START_FAILED

Common Postgres-specific causes:
- Missing JDBC driver asset (must be uploaded to live version stage before commit)
- Invalid secret reference (`fullyQualifiedSecretName` must use format `<db>.<schema>.<secret_name>`)
- Network rule doesn't include Postgres host:port
- Postgres publication doesn't exist or user lacks replication privileges
- Source database requires SSL but URL lacks `?sslmode=require`

Use the event table query from `references/core-troubleshooting.md` to get the specific error message.

---

## Guided Wizard Alternative

For first-time setup, the Openflow UI provides a Guided Wizard for the Postgres CDC connector. See `references/connector-wizard.md` for the wizard workflow.

The wizard produces a config.json that can be used as a template for subsequent SQL-based deployments.

---

## See Also

- `references/connector-main.md` — Connector routing and Gen1/Gen2 detection
- `references/connector-cdc.md` — Gen1 PostgreSQL/MySQL CDC (nipyapi)
- `references/connector-wizard.md` — Guided Wizard workflow
- `references/platform-eai.md` — External Access Integration for SPCS
- `references/core-guidelines.md` — SOM operations table
