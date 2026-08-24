---
name: openflow-ops-tracked-modifications
description: Preserve and restore local modifications when changing flow versions. Use when switching versions without committing or losing local changes.
---

# Tracked Modifications

Safely change flow versions while preserving local modifications.

**Note:** These operations modify service state. Apply the Check-Act-Check pattern (see `references/core-guidelines.md`).

## Scope

- Preserving local modifications during version changes
- Switching versions without committing or losing changes
- Alternatives: commit first (`ops-version-control.md`) or fork the flow

## Key Insight

NiFi automatically tracks all local modifications. The `get_flow_diff` CI function retrieves these - no manual tracking needed.

## Workflow: Version Change with Preserved Modifications

### Step 1: Verify Local Modifications Exist

```bash
nipyapi --profile <profile> ci list_flows
```

Look for `state: LOCALLY_MODIFIED` or `modified: true`.

| State | Meaning |
|-------|---------|
| `LOCALLY_MODIFIED` | Changes exist, current version is latest |
| `LOCALLY_MODIFIED_AND_STALE` | Local changes exist, newer version available on repository |
| `UP_TO_DATE` | No local changes - this workflow not needed |

### Step 2: Capture Modifications

```bash
nipyapi --profile <profile> ci get_flow_diff --process_group_id <pg_id>
```

**Example output:**

```json
{
  "process_group_id": "ee6fa0cb-019a-1000-0000-00004a06fef2",
  "process_group_name": "My Flow",
  "flow_id": "my-flow",
  "current_version": "abc123...",
  "state": "LOCALLY_MODIFIED",
  "modification_count": 2,
  "modifications": [
    {
      "component_id": "...",
      "component_name": "FetchData",
      "component_type": "Processor",
      "changes": [
        {
          "type": "Run Schedule Changed",
          "description": "From '1 min' to '5 sec'"
        }
      ]
    }
  ]
}
```

### Step 3: Save Modifications to Memory

**Save with a unique timestamped name:**

Format: `YYYY-MM-DDTHH-MM-SS_<flow_name>_modifications`

Example: `2024-12-17T20-45-30_MyFlow_modifications`

**Do not overwrite previous captures** - include full timestamp to preserve history.

### Step 4: Revert Local Changes

**The version change will fail if local modifications exist.** Revert first:

```bash
nipyapi --profile <profile> ci revert_flow --process_group_id <pg_id>
```

Verify the revert succeeded:

```bash
nipyapi --profile <profile> ci list_flows
# Should show state: UP_TO_DATE or STALE (not LOCALLY_MODIFIED)
```

### Step 5: Change Version

**Upgrade to latest:**
```bash
nipyapi --profile <profile> ci change_flow_version --process_group_id <pg_id>
```

**Switch to specific version:**
```bash
nipyapi --profile <profile> ci change_flow_version --process_group_id <pg_id> --target_version <commit_sha>
```

**Downgrade to earlier version:**
```bash
# Get version history first
nipyapi --profile <profile> ci get_flow_versions --process_group_id <pg_id>

# Then switch to the desired version
nipyapi --profile <profile> ci change_flow_version --process_group_id <pg_id> --target_version <older_commit_sha>
```

### Step 6: Review and Re-apply Modifications

For each modification in the saved list:

1. **Check if component still exists** - The version change may have renamed or removed it
2. **Compare values:**
   - What is the value in the new version?
   - What was your modified value?
3. **Ask the user:** "Do you want to re-apply this modification?"

**Example interaction:**

```
Modification 1 of 2:
  Component: FetchData (Processor)
  Change: Run Schedule
  - New version value: 1 min
  - Your previous value: 5 sec

Do you want to re-apply this change? (yes/no/skip all)
```

### Step 7: Apply Approved Modifications

```python
import nipyapi

nipyapi.profiles.switch('<profile>')

# Example: Re-apply scheduling change
proc = nipyapi.canvas.get_processor('<processor_id>', identifier_type='id')
config = nipyapi.nifi.ProcessorConfigDTO(scheduling_period="5 sec")
nipyapi.canvas.update_processor(proc, update=config, auto_stop=True)
```

### Step 8: Verify

```bash
nipyapi --profile <profile> ci get_status --process_group_id <pg_id>
```

## Common Modification Types

| Type | How to Re-apply |
|------|-----------------|
| Run Schedule Changed | `ProcessorConfigDTO(scheduling_period="X")` |
| Concurrent Tasks Changed | `ProcessorConfigDTO(concurrent_tasks=N)` |
| Component Name Changed | `update_processor(proc, name="...")` |
| Property Value Changed | `prepare_processor_config(proc, {"prop": "value"})` |
| Back Pressure Changed | Update connection settings |

## Handling Issues

### Component Not Found

If a component was renamed or removed in the new version:
- Search by type and approximate name
- Ask the user to identify the equivalent component
- Skip if the modification is no longer applicable

### Value Already Matches

If the new version already has the same or better value:
- Show both values to the user
- Let them decide if the modification is still needed

### Batch Apply

If the user says "apply all", proceed without individual confirmation.

## Related References

- `references/ops-version-control.md` - Commit changes, view history, switch versions
- `references/ops-layout.md` - Canvas organization (layout changes are tracked modifications)
