---
name: openflow-ops-parameters-main
description: Parameter context management for Openflow. Router for parameter inspection, configuration, export/import, and assets.
---

# Parameter Context Operations

Router for all parameter operations. Read the concepts below, then route to the appropriate sub-reference.

**Scope:** This is the main entry point for parameter operations. Covers concepts and routing only. For specific operations, see the sub-references below.

**Note:** Parameter updates modify service state. Apply the Check-Act-Check pattern (see `references/core-guidelines.md`).

## Parameter Context Concepts

### What Are Parameter Contexts?

Parameter contexts store configuration values (connection strings, credentials, settings, files) that processors and controller services reference using `#{parameter_name}` syntax. This externalizes configuration from flow definitions.

### Inheritance Pattern

Snowflake Connectors use a two-level inheritance hierarchy:

```
Ingestion Parameters (bound to Process Group)
├── Flow-specific settings (table names, schedule, etc.)
│
├── Inherits: Destination Parameters
│   └── Snowflake settings (role, warehouse, database, auth)
│
└── Inherits: Source Parameters
    └── Source connection settings (URL, credentials)
```

Other Process Groups may use a single directly bound parameter context, or no parameters, so always investigate first.

When a processor references `#{Some Parameter}`:
1. NiFi checks the bound context (Ingestion Parameters)
2. If not found, checks inherited contexts in listed order
3. First Key match wins, even if empty

**Key insight:** Parameters are defined in specific contexts. To update a parameter, you must update its owning context, not a parent context.

### Shared Parameter Contexts

Connectors of the same type share parameter contexts via Name matching. This is critical behavior:

1. **Deploying a connector** - If parameter contexts for that connector type already exist, the new deployment adopts the existing contexts rather than creating new ones.

2. **Parameter changes affect all instances** - Changing a parameter affects every connector sharing that context.

3. **Duplicate deployments** - May create contexts with numeric suffixes (e.g., `PostgreSQL Ingestion Parameters (1)`) if original contexts are bound elsewhere.

### Parameter Context Handling Strategy (Git Registries Only)

When deploying from Git-based registries (GitHub, GitLab), you can control how parameter contexts are handled using the `parameter_context_handling` option:

| Strategy | Behavior |
|----------|----------|
| `KEEP_EXISTING` (default) | If a context with the same name exists, reuse it. Parameter values from the existing context are preserved. |
| `REPLACE` | Create a new context with a numbered suffix (e.g., `My Context (1)`). The new context gets values from the flow definition. |

**When to use REPLACE:**
- Deploying a second instance that needs independent parameter values
- Testing flow changes without affecting production contexts
- Creating isolated environments

**Example:**

```bash
# Default: reuse existing contexts
nipyapi ci deploy_flow --registry_client "MyGithubRegistry" --bucket flows --flow my-connector

# Create fresh contexts with numbered suffix
nipyapi ci deploy_flow --registry_client "MyGithubRegistry" --bucket flows --flow my-connector \
    --parameter_context_handling REPLACE
```

**Note:** This option is only available for Git-based Flow Registry Clients. Traditional NiFi Registry and direct JSON file imports always use name-based matching (equivalent to `KEEP_EXISTING`).

### Implications for Operations

| Operation | Consideration |
|-----------|---------------|
| Configure parameters | Changes affect all connectors sharing the context |
| Delete parameter context | Breaks all connectors using it |
| Deploy same connector twice | May share contexts or create duplicates (use `REPLACE` for isolation) |
| Export parameters | Exports from one context hierarchy |
| Migrate parameters | Must handle sensitive values separately |
| Deploy with `REPLACE` | Creates independent contexts but may diverge from shared config |

### Before Modifying Parameters

Always inspect first:
1. Which contexts exist and their relationships
2. Which process groups are bound to each context
3. Which context owns the parameter you want to change

## Routing Table

Route based on user intent:

| Intent | Reference |
|--------|-----------|
| Create, bind, unbind, delete parameter contexts | `references/ops-parameters-contexts.md` |
| Inspect hierarchy, find which context owns a parameter, check bindings | `references/ops-parameters-inspect.md` |
| Set parameter values, export parameters, import from file, migrate | `references/ops-parameters-configure.md` |
| Upload JARs, certificates, drivers (binary assets) | `references/ops-parameters-assets.md` |
| Curl-only environment (no nipyapi available) | `references/ops-parameters-curl.md` |

### Quick Reference: Common Commands

| Task | Command |
|------|---------|
| Create context | `nipyapi.parameters.create_parameter_context(name="...", parameters=[...])` (Python) |
| Bind to process group | `nipyapi.parameters.assign_context_to_process_group(pg, ctx.id)` (Python) |
| Get hierarchy | `nipyapi parameters get_parameter_context_hierarchy "<ctx-id>"` |
| Get ownership map | `nipyapi.parameters.get_parameter_ownership_map("<ctx-id>")` (Python) |
| Get inheritance map | `nipyapi parameters list_all_parameter_contexts \| jq '.[] \| {name: .component.name, inherits_from: [.component.inherited_parameter_contexts[]?.component.name]}'` |
| List orphaned contexts | `nipyapi parameters list_orphaned_contexts` |
| Configure parameters | `nipyapi ci configure_inherited_params --process_group_id "<pg-id>" --parameters '{...}'` |
| Export parameters | `nipyapi ci export_parameters --context_id "<ctx-id>" --file_path params.json` |
| Import from file | `nipyapi ci configure_inherited_params --process_group_id "<pg-id>" --parameters_file params.json` |
| Upload asset | `nipyapi ci upload_asset --context_id "<ctx-id>" --param_name "..." --url "..."` |

## Workflow: Parameter Configuration

For connector deployment, follow this sequence:

1. **Inspect** - Load `ops-parameters-inspect.md` to understand the hierarchy
2. **Configure** - Load `ops-parameters-configure.md` to set values
3. **Verify** - Check that controllers can enable and processors validate

## Sensitive Parameters

Sensitive parameter values (passwords, keys, tokens) are:
- **Never exported** - NiFi returns null for sensitive values
- **Must be set separately** - After import or migration
- **Masked in output** - Shown as `********` in dry runs

When migrating, export captures parameter keys but not sensitive values. You must separately configure sensitive parameters on the target.

## See Also

- `references/ops-parameters-contexts.md` - Create, bind, delete contexts
- `references/ops-parameters-inspect.md` - Inspection and discovery
- `references/ops-parameters-configure.md` - Configuration and migration
- `references/ops-parameters-assets.md` - Binary asset management
- `references/ops-parameters-curl.md` - Curl alternatives
- `references/ops-snowflake-auth.md` - Snowflake destination authentication
