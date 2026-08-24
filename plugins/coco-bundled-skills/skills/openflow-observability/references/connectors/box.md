---
name: openflow-observability-connector-box
description: Box unstructured connector troubleshooting and SPCS domain allowlist.
---

# Box (Unstructured)

## Official Docs

- [About](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/box/about)
- [Setup](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/box/setup)

## SPCS Domain Allowlist

> **Note:** Verify against the latest [Configure allowed domains for connectors](https://docs.snowflake.com/en/user-guide/data-integration/openflow/setup-openflow-spcs-sf-allow-list) page if connector versions have been updated.

| Domain | Notes |
| --- | --- |
| `api.box.com` | Box API |
| `box.com` | Box authentication |

## Root Processor

| Source | Root Processor | Controller Service Verification |
| --- | --- | --- |
| Box | `Consume File Events` | Supported (`JsonConfigBasedBoxClientService`) |

## Troubleshooting

### Ingestion Stopped

**Common causes:**
1. **Invalid source credentials:** Check the `Consume File Events` processor for errors. Use Controller Service Verification: disable the `JsonConfigBasedBoxClientService` > Edit > Properties > Verification.
2. **Invalid access scopes:** Check processor logs for scope/permission errors.
3. **Invalid Snowflake credentials:** Check `ExecuteSQL` or `ExecuteSQLStatement` processors. On SPCS with session token auth, this should not occur.

---

For shared SaaS patterns (OAuth failures, rate limiting, API versioning), load `references/connectors/saas-connectors.md`. For shared Snowflake-side destination failures and customer state inspection queries for unstructured connectors, see [Unstructured Connector Shared Patterns](saas-connectors.md#unstructured-connector-shared-patterns), and load `connector-shared-generic.md` for the destination-side diagnosis itself.
