---
name: openflow-nifi-concepts
description: Core NiFi architectural concepts. Load when needing to understand FlowFile lifecycle, connections, backpressure, or NiFi architecture.
---

# NiFi Concepts

Core architectural concepts from the [NiFi User Guide](https://nifi.apache.org/docs/nifi-docs/html/user-guide.html).

---

## FlowFile

A FlowFile represents a single piece of data moving through NiFi.

| Component | Description |
|-----------|-------------|
| **Content** | The actual data (bytes) - the file content, message body, etc. |
| **Attributes** | Key-value metadata about the data |

### Standard Attributes

Every FlowFile has these core attributes:

| Attribute | Description |
|-----------|-------------|
| `uuid` | Unique identifier for this FlowFile |
| `filename` | Human-readable filename |
| `path` | Hierarchical path (for filesystem operations) |

Processors add custom attributes as data flows through the system.

---

## Processor

A Processor performs operations on FlowFiles:
- Listen for incoming data
- Pull data from external sources
- Transform or extract information
- Route data based on content/attributes
- Publish data to external systems

### Processor States

| State | Description | Can Start? |
|-------|-------------|------------|
| `RUNNING` | Actively processing FlowFiles | N/A (already running) |
| `STOPPED` | Not processing, ready to start | Yes |
| `DISABLED` | Prevented from starting | No (must enable first) |
| `INVALID` | Configuration errors | No (must fix config) |

### Scheduling

Processors have scheduling configuration:

| Setting | Description |
|---------|-------------|
| **Scheduling Strategy** | Timer-driven, CRON, or Event-driven |
| **Run Schedule** | How often to execute (e.g., "1 sec", "0 0 * * * ?") |
| **Concurrent Tasks** | How many threads can run simultaneously |
| **Run Duration** | How long each run can execute |

---

## Relationship

Each Processor defines Relationships that describe processing outcomes:

| Common Relationships | Meaning |
|---------------------|---------|
| `success` | Processing completed successfully |
| `failure` | Processing failed |
| `original` | The original FlowFile (some processors emit modified + original) |
| `matched` / `unmatched` | Content matched/didn't match criteria |

Connect Relationships to downstream components to define where FlowFiles go after processing.

---

## Connection

A Connection links processors via Relationships. Each Connection has:

| Component | Description |
|-----------|-------------|
| **Queue** | FlowFiles waiting to be processed by the destination |
| **Back Pressure** | Thresholds that pause upstream processors |
| **Prioritizers** | Rules for ordering FlowFiles in the queue |
| **Expiration** | How long FlowFiles can wait before being dropped |

### Back Pressure

Connections have thresholds that pause upstream processors when exceeded:

| Threshold | Description | Default |
|-----------|-------------|---------|
| **Object Threshold** | Max number of FlowFiles in queue | 10,000 |
| **Size Threshold** | Max total data size in queue | 1 GB |

When back pressure is applied, upstream processors stop sending data to that connection until the queue drains below thresholds.

---

## Process Group

A container for organizing components. Process Groups can:
- Contain processors, connections, other process groups
- Have their own parameter context
- Be versioned independently
- Be started/stopped as a unit

---

## Controller Service

A shared service used by multiple processors:

| Examples | Purpose |
|----------|---------|
| `JsonTreeReader` | Parse JSON into records |
| `JsonRecordSetWriter` | Write records as JSON |
| `DBCPConnectionPool` | Database connection pooling |
| `StandardSSLContextService` | TLS/SSL configuration |
| `SnowflakeConnectionService` | Snowflake authentication |

Controller Services must be **enabled** before processors can use them.

### Controller Service States

| State | Description |
|-------|-------------|
| `ENABLED` | Active and available for use |
| `DISABLED` | Not available |
| `ENABLING` | Transitioning to enabled |
| `DISABLING` | Transitioning to disabled |

---

## Data Provenance

NiFi tracks the complete lineage of every FlowFile:
- Where it came from
- What transformations occurred
- Where it was sent
- Fork/clone/join events

This enables debugging and auditing of data flow.

---

## Bulletins

Bulletins are log messages displayed in the NiFi UI:

| Level | Description |
|-------|-------------|
| `ERROR` | Processing failure, needs attention |
| `WARNING` | Potential issue, may self-resolve |
| `INFO` | Informational message |

Bulletins are ephemeral (they expire). For persistent logs, query the events table (see `platform-diagnostics.md`).

See `ops-bulletins.md` for bulletin operations.

---

## FlowFile Lifecycle

1. **Created** - Generated or received from external source
2. **Queued** - Waiting in a connection queue
3. **Processing** - Being operated on by a processor
4. **Transferred** - Moved to next connection/relationship
5. **Dropped** - Removed (routed to auto-terminated relationship, expired, or deleted)

---

## Versioning

Process Groups can be version-controlled via a Flow Registry (Git-based in Openflow).

| State | Description |
|-------|-------------|
| `NOT_VERSIONED` | No version control |
| `UP_TO_DATE` | Matches registry version |
| `LOCALLY_MODIFIED` | Local changes not committed |
| `STALE` | Registry has newer version |
| `SYNC_FAILURE` | Cannot reach registry |

See `ops-version-control.md` for versioning operations.

---

## Official Documentation

| Topic | Link |
|-------|------|
| User Guide | [nifi.apache.org/docs/nifi-docs/html/user-guide.html](https://nifi.apache.org/docs/nifi-docs/html/user-guide.html) |
| Admin Guide | [nifi.apache.org/docs/nifi-docs/html/administration-guide.html](https://nifi.apache.org/docs/nifi-docs/html/administration-guide.html) |
| Expression Language | [nifi.apache.org/docs/nifi-docs/html/expression-language-guide.html](https://nifi.apache.org/docs/nifi-docs/html/expression-language-guide.html) |
| RecordPath | [nifi.apache.org/docs/nifi-docs/html/record-path-guide.html](https://nifi.apache.org/docs/nifi-docs/html/record-path-guide.html) |
| REST API | [nifi.apache.org/docs/nifi-docs/rest-api/index.html](https://nifi.apache.org/docs/nifi-docs/rest-api/index.html) |
| Processor Components (2.x) | [nifi.apache.org/components/](https://nifi.apache.org/components/) |

---

## Related References

- `nifi-main.md` - NiFi reference router
- `nifi-expression-language.md` - Attribute manipulation
- `nifi-recordpath.md` - Record field manipulation
- `ops-flow-lifecycle.md` - Start, stop, status operations
- `ops-bulletins.md` - Bulletin operations
