---
name: openflow-ops-parameters-contexts
description: Create, bind, and delete parameter contexts. Use for context lifecycle operations.
---

# Parameter Context Lifecycle

Create, bind, unbind, and delete parameter contexts.

## Scope

This reference covers:
- Creating parameter contexts (empty or with initial parameters)
- Creating contexts with inheritance
- Binding and unbinding contexts to process groups
- Deleting contexts

For setting parameter values, see `ops-parameters-configure.md`.
For inspecting context hierarchy, see `ops-parameters-inspect.md`.

---

**Prerequisite:** Understand parameter context concepts in `ops-parameters-main.md`.

## Create Context

Create empty context, then add parameters:

```python
ctx = nipyapi.parameters.create_parameter_context(name="My Flow Parameters")

param = nipyapi.parameters.prepare_parameter("api.url", value="https://api.example.com")
nipyapi.parameters.upsert_parameter_to_context(ctx, param)

sensitive_param = nipyapi.parameters.prepare_parameter("api.key", value="secret", sensitive=True)
nipyapi.parameters.upsert_parameter_to_context(ctx, sensitive_param)
```

Or create with initial parameters (list of ParameterEntity):

```python
params = [
    nipyapi.parameters.prepare_parameter("api.url", value="https://api.example.com"),
    nipyapi.parameters.prepare_parameter("api.key", value="secret", sensitive=True)
]
ctx = nipyapi.parameters.create_parameter_context(name="My Flow Parameters", parameters=params)
```

## Create with Inheritance

`inherited_contexts` takes a list of ParameterContextEntity objects:

```python
parent_ctx = nipyapi.parameters.create_parameter_context(name="Shared Settings")
nipyapi.parameters.upsert_parameter_to_context(
    parent_ctx,
    nipyapi.parameters.prepare_parameter("environment", value="dev")
)

child_ctx = nipyapi.parameters.create_parameter_context(
    name="Flow Specific",
    inherited_contexts=[parent_ctx]
)
```

## Bind Context to Process Group

```python
nipyapi.parameters.assign_context_to_process_group(pg, ctx.id)
```

A process group can only have one directly bound context. Binding a new context replaces the existing binding.

## Unbind Context

```python
nipyapi.parameters.remove_context_from_process_group(pg)
```

## Update Context

Add or update parameters:

```python
nipyapi.parameters.upsert_parameter_to_context(
    ctx,
    nipyapi.parameters.prepare_parameter("new_param", value="new_value")
)
```

Rename context:

```python
nipyapi.parameters.rename_parameter_context(ctx, "New Name")
```

## Delete Context

Context must not be bound to any process groups:

```python
ctx = nipyapi.parameters.get_parameter_context('<name-or-id>')

if ctx.component.bound_process_groups:
    print(f"Cannot delete - bound to: {[pg.name for pg in ctx.component.bound_process_groups]}")
else:
    nipyapi.parameters.delete_parameter_context(ctx)
```

## Find Orphaned Contexts

Contexts not bound to any process group:

```bash
nipyapi parameters list_orphaned_contexts
```

## Related References

- `ops-parameters-main.md` - Concepts and routing
- `ops-parameters-configure.md` - Set parameter values
- `ops-parameters-inspect.md` - Inspect context hierarchy
