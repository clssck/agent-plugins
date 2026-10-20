---
name: evidence-led-exploration
description: Invoke explicitly to run ambiguous debugging, root-cause hunts, and research with an evidence ledger — claims linked to evidence, branches with owners and wake conditions, contradictions kept visible — and emit a handoff packet. Best when several explanations stay plausible, work will branch, span sessions, or fan out to parallel workers, or findings must survive context loss. Not for single lookups or known linear procedures; a domain skill's own method wins.
disable-model-invocation: true
---

# Evidence-Led Exploration

Keeps facts about the subject separate from the history of exploring it. Short investigation → compact inline ledger; likely context loss, branching, or handoff → persist a task-owned artifact in the project's notes location if one exists. NEVER create hidden global state. The failure this prevents: an inference repeated until it reads as fact, a failed probe retried by the next worker, a contradiction resolved by intuition.

Ledger template → [investigation-ledger.md](skill://evidence-led-exploration/references/investigation-ledger.md). Worker or session boundary → [handoff-packet.md](skill://evidence-led-exploration/references/handoff-packet.md).

<instruction>

Use `eval` for the working ledgers: keep subject claims, branches, and probes in Python/JS variables for cheap queries and diffs, and persist the canonical ledger with `write`/`edit` after each merge. Eval state is not durable and subagents have separate kernels; the file is the handoff source. Use `read`/`grep`/`glob` for evidence, `find` when the location or behavior is unknown, `bash` for real binaries, and `artifact://` for bulky output. Use `task`/`workpool` for isolated workers and `wait` for their handles; worker output is at `agent://<id>` and its transcript at `history://<id>`. Use `local://<name>.md` for a shared handoff, `web_search` for external sources (cite URL and access time), `todo` for execution phases, and `ask` for material branch choices; the ledger remains canonical. Memory (`recall`/`reflect`) can seed a hypothesis but never replaces cited evidence. Do not build a custom ledger CLI.

</instruction>

<instruction>

**Use explicitly when ≥1 holds:**

- Several explanations plausible; next action not obvious.
- Work will branch, span sessions, or involve multiple agents.
- Earlier attempts, contradictions, or provenance would be lost with the context.
- Deferred leads need to wake when later evidence changes their value.

**Not for** a single lookup, a known linear procedure, or an established next step. Domain skill defines the execution method → it wins; this skill owns ledger structure, branch management, contradictions, handoff only.

For an authorized penetration test, `pentest-tradecraft` owns scope, the check/finding records, cleanup, and handoff. Use this ledger only for an unresolved investigation branch, never as a replacement for the assessment records.

</instruction>

<critical>

- **Every claim MUST be evidence-linked or `inferred`.** Repetition never promotes an inference to fact.
- **Record a failed probe** when it rules out an explanation, narrows scope, or prevents duplicate work. Negative evidence holds only for the tested input, time, version, environment, scope.
- **Three distinct technique probes under one broader strategy, no new information ⇒ exhaustion:** change strategy or close the branch unless evidence justifies another attempt.
- **Raw output stays in its artifact;** the ledger holds the exact locator + decisive observation.
- **NEVER overwrite conflicting evidence.** Record the contradiction + the observation that could distinguish the accounts.
- **One active branch per worker;** other leads stay `open` or `deferred`.
- **Branches record parent + origin;** derived work traces to the evidence or branch that created it.
- **Investigation NEVER widens authorization.** Task scope, safety constraints, mutation approvals persist.
- **One loop:** NEVER run a second competing exploration loop alongside the owning domain skill.

</critical>

## Two ledgers

|Ledger|Tracks|Rule|
|---|---|---|
|Subject — what is known|Entities, components, artifacts, states, relationships, claims|Claim status: `observed` (cited evidence directly supports) · `inferred` (best current explanation, not observed) · `disputed` (credible evidence conflicts) · `disproved` (evidence rules it out)|
|Investigation — how it is learned|Questions, hypotheses, branches, probes, outcomes, dependencies, owners, next actions|NEVER put speculative explanations in the subject ledger as observed state|

Stable IDs shared across evidence, claims, branches, probes. Append or supersede; NEVER renumber.

<procedure>

1. **Frame:** objective, observable done condition, scope, constraints, current unknowns.
2. **Inventory:** seed the subject ledger from available evidence; label gaps and inferences.
3. **Branch:** one question or hypothesis, its origin, the outcomes that would distinguish it.
4. **Choose:** SHOULD pick strongest objective relevance + discriminating power, then lowest risk, irreversibility, cost. NEVER invent numeric scores.
5. **Probe:** smallest action that can change the decision. Record expected outcomes before acting; change one material variable at a time.
6. **Ingest:** evidence record — source, locator, time or version, scope, decisive observation.
7. **Reconcile:** update claim status, record contradictions, transition the branch.
8. **Wake:** re-evaluate every deferred lead whose `wake_when` may now hold.
9. **Continue or hand off:** next frontier item, stop on the done condition, or emit a handoff packet.

</procedure>

## Branch lifecycle

|State|Meaning|Required field|
|---|---|---|
|`open`|Eligible, not selected|question or hypothesis|
|`active`|Current worker owns the next probe|owner + next probe|
|`blocked`|External prerequisite pending|`blocked_by` + observable `unblock_when`|
|`deferred`|Parked until another result is checked|observable `wake_when`|
|`resolved`|Answered with evidence|conclusion + evidence IDs|
|`disproved`|Hypothesis conflicts with evidence|refuting evidence IDs|
|`exhausted`|Reasonable discriminators gave no answer, or no safe probe remains|attempts + residual uncertainty|
|`superseded`|Replaced by a better-scoped branch, history kept|replacement branch ID + reason|

Transitions: `open → active → terminal | blocked | deferred`; `blocked`/`deferred` → `open` when the predicate holds. Reopen a terminal branch only for new contradictory evidence; keep the previous conclusion + transition reason.

**Ownership is literal.** A branch becomes `active` only after its named current worker accepts it, even before the first probe. At handoff a chosen branch without an accepted owner stays `open`: mark `selected_next`, include its prepared probe, leave the active frontier empty. The recipient moves it to `active` on acceptance. NEVER use a placeholder owner such as "next worker."

**A wake condition MUST be testable:** "when the deployment version is known", "when evidence shows the request reached the origin" — not "later", not "if useful".

Required confirmation prohibited, unavailable, or out of scope → claim stays `inferred`; name the unrun check in the handoff.

<caution>

Cite both evidence sets; identify whether they differ by time, version, environment, scope, or source; state one next discriminator. Mark affected claims `disputed` until resolved. NEVER pick the preferred story by intuition.

</caution>

## Parallel workers

Each worker gets one branch, an immutable snapshot of relevant subject records, explicit scope, a requested return format. Workers return evidence + proposed ledger deltas; NEVER silently rewrite shared conclusions. Coordinator merges deltas serially, records conflicts, wakes dependent leads, blocks duplicate probes unless independent reproduction is intentional. Target traffic still follows the domain skill's budget and one-integration-owner rule; parallel branches do not authorize concurrent probes.

<critical>

Stop when: done condition met · all useful branches terminal · next step needs an external prerequisite · remaining probes exceed scope or risk. Outcome and stop reason are separate fields: `resolved / unresolved / inconclusive` ≠ `done_condition_met / external_prerequisite / frontier_exhausted / scope_or_risk_limit / budget_limit`.

**MUST produce a [handoff packet](skill://evidence-led-exploration/references/handoff-packet.md) before stopping:** evidence-linked facts, contradictions, branch states, artifacts, exactly one best next action; exhausted paths named. Objective and done condition MUST be observable; every blocked or deferred branch carries an observable predicate.

</critical>
