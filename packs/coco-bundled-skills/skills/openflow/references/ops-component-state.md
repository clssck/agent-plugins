---
name: openflow-ops-component-state
description: Inspect and manage component state for processors and controller services. Use when troubleshooting stateful flows, resetting listing processors, or clearing CDC table state.
---

# Component State Operations

This reference covers inspecting and managing internal state for NiFi processors and controller services. Many components maintain state to track progress (e.g., listed files, CDC table positions, cache entries).

**Note:** Clearing state modifies component behavior. Reading state is a safe, read-only operation.

## Scope

This reference covers:
- Retrieving state entries from processors and controller services
- Clearing state to reset component behavior
- Understanding local vs cluster state scopes
- Common patterns for stateful components

This reference does NOT cover:
- Bulletins or error messages (see `references/ops-bulletins.md`)
- Controller service configuration verification (see `references/ops-config-verification.md`)
- Parameter context management (see `references/ops-parameters-assets.md`)

## Key Concepts

| Term | Meaning |
|------|---------|
| **Component State** | Key-value pairs stored by a processor or controller service |
| **Local State** | State scoped to a single node (standalone or primary node) |
| **Cluster State** | State shared across all cluster nodes |
| **State Scope** | Whether component uses LOCAL or CLUSTER state (set in component design) |

## Prerequisites

- nipyapi CLI installed and profile configured (see `references/bootstrap-cli.md`)
- Component ID from flow inspection or `list_all_controllers`/`get_processor`
- For clearing controller state: controller must be DISABLED first

## CLI Commands Reference

| Command | Purpose |
|---------|---------|
| `nipyapi canvas get_processor_state <id>` | Get state entries for a processor |
| `nipyapi canvas clear_processor_state <id>` | Clear all state for a processor |
| `nipyapi canvas get_controller_state <id>` | Get state entries for a controller service |
| `nipyapi canvas clear_controller_state <id>` | Clear state for a controller (must be DISABLED) |

---

## 1. Get Processor State

Processors like ListFile, ListS3, TailFile, and CDC capture processors maintain state to track what has been processed.

```bash
nipyapi --profile <profile> canvas get_processor_state "<processor-id>"
```

### Response Structure

```json
{
  "component_state": {
    "component_id": "<processor-id>",
    "local_state": {
      "scope": "LOCAL",
      "total_entry_count": 3,
      "state": [
        {"key": "listing.timestamp", "value": "1735329600000"},
        {"key": "file1.txt", "value": "1735329600000,12345"}
      ]
    },
    "cluster_state": {
      "scope": "CLUSTER",
      "total_entry_count": 0,
      "state": []
    }
  }
}
```

State is typically in either `local_state` OR `cluster_state` depending on the component's design:
- **Local scope**: ListFile, TailFile (tracks per-node)
- **Cluster scope**: ListS3, ListGCSBucket (tracks across cluster)

### Python Example

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

processor_id = "<processor-id>"
state = nipyapi.canvas.get_processor_state(processor_id)

# Check whichever scope has entries
state_map = state.component_state.local_state
if state_map.total_entry_count == 0:
    state_map = state.component_state.cluster_state

print(f"State scope: {state_map.scope}")
print(f"Entry count: {state_map.total_entry_count}")
for entry in state_map.state:
    print(f"  {entry.key}: {entry.value}")
```

---

## 2. Clear Processor State

Clear state to reset a processor and have it reprocess all data:

```bash
nipyapi --profile <profile> canvas clear_processor_state "<processor-id>"
```

### When to Clear Processor State

| Scenario | Effect |
|----------|--------|
| ListFile state cleared | All files in directory will be re-listed |
| TailFile state cleared | File will be read from beginning |
| CDC capture state cleared | Will re-capture from current position (NOT full re-snapshot) |

### Python Example

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

processor_id = "<processor-id>"

# Clear and verify
nipyapi.canvas.clear_processor_state(processor_id)
state = nipyapi.canvas.get_processor_state(processor_id)
assert state.component_state.local_state.total_entry_count == 0
print("State cleared successfully")
```

---

## 3. Get Controller Service State

Controller services like TableStateService, DistributedMapCacheServer, and StandardStateProvider maintain state:

```bash
nipyapi --profile <profile> canvas get_controller_state "<controller-id>"
```

### Finding Controller Services

```bash
# List all controllers in a process group
nipyapi --profile <profile> canvas list_all_controllers "<pg-id>"

# Find by type pattern
nipyapi --profile <profile> canvas get_controller "TableStateService" --identifier "type" --pg_id "<pg-id>"
```

### Python Example

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

pg_id = "<pg-id>"

# Find controller by type
controllers = nipyapi.canvas.list_all_controllers(pg_id)
state_service = next(
    c for c in controllers
    if 'TableStateService' in c.component.type
)

# Get state
state = nipyapi.canvas.get_controller_state(state_service)
state_map = state.component_state.local_state or state.component_state.cluster_state

for entry in state_map.state:
    print(f"{entry.key}: {entry.value}")
```

---

## 4. Clear Controller Service State

**Important:** Controller services must be DISABLED before clearing state.

```bash
# First disable the controller
nipyapi --profile <profile> canvas schedule_controller "<controller-id>" --scheduled false

# Then clear state
nipyapi --profile <profile> canvas clear_controller_state "<controller-id>"

# Re-enable if needed
nipyapi --profile <profile> canvas schedule_controller "<controller-id>" --scheduled true
```

### When to Clear Controller State

| Controller Type | Effect of Clearing |
|-----------------|-------------------|
| TableStateService | CDC tables will be re-snapshotted |
| DistributedMapCacheServer | All cache entries removed |
| StandardStateProvider | All stored state removed |

### Python Example

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

controller_id = "<controller-id>"

# Disable controller first
controller = nipyapi.canvas.get_controller(controller_id, 'id')
nipyapi.canvas.schedule_controller(controller, scheduled=False, refresh=True)

# Clear state
nipyapi.canvas.clear_controller_state(controller)

# Verify cleared
state = nipyapi.canvas.get_controller_state(controller)
assert state.component_state.local_state.total_entry_count == 0

# Re-enable
nipyapi.canvas.schedule_controller(controller, scheduled=True, refresh=True)
print("State cleared and controller re-enabled")
```

---

## 5. Common Patterns

### Check CDC Table State

For CDC connectors, the `StandardTableStateService` tracks table replication status:

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

pg_id = "<cdc-pg-id>"

# Find TableStateService
controllers = nipyapi.canvas.list_all_controllers(pg_id)
state_service = next(c for c in controllers if 'TableStateService' in c.component.type)

# Get and parse state
state = nipyapi.canvas.get_controller_state(state_service)
state_map = state.component_state.local_state or state.component_state.cluster_state

for entry in state_map.state:
    table_name = entry.key
    parts = entry.value.split(',')
    replication_status = parts[1] if len(parts) > 1 else 'UNKNOWN'
    print(f"{table_name}: {replication_status}")
```

Status values: `NEW`, `SNAPSHOT_REPLICATION`, `INCREMENTAL_REPLICATION`, `FAILED`

### Reset Listing Processor for Re-run

```bash
# Stop the processor
nipyapi --profile <profile> canvas schedule_processor "<processor-id>" --scheduled false

# Clear state
nipyapi --profile <profile> canvas clear_processor_state "<processor-id>"

# Restart
nipyapi --profile <profile> canvas schedule_processor "<processor-id>" --scheduled true
```

### Verify State Before/After Operations

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

processor_id = "<processor-id>"

# Check before
state_before = nipyapi.canvas.get_processor_state(processor_id)
count_before = state_before.component_state.local_state.total_entry_count

# Run operation...

# Check after
state_after = nipyapi.canvas.get_processor_state(processor_id)
count_after = state_after.component_state.local_state.total_entry_count

print(f"State entries: {count_before} -> {count_after}")
```

---

## Curl Alternatives

For environments using curl. Ensure `$BASE_URL` and `$AUTH_HEADER` are set from your nipyapi profile (see `references/core-guidelines.md` section 4).

### Get Processor State (curl)

```bash
PROCESSOR_ID="<processor-id>"
curl -sk -H "$AUTH_HEADER" "$BASE_URL/processors/$PROCESSOR_ID/state" | \
  jq '.componentState.localState // .componentState.clusterState | {scope, count: .totalEntryCount, entries: .state}'
```

### Clear Processor State (curl)

```bash
PROCESSOR_ID="<processor-id>"
curl -sk -X POST -H "$AUTH_HEADER" "$BASE_URL/processors/$PROCESSOR_ID/state/clear-requests"
```

### Get Controller State (curl)

```bash
CONTROLLER_ID="<controller-id>"
curl -sk -H "$AUTH_HEADER" "$BASE_URL/controller-services/$CONTROLLER_ID/state" | \
  jq '.componentState.localState // .componentState.clusterState | {scope, count: .totalEntryCount, entries: .state}'
```

### Clear Controller State (curl)

```bash
# Controller must be DISABLED first
CONTROLLER_ID="<controller-id>"
curl -sk -X POST -H "$AUTH_HEADER" "$BASE_URL/controller-services/$CONTROLLER_ID/state/clear-requests"
```

---

## Stateful Components Reference

Sample of components that have internal state tracking

### Processors with State

| Processor | State Contains |
|-----------|----------------|
| ListFile, ListS3, ListGCSBucket | Listing timestamps, processed file metadata |
| TailFile | File position, inode tracking |
| CaptureChangeMySQL/Postgres/SQLServer | Transaction position, binlog/WAL offset |
| CaptureSharepointChanges | Change tracking position |
| GetSFTP, GetFTP | Listing state |

### Controller Services with State

| Controller Service | State Contains |
|-------------------|----------------|
| StandardTableStateService | CDC table status and positions |
| DistributedMapCacheServer | Cache key-value entries |
| StandardStateProvider | Generic key-value state |

---

## Next Step

After inspecting or clearing state:
- For CDC issues, see `references/connector-cdc.md`
- For bulletin errors, see `references/ops-bulletins.md`
- For controller configuration, see `references/ops-config-verification.md`
- Return to calling workflow to continue

## Related References

- `references/ops-bulletins.md` - Investigate error messages
- `references/ops-flow-lifecycle.md` - Start, stop, status operations
- `references/connector-cdc.md` - CDC connector specifics
