---
name: openflow-observability-connector-kafka
description: Kafka connector troubleshooting and SPCS domain allowlist.
---

# Kafka

## Official Docs

- [Setup (core)](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/kafka/setup)
- [JSON/AVRO setup](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/kafka/kafka-json-avro)
- [DLQ & metadata setup](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/kafka/kafka-dlq-metadata)
- [Authentication methods](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/kafka/authentication)
- [Performance tuning](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/kafka/performance-tuning)

## SPCS Domain Allowlist

> **Note:** Verify against the latest [Configure allowed domains for connectors](https://docs.snowflake.com/en/user-guide/data-integration/openflow/setup-openflow-spcs-sf-allow-list) page if connector versions have been updated.

| Domain | Notes |
|--------|-------|
| `<bootstrap-server-host>:<port>` | All Kafka bootstrap servers AND all broker hosts |
| `<schema-registry-host>:<port>` | If Schema Registry is used |
| `sts.<region>.amazonaws.com` | If using AWS MSK with IAM authentication |

## Parameters & Required Assets

The Kafka connector has three variants. Each variant handles a different data format. From the [official setup documentation](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/kafka/setup):

### Variants

| Variant | Use Case | Schema Registry Required |
|---------|----------|------------------------|
| **JSON** | JSON-encoded messages without schema registry | No |
| **AVRO** | Avro-encoded messages with schema registry | Yes |
| **DLQ + metadata** | JSON messages with dead letter queue support and metadata columns | No |

Choose the variant that matches the message format in the Kafka topics. If unsure, check with the customer what serialization format their Kafka producers use.

### Source Parameters (Common)

| Parameter | Description | Notes |
|-----------|-------------|-------|
| `Kafka Bootstrap Servers` | Broker addresses | Comma-separated `host:port` list |
| `Kafka Topic Name` | Topic to consume | Single topic per connector instance |
| `Kafka Group Id` | Consumer group ID | Must be unique per connector; shared group IDs cause partition competition |
| `Kafka Security Protocol` | Authentication protocol | `PLAINTEXT`, `SASL_PLAINTEXT`, `SASL_SSL`, `SSL` -- **must be typed manually** (no dropdown) |
| `Kafka SASL Mechanism` | SASL auth mechanism | `PLAIN`, `SCRAM-SHA-256`, `SCRAM-SHA-512`, `OAUTHBEARER` -- **must be typed manually** |
| `Kafka SASL Username` | SASL username | Required for SASL protocols |
| `Kafka SASL Password` | SASL password | Required for SASL protocols |
| `Kafka Auto Offset Reset` | Initial offset behavior | `earliest` (from start) or `latest` (new messages only) |

> **Warning:** Boolean and enum parameters (`Kafka Security Protocol`, `Iceberg Enabled`, `Schematization Enabled`, `Kafka SASL Mechanism`) have **no dropdown** in the UI -- they must be typed manually. Typos cause silent failures. Verify exact spelling and casing.

### Kafka Connection Service Parameter

The `Kafka Connection Service` parameter requires the **Controller Service ID** (not the name). To find it:
1. Right-click on the canvas > **Controller Services**
2. Find the relevant Kafka Connection SSL or Kafka Connection service
3. Select **View Configuration**
4. Copy the ID value

> **Note:** If the customer does not use mTLS, the `Kafka Connection SSL` controller services being in INVALID state is **expected behavior** -- do not treat this as an error.

### Controller Service Verification

To pre-flight check Kafka connectivity before starting the connector:
1. **Disable** the controller service (it must be disabled to run verification)
2. Select **Edit** > go to **Properties** tab > select **Verification**
3. The verification will test connectivity to the broker and return pass/fail
4. Re-enable the service after verification

### Source Parameters (AVRO variant only)

| Parameter | Description | Notes |
|-----------|-------------|-------|
| `Schema Registry URL` | Confluent Schema Registry URL | Required for AVRO variant |
| `Schema Registry Authentication` | Auth type for registry | `NONE`, `BASIC`, `OAUTH` |

### Destination Parameters

See [Standard Destination Parameters](connector-shared-generic.md#standard-destination-parameters).

### Secrets Manager Integration

Kafka connectors support external secrets managers for credential storage:
- **AWS Secrets Manager**
- **Azure Key Vault**
- **HashiCorp Vault**

When a secrets manager is configured, sensitive parameters (passwords, keys) are fetched from the secrets manager at runtime instead of being stored in the parameter context.

### Network Rule: All Broker Hosts

> **Important (SPCS):** The network rule must include ALL Kafka broker hosts, not just the bootstrap servers. The bootstrap servers are only used for initial connection; the client then connects directly to individual brokers. If a broker host is not allowlisted, the connector will fail with connection errors after initial bootstrap.

## Troubleshooting

### Consumer Group Errors

**Pattern:** The `ConsumeKafka` processor is running but no data is being consumed.

**Snowsight Checks:**
1. Check if the consumer group exists in Kafka (customer action -- they should verify with their Kafka tools):
   - Group does not exist = the connector most likely cannot connect to the broker
   - Group exists but offsets are not advancing = `ConsumeKafka` cannot consume data
2. Search for Kafka connection errors in the event table:


```sql
SELECT
  timestamp,
  TRY_PARSE_JSON(value):"formattedMessage"::STRING AS message,
  TRY_PARSE_JSON(value):"throwable":"message"::STRING AS error_message
FROM {event_table}
WHERE record_type = 'LOG'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND TRY_PARSE_JSON(value):"level"::STRING = 'ERROR'
  AND (TRY_PARSE_JSON(value):"formattedMessage"::STRING ILIKE '%ConsumeKafka%'
       OR TRY_PARSE_JSON(value):"formattedMessage"::STRING ILIKE '%KafkaException%'
       OR TRY_PARSE_JSON(value):"formattedMessage"::STRING ILIKE '%kafka%')
ORDER BY timestamp DESC
LIMIT 100;
```

### Broker Connectivity Issues

**Common error patterns:**

| Error Pattern | Cause |
|---------------|-------|
| `No resolvable bootstrap urls given in bootstrap.servers` | Invalid bootstrap URL or no network connectivity to broker |
| `Connection to node -1 ... terminated during authentication` | Authentication error (wrong credentials or mechanism) |
| `Failed to construct kafka consumer` | Configuration error in Kafka connection parameters |
| `Broker may not be available` | Broker is down or unreachable from the runtime |

**Recommended Action:**
1. Verify the `Kafka Bootstrap Servers` parameter has the correct host:port (e.g., `kafka-broker:9092`)
2. For SPCS deployments, verify the broker domains are allowlisted in the network rule
3. Verify the `Kafka Security Protocol` matches what the broker expects (`SASL_PLAINTEXT` or `SASL_SSL`)
4. Verify `Kafka SASL Mechanism` matches the broker configuration (`PLAIN`, `SCRAM-SHA-256`, `SCRAM-SHA-512`)
5. Check that credentials (`Kafka SASL Username` and `Kafka SASL Password`) are correct

### Schema Registry Connection Failures

**Pattern:** Errors mentioning schema registry, Avro deserialization, or schema lookup failures.

**Snowsight Checks:** Search for schema registry errors:


```sql
SELECT timestamp, TRY_PARSE_JSON(value):"formattedMessage"::STRING AS message
FROM {event_table}
WHERE record_type = 'LOG'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND (value ILIKE '%schema registry%' OR value ILIKE '%schema.registry%' OR value ILIKE '%avro%')
ORDER BY timestamp DESC
LIMIT 50;
```

**Recommended Action:**
1. Verify the schema registry URL is correct and reachable
2. For SPCS, verify the schema registry domain is in the network rule
3. Verify schema registry authentication credentials if required

### Offset Management Issues

**Pattern:** Kafka connector re-consuming old messages or skipping messages after restart.

**Key parameter:** `Kafka Auto Offset Reset` -- controls behavior when no previous offset exists:
- `earliest` -- start from the beginning of the topic
- `latest` -- start from the latest offset (default)

**Snowsight Checks:**
1. Check the `Kafka Group Id` parameter -- it must be unique per connector instance
2. If multiple connectors use the same group ID, they will compete for partitions
3. After connector restart with `latest`, any messages produced during downtime are skipped

**Recommended Action:**
- To reprocess from beginning: the `Kafka Auto Offset Reset` parameter needs to be changed to `earliest`, and optionally `Kafka Group Id` changed to a new unique value. This is a customer-owned configuration change.
- To verify offsets are advancing: run `SHOW CHANNELS IN TABLE {destination_database}."{failed_schema}"."{failed_table}";` to check Snowpipe Streaming channel offsets

### Snowflake Connection from Kafka Connector

**Pattern:** Errors from `PutSnowpipeStreaming` or Snowflake connection failures.

**Common error patterns:**

| Error Pattern | Cause |
|---------------|-------|
| `Failed to create a connection for <USER>` | Invalid Snowflake credentials or unreachable endpoint |
| `HTTP status=404` | Wrong Snowflake account identifier |
| `Role '<ROLE_NAME>' specified in the connect string is not granted to this user` | Role not granted |
| `Cannot perform SELECT. This session does not have a current database.` | Missing grants on database or schema |
| `No active warehouse selected in the current session` | No default warehouse set for the connector user |

**Required grants (guide customer's Snowflake admin to add if missing):**
- `USAGE ON DATABASE <db>` to the connector role
- `USAGE ON SCHEMA <db>.<schema>` to the connector role
- `CREATE TABLE ON SCHEMA <db>.<schema>` to the connector role
- `OWNERSHIP ON TABLE <table>` to the connector role (only if destination table was not created by the connector)

**Recommended Action:**
1. Verify Snowflake account URL, user, role, and warehouse in connector parameters
2. Verify the role is granted to the user and set as default role
3. If grants are missing, the customer's Snowflake admin needs to add them
4. Verify a default warehouse is assigned or set in the `Snowflake Warehouse` parameter

### Snowpipe Streaming Verification

To verify the Kafka connector is successfully writing data via Snowpipe Streaming:

```sql
SHOW CHANNELS IN TABLE <database>.<schema>.<table>;
```

- If the offset column is growing over time, data is being ingested successfully.
- Success logs in the event table contain `Start registering blobs`.
- If no channels exist, the connector has not started writing to this table yet.

### Schema Evolution

For schema evolution (auto-adding new columns from Kafka messages), both of the following must be true:
1. `Schematization Enabled = true` in the connector parameter context (typed manually, no dropdown)
2. `ENABLE_SCHEMA_EVOLUTION = TRUE` on the destination Snowflake table

If only one is set, new columns will not be added. If either is missing, the customer needs to correct the connector setting or destination table configuration.

---

## Snowflake to Kafka

The **Snowflake to Kafka** connector is a reverse-direction connector that consumes a Snowflake stream and sends CDC records (inserts, updates, deletes) to a Kafka topic.

**Official Docs:** [About](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/snowflake-to-kafka/about) | [Setup](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/snowflake-to-kafka/setup)

**Key limitations:**
- One connector = one Snowflake stream only
- Messages sent without a schema
- Schema evolution not supported

**Troubleshooting:** This connector uses the standard Snowflake connection and Kafka producer parameters. For Kafka-side connectivity issues, refer to the [Broker Connectivity Issues](#broker-connectivity-issues) section above. For Snowflake stream issues, verify the stream exists and the connector user has SELECT on the stream and its underlying object.
