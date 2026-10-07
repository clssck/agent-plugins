---
name: openflow-observability-connector-shopify
description: Shopify connector troubleshooting. Use when a customer reports Shopify sync failures, Admin API access-token setup errors, THROTTLED leaky-bucket rate-limit errors, bulk operation polling failures, or schema-evolution issues. Scaffolded stub - not yet in SOM.
---

# Shopify

> **Scaffolded stub.** Not yet in the SOM; no Openflow SQL action support. Outline pending completion; verify against official docs.

## Official Docs

- [About](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/shopify/about)

## Troubleshooting (outline - needs completion)

- Admin API access token setup (custom app required; OAuth not supported).
- Leaky-bucket rate limiting and `THROTTLED` GraphQL error handling.
- Bulk operation polling failures.
- Schema evolution limitations (state reset required).
- Child-record page-size truncation.
- Delete-detection scope.

---

For shared SaaS/API patterns load `references/connectors/saas-connectors.md`; for destination-side diagnosis load `connector-shared-generic.md`. Route here from `connector-router-non-cdc.md`.
