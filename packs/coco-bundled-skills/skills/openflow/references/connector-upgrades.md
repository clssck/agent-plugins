---
name: openflow-connector-upgrades
description: Upgrade Openflow connectors to newer versions. Use for identifying stale connectors and executing upgrade workflows.
---

# Connector Upgrades

Identify stale connectors, check available versions, and execute upgrades.

**Note:** These operations modify service state. Apply the Check-Act-Check pattern from `references/core-guidelines.md`.

## Scope

This reference covers:
- Identifying stale connectors
- Upgrade workflow with baseline capture and validation
- Troubleshooting post-upgrade issues

For local modifications during upgrade, see `references/ops-tracked-modifications.md`.

---

## Identifying Stale Connectors

### List All Connectors with Version State

```bash
nipyapi --profile <profile> ci list_flows
```

| Field | Meaning |
|-------|---------|
| `state` | `UP_TO_DATE`, `STALE`, `LOCALLY_MODIFIED`, `SYNC_FAILURE` |
| `current_version` | Currently deployed version |
| `stale_count` | Number with available updates |

**`STALE`** means a newer version is available.

### Include Nested Process Groups

```bash
nipyapi --profile <profile> ci list_flows --descendants
```

---

## Checking Available Versions

```bash
REGISTRY_ID="<connector-registry-id>"
nipyapi --profile <profile> versioning list_git_registry_flow_versions "$REGISTRY_ID" "connectors" "<flow-name>"
```

---

## Executing an Upgrade

Upgrades require three phases: **Preparation**, **Execution**, **Validation**.

### Phase 1: Preparation

**Check for local modifications:**

```bash
nipyapi --profile <profile> ci list_flows
```

**CRITICAL:** If state is `LOCALLY_MODIFIED` or `LOCALLY_MODIFIED_AND_STALE`:

**STOP.** Load `references/ops-tracked-modifications.md` immediately. That reference handles capture, revert, upgrade, and re-apply. Do not proceed here.

**Only continue if state is `STALE` (not `LOCALLY_MODIFIED`).**

**Capture baseline:**

```bash
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
```

Record these values for comparison:
- `running_processors`
- `stopped_processors` (should be 0)
- `invalid_processors`
- `bulletin_errors`

Record:
- `running_processors`
- `stopped_processors`
- `invalid_processors`
- `bulletin_errors`

### Phase 2: Execution

**Upgrade to latest:**

```bash
nipyapi --profile <profile> ci change_flow_version --process_group_id "<pg-id>"
```

**Upgrade to specific version:**

```bash
nipyapi --profile <profile> ci change_flow_version --process_group_id "<pg-id>" --version 5
```

### Phase 3: Validation

**Immediately after upgrade:**

```bash
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
```

**Compare to baseline:**

| Metric | Expected | If Different |
|--------|----------|--------------|
| `running_processors` | Same as baseline | See troubleshooting |
| `stopped_processors` | Same as baseline | See troubleshooting |
| `invalid_processors` | 0 | Check controller config |
| `bulletin_errors` | 0 | Check bulletins |

**Success criteria:**
- Processor counts match baseline
- No new `bulletin_errors`
- No `invalid_processors`

---

## Troubleshooting

### Processors Stopped After Upgrade

**Cause:** Upgrade may stop processors without clean restart.

**Solution:** Perform stop/start cycle:

```bash
# Full stop
nipyapi --profile <profile> ci stop_flow --process_group_id "<pg-id>" --disable_controllers

# Wait for threads to terminate
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
# Repeat until active_threads=0

# Restart
nipyapi --profile <profile> ci start_flow --process_group_id "<pg-id>"

# Verify
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
```

### SYNC_FAILURE State

**Cause:** Registry communication issue or local modifications conflict.

**Solution:**

1. Check for local modifications
2. If modified, revert: `nipyapi ci revert_flow --process_group_id "<pg-id>"`
3. Retry upgrade

### Upgrade Fails with Conflict

**Cause:** Local modifications conflict with upstream changes.

**Solution:**

1. Revert local changes
2. Upgrade
3. Re-apply customizations

### Controller Services Invalid

**Cause:** New version requires additional configuration.

**Solution:**

1. Find invalid controllers:
   ```bash
   nipyapi --profile <profile> canvas list_all_controllers "<pg-id>"
   ```

2. Check validation errors and fix configuration

### Connector Still Broken After Upgrade

**Cause:** The connector may have had incomplete configuration before the upgrade (missing parameters, disabled controllers, etc.).

**Solution:** Use the deployment workflow in `references/connector-main.md` as a validation checklist. Work through each step to verify it is complete:

1. Network Access (SPCS only)
2. Deploy (already done)
3. Configure Parameters
4. Enable Controller Services
5. Start and Validate

This will identify which step was incomplete. Common issues:
- **High invalid processor count (30+)** - Usually means parameters were never configured
- **Disabled controllers** - Parameters or assets may be missing
- **Verification failures** - Check `nipyapi ci verify_config` output

---

## Proactive Upgrade Checks

Periodically check for stale connectors:

```bash
nipyapi --profile <profile> ci list_flows
```

If `stale_count` is 0, all connectors are up to date.

---

## Next Step

After upgrade completes and validates, return to `references/connector-main.md` or the calling workflow.

## See Also

- `references/connector-main.md` - Connector workflow overview
- `references/ops-tracked-modifications.md` - Handling local modifications during upgrade
- `references/ops-flow-lifecycle.md` - Stop/start operations
