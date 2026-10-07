---
name: openflow-connector-kinesis-main
description: Router for the Openflow Connector for Amazon Kinesis Data Streams. Use for initial Kinesis connector setup (creating AWS and Snowflake objects, configuring and starting the connector) and to route to Kinesis streaming customizations.
---

# Kinesis Connector

The Openflow Connector for Amazon Kinesis Data Streams ingests JSON messages from a Kinesis stream into a Snowflake table, with automatic schema evolution. It reads records with the Kinesis Client Library style architecture and stores consumer checkpoints (offsets) in a DynamoDB table that the connector creates automatically.

## Scope

This reference is the **router** for the Kinesis connector. It routes to:

- **Initial setup** — create the required AWS and Snowflake objects, configure the connector, and start it → `references/connector-kinesis-setup.md`
- **Streaming customizations** shared with Kafka (data type switching, transformations, dead letter queue, Snowflake Private Key Auth) → `references/connector-streaming-main.md`

For initial connector deployment to a runtime (install from registry):
**Load** `references/connector-main.md`

For network access on SPCS (External Access Integration, required domains):
**Load** `references/platform-eai.md`

---

## Base Flow

| Property | Default Value |
|----------|--------------|
| Flow name | `kinesis-high-performance` |
| Source | Amazon Kinesis Data Streams (JSON messages) |
| Architecture | ConsumeKinesis → PublishSnowpipeStreaming |
| Checkpoint store | Amazon DynamoDB table named after the `AWS Kinesis Application Name` (auto-created) |
| Data type | JSON (schema inference) |
| Snowflake auth | Runtime identity (SNOWFLAKE_MANAGED) by default; KEY_PAIR optional |
| Parameter context | `Kinesis` |

---

## Routing Table

| User Language | Route To |
|---------------|----------|
| set up Kinesis, install Kinesis connector, configure Kinesis, first time, create the stream / IAM / table, get Kinesis into Snowflake, initial setup, prerequisites | `references/connector-kinesis-setup.md` |
| streaming customizations — change data type (JSON to Avro/Protobuf), transformation/filter/map/route, dead letter queue (DLQ), Snowflake auth (Private Key/KEY_PAIR) | `references/connector-streaming-main.md` |

---

## User Intent Detection

Ask the user what they need:

> "What would you like to do with the Kinesis connector?
> - **Initial setup** — create the AWS and Snowflake objects, configure the connector, and start it
> - **Data type** — switch incoming messages from JSON to Avro or Protobuf
> - **Transformations** — add processing between source and Snowflake
> - **Snowflake authentication** — switch to Private Key Auth
> - **Dead letter queue** — route failed records to a separate destination"

Route based on the response:
- **Initial setup** → **Load** `references/connector-kinesis-setup.md`
- **Data type / Transformations / DLQ / Snowflake auth** → **Load** `references/connector-streaming-main.md`

---

## See Also

- `references/connector-kinesis-setup.md` — Initial Kinesis setup across AWS and Snowflake
- `references/connector-streaming-main.md` — Streaming customization router (Kafka, Kinesis)
- `references/connector-main.md` — General connector deployment workflow
- `references/platform-eai.md` — Network access (EAI) for SPCS, required Kinesis domains
- `references/ops-snowflake-auth.md` — General Snowflake key-pair setup
