---
name: openflow-observability-connector-veeva-vault
description: Veeva Vault connector troubleshooting. Use when a customer reports Veeva Vault sync failures, Direct Data API enablement or session re-authentication problems, ingestion-mode (snapshot/incremental) issues, or schema-evolution or delete-strategy questions. Scaffolded stub - not yet in SOM.
---

# Veeva Vault

> **Scaffolded stub.** Not yet in the SOM; no Openflow SQL action support. Outline pending completion; verify against official docs.

## Official Docs

- [About](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/veeva-vault/about)

## Troubleshooting (outline - needs completion)

- Direct Data API enablement prerequisite.
- Session-based auth and automatic re-authentication on expiry.
- Ingestion modes: `SNAPSHOT`, `INCREMENTAL`, `SNAPSHOT_AND_INCREMENTAL`.
- Delete strategy (hard vs soft).
- Schema evolution column-removal strategies.
- `legacy_workflow` object initial-load-only limitation.

---

For shared SaaS/API patterns load `references/connectors/saas-connectors.md`; for destination-side diagnosis load `connector-shared-generic.md`. Route here from `connector-router-non-cdc.md`.
