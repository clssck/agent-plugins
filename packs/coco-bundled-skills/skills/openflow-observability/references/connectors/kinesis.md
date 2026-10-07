---
name: openflow-observability-connector-kinesis
description: Kinesis connector troubleshooting and SPCS domain allowlist.
---

# Kinesis

## Official Docs

- [About](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/kinesis/about)
- [Setup](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/kinesis/setup)
- [Maintenance](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/kinesis/maintenance)
- [Troubleshoot](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/kinesis/troubleshoot)

## SPCS Domain Allowlist

> **Note:** Verify against the latest [Configure allowed domains for connectors](https://docs.snowflake.com/en/user-guide/data-integration/openflow/setup-openflow-spcs-sf-allow-list) page if connector versions have been updated.

All domains are AWS region-dependent. Replace `<region>` with the customer's AWS region (e.g., `us-west-2`).

| Domain | Notes |
|--------|-------|
| `kinesis.<region>.amazonaws.com` | Kinesis data streams |
| `kinesis-fips.<region>.api.aws` | FIPS endpoint (if required) |
| `kinesis-fips.<region>.amazonaws.com` | FIPS endpoint (if required) |
| `kinesis.<region>.api.aws` | Kinesis API |
| `*.control-kinesis.<region>.amazonaws.com` | Kinesis control plane |
| `*.control-kinesis.<region>.api.aws` | Kinesis control plane |
| `*.data-kinesis.<region>.amazonaws.com` | Kinesis data plane |
| `*.data-kinesis.<region>.api.aws` | Kinesis data plane |
| `dynamodb.<region>.amazonaws.com` | DynamoDB for KCL lease table |
| `monitoring.<region>.amazonaws.com:80` | CloudWatch monitoring |
| `monitoring.<region>.amazonaws.com:443` | CloudWatch monitoring |
| `monitoring-fips.<region>.amazonaws.com:80` | CloudWatch FIPS (if required) |
| `monitoring-fips.<region>.amazonaws.com:443` | CloudWatch FIPS (if required) |
| `monitoring.<region>.api.aws:80` | CloudWatch API |
| `monitoring.<region>.api.aws:443` | CloudWatch API |

## Parameters & Required Assets

Key parameters from the [official setup documentation](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/kinesis/setup):

### Source Parameters

| Parameter | Description | Notes |
|-----------|-------------|-------|
| `AWS Access Key ID` | IAM access key | Required |
| `AWS Secret Access Key` | IAM secret key | Required |
| `Kinesis Stream Name` | Stream to consume | Case-sensitive; must match exactly |
| `Kinesis Region` | AWS region | Must match the stream's region |
| `Kinesis Application Name` | KCL application name | Used as the DynamoDB lease table name |
| `Kinesis Consumer Type` | Consumer throughput mode | `SHARED_THROUGHPUT` (default) or `DEDICATED_THROUGHPUT` (enhanced fan-out) |

### Destination Parameters

See [Standard Destination Parameters](connector-shared-generic.md#standard-destination-parameters). Additional Kinesis-specific parameter:

| Parameter | Description | Notes |
|-----------|-------------|-------|
| `Iceberg Mode` | Write to Iceberg table | When enabled, destination tables are Apache Iceberg format |

### Schema Evolution Parameters

| Parameter | Description | Notes |
|-----------|-------------|-------|
| `Schema Evolution Enabled` | Auto-add new columns | Detects schema changes in incoming data |
| `Schema Evolution Type` | Evolution strategy | Controls how schema changes are applied |

### SPCS Domain Allowlist Addition

> **Note:** In addition to the domains listed above, the STS endpoint must also be allowlisted for AWS credential operations:

| Domain | Notes |
|--------|-------|
| `sts.<region>.amazonaws.com` | AWS Security Token Service |

## Troubleshooting

### KCL Errors

The Kinesis connector uses the AWS Kinesis Client Library (KCL) v3 internally.

> **Critical:** KCL errors are **not** propagated to the Openflow UI. The connector may appear healthy in the UI while KCL is failing silently. Always check KCL logs via the event table when investigating "no data ingested" issues.

**Query KCL logs:**


```sql
SELECT
  timestamp,
  resource_attributes:"k8s.namespace.name"::STRING AS runtime_key,
  TRY_PARSE_JSON(value) AS log,
  TRY_PARSE_JSON(value):"formattedMessage"::STRING AS message
FROM {event_table}
WHERE record_type = 'LOG'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND resource_attributes:"k8s.container.name"::STRING ILIKE '%-server'
  AND TRY_PARSE_JSON(value):"loggerName"::STRING LIKE 'software.amazon.kinesis.%'
  AND TRY_PARSE_JSON(value):"level"::STRING IN ('WARN', 'ERROR')
ORDER BY timestamp DESC
LIMIT 100;
```

### KCL Error: UnknownHostException

**Pattern:** `java.net.UnknownHostException: dynamodb.<region>.amazonaws.com`

**Likely Cause:** Network rule misconfigured (SPCS) or DNS resolution failure. KCL requires access to DynamoDB, CloudWatch, STS, and Kinesis endpoints.

**Required domains (SPCS):** The following AWS domains must be allowlisted in the network rule (replace `<region>` with the customer's AWS region):

| Service | Domain Pattern |
|---------|----------------|
| Kinesis | `kinesis.<region>.amazonaws.com` |
| Kinesis (control) | `*.control-kinesis.<region>.amazonaws.com` |
| Kinesis (data) | `*.data-kinesis.<region>.amazonaws.com` |
| DynamoDB | `dynamodb.<region>.amazonaws.com` |
| CloudWatch | `monitoring.<region>.amazonaws.com:80`, `monitoring.<region>.amazonaws.com:443` |
| STS | `sts.<region>.amazonaws.com` |

**Recommended Action:**
1. Verify all required domains are in the network rule: [Configure allowed domains for connectors](https://docs.snowflake.com/en/user-guide/data-integration/openflow/setup-openflow-spcs-sf-allow-list)
2. Verify the EAI is associated with the runtime (Openflow UI > Runtimes > External access integrations)
3. If domains are correct, **Load** `references/troubleshoot-network.md` for full EAI validation

### KCL Error: User Not Authorized (IAM)

**Pattern:** `User: **** is not authorized to perform: kinesis:RegisterStreamConsumer on resource: arn:aws:kinesis:...`

**Likely Cause:** The configured AWS credentials lack the required IAM permissions for KCL consumer applications.

**Recommended Action:**
1. Guide the customer to review the AWS IAM permissions required for KCL consumer applications (see AWS documentation: "IAM permissions required for KCL consumer applications")
2. Required permissions include: `kinesis:RegisterStreamConsumer`, `kinesis:SubscribeToShard`, `kinesis:DescribeStreamSummary`, `kinesis:ListShards`, `dynamodb:CreateTable`, `dynamodb:DescribeTable`, `dynamodb:GetItem`, `dynamodb:PutItem`, `dynamodb:Scan`, `dynamodb:UpdateItem`, `dynamodb:DeleteItem`, `cloudwatch:PutMetricData`

### KCL Error: No Shards Found

**Pattern:** `java.lang.IllegalStateException: No shards found when attempting to validate complete hash range.`

**Likely Cause:** The Kinesis stream does not exist, the stream name is misspelled, or the AWS region is incorrect.

**Snowsight Checks:** Check KCL logs for additional context:


```sql
SELECT timestamp, TRY_PARSE_JSON(value):"formattedMessage"::STRING AS message
FROM {event_table}
WHERE record_type = 'LOG'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND value ILIKE '%ResourceNotFoundException%'
ORDER BY timestamp DESC
LIMIT 20;
```

Look for: `Got ResourceNotFoundException when fetching shard list for stream-name. Stream no longer exists.`

**Recommended Action:**
1. Verify the stream name matches exactly (case-sensitive) in the connector parameters
2. Verify the AWS region is specified correctly
3. Verify the stream exists and is in ACTIVE state in the AWS console

### FlowFile Queue Full / Backpressure

**Pattern:** FlowFile queues are filling up, connector not processing data fast enough.

**Likely Cause:** Downstream processors (typically `PutSnowpipeStreaming`) cannot keep up with the incoming data rate.

**Recommended Action:**

If the downstream processor (typically `PutSnowpipeStreaming`) cannot keep up:

- Tell the customer that the current runtime size may be too small for the ingestion rate.
- Tell the customer to reduce source throughput if they control it.
- Avoid prescribing NiFi-internal task counts unless a public connector document explicitly exposes those settings.
- If backlog persists after resizing the runtime and reducing source throughput, check for errors in `PutSnowpipeStreaming` logs. If the processor is healthy but simply cannot keep pace, the customer may need to split the workload across multiple runtimes.

### CPU Monitoring and Autoscaling

The Kinesis connector supports autoscaling based on CPU consumption. The CPU Utilization by Pod query in `references/core-queries-resource.md` already normalizes CPU usage as a percentage of allocated cores. No special interpretation is needed for Kinesis -- a `cpu_usage_percentage` of 80 means 80% of the runtime's total CPU capacity.
