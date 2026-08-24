---
name: openflow-observability-connector-mongodb
description: MongoDB CDC connector troubleshooting (change streams). Use when a customer reports MongoDB sync failures, invalid or expired resume tokens, change-stream-not-available (standalone) errors, oplog retention issues, or SCRAM/x.509 auth or TLS failures. Scaffolded stub - open public preview, not yet in SOM.
---

# MongoDB (CDC)

> **Scaffolded stub (open public preview, June 2026).** This connector is not yet in the SOM and has no Openflow SQL action support. Guidance below is an outline pending completion; verify every claim against the official docs before relying on it.

## Official Docs

- [About](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/mongodb/about)
- [Setup](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/mongodb/setup)

## Source Prerequisites (to be confirmed)

- Change streams require a replica set or sharded cluster (not standalone).
- Oplog retention must exceed the connector's resume window.
- Authentication: SCRAM or x.509.

## Troubleshooting (outline - needs completion)

- Resume token invalid / expired after a resume failure (oplog rolled past the token).
- Change stream not available (standalone deployment).
- Authentication / TLS failures.
- Iceberg destination support and constraints.

---

For shared CDC diagnostics (table replication state, FAILED-table recovery), load `references/connectors/connector-shared-cdc.md`. Route here from `connector-router-cdc.md`.
