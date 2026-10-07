---
name: openflow-connector-streaming-main
description: Route streaming connector (Kafka high-performance, Kinesis) customizations - data type switching, custom transformations, dead letter queue, and Snowflake Private Key Auth. Load when customizing a streaming connector or changing how it authenticates to Snowflake.
---

# Streaming Connectors

## Scope

This reference is the router for shared customizations of streaming connectors (Kafka high-performance, Kinesis). It routes to focused sub-references.

- **Data type switching** (JSON → Avro, JSON → Protobuf) → `references/connector-streaming-datatypes.md`
- **Custom Transformations** (filtering, mapping, routing, default values, Groovy) → `references/connector-streaming-transformations.md`
- **Dead Letter Queue** (failed/rejected record handling) → `references/connector-streaming-dlq.md`
- **Private Key Auth** for `PublishSnowpipeStreaming` (Snowflake destination, KEY_PAIR) → `references/connector-streaming-snowflake-auth.md`

For Kafka broker authentication (SASL → MSK IAM, mTLS):
**Load** `references/connector-kafka.md`

For initial Kinesis connector setup (creating AWS and Snowflake objects, configuring and starting the connector):
**Load** `references/connector-kinesis-main.md`

For general Snowflake destination key-pair setup (key generation, user assignment, service user creation, grants):
**Load** `references/ops-snowflake-auth.md`

For initial connector deployment:
**Load** `references/connector-main.md`

---

## Routing Table

| User Language | Route To |
|---------------|----------|
| change data type, JSON to Avro, Avro, Protobuf, Confluent Schema Registry, schema text, AvroReader, StandardProtobufReader, message name resolution | `references/connector-streaming-datatypes.md` |
| transformation, transform, filter messages, map/rename/flatten/remove fields, topic-to-table, route to tables, content-based routing, default values, Groovy script, Jolt, QueryRecord, PartitionRecord, RouteOnAttribute, UpdateAttribute | `references/connector-streaming-transformations.md` |
| dead letter queue, DLQ, failed records, rejected messages, parse failure routing, error queue | `references/connector-streaming-dlq.md` |
| Snowflake auth, Snowflake authentication, Private Key, private key auth, KEY_PAIR, key-pair, PublishSnowpipeStreaming auth, service user, switch from SNOWFLAKE_MANAGED | `references/connector-streaming-snowflake-auth.md` |

---

## User Intent Detection

Ask the user what customization they need:

> "What would you like to customize? Options include:
> - **Data type** — switch incoming messages from JSON to Avro or Protobuf
> - **Transformations** — add processing between source and Snowflake (filtering, mapping, routing, etc.)
> - **Snowflake authentication** — switch from SNOWFLAKE_MANAGED to Private Key Auth
> - **Dead letter queue** — route failed/rejected records to a separate destination
> - **A combination** of the above"

Route based on the response:
- **Data type** → **Load** `references/connector-streaming-datatypes.md`
- **Transformations** → **Load** `references/connector-streaming-transformations.md` (it covers transformation patterns and the restriction rules; evaluate any user-described transformation against those rules before proceeding)
- **Dead letter queue** → **Load** `references/connector-streaming-dlq.md`
- **Snowflake authentication** → **Load** `references/connector-streaming-snowflake-auth.md`

These customizations can be combined freely. Execute in this order:
1. Data type change (affects how messages are read) — `references/connector-streaming-datatypes.md`
2. Snowflake Private Key Auth (independent of data path) — `references/connector-streaming-snowflake-auth.md`
3. Custom transformations (depends on correct data flow) — `references/connector-streaming-transformations.md`

---

## See Also

- `references/connector-streaming-datatypes.md` — JSON → Avro/Protobuf data type switching
- `references/connector-streaming-transformations.md` — Filtering, mapping, routing, defaults, Groovy
- `references/connector-streaming-dlq.md` — Dead Letter Queue handling (raw + optional structured payload routing)
- `references/connector-streaming-snowflake-auth.md` — Snowflake Private Key Auth (KEY_PAIR)
- `references/connector-kafka.md` — Kafka broker auth customizations (MSK IAM, mTLS)
- `references/connector-kinesis-main.md` — Kinesis router (initial setup vs customizations)
- `references/connector-main.md` — General connector deployment workflow
- `references/ops-snowflake-auth.md` — General Snowflake key-pair setup
