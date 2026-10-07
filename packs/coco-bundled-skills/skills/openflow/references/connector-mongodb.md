---
name: openflow-connector-mongodb
description: MongoDB CDC connector for replicating MongoDB collections to Snowflake using change streams. Use for MongoDB ingestion, snapshot + incremental replication, collection state monitoring, and recovery. Each collection lands as an `id` + `data` (VARIANT) table plus `_SNOWFLAKE_*` metadata columns; deletes are soft. Requires a replica set or sharded cluster (MongoDB 4.4+); standalone instances are not supported.
---

<!--
MAINTAINER NOTE:

Routed from two locations (added in the same PR):

1. connector-main.md — "Connectors with Specific Documentation" table:
   | MongoDB, Mongo, document database replication, change streams | `mongodb` | `references/connector-mongodb.md` |

2. SKILL.md — Reference Index under "Connector Operations":
   | `references/connector-mongodb.md` | MongoDB CDC connector (change-stream replication, snapshot + incremental, collection state recovery) |
-->

# MongoDB CDC Connector

Replicates MongoDB collections to Snowflake in near-real-time. The connector runs a full initial snapshot per collection, then streams inserts, updates, and deletes from the MongoDB **change stream** and merges them into the destination tables.

**Note:** These operations modify service state. Apply the Check-Act-Check pattern from `references/core-guidelines.md`.

## Scope

This reference covers:
- The MongoDB connector (`mongodb`)
- Snapshot + change-stream (CDC) replication to Snowflake
- Collection replication state monitoring and recovery
- The landing schema: one table per collection (`id`, `data`) plus `_SNOWFLAKE_*` metadata columns; deletes are soft

MongoDB has a single source type, so there is no per-database branching (unlike `references/connector-cdc.md`) and no licensing decision (unlike `references/connector-oracle.md`). For other connectors, see `references/connector-main.md`.

## Workflow Summary

Complete ALL steps before starting the flow:

1. **Network Access** - runtime can reach MongoDB (EAI on SPCS; VPC egress + Atlas IP Access List on BYOC)
2. **Network Validate** - Test connectivity to the MongoDB endpoint(s)
3. **Deploy** - Deploy the `mongodb` flow
4. **Handle Parameters** - Configure source, destination, and ingestion parameters
5. **Asset Uploads** - None required (the MongoDB driver is bundled). Only the Snowflake private key file when using `KEY_PAIR`.
6. **Verify Controllers** - Run `verify_config` before enabling
7. **Enable Controllers** - Enable after verification passes
8. **Verify Processors** - Run `verify_config` after controllers enabled
9. **Start** - Start the flow
10. **Validate** - Confirm data is flowing

See [Deployment Workflow](#deployment-workflow) for detailed instructions.

---

## Flow Name

| Source | Flow Name | Root Process Group |
|--------|-----------|--------------------|
| MongoDB | `mongodb` | `MongoDB` |

Confirm the exact name in the registry before deploying.

## Collect Checklist

Gather this information from the user **before** proceeding with deployment.

### Source MongoDB Configuration (Required)

| Item | Description | Collected |
|------|-------------|-----------|
| Connection URI | `mongodb://host1[:port1][,...]/?[options]`. **No username/password in the URI** — set those separately. Snowflake recommends appending `readPreference=secondaryPreferred`. | [ ] |
| Authentication Mechanism | `SCRAM-SHA-256` (username/password) or `None` (unauthenticated). | [ ] |
| Username | MongoDB user (required for `SCRAM-SHA-256`). | [ ] |
| Password | (sensitive) — required for `SCRAM-SHA-256`. | [ ] |
| Authentication Source | Database holding the user's credentials (typically `admin`). | [ ] |
| Collections to Replicate | Comma-separated `db.collection` list and/or a regex. | [ ] |

### Snowflake Configuration (Required)

| Item | Description | Collected |
|------|-------------|-----------|
| Destination Database | Database for replicated data (**must already exist**). | [ ] |
| Snowflake Role | Role with CREATE SCHEMA / table privileges on the destination database. | [ ] |
| Snowflake Warehouse | Warehouse for running merge queries. | [ ] |
| Authentication Strategy | `SNOWFLAKE_MANAGED` (preferred, SPCS/BYOC execute-as role) or `KEY_PAIR` (BYOC). | [ ] |
| Destination Schema Pattern | Schema naming (default `${source.schema.name}` = MongoDB database name). **Cannot be changed after initial start** — decide now. | [ ] |
| Object Identifier Resolution | `CASE_INSENSITIVE` (default; uppercases names) or `CASE_SENSITIVE` (preserves casing). **Cannot be changed after initial start** — decide now. | [ ] |

### Source Prerequisites (User Must Complete)

| Prerequisite | Requirement |
|--------------|-------------|
| Deployment topology | **Replica set or sharded cluster** — required for change streams. Standalone instances are NOT supported. |
| MongoDB version | **4.4 or later.** |
| Database user | A user with the `readAnyDatabase` role on the `admin` database. The connector monitors change events at the **cluster level** (database-scoped change streams are not currently supported), so a cluster-wide read role is required. |
| Oplog retention | `oplogSizeMB` large enough to retain change history across connector downtime (e.g. `oplogSizeMB: 51200`). If the oplog rolls past the connector's resume point, a full re-sync is required. |
| Network | Network access from MongoDB to the Openflow Runtime. |
| Runtime size | Single-node runtime of at least **Medium** (use **Large** for high throughput or large collections). **Multi-node runtimes are not supported — set Min and Max nodes to 1**, as with the other database CDC connectors (the change-stream reader is pinned to one node). |

**Do not proceed until all required items are collected and prerequisites confirmed.**

---

## Supported Platforms and Limitations

| Area | Support |
|------|---------|
| MongoDB version | 4.4+ |
| Topology | Replica set or sharded cluster only (standalone unsupported — change streams require an oplog) |
| Authentication | Username/password via `SCRAM-SHA-256` (or `None`). X.509, LDAP, Kerberos, and AWS IAM are not supported. |
| Captured operations | Inserts, updates, and deletes (deletes are **soft** — see below). Collection DDL such as drop/rename is not propagated. |
| Availability | Preview Feature. Snowflake deployments: AWS, Azure, GCP commercial regions. BYOC: AWS commercial regions only. |

---

## Official Documentation

Refer to the official Snowflake documentation for current requirements:

- **About:** https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/mongodb/about
- **Connect to MongoDB:** https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/mongodb/connect
- **Set up the connector:** https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/mongodb/setup
- **Use the connector:** https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/mongodb/use

---

## Deployment Workflow

Follow the main workflow in `references/connector-main.md`. This section provides MongoDB-specific details for each step.

### 1. Network Access

The runtime must reach every MongoDB host in the connection URI on its port (default **27017**).

**SPCS:** **load** `references/platform-eai.md` and add an EAI rule for each MongoDB host:
- Self-managed: each replica-set/shard member host.
- Atlas: the `mongodb+srv://` string is accepted by the driver (though Snowflake's docs only show the `mongodb://` form). It resolves via DNS SRV to several `*.mongodb.net` hosts over TLS — allow each one, or use the standard `mongodb://` seed-list string Atlas also provides.

**BYOC:** no EAI (the runtime uses your own VPC networking), but reachability is **not** automatic — open security-group/VPC egress to the MongoDB hosts, and for **MongoDB Atlas** add the runtime's egress IP(s) to the Atlas **IP Access List** (a common silent blocker).

### 2. Network Validate

**Load** `references/ops-network-testing.md` and test connectivity to the MongoDB endpoint(s):

```python
targets = [
    {"host": "mycluster-shard-00-00.abcde.mongodb.net", "port": 27017, "type": "MongoDB"},
    # add every host listed in the connection URI / SRV record
]
```

With a `mongodb+srv://` URI, the driver resolves the SRV record to multiple member hosts — each must be reachable. A `SocketTimeoutException` after DNS success means the port is blocked (missing EAI rule on SPCS; security group or Atlas IP Access List on BYOC).

**If any tests fail:** stop and resolve the block before proceeding — EAI rules (SPCS), or VPC/security-group egress and the Atlas IP Access List (BYOC).

### 3. Deploy

**Load** `references/ops-flow-deploy.md`. Flow name: `mongodb` (deploy with `ci deploy_flow --flow mongodb`; it lands on the canvas as `MongoDB`).

### 4. Handle Parameters

Configure parameters in order:
1. **Source Parameters** - See [Source Parameters](#source-parameters) below
2. **Destination Parameters** - See [Destination Parameters](#destination-parameters) below; **load** `references/ops-snowflake-auth.md` for Snowflake authentication
3. **Ingestion Parameters** - See [Ingestion Parameters](#ingestion-parameters) below

Use `references/ops-parameters-main.md` for configuration commands.

Parameter names below are taken from the deployed flow, but always inspect the deployed parameter context before setting values (see `references/ops-parameters-inspect.md`); names can vary by flow version.

### 5. Asset Uploads

**None for MongoDB** — the driver is bundled. Only when using `KEY_PAIR` with a key *file*: upload `Snowflake Private Key File` as a reference asset (see `references/ops-parameters-assets.md`).

### 6–8. Verify Controllers → Enable → Verify Processors

Standard for all connectors — see `references/connector-main.md` (steps 9–11) and `references/ops-flow-lifecycle.md`:
`verify_config --verify_processors=false` → enable controllers → `verify_config --verify_controllers=false`. After enabling, check bulletins for MongoDB connection/auth errors.

### 9. Start

**Load** `references/ops-flow-lifecycle.md` to start the flow.

Run this connector on a **single-node runtime** (Min/Max nodes = 1), like the other database CDC connectors — the change-stream reader is pinned to one node (the NiFi primary, **not** the MongoDB primary).

### 10. Validate

After starting, validate data is flowing. See [Validate Data Flow](#validate-data-flow) below.

---

## Source Parameters

**Sensitive values:** Ask the user to provide directly. Cannot be read back once set. Never display these values — use `[REDACTED]` in confirmations.

`MongoDB Source Parameters` context:

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `MongoDB Connection URI` | Yes | — | `mongodb://host1[:port1][,...]/?[options]` (seed-list form; Atlas `mongodb+srv://` also accepted). **No credentials in the URI** (rejected by the connector). |
| `MongoDB Authentication Mechanism` | Yes | — | `SCRAM-SHA-256` or `None`. |
| `MongoDB Username` | For SCRAM | — | MongoDB user. |
| `MongoDB Password` | For SCRAM | — | Password (sensitive). |
| `MongoDB Authentication Source` | For SCRAM | — | Database holding credentials (typically `admin`). |

## Destination Parameters

`MongoDB Destination Parameters` context. For Snowflake authentication details, **load** `references/ops-snowflake-auth.md`.

> **Auth strategy:** SPCS → `SNOWFLAKE_MANAGED` (execute-as role); BYOC → `SNOWFLAKE_MANAGED` or `KEY_PAIR`. These are the connector's only valid values — `SNOWFLAKE_SESSION_TOKEN` is **not** accepted.
>
> **BYOC + `SNOWFLAKE_MANAGED`:** the runtime authenticates as a fixed service user with a fixed primary role (it is **not** auto-selected). `Snowflake Role` must be a role **granted to that user**, or `verify_config` fails with `Role '…' is not granted to this user`. Identify the user via `SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY` (filter `USER_NAME ILIKE '%OPENFLOW%'`, `FIRST_AUTHENTICATION_FACTOR = 'RSA_KEYPAIR'`), then either set `Snowflake Role` to a role it already has or `GRANT ROLE <role> TO USER <service-user>`. Grant that role `USAGE` on the destination database + warehouse and `CREATE SCHEMA` / `CREATE TABLE` (or `OWNERSHIP`) on the database.

**Sensitive values** (`Snowflake Private Key`, `Snowflake Private Key Password`): ask the user to provide directly; never display — use `[REDACTED]` in confirmations.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `Destination Database` | Yes | — | Target Snowflake database. Must already exist. |
| `Destination Schema Pattern` | No | `${source.schema.name}` | Schema naming pattern. Supports `${source.schema.name}` (MongoDB database) and `${source.table.name}` (collection). **Do not change after initial start** — to change it later, perform a full connector reset (stop flow, clear state, drop destination tables, restart), same as `Object Identifier Resolution`. |
| `Snowflake Authentication Strategy` | Yes | `SNOWFLAKE_MANAGED` | `SNOWFLAKE_MANAGED` (execute-as role) or `KEY_PAIR` (BYOC). |
| `Snowflake Account Identifier` | KEY_PAIR only | — | `[org-name]-[account-name]`. Blank for managed token. |
| `Snowflake Username` | KEY_PAIR only | — | Service user. Blank for managed token. |
| `Snowflake Private Key` / `Snowflake Private Key File` | KEY_PAIR only | — | PKCS8 PEM. Provide one. `Snowflake Private Key` is **sensitive** (inline key); the file variant is uploaded as a reference asset. |
| `Snowflake Private Key Password` | KEY_PAIR only | — | If the key is encrypted (sensitive). |
| `Snowflake Connection Strategy` | KEY_PAIR only | `STANDARD` | `STANDARD` or `PRIVATE_CONNECTIVITY` (PrivateLink). |
| `Snowflake Role` | Yes | — | Managed token: execute-as role (SPCS) or a role granted to the BYOC service user (see Auth-strategy note above). KEY_PAIR: service-user role. |
| `Snowflake Warehouse` | Yes | — | Warehouse for merge queries. |

## Ingestion Parameters

`MongoDB Ingestion Parameters` context (inherits Source + Destination):

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `Included Collection Names` | No* | — | Comma-separated fully-qualified names, e.g. `sales.orders, sales.customers`. |
| `Included Collection Regex` | No* | — | Regex against fully-qualified names, e.g. `sales\..*` for all collections in the `sales` database. |
| `Merge Task Schedule CRON` | No | `* * * * * ?` | Quartz CRON controlling Journal→Destination merges. Default is continuous; set a schedule to bound warehouse runtime. |
| `Object Identifier Resolution` | No | `CASE_INSENSITIVE` | `CASE_INSENSITIVE` (uppercases names) or `CASE_SENSITIVE` (preserves casing). **Do not change after initial start.** |

*Provide at least one of `Included Collection Names` or `Included Collection Regex` (combined as a union). **If neither is set, the connector matches zero collections and replicates nothing** — it does not default to replicating everything.

**Journal tables:** the connector writes change events to internally managed `*_JOURNAL_*` tables and merges them into the destination on the CRON schedule. **Do not modify, query-lock, or drop the journal tables** — manual changes disrupt synchronization and can compromise data integrity.

### Object Identifier Resolution

Controls how database/collection/field names map to Snowflake identifiers. MongoDB defaults to `CASE_INSENSITIVE` — unlike the other Openflow database connectors (Postgres, MySQL, …), which default to `CASE_SENSITIVE`. Call this out so users aren't surprised.

| Value | Behavior | Use When |
|-------|----------|----------|
| `CASE_INSENSITIVE` (default) | Uppercases names (e.g. `SALES.ORDERS`) | You prefer Snowflake-native naming; allows unquoted SQL |
| `CASE_SENSITIVE` | Preserves source casing (e.g. `"sales"."orders"`) | You want an exact match to source; requires quoted identifiers in SQL |

**WARNING:** Cannot be changed after replication has started without a full connector reset (stop flow, clear state, drop destination tables, restart). Confirm the user's choice before initial deployment.

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

Each collection lands as **one table** in the schema chosen by `Destination Schema Pattern` (default: the MongoDB database name). Every table has the same shape:

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT | The MongoDB document `_id`, serialized as text (primary key). |
| `data` | VARIANT | The full MongoDB document as semi-structured JSON. |
| `_SNOWFLAKE_DELETED` | BOOLEAN | Soft-delete flag — set to `TRUE` when the source document is deleted (see below). |
| `_SNOWFLAKE_INSERTED_AT` | TIMESTAMP_NTZ | When the connector first wrote the row. |
| `_SNOWFLAKE_UPDATED_AT` | TIMESTAMP_NTZ | When the connector last updated the row. |

`_SNOWFLAKE_INSERTED_AT` and `_SNOWFLAKE_UPDATED_AT` are observed from the connector flow; only `_SNOWFLAKE_DELETED` is documented in the public docs.

**Deletes are soft.** A delete in MongoDB does **not** remove the Snowflake row — the connector sets `_SNOWFLAKE_DELETED = TRUE` and leaves the row in place. Queries that should reflect the live collection must filter `WHERE NOT _SNOWFLAKE_DELETED`.

```sql
-- With Object Identifier Resolution = CASE_INSENSITIVE (default), names are uppercased
SHOW SCHEMAS IN DATABASE <destination_database>;
SHOW TABLES IN SCHEMA <destination_database>.<source_db>;

SELECT COUNT(*) FROM <destination_database>.<source_db>.<collection>;

-- The document body lives in the VARIANT column; query fields with path notation.
-- Exclude soft-deleted rows to match the live collection.
SELECT id, data:name::string AS name, data:address.city::string AS city
FROM   <destination_database>.<source_db>.<collection>
WHERE  NOT _SNOWFLAKE_DELETED
LIMIT 5;
```

With `CASE_SENSITIVE`, quote the lowercase identifiers (e.g. `"sales"."orders"`).

### Step 3: Monitor Initial Replication

For large collections, the initial snapshot may take time. Snapshots run sequentially per collection; incremental change-stream events for a collection are buffered until its snapshot completes. Check collection state to monitor progress — see [CDC Health Monitoring](#cdc-health-monitoring).

---

## CDC Health Monitoring

### Collection Replication State

The connector tracks per-collection state in a `StandardTableStateService` (the **`Collection State Store`** controller). Use the component state operations to inspect it.

**For detailed state management commands, see `references/ops-component-state.md`.**

```bash
# Find the state service controller ID (named "Collection State Store")
nipyapi --profile <profile> canvas list_all_controllers "<pg-id>" | \
  jq '.[] | select(.component.type | contains("TableState")) | {id: .id, name: .component.name}'

# Get state entries
nipyapi --profile <profile> canvas get_controller_state "<collection-state-service-id>"
```

### Replication Status Values

| Status | Meaning |
|--------|---------|
| `NEW` | Collection discovered, replication not started |
| `SNAPSHOT_REPLICATION` | Capturing initial snapshot |
| `INCREMENTAL_REPLICATION` | Streaming change-stream events |
| `FAILED` | Cannot replicate (see failure reason) |

### Resume Position

The change-stream reader stores a MongoDB **resume token** in NiFi cluster state and resumes from it on restart. If the oplog has rolled past that token (downtime longer than oplog retention), the stream cannot resume and the collection must be re-synced — see [Recovering from FAILED State](#recovering-from-failed-state).

---

## Recovering from FAILED State

**First, triage the failure.** Inspect the collection's failure reason via bulletins or the `Collection State Store` (see [CDC Health Monitoring](#cdc-health-monitoring)), then branch:

- **Transient / recoverable** (authentication failure, network/EAI block, missing privilege): fix the underlying cause — see [Troubleshooting](#troubleshooting) — and let the connector retry (restart the flow if needed). The destructive steps below are **not** required.
- **Irrecoverable** (oplog rolled past the resume token, incompatible schema change): the collection must be re-synced via the remove → drop → re-add path below.

**WARNING:** The steps below include destructive, irreversible operations (parameter changes and `DROP TABLE`). Each state-modifying step has a **⚠️ MANDATORY CHECKPOINT** — present the action to the user and **wait for explicit confirmation. NEVER proceed without it.**

### Step 1: Remove Collection from Replication

**⚠️ MANDATORY CHECKPOINT:** this changes connector parameters. Confirm with the user and **wait for explicit approval before proceeding.**

Then update parameters to exclude the failed collection. Ensure BOTH `Included Collection Names` AND `Included Collection Regex` exclude it. Use `references/ops-parameters-main.md` for the commands.

### Step 2: Verify Collection Removed from State

Wait for the change to propagate, then re-check the controller state (above). The failed collection should no longer appear.

**Note:** Other collections continue processing. Do NOT purge flow files unless doing a full reset.

### Step 3: Drop Destination Table in Snowflake

**⚠️ MANDATORY CHECKPOINT:** ask the user — "This will DROP the table from Snowflake. This is irreversible. Proceed?" **Wait for explicit confirmation. NEVER run the `DROP` without it.**

```sql
-- Match the case of Object Identifier Resolution
DROP TABLE <destination_database>.<source_db>.<collection>;
```

### Step 4: Re-add Collection to Replication

**⚠️ MANDATORY CHECKPOINT:** ask the user — "Re-adding this collection will trigger a full snapshot reload. Proceed?" **Wait for explicit confirmation before changing parameters.**

Then update the inclusion parameters to add the collection back.

---

## Known Issues

### Standalone MongoDB Not Supported

The connector relies on change streams, which require an oplog available only on a replica set or sharded cluster. Point-in-time enable: convert a standalone to a single-node replica set, or use Atlas.

### Oplog Rolled Past Resume Token

If connector downtime exceeds oplog retention, the stored resume token is no longer in the oplog and the change stream cannot resume. The affected collection must be re-synced (see [Recovering from FAILED State](#recovering-from-failed-state)). Prevent by sizing `oplogSizeMB` for your peak downtime window.

### StandardPrivateKeyService INVALID on SPCS or BYOC with Managed Token

Expected — the `Snowflake Private Key Service` controller is unused unless you use `KEY_PAIR` auth, so it shows INVALID (and inflates `verify_config`'s `failed_count`). Impact: none. See `references/known-issues-common.md`.

---

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Controller invalid: credentials in URI | URI contains `@` (any embedded credentials) | Remove credentials from `MongoDB Connection URI`; set `MongoDB Username` / `MongoDB Password` instead |
| Authentication failed | Wrong credentials or auth source | Verify user/password; confirm `MongoDB Authentication Source` (usually `admin`) |
| `UnknownHostException` / `SocketTimeoutException` | Missing EAI rule (SPCS); not all SRV hosts reachable | Add every member host (default port 27017) to the network rule |
| Change stream error / "not supported" | Standalone MongoDB | Use a replica set or sharded cluster |
| Collection in `FAILED` after downtime | Oplog rolled past resume token | Re-sync the collection; increase `oplogSizeMB` |
| No collections replicated | Inclusion filters don't match | Check `Included Collection Names` (`db.collection`) and `Included Collection Regex` against fully-qualified names |
| Destination write fails | Snowflake role lacks privileges | Grant CREATE SCHEMA / table privileges on the destination database |
| `Snowflake Private Key Service` bulletins (SPCS, or BYOC with managed token) | Expected — service unused unless `KEY_PAIR` auth | Ignore |

Reference `references/core-troubleshooting.md` for general patterns.

---

## Next Step

After deployment and configuration, return to `references/connector-main.md` or the calling workflow.

## See Also

- `references/connector-main.md` - Connector workflow overview
- `references/connector-cdc.md` - PostgreSQL/MySQL CDC connectors (shared CDC patterns)
- `references/ops-component-state.md` - Inspect and clear collection replication state
- `references/ops-snowflake-auth.md` - Snowflake destination authentication
- `references/platform-eai.md` - Network access for SPCS
- `references/ops-network-testing.md` - Network connectivity testing
- `references/ops-parameters-main.md` - Parameter configuration
- `references/core-troubleshooting.md` - Error patterns
