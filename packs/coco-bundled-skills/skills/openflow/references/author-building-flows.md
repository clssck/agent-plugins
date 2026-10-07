---
name: openflow-author-building-flows
description: Build custom NiFi flows with the inspect-modify-test cycle. Component CRUD operations, connecting processors, and iterative development.
---

# Building Flows

Create and modify custom NiFi flows using the inspect-modify-test cycle.

**Scope:** Component CRUD (create, inspect, update, delete), testing with RUN_ONCE, validation.

**Prerequisite:** Review flow design principles in `author-main.md` before building.

---

## Operations Overview

| Operation | Function | Section |
|-----------|----------|---------|
| Create process group | `canvas.create_process_group()` | [Create](#create) |
| Create processor | `canvas.create_processor()` | [Create](#create) |
| Create connection | `canvas.create_connection()` | [Create](#create) |
| Create controller | `canvas.create_controller()` | [Create](#create) |
| Create input/output port | `canvas.create_port()` | [Modular Design](#modular-flow-design) |
| Get/inspect component | `canvas.get_processor()`, `get_controller()` | [Inspect](#inspect) |
| List components | `canvas.list_all_processors()`, etc. | [Inspect](#inspect) |
| Update properties | `canvas.update_processor()`, `update_controller()` | [Update](#update) |
| Delete component | `canvas.delete_processor()`, etc. | [Delete](#delete) |
| Validate config | `canvas.verify_processor()`, `ci.verify_config()` | [Validate](#validate) |
| Test single FlowFile | `canvas.schedule_processor(p, 'RUN_ONCE')` | [Testing](#testing-your-flow) |
| Organize into child PGs | Child PGs with ports | [Modular Design](#modular-flow-design) |

---

## The Inspect-Modify-Test Cycle

Authoring is iterative. **One change at a time, with validation between each.**

1. **Inspect** - Check current state, read properties, view FlowFile content
2. **Modify** - Make ONE change (create one component, update one property)
3. **Test** - Verify that specific change worked before proceeding
4. **Repeat** - Until flow works as expected

**Anti-pattern:** Jumping straight into writing multi-step scripts that create multiple components at once. When they fail, you don't know which step failed.

**Discovery before action:** Before using any function for the first time, check its signature:
```bash
nipyapi canvas create_processor --help
nipyapi canvas get_processor_docs --processor <name>
nipyapi canvas get_controller_docs --controller <name>
```
```python
help(nipyapi.canvas.create_processor)
```

---

## Create

```python
import nipyapi
import nipyapi.layout as layout
nipyapi.profiles.switch('<profile>')

# Process group (NEVER build on root canvas)
pg = nipyapi.canvas.create_process_group(
    parent_pg="root",
    new_pg_name="My Custom Flow",
    location=layout.suggest_pg_position("root")
)

# Processors
proc_type = nipyapi.canvas.get_processor_type('UpdateRecord')
proc = nipyapi.canvas.create_processor(pg, proc_type, layout.new_flow(), "Transform")

# Connections
conn = nipyapi.canvas.create_connection(source_proc, dest_proc, ['success'])

# Controller services (in same PG as processors that use them)
cs_type = nipyapi.canvas.get_controller_type('JsonTreeReader')
cs = nipyapi.canvas.create_controller(pg, cs_type, "My Reader")
```

**Note:** `parent_pg` accepts `"root"`, a UUID string, or a `ProcessGroupEntity` object.

**Naming:** The process group name becomes the permanent flow identifier in version control. Confirm with the user: "Is `{name}` the final name for this flow?"

**Positioning:** Use `layout.below()`, `layout.fork()`, etc. - see `ops-layout.md`

---

## Inspect

**Prefer CLI for inspection** - simpler and avoids object model errors:

```bash
nipyapi canvas list_all_processors --pg_id <pg_id>
nipyapi canvas list_all_connections --pg_id <pg_id>
nipyapi canvas list_all_controllers --pg_id <pg_id>
nipyapi canvas get_processor --identifier <name_or_id>
nipyapi canvas get_controller --identifier <name_or_id>
```

Python API (when CLI output insufficient):

```python
# Get processor by name or ID
proc = nipyapi.canvas.get_processor("UpdateRecord")
proc = nipyapi.canvas.get_processor("<uuid>", identifier_type="id")

# Read current configuration
print(proc.component.config.properties)
print(f"State: {proc.component.state}")

# Get controller service
cs = nipyapi.canvas.get_controller("JsonTreeReader", identifier_type="name")
print(cs.component.properties)

# List all in a process group
processors = nipyapi.canvas.list_all_processors(pg.id)
controllers = nipyapi.canvas.list_all_controllers(pg.id)
connections = nipyapi.canvas.list_all_connections(pg.id)
```

For inspecting FlowFile content and attributes, see `ops-connection-inspection.md`.

---

## Update

See `ops-component-config.md` for property configuration with validation.

```python
config = nipyapi.canvas.prepare_processor_config(proc, {'Record Reader': cs.id})
nipyapi.canvas.update_processor(proc, update=config, auto_stop=True)

# Rename
nipyapi.canvas.update_processor(proc, name="New Name", auto_stop=True)
```

---

## Delete

```python
# Delete processor (must be stopped, no active connections)
nipyapi.canvas.delete_processor(proc)

# Delete connection (must be empty - purge first if needed)
nipyapi.canvas.purge_connection(conn.id)
nipyapi.canvas.delete_connection(conn)

# Delete controller service (must be disabled, no references)
nipyapi.canvas.delete_controller(cs)

# Delete process group (must be stopped, controllers disabled)
nipyapi.canvas.delete_process_group(pg)
```

**Deletion order:** Connections first, then processors, then controllers, then process groups.

---

## Validate

Before starting, verify configuration is correct:

```python
# Verify a single processor
results = nipyapi.canvas.verify_processor(proc)
for r in results:
    print(f"{r.verification_step_name}: {r.outcome}")

# Verify a single controller
results = nipyapi.canvas.verify_controller(cs)

# Batch verify entire process group
result = nipyapi.ci.verify_config(process_group_id=pg.id)
print(result['summary'])
```

See `ops-config-verification.md` for detailed verification workflows.

---

## Testing Your Flow

### Run Once

Process a single FlowFile to verify behavior:

```python
# Generate one FlowFile
nipyapi.canvas.schedule_processor(source_proc, 'RUN_ONCE')

# Get outgoing connection for this processor
conns = nipyapi.canvas.get_component_connections(source_proc)
out_conn = next(c for c in conns if c.source_id == source_proc.id)
flowfiles = nipyapi.canvas.peek_flowfiles(out_conn, limit=1)

if flowfiles:
    print(f"Attributes: {flowfiles[0].attributes}")
    content = nipyapi.canvas.get_flowfile_content(out_conn, flowfiles[0].uuid)
    print(f"Content: {content[:500]}")
```

### Check for Errors

```python
# After running, check for bulletins
bulletins = nipyapi.bulletins.get_bulletin_board(pg_id=pg.id)
for b in bulletins:
    print(f"[{b.level}] {b.source_name}: {b.message}")
```

**Bulletin hygiene:** Clear bulletins between test iterations to avoid mixing old and new errors:

```python
nipyapi.bulletins.clear_bulletin_board()
```

### Funnels as Inspection Points

During development, use Funnels as temporary destinations for connections when you're unsure what to do with an output. **Do not auto-terminate relationships** during authoring - this prevents inspection.

```python
# Create a funnel to hold output for inspection (note: pg.id, not pg object)
funnel = nipyapi.canvas.create_funnel(pg.id, position=layout.below(proc))

# Connect processor output to funnel instead of terminating
nipyapi.canvas.create_connection(proc, funnel, ['success'])
```

**Why Funnels over auto-terminate:**
- Auto-terminated FlowFiles are immediately discarded with no way to inspect them
- Funnels queue FlowFiles so you can peek at attributes and content
- Helps verify transformations are working before wiring to the next processor

**Canonical example:** Testing GenerateFlowFile content:

```python
# Create generator with custom content
gen = nipyapi.canvas.create_processor(pg, gen_type, layout.new_flow(), "Test Generator")
config = nipyapi.canvas.prepare_processor_config(gen, {'Custom Text': '{"id": 1, "name": "test"}'})
nipyapi.canvas.update_processor(gen, update=config, auto_stop=True)

# Connect to funnel for inspection (not auto-terminate)
funnel = nipyapi.canvas.create_funnel(pg.id, position=layout.below(gen))
nipyapi.canvas.create_connection(gen, funnel, ['success'])

# Generate one FlowFile and inspect
nipyapi.canvas.schedule_processor(gen, 'RUN_ONCE')

# Get connections for this specific processor (returns both incoming and outgoing)
conns = nipyapi.canvas.get_component_connections(gen)
out_conn = next(c for c in conns if c.source_id == gen.id)  # Filter to outgoing

flowfiles = nipyapi.canvas.peek_flowfiles(out_conn, limit=1)
content = nipyapi.canvas.get_flowfile_content(out_conn, flowfiles[0].uuid)
print(content)  # Verify the JSON is correct before proceeding
```

**When to replace Funnels:** Once you've verified the output and know the next step, delete the funnel and connect to the actual destination processor.

### Auto-Terminating Relationships

When a relationship has no downstream destination and you want to discard its FlowFiles, auto-terminate it via `ProcessorConfigDTO.auto_terminated_relationships`. This field takes a **list of plain strings** (relationship names), not `RelationshipDTO` objects.

```python
# Correct: list of strings
config = nipyapi.nifi.ProcessorConfigDTO(
    auto_terminated_relationships=['success', 'failure']
)
nipyapi.canvas.update_processor(proc, update=config, auto_stop=True)

# Also correct: set during processor creation
proc = nipyapi.canvas.create_processor(
    pg, proc_type, layout.new_flow(), "My Processor",
    config=nipyapi.nifi.ProcessorConfigDTO(
        scheduling_period='10s',
        auto_terminated_relationships=['success']
    )
)
```

**Common mistake:** Do not use `RelationshipDTO` objects here. `RelationshipDTO` is a read-only representation returned when you GET a processor (via `proc.component.relationships`). The `auto_terminated_relationships` field on `ProcessorConfigDTO` is a separate, writable `list[str]` used when updating a processor.

---

## Common Patterns

| Pattern | Key Processors |
|---------|---------------|
| **Read → Transform → Write** | GetFile/GenerateFlowFile → UpdateRecord → PutFile/PutS3 |
| **API Ingestion** | InvokeHTTP → SplitJson → UpdateRecord |
| **JMS Messaging** | ConsumeJMS → ConvertRecord → PutSnowpipeStreaming |
| **File Processing** | ListS3 → FetchS3Object → ConvertRecord → PutSnowpipeStreaming |

**Loop-back connections:** For retry or pagination loops, route connections left around the spine with bend points. See `ops-layout.md` → "Loop-Back Connections".

For detailed patterns, see:
- `author-pattern-rest-api.md` - REST API ingestion
- `author-pattern-files.md` - Cloud file processing
- `author-pattern-activemq.md` - ActiveMQ/JMS messaging

---

## Modular Flow Design

For flows with more than a few processors, consider organizing into child process groups.

**When to modularize:** Ask the user: "This sounds like a multi-step process. Would breaking it into child process groups help organize and maintain it?"

### Sequential Pattern (Ingress → Transform → Egress)

Use for linear data pipelines where data flows through stages:

```
Main Flow (container)
├── Ingress (fetches data)
│   └── Output Port: "raw data"
├── Transform (processes data)
│   ├── Input Port: "raw data"
│   └── Output Port: "processed data"
└── Egress (writes data)
    └── Input Port: "processed data"
```

**Ports as contracts:** Input/output ports define the interface between child PGs. The main flow connects ports together.

```python
# Create child PGs
ingress_pg = nipyapi.canvas.create_process_group(main_pg, "Ingress", layout.new_flow())
transform_pg = nipyapi.canvas.create_process_group(main_pg, "Transform", layout.below(ingress_pg))
egress_pg = nipyapi.canvas.create_process_group(main_pg, "Egress", layout.below(transform_pg))

# Create ports (inside each child PG) - note: requires pg_id, port_type, name, state
ingress_out = nipyapi.canvas.create_port(ingress_pg.id, 'OUTPUT_PORT', 'raw data', 'STOPPED')
transform_in = nipyapi.canvas.create_port(transform_pg.id, 'INPUT_PORT', 'raw data', 'STOPPED')
transform_out = nipyapi.canvas.create_port(transform_pg.id, 'OUTPUT_PORT', 'processed data', 'STOPPED')
egress_in = nipyapi.canvas.create_port(egress_pg.id, 'INPUT_PORT', 'processed data', 'STOPPED')

# Connect ports in main PG
nipyapi.canvas.create_connection(ingress_out, transform_in, [''])
nipyapi.canvas.create_connection(transform_out, egress_in, [''])
```

**User-owned transform layer:** Keep ingress/egress stable; users customize the transform PG.

### Parallel Pattern (Independent Workflows)

Use when multiple workflows run independently but may coordinate:

```
Main Flow (container)
├── Workflow A (e.g., initial load)
├── Workflow B (e.g., incremental updates)
└── Workflow C (e.g., maintenance tasks)
```

Coordination via processors like wait/notify or state checks between workflows.

### Shared Processing

Route multiple flows to a common processor (logging, error handling):

```python
# Create shared logging PG with input port
logging_pg = nipyapi.canvas.create_process_group(main_pg, "Logging")
log_input = nipyapi.canvas.create_port(logging_pg.id, 'INPUT_PORT', 'log events', 'STOPPED')

# In the source PG, create an output port
source_out = nipyapi.canvas.create_port(source_pg.id, 'OUTPUT_PORT', 'to logging', 'STOPPED')

# Connect processor to output port (within source PG)
nipyapi.canvas.create_connection(some_processor, source_out, ['failure'])

# Connect output port to input port (in parent PG)
nipyapi.canvas.create_connection(source_out, log_input, [''])
```

**Note:** You cannot connect a processor directly to a port in another PG. You must use an output port in the source PG that connects to an input port in the destination PG.

Avoids duplicating logging processors in every child PG.

---

## After Building

- **Start the flow** - See `ops-flow-lifecycle.md`
- **Save to version control** - See `ops-version-control.md`
- **Monitor and troubleshoot** - See `ops-flow-investigation.md`

---

## Related References

- `author-main.md` - Design principles and routing
- `author-component-selection.md` - Find the right processor
- `ops-layout.md` - Canvas positioning
- `ops-connection-inspection.md` - Inspect FlowFile content
- `ops-config-verification.md` - Validate configuration
