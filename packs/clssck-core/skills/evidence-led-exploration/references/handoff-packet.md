# Exploration Handoff Packet

Use stable ledger IDs. A recipient should be able to resume without reading the full transcript or repeating exhausted work.

## Full Handoff

### Objective

- **Goal:**
- **Done when:**
- **Scope / constraints / approvals:**
- **Current investigation status:** ready / active / blocked / complete
- **Outcome:** resolved / unresolved / inconclusive
- **Stop reason:** done_condition_met / external_prerequisite / frontier_exhausted / scope_or_risk_limit / budget_limit

`ready` means a next branch is selected but no recipient has accepted ownership. It is investigation status, not branch state.

### Evidence-Based State

- **Observed facts:** claim IDs + evidence IDs
- **Current inferences:** claim IDs + supporting evidence IDs
- **Contradictions:** conflict IDs + next discriminator
- **Residual unknowns:**
- **Checks deliberately not run:** check + reason; affected claims remain inferred

### Frontier

- **Active branch:** ID, current owner, question, expected discriminator; write `none` when no current worker owns a probe
- **Selected next branch:** open branch ID + prepared probe + expected discriminator; omit after a recipient accepts it
- **Open branches:** IDs in priority order
- **Deferred branches:** ID + observable `wake_when`
- **Blocked branches:** ID + `blocked_by` + observable `unblock_when`
- **Terminal branches:** resolved, disproved, exhausted, and superseded IDs with evidence

### Artifacts

| Artifact | Exact location | Contents / why it matters |
|---|---|---|
|  |  |  |

Never include secrets in the packet. Name the approved access method or prerequisite instead.

### Resume

- **One best next action:**
- **Why this action:** objective relevance and expected discriminator
- **Command / tool / owner:** if already determined
- **Expected outcomes and resulting transitions:**

A sender never marks a branch `active` for a hypothetical “next worker.” Keep an unowned choice `open` and `selected_next`; the recipient moves it to `active` and names itself as owner when accepting the handoff.

## Worker Delta

Use this smaller packet when a parallel worker returns one scoped branch to a coordinator.

- **Assigned branch and scope:**
- **Probes run:** probe IDs
- **New evidence:** evidence IDs and exact locators
- **Unmerged observations:** raw observation + source; coordinator assigns evidence and claim IDs
- **Proposed claim changes:** claim ID, old -> new status, evidence
- **Proposed branch transition:** old -> new state, reason
- **New leads:** question, origin evidence, proposed state
- **Contradictions found:** both evidence sets and next discriminator
- **Artifacts created:** exact locations
- **Blocked by:** prerequisite and `unblock_when`
- **One recommended next action:**

The coordinator validates and merges this delta. The worker does not declare shared state updated merely because it proposed a change.
