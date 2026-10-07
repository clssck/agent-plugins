---
name: openflow-connector-streaming-transformations
description: Add custom processing between the streaming source and Snowflake - filtering, field mapping/flattening/renaming/removing, topic-to-table mapping, content-based routing to multiple tables, default values, Groovy scripts. Covers ser/de minimization, PartitionRecord/RouteOnAttribute/QueryRecord/JoltTransformRecord. Load when modifying data in-flight.
---

# Streaming Connectors — Custom Transformations

## Scope

This reference covers inserting custom processing between the source processor (e.g., ConsumeKafka) and the destination (PublishSnowpipeStreaming) for streaming connectors (Kafka high-performance, Kinesis):
- Filtering messages (by attribute/key or by content)
- Mapping / field transformations (flatten, rename, remove, defaults)
- Topic-to-table mapping
- Content-based routing to multiple tables
- Default values for null/empty fields
- Custom Groovy scripts
- ser/de minimization, connection configuration

For data type switching (JSON → Avro/Protobuf):
**Load** `references/connector-streaming-datatypes.md`

For Snowflake Private Key Auth (PublishSnowpipeStreaming) and overall routing:
**Load** `references/connector-streaming-main.md`

---

## Architecture

Insert a process group called **"Custom Transformations"** between the source processor (e.g., ConsumeKafka) and the destination processor (PublishSnowpipeStreaming).

```
ConsumeKafka
    ↓ (success)
[Custom Transformations Input]  ← Input Port
    ↓
    ... transformation processors ...
    ↓
[Custom Transformations Output] ← Output Port
    ↓
PublishSnowpipeStreaming
```

**Steps to create the group:**

1. Remove the existing connection between ConsumeKafka and PublishSnowpipeStreaming
2. Create a process group named `Custom Transformations`
3. Inside the group: create Input Port named `Custom Transformations Input`
4. Inside the group: create Output Port named `Custom Transformations Output`
5. Connect ConsumeKafka (success) → Custom Transformations Input
6. Connect Custom Transformations Output → PublishSnowpipeStreaming
7. **Connect all processors** inside the group in sequence.
8. **Add a NiFi Label** inside the Custom Transformations group displaying the restriction rules (see step below).

**Port creation requires `state` parameter:**

```python
input_port = nipyapi.canvas.create_port(
    pg_id=ct_pg.id,
    port_type='INPUT_PORT',
    name='Custom Transformations Input',
    position=layout.new_flow(),
    state='STOPPED'
)
output_port = nipyapi.canvas.create_port(
    pg_id=ct_pg.id,
    port_type='OUTPUT_PORT',
    name='Custom Transformations Output',
    position=layout.new_flow(),
    state='STOPPED'
)
```

**Cross-PG connections require raw API:**

`nipyapi.canvas.create_connection()` does NOT support connecting to/from a child process group's ports. You must use `ProcessGroupsApi().create_connection()` with a full `ConnectionEntity` that includes `source_type`, `destination_type`, `source_group_id`, and `destination_group_id` at the entity level:

```python
# Connect processor → child PG input port (or child PG output port → processor)
def create_cross_pg_connection(source_id, source_group_id, source_type,
                               dest_id, dest_group_id, dest_type,
                               relationships, parent_pg_id):
    conn_entity = nipyapi.nifi.ConnectionEntity(
        revision=nipyapi.nifi.RevisionDTO(version=0),
        source_type=source_type,
        destination_type=dest_type,
        source_group_id=source_group_id,
        destination_group_id=dest_group_id,
        component=nipyapi.nifi.ConnectionDTO(
            source=nipyapi.nifi.ConnectableDTO(
                id=source_id, group_id=source_group_id, type=source_type
            ),
            destination=nipyapi.nifi.ConnectableDTO(
                id=dest_id, group_id=dest_group_id, type=dest_type
            ),
            selected_relationships=relationships,
        )
    )
    return nipyapi.nifi.ProcessGroupsApi().create_connection(
        id=parent_pg_id, body=conn_entity
    )

# Example: ConsumeKafka → Custom Transformations Input Port
create_cross_pg_connection(
    source_id=consume_kafka.id,
    source_group_id=parent_pg_id,      # parent PG where ConsumeKafka lives
    source_type='PROCESSOR',
    dest_id=input_port.id,
    dest_group_id=ct_pg.id,            # child PG where the input port lives
    dest_type='INPUT_PORT',
    relationships=['success'],
    parent_pg_id=parent_pg_id
)

# Example: Custom Transformations Output Port → PSS
create_cross_pg_connection(
    source_id=output_port.id,
    source_group_id=ct_pg.id,
    source_type='OUTPUT_PORT',
    dest_id=pss.id,
    dest_group_id=parent_pg_id,
    dest_type='PROCESSOR',
    relationships=None,  # OUTPUT_PORT pass-through — verified against preprod8 (selected_relationships=null on live connectors)
    parent_pg_id=parent_pg_id
)
```

**Valid `source_type`/`destination_type` values:** `PROCESSOR`, `INPUT_PORT`, `OUTPUT_PORT`, `FUNNEL`


For detailed commands on creating process groups, processors, connections, and ports, **Load** `references/author-building-flows.md`.

## Restriction Rules

**These rules must be followed. Violating them causes data loss or performance degradation.**

**⚠️ MANDATORY — Create NiFi Label (Step 8 from Architecture):**

After creating the Custom Transformations process group, you MUST create a NiFi Label inside it displaying the restriction rules below. This is not optional — execute this before adding any transformation processors.

**Run exactly** (substitute `<profile>` and `<ct-pg-id>` from session — the Custom Transformations process group ID):
```python
import nipyapi
nipyapi.profiles.switch('<profile>')

LABEL_TEXT = """RESTRICTIONS:
1. Minimize ser/de operations. Plan transformations BEFORE creating processors.
   Combine filtering, renaming, defaults into as few record-aware processors as
   possible. Extract useful attributes (e.g., routing fields) in a QueryRecord
   or first ser/de processor so downstream processors can use RouteOnAttribute
   (no ser/de) instead of PartitionRecord (extra ser/de).

2. Any processor requiring ser/de MUST use the existing flow JsonTreeReader
   (schema inference with VolatileSchemaCache) and the flow JsonRecordSetWriter.
   Do NOT create a separate "internal" reader — reuse the reader already in the
   connector's process group.

3. A single FlowFile can contain data for only ONE table. Prefer RouteOnAttribute
   over PartitionRecord when the routing field can be extracted as an attribute
   by an upstream ser/de processor (saves one ser/de operation).

4. Array exploding to the same table is NOT possible.
   Array exploding is only valid when routing to different tables.

6. Use the existing flow JsonTreeReader (with VolatileSchemaCache) and
   JsonRecordSetWriter for all record-aware processors. Schema inference handles
   structural changes automatically."""

label_entity = nipyapi.nifi.LabelEntity(
    revision=nipyapi.nifi.RevisionDTO(version=0),
    component=nipyapi.nifi.LabelDTO(
        parent_group_id='<ct-pg-id>',
        label=LABEL_TEXT,
        position=nipyapi.nifi.PositionDTO(x=0.0, y=0.0),
        width=800.0,
        height=400.0
    )
)
nipyapi.nifi.ProcessGroupsApi().create_label(id='<ct-pg-id>', body=label_entity)
```

**Verify the label was created:**
```python
labels = nipyapi.nifi.ProcessGroupsApi().get_labels('<ct-pg-id>')
assert any('RESTRICTIONS' in l.component.label for l in labels.labels), (
    "NiFi Label with restriction rules was NOT created inside Custom Transformations group"
)
```

The restriction rules text for reference:

```
RESTRICTIONS:
1. Minimize ser/de operations. Plan transformations BEFORE creating processors.
   Combine filtering, renaming, defaults into as few record-aware processors as
   possible. Extract useful attributes (e.g., routing fields) in a QueryRecord
   or first ser/de processor so downstream processors can use RouteOnAttribute
   (no ser/de) instead of PartitionRecord (extra ser/de).

2. Any processor requiring ser/de MUST use the existing flow JsonTreeReader
   (schema inference with VolatileSchemaCache) and the flow JsonRecordSetWriter.
   Do NOT create a separate "internal" reader — reuse the reader already in the
   connector's process group.

3. A single FlowFile can contain data for only ONE table. Prefer RouteOnAttribute
   over PartitionRecord when the routing field can be extracted as an attribute
   by an upstream ser/de processor (saves one ser/de operation).

4. Array exploding to the same table is NOT possible.
   Array exploding is only valid when routing to different tables.

6. Use the existing flow JsonTreeReader (with VolatileSchemaCache) and
   JsonRecordSetWriter for all record-aware processors. Schema inference handles
   structural changes automatically.
```

### Setting Up Reader/Writer for Transformations

Transformation processors that access FlowFile content (ser/de) need a Record Reader and Record Writer. **Reuse the existing JsonTreeReader and JsonRecordSetWriter from the connector's parent process group** — do NOT create new ones inside the Custom Transformations group. Controller services defined at the parent PG level are visible to child PGs.

**Locate the existing services:**

```python
pg_id = '<connector-pg-id>'  # Parent PG (not the Custom Transformations PG)
controllers = nipyapi.canvas.list_all_controllers(pg_id)
json_reader = next(c for c in controllers if 'JsonTreeReader' in c.component.type)
json_writer = next(c for c in controllers if 'JsonRecordSetWriter' in c.component.type)
print(f"Reader: {json_reader.id}, Writer: {json_writer.id}")
```

**Add VolatileSchemaCache to the reader** (if not already configured):

The existing JsonTreeReader uses schema inference. To avoid re-inferring the schema on every FlowFile, add a `VolatileSchemaCache` service and configure the reader to use it:

```python
# Create VolatileSchemaCache at the connector PG level
pg = nipyapi.canvas.get_process_group(pg_id, identifier_type='id')
cs_type = nipyapi.canvas.get_controller_type('VolatileSchemaCache')
schema_cache = nipyapi.canvas.create_controller(pg, cs_type, 'VolatileSchemaCache')

# Configure cache size (default 100 is usually sufficient)
update_dto = nipyapi.nifi.ControllerServiceDTO(
    properties={
        'Maximum Cache Size': '100'
    }
)
nipyapi.canvas.update_controller(schema_cache, update_dto)

# IMPORTANT: Re-fetch entity before enabling (revision changes after update)
schema_cache = nipyapi.canvas.get_controller(schema_cache.id, identifier_type='id')
nipyapi.canvas.schedule_controller(schema_cache, True)

# Disable the reader before updating (required)
nipyapi.canvas.schedule_controller(json_reader, False)
# Re-fetch reader after state change
json_reader = nipyapi.canvas.get_controller(json_reader.id, identifier_type='id')

# Configure the reader to use the cache
update_dto = nipyapi.nifi.ControllerServiceDTO(
    properties={
        'Schema Inference Cache': schema_cache.id
    }
)
nipyapi.canvas.update_controller(json_reader, update_dto)

# Re-fetch before re-enabling
json_reader = nipyapi.canvas.get_controller(json_reader.id, identifier_type='id')
nipyapi.canvas.schedule_controller(json_reader, True)
```

**Revision conflict pattern:** Any time you update or change the state of a controller service, the entity's revision increments. Re-fetch the entity via `get_controller(id, identifier_type='id')` before the next operation (update or enable/disable). Failing to do so causes a 409 Conflict error.

This significantly improves performance for repeated messages with the same structure — the inferred schema is cached and reused instead of being re-parsed on every FlowFile.

**Rule:** Every record-aware processor that transforms content MUST reference the existing connector-level `JsonTreeReader` and `JsonRecordSetWriter`. Do NOT create additional readers/writers inside the Custom Transformations group.

---

### Parameterization (after wiring transformations)

**After wiring all transformation processors, inspect hardcoded property values and offer to store suitable ones in the connector's parameter context.** This makes the flow easier to maintain and reconfigure without editing processors.

**Good candidates for parameters:**
- Connection strings, URLs, hostnames
- Topic-to-table mappings
- Schema Registry URLs and credentials
- Threshold values, timeouts, constants

**NOT suitable for parameters:**
- Groovy scripts (too large, better inline in processor)
- Jolt transformation specs (complex JSON, better inline)
- Filter conditions and routing rules (better inline in processor)
- Large schema definitions

Use `references/ops-parameters-main.md` to add parameters to the context.

---

### Transformation Planning (before creating processors)

**Before creating any processor, plan the full transformation pipeline to minimize ser/de operations.** Do not create processors one-by-one without a plan.

**Planning checklist:**

1. **List all required transformations** (filtering, renaming, defaults, routing, etc.)
2. **Identify which can be done on attributes alone** (no ser/de):
   - Topic-based routing → `UpdateAttribute` (zero ser/de)
   - Attribute-based filtering → `RouteOnAttribute` (zero ser/de)
   - **Note:** Attribute-only processors work ONLY when the FlowFile already has the attribute set (e.g., `kafka.topic` from ConsumeKafka, or attributes set by a prior PartitionRecord)
3. **Combine content transformations into minimal ser/de processors:**
   - Filtering + renaming + defaults → ONE `JoltTransformRecord` with Chain spec or ONE `QueryRecord`
   - If content-based routing to multiple tables is needed, you MUST use `PartitionRecord` to split the FlowFile so each output FlowFile contains records for only ONE table. A single FlowFile may contain multiple records with different field values — you cannot skip partitioning.
4. **PartitionRecord is required for multi-table routing:**
   - A FlowFile can contain many records. Even if you extract a field value as an attribute, that attribute represents only ONE value — but the FlowFile may contain records with DIFFERENT values for that field.
   - `PartitionRecord` splits the FlowFile into separate FlowFiles, each containing only records with the same value for the partition field. The field value becomes a FlowFile attribute.
   - After PartitionRecord, you can use `RouteOnAttribute` (zero ser/de) to filter based on the partitioned attribute.
   - **Multi-table routing does NOT require RouteOnAttribute.** PSS with `Table = ${attribute}` handles it natively. RouteOnAttribute is ONLY needed to drop/filter unwanted values.
5. **Order: content transforms BEFORE partitioning, attribute ops AFTER:**
   - Rename/default/filter first (operates on the full FlowFile — one ser/de pass)
   - Then partition (splits into per-value FlowFiles — one ser/de pass)
   - Then UpdateAttribute (set table.name — zero ser/de)
   - Then RouteOnAttribute ONLY if filtering is needed (zero ser/de)

**Step 6: Count ser/de passes and present choice**

After planning Option A (the readable pipeline with standard processors), count the total ser/de passes. If the pipeline has **2 or more ser/de passes**, a single Groovy script could consolidate ALL content operations (filtering, renaming, defaults, partitioning) into 1 ser/de pass. In that case, you **MUST** present both options to the user before implementing.

**Ask the user which approach they prefer:**

> "Here's my plan for the transformation pipeline:
>
> **Option A — Readable ({N} ser/de passes):**
> ```
> {describe the planned pipeline with labeled ser/de passes}
> ```
> Uses standard NiFi processors — easy to maintain, debug, and modify later.
>
> **Option B — Optimized (1 ser/de pass):**
> ```
> Input Port
>   → ExecuteGroovyScript (ser/de #1: {list ALL content operations combined})
>   → {attribute-only processors if needed}
>   → Output Port
> ```
> A single Groovy script handles all content operations in one pass — better performance but more complex to modify later.
>
> Which do you prefer?"

Choose Option A as default unless the user explicitly requests maximum performance. If the pipeline only has 1 ser/de pass, skip this question — there's nothing to optimize.

**Example — "filter by timestamp, rename fields, add defaults, route to tables by field value":**

**Option A — Readable (3 ser/de passes):**
```
Input Port
  → JoltTransformRecord (ser/de #1: rename fields + defaults)
  → QueryRecord (ser/de #2: filter by timestamp)
  → PartitionRecord (ser/de #3: split by routing field → sets attribute)
  → UpdateAttribute (zero ser/de: set table.name = ${routing-field})
  → RouteOnAttribute (zero ser/de: filter unwanted values, auto-terminate unmatched)
  → Output Port
```

**Option A — Readable (2 ser/de passes, combined filter+rename):**
```
Input Port
  → QueryRecord (ser/de #1: rename via SELECT aliases + defaults via COALESCE + filter via WHERE)
  → PartitionRecord (ser/de #2: split by routing field → sets attribute)
  → UpdateAttribute (zero ser/de: set table.name = ${routing-field})
  → RouteOnAttribute (zero ser/de: filter unwanted values, auto-terminate unmatched)
  → Output Port
```

**Option B — Maximum performance (1 ser/de pass):**
```
Input Port
  → ExecuteGroovyScript (ser/de #1: rename + defaults + filter + partition into separate FlowFiles by routing field)
  → UpdateAttribute (zero ser/de: set table.name = ${routing-field})
  → RouteOnAttribute (zero ser/de: filter unwanted values)
  → Output Port
```

Option B combines all content operations into a single Groovy script that reads each record, applies transformations, filters, and emits separate FlowFiles per routing field value.

PSS `Table` = `${table.name}` — handles multi-table routing natively. RouteOnAttribute is ONLY for filtering (dropping unwanted values), not for routing.

**When planning Option A, also minimize within that tier:**
- Combine filter + rename + defaults into a single processor where possible (QueryRecord with SQL aliases and WHERE, or JoltTransformRecord Chain spec)
- Only use separate processors when operations genuinely cannot be combined (e.g., PartitionRecord must be separate because it changes FlowFile boundaries)

**Anti-pattern — wasteful pipeline:**
```
Input Port
  → QueryRecord (ser/de #1: filter only)
  → JoltTransformRecord (ser/de #2: rename only)
  → PartitionRecord (ser/de #3: split by field)
  → UpdateAttribute (set table name)  ← one per route — WRONG
  → Output Port
```
The anti-pattern uses 3 ser/de passes where 2 would suffice (combine filter+rename into one processor). Additionally, creating separate UpdateAttribute processors per route value is unnecessary — use a single UpdateAttribute with `table.name = ${routing-field}` before any filtering.

---

### Connection Configuration

**PSS queue size:** Set the back-pressure object threshold on the connection leading into `PublishSnowpipeStreaming` to **5 GB** (change `Back Pressure Object Threshold` from the default `1 GB`). PSS holds FlowFiles in the queue until Snowflake acknowledges ingestion — with the default 1 GB limit, this queue triggers backpressure under normal load and stalls upstream processors.

---

### Processor Type Disambiguation

When `get_processor_type()` returns **multiple results** (a list), you must select the correct one. Common ambiguous types:

| Search Term | Results | Correct Choice |
|-------------|---------|----------------|
| `PartitionRecord` | ScriptedPartitionRecord, **PartitionRecord** | `next(r for r in results if 'Scripted' not in r.type)` |
| `JoltTransformRecord` | May return JoltTransformJSON too | `next(r for r in results if 'JoltTransformRecord' in r.type)` |

**Always check:**
```python
results = nipyapi.canvas.get_processor_type('PartitionRecord')
if isinstance(results, list):
    proc_type = next(r for r in results if 'Scripted' not in r.type)
else:
    proc_type = results
```

---

### Finalizing a Processor — Auto-Termination

`prepare_processor_config(proc, {...})` returns a **`ProcessorConfigDTO`** (not a `ProcessorEntity`). Property values go in the dict; set auto-terminated relationships as an **attribute on that returned object** before `update_processor`:

- **`auto_terminated_relationships = [...]`** — every relationship that is neither connected onward nor auto-terminated leaves the processor INVALID and accumulates FlowFiles.

Use this helper in every pattern below instead of calling `update_processor` directly:

```python
def finalize_processor(proc, config, auto_terminate=None, max_tasks=None):
    """Set auto-terminated relationships (and optionally Max Task Count) on the config, then update."""
    if max_tasks is not None:
        config.concurrently_schedulable_task_count = max_tasks
    if auto_terminate:
        config.auto_terminated_relationships = auto_terminate
    nipyapi.canvas.update_processor(proc, update=config)
```

---

### Transformation Patterns

Ask the user what transformation they need. Present options:

> "What transformation do you need?
> - **Filter messages** — drop messages based on attributes, keys, or content
> - **Map/transform fields** — flatten, rename, or remove fields
> - **Topic-to-table mapping** — route messages to different tables based on topic
> - **Default values** — fill in null or empty fields
> - **Content-based routing** — route to different tables based on message content
> - **Custom Groovy script** — anything that doesn't fit the above patterns
> - **Something else** — describe what you need"

If the user describes a transformation not listed above, validate it against the [Restriction Rules](#restriction-rules) before implementing. Key questions to ask:
- Does it require accessing FlowFile content? (ser/de impact)
- Does it split messages across multiple tables? (partitioning required)

- Does it explode arrays into separate records for the same table? (NOT allowed)

If the transformation is feasible within the rules, use the Groovy script pattern or an appropriate NiFi processor. If it violates a rule, explain the constraint and propose an alternative.

---

#### Pattern: Filtering Messages

> Before creating any processors, present a plan and ask for approval:
>
> "I will add the following inside the Custom Transformations group:
> - `RouteOnAttribute` ('FilterByAttribute') — routes matching messages to a named relationship; unmatched go to `unmatched`
> (or `QueryRecord` ('FilterByContent') if filtering by message content)
>
> Proceed? (Yes / No / Modify)"

**By attributes/keys (no ser/de — preferred):**

Use `RouteOnAttribute` processor. Does NOT access FlowFile content, so no performance impact.

```python
proc_type = nipyapi.canvas.get_processor_type('RouteOnAttribute')
filter_proc = nipyapi.canvas.create_processor(pg, proc_type, layout.new_flow(), 'FilterByAttribute')
```

Configure with Expression Language conditions as dynamic properties:
- Messages matching a condition route to that relationship
- Unmatched messages route to `unmatched`
- Connect desired relationship → Output Port
- Connect `unmatched` → auto-terminate (to drop) or to Output Port (to keep)

**By content (requires ser/de):**

Use `QueryRecord` processor with SQL WHERE clause. Requires the existing flow `JsonTreeReader` and `JsonRecordSetWriter` (do NOT create a separate reader/writer).

```python
proc_type = nipyapi.canvas.get_processor_type('QueryRecord')
query_proc = nipyapi.canvas.create_processor(pg, proc_type, layout.new_flow(), 'FilterByContent')

config = nipyapi.canvas.prepare_processor_config(query_proc, {
    'Record Reader': '<json-reader-id>',
    'Record Writer': '<json-writer-id>',
    'filtered': "SELECT * FROM FLOWFILE WHERE <condition>"
}, allow_dynamic=True)
finalize_processor(query_proc, config, auto_terminate=['original', 'failure'])
```

Route `filtered` relationship → Output Port. `original` and `failure` are auto-terminated above.

---

#### Pattern: Mapping / Field Transformations

> Before creating any processors, present a plan and ask for approval:
>
> "I will add the following inside the Custom Transformations group:
> - `JoltTransformRecord` ('TransformFields') — applies the Jolt Chain spec (rename, flatten, remove, defaults) in one ser/de pass
>
> Proceed? (Yes / No / Modify)"

Use `JoltTransformRecord` for record-aware JSON transformations (ser/de with proper reader/writer). Handles:
- **Flattening:** Shift spec to move nested fields to top level
- **Renaming fields:** Shift spec with new field names
- **Removing fields:** Remove spec to drop unwanted fields
- **Default values:** Default spec for null/missing fields

**Always use `JoltTransformRecord` (not `JoltTransformJSON`).** `JoltTransformRecord` is record-aware — it uses the flow's Record Reader/Writer and properly handles schema changes. `JoltTransformJSON` treats the **entire FlowFile as a single JSON document** and **must not be used** with high-performance connectors: these produce NDJSON (one JSON object per line), which `JoltTransformJSON` rejects as invalid input. Always use `JoltTransformRecord`.

**Simpler alternative for add/rename/remove/default:** `UpdateRecord` uses RecordPath expressions with SQL-style syntax and is often more readable than Jolt specs for single-step operations. Use it when you only need one operation and don't need to chain multiple transforms in one ser/de pass (see [Default Values pattern](#pattern-default-values-for-nullempty-fields) for a code example).

**Content-based filtering without Jolt:** `QueryRecord` applies a SQL `WHERE` clause directly against FlowFile records. It is the recommended alternative to combining `RouteOnAttribute` with field-shifting Jolt specs when the routing condition depends on record content rather than attributes.

```python
proc_type = nipyapi.canvas.get_processor_type('JoltTransformRecord')
jolt_proc = nipyapi.canvas.create_processor(pg, proc_type, layout.new_flow(), 'TransformFields')

config = nipyapi.canvas.prepare_processor_config(jolt_proc, {
    'Record Reader': '<json-reader-id>',
    'Record Writer': '<json-writer-id>',
    'Jolt Specification': '<jolt-spec-json>',
    'Jolt Transform': 'jolt-transform-chain'
})
finalize_processor(jolt_proc, config, auto_terminate=['failure', 'original'])
```

**Combine multiple operations** into a single Chain spec to minimize ser/de:

```json
[
  {"operation": "default", "spec": { "fieldName": "defaultValue" }},
  {"operation": "shift", "spec": { "oldName": "newName", "*": "&" }},
  {"operation": "remove", "spec": { "unwantedField": "" }}
]
```

**Tip:** Combine filtering + renaming + defaults into ONE `JoltTransformRecord` when possible. A single Chain spec with default + shift + remove handles all three in one ser/de pass.

---

#### Pattern: Topic-to-Table Mapping

> Before creating any processors, present a plan and ask for approval:
>
> "I will add the following inside the Custom Transformations group:
> - `UpdateAttribute` ('SetTableFromTopic' / 'SetTableFromStream') — maps the source topic/stream name to a Snowflake table name via the `Topic To Table Map` parameter
> - Update `PublishSnowpipeStreaming` `Table` property to `${table.name}`
>
> Proceed? (Yes / No / Modify)"

Route messages to different Snowflake tables based on the source topic or stream name.

**Inside Custom Transformations group:**

Use `UpdateAttribute` with a dynamic property `table.name` that applies a topic-to-table mapping. The source attribute differs by connector type:

For **Kafka** (`kafka.topic` is set automatically by `ConsumeKafka`):

```python
proc_type = nipyapi.canvas.get_processor_type('UpdateAttribute')
update_attr = nipyapi.canvas.create_processor(pg, proc_type, layout.new_flow(), 'SetTableFromTopic')

config = nipyapi.canvas.prepare_processor_config(update_attr, {
    'table.name': "${kafka.topic:replaceByPattern(#{'Topic To Table Map'})}"
})
finalize_processor(update_attr, config)   # UpdateAttribute has only 'success' — no auto-terminate needed
```

For **Kinesis** (`aws.kinesis.stream.name` is set automatically by `ConsumeKinesisStream`):

```python
proc_type = nipyapi.canvas.get_processor_type('UpdateAttribute')
update_attr = nipyapi.canvas.create_processor(pg, proc_type, layout.new_flow(), 'SetTableFromStream')

config = nipyapi.canvas.prepare_processor_config(update_attr, {
    'table.name': "${aws.kinesis.stream.name:replaceByPattern(#{'Topic To Table Map'})}"
})
finalize_processor(update_attr, config)
```

**Add `Topic To Table Map` parameter** to the connector's parameter context. Ask the user for the mapping value.

This parameter maps topic names (or regex patterns) to Snowflake table names. Each topic-table pair is separated by a colon, multiple pairs separated by commas. Table names must be valid Snowflake unquoted identifiers. Regex patterns must be unambiguous — a topic must match only a single target table. If empty or no match found, the topic name is used as the table name.

Examples:
- Explicit mapping: `topic1:low_range,topic2:low_range,topic5:high_range,topic6:high_range`
- Regex mapping: `topic[0-4]:low_range,topic[5-9]:high_range`

**Update PublishSnowpipeStreaming** to use the attribute for table name:

```python
pss = nipyapi.canvas.get_processor('<publish-snowpipe-streaming-id>')
config = nipyapi.canvas.prepare_processor_config(pss, {
    'Table': '${table.name}'
})
nipyapi.canvas.update_processor(pss, update=config)
```

No ser/de needed — this operates on FlowFile attributes only.

---

#### Pattern: Default Values for Null/Empty Fields

> Before creating any processors, present a plan and ask for approval:
>
> "I will add the following inside the Custom Transformations group:
> - `JoltTransformRecord` with a `default` operation (combined with any other Jolt ops in one ser/de pass)
> (or `UpdateRecord` ('SetDefaults') with RecordPath expressions if a standalone step is preferred)
>
> Proceed? (Yes / No / Modify)"

Use `JoltTransformRecord` with a `default` operation (combine with other Jolt ops in a Chain), or `UpdateRecord` with RecordPath expressions.

**JoltTransformRecord (preferred — combine with other Jolt ops in one ser/de pass):**

```json
[
  {"operation": "default", "spec": {
    "field_name": "default_value",
    "nested": {"field": "default_value"}
  }}
]
```

**UpdateRecord alternative:**

```python
proc_type = nipyapi.canvas.get_processor_type('UpdateRecord')
update_rec = nipyapi.canvas.create_processor(pg, proc_type, layout.new_flow(), 'SetDefaults')

config = nipyapi.canvas.prepare_processor_config(update_rec, {
    'Record Reader': '<json-reader-id>',
    'Record Writer': '<json-writer-id>',
    '/field_name': "replaceNull(/field_name, 'default_value')"
}, allow_dynamic=True)
finalize_processor(update_rec, config, auto_terminate=['failure'])
```

---

#### Pattern: Content-Based Routing to Multiple Tables

> Before creating any processors, present a plan and ask for approval:
>
> "I will add the following inside the Custom Transformations group:
> - `PartitionRecord` ('PartitionByField') — splits the FlowFile so each output FlowFile contains records for only one routing-field value
> - (Optional) `UpdateAttribute` ('SetTableName') — maps partitioned attribute to final table name
> - (Optional) `RouteOnAttribute` ('FilterByField') — only if unwanted values need to be dropped
> - Update `PublishSnowpipeStreaming` `Table` property to reference the partitioned attribute
>
> Proceed? (Yes / No / Modify)"

Route messages to different Snowflake tables based on a field value in the message content.

**CRITICAL:** A single FlowFile can contain MULTIPLE records with DIFFERENT values for the routing field. You MUST use `PartitionRecord` to split the FlowFile so each output FlowFile contains records for only ONE table. There is no shortcut — partitioning is always required for multi-table routing.

**Key insight: PublishSnowpipeStreaming handles multi-table routing natively.** After `PartitionRecord` splits by the routing field and sets the field value as a FlowFile attribute, you only need to set the PSS `Table` property to reference that attribute via Expression Language (e.g., `${animalType}` or `${table.name}`). No RouteOnAttribute or per-table UpdateAttribute is needed for routing alone.

**RouteOnAttribute is ONLY needed for filtering** — i.e., dropping FlowFiles with unwanted field values. If all values are valid table destinations, skip RouteOnAttribute entirely.

**Step 1:** Use `PartitionRecord` to split by the routing field:

**Disambiguation:** `get_processor_type('PartitionRecord')` returns MULTIPLE results. Always filter:
```python
results = nipyapi.canvas.get_processor_type('PartitionRecord')
proc_type = next(r for r in results if 'standard.PartitionRecord' in r.type)
```

```python
partition_proc = nipyapi.canvas.create_processor(pg, proc_type, layout.new_flow(), 'PartitionByField')

config = nipyapi.canvas.prepare_processor_config(partition_proc, {
    'Record Reader': '<json-reader-id>',
    'Record Writer': '<json-writer-id>',
    '<routing-field-name>': '/routing_field'
}, allow_dynamic=True)

finalize_processor(partition_proc, config, auto_terminate=['failure', 'original'])
```

This creates separate FlowFiles for each distinct value of the routing field. The field value is set as a FlowFile attribute (e.g., attribute `animalType` = `dog`).

**Step 2 (optional mapping):** Use a single `UpdateAttribute` to set `table.name` from the partitioned attribute:

```python
proc_type = nipyapi.canvas.get_processor_type('UpdateAttribute')
ua_proc = nipyapi.canvas.create_processor(pg, proc_type, layout.new_flow(), 'SetTableName')

config = nipyapi.canvas.prepare_processor_config(ua_proc, {
    'table.name': '${<routing-field-attribute>}'
}, allow_dynamic=True)
finalize_processor(ua_proc, config)   # UpdateAttribute has only 'success'
```

This step is optional — use it when the attribute value differs from the desired table name (e.g., mapping `animalType=DOG` → `table.name=dogs_table`). If the attribute value IS the table name, skip this and set PSS `Table` directly to `${<attribute>}`.

**Step 3 (optional filtering):** Use `RouteOnAttribute` ONLY if you need to drop unwanted values:

```python
proc_type = nipyapi.canvas.get_processor_type('RouteOnAttribute')
route_proc = nipyapi.canvas.create_processor(pg, proc_type, layout.new_flow(), 'FilterByField')

config = nipyapi.canvas.prepare_processor_config(route_proc, {
    'dog': "${animalType:equals('dog')}",
    'cat': "${animalType:equals('cat')}"
}, allow_dynamic=True)
finalize_processor(route_proc, config, auto_terminate=['unmatched'])
```

- Matched relationships (`dog`, `cat`) → connect ALL to Output Port (single connection with multiple relationships)
- `unmatched` → auto-terminate (filtered out)

**Do NOT create separate UpdateAttribute processors per route.** Use one UpdateAttribute before RouteOnAttribute that sets `table.name` from the partitioned attribute.

**Step 4:** Update PublishSnowpipeStreaming: `Table` = `${table.name}` (or `${<attribute>}` directly)

PSS supports Expression Language (FlowFile attributes) on the `Database`, `Schema`, `Table`, AND `Pipe` properties — not just `Table`. It evaluates each per FlowFile, so a single PSS processor can fan out across different databases, schemas, and tables. To route fully dynamically, set upstream attributes (via `UpdateAttribute` / `PartitionRecord`) and reference them, e.g. `Database` = `${target.db}`, `Schema` = `${target.schema}`, `Table` = `${table.name}`. No additional routing logic needed.



**Summary of patterns:**

| Need | Pipeline |
|------|----------|
| Route to multiple tables (all values valid) | PartitionRecord → Output Port. PSS `Table` = `${field}` |
| Route to multiple tables + rename attribute | PartitionRecord → UpdateAttribute (set table.name) → Output Port |
| Route to multiple tables + filter some values | PartitionRecord → UpdateAttribute → RouteOnAttribute (filter) → Output Port |

---

#### Pattern: Groovy Script (Catch-All)

> Before creating any processors, present a plan and ask for approval:
>
> "I will add the following inside the Custom Transformations group:
> - `ExecuteGroovyScript` ('CustomTransform') — applies the custom transformation logic in one ser/de pass
>
> Proceed? (Yes / No / Modify)"

Use `ExecuteGroovyScript` for transformations that don't fit the above patterns. The agent should help the user write the Groovy script for their specific use case.

```python
proc_type = nipyapi.canvas.get_processor_type('ExecuteGroovyScript')
groovy_proc = nipyapi.canvas.create_processor(pg, proc_type, layout.new_flow(), 'CustomTransform')
```

**Restriction rule still applies:**
- Single table per FlowFile output

**CRITICAL: Preserve original FlowFile attributes.** The Groovy script MUST NOT remove or overwrite incoming attributes (e.g., `kafka.topic`, `kafka.partition`). These are used in `PublishSnowpipeStreaming` channel names — the connectors do not track offsets, but topic and partition IDs must be preserved. When creating output FlowFiles, always inherit attributes from the incoming FlowFile.

**Common Groovy patterns:**
- Record-by-record transformation with `RecordReader`/`RecordWriter`
- Attribute manipulation (adding new attributes — never removing originals)
- Complex conditional logic
- Multi-field computed values

Ask the user to describe their transformation requirements and help them write the script. Validate the script handles edge cases (nulls, missing fields, type mismatches).

---

### Combining Transformations

Multiple transformation processors can be chained inside the Custom Transformations group:

```
Input Port → Processor A → Processor B → ... → Output Port
```

**Ordering principle:** Place attribute-only processors (no ser/de) BEFORE content-access processors. For example, filter messages by attribute/key first to drop unwanted data early, then apply costly ser/de transformations (Jolt, QueryRecord, etc.) only on messages that will actually be written to Snowflake.

**Minimize ser/de:** If multiple operations need content access, combine them into a single processor where possible (e.g., Chain multiple Jolt operations in one JoltTransformRecord).

**Connection rules between processors:**
- Route failures/errors appropriately (auto-terminate or to a dead-letter output)

---

## Verification

After creating all processors, wiring all connections, and updating PSS, run a full verification pass. **But first — enable all controller services.** `verify_config` validates processors, but processors reference controller services. If services are DISABLED, processors that depend on them will show as INVALID.

**Step 1: Enable all disabled services:**

```python
controllers = nipyapi.canvas.list_all_controllers(parent_pg_id)
for cs in controllers:
    if cs.component.state == 'DISABLED':
        cs = nipyapi.canvas.get_controller(cs.id, identifier_type='id')
        nipyapi.canvas.schedule_controller(cs, True)
        print(f"Enabled: {cs.component.name}")
```

**Step 2: Run verify_config:**

**Run exactly** (substitute `<profile>` and `<connector-pg-id>` from session):
```bash
nipyapi --profile <profile> ci verify_config --process_group_id "<connector-pg-id>"
```

**Step 3: Interpret results:**

| Result | Action |
|--------|--------|
| All passed | Inform user: "All components verified. Ready to start." |
| Processor INVALID | Check `failures[].explanation` — usually a disabled service dependency or missing property |
| Controller skipped (already ENABLED) | Normal — verify_config only enables DISABLED services |

**Common verification failure:** A processor referencing a service that was DISABLED at validation time. The fix is always: enable the service first, then re-run verify_config.

---

## Troubleshooting

| Symptom | Likely Cause |
|---------|--------------|


---

## Next Step

After completing the transformations, if you arrived here from `references/connector-main.md` deployment workflow, **Continue** to `references/connector-main.md` Step 9 (Verify Controllers).

If a data type change is also needed, **Load** `references/connector-streaming-datatypes.md`.
If Snowflake Private Key Auth is also needed, **Load** `references/connector-streaming-main.md`.

Otherwise, the customization is complete.

---

## See Also

- `references/connector-streaming-main.md` — Streaming customization router + Snowflake Private Key Auth
- `references/connector-streaming-datatypes.md` — JSON → Avro/Protobuf data type switching
- `references/connector-kafka.md` — Kafka broker auth customizations (MSK IAM, mTLS)
- `references/connector-main.md` — General connector deployment workflow
- `references/author-building-flows.md` — Creating processors and connections (inspect-modify-test)
- `references/ops-parameters-main.md` — Parameter configuration
- `references/nifi-expression-language.md` — Expression Language syntax for attributes
- `references/nifi-recordpath.md` — RecordPath syntax for field operations
