---
name: openflow-ops-parameters-configure
description: Configure parameter values, export and import parameters. Use for setting values, migration, and backup.
---

# Parameter Configuration

Configure parameter values, export for backup, and import from files.

**Scope:** Use this reference to set, export, or import parameter values. For discovering parameter structure first, see `references/ops-parameters-inspect.md`.

**Prerequisite:** Understand parameter context concepts in `references/ops-parameters-main.md`.

**Discovery:** Run `nipyapi ci configure_inherited_params --help` to see all available arguments.

---

## Prerequisite: Verify Before Configuring

If you encounter unexpected failures when setting parameters, run verification first:

```bash
nipyapi --profile <profile> ci verify_config --process_group_id "<pg-id>" --only_failures
```

If verification reports failures, load `ops-config-verification.md` for failure pattern interpretation before continuing.

## Parameter Value Semantics

When using `prepare_parameter()` (Python) or setting parameter values:

| Call | Meaning |
|------|---------|
| `prepare_parameter("Param")` | Ensure parameter exists, don't change value |
| `prepare_parameter("Param", description="...")` | Update description only, preserve existing value |
| `prepare_parameter("Param", value=None)` | Explicitly unset/remove the value |
| `prepare_parameter("Param", value="")` | Set to empty string |
| `prepare_parameter("Param", value="foo")` | Set to "foo" |

**Key distinction:**
- Omitting `value` = "leave existing value unchanged" (useful for sensitive params)
- `value=None` = "explicitly unset/remove the value"
- `value=""` = "set to empty string"

---

## Configure Parameters (Inheritance-Aware)

The `configure_inherited_params` function safely updates parameters in their owning contexts, preventing accidental shadowing.

**Exact argument names:**
- `--process_group_id` (not --pg_id, --id, etc.)
- `--parameters` (JSON string) or `--parameters_file` (file path)
- `--dry_run` (optional, always use first)

### Dry Run (Always Do This First)

```bash
nipyapi ci configure_inherited_params \
  --process_group_id "<pg-id>" \
  --parameters '{"Param1": "value1", "Param2": "value2"}' \
  --dry_run
```

Output shows where each parameter will be updated:

```json
{
  "dry_run": "true",
  "parameters_updated": "0",
  "contexts_modified": "0",
  "plan": "Param1→Ingestion Parameters | Param2→Source Parameters"
}
```

### Execute Parameter Updates

After confirming the plan:

```bash
nipyapi ci configure_inherited_params \
  --process_group_id "<pg-id>" \
  --parameters '{"Param1": "value1", "Param2": "value2"}'
```

### Set Multiple Parameters Across Hierarchy

```bash
nipyapi ci configure_inherited_params \
  --process_group_id "<pg-id>" \
  --parameters '{
    "Ingestion Type": "cdc",
    "Source Username": "myuser",
    "Snowflake Warehouse": "my_wh"
  }'
```

Each parameter is automatically routed to its owning context.

### Error Handling

Unknown parameters are rejected with helpful errors:

```json
{
  "errors": "Parameter 'NonExistentParam' not found in any context. Use --allow_override to create it."
}
```

### Asset Replacement Warning

If you try to set a value on a parameter that currently references an asset:

```json
{
  "plan": "My Asset Param→Source Parameters",
  "warnings": "Parameter 'My Asset Param' currently has asset 'file.jar' mapped. Setting a value will replace the asset reference."
}
```

### Sensitive Parameters

The function automatically detects sensitive parameters. In dry run output, sensitive values are masked as `********`.

**Agent behavior:** When collecting sensitive values from users (passwords, secrets, tokens, keys):
- Do NOT echo the value back in confirmation messages
- Use `[REDACTED]` when referencing the parameter in explanations
- Pass values directly to commands without displaying them

**Example:**
- Bad: "I'll set Client Secret to `abc123xyz`"
- Good: "I'll configure the Client Secret you provided"

---

## Import Parameters from File

Load parameters directly from a JSON or YAML file:

```bash
nipyapi ci configure_inherited_params \
  --process_group_id "<pg-id>" \
  --parameters_file params.json
```

Supports both formats. The file should contain a flat object:

**JSON:**
```json
{
  "Ingestion Type": "cdc",
  "Included Table Names": "public.users,public.orders",
  "Snowflake Warehouse": "COMPUTE_WH"
}
```

**YAML:**
```yaml
Ingestion Type: cdc
Included Table Names: public.users,public.orders
Snowflake Warehouse: COMPUTE_WH
```

Always dry run first:

```bash
nipyapi ci configure_inherited_params \
  --process_group_id "<pg-id>" \
  --parameters_file params.json \
  --dry_run
```

---

## Export Parameters

Export parameters from a context hierarchy for backup or migration:

```bash
# Export by parameter context ID
nipyapi ci export_parameters --context_id "<ctx-id>" --file_path params.json

# Export from process group's bound context
nipyapi ci export_parameters --process_group_id "<pg-id>" --file_path params.yaml --mode yaml

# Export with full hierarchy structure (shows which context owns each parameter)
nipyapi ci export_parameters --context_id "<ctx-id>" --include_hierarchy --file_path hierarchy.json
```

### Export Options

| Option | Description |
|--------|-------------|
| `--context_id` | Parameter context ID to export (one-of) |
| `--process_group_id` | Resolve context from this PG (one-of) |
| `--file_path` | Output file path (default: stdout) |
| `--mode` | `json` or `yaml` (default: json) |
| `--include_hierarchy` | Include full hierarchy structure |

**Note:** Sensitive parameter values cannot be exported (NiFi returns null), but their keys are preserved so you know what needs to be set manually.

---

## Parameter Migration Roundtrip

Export from one environment and import to another:

```bash
# 1. Export from source environment
nipyapi --profile source ci export_parameters \
  --process_group_id "<source-pg-id>" \
  --file_path params.json

# 2. Edit params.json if needed (update environment-specific values)

# 3. Dry run on target to verify (always do this first)
nipyapi --profile target ci configure_inherited_params \
  --process_group_id "<target-pg-id>" \
  --parameters_file params.json \
  --dry_run

# 4. Apply to target
nipyapi --profile target ci configure_inherited_params \
  --process_group_id "<target-pg-id>" \
  --parameters_file params.json
```

After import, you must separately set any sensitive parameters (passwords, keys, etc.).

---

## Troubleshooting

### "Parameter not found in any context"

The parameter name doesn't match any existing parameter. Check:
1. Exact spelling (case-sensitive)
2. Use `get_parameter_ownership_map` to list valid parameter names (see `references/ops-parameters-inspect.md`)

### "Setting a value will replace the asset reference"

You're trying to set a text value on a parameter that currently references an asset. If intentional, proceed. If you want to update the asset itself, use `upload_asset` instead (see `references/ops-parameters-assets.md`).

### Parameter context locked

If updates fail with a conflict error, another operation may be in progress. Wait and retry, or check for stuck update requests in the NiFi UI.

---

## Next Step

After configuration:
- To manage assets, load `references/ops-parameters-assets.md`
- To verify flow, load `references/ops-flow-lifecycle.md`
- Return to `references/ops-parameters-main.md` for routing
