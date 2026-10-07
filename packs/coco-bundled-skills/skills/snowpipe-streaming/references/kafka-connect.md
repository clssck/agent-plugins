# Kafka Connect Code Samples

Code examples for integrating Kafka with Snowpipe Streaming via the Snowflake Kafka Connector (High-Performance Architecture).

Production-ready patterns for the Snowflake Kafka Connector.

---

## Basic Streaming Connector

```json
{
    "name": "snowflake-streaming-sink",
    "config": {
        "connector.class": "com.snowflake.kafka.connector.SnowflakeStreamingSinkConnector",
        "snowflake.ingestion.method": "SNOWPIPE_STREAMING",
        "tasks.max": "4",
        "topics": "MY_TOPIC",
        "bootstrap.servers": "kafka:9092",

        "snowflake.url.name": "myorg-myaccount.snowflakecomputing.com",
        "snowflake.user.name": "STREAMING_USER",
        "snowflake.private.key": "<BASE64_ENCODED_PRIVATE_KEY>",
        "snowflake.database.name": "MY_DATABASE",
        "snowflake.schema.name": "MY_SCHEMA",
        "snowflake.role.name": "STREAMING_ROLE",

        "key.converter": "org.apache.kafka.connect.storage.StringConverter",
        "value.converter": "org.apache.kafka.connect.json.JsonConverter",
        "value.converter.schemas.enable": false,

        "buffer.count.records": "10000",
        "buffer.flush.time": "60",
        "buffer.size.bytes": "5000000"
    }
}
```

---

## With Schematization (Optional — Auto Schema Mapping)

Maps JSON fields directly to table columns instead of storing as VARIANT. This is **optional** — default pipes support schema evolution automatically (new columns added on the fly). Enable schematization only when you need explicit column-level control:

```json
{
    "name": "snowflake-streaming-schematized",
    "config": {
        "connector.class": "com.snowflake.kafka.connector.SnowflakeStreamingSinkConnector",
        "snowflake.ingestion.method": "SNOWPIPE_STREAMING",
        "snowflake.enable.schematization": true,
        "tasks.max": "4",
        "topics.regex": ".*_TOPIC$",

        "snowflake.url.name": "myorg-myaccount.snowflakecomputing.com",
        "snowflake.user.name": "STREAMING_USER",
        "snowflake.private.key": "<BASE64_ENCODED_PRIVATE_KEY>",
        "snowflake.database.name": "MY_DATABASE",
        "snowflake.schema.name": "MY_SCHEMA",
        "snowflake.role.name": "STREAMING_ROLE",

        "key.converter": "org.apache.kafka.connect.storage.StringConverter",
        "value.converter": "org.apache.kafka.connect.json.JsonConverter",
        "value.converter.schemas.enable": false
    }
}
```

---

## With Iceberg Tables

Add these config properties to enable Iceberg table ingestion:

```json
{
    "snowflake.streaming.iceberg.enabled": "true",
    "snowflake.enable.schematization": true
}
```

---

## With HoistField Transform

Wraps the Kafka message value into a named field — useful when you want the entire payload stored under a single column:

```json
{
    "transforms": "wrapKafkaMessageContent",
    "transforms.wrapKafkaMessageContent.type": "org.apache.kafka.connect.transforms.HoistField$Value",
    "transforms.wrapKafkaMessageContent.field": "RECORD_CONTENT"
}
```

---

## With Multiple Transforms

Combine HoistField with timestamp extraction:

```json
{
    "transforms": "wrapContent,addTimestamp",
    "transforms.wrapContent.type": "org.apache.kafka.connect.transforms.HoistField$Value",
    "transforms.wrapContent.field": "RECORD_CONTENT",
    "transforms.addTimestamp.type": "org.apache.kafka.connect.transforms.InsertField$Value",
    "transforms.addTimestamp.timestamp.field": "KAFKA_TIMESTAMP"
}
```

---

## Deploy & Manage Connector via REST

```bash
# Deploy connector
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d @snowflake-connector.json

# Check connector status
curl http://localhost:8083/connectors/snowflake-streaming-sink/status

# List all connectors
curl http://localhost:8083/connectors

# Pause connector
curl -X PUT http://localhost:8083/connectors/snowflake-streaming-sink/pause

# Resume connector
curl -X PUT http://localhost:8083/connectors/snowflake-streaming-sink/resume

# Restart a failed task
curl -X POST http://localhost:8083/connectors/snowflake-streaming-sink/tasks/0/restart

# Update connector config
curl -X PUT http://localhost:8083/connectors/snowflake-streaming-sink/config \
  -H "Content-Type: application/json" \
  -d @updated-config.json

# Delete connector
curl -X DELETE http://localhost:8083/connectors/snowflake-streaming-sink
```

---

## Docker Compose for Kafka + Snowpipe Streaming

```yaml
version: '3.8'

services:
  zookeeper:
    image: confluentinc/cp-zookeeper:7.4.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181

  kafka:
    image: confluentinc/cp-kafka:7.4.0
    depends_on:
      - zookeeper
    ports:
      - "9092:9092"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
    healthcheck:
      test: ["CMD-SHELL", "kafka-topics --bootstrap-server localhost:9092 --list"]
      interval: 10s
      timeout: 10s
      retries: 3

  kafka-connect:
    build: ./consumer
    depends_on:
      kafka:
        condition: service_healthy
    ports:
      - "8083:8083"
    environment:
      CONNECT_BOOTSTRAP_SERVERS: kafka:9092
      CONNECT_REST_PORT: 8083
      CONNECT_GROUP_ID: connect-group
      CONNECT_CONFIG_STORAGE_TOPIC: connect-configs
      CONNECT_OFFSET_STORAGE_TOPIC: connect-offsets
      CONNECT_STATUS_STORAGE_TOPIC: connect-status
      CONNECT_CONFIG_STORAGE_REPLICATION_FACTOR: 1
      CONNECT_OFFSET_STORAGE_REPLICATION_FACTOR: 1
      CONNECT_STATUS_STORAGE_REPLICATION_FACTOR: 1
      CONNECT_KEY_CONVERTER: org.apache.kafka.connect.storage.StringConverter
      CONNECT_VALUE_CONVERTER: org.apache.kafka.connect.json.JsonConverter
      CONNECT_PLUGIN_PATH: "/usr/share/java,/usr/share/confluent-hub-components"
    volumes:
      - ./snowflake-connector.json:/tmp/snowflake-connector.json
```

### Kafka Connect Dockerfile (consumer/Dockerfile)

```dockerfile
FROM confluentinc/cp-kafka-connect:7.4.0

RUN confluent-hub install --no-prompt snowflakeinc/snowflake-kafka-connector:2.4.1
```

---

## Confluent Kafka Producer (Python)

Pair with the connector above to produce messages:

```python
from confluent_kafka import Producer
import json

producer = Producer({"bootstrap.servers": "localhost:9092"})

def delivery_report(err, msg):
    if err:
        print(f"Delivery failed: {err}")

for i in range(100):
    event = {"id": i, "name": f"event_{i}", "value": i * 1.5}
    producer.produce(
        "MY_TOPIC",
        key=str(i),
        value=json.dumps(event),
        callback=delivery_report,
    )

producer.flush()
```
