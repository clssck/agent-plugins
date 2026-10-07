---
name: snowpipe-streaming-setup
description: "Set up Snowpipe Streaming High-Performance Architecture pipelines from scratch."
parent_skill: snowpipe-streaming
---

# Setup Snowpipe Streaming (High-Performance Architecture)

## When to Load

Parent skill routes here for SETUP intent.

## Workflow

### Step 1: Gather Requirements

**Ask** the user:
```
1. Target table — existing or new? (database.schema.table)
2. Data source — Python SDK, Java SDK, Kafka Connect, or REST API?
3. Authentication — key-pair already configured, or need to set up?
4. Schema — what columns will the target table have?
```

**⚠️ STOP**: Confirm requirements before proceeding.

### Step 2: Generate Key-Pair (if needed)

If user needs key-pair auth, **load** `references/common-patterns.md` for complete instructions.

Quick reference:
```bash
mkdir -p keys
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out keys/rsa_key.p8 -nocrypt
openssl rsa -in keys/rsa_key.p8 -pubout -out keys/rsa_key.pub
```

```sql
ALTER USER <USERNAME> SET RSA_PUBLIC_KEY='<public_key_content_without_headers>';
```

### Step 3: Create Snowflake Objects

Create the required database objects:

```sql
CREATE DATABASE IF NOT EXISTS <DATABASE>;
CREATE SCHEMA IF NOT EXISTS <DATABASE>.<SCHEMA>;

CREATE OR REPLACE TABLE <DATABASE>.<SCHEMA>.<TABLE> (
    -- User-specified columns
);

-- Create role with streaming permissions
CREATE ROLE IF NOT EXISTS <STREAMING_ROLE>;
GRANT USAGE ON DATABASE <DATABASE> TO ROLE <STREAMING_ROLE>;
GRANT USAGE ON SCHEMA <DATABASE>.<SCHEMA> TO ROLE <STREAMING_ROLE>;
GRANT INSERT ON TABLE <DATABASE>.<SCHEMA>.<TABLE> TO ROLE <STREAMING_ROLE>;
GRANT ROLE <STREAMING_ROLE> TO USER <USERNAME>;
```

**Note**: The default pipe `<TABLE>-STREAMING` is auto-created on first SDK use. For transformations or pre-clustering, create a named pipe with `CREATE PIPE`.

### Step 4: Implement the Client

**Load** the matching reference file: `references/python-sdk.md`, `references/java-sdk.md`, `references/rest-api.md`, or `references/kafka-connect.md`.

**Route based on data source:**

#### Python SDK

Install the SDK:
```bash
pip install snowpipe-streaming
```

Minimal working example:

```python
import json
from snowflake.ingest.streaming import StreamingIngestClient

profile = {
    "account": "<ACCOUNT>",
    "user": "<USER>",
    "url": "https://<ACCOUNT>.snowflakecomputing.com:443",
    "private_key": open("keys/rsa_key.p8").read(),
}

with open("/tmp/profile.json", "w") as f:
    json.dump(profile, f)

client = StreamingIngestClient(
    client_name="my_client",
    db_name="<DATABASE>",
    schema_name="<SCHEMA>",
    pipe_name="<TABLE>-STREAMING",
    profile_json="/tmp/profile.json",
)

channel, status = client.open_channel(channel_name="channel_1")

channel.append_row(
    {"col1": "value1", "col2": 42, "col3": {"nested": "data"}},
    offset_token="1",
)

channel.wait_for_flush(timeout_seconds=30)
client.close()
```

**Key patterns from reference implementation:**
- Use long-lived channels — open once, reuse across requests
- Partition channels by a key (e.g., `tenant_id`) for ordered ingestion
- Wrap `append_row` in try-catch with automatic channel recovery
- Use threading.Lock for thread-safe channel recovery

#### Kafka Connect

Use the Snowflake Kafka Connector with Snowpipe Streaming:

```json
{
    "connector.class": "com.snowflake.kafka.connector.SnowflakeStreamingSinkConnector",
    "snowflake.ingestion.method": "SNOWPIPE_STREAMING",
    "tasks.max": "1",
    "topics": "<TOPIC>",
    "snowflake.url.name": "<ACCOUNT>.snowflakecomputing.com",
    "snowflake.user.name": "<USER>",
    "snowflake.private.key": "<BASE64_PRIVATE_KEY>",
    "snowflake.database.name": "<DATABASE>",
    "snowflake.schema.name": "<SCHEMA>",
    "snowflake.role.name": "<ROLE>",
    "key.converter": "org.apache.kafka.connect.storage.StringConverter",
    "value.converter": "org.apache.kafka.connect.json.JsonConverter",
    "value.converter.schemas.enable": false
}
```

Enable schematization for automatic schema mapping:
```json
"snowflake.enable.schematization": true
```

#### REST API

For lightweight / IoT workloads, use the REST API directly. See [REST API docs](https://docs.snowflake.com/en/user-guide/snowpipe-streaming/snowpipe-streaming-high-performance-rest-api).

### Step 5: Verify Ingestion

```sql
SELECT COUNT(*) FROM <DATABASE>.<SCHEMA>.<TABLE>;
SELECT * FROM <DATABASE>.<SCHEMA>.<TABLE> LIMIT 10;

-- Verify VARIANT data is structured (not string literal)
SELECT data, TYPEOF(data) AS data_type
FROM <DATABASE>.<SCHEMA>.<TABLE> LIMIT 10;
```

If `TYPEOF` returns `VARCHAR` instead of `OBJECT`, the SDK is receiving string literals instead of native objects.

**⚠️ STOP**: Confirm data is flowing correctly.

### Step 6: Production Hardening (Optional)

Recommend:
1. Add client-side metadata columns (`CHANNEL_ID`, `STREAM_OFFSET`) for gap detection
2. Implement exponential backoff for 429/503 errors
3. Monitor with `SHOW CHANNELS` and `SNOWPIPE_STREAMING_CHANNEL_HISTORY`
4. Enable Prometheus metrics: `export SS_ENABLE_METRICS=true`

## Stopping Points

- ✋ Step 1: Requirements confirmed
- ✋ Step 5: Ingestion verified
- ✋ Step 6: Production hardening reviewed

## Output

Working Snowpipe Streaming pipeline with verified data flow.
