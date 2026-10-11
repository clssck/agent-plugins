# Investigation Ledger Template

Use one file if convenient, but preserve the logical boundary between subject state and investigation state. Delete unused rows rather than filling them with placeholders.

## Header

- **Investigation:**
- **Objective:**
- **Done when:**
- **Scope:**
- **Constraints / approvals:**
- **Started:**
- **Last updated:**
- **Coordinator:**

## Subject Ledger

### Entities

| ID | Entity or artifact | Role / boundary | Evidence |
|---|---|---|---|
| S-001 |  |  | E-001 |

### Claims

| ID | Subject | Claim | Status | Evidence | Last checked |
|---|---|---|---|---|---|
| C-001 | S-001 |  | observed / inferred / disputed / disproved | E-001 |  |

Rules:

- `observed` requires direct evidence. A user report is valid evidence with source `user report`; note whether it was independently reproduced.
- `inferred` cites the evidence that motivated it and stays inferred until a direct discriminator runs.
- When a newer claim supersedes an older one, retain both and record the relationship in the decision log.

## Evidence Registry

| ID | Source | Exact locator | Time / version / scope | Decisive observation | Produced by |
|---|---|---|---|---|---|
| E-001 | command, file, test, user report, document | path:line, URL, artifact, command output range |  |  | P-001 |

An evidence record describes what was observed, not why it happened. Keep bulky output in the cited artifact. A negative result is bounded by its recorded input, time, version, environment, and scope; never promote it to a universal claim.

## Contradictions

| ID | Conflicting claims / evidence | Possible boundary difference | Next discriminator | Status |
|---|---|---|---|---|
| X-001 | C-001 vs E-002 | time / version / environment / scope / source |  | open / resolved |

When resolving a contradiction, cite the deciding evidence and update every affected claim.

## Investigation Ledger

### Branches

| ID | Parent / origin | Question or hypothesis | State | Owner | Evidence | Next / predicate |
|---|---|---|---|---|---|---|
| B-001 | objective |  | open |  |  | next probe |
| B-002 | B-001 from E-001 |  | deferred |  | E-001 | `wake_when:` observable condition |

Allowed states: `open`, `active`, `blocked`, `deferred`, `resolved`, `disproved`, `exhausted`, `superseded`.

For `blocked`, write both `blocked_by` and `unblock_when`. For `deferred`, write `wake_when`. For `superseded`, link the replacement branch. For terminal states, cite the conclusion or residual uncertainty and evidence.

A chosen branch without an accepted current owner remains `open`; write `selected_next` and its prepared probe in the final column. Move it to `active` only when a named worker accepts ownership.

### Probe Log

| ID | Branch | Action | Expected discriminator | Observed outcome | Evidence | Interpretation |
|---|---|---|---|---|---|---|
| P-001 | B-001 |  | If A, support H1; if B, weaken H1 |  | E-001 | claim / branch updates |

Write the expected discriminator before running the probe. A tool failure is not evidence about the subject unless the failure itself is the subject.

### Frontier

- **Active:** named current owner, or `none`
- **Selected next:** open branch + prepared probe when no worker has accepted it
- **Open:**
- **Deferred:** branch + `wake_when`
- **Blocked:** branch + `blocked_by` + `unblock_when`
- **Terminal:** resolved / disproved / exhausted / superseded branches

After every evidence merge, check deferred and blocked predicates before choosing a new open branch.

## Decision Log

| Time | Evidence / branch | Decision and reason | Records changed |
|---|---|---|---|
|  |  |  |  |

Record decisions that change priority, scope, claim status, or branch state. Do not duplicate the probe log.

## Current State

- **Done condition status:**
- **Outcome:** resolved / unresolved / inconclusive
- **Stop reason:** done_condition_met / external_prerequisite / frontier_exhausted / scope_or_risk_limit / budget_limit
- **Best supported conclusion:**
- **Residual uncertainty:**
- **One best next action:**
