---
name: openflow-author-main
description: Flow authoring router. Load when building custom flows, creating processors, or making structural changes to flows.
---

# Flow Authoring

Build custom NiFi flows for data integration needs not met by pre-built connectors.

**When to use:** Creating new flows, adding/modifying processors, building custom integrations.

**When NOT to use:** Deploying existing connectors (see `ops-flow-deploy.md`), starting/stopping flows (see `ops-flow-lifecycle.md`).

**Connectors vs Custom:** Connectors are supported by Snowflake; custom flows put maintenance burden on the customer. Prefer connectors when available.

---

## Strategy-First Workflow

Before building, formulate a strategy. This prevents wasted cycles from trial-and-error.

### Step 1: Understand the Goal

Clarify with the user:
- What data is being moved/transformed?
- What is the source? What is the destination?
- Are there any ordering, batching, or timing requirements?

### Step 2: Design the Flow

Sketch the data flow before touching any tools:
- What processors are needed? (Check `author-component-selection.md`)
- What is the logical sequence?
- What controller services are required?
- Load any relevant pattern reference (e.g., `author-pattern-activemq.md`)

### Step 3: Start an Investigation Diary

For flows with more than 2-3 components, start a diary immediately (see `core-investigation-diary.md`). As context grows with tool outputs, the diary provides breadcrumbs to get back on track.

```markdown
# Building: [Flow Name]

## Goal
[What we're building and why]

## Design
[Components identified, sequence planned]

## Progress
- [ ] Process group created
- [ ] Controller service configured
- [ ] Processor 1: [name] - [status] - [purpose]
- [ ] Processor 2: [name] - [status] - [purpose]

## Current State
[Last validated working point]

## Next Step
[What to do next]
```

### Step 4: Discover the Tooling

For each function you'll use, check its signature BEFORE writing code:

```bash
nipyapi canvas create_processor --help
nipyapi canvas get_processor_docs --processor ConsumeJMS
nipyapi canvas get_controller_docs --controller JMSConnectionFactoryProvider
```

```python
help(nipyapi.canvas.create_processor)
help(nipyapi.layout.suggest_pg_position)
```

### Step 5: Build Incrementally

Execute one step at a time with validation between each:

1. Create process group → verify it exists
2. Create controller service → set configuration, validate configuration
3. Create first processor → set configuration, validate configuration
4. Update diary with progress
5. Continue...

See `author-building-flows.md` for the inspect-modify-test cycle.

---

## Routing

| If you need to... | Load |
|-------------------|------|
| **Build a flow (CRUD operations)** | `author-building-flows.md` |
| **Find the right processor** | `author-component-selection.md` |
| **Blueprints (patterns):** | |
| Ingest from REST API | `author-pattern-rest-api.md` |
| Process files from S3/GCS | `author-pattern-files.md` |
| Publish/consume ActiveMQ/JMS | `author-pattern-activemq.md` |
| Generate synthetic test data | `author-pattern-data-generation.md` |
| Write to Snowflake | `author-snowflake-destination.md` |
| **NiFi tool knowledge:** | |
| Manipulate FlowFile attributes | `nifi-expression-language.md` |
| Transform record content | `nifi-recordpath.md` |
| Work with dates/timestamps | `nifi-date-formatting.md` |
| Understand NiFi architecture | `nifi-concepts.md` |
| **Operations:** | |
| Set component properties | `ops-component-config.md` |
| Position components on canvas | `ops-layout.md` |
| Configure parameters | `ops-parameters-main.md` |
| Save to version control | `ops-version-control.md` |
| Inspect connections/FlowFiles | `ops-connection-inspection.md` |

---

## Tool Hierarchy

1. **nipyapi.ci** - High-level commands (import/export flow)
2. **nipyapi.canvas** - Component CRUD (create, get, update, delete, list)
3. **nipyapi.layout** - Positioning (`below()`, `fork()`, `right_of()`)
4. **nipyapi.parameters** - Parameter contexts and values

**CLI vs Python:** CLI for quick single commands; Python for multi-step operations.

---

## Flow Design Principles

### 1. Always Use a Process Group

**Never** build flows directly on the root canvas. Always encapsulate in a process group:

```python
# Correct: Create a process group first
my_pg = nipyapi.canvas.create_process_group(
    parent_pg="root",
    new_pg_name="My Custom Flow",
    location=layout.suggest_pg_position("root")
)

# Then add processors inside it
proc = nipyapi.canvas.create_processor(parent_pg=my_pg, ...)
```

**Why:**
- Enables version control (only PGs can be versioned)
- Clean organization and navigation
- Easier to move, copy, or delete
- Required for parameter context binding

### 2. Controller Services in Same Process Group

Place controller services in the **same process group** as the processors that use them:

```python
# Create controller in the flow's PG, not root
reader = nipyapi.canvas.create_controller(
    parent_pg=my_pg,  # Same PG as processors
    controller=nipyapi.canvas.get_controller_type('JsonTreeReader'),
    name="My Reader"
)
```

**Why:**
- Travels with the flow during export/import
- Avoids cross-PG dependencies
- Cleaner version control
- Easier to understand flow dependencies

A parent Process Group may hold Controllers shared by child Process Groups, but they should not be in the root as it cannot be versioned.

Management Controllers like Registry Clients are a special group and may not be created within a Process Group anyway.

### 3. Use Parameter Contexts for Configuration

Externalize connection strings, credentials, and environment-specific values:

```python
ctx = nipyapi.parameters.create_parameter_context(
    name="My Flow Parameters",
    parameters=[
        {"name": "api.url", "value": "https://api.example.com"},
        {"name": "api.key", "sensitive": True, "value": "secret"}
    ]
)
nipyapi.parameters.assign_context_to_process_group(my_pg, ctx.id)

# Reference in processor properties
config = nipyapi.canvas.prepare_processor_config(proc, {'URL': '#{api.url}'})
nipyapi.canvas.update_processor(proc, update=config, auto_stop=True)
```

**Why:**
- Environment promotion (dev → prod)
- Secrets management
- Change values without editing flow triggering version control notifications

### 4. Version Control Before Changes

Before making structural changes:

> "You're about to make structural changes. Would you like to set up version control first? This provides undo capability and change tracking. (Skip if experimenting.)"

See `ops-version-control.md` for Git registry setup.

**Note:** The Snowflake connector registry is read-only. Custom work requires your own Git repository.

---

## Related References

### Building (how-to)
- `author-building-flows.md` - Component operations, inspect-modify-test cycle

### Tools (the workbench)
- `author-component-selection.md` - What each component does
- `nifi-main.md` - NiFi tool reference router

### Blueprints (project patterns)
- `author-pattern-rest-api.md` - REST API ingestion
- `author-pattern-files.md` - Cloud file processing
- `author-pattern-activemq.md` - ActiveMQ/JMS messaging
- `author-pattern-data-generation.md` - Synthetic test data with GenerateJSON
- `author-snowflake-destination.md` - Snowflake destination

### Operations
- `ops-layout.md` - Canvas positioning
- `ops-version-control.md` - Version control setup
- `ops-connection-inspection.md` - Inspect FlowFiles
