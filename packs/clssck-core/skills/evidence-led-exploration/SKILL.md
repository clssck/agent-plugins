---
name: evidence-led-exploration
description: Manage open-ended investigations with separate subject and investigation ledgers, evidence-linked claims, explicit branch states, contradiction handling, deferred leads with wake conditions, and compact agent handoffs. Use for ambiguous debugging, research, incident analysis, or multi-agent exploration. Not for a known linear procedure or a single lookup.
---

# Evidence-Led Exploration

Keep facts about the subject separate from the history of exploring it. Use a compact inline ledger for a short investigation; persist a task-owned artifact when context loss, branching, or handoff is likely. Reuse the project's notes location when one exists. Do not create hidden global state.

Start from [the ledger template](references/investigation-ledger.md). For a worker or session boundary, use [the handoff packet](references/handoff-packet.md).

## Activate Deliberately

Use this skill when at least one condition holds:

- several explanations remain plausible and the next action is not obvious;
- the work will branch, span sessions, or involve multiple agents;
- earlier attempts, contradictions, or provenance must survive context loss;
- deferred leads need to wake when later evidence changes their value.

Skip it for a single lookup, a known linear procedure, or a task whose next step is already established.

When a domain skill defines the execution method, it wins. Use this skill only for ledger structure, branch management, contradictions, and handoff; do not run a second competing loop.

## Invariants

- Every claim is either evidence-linked or explicitly `inferred`; never let repetition turn an inference into fact.
- Record a failed probe when it rules out an explanation, narrows scope, or prevents duplicate work. Negative evidence applies only to the tested input, time, version, environment, and scope.
- Three probes of the same strategy with no new information are a default exhaustion signal: change approach or close the branch unless evidence justifies another attempt.
- Keep raw output in its artifact. The ledger stores the exact locator and only the decisive observation.
- Never overwrite conflicting evidence. Record the contradiction and the next observation that could distinguish the accounts.
- Keep one active branch per worker. Additional leads stay `open` or `deferred`.
- A branch records its parent and origin. Derived work must remain traceable to the evidence or branch that created it.
- Investigation never widens authorization. Preserve the task's scope, safety constraints, and mutation approvals.

## Maintain Two Ledgers

### Subject ledger — what is known

Track entities, components, artifacts, states, relationships, and claims about the thing being investigated. Claims use one status:

- `observed`: directly supported by cited evidence;
- `inferred`: best current explanation, not directly observed;
- `disputed`: credible evidence conflicts;
- `disproved`: evidence rules the claim out.

### Investigation ledger — how it is being learned

Track questions, hypotheses, branches, probes, outcomes, dependencies, owners, and next actions. Do not place speculative explanations in the subject ledger as observed state.

Both ledgers share stable IDs for evidence, claims, branches, and probes. Append or supersede records; do not renumber them.

## Exploration Loop

1. **Frame** — state the objective, observable done condition, scope, constraints, and current unknowns.
2. **Inventory** — seed the subject ledger from available evidence; label gaps and inferences.
3. **Branch** — state one question or hypothesis, its origin, and the outcomes that would distinguish it.
4. **Choose** — prefer the action with the strongest objective relevance and discriminating power, then the lowest risk, irreversibility, and cost. Do not invent numeric scores.
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

Ownership is literal. A branch becomes `active` only after its named current worker accepts it, even if the first probe has not run. At handoff, a chosen branch without an accepted owner stays `open`; mark it `selected_next`, include its prepared probe, and leave the active frontier empty. The recipient transitions it to `active` when accepting ownership. Never use a placeholder owner such as “next worker.”

A wake condition must be testable: “when the deployment version is known” or “when evidence shows the request reached the origin,” not “later” or “if useful.”

If required confirmation is prohibited, unavailable, or outside scope, keep the claim `inferred` and name the unrun check in the handoff.

## Contradictions

For each conflict, cite both evidence sets, identify whether they differ by time, version, environment, scope, or source, and state one next discriminator. Until resolved, mark affected claims `disputed`; do not choose the preferred story by intuition.

## Parallel Workers

Give each worker one branch, an immutable snapshot of relevant subject records, explicit scope, and a requested return format. Workers return evidence and proposed ledger deltas; they do not silently rewrite shared conclusions. The coordinator merges deltas serially, records conflicts, wakes dependent leads, and prevents duplicate probes unless independent reproduction is intentional.

## Stop and Handoff

Stop when the observable done condition is met, all useful branches are terminal, the next step requires an external prerequisite, or the remaining probes exceed scope or risk. Record the outcome separately from why work stopped: `resolved / unresolved / inconclusive` is not the same as `done_condition_met / external_prerequisite / frontier_exhausted / scope_or_risk_limit / budget_limit`. Before stopping, produce a [handoff packet](references/handoff-packet.md) with evidence-linked facts, contradictions, branch states, artifacts, and exactly one best next action.

## Checklist

- Objective and done condition are observable.
- Subject and investigation state are separate.
- Claims cite evidence or say `inferred`.
- Failed probes and contradictions remain visible.
- Every blocked or deferred branch has an observable predicate.
- One branch is active per worker; merges are serialized.
- Handoff names exhausted paths and one next action.

## Provenance

Original operational synthesis; no ARTEX source code or prompt text is included. The subject/investigation split was informed by ARTEX v0.3.15 exploration-state design (commit `e6ec56999175509551a1e43a3ee3b053d0941bd9`), reviewed read-only through surviving mirrors after the original repository disappeared.
