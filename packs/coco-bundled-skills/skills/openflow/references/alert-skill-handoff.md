---
name: openflow-alert-skill-handoff
description: Handoff contract from Openflow workflows to Alert skill after user opt-in.
---

# Alert Skill Handoff

Use this reference when a user accepts OpenFlow alert setup.

## When to Load

Load this reference after an OpenFlow nudge is accepted (Primary, Secondary, or Compound workflow).

## Handoff Workflow

Do not improvise alert SQL in this skill; invoke/delegate through the `alert` skill router only.

1. Confirm the transition briefly:
   > "Understood - I'll set up OpenFlow monitoring alerts next."
2. Invoke the `alert` skill object.
3. Route as create/setup alert intent:
   - Delegate to the `alert-create-alter` path through the alert router.

If the user declines alert setup, continue OpenFlow work and do not repeat the nudge in the same session.

## Carryover Contract

### Required to proceed smoothly

Carry these items into the Alert setup conversation when available:

- User opt-in to create alerts now
- OpenFlow monitoring intent to prioritize (for example: no data, replication failure, high CPU, high queued count/backpressure, runtime high error rate)
- Notification preference if already stated (`EMAIL` or `WEBHOOK`)
- Schedule preference if already stated
- Alert naming preference if already stated

If any item is missing, do not block handoff. Continue with Alert skill defaults and ask follow-up questions only where needed.

## Canonical Ownership

This file is canonical for OpenFlow skill nudge -> alert setup handoff behavior.

The paired troubleshooting handoff in `data-engineering/openflow-observability/references/alert-skill-handoff.md`
should stay aligned on shared handoff semantics (transition confirmation, alert-skill invocation, and router-based delegation),
while keeping observability-specific carryover fields tuned independently.
