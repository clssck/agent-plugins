---
name: incident-postmortem
description: "Write or review blameless, evidence-backed incident post-mortems. Use when asked for a postmortem, post-incident review, incident report, RCA, root-cause analysis, outage writeup, incident timeline, 5 Whys, SEV1/SEV2 follow-up, or action items after an outage, data loss, or security incident. Not for live triage or paging, bug triage, or sprint retrospectives; vulnerability finding → /security instead."
---

# Incident Post-Mortem

Blameless, evidence-backed record of a production incident that already happened: severity, UTC timeline, impact, root cause, contributing factors, owned action items. Output: one Markdown document at `docs/postmortems/YYYY-MM-DD-short-slug.md` (date = incident **start**, not authoring date). Governing principle: **timeline before theories, systems before people** — speculation anchored on a wrong fact is worse than no theory, and a post-mortem with no durable change (monitor, runbook, code, process) has failed.

Scope split: `/security` finds vulnerabilities; this skill records an incident that occurred. Live response, paging, bug triage, sprint retrospectives → out of scope.

<critical>

- **MUST be blameless**; read [blameless-language.md](skill://incident-postmortem/references/blameless-language.md) before final drafting. NEVER name a person as a cause.
- **NEVER invent timeline entries, owners, or numbers.** Estimates labelled `est.` with method; no basis → `unknown`.
- **NEVER animated or judgemental wording** ("ridiculous", "careless", "!!!"); state verifiable data.
- **NEVER turn the post-mortem into a runbook.**
</critical>

<procedure>

1. **Gather facts** — dates, impact, affected users/systems, detection path, mitigation, recovery, evidence links. `read`/`grep`/`glob` over chat exports, alert history, deploy logs; `ask` for anything not in evidence.
2. **Confirm severity** against [severity-levels.md](skill://incident-postmortem/references/severity-levels.md); record live and final severity.
3. **Build the UTC timeline** forward from before the trigger (avoids hindsight bias); source link per entry; fact separate from inference.
4. **Root-cause analysis** — 5 Whys plus ALL contributing factors.
5. **Went well / went wrong / got lucky.**
6. **Action items** with required fields.
7. **`write`** the document from [post-mortem-template.md](skill://incident-postmortem/references/post-mortem-template.md).
8. **Review gate.** Run [Verification](#verification) below and the blameless self-check. SEV1/SEV2 → also spawn a `task` agent (children start blank) with the file path, `blameless-language.md`, and the [Verification](#verification) list; it returns gaps by section. Fix them before circulating. Spawning unavailable → say the check was not independent.

Process detail, interview prompts, anti-patterns, sources: [full-guide.md](skill://incident-postmortem/references/full-guide.md).
</procedure>

## Verification

<critical>

Document is complete only when every line holds:

- Live and final severity recorded; Incident ID and IC present.
- Timeline UTC with detection, acknowledgement, mitigation, resolution; each entry sourced.
- Impact quantified (users, requests, duration, revenue/data/compliance) or marked `unknown`.
- Every duration states its endpoints; metrics consistent across header, summary, impact, timeline.
- Root cause: 5 Whys, contributing factors, category; not "human error" or bare vendor fault.
- Went well / went wrong / got lucky filled.
- Action items actionable, specific, bounded; ≥1 `detect` and ≥1 `prevent`/`mitigate`; blameless wording.
- No item `UNASSIGNED`; each has owner, deadline, tracking link — else status stays Draft.
- SEV1/SEV2 inside the 5-day window, or the slip recorded as a `process` action item.

**Circulation is a proposed handoff**: name the intended audience (responders and the IC's manager; SEV1 also the engineering leadership channel) and ask the user to send. Send or publish only when the user explicitly authorized it and supplied the actual destination (channel, list, or recipients) — never infer one. Draft-only and review-only requests end at the document and the proposal.
</critical>

## Reviewing an existing post-mortem

Run [Verification](#verification) above plus the blameless self-check in [blameless-language.md](skill://incident-postmortem/references/blameless-language.md#self-check); report each gap with its section.

## Timestamps

| Name | Meaning |
|---|---|
| Trigger | Deploy or change that started it; recorded separately |
| Start | First customer impact (often before anyone knew) |
| Detection | Alert fired or report reached responders |
| Acknowledgement | Incident declared / responder engaged |
| Mitigation | Customer impact stopped |
| Resolution | Underlying issue fixed |

TTD = Detection − Start · TTA = Acknowledgement − Detection · TTM = Mitigation − Detection · TTR = Resolution − Start. Header, summary, impact, timeline MUST agree.

- **MUST state both endpoints beside every duration.** NEVER a bare "MTTR": means repair, recovery, respond, or resolve depending on source.
- **NEVER claim a reliability trend** from one incident or MTTx averages over a few incidents; report this incident's durations only.

## Severity

| Level | Post-mortem |
|---|---|
| SEV1 / SEV2 | REQUIRED within 5 business days of incident closure |
| SEV3 | Optional; recommend when a trigger in [severity-levels.md](skill://incident-postmortem/references/severity-levels.md#sev3--moderate) applies |

- **Check every SEV1 criterion in the [severity-levels.md](skill://incident-postmortem/references/severity-levels.md#decision-flow) decision flow independently**; any one met makes it SEV1 whatever the outage size, including data loss, corruption, or exposure, a breach or credible suspected breach, and a regulatory-reporting failure. Security or compliance effects meeting none of them follow the rest of the flow; an ambiguous result takes the higher severity.
- **NEVER classify down** to dodge the deadline.

## Root cause

- **Trigger (proximate cause) ≠ root cause.** Root cause: point in the chain where a change prevents the whole class of incident, not just this occurrence.
- **NEVER accept "human error"**; ask why the action looked reasonable and what let it reach production.
- **Dependency/vendor failure** → compare with its SLO or agreed expectation. Breached → their fix + your resilience review. Within → your service's resilience gap is the root cause. NEVER stop at "AWS/vendor outage".
- **Not determined** → write `Undetermined`, state missing evidence, add a `detect` item for the observability gap. NEVER guess.

## Action items

Every item MUST have:

| Field | Rule |
|---|---|
| Owner | Named person; NEVER a role, rotation, or team |
| Deadline | Absolute `YYYY-MM-DD` |
| Tracking link | Real issue ID |
| Priority | P0, P1, P2 |
| Type | `prevent`, `detect`, `mitigate`, `process`, `documentation` |

- **Unknown owner or link** → `UNASSIGNED` or blank; NEVER invent. Document stays **Draft**.
- **Coverage:** ≥1 `detect` AND ≥1 `prevent`/`mitigate` aimed at the root cause, not only the trigger.
- **Distinct priorities** so order of work is clear; NOT everything P0.
- **Wording MUST be actionable** (starts with a verb), **specific** (scope stated), **bounded** (clear done-state):

| Bad | Good |
|---|---|
| Investigate monitoring for this scenario. | Add alert when `/checkout` 5xx > 1% for 5 min. |
| Fix the issue that caused the outage. | Handle missing `pricing_context.region` in `CartHydrator` without throwing. |
| Make sure engineers check the schema before deploying. | Add CI pre-merge check that parses schema changes. |
| Train the team on rollbacks. | Write and test the `orders-api` rollback runbook. |

- **REJECT actions relying on people "being careful" or training alone**; change the system.
- **Record actions considered but not pursued**, with reason.
- Optional tracker skeleton: [action-items-header.md](skill://incident-postmortem/assets/action-items-header.md).
