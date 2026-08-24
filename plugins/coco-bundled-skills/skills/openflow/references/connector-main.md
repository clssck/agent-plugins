---
name: openflow-connector-main
description: Deploy and configure Snowflake Openflow connectors. Use for connector deployment workflow and routing to connector-specific documentation.
---

# Connectors

Connectors are pre-built flows supplied and supported by Snowflake. This reference provides routing to connector-specific documentation and the standard deployment workflow.

## Scope

This reference covers:
- Routing to connector-specific documentation
- Standard connector deployment workflow
- General connector configuration guidance

---

## Generation Detection (Gen1 vs Gen2)

Before routing to a connector-specific reference, determine which generation applies **and** whether the current surface can perform it (see `SKILL.md` Surface Detection). This controls the entire deployment and management workflow.

**Surface gate (apply first):**
- **Snowsight (SQL-only):** only the Gen2 (SQL) path is possible. If the request resolves to Gen1 (below), **decline**: "That connector uses the Gen1 registry workflow via the NiFi API (nipyapi), which isn't available in Snowsight. Run it from the Openflow UI or in Cortex Code CLI/Desktop with nipyapi configured." Do not load nipyapi references.
- **CLI:** both paths available. For a Gen2 connector, proceed on the SQL path **without** nipyapi setup (defer it); load `references/core-session-cli.md` only if the work later needs the NiFi canvas.

**Generation detection steps:**

1. Determine `som_enabled`:
   - **SQL surface:** from the `references/core-session-sql.md` probe (`SHOW OPENFLOW CONNECTOR DEFINITIONS` returned rows = SOM enabled).
   - **CLI surface:** from the cache (or the probe if no cache):
     ```bash
     jq '.som_enabled' ~/.snowflake/cortex/memory/openflow_infrastructure_*.json
     ```
2. If SOM is not enabled → **Gen2 is not available.** All connector operations use the Gen1 path (nipyapi) — CLI only; decline on Snowsight. Skip to [Connector Routing](#connector-routing).
3. **CLI only:** if `null` or missing (cache predates SOM support) → Load `references/bootstrap-discovery.md` (or re-run the probe) to refresh before proceeding.
4. If SOM is enabled → check if the requested connector type has a Gen2 definition:
   ```sql
   SHOW OPENFLOW CONNECTOR DEFINITIONS;
   ```
5. If the requested connector type appears in the definitions list → **Gen2 path** (SQL-based)
6. If not → **Gen1 path** (nipyapi registry-based) — CLI only; decline on Snowsight

| Generation | Workflow | Reference |
|------------|----------|-----------|
| **Gen2** (SQL API) | `CREATE OPENFLOW CONNECTOR ... FROM DEFINITION` | `references/connector-postgres-gen2.md`, `references/connector-mysql-gen2.md` |
| **Gen1** (NiFi Registry) | Deploy via nipyapi from Snowflake Connector Registry | Continue below to [Connector Routing](#connector-routing) |

**Gen2 path note:** Once routed to the connector's Gen2 reference
(`connector-postgres-gen2.md` or `connector-mysql-gen2.md`), the complete
workflow is in that reference — the 14-step Connector Workflow further below
does not apply to Gen2. Before running `CREATE OPENFLOW CONNECTOR`, verify
prerequisites with `references/connector-prereqs-gen2.md`.

**Available Gen2 definitions:** Run `SHOW OPENFLOW CONNECTOR DEFINITIONS` to see which connector types support the Gen2 SQL workflow on this account.

**Important:** Gen1 connectors that are already deployed remain managed via nipyapi. They are not automatically migrated to Gen2 and do not appear in `SHOW OPENFLOW CONNECTORS`.

**Legacy account message:** If a user requests a Gen2 connector on a legacy account, inform them: "Gen2 SQL connectors require the Snowflake Object Model which is not enabled on this account. I can deploy the connector using the Gen1 (registry-based) workflow instead."

---

## Connector Routing

**Route first, then follow the workflow.** Load the connector-specific reference before starting deployment.

### Connectors with Specific Documentation

These connectors have detailed reference documentation with parameter guides, prerequisites, and troubleshooting.

| User Intent | Flow Name | Reference |
|-------------|-----------|-----------|
| PostgreSQL, Postgres, CDC, database replication | Gen2: `OPENFLOW_POSTGRES_CDC` / Gen1: `postgresql` | Gen2: `references/connector-postgres-gen2.md` / Gen1: `references/connector-cdc.md` |
| MySQL, MariaDB, CDC, database replication | Gen2: `OPENFLOW_MYSQL_CDC` / Gen1: `mysql` | Gen2: `references/connector-mysql-gen2.md` / Gen1: `references/connector-cdc.md` |
| SQL Server, MSSQL, CDC, database replication | `sqlserver-multidatabase` | `references/connector-sqlserver.md` |
| Oracle, Oracle CDC, Oracle database replication | `oracle-embedded-license` or `oracle-independent-license` | `references/connector-oracle.md` |
| MongoDB, Mongo, document database replication, change streams | `mongodb` | `references/connector-mongodb.md` |
| Google Drive, Google Drive Cortex, unstructured data | `unstructured-google-drive-cdc` | `references/connector-googledrive.md` |
| SharePoint, SharePoint Cortex, SharePoint to Stage | (see reference for variants) | `references/connector-sharepoint-simple.md` |
| HubSpot | `hubspot` | `references/connector-hubspot.md` |
| Jira, Atlassian Jira, Jira Cloud | `jira-connector-core` (required) and `jira-connector-agile` (optional) | `references/connector-jira.md` |
| Kafka, Kafka high performance, Kafka customization, Kafka auth, Kafka transformation, Kafka modification | `kafka-high-performance` | `references/connector-kafka.md` |
| Kinesis, Amazon Kinesis, Kinesis Data Streams, Kinesis setup, set up Kinesis, Kinesis connector | `kinesis-high-performance` | `references/connector-kinesis-main.md` |
| Shopify, Shopify store, e-commerce | `shopify-connector` | `references/connector-shopify.md` |

### Connectors without Specific Documentation

These connectors are available but we do not have detailed skill documentation. We can assist with deployment and general configuration using the standard workflow, but may not have connector-specific troubleshooting or parameter guidance.

**Be transparent with the user:** "I don't have specific documentation for this connector, but I can help you deploy and configure it using the standard workflow. You may want to consult the Snowflake documentation for connector-specific details."

| Category | Flow Name | Common Names |
|----------|-----------|--------------|
| **Advertising** | `amazon-ads` | Amazon Ads |
| | `google-ads` | Google Ads |
| | `linkedin-ads` | LinkedIn Ads |
| | `meta-ads` | Meta Ads, Facebook Ads |
| **CRM** | `salesforce-bulk-api` | Salesforce, Salesforce Bulk API |
| | `microsoft-dataverse` | Dataverse, Microsoft Dataverse, Dynamics 365 |
| **Document Storage** | `box-admin` | Box Admin |
| | `box-to-snowflake-metadata` | Box Metadata |
| | `google-drive-admin` | Google Drive Admin |
| | `google-drive-no-cortex` | Google Drive (no Cortex) |
| | `unstructured-box-to-stage-no-cortex` | Box to Stage |
| **Cortex Connect** | `unstructured-box-cdc` | Box CDC, Box Cortex |
| | `unstructured-slack-cdc` | Slack CDC, Slack Cortex |
| **Productivity** | `google-sheets` | Google Sheets |
| | `slack-no-cortex` | Slack (no Cortex) |
| **Streaming (Ingress)** | `kafka-sasl` | Kafka SASL |
| | `kafka-avro-sasl-topic2table-schemaev` | Kafka Avro SASL, schema evolution |
| | `kafka-json-sasl-topic2table-schemaev` | Kafka JSON SASL, schema evolution |
| | `kinesis-json-modularized` | Kinesis JSON (modularized) |
| **HR** | `workday` | Workday |

**Note:** For Kafka high-performance connector customizations (auth changes, data type switching, transformations), see `references/connector-kafka.md` and `references/connector-streaming-main.md`. Legacy Kafka ingress connectors are organized by authentication type (SASL) and data format (Avro, JSON). The `topic2table-schemaev` variants support schema evolution.

### Egress Connectors (Snowflake to External)

Most connectors above are **ingress** (external data into Snowflake). The following are **egress** connectors that send data from Snowflake to external systems:

| Category | Flow Name | Common Names | Auth Type |
|----------|-----------|--------------|-----------|
| **Kafka Sink** | `kafka-sink-sasl` | Kafka Sink SASL | SASL |
| | `kafka-sink-iam` | Kafka Sink IAM | AWS IAM |
| | `kafka-sink-mtls` | Kafka Sink mTLS | Mutual TLS |
| **Document Sync** | `snowflake-to-box-metadata` | Snowflake to Box | OAuth |

---

## Connector Workflow

**Scope: Gen1 (nipyapi/registry) connectors only.** Gen2 connectors follow the
workflow in their connector-specific reference (e.g., `connector-postgres-gen2.md`).
If you are working with a Gen2 connector, do not follow steps 1–14 below.

**Load each reference as you reach that step.** This keeps context fresh and allows recovery if the user encounters issues (permissions, network, etc.) that require investigation before continuing.

**Do not skip steps or improvise commands.** Use exact syntax from the loaded references.

### 1. Understand

Load the connector-specific reference from [Connector Routing](#connector-routing) above. This provides:
- Prerequisites (source system configuration)
- Required parameters and how to obtain them
- Connector-specific configuration steps

If no specific reference exists, use this general workflow with `ops-flow-deploy.md`.

### 2. Collect

Gather all required information from the user **before** taking any action. Each connector reference includes a prerequisites checklist.

**Minimum for all connectors:**
- Source connection details (host, port, credentials)
- Snowflake destination (database, schema, warehouse, role)
- Snowflake authentication method (see `references/ops-snowflake-auth.md`)

**Do not proceed** until you have resolved the required values. Missing information causes failed deployments.

### 3. Network Access (SPCS Only)

Before deploying, ensure network access is configured for external sources.

- **SPCS:** Requires External Access Integration. **Load** `references/platform-eai.md`.
- **BYOC:** Typically has direct network access, no EAI required.
- **Private Link:** If using AWS PrivateLink or Azure Private Link, confirm with user as this affects connectivity patterns.

### 4. Network Validate (SPCS Only)

After EAI is configured, validate network connectivity before deploying the connector.

**Load** `references/ops-network-testing.md` to run connectivity tests against the source endpoints.

This catches EAI misconfigurations early, before investing time in connector deployment and configuration.

**If validation fails:** Stop and resolve network issues before proceeding. See `references/platform-eai.md` for troubleshooting.

### 5. Check for Existing Connectors

**Load** `references/ops-flow-deploy.md` for checking existing deployments. Deploying the same connector twice may share parameter contexts or mistakenly duplicate an existing datasource.

### 6. Deploy the Connector

**Load** `references/ops-flow-deploy.md` for registry discovery and deployment. The Snowflake Connector Registry uses the same commands as Git registries.

### 7. Handle Parameters

Parameters provide values that controllers need to enable successfully (connection URLs, credentials, etc.).

**Load** `references/ops-parameters-main.md` for parameter configuration (includes routing to assets for certificates, keys, JARs).

**Understand before configuring:** Use `references/ops-parameters-inspect.md` to read parameter descriptions. Descriptions contain valid values, defaults, and SPCS vs BYOC differences that inform correct configuration.

For Snowflake destination authentication, **load** `references/ops-snowflake-auth.md`.

### 8. Processor Updates

Some connectors require processor-specific configuration (concurrent tasks, scheduling, etc.). Check the connector reference for any required updates. If there are none specified then you can skip this step.

### 9. Verify Controllers

Verify controller configuration BEFORE enabling. Controllers must be DISABLED for verification.

```bash
nipyapi --profile <profile> ci verify_config --process_group_id "<pg-id>" --verify_processors=false
```

**If verification fails:** Fix parameter configuration before proceeding.

### 10. Enable Controllers

Enable controller services after verification passes.

**Load** `references/ops-flow-lifecycle.md` and use the "Enable Controllers Only" section.

After enabling, check for errors:
- All controllers should show `ENABLED` state
- Check bulletins for runtime errors (authentication, connection, etc.)

**If controllers fail to enable:** Check bulletins for specific error messages.

### 11. Verify Processors

Verify processor configuration AFTER controllers are enabled (processors may depend on enabled controllers).

```bash
nipyapi --profile <profile> ci verify_config --process_group_id "<pg-id>" --verify_controllers=false
```

**If verification fails:** Check processor dependencies and parameter values.

### 12. Start

**Load** `references/ops-flow-lifecycle.md` for starting the flow.

### 13. Validate

After starting, validate data is actually flowing. This is a runtime check.

See [Validate Data Flow](#validate-data-flow) below, then check connector-specific validation in the connector reference.

### 14. Upgrades

**Load** `references/connector-upgrades.md` for identifying and applying connector updates.

---

## Validate Data Flow

After starting a connector, validate data is actually flowing. The specific checks depend on connector type.

### General Checks (All Connectors)

```bash
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
```

Expect:
- `running_processors` > 0
- `invalid_processors` = 0
- `bulletin_errors` = 0

### Connector-Specific Validation

For detailed validation steps, **load** the appropriate connector reference from the [Connector Routing](#connector-routing) section above.

### Troubleshooting Validation Failures

If `bulletin_errors` > 0:
- **Load** `references/ops-flow-lifecycle.md` to check bulletins

If `invalid_processors` > 0 after starting:
- Controller services may not be enabled
- Parameters may be misconfigured
- Re-check previous workflow steps

---

## Shared Parameter Contexts

Connectors of the same type share parameter contexts. This means:

1. **Check before deploying** - Avoid duplicate connectors of the same type
2. **Parameter changes affect all instances** - Changing parameters affects all connectors sharing that context
3. **Never delete parameter contexts** - Without understanding the impact on other connectors

---

## Next Step

Connector deployment is a primary workflow that users commonly request. After completing deployment:

1. **Ask the user** if they have additional tasks or want to continue with another operation
2. If no further tasks, return to the main router (`SKILL.md`) for other Openflow operations
3. For ongoing connector management, see `references/connector-upgrades.md`

---

## See Also

- `references/ops-flow-deploy.md` - Deploy flows from registry
- `references/ops-flow-lifecycle.md` - Start, stop, monitor
- `references/ops-parameters-main.md` - Parameter configuration
- `references/ops-snowflake-auth.md` - Snowflake destination authentication
- `references/platform-eai.md` - Network access for SPCS
- `references/connector-upgrades.md` - Version management
