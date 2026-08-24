---
name: openflow-observability-connector-support-matrix
description: Single source of truth for which connector definitions support Openflow SQL actions, what runtime size they need, which driver / property fix-candidates apply, and which per-connector troubleshoot file owns the source-side prerequisites.
---

# Openflow SQL Action Support Matrix (Per-Connector)

This file is the canonical lookup other Tier 2 references consult when they need to know:

- Which connector definitions are SQL-managed today (`GA`, `MVP`, `PrPr`, `Coming next`, `Not yet`)
- The minimum parent runtime `NODE_TYPE` for each connector
- The connector family (drives whether the CDC Retention banner applies)
- The required JDBC driver / ASSET_REFERENCE asset name (for `connector.config_set_asset`)
- The common STRING_LITERAL properties an agent should be ready to fix via `connector.config_set_property`
- The per-connector troubleshoot doc that owns the source-side prerequisites

**Rule:** other references (`action-guidelines.md`, `connector-actions.md`, `connector-config-edit.md`, `connectors/connector-shared-cdc.md`) MUST consult this matrix rather than inlining the connector list. When a new connector is promoted to `GA`, `MVP`, or `PrPr`, update one row here and the rest of the skill follows.

---

## Connector Capability Matrix

The `connector_type alias` column is the value the agent has **pre-SQL** (from page context or user input). The `Connector definition` column is the value Snowflake returns from `SHOW`/`DESCRIBE OPENFLOW CONNECTOR` **post-SQL**. The pre-gate uses the alias; the live SQL check uses the Snowflake-side definition. They MUST agree -- divergence means page-context drift and the live check wins.

| `connector_type` alias | Connector definition | Openflow SQL support | Family | Min parent `NODE_TYPE` | Driver ASSET_REFERENCE property | Common STRING_LITERAL fix-candidates | Per-connector troubleshoot doc |
|---|---|---|---|---|---|---|---|
| `postgresql` | `OPENFLOW_POSTGRES_CDC` | **GA** | CDC | `MEDIUM` | `Source Database Driver` (`PostgreSQL JDBC Driver`) | `Source Database Connection URL`, `Source Database User`, `Source Database Publication Name`, `Source Database Schema`, `Replication Slot Name` | [`../connectors/postgresql.md`](../connectors/postgresql.md) |
| `mysql` | `OPENFLOW_MYSQL_CDC` | **PrPr** | CDC | `MEDIUM` | `Source Database Driver` (`MariaDB Connector/J`) | `Source Database Connection URL`, `Source Database User`, `Starting Binlog Position`, `Re-read Tables in State` | [`../connectors/mysql.md`](../connectors/mysql.md) |
| `sql_server` | `OPENFLOW_SQL_SERVER_CDC` | Not yet | CDC | `MEDIUM` | `Source Database Driver` (`SQLServer JDBC Driver`) | `Source Database Connection URL`, `Source Database User`, `Source Database Schema`, `Table Filter` | [`../connectors/sql-server.md`](../connectors/sql-server.md) |
| `oracle` | `OPENFLOW_ORACLE_CDC` | Not yet | CDC | `MEDIUM` | `Source Database Driver` (`Oracle JDBC Driver`) | `Source Database Connection URL`, `Source Database User`, `Container Name`, `Table Filter` | [`../connectors/oracle.md`](../connectors/oracle.md) |
| `mongodb` | n/a -- not yet in SOM (open public preview, June 2026) | Not yet | CDC (change streams) | `MEDIUM` | none (change streams, no JDBC driver) | `Connection URI`, database / collection filter | [`../connectors/mongodb.md`](../connectors/mongodb.md) |
| `google_bigquery` | n/a -- not yet in SOM (open public preview, June 2026) | Not yet | CDC (change history) | `MEDIUM` | none (BigQuery Storage Read API + `CHANGES` function, no JDBC driver) | dataset / table filter (`Included Dataset Names`, `Included Table Names`) | [`../connectors/google-bigquery.md`](../connectors/google-bigquery.md) |
| `kafka`, `kinesis`, SaaS aliases (`salesforce_bulk_api`, `microsoft_dataverse`, `sharepoint_unstructured`, `google_drive_unstructured`, `box_unstructured`, ads connectors, and SaaS connectors `google_drive`, `sharepoint`, `box`, `jira`, `hubspot`, `workday`, `confluence`, `slack`, `google_sheets`) | (varies) | Not yet | Non-CDC | (TBD per connector) | (varies; many have no JDBC driver) | (varies) | per-connector file in `connectors/` |

Alias normalization rules (apply before lookup): `postgres` -> `postgresql`, `mssql` / `sqlserver` -> `sql_server`. The aliases match the `connector_type` values used elsewhere in the skill (Startup Sequence, per-connector files).

**Status legend:**

- `GA`: Openflow SQL lifecycle and config-edit actions are fully supported. The agent may offer `connector.start` / `connector.stop` / `connector.commit` / `connector.abort` / `connector.config_set_property` / `connector.config_set_asset` when other gates pass.
- `MVP`: Same as GA for the actions the connector definition supports today. Treat as GA unless a per-connector caveat is documented below.
- `PrPr`: Private Preview connector definition. The Openflow SQL action lane is **enabled** -- treat it like `MVP` (same actions, same gates) because the SQL lifecycle is identical to the GA connectors. A mutating-action Confirmation Preview may **optionally** add a line noting the connector definition is in Private Preview (e.g. `Note: <CONNECTOR_DEFINITION> is a Private Preview connector.`) alongside any CDC retention banner.
- `Coming next`: Not yet enabled. The agent MUST route customers to the Openflow UI for lifecycle and config edits, regardless of how the customer phrased the ask. Diagnostic reads (`DESCRIBE`, `SHOW`, Recent Error Logs) are still allowed.
- `Not yet`: Same as `Coming next`. The two values exist only to communicate roadmap intent in this matrix; the agent treats them identically.

> **Gate semantics.** The [Connector-Definition Support Gate](action-guidelines.md#connector-definition-support-gate-sub-check-of-hard-gate-2) reads only `Openflow SQL support`: `GA`/`MVP`/`PrPr` may enter the action lane; `Coming next`/`Not yet` fails closed before `SHOW`/`DESCRIBE`. Today `OPENFLOW_POSTGRES_CDC` is `GA` and `OPENFLOW_MYSQL_CDC` is `PrPr`; both enter the action lane and are authorized by the live definition match (a preview note is optional). Enabling another connector is a matrix-row change, not a template edit.

---

## How to read this matrix

### From `connector-actions.md > connector.start > Connector-definition node-size gate`

The "Min parent `NODE_TYPE`" column gates `connector.start`. If the parent runtime's `NODE_TYPE` is below the listed minimum, **fail closed** and tell the customer the runtime must be rebuilt at the larger size (`NODE_TYPE` is immutable after runtime creation).

If the connector definition is not in this matrix (third-party or future definition), the agent has no node-size data and must NOT proceed -- fall back to customer-run guidance via the Openflow UI.

### From `action-guidelines.md > CDC Retention Warning` and any action template that pauses a connector

The "Family" column drives whether the [CDC Retention Warning](action-guidelines.md#cdc-retention-warning-cross-cutting) is surfaced in the Confirmation Preview. Surface the banner whenever the in-scope connector has `Family = CDC` and the action is `connector.stop`, `connector.commit`, `connector.config_set_property`, `connector.config_set_asset`, `runtime.suspend`, or `runtime.restart`.

### From `connector-config-edit.md > connector.config_set_property`

The "Common STRING_LITERAL fix-candidates" column lists the property names most often surfaced as wrong by the [Connector Config Snapshot](connector-diagnostics.md#connector-config-snapshot-read-only) paired with Recent Error Logs, or by per-connector source-prereq checks. This is the agent's shortlist when proposing `connector.config_set_property` -- the property must still pass the uniqueness gate (`REGEXP_COUNT` of the property name in `config.json` equals exactly `1`).

### From `../connectors/connector-shared-cdc.md > Openflow SQL Action Candidates for CDC Config Errors`

The matrix replaces the previously-inlined per-connector property tables in CDC routing. Per-connector troubleshoot files (e.g., `connectors/postgresql.md`) link back to that section, which in turn links here.

### From `connectors/connector-shared-generic.md > Missing JDBC Driver / Parameter Context Assets`

The "Driver ASSET_REFERENCE property" column is the property name that `connector.config_set_asset` targets when wiring a JDBC driver. The friendly driver name (e.g., `PostgreSQL JDBC Driver`) matches the parameter-context asset name surfaced in the Openflow UI.

---

## Adding a new SQL-managed connector

When a new connector definition is promoted to `GA`, `MVP`, or `PrPr`:

1. Update the row in the matrix above:
   - Set `Openflow SQL support` to `GA`, `MVP`, or `PrPr`.
   - Confirm the `Min parent NODE_TYPE` (consult the connector-definition spec; CDC defaults to `MEDIUM`).
   - Confirm or add the `Driver ASSET_REFERENCE property` (the parameter-context asset name from the UI wizard).
   - List the common `STRING_LITERAL` fix-candidates the agent should be prepared to propose.
   - Link the per-connector troubleshoot doc.
2. In the per-connector troubleshoot file (e.g., `connectors/mysql.md`), add inline cross-references next to source-prereq checks using the convention:

   > **If the property exists but the connector references a wrong value:** the source side is fine; the connector's `<property name>` is wrong. For SQL-managed connectors, the agent can update that single property via `connector.config_set_property` after confirmation -- see [Openflow SQL Action Candidates for CDC Config Errors](../connectors/connector-shared-cdc.md#openflow-sql-action-candidates-for-cdc-config-errors). For BYOC or non-SQL-managed connectors, guide the customer to fix the value in the Openflow UI wizard.

3. Add at least one happy-path eval and one fail-closed eval under `evals/data-engineering/openflow-observability/connector-<name>-*` (mirror the existing Postgres evals).
4. Re-run the verifier smoke test (see `evals/data-engineering/openflow-observability/shared/verifier/`) to confirm `assert_executed_sql_uses_add_version_from` and `assert_no_unconfirmed_chained_mutations` still pass for the new connector's scenarios.

No other Tier 2 file needs to change. The action templates, diagnostic fast-paths, retention banner, and allowlist are connector-agnostic by design and will apply automatically once the matrix row flips.
