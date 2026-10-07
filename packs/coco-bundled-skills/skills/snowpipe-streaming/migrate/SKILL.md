---
name: snowpipe-streaming-migrate
description: "Migrate from Snowpipe Streaming classic to High-Performance Architecture."
parent_skill: snowpipe-streaming
---

# Migrate Classic → High-Performance Architecture

## When to Load

Parent skill routes here for MIGRATE intent.

## Important Context

- Classic architecture deprecation announcement planned for **mid-2026**
- After announcement: **18-month migration window** before end-of-life
- High-Performance Architecture is recommended for **all new implementations** now
- Migration requires **client code changes** — it is NOT a server-side toggle

## Key Differences

| Aspect | Classic | High-Performance Architecture |
|--------|---------|----------------------|
| SDK (Java) | `snowflake-ingest-sdk` | `snowpipe-streaming` |
| SDK (Python) | Not available | `snowpipe-streaming` (PyPI) |
| PIPE object | Not used | Required (default or named) |
| Channel target | Opens against tables | Opens against pipes |
| Schema validation | Client-side | Server-side |
| Insert method | `insertRow` / `insertRows` | `appendRow` / `appendRows` (Python); `insertRow`/`insertRows` (Java) |
| Throughput | Moderate | Up to 10 GB/s per table |
| Billing | Serverless compute + connections | [Throughput-based pricing](https://docs.snowflake.com/en/user-guide/snowpipe-streaming/snowpipe-streaming-high-performance-cost) |
| Transformations | Not supported | In-flight via PIPE COPY syntax |
| Pre-clustering | Not supported | Supported via `CLUSTER_AT_INGEST_TIME` |
| REST API | Not available | Available |

## Workflow

### Step 1: Assess Current Setup

**Ask** the user:
```
1. What SDK are you currently using? (Java snowflake-ingest-sdk)
2. How many channels/tables are you streaming to?
3. Do you use the Kafka Connector for streaming?
4. Do you need in-flight transformations?
```

**Inventory current channels:**
```sql
SHOW CHANNELS IN TABLE <DATABASE>.<SCHEMA>.<TABLE>;
```

**⚠️ STOP**: Confirm current setup before planning migration.

### Step 2: Create PIPE Objects

For each target table, decide: default pipe or named pipe.

**Default pipe** (simplest — auto-created):
- Name: `<TABLE>-STREAMING`
- No transformations, uses `MATCH_BY_COLUMN_NAME`
- No configuration needed — just start using the new SDK

**Named pipe** (for transformations or pre-clustering):
```sql
CREATE OR REPLACE PIPE <DATABASE>.<SCHEMA>.<PIPE_NAME>
AS COPY INTO <TABLE>
  FROM (SELECT $1, $1:c1, $1:ts FROM TABLE(DATA_SOURCE(TYPE => 'STREAMING')))
  MATCH_BY_COLUMN_NAME = CASE_SENSITIVE
  CLUSTER_AT_INGEST_TIME = TRUE;

GRANT OPERATE ON PIPE <DATABASE>.<SCHEMA>.<PIPE_NAME> TO ROLE <STREAMING_ROLE>;
```

### Step 3: Update SDK Dependencies

**Java:**
```xml
<!-- Remove old -->
<dependency>
    <groupId>net.snowflake</groupId>
    <artifactId>snowflake-ingest-sdk</artifactId>
</dependency>

<!-- Add new -->
<dependency>
    <groupId>com.snowflake</groupId>
    <artifactId>snowpipe-streaming</artifactId>
    <version>LATEST</version>
</dependency>
```

**Python** (new — no classic equivalent):
```bash
pip install snowpipe-streaming
```

**Kafka Connector:**
```json
{
    "connector.class": "com.snowflake.kafka.connector.SnowflakeStreamingSinkConnector",
    "snowflake.ingestion.method": "SNOWPIPE_STREAMING"
}
```
Note: The Kafka connector class name changes from `SnowflakeSinkConnector` (classic) to `SnowflakeStreamingSinkConnector` (High-Performance Architecture with explicit streaming).

### Step 4: Update Client Code

**Classic Java → HPA Java:**

```java
// CLASSIC: Channel opened against table
SnowflakeStreamingIngestChannel channel =
    client.openChannel(OpenChannelRequest.builder("ch1")
        .setDBName("DB").setSchemaName("SCH").setTableName("TBL")
        .build());
channel.insertRow(row, "offset_1");

// HPA: Channel opened against pipe
// Client is scoped to DB/SCHEMA/PIPE at construction time
StreamingIngestClient client = new StreamingIngestClient(
    "client_1", "DB", "SCH", "TBL-STREAMING", profilePath);
StreamingIngestChannel channel = client.openChannel("ch1");
channel.insertRow(row, "offset_1");
```

**Classic (no Python) → HPA Python:**

```python
from snowflake.ingest.streaming import StreamingIngestClient

client = StreamingIngestClient(
    client_name="my_client",
    db_name="DB",
    schema_name="SCH",
    pipe_name="TBL-STREAMING",
    profile_json="/path/to/profile.json",
)

channel, status = client.open_channel("ch1")
channel.append_row({"col1": "val"}, offset_token="1")
```

### Step 5: Migrate Channels

**Strategy**: Run classic and HPA in parallel during migration.

1. Keep classic channels running
2. Start HPA channels with new names (e.g., `hpa-<original_name>`)
3. Verify HPA data flow
4. Switch traffic to HPA
5. Decommission classic channels

**Note**: Classic channels auto-delete after 30 days of inactivity.

**⚠️ STOP**: Get approval for cutover plan.

### Step 6: Verify Migration

```sql
-- Compare row counts
SELECT 'classic' AS source, COUNT(*) FROM <TABLE>
WHERE instance_id LIKE 'classic%'
UNION ALL
SELECT 'hpa', COUNT(*) FROM <TABLE>
WHERE instance_id LIKE 'hpa%';

-- Verify no data loss
SELECT COUNT(*) FROM <TABLE>;
```

**Check HPA channel health:**
```sql
SHOW CHANNELS IN TABLE <DATABASE>.<SCHEMA>.<TABLE>;
SHOW PIPES IN SCHEMA <DATABASE>.<SCHEMA>;
```

### Step 7: Cleanup

After successful migration:
1. Remove classic SDK dependencies
2. Drop classic channel references from code
3. Update monitoring/alerting for HPA views
4. Document the new architecture

## Migration Checklist

- [ ] PIPE objects created (or default pipe confirmed)
- [ ] SDK dependencies updated
- [ ] Client code updated (channel opens against pipe)
- [ ] OPERATE privilege granted on pipes
- [ ] Parallel run validated
- [ ] Traffic switched to HPA
- [ ] Classic channels decommissioned
- [ ] Monitoring updated

## Stopping Points

- ✋ Step 1: Current setup confirmed
- ✋ Step 5: Cutover plan approved
- ✋ Step 6: Migration verified

## Output

Fully migrated Snowpipe Streaming pipeline running on the High-Performance Architecture.
