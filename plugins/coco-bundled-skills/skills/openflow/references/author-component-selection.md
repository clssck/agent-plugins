---
name: openflow-author-component-selection
description: NiFi component reference - what each processor and controller service does. Load when you need to understand available tools.
---

# Component Reference

Understand the tools on the NiFi workbench. This reference describes what each component does and when to use it.

**Scope:** Tool descriptions for the hundreds of turn-key components within NiFi that can be used in various Flows (the workbench). For blueprints on how to combine tools for specific projects, see the `author-pattern-*.md` references.

---

## Discovery Methods

### 1. Search by Name/Tag

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

# Search processors by keyword
types = nipyapi.canvas.list_all_processor_types()
matches = [t for t in types if 'kafka' in t.type.lower()]
for m in matches:
    print(f"{m.type}: {m.description[:80]}...")
```

### 2. Get Detailed Documentation

```bash
# Get full processor documentation
nipyapi --profile <profile> canvas get_processor_docs --processor UpdateRecord
```

### 3. Browse by Category

Processors are tagged by function. Common tags:
- `record`, `json`, `avro`, `csv` - Record/data format
- `kafka`, `s3`, `http`, `database` - External systems
- `transform`, `route`, `filter` - Processing type

---

## Component Instantiation

### Get Type Object

`get_processor_type()` returns a **LIST** when multiple types match:

```python
types = nipyapi.canvas.get_processor_type('ExecuteSQL')
if isinstance(types, list):
    proc_type = next(p for p in types if p.type == 'org.apache.nifi.processors.standard.ExecuteSQL')
else:
    proc_type = types
```

### Property Configuration

See `ops-component-config.md` for setting processor and controller properties.

---

## Processor Categories

### Data Ingestion (Sources)

| Processor | Use When |
|-----------|----------|
| `GenerateFlowFile` | Testing, generate static content |
| `GenerateJSON` | Generate synthetic data with DataFaker expressions (see `author-pattern-data-generation.md`) |
| `GetFile` | Read files from local filesystem |
| `ListS3` + `FetchS3Object` | Read files from S3 |
| `ListGCSBucket` + `FetchGCSObject` | Read files from GCS |
| `ConsumeKafka` | Stream from Kafka topic |
| `ConsumeJMS` | Consume from JMS queue/topic (ActiveMQ, etc.) |
| `InvokeHTTP` | Call REST APIs |
| `ExecuteSQLRecord` | Query database, output as records |
| `QueryDatabaseTable` | Incremental database ingestion |
| `ListenHTTP` | Receive HTTP requests |

### Data Transformation

| Processor | Use When |
|-----------|----------|
| `UpdateRecord` | Modify record fields (RecordPath) |
| `UpdateAttribute` | Add/modify FlowFile attributes |
| `JoltTransformJSON` | Complex JSON restructuring |
| `QueryRecord` | SQL queries on record data |
| `ConvertRecord` | Change format (JSON→Avro, CSV→JSON) |
| `SplitRecord` | Split large records into smaller batches |
| `MergeRecord` | Combine multiple records into one FlowFile |
| `ReplaceText` | Regex-based text replacement |
| `ExtractText` | Extract regex matches to attributes |

### Routing & Filtering

| Processor | Use When |
|-----------|----------|
| `RouteOnAttribute` | Route based on attribute values |
| `RouteOnContent` | Route based on content patterns |
| `RouteText` | Route based on text matching |
| `ValidateRecord` | Validate against schema, route invalid |
| `PartitionRecord` | Split records by field value |
| `FilterRecord` | Remove records matching criteria |

### Content Manipulation (Compression, Encryption, Packaging)

| Processor | Use When |
|-----------|----------|
| `ModifyCompression` | Compress or decompress (gzip, bzip2, xz, snappy, zstd) |
| `UnpackContent` | Extract archives (tar, zip, FlowFile packages) |
| `DecryptContentPGP` | Decrypt PGP/OpenPGP encrypted content (`org.apache.nifi - nifi-pgp-nar`) |
| `EncryptContentPGP` | Encrypt content with PGP/OpenPGP |

### Data Output (Sinks)

| Processor | Use When |
|-----------|----------|
| `PutSnowpipeStreaming` | Write to Snowflake (Openflow) |
| `PutFile` | Write to local filesystem |
| `PutS3Object` | Write to S3 |
| `PublishKafka` | Write to Kafka topic |
| `PublishJMS` | Publish to JMS queue/topic (ActiveMQ, etc.) |
| `PutDatabaseRecord` | Insert/update database |
| `InvokeHTTP` | POST to REST API |

### Schema & Format

| Processor | Use When |
|-----------|----------|
| `ConvertRecord` | Format conversion (requires Reader + Writer) |
| `UpdateSnowflakeDatabase` | Create/alter Snowflake table from schema |
| `ValidateRecord` | Schema validation |

### Control Flow

| Processor | Use When |
|-----------|----------|
| `Wait` / `Notify` | Coordinate between flow branches |
| `ControlRate` | Throttle FlowFile throughput |
| `RetryFlowFile` | Implement retry logic |
| `RouteOnAttribute` | Conditional branching |

---

## Controller Services

Shared services used by multiple processors.

### Record Readers

| Service | Format |
|---------|--------|
| `JsonTreeReader` | JSON (nested/complex) |
| `JsonPathReader` | JSON with JsonPath extraction |
| `AvroReader` | Avro binary |
| `CSVReader` | CSV/TSV |
| `GrokReader` | Log files (Grok patterns) |

### Record Writers

| Service | Format |
|---------|--------|
| `JsonRecordSetWriter` | JSON output |
| `AvroRecordSetWriter` | Avro binary output |
| `CSVRecordSetWriter` | CSV output |
| `FreeFormTextRecordSetWriter` | Custom text format |

### Database

| Service | Purpose |
|---------|---------|
| `DBCPConnectionPool` | JDBC database connections |
| `HikariCPConnectionPool` | High-performance JDBC pool |
| `SnowflakeConnectionService` | Snowflake-specific connection |

### Security

| Service | Purpose |
|---------|---------|
| `StandardSSLContextService` | TLS/SSL configuration |
| `AWSCredentialsProviderControllerService` | AWS authentication |

---

## Integration Patterns

For complete blueprints on how to combine these components, see the pattern references:

| Pattern | Reference |
|---------|-----------|
| REST API ingestion | `author-pattern-rest-api.md` |
| Cloud file processing | `author-pattern-files.md` |
| ActiveMQ/JMS messaging | `author-pattern-activemq.md` |
| Snowflake destination | `author-snowflake-destination.md` |
| Synthetic test data | `author-pattern-data-generation.md` |

**Note:** For database and Kafka sources, use the pre-built Connectors (see `connector-main.md`).

**Check Connectors first:** Before building custom flows, check if a pre-built Connector exists in `connector-main.md`.

---

## Decision Tree

### "I need to read data from..."

| Source | Processor(s) |
|--------|-------------|
| REST API | `InvokeHTTP` |
| Database (batch) | `ExecuteSQLRecord` |
| Database (incremental) | `QueryDatabaseTable` |
| Kafka | `ConsumeKafka` |
| ActiveMQ/JMS | `ConsumeJMS` |
| S3/GCS | `ListS3`/`ListGCS` + `FetchS3Object`/`FetchGCSObject` |
| Local files | `GetFile` or `ListFile` + `FetchFile` |
| HTTP webhook | `ListenHTTP` |

### "I need to transform..."

| Task | Processor |
|------|-----------|
| Change record field values | `UpdateRecord` (RecordPath) |
| Add/modify attributes | `UpdateAttribute` (EL) |
| Restructure JSON | `JoltTransformJSON` |
| Query/filter records | `QueryRecord` (SQL) |
| Change format (JSON↔Avro) | `ConvertRecord` |
| Text replacement | `ReplaceText` |

### "I need to decompress or decrypt..."

| Task | Processor |
|------|-----------|
| Decompress gzip/bzip2/xz/zstd | `ModifyCompression` (decompress mode) |
| Extract tar/zip archive | `UnpackContent` |
| Decrypt PGP/OpenPGP | `DecryptContentPGP` |

### "I need to route based on..."

| Criteria | Processor |
|----------|-----------|
| Attribute value | `RouteOnAttribute` |
| Content pattern | `RouteOnContent` |
| Record field value | `PartitionRecord` or `QueryRecord` |
| Schema validity | `ValidateRecord` |

---

## Related References

- `author-main.md` - Authoring router and flow building
- `author-pattern-rest-api.md` - REST API ingestion blueprint
- `author-pattern-files.md` - Cloud file processing blueprint
- `author-pattern-activemq.md` - ActiveMQ/JMS messaging blueprint
- `author-pattern-data-generation.md` - Synthetic test data with GenerateJSON
- `author-snowflake-destination.md` - Snowflake destination
- `nifi-expression-language.md` - Attribute manipulation
- `nifi-recordpath.md` - Record field manipulation
