---
name: openflow-ops-flow-export
description: Export and import flow definitions for backup, static analysis, or migration. Use when you need to download a flow as JSON/YAML for inspection, save a backup without VCS, or instantiate a flow from a definition file.
---

# Flow Export and Import

Export and import flow definitions as JSON/YAML files.

**Scope:** Use this reference for backup, static analysis, or migration when VCS is not available. For VCS-based deployments, see `references/ops-version-control.md`. For registry deployments, see `references/ops-flow-deploy.md`.

**Note:** A VCS approach is recommended when available as it has superior version management functionality.
- Does NOT cover Git-based version control (see `references/ops-version-control.md`)

## When to Use

| Scenario | Operation |
|----------|-----------|
| Deploy flow from local file (no VCS) | Import |
| Share flow definition between teams | Export (source) + Import (target) |
| Backup flow before changes | Export |
| Restore flow from backup | Import |
| Migrate flow between environments | Export + Import |
| Clone a flow on the same canvas | Export + Import |
| Analyze flow structure offline | Export |
| Compare configurations between environments | Export both, diff |

## Prerequisites

- nipyapi CLI installed and profile configured (see `references/bootstrap-cli.md`)
- Process group ID from `get_status` or `list_flows`

## CLI Commands Reference

| Command | Purpose |
|---------|---------|
| `nipyapi ci export_flow_definition` | Export PG to JSON/YAML |
| `nipyapi ci import_flow_definition` | Create PG from definition |

---

## 1. Export Flow Definition

### Export to File

```bash
nipyapi --profile <profile> ci export_flow_definition \
  --process_group_id "<pg-id>" \
  --file_path flow.json
```

### Export to stdout (for piping)

```bash
nipyapi --profile <profile> ci export_flow_definition \
  --process_group_id "<pg-id>"
```

### Export as YAML

```bash
nipyapi --profile <profile> ci export_flow_definition \
  --process_group_id "<pg-id>" \
  --mode yaml \
  --file_path flow.yaml
```

### Include External Controller Services

Include controller services referenced from outside the process group:

```bash
nipyapi --profile <profile> ci export_flow_definition \
  --process_group_id "<pg-id>" \
  --include_referenced_services \
  --file_path flow-complete.json
```

### Python Example

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

pg = nipyapi.canvas.get_process_group('<pg-id>', 'id')

# Export to file
nipyapi.versioning.export_process_group_definition(
    pg, file_path='flow.json', mode='json'
)

# Export to string for analysis
flow_json = nipyapi.versioning.export_process_group_definition(pg, mode='json')
```

---

## 2. Import Flow Definition

### Import from File

```bash
nipyapi --profile <profile> ci import_flow_definition \
  --file_path flow.json
```

### Import with Custom Position

```bash
nipyapi --profile <profile> ci import_flow_definition \
  --file_path flow.json \
  --location_x 500 \
  --location_y 500
```

### Import to Specific Parent

```bash
nipyapi --profile <profile> ci import_flow_definition \
  --file_path flow.json \
  --parent_id "<parent-pg-id>"
```

### Import from String (Piping)

```bash
cat flow.json | nipyapi --profile <profile> ci import_flow_definition \
  --flow_definition "$(cat)"
```

### Python Example

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

# Import from file
root_pg = nipyapi.canvas.get_process_group(nipyapi.canvas.get_root_pg_id(), 'id')

imported_pg = nipyapi.versioning.import_process_group_definition(
    parent_pg=root_pg,
    file_path='flow.json',
    position=(500, 500)
)

print(f"Created: {imported_pg.component.name} ({imported_pg.id})")
```

### After Import: Next Steps

After importing a flow, you typically need to:

1. **Check for parameter context:** The imported flow may reference a parameter context by name. If that context doesn't exist, create it or bind an existing one. See `references/ops-parameters-main.md`.

2. **Configure parameters:** Set parameter values for the imported flow. See `references/ops-parameters-main.md`.

3. **Verify configuration:** Check that controller services and processors are valid. See `references/ops-config-verification.md`.

4. **Start the flow:** Enable controllers and start processors. See `references/ops-flow-lifecycle.md`.

---

## 3. What's in the Definition

The JSON definition contains the flow structure but **not** parameter context definitions:

| Section | Contents |
|---------|----------|
| `flowContents` | Root container with all components |
| `flowContents.processors` | All processors with full configuration |
| `flowContents.controllerServices` | Controller service definitions |
| `flowContents.connections` | Relationships between components |
| `flowContents.processGroups` | Nested process groups (recursive) |
| `flowContents.parameterContextName` | **Name only** - not the full definition |
| `flowContents.inputPorts` / `outputPorts` | Port definitions |
| `flowContents.funnels` | Funnel components |
| `flowContents.labels` | Canvas labels |

### What's NOT Included (Important for Import)

| Missing | Impact on Import | Workaround |
|---------|------------------|------------|
| Parameter context definitions | Must create/bind context after import | Create context with matching name |
| Parameter values | Parameters will be empty | Configure via `configure_params` or UI |
| Sensitive parameter values | Never included (security) | Must set manually after import |
| Assets (binary files) | Referenced assets won't exist | Upload assets separately |

**Key difference from VCS:** When NiFi Registry saves a flow, it includes full `parameterContexts` with all parameter definitions. Direct export/import only includes the parameter context **name** reference - you must handle parameter contexts separately.

### Key Fields per Component

| Component | Key Fields |
|-----------|------------|
| Processor | `type`, `name`, `properties`, `schedulingStrategy`, `autoTerminatedRelationships` |
| Controller Service | `type`, `name`, `properties`, `scheduledState` |
| Connection | `source`, `destination`, `selectedRelationships`, `backPressureObjectThreshold` |

---

## 4. Inspecting Flow Definitions

Use jq or Python to inspect flow definitions - whether analyzing an export or validating a file before import.

### List All Processor Types

```bash
cat flow.json | jq -r '.flowContents.processors[].type' | sort | uniq -c | sort -rn
```

### Find Processors by Type

```bash
cat flow.json | jq '.flowContents.processors[] | select(.type | contains("PutDatabaseRecord"))'
```

### List Controller Services

```bash
cat flow.json | jq '.flowContents.controllerServices[] | {name, type}'
```

### Find Parameter References

```bash
cat flow.json | jq -r '.. | strings | select(contains("#{"))' | sort -u
```

### Check for Specific Properties

```bash
cat flow.json | jq '.flowContents.processors[] | select(.properties["Table Name"] != null) | {name, table: .properties["Table Name"]}'
```

### Count Components

```bash
cat flow.json | jq '{
  processors: (.flowContents.processors | length),
  controllers: (.flowContents.controllerServices | length),
  connections: (.flowContents.connections | length),
  nested_groups: (.flowContents.processGroups | length)
}'
```

### Python Analysis Example

```python
import json

with open('flow.json') as f:
    flow = json.load(f)

contents = flow['flowContents']

# Find all database-related processors
db_processors = [
    p for p in contents.get('processors', [])
    if 'Database' in p.get('type', '') or 'SQL' in p.get('type', '')
]

for p in db_processors:
    print(f"{p['name']} ({p['type']})")
    for prop, val in p.get('properties', {}).items():
        if val and '#{' in str(val):
            print(f"  {prop}: {val}")
```

---

## 5. Common Patterns

### Deploy Flow from Local File

When VCS is not available, deploy a flow directly from a JSON file:

```bash
nipyapi --profile <profile> ci import_flow_definition \
  --file_path my-flow.json
```

**After import:** Configure parameters (`references/ops-parameters-main.md`), verify configuration (`references/ops-config-verification.md`), and start the flow (`references/ops-flow-lifecycle.md`).

### Share Flow Between Teams

Export a flow and share it with another team or environment:

```bash
# Team A: Export their flow
nipyapi --profile team-a ci export_flow_definition \
  --process_group_id "<pg-id>" \
  --file_path shared-flow.json

# Team B: Import the shared flow
nipyapi --profile team-b ci import_flow_definition \
  --file_path shared-flow.json
```

### Backup Before Changes

```bash
# Export current state
nipyapi --profile <profile> ci export_flow_definition \
  --process_group_id "<pg-id>" \
  --file_path "backup-$(date +%Y%m%d-%H%M%S).json"

# Make changes...

# Restore if needed
nipyapi --profile <profile> ci import_flow_definition \
  --file_path backup-*.json
```

### Compare Environments

```bash
# Export from both
nipyapi --profile dev ci export_flow_definition --process_group_id "<pg-id>" --file_path dev.json
nipyapi --profile prod ci export_flow_definition --process_group_id "<pg-id>" --file_path prod.json

# Compare (ignoring IDs which will differ)
diff <(cat dev.json | jq 'del(.. | .identifier?, .groupIdentifier?)') \
     <(cat prod.json | jq 'del(.. | .identifier?, .groupIdentifier?)')
```

### Clone a Flow

```bash
# Export
nipyapi --profile <profile> ci export_flow_definition \
  --process_group_id "<pg-id>" --file_path flow.json

# Import as new instance
nipyapi --profile <profile> ci import_flow_definition \
  --file_path flow.json --location_x 400 --location_y 400
```

### Complete Backup (Flow + Parameter Context)

Since the flow export only includes parameter context names, export them separately for a complete backup:

1. Export the flow definition using `export_flow_definition`
2. Find the `parameterContextName` in the exported JSON
3. Export the parameter context hierarchy - see `references/ops-parameters-main.md` for `get_parameter_context_hierarchy`
4. Save both files together

### Design Review Checklist

After exporting, check for common issues:

```bash
# Check for hardcoded values (should use parameters)
cat flow.json | jq -r '.. | strings' | grep -E '(password|secret|key|token)' | head -20

# Check for missing auto-terminate
cat flow.json | jq '.flowContents.processors[] | select(.autoTerminatedRelationships == []) | .name'

# Check scheduling periods
cat flow.json | jq '.flowContents.processors[] | {name, period: .schedulingPeriod}' | grep -v '"0 sec"'
```

---

## 6. Curl Alternatives

For environments using curl. Ensure `$BASE_URL` and `$AUTH_HEADER` are set from your nipyapi profile (see `references/core-guidelines.md` section 4).

### Export (curl)

```bash
PG_ID="<pg-id>"
curl -sk -H "$AUTH_HEADER" \
  "$BASE_URL/process-groups/$PG_ID/download?includeReferencedServices=false" \
  -o flow.json
```

### Import (curl)

```bash
PARENT_ID="<parent-pg-id>"  # Use root PG ID if importing to canvas root
curl -sk -X POST -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d @flow.json \
  "$BASE_URL/process-groups/$PARENT_ID/process-groups/import?positionX=0&positionY=0"
```

---

## Next Step

After export/import:
- For flow operations, see `references/ops-flow-lifecycle.md`
- For version control, see `references/ops-version-control.md`
- For parameter inspection, see `references/ops-parameters-main.md`

Return to the calling workflow to continue.

## Related References

- `references/ops-flow-lifecycle.md` - Start, stop, status operations
- `references/ops-version-control.md` - Git-based version control
- `references/ops-config-verification.md` - Validate configuration
