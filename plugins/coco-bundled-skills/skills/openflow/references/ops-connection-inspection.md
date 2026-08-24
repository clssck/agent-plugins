---
name: openflow-ops-connection-inspection
description: Inspect connections and their FlowFile contents. Use for debugging data flow, examining queued data, checking attributes and content without consuming FlowFiles.
---

# Connection Inspection

Inspect connections (the queues between components) and their FlowFile contents. These are non-destructive read operations - FlowFiles remain in the queue after inspection.

## Concepts

| Term | Meaning |
|------|---------|
| **Connection** | A queue between two NiFi components. Holds FlowFiles waiting to be processed. |
| **FlowFile** | A data item in a connection. Has content (the data) and attributes (metadata). |
| **Queue depth** | Number of FlowFiles waiting in a connection |
| **Backpressure** | Threshold that pauses upstream when queue is full (object count or data size) |
| **Prioritizer** | Rules for ordering FlowFiles in the queue (FIFO, oldest first, etc.) |


## When to Use

- **Debugging transformations** - Check content/attributes after a processor
- **Verifying data format** - Inspect actual data structure before destination
- **Troubleshooting stuck flows** - See what's queued and why
- **Testing flows** - Run once, then inspect output

## Finding Connections

### List All Connections in a Process Group

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

pg = nipyapi.canvas.get_process_group("<pg-name-or-id>")
connections = nipyapi.canvas.list_all_connections(pg.id)

for conn in connections:
    source = conn.component.source.name
    dest = conn.component.destination.name
    queued = conn.status.aggregate_snapshot.flow_files_queued
    print(f"{source} -> {dest}: {queued} queued")
```

### Find Connection by Source/Destination

```python
# Find connection from a specific processor
proc = nipyapi.canvas.get_processor("MyProcessor")
connections = nipyapi.canvas.list_all_connections(pg.id)

# Connections where this processor is the source
outbound = [c for c in connections if c.source_id == proc.id]

# Connections where this processor is the destination
inbound = [c for c in connections if c.destination_id == proc.id]
```

### Connection Properties

| Property | Description |
|----------|-------------|
| `id` | Connection UUID |
| `source_id` | Source component UUID |
| `destination_id` | Destination component UUID |
| `component.source.name` | Source component name |
| `component.destination.name` | Destination component name |
| `status.aggregate_snapshot.flow_files_queued` | Number of FlowFiles in queue |
| `status.aggregate_snapshot.bytes_queued` | Total bytes queued |

---

## Listing FlowFiles

List FlowFiles waiting in a connection:

```python
# Get summaries of FlowFiles in the queue
flowfiles = nipyapi.canvas.list_flowfiles(connection)

for ff in flowfiles:
    print(f"UUID: {ff.uuid}")
    print(f"  Filename: {ff.filename}")
    print(f"  Size: {ff.size} bytes")
    print(f"  Queued: {ff.queued_duration}")
```

### FlowFile Summary Fields

| Field | Description |
|-------|-------------|
| `uuid` | Unique identifier for this FlowFile |
| `filename` | The filename attribute (often UUID if not set) |
| `size` | Content size in bytes |
| `queued_duration` | How long FlowFile has been in queue |
| `lineage_duration` | Total time since FlowFile creation |
| `penalized` | Whether FlowFile is penalized (delayed) |

**Note:** `list_flowfiles` returns summaries only - no attributes or content. Use `get_flowfile_details` for attributes.

---

## Getting FlowFile Details

Get full metadata and attributes for a specific FlowFile:

```python
# Get details including all attributes
ff = nipyapi.canvas.get_flowfile_details(connection, flowfile_uuid)

print(f"Filename: {ff.filename}")
print(f"MIME Type: {ff.mime_type}")
print(f"Size: {ff.size}")
print("\nAttributes:")
for key, value in ff.attributes.items():
    print(f"  {key}: {value}")
```

### Common FlowFile Attributes

| Attribute | Description |
|-----------|-------------|
| `filename` | Name of the FlowFile |
| `uuid` | Unique identifier |
| `path` | Directory path (often `./`) |
| `mime.type` | Content MIME type |
| `fileSize` | Content size |
| `entryDate` | When FlowFile entered the flow |

Processors add their own attributes. Common examples:

| Source | Typical Attributes |
|--------|-------------------|
| HTTP processors | `http.status.code`, `http.headers.*` |
| Record processors | `record.count`, `avro.schema` |
| Kafka processors | `kafka.topic`, `kafka.partition`, `kafka.offset` |
| S3 processors | `s3.bucket`, `s3.key`, `s3.etag` |

---

## Getting FlowFile Content

Download the actual content of a FlowFile:

```python
# Get content (auto-detects text vs binary based on mime type)
content = nipyapi.canvas.get_flowfile_content(connection, flowfile_uuid)

# For text content, it's returned as a string
print(content)

# Force text decoding
text = nipyapi.canvas.get_flowfile_content(connection, uuid, decode='text')

# Force raw bytes
raw = nipyapi.canvas.get_flowfile_content(connection, uuid, decode='bytes')
```

### Save Content to File

```python
# Save using FlowFile's filename attribute (to current directory)
path = nipyapi.canvas.get_flowfile_content(connection, uuid, output_file=True)
print(f"Saved to: {path}")

# Save to specific directory
path = nipyapi.canvas.get_flowfile_content(connection, uuid, output_file='/tmp/debug/')

# Save to specific file path
path = nipyapi.canvas.get_flowfile_content(connection, uuid, output_file='/tmp/data.json')
```

### Decode Options

| Option | Behavior |
|--------|----------|
| `decode='auto'` | Use `mime.type` to decide text vs bytes (default) |
| `decode='text'` | Force UTF-8 decode |
| `decode='bytes'` | Return raw bytes |

---

## Peek (List + Details)

Convenience function to list and get details for the first N FlowFiles:

```python
# Get details for first 5 FlowFiles
flowfiles = nipyapi.canvas.peek_flowfiles(connection, limit=5)

for ff in flowfiles:
    print(f"{ff.filename}: {ff.mime_type}")
    print(f"  Attributes: {list(ff.attributes.keys())}")
```

This combines `list_flowfiles` and `get_flowfile_details` in one call.

---

## Common Patterns

### Debug a Transformation

Run a processor once and inspect its output:

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

# Get the processor and its output connection
proc = nipyapi.canvas.get_processor("UpdateRecord")
connections = nipyapi.canvas.list_all_connections(pg_id)
out_conn = next(c for c in connections if c.source_id == proc.id)

# Run once to process one FlowFile
nipyapi.canvas.schedule_processor(proc, "RUN_ONCE")

# Inspect output
flowfiles = nipyapi.canvas.peek_flowfiles(out_conn, limit=1)
if flowfiles:
    ff = flowfiles[0]
    print(f"Attributes: {ff.attributes}")
    content = nipyapi.canvas.get_flowfile_content(out_conn, ff.uuid)
    print(f"Content: {content[:1000]}")  # First 1000 chars
```

### Compare Before and After

```python
# Get connections before and after a processor
proc = nipyapi.canvas.get_processor("TransformProcessor")
connections = nipyapi.canvas.list_all_connections(pg_id)

in_conn = next(c for c in connections if c.destination_id == proc.id)
out_conn = next(c for c in connections if c.source_id == proc.id)

# Inspect input
in_ff = nipyapi.canvas.peek_flowfiles(in_conn, limit=1)
if in_ff:
    in_content = nipyapi.canvas.get_flowfile_content(in_conn, in_ff[0].uuid)
    print("INPUT:", in_content[:500])

# Run once
nipyapi.canvas.schedule_processor(proc, "RUN_ONCE")

# Inspect output
out_ff = nipyapi.canvas.peek_flowfiles(out_conn, limit=1)
if out_ff:
    out_content = nipyapi.canvas.get_flowfile_content(out_conn, out_ff[0].uuid)
    print("OUTPUT:", out_content[:500])
```

### Check Schema Attribute

For record-based flows, check the inferred or applied schema:

```python
ff = nipyapi.canvas.peek_flowfiles(connection, limit=1)[0]

if 'avro.schema' in ff.attributes:
    import json
    schema = json.loads(ff.attributes['avro.schema'])
    print(json.dumps(schema, indent=2))
```

---

## Available Functions

| Function | Purpose |
|----------|---------|
| `nipyapi.canvas.list_all_connections` | List connections in a process group |
| `nipyapi.canvas.list_flowfiles` | List FlowFile summaries in a connection |
| `nipyapi.canvas.get_flowfile_details` | Get full FlowFile metadata and attributes |
| `nipyapi.canvas.get_flowfile_content` | Download FlowFile content |
| `nipyapi.canvas.peek_flowfiles` | List and get details for first N FlowFiles |
| `nipyapi.canvas.purge_connection` | Remove all FlowFiles from a connection |

---

## Next Steps

After inspecting connections:

- **Found transformation issue** → Update processor configuration
- **Found schema mismatch** → See `references/author-snowflake-destination.md` for type mapping
- **Need to clear bad data** → Use `nipyapi.canvas.purge_connection(connection_id)`
- **Return to investigation** → Back to `references/ops-flow-investigation.md`

---

## Related References

- `references/ops-flow-lifecycle.md` - Run processor once, start/stop flow
- `references/ops-bulletins.md` - Error messages from processors
- `references/nifi-concepts.md` - FlowFile, connection, backpressure concepts
