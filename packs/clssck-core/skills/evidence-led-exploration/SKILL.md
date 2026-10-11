---
name: evidence-led-exploration
description: Use for ambiguous debugging/research, evidence ledgers, and handoffs; not single lookups.
---

# Evidence-Led Exploration

Keep facts about the subject separate from the history of exploring it. Short investigation → compact inline ledger; likely context loss, branching, or handoff → persist a task-owned artifact. Reuse the project's notes location when one exists. NEVER create hidden global state.

Start from [the ledger template](references/investigation-ledger.md). Worker or session boundary → [the handoff packet](references/handoff-packet.md).

## Activate Deliberately

You SHOULD activate when at least one condition holds:

- Several explanations remain plausible; next action not obvious.
- Work will branch, span sessions, or involve multiple agents.
- Earlier attempts, contradictions, or provenance MUST survive context loss.
- Deferred leads need to wake when later evidence changes their value.

NEVER use for a single lookup, a known linear procedure, or an already-established next step.

Domain skill defines the execution method? It wins. Use this skill only for ledger structure, branch management, contradictions, and handoff; NEVER run a second competing loop.

## Invariants

- Every claim MUST be evidence-linked or explicitly `inferred`; NEVER let repetition turn an inference into fact.
- Record a failed probe when it rules out an explanation, narrows scope, or prevents duplicate work. Negative evidence applies only to the tested input, time, version, environment, and scope.
- Three probes of one strategy with no new information = default exhaustion signal: change approach or close the branch unless evidence justifies another attempt.
- Keep raw output in its artifact; the ledger stores the exact locator and only the decisive observation.
- NEVER overwrite conflicting evidence. Record the contradiction and the next observation that could distinguish the accounts.
- One active branch per worker; additional leads stay `open` or `deferred`.
- A branch MUST record its parent and origin; derived work stays traceable to the evidence or branch that created it.
- Investigation NEVER widens authorization. Preserve the task's scope, safety constraints, and mutation approvals.

## Maintain Two Ledgers

### Subject ledger — what is known

Track entities, components, artifacts, states, relationships, and claims about the thing being investigated. Claims use one status:

- `observed`: directly supported by cited evidence;
- `inferred`: best current explanation, not directly observed;
- `disputed`: credible evidence conflicts;
- `disproved`: evidence rules the claim out.

### Investigation ledger — how it is being learned

Track questions, hypotheses, branches, probes, outcomes, dependencies, owners, and next actions. NEVER place speculative explanations in the subject ledger as observed state.

Both ledgers share stable IDs for evidence, claims, branches, and probes. Append or supersede records; NEVER renumber them.

## Exploration Loop

1. **Frame** — state the objective, observable done condition, scope, constraints, and current unknowns.
2. **Inventory** — seed the subject ledger from available evidence; label gaps and inferences.
3. **Branch** — state one question or hypothesis, its origin, and the outcomes that would distinguish it.
4. **Choose** — SHOULD pick the action with the strongest objective relevance and discriminating power, then the lowest risk, irreversibility, and cost. NEVER invent numeric scores.
5. **Probe** — run the smallest action that can change the decision. Record expected outcomes before acting, and change one material variable at a time so the result is interpretable.
6. **Ingest** — create an evidence record with source, locator, time or version, scope, and decisive observation.
7. **Reconcile** — update claim status, record contradictions, and transition the branch.
8. **Wake** — re-evaluate every deferred lead whose `wake_when` predicate may now be true.
9. **Continue or hand off** — choose the next frontier item, stop on the done condition, or emit a handoff packet.

## Branch Lifecycle

| State | Meaning | Required field |
|---|---|---|
| `open` | Eligible but not selected | question or hypothesis |
| `active` | Current worker owns the next probe | owner and next probe |
| `blocked` | Cannot proceed until an external prerequisite arrives | `blocked_by` and observable `unblock_when` |
| `deferred` | Intentionally parked because another result should be checked first | observable `wake_when` |
| `resolved` | The branch answered its question with evidence | conclusion and evidence IDs |
| `disproved` | Its hypothesis conflicts with evidence | refuting evidence IDs |
| `exhausted` | Reasonable discriminators produced no answer or no safe probe remains | attempts and residual uncertainty |
| `superseded` | Replaced by a better-scoped branch without erasing history | replacement branch ID and reason |

Normal transitions are `open -> active -> terminal/blocked/deferred`; `blocked` and `deferred` return to `open` when their predicate becomes true. Reopen a terminal branch only for new contradictory evidence, retaining the previous conclusion and transition reason.

Ownership is literal. A branch becomes `active` only after its named current worker accepts it, even if the first probe has not run. At handoff, a chosen branch without an accepted owner stays `open`; mark it `selected_next`, include its prepared probe, and leave the active frontier empty. The recipient transitions it to `active` when accepting ownership. NEVER use a placeholder owner such as “next worker.”

A wake condition MUST be testable: “when the deployment version is known” or “when evidence shows the request reached the origin,” not “later” or “if useful.”

Required confirmation prohibited, unavailable, or outside scope? Keep the claim `inferred` and name the unrun check in the handoff.

## Contradictions

For each conflict, cite both evidence sets, identify whether they differ by time, version, environment, scope, or source, and state one next discriminator. Until resolved, mark affected claims `disputed`; NEVER choose the preferred story by intuition.

## Parallel Workers

Give each worker one branch, an immutable snapshot of relevant subject records, explicit scope, and a requested return format. Workers return evidence and proposed ledger deltas; they NEVER silently rewrite shared conclusions. The coordinator merges deltas serially, records conflicts, wakes dependent leads, and prevents duplicate probes unless independent reproduction is intentional.

## Stop and Handoff

Stop when the observable done condition is met, all useful branches are terminal, the next step requires an external prerequisite, or the remaining probes exceed scope or risk. Record the outcome separately from why work stopped: `resolved / unresolved / inconclusive` ≠ `done_condition_met / external_prerequisite / frontier_exhausted / scope_or_risk_limit / budget_limit`. Before stopping, you MUST produce a [handoff packet](references/handoff-packet.md) with evidence-linked facts, contradictions, branch states, artifacts, and exactly one best next action.

## Checklist

- Objective and done condition are observable.
- Subject and investigation state are separate.
- Claims cite evidence or say `inferred`.
- Failed probes and contradictions remain visible.
- Every blocked or deferred branch has an observable predicate.
- One branch is active per worker; merges are serialized.
- Handoff names exhausted paths and one next action.
