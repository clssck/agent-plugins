---
name: openflow-ops-status-check
description: Quick status checks for Openflow flows. Primary tier reference for listing flows, checking health, and basic start/stop. For advanced lifecycle operations, see ops-flow-lifecycle.md.
---

# Status Check

Quick health checks and basic control for deployed flows. This is the Primary tier reference for everyday status operations.

**Surface / generation scope:** this reference uses the NiFi API (nipyapi) and covers **Gen1 / NiFi-canvas** flows on the **CLI/Desktop** surface. On the **Snowsight (SQL-only)** surface, or for **Gen2 / SQL-managed** connectors, use `references/ops-status-check-sql.md` for health/status (and it routes log/metric diagnosis to the `openflow-observability` skill). nipyapi is not available in Snowsight.

**For advanced operations** (force stop, purge, delete, controller management): Load `references/ops-flow-lifecycle.md`

---

## List Deployed Flows

See what's deployed on the canvas.

**Run exactly** (substitute `<profile>` from session):

```bash
nipyapi --profile <profile> ci list_flows
```

**Filter to names only:**

```bash
nipyapi --profile <profile> ci list_flows | jq -r '.process_groups[].name'
```

**Summary with status:**

```bash
nipyapi --profile <profile> ci list_flows | jq '.process_groups[] | {name, id, running: .running_count, stopped: .stopped_count}'
```

---

## Check Flow Health

Get status for a specific flow.

**Run exactly** (substitute `<profile>` and `<pg-id>`):

```bash
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
```

### Interpreting Status

| Field | Healthy Value | If Not |
|-------|---------------|--------|
| `running_processors` | > 0 | Flow not started or all stopped |
| `stopped_processors` | 0 | Some processors stopped (may be intentional) |
| `invalid_processors` | 0 | Configuration errors - check parameters |
| `bulletin_errors` | 0 | Errors occurred - see Quick Bulletin Check |
| `bulletin_warnings` | 0 | Warnings - may need attention |
| `queued_flowfiles` | Low or draining | High + not draining = bottleneck |
| `active_threads` | 0 when stopped | Threads still running after stop |

### Quick Health Assessment

```
Status shows bulletin_errors > 0?
  → Check bulletins (see below)

Status shows invalid_processors > 0?
  → Parameters misconfigured - load ops-parameters-main.md

Status shows running_processors = 0 but should be running?
  → Flow stopped - use Start Flow below

Status shows high queued_flowfiles not draining?
  → Downstream bottleneck - load ops-flow-investigation.md
```

### Version State Check

When listing flows, also check version state. Flag these conditions to the user:

| State | Concern | Action |
|-------|---------|--------|
| `LOCALLY_MODIFIED` | Uncommitted changes exist | Ask if intentional; recommend commit or revert |
| `LOCALLY_MODIFIED_AND_STALE` | Local changes + newer version available | Warn user; recommend resolving before operations |
| `STALE` | Newer version available | Inform user; consider upgrade |
| No version info / untracked | Flow not under version control | Flag as risk; changes cannot be tracked or reverted |

**Why this matters:** Novice users may not realise their flow is untracked or has drifted from the registry. Operations on unversioned flows are harder to recover from. All Snowflake Connectors should remain in version control or the agent cannot know what modifications might be causing errors.

---

## Quick Bulletin Check

When `bulletin_errors` or `bulletin_warnings` > 0, see what's wrong.

**Run exactly** (substitute `<profile>` and `<pg-id>`):

```bash
nipyapi --profile <profile> bulletins get_bulletin_board --pg_id "<pg-id>"
```

**Note:** Bulletins persist for 5 minutes after the error. Check timestamps to ensure you're looking at current issues.

For detailed bulletin investigation (filtering, patterns, clearing): Load `references/ops-bulletins.md`

---

## Start Flow

Start a stopped flow.

**Run exactly** (substitute `<profile>` and `<pg-id>`):

```bash
nipyapi --profile <profile> ci start_flow --process_group_id "<pg-id>"
```

**Verify after starting:**

```bash
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
```

Expect: `running_processors` > 0, `bulletin_errors` = 0

---

## Stop Flow

Stop a running flow (processors only, controllers stay enabled for quick restart).

**Run exactly** (substitute `<profile>` and `<pg-id>`):

```bash
nipyapi --profile <profile> ci stop_flow --process_group_id "<pg-id>"
```

**Verify after stopping:**

```bash
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
```

Expect: `stopped_processors` > 0, `running_processors` = 0

---

## When to Load Other References

| Situation | Load |
|-----------|------|
| Need to force stop stuck threads | `ops-flow-lifecycle.md` |
| Need to purge queued data | `ops-flow-lifecycle.md` |
| Need to delete a flow | `ops-flow-lifecycle.md` |
| Need to enable/disable controllers only | `ops-flow-lifecycle.md` |
| Investigating why data isn't flowing | `ops-flow-investigation.md` |
| Bulletins show specific errors to resolve | `ops-bulletins.md` |
| Invalid processors need parameter fixes | `ops-parameters-main.md` |

---

## Command Reference

All commands below are **exact** - substitute `<profile>` and `<pg-id>` only.

| Operation | Command |
|-----------|---------|
| List flows | `nipyapi --profile <profile> ci list_flows` |
| Get status | `nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"` |
| Get bulletins | `nipyapi --profile <profile> bulletins get_bulletin_board --pg_id "<pg-id>"` |
| Start flow | `nipyapi --profile <profile> ci start_flow --process_group_id "<pg-id>"` |
| Stop flow | `nipyapi --profile <profile> ci stop_flow --process_group_id "<pg-id>"` |
