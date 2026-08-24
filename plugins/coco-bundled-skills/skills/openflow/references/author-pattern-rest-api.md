---
name: openflow-author-pattern-rest-api
description: Blueprint for ingesting data from REST APIs. Load when building flows that call HTTP endpoints.
---

# Pattern: REST API Ingestion

Blueprint for building flows that ingest data from REST APIs into Snowflake.

**Check first:** Does a pre-built Connector exist for this API? Check `connector-main.md` before building custom.

---

## When to Use This Pattern

- No pre-built Connector for the target API
- API requires custom authentication not supported by Connectors
- Need custom pagination or rate limiting logic
- API has non-standard response format

---

## Core Components

| Tool | Purpose | See |
|------|---------|-----|
| `InvokeHTTP` | Call REST endpoints | `author-component-selection.md` |
| `SplitJson` | Split array responses | `author-component-selection.md` |
| `UpdateRecord` | Transform response fields | `nifi-recordpath.md` |
| `UpdateSnowflakeDatabase` | Create/alter table from schema | `author-snowflake-destination.md` |
| `PutSnowpipeStreaming` | Write to Snowflake | `author-snowflake-destination.md` |

---

## Sub-Patterns

<!-- TODO: Detail these sections -->

### Basic GET Request

*To be detailed*

### Pagination Handling

*To be detailed: offset, cursor, link-header patterns*

### Bearer Token Refresh

*To be detailed: OAuth2 token refresh, token caching*

### Rate Limiting

*To be detailed: ControlRate, backoff strategies*

### Error Handling

*To be detailed: retry logic, dead-letter routing*

---

## Related References

- `author-main.md` - Authoring router
- `author-component-selection.md` - Component descriptions
- `nifi-expression-language.md` - Attribute manipulation
- `author-snowflake-destination.md` - Snowflake destination
