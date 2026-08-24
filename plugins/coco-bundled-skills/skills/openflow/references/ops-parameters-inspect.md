---
name: openflow-ops-parameters-inspect
description: Inspect parameter context hierarchy, ownership, and bindings. Use before configuring parameters to understand the structure.
---

# Parameter Inspection

Inspect parameter context hierarchy, ownership, and bindings.

**Scope:** Use this reference to discover and understand parameter structure before making changes. For setting parameter values, see `references/ops-parameters-configure.md`.

**Prerequisite:** Understand parameter context concepts in `references/ops-parameters-main.md`.

## Get Parameter Context from Process Group

Find which parameter context is bound to a process group:

```bash
nipyapi canvas get_process_group "ConnectorName" | jq '{
  id: .id,
  name: .component.name,
  parameter_context: .component.parameter_context
}'
```

Output:

```json
{
  "id": "4d2fefef-...",
  "name": "PostgreSQL",
  "parameter_context": {
    "id": "6832efd7-...",
    "name": "PostgreSQL Ingestion Parameters"
  }
}
```

## Extract Full Parameter Hierarchy

The `get_parameter_context_hierarchy` function traverses the complete inheritance chain:

```bash
nipyapi parameters get_parameter_context_hierarchy "<context-id>"
```

Or with options:

```bash
# Include bindings (which PGs use each context)
nipyapi parameters get_parameter_context_hierarchy "<context-id>" True False

# Include parameters and bindings
nipyapi parameters get_parameter_context_hierarchy "<context-id>" True True
```

Arguments: `context_id`, `include_bindings`, `include_parameters`

Output:

```json
{
  "id": "6832efd7-...",
  "name": "PostgreSQL Ingestion Parameters",
  "bound_process_groups": [{"id": "4d2fefef-...", "name": "PostgreSQL"}],
  "parameters": [
    {
      "name": "Ingestion Type",
      "description": "Type of data ingestion: cdc or snapshot",
      "value": "cdc",
      "sensitive": false,
      "has_asset": false
    }
  ],
  "inherited": [
    {
      "id": "950d10d3-...",
      "name": "PostgreSQL Destination Parameters",
      "bound_process_groups": [],
      "parameters": [...]
    },
    {
      "id": "52e487ce-...",
      "name": "PostgreSQL Source Parameters",
      "bound_process_groups": [],
      "parameters": [...]
    }
  ]
}
```

### Use Cases

| Use Case | CLI | What You Get |
|----------|-----|--------------|
| Extract all parameter values | `... "<ctx-id>"` | Full hierarchy with parameters |
| Cleanup safety check | `... "<ctx-id>" True False` | Structure + bindings, no parameters |
| Complete inspection | `... "<ctx-id>" True True` | Parameters + bindings |

**Note:** Sensitive parameter values are returned as `null` with `"sensitive": true`.

## Get Parameter Descriptions

The `description` field contains help text explaining what each parameter does and what values are expected. **Always read descriptions before configuring parameters** to take informed action.

```bash
nipyapi parameters get_parameter_context_hierarchy "<context-id>"
```

The output includes full descriptions for each parameter. Read them to understand expected values, defaults, and SPCS vs BYOC differences.

**Why this matters:** Parameter descriptions often contain:
- Valid values and formats
- Default behavior when empty
- SPCS vs BYOC differences
- Links to external documentation

## Get Parameter Ownership Map

See which context owns each parameter (essential before making changes):

```bash
nipyapi ci get_parameter_context_hierarchy "<ctx-id>" True True
```

The output JSON includes each context's parameters with `sensitive` and `referenced_assets` fields. Parse the hierarchy to determine which context owns each parameter before making changes.

Example ownership from hierarchy output:

```
Database Host: PostgreSQL Source Parameters
Database Port: PostgreSQL Source Parameters
Password: PostgreSQL Source Parameters [SENSITIVE]
Snowflake Database: PostgreSQL Destination Parameters
Snowflake Role: PostgreSQL Destination Parameters
Ingestion Type: PostgreSQL Ingestion Parameters
```

This shows:
- Which context each parameter is defined in
- Whether it's sensitive
- Whether it references an asset

## Inspect a Single Context

Get details about a specific parameter context:

```bash
CONTEXT_ID="<parameter-context-id>"
nipyapi parameters get_parameter_context "$CONTEXT_ID" "id" | jq '{
  name: .component.name,
  inherited_parameter_contexts: .component.inherited_parameter_contexts,
  parameters: [.component.parameters[].parameter | {name: .name, value: .value, sensitive: .sensitive}]
}'
```

## Check Which Process Groups Use a Context

Important for understanding the impact of changes:

```bash
nipyapi parameters get_parameter_context "<context-id>" "id" | jq '{
  name: .component.name,
  bound_process_groups: [.component.bound_process_groups[]? | {name: .component.name, id: .id}]
}'
```

If `bound_process_groups` is empty, the context is not directly bound to any process group (but may still be inherited by another context that is bound).

## List All Parameter Contexts

```bash
nipyapi parameters list_all_parameter_contexts | jq -r '.[].component.name' | sort
```

## Get Inheritance Map for All Contexts

View all parameter contexts with their inheritance relationships. Useful for cleanup operations or understanding the full dependency structure:

```bash
nipyapi parameters list_all_parameter_contexts | jq '.[] | {
  name: .component.name,
  id: .component.id,
  inherits_from: [.component.inherited_parameter_contexts[]?.component.name]
}'
```

Output shows which contexts inherit from which:

```json
{"name": "PostgreSQL Ingestion Parameters", "id": "6832efd7-...", "inherits_from": ["PostgreSQL Destination Parameters", "PostgreSQL Source Parameters"]}
{"name": "PostgreSQL Destination Parameters", "id": "950d10d3-...", "inherits_from": []}
{"name": "PostgreSQL Source Parameters", "id": "52e487ce-...", "inherits_from": []}
```

**Deletion order:** When deleting parameter contexts, delete children first (those that inherit from others), then parents. Contexts with empty `inherits_from` arrays are roots and should be deleted last.

## List Orphaned Contexts

Find parameter contexts that are not bound to any process groups (may be safe to delete):

```bash
nipyapi parameters list_orphaned_contexts | jq '.[].component.name'
```

**Note:** An orphaned context may still be inherited by another context. Check the inheritance map before deleting.

## Delete Orphaned Contexts

To clean up orphaned contexts, first list them to review, then delete:

```python
import nipyapi

# List orphaned contexts
orphans = nipyapi.parameters.list_orphaned_contexts()
for ctx in orphans:
    print(f"Orphaned: {ctx.component.name}")

# Delete after review
for ctx in orphans:
    nipyapi.parameters.delete_parameter_context(ctx)
    print(f"Deleted: {ctx.component.name}")
```

**Warning:** Always review the list before deleting, and get user confirmation. Contexts may be orphaned intentionally (e.g., templates awaiting deployment).

## Before/After Deployment Comparison

**Before deploying**, capture the current state:

```bash
# List all parameter contexts
nipyapi parameters list_all_parameter_contexts | jq -r '.[].component.name' | sort > before.txt

# Check for existing connectors of the same type
nipyapi ci list_flows | jq -r '.process_groups[].name' | grep -i "<connector-type>"
```

**After deploying**, check what changed:

```bash
# List parameter contexts again
nipyapi parameters list_all_parameter_contexts | jq -r '.[].component.name' | sort > after.txt

# Compare
diff before.txt after.txt

# Inspect the deployed connector's bound context
nipyapi canvas get_process_group "<new-pg-name>" | jq '.component.parameter_context'
```

This pattern identifies whether the connector adopted existing contexts or created new ones.

---

## Next Step

After inspection:
- To configure parameters, load `references/ops-parameters-configure.md`
- To manage assets, load `references/ops-parameters-assets.md`
- Return to `references/ops-parameters-main.md` for routing
