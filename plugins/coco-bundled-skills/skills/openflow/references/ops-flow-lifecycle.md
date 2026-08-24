---
name: openflow-ops-flow-lifecycle
description: Start, stop, monitor, and manage Openflow flows. Use for flow lifecycle operations including status checks, bulletins, and force stop.
---

# Flow Lifecycle Operations

Start, stop, monitor, and manage flows. These operations apply to all process groups regardless of whether they are connectors or custom flows.

**Note:** These operations modify service state. Apply the Check-Act-Check pattern (see `references/core-guidelines.md`).

## Approach

Use `get_status` as the default Check function. It provides a summary of flow health. For specific investigations, use more targeted read functions.

After reviewing status, select the appropriate operation from the table below.

## Operations Overview

| User Intent | Operation | When to Use |
|-------------|-----------|-------------|
| What connectors exist, what's deployed | [List Flows](#list-flows) | See all deployed flows on the canvas |
| Check health, see what's happening | [Get Status](#get-status) | First step for any investigation |
| See actual error messages | [Get Detailed Bulletins](#get-detailed-bulletins) | After get_status shows bulletin_errors > 0 |
| Activate a stopped flow | [Start Flow](#start-a-flow) | Flow is stopped and ready to run |
| Pause data processing | [Stop Flow](#stop-a-flow) | Maintenance, before configuration changes |
| Process one item only | [Run Processor Once](#run-processor-once) | Troubleshooting, testing, controlled processing |
| Inspect queued data | [Inspect Connection Queues](#inspect-connection-queues) | Debug content/attributes in queues |
| Prevent processor from starting | [Disable Processor](#disable-a-processor) | Maintenance, mark as inactive |
| Stuck threads won't stop | [Force Stop](#force-stop-terminate-threads) | Standard stop doesn't work, threads stuck |
| Enable controllers (all or single) | [Enable Controllers](#enable-controllers) | Validate config before starting processors |
| Disable controllers (all or single) | [Disable Controllers](#disable-controllers) | Maintenance, disable invalid controllers |
| Clear in-flight data | [Purge Flowfiles](#purge-flowfiles) | Recovery from errors, fresh start without delete |
| Remove flow from canvas | [Delete Flow](#delete-a-flow) | Flow no longer needed |

---

## List Flows

See all deployed flows (process groups) on the canvas.

```bash
nipyapi --profile <profile> ci list_flows
```

Output includes:
- `process_groups[]` - array of deployed flows
- Each entry shows `name`, `id`, `versioned` (boolean), and status counts

**Filter to names only:**

```bash
nipyapi --profile <profile> ci list_flows | jq -r '.process_groups[].name'
```

**Get summary with status:**

```bash
nipyapi --profile <profile> ci list_flows | jq '.process_groups[] | {name, id, running: .running_count, stopped: .stopped_count, invalid: .invalid_count}'
```

---

## Get Status

```bash
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
```

### Key Status Fields

| Field | Meaning |
|-------|---------|
| `running_processors` | Number of actively running processors |
| `stopped_processors` | Number of stopped processors |
| `invalid_processors` | Processors with configuration errors |
| `queued_flowfiles` | Data waiting in queues |
| `active_threads` | Currently executing threads |
| `bulletin_errors` | Error count from bulletins |
| `bulletin_warnings` | Warning count from bulletins |

### Healthy Flow Indicators

- `running_processors` > 0 (flow is active)
- `stopped_processors` = 0 (all processors running)
- `invalid_processors` = 0 (no configuration issues)
- `bulletin_errors` = 0 (no errors)

### Interpreting Status

| Observation | Likely Action |
|-------------|---------------|
| `bulletin_errors` > 0 | Get detailed bulletins to see error messages |
| `stopped_processors` > 0 when should be running | Start flow or investigate invalid processors |
| `queued_flowfiles` very high | Downstream bottleneck or failed processor |
| `active_threads` > 0 after stop | Wait for threads or force stop |

---

## Get Detailed Bulletins

When `get_status` shows `bulletin_errors` or `bulletin_warnings`, get the actual messages:

```bash
nipyapi --profile <profile> bulletins get_bulletin_board --pg_id "<pg-id>"
```

Or in Python:

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

pg_id = "<pg-id>"
bulletins = nipyapi.bulletins.get_bulletin_board(pg_id=pg_id)

for b in bulletins:
    print(f"[{b.level}] {b.source_name}: {b.message}")
```

**Note:** Bulletins remain visible for 5 minutes, even across component restarts. When troubleshooting, check the bulletin timestamp to ensure you're looking at current issues, not stale messages from before a restart.

For advanced bulletin operations (filtering, clearing, investigation patterns), see `references/ops-bulletins.md`.

---

## Start a Flow

**Check:** `get_status` - expect `stopped_processors` > 0

**Act:**

```bash
nipyapi --profile <profile> ci start_flow --process_group_id "<pg-id>"
```

**Check:** `get_status` - expect `running_processors` > 0, `bulletin_errors` = 0

If `bulletin_errors` > 0 after starting, see [Get Detailed Bulletins](#get-detailed-bulletins).

---

## Stop a Flow

### Standard Stop (Processors Only)

Stop processors but leave controllers enabled for quick restart. Processors must be stopped before they can be edited.

**Check:** `get_status` - expect `running_processors` > 0

**Act:**

```bash
nipyapi --profile <profile> ci stop_flow --process_group_id "<pg-id>"
```

**Check:** `get_status` - expect `stopped_processors` > 0, `running_processors` = 0

### Full Stop (Processors and Controllers)

Required before deletion or version changes.

**Check:** `get_status` - expect `running_processors` > 0

**Act:**

```bash
nipyapi --profile <profile> ci stop_flow --process_group_id "<pg-id>" --disable_controllers
```

**Check:** `get_status` - expect `stopped_processors` > 0, `active_threads` = 0

### Force Stop (Terminate Threads)

When standard stop doesn't work and threads are stuck.

**Check:** `get_status` - expect `active_threads` > 0 persisting after standard stop

**Act:**

```bash
nipyapi --profile <profile> ci stop_flow --process_group_id "<pg-id>" --terminate
```

**Check:** `get_status` - expect `active_threads` = 0

**Warning:** Terminating threads may result in data loss for in-flight flowfiles.

---

## Run Processor Once

Execute a single scheduling cycle of a processor, then automatically stop. This is useful for:

- **Troubleshooting:** Process one flowfile to observe behavior without continuous execution
- **Testing:** Generate a single test flowfile from GenerateFlowFile or similar sources
- **Controlled processing:** Process exactly one item from a queue for verification

**Note:** RUN_ONCE operates on individual processors, not entire process groups.

### Python

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

# Get the processor
proc = nipyapi.canvas.get_processor("<processor-name-or-id>")

# Run once - executes one scheduling cycle then returns to STOPPED
nipyapi.canvas.schedule_processor(proc, "RUN_ONCE")

# The function waits for completion and returns True when the processor
# finishes execution and returns to STOPPED state
```

### CLI

```bash
nipyapi --profile <profile> canvas schedule_processor "<processor-id>" RUN_ONCE
```

### Common Use Cases

**Generate a single test flowfile:**
```python
# Get GenerateFlowFile processor
gen = nipyapi.canvas.get_processor("GenerateFlowFile")

# Generate exactly one flowfile
nipyapi.canvas.schedule_processor(gen, "RUN_ONCE")
```

**Process one item from a queue:**
```python
# Get the processor that reads from a queue
proc = nipyapi.canvas.get_processor("ConsumeKafka")

# Process one batch/message
nipyapi.canvas.schedule_processor(proc, "RUN_ONCE")
```

**Step through a flow for debugging:**
```python
# Run each processor in sequence to observe data transformation
processors = ["ParseJSON", "TransformRecord", "UpdateRecord"]
for name in processors:
    proc = nipyapi.canvas.get_processor(name)
    nipyapi.canvas.schedule_processor(proc, "RUN_ONCE")
    # Check queues/bulletins between each step
```

### Disable a Processor

Disable a processor to prevent it from being started (useful during maintenance or to mark processors that shouldn't run):

```python
# Disable
nipyapi.canvas.schedule_processor(proc, "DISABLED")

# Re-enable by setting to STOPPED (can then be started)
nipyapi.canvas.schedule_processor(proc, "STOPPED")
```

**Note:** The `schedule_processor` function accepts:
- Boolean: `True` (RUNNING), `False` (STOPPED) - backwards compatible
- String: `"RUNNING"`, `"STOPPED"`, `"DISABLED"`, `"RUN_ONCE"`

---

## Inspect Connection Queues

Examine FlowFiles waiting in connections without consuming them. Useful for debugging transformations, verifying data format, and troubleshooting stuck flows.

**Quick example:**

```python
# Run processor once, then inspect output
proc = nipyapi.canvas.get_processor("MyProcessor")
nipyapi.canvas.schedule_processor(proc, "RUN_ONCE")

# Find output connection and peek at FlowFiles
connections = nipyapi.canvas.list_all_connections(pg_id)
out_conn = next(c for c in connections if c.source_id == proc.id)
flowfiles = nipyapi.canvas.peek_flowfiles(out_conn, limit=1)

if flowfiles:
    print(f"Attributes: {flowfiles[0].attributes}")
    content = nipyapi.canvas.get_flowfile_content(out_conn, flowfiles[0].uuid)
    print(f"Content: {content[:500]}")
```

**For detailed connection and FlowFile inspection:** See `references/ops-connection-inspection.md`

---

## Enable Controllers

Enable controller services without starting processors. Useful for validating configuration.

```bash
# All controllers in process group
nipyapi canvas schedule_all_controllers "<pg-id>" True

# Single controller by name or ID
nipyapi canvas schedule_controller "JsonTreeReader" True
```

**Check:** Verify controllers enabled, no validation errors in bulletins.

---

## Disable Controllers

Disable controller services. Controllers must be disabled before editing. Stop processors first.

```bash
# All controllers in process group
nipyapi canvas schedule_all_controllers "<pg-id>" False

# Single controller (e.g., invalid Private Key Service on SPCS)
nipyapi canvas schedule_controller "Snowflake Private Key Service" False
```

**Check:** Controllers disabled, `get_status` shows expected state.

---

## Purge Flowfiles

Clear all queued data from the flow without deleting the flow itself.

**Check:** `get_status` - note current `queued_flowfiles` count

**Act:**

```bash
nipyapi --profile <profile> ci purge_flowfiles --process_group_id "<pg-id>"
```

**Check:** `get_status` - expect `queued_flowfiles` = 0

**Warning:** This removes all queued flowfiles from the canvas and marks them for deletion. While content may persist briefly on disk until garbage collection runs, this is not a reliable recovery mechanism as the user has no control over when garbage collection occurs. Treat purged data as lost.

**Before purging**, consider:
- Can the flow drain naturally? Check `queued_flowfiles` over time
- Is there data that should be preserved?

---

## Delete a Flow

**Before deleting**, consider exporting a backup if the flow is not under version control:

```bash
nipyapi --profile <profile> ci export_flow_definition \
  --process_group_id "<pg-id>" \
  --file_path backup-$(date +%Y%m%d).json
```

See `references/ops-flow-export.md` for complete backup workflows including parameter contexts.

### Safe Delete (Preserves Parameter Context)

**Check:** `get_status` - expect `running_processors` = 0, `active_threads` = 0

**Act:**

```bash
nipyapi --profile <profile> ci cleanup --process_group_id "<pg-id>"
```

**Check:** `list_flows` - flow no longer appears

### Full Delete (Including Parameter Context)

**Check:** `get_status` - expect `running_processors` = 0, `active_threads` = 0

**Act:**

```bash
nipyapi --profile <profile> ci cleanup \
  --process_group_id "<pg-id>" \
  --delete_parameter_context \
  --force
```

**Check:** `list_flows` - flow no longer appears; parameter context also removed

**Warning:** Only use `--delete_parameter_context` when:
- This is the only flow using that context
- You are certain no other flows depend on it

**Note:** The `--delete_parameter_context` flag only deletes the directly bound context. Connectors with inherited parameter contexts (e.g., Snowflake Connectors with Ingestion/Source/Destination contexts) require the complete removal workflow below.

### Complete Connector Removal (Including Inherited Contexts)

For connectors with parameter inheritance (e.g., PostgreSQL, MySQL connectors), follow this workflow to safely remove the process group and all associated parameter contexts.

**Step 1: Get the parameter context ID**

```bash
CTX_ID=$(nipyapi --profile <profile> canvas get_process_group "<pg-name>" | jq -r '.component.parameter_context.id')
echo "Context ID: $CTX_ID"
```

**Step 2: Inspect the hierarchy with bindings**

```bash
nipyapi --profile <profile> parameters get_parameter_context_hierarchy "$CTX_ID" True False
```

This shows all contexts in the hierarchy and which process groups are bound to each. Contexts with empty `bound_process_groups` arrays can be safely deleted after the process group is removed.

**Step 3: Delete the process group**

```bash
nipyapi --profile <profile> ci cleanup --process_group_id "<pg-id>"
```

**Step 4: Delete unbound parameter contexts**

After the process group is deleted, re-check bindings and delete contexts that are no longer used:

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

# Context IDs from step 2 (work from leaves up)
context_ids = ["<source-ctx-id>", "<dest-ctx-id>", "<ingestion-ctx-id>"]

for ctx_id in context_ids:
    ctx = nipyapi.parameters.get_parameter_context(ctx_id, identifier_type="id")
    if not ctx.component.bound_process_groups:
        print(f"Deleting: {ctx.component.name}")
        nipyapi.parameters.delete_parameter_context(ctx)
    else:
        print(f"Skipping (still bound): {ctx.component.name}")
```

**Check:** Verify contexts are removed:

```bash
nipyapi --profile <profile> parameters list_all_parameter_contexts | jq '.[].component.name'
```

---

## Common Patterns

### Clean Stop Before Version Change

```bash
# Check
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"

# Act: Stop with controllers disabled
nipyapi --profile <profile> ci stop_flow --process_group_id "<pg-id>" --disable_controllers

# Check: Wait for threads
while [ "$(nipyapi --profile <profile> ci get_status --process_group_id '<pg-id>' | jq -r '.active_threads')" != "0" ]; do
  sleep 2
done

# Act: Version change
nipyapi --profile <profile> ci change_flow_version --process_group_id "<pg-id>"

# Act: Restart
nipyapi --profile <profile> ci start_flow --process_group_id "<pg-id>"

# Check
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
```

### Recovery: Purge and Restart

```bash
# Check
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"

# Act: Stop
nipyapi --profile <profile> ci stop_flow --process_group_id "<pg-id>" --disable_controllers

# Check: Wait for threads
while [ "$(nipyapi --profile <profile> ci get_status --process_group_id '<pg-id>' | jq -r '.active_threads')" != "0" ]; do
  sleep 2
done

# Act: Purge
nipyapi --profile <profile> ci purge_flowfiles --process_group_id "<pg-id>"

# Check: Confirm purged
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
# Expect: queued_flowfiles = 0

# Act: Restart
nipyapi --profile <profile> ci start_flow --process_group_id "<pg-id>"

# Check
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
```

---

## Available Functions

| Function | Purpose |
|----------|---------|
| `nipyapi ci get_status` | Get flow status and health metrics |
| `nipyapi ci start_flow` | Enable controllers and start processors |
| `nipyapi ci stop_flow` | Stop processors (options: --disable_controllers, --terminate) |
| `nipyapi canvas schedule_processor` | Control individual processor (True/False/"RUN_ONCE"/"DISABLED") |
| `nipyapi canvas list_flowfiles` | List FlowFiles in a connection queue |
| `nipyapi canvas get_flowfile_details` | Get FlowFile attributes and metadata |
| `nipyapi canvas get_flowfile_content` | Download FlowFile content (with decode/save options) |
| `nipyapi canvas peek_flowfiles` | List and get details for first N FlowFiles |
| `nipyapi ci purge_flowfiles` | Clear all queued data |
| `nipyapi ci cleanup` | Delete a flow from the canvas |
| `nipyapi canvas schedule_all_controllers` | Enable/disable all controllers in a process group |
| `nipyapi canvas schedule_controller` | Enable/disable a single controller by name or ID |
| `nipyapi bulletins get_bulletin_board` | Get bulletins for a process group |
| `nipyapi bulletins clear_all_bulletins` | Clear all bulletins (NiFi 2.7.0+) |

---

## Curl Alternatives

For environments using curl instead of nipyapi. Ensure `$BASE_URL` and `$AUTH_HEADER` are set from your nipyapi profile (see `references/core-guidelines.md` section 4).

### Get Status (curl)

```bash
PG_ID="<pg-id>"
curl -sk -H "$AUTH_HEADER" "$BASE_URL/flow/process-groups/$PG_ID?uiOnly=true" | jq '{
  running: .processGroupFlow.flow.processGroups[0].runningCount,
  stopped: .processGroupFlow.flow.processGroups[0].stoppedCount,
  invalid: .processGroupFlow.flow.processGroups[0].invalidCount,
  queued: .processGroupFlow.flow.processGroups[0].status.aggregateSnapshot.flowFilesQueued
}'
```

### Get Bulletins (curl)

```bash
PG_ID="<pg-id>"
curl -sk -H "$AUTH_HEADER" "$BASE_URL/flow/process-groups/$PG_ID?uiOnly=true" | jq '.processGroupFlow.flow.processGroups[0].bulletins[]'
```

### Start Flow (curl)

Enable controllers first, then start:

```bash
PG_ID="<pg-id>"

# Enable controllers
curl -sk -X PUT -H "$AUTH_HEADER" -H "Content-Type: application/json" \
  -d '{"id": "'"$PG_ID"'", "disconnectedNodeAcknowledged": false, "state": "ENABLED"}' \
  "$BASE_URL/flow/process-groups/$PG_ID/controller-services"

# Start processors
curl -sk -X PUT -H "$AUTH_HEADER" -H "Content-Type: application/json" \
  -d '{"id": "'"$PG_ID"'", "disconnectedNodeAcknowledged": false, "state": "RUNNING"}' \
  "$BASE_URL/flow/process-groups/$PG_ID"
```

### Stop Flow (curl)

```bash
PG_ID="<pg-id>"

# Stop processors
curl -sk -X PUT -H "$AUTH_HEADER" -H "Content-Type: application/json" \
  -d '{"id": "'"$PG_ID"'", "disconnectedNodeAcknowledged": false, "state": "STOPPED"}' \
  "$BASE_URL/flow/process-groups/$PG_ID"

# Disable controllers (for full stop)
curl -sk -X PUT -H "$AUTH_HEADER" -H "Content-Type: application/json" \
  -d '{"id": "'"$PG_ID"'", "disconnectedNodeAcknowledged": false, "state": "DISABLED"}' \
  "$BASE_URL/flow/process-groups/$PG_ID/controller-services"
```

**Note:** After stopping, processors may transition to 'STOPPING' state with active threads. Check status until `active_threads` = 0.

### Run Processor Once (curl)

Execute a single scheduling cycle of a processor:

```bash
PROCESSOR_ID="<processor-id>"

# Get current revision
REVISION=$(curl -sk -H "$AUTH_HEADER" "$BASE_URL/processors/$PROCESSOR_ID" | jq '.revision')

# Run once
curl -sk -X PUT -H "$AUTH_HEADER" -H "Content-Type: application/json" \
  -d "{\"revision\": $REVISION, \"state\": \"RUN_ONCE\"}" \
  "$BASE_URL/processors/$PROCESSOR_ID/run-status"
```

The processor will execute one scheduling cycle then return to STOPPED state.

### Terminate Threads (curl - processor level)

If a specific processor is stuck, terminate its threads:

```bash
PG_ID="<pg-id>"

# Find processor ID from flow
curl -sk -H "$AUTH_HEADER" "$BASE_URL/process-groups/$PG_ID/processors" | jq '.processors[] | {id: .id, name: .component.name, state: .component.state, activeThreads: .status.aggregateSnapshot.activeThreadCount}'

# Terminate specific processor (use DELETE on running threads)
PROCESSOR_ID="<processor-id>"
curl -sk -X DELETE -H "$AUTH_HEADER" "$BASE_URL/processors/$PROCESSOR_ID/threads"
```

---

## Next Step

After lifecycle operations complete, **return to the calling workflow** to continue with the next step.

If you arrived here directly from the main router, return there for further routing.

---

## Related References

- `references/ops-component-config.md` - Set component properties
- `references/ops-flow-deploy.md` - Deploy flows from registries
- `references/ops-version-control.md` - Git-based version control
- `references/ops-flow-export.md` - Export/import flows for backup or migration
- `references/ops-bulletins.md` - Detailed bulletin investigation
