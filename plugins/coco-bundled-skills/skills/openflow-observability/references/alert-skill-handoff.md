---
name: openflow-observability-alert-skill-handoff
description: Handoff contract from Openflow Observability troubleshooting to Alert skill.
---

# Alert Skill Handoff

Use this reference when a customer asks to set up alerts during or after Openflow troubleshooting.

## Handoff Workflow

1. Confirm the transition briefly:
   > "Understood - I'll set up OpenFlow monitoring alerts next."
2. Invoke the `alert` skill object.
3. Route through the Alert router based on customer intent:
   - create/setup/change alert -> delegate to `alert-create-alter`
   - troubleshoot existing alert firing/failure/delivery issues -> delegate to `alert-troubleshoot`

If the customer declines alert setup, continue troubleshooting and do not repeat the nudge in the same session.

## Carryover Contract

Carryover differs by routed alert intent:

### Create/setup/change alert (`alert-create-alter`)

Carry these items when available:

- monitoring intent to prioritize (for example: no data, replication failure, high CPU, high queued count/backpressure, runtime high error rate)
- notification preference if already stated (`EMAIL` or `WEBHOOK`)
- schedule preference if already stated
- alert naming preference if already stated
- `deployment_id` (optional scope hint)
- `runtime_name` (optional scope hint)
- `connector_type` (optional scope hint)
- `error_message` (optional context)
- `event_table` (advisory only; `alert-create-alter` must still discover the event table via its mandatory setup flow)

Do not pass `time_window` for create/setup handoff.

### Troubleshoot existing alert (`alert-troubleshoot`)

Carry these fields when available from the current troubleshooting context:

- `event_table`
- `deployment_id`
- `runtime_name`
- `connector_type`
- `error_message`
- `time_window`
- alert name (if known)

Do not block alert setup/troubleshooting when fields are missing. Pass known context and continue with Alert skill defaults.

## Canonical Ownership

For shared handoff semantics, align with the canonical OpenFlow handoff reference:
`data-engineering/openflow/references/alert-skill-handoff.md`.

This observability handoff is canonical only for troubleshooting-specific carryover shaping
(including create-vs-troubleshoot carryover split and observability-context fields).
