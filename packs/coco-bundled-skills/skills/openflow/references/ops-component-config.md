---
name: openflow-ops-component-config
description: Set properties on processors and controller services. Load when configuring component properties.
---

# Component Configuration

Set properties on processors and controller services.

## Scope

This reference covers:
- Setting static and dynamic properties on processors
- Setting properties on controller services
- Property value semantics (set, clear, delete)
- Discovery of valid property keys

For parameter context configuration, see `ops-parameters-main.md`.
For scheduling and run state, see `ops-flow-lifecycle.md`.

---

## Prerequisite: Verify Before Configuring

If you encounter unexpected failures when setting properties, run verification first:

```bash
nipyapi --profile <profile> ci verify_config --process_group_id "<pg-id>" --only_failures
```

If verification reports failures, load `ops-config-verification.md` for failure pattern interpretation before continuing.

---

## Decision: Static vs Dynamic Properties

**Before setting any property, determine the property type:**

| Property Type | How to Recognize | Parameter |
|---------------|------------------|-----------|
| **Static** | Property appears in processor's `descriptors` | (default) |
| **Dynamic** | Property does NOT appear in `descriptors` - you're creating it | `allow_dynamic=True` |

**Common dynamic property processors:**
- `UpdateAttribute` - attribute names are dynamic
- `ExtractText` - regex capture group names are dynamic
- `RouteOnAttribute` - route names are dynamic

**If you omit `allow_dynamic=True` for a dynamic property:**
```
ValueError: Property keys not in static descriptors: ['url']
Valid static keys for org.apache.nifi.processors.standard.ExtractText: [...]
Use allow_dynamic=True to create dynamic properties intentionally.
```

## Setting Properties

```python
proc = nipyapi.canvas.get_processor('<name-or-id>')

# Static property (exists in processor's descriptors)
config = nipyapi.canvas.prepare_processor_config(proc, {'SQL Query': 'SELECT 1'})

# Dynamic property (you're creating a new property name)
config = nipyapi.canvas.prepare_processor_config(proc, {'url': '(.+)'}, allow_dynamic=True)

nipyapi.canvas.update_processor(proc, update=config, auto_stop=True)
```

**Discovery:** To list valid static property keys:
```python
valid_keys = nipyapi.canvas.prepare_processor_config(proc)
```

## Property Value Semantics

| Value | Static Property | Dynamic Property |
|-------|-----------------|------------------|
| `'text'` | Set to "text" | Set to "text" |
| `''` (empty) | Set to empty string | Set to empty string |
| `None` | Clear/unset value | **Delete property entirely** |

### Clear a Static Property

```python
config = nipyapi.canvas.prepare_processor_config(proc, {'Custom Text': None})
nipyapi.canvas.update_processor(proc, update=config, auto_stop=True)
```

### Delete a Dynamic Property

```python
config = nipyapi.canvas.prepare_processor_config(proc, {'my.attr': None}, allow_dynamic=True)
nipyapi.canvas.update_processor(proc, update=config, auto_stop=True)
```

After this, `my.attr` no longer exists in the processor's properties or descriptors.

## Controller Services

```python
cs = nipyapi.canvas.get_controller('<name-or-id>')
config = nipyapi.canvas.prepare_controller_config(cs, {'Schema Access Strategy': 'infer-schema'})
nipyapi.canvas.update_controller(cs, update=config, auto_disable=True)
```

## Scheduling Configuration

Scheduling and concurrency use `ProcessorConfigDTO` directly:

```python
config = nipyapi.nifi.ProcessorConfigDTO(
    scheduling_period='5 sec',
    concurrently_schedulable_task_count=2
)
nipyapi.canvas.update_processor(proc, update=config, auto_stop=True)
```

## auto_stop / auto_disable

- `update_processor(..., auto_stop=True)` - stops processor before update, restarts after
- `update_controller(..., auto_disable=True)` - disables controller before update, re-enables after

`auto_disable` does not handle referencing components - stop dependent processors separately.

## Related References

- `ops-flow-lifecycle.md` - Start/stop flows and components
- `ops-config-verification.md` - Validate configuration
- `ops-component-state.md` - Internal state (CDC positions, etc.)
