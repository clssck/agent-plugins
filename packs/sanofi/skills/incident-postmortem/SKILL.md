---
name: incident-postmortem
description: Write or review Sanofi blameless post-mortems for production incidents (severity, UTC timeline, impact, root cause, contributing factors, owned actions). Use when writing a post-mortem, post-incident review (PIR), incident report, RCA, or outage writeup. Not for live response or paging, bug triage, sprint retrospectives, or security scanning (/security).
---

# Incident Post-Mortem

Blameless, evidence-backed post-mortems for production incidents. Output: one Markdown document at `docs/postmortems/YYYY-MM-DD-short-slug.md` (date = incident start). Complements `/security`: that finds vulnerabilities; this records an incident that occurred.

## Workflow

1. Gather facts: dates, impact, affected users/systems, detection path, mitigation, recovery, evidence links. Use `read`/`grep`/`glob` on chat exports, alert history, deploy logs; `ask` for anything not in evidence.
2. Confirm severity against [severity-levels.md](references/severity-levels.md); record live and final severity.
3. Build the UTC timeline forward from before the trigger (avoids hindsight bias); link a source per entry; separate fact from inference.
4. Run root-cause analysis: 5 Whys plus ALL contributing factors (rules below).
5. Capture what went well, what went wrong, where we got lucky.
6. Define action items (required fields below).
7. `write` the document from [post-mortem-template.md](references/post-mortem-template.md).
8. Run the review gate.

Reviewing an existing post-mortem: run the Checklist and the blameless self-check; report each gap with its section.

Process detail, prompts, anti-patterns: [full-guide.md](references/full-guide.md).

## Timestamps

| Name | Meaning |
|---|---|
| Trigger | Deploy or change that started it; record separately |
| Start | First customer impact (often before anyone knew) |
| Detection | Alert fired or report reached responders |
| Acknowledgement | Incident declared / responder engaged |
| Mitigation | Customer impact stopped |
| Resolution | Underlying issue fixed |

TTD = Detection − Start. TTA = Acknowledgement − Detection. TTM = Mitigation − Detection. TTR = Resolution − Start. Header, summary, impact, and timeline MUST agree.

- MUST state both endpoints next to every duration. NEVER write a bare "MTTR": it means repair, recovery, respond, or resolve depending on the source.
- NEVER claim a reliability trend from one incident or from MTTx averages over a few incidents. Report this incident's durations only.

## Severity

- SEV1/SEV2: post-mortem REQUIRED within 5 business days of incident closure.
- SEV3: optional; recommend one when a trigger in [severity-levels.md](references/severity-levels.md#sev3--moderate) applies.
- Check every SEV1 criterion independently; security or compliance impact makes any size SEV1.
- NEVER classify down to dodge the deadline.

## Root Cause

- Trigger (proximate cause) ≠ root cause. Root cause = the point in the chain where a change prevents the whole class of incident, not just this occurrence.
- NEVER accept "human error" as a cause; ask why the action looked reasonable and what let it reach production.
- Dependency or vendor failure: compare with the dependency's SLO or agreed expectation. Breached → their fix, plus your resilience review. Within it → your service's resilience gap is the root cause. NEVER stop at "AWS/vendor outage".
- Not determined: write `Undetermined`, state what evidence is missing, and add a `detect` item for the observability gap. NEVER guess.

## Action Items

Every item MUST have:

| Field | Rule |
|---|---|
| Owner | Named person; NEVER a role, rotation, or team |
| Deadline | Absolute `YYYY-MM-DD` |
| Tracking link | Real issue ID |
| Priority | P0, P1, P2 |
| Type | `prevent`, `detect`, `mitigate`, `process`, `documentation` |

- Unknown owner or link: write `UNASSIGNED` or leave blank; NEVER invent. The document stays **Draft**.
- Include at least one `detect` item AND at least one `prevent`/`mitigate` item aimed at the root cause, not only the trigger.
- Assign different priorities so the order of work is clear; NOT everything P0.
- Wording MUST be actionable (starts with a verb), specific (scope stated), bounded (clear done-state):

| Bad | Good |
|---|---|
| Investigate monitoring for this scenario. | Add alert when `/checkout` 5xx > 1% for 5 min. |
| Fix the issue that caused the outage. | Handle missing `pricing_context.region` in `CartHydrator` without throwing. |
| Make sure engineers check the schema before deploying. | Add CI pre-merge check that parses schema changes. |
| Train the team on rollbacks. | Write and test the `orders-api` rollback runbook. |

- REJECT actions that depend on people "being careful" or on training alone; change the system.
- Record actions considered but not pursued, with the reason.
- Optional tracker skeleton: [action-items-header.md](assets/action-items-header.md).

## Language

- MUST be blameless; read [blameless-language.md](references/blameless-language.md) before final drafting.
- NEVER name a person as a cause.
- NEVER invent timeline entries, owners, or numbers. Label estimates `est.` with their method; write `unknown` when there is no basis.
- NEVER use animated or judgemental wording ("ridiculous", "careless", "!!!"); state verifiable data.
- NEVER turn the post-mortem into a runbook.

## Review Gate

- Complete only when no action item is `UNASSIGNED` and each has owner, deadline, tracking link.
- SEV1/SEV2 inside the 5-day window, or the slip recorded as a `process` action item.
- Circulate to responders and the IC's manager; SEV1 also goes to the engineering leadership channel.

## Checklist

- Live and final severity recorded; Incident ID and IC present.
- Timeline UTC with detection, acknowledgement, mitigation, resolution; each entry sourced.
- Impact quantified (users, requests, duration, revenue/data/compliance) or marked `unknown`.
- Every duration states its endpoints; metrics consistent across header, summary, impact, timeline.
- Root cause has 5 Whys, contributing factors, a category, and is not "human error" or a bare vendor fault.
- Went well / went wrong / got lucky filled.
- Action items actionable, specific, bounded; at least one `detect` and one `prevent`/`mitigate`.
- Blameless wording; action items complete or Draft.
