# Post-Mortem Process Guide

Blameless post-mortem for Sanofi incident management. Output: single Markdown document — severity classification, reconstructed timeline, root-cause analysis, action items owned by named people with deadlines.

## Philosophy

- **Blameless.** Focus on systems, processes, missing safeguards; NEVER individuals. Bad outcomes come from weak systems, not bad people.
- **Timeline before theories.** Reconstruct chronologically before explaining. Speculation anchored on a wrong fact is worse than no theory.
- **Lessons > documents.** No durable change (runbook update, monitor added, code fix, process change) ⇒ post-mortem failed.

## Workflow

### 1. Confirm (or revise) severity

Severity is set **during** the incident — it drives paging, war-room activation, comms plan; it cannot wait. The post-mortem **confirms the live classification or deliberately reclassifies** once settled facts (user impact, duration, data/compliance blast radius) are known. Definitions, response SLAs, decision flow: [severity-levels.md](skill://incident-postmortem/references/severity-levels.md).

- **Reclassify up** when settled facts show a larger blast radius (more users, longer duration, data/compliance impact discovered after the fact).
- **Reclassify down** only when measured impact is genuinely smaller than the live call; record the reason. NEVER down to avoid the 5-business-day deadline — real, material impact is SEV2 (or higher) however inconvenient the write-up.
- **No live severity** (incident bypassed declared process) → record a process gap in Contributing Factors; classify now on measured impact.

Record live and final severity (plus reason if they differ) in the document header.

### 2. Identify roles

| Role | Duty |
|---|---|
| Incident Commander (IC) | Owned response, drove decisions, coordinated comms; usually on-call engineer or designated deputy. **Responsible for ensuring the post-mortem is written**, not for writing every section alone |
| Responders | Engineers who diagnosed or remediated |
| Communications lead | SEV1 only; owned customer/stakeholder updates |
| Post-mortem author | Usually the IC; name explicitly so ownership is unambiguous |

Capture all in the header with the **Incident ID**. Reuse the ID from the team's incident tracker (PagerDuty incident ID, ServiceNow ticket, Opsgenie alert ID, Jira incident issue, etc.) so the post-mortem links from the ID responders used in the war room. No tracker → `INC-YYYY-MMDD-NNN` (incident start date + daily sequence number).

### 3. Reconstruct the timeline

Raw sources, in order:

```text
# Incident chat/war room transcript
# Paging/alerting history (PagerDuty, Opsgenie, etc.)
# Deploy history around the incident window
# Monitoring dashboards (screenshot or link)
# Customer support tickets filed during the incident
```

UTC, source links where possible. Entry = timestamp + actor (role, not person, when identity is immaterial) + short factual statement + metric/log search/dashboard link showing provenance. Put commands/queries in the document so others can reproduce. **Do not interpret yet.** Include status/impact changes, key responder actions and decisions.

Impact duration ≠ response duration: impact may start before detection and end before resolution.

Good:

> `14:03 UTC` — Deploy of `orders-api` v2.41.0 completes.
> `14:07 UTC` — Error rate on `/checkout` climbs from 0.1% to 8% (link to dashboard).
> `14:09 UTC` — First customer ticket filed ("Payment fails with 500").

Bad — interpretation and blame:

> `14:07 UTC` — Alice's deploy breaks checkout because she didn't test properly.

Key timestamps — always capture:

| Name | Question |
|---|---|
| Detection | When did an alert fire or a report first reach responders? |
| Acknowledgement | When was the incident declared / on-call paged? |
| Mitigation | When did customer impact stop (root cause may still be unknown)? |
| Resolution | When was the underlying issue fully fixed? |

**Start** = first customer impact; record the triggering deploy/change separately. Impact often starts before responders know ⇒ keep Start separate from Detection.

- **TTD** = Detection − Start
- **TTA** = Acknowledgement − Detection
- **TTM** = Mitigation − Detection
- **TTR** = Resolution − Start

**Durations.** Write both endpoint events beside each duration. "MTTR" covers repair, recover/restore, respond, resolve ⇒ bare "MTTR" ambiguous. Averages of a few incident durations are not evidence of improvement: Google's analysis of incident metrics found MTTx statistics poorly suited to decisions or trend analysis ⇒ report this incident's durations only. TTR above ≠ DORA's "failed deployment recovery time" (recovery only from a deployment that fails and needs immediate intervention); NEVER use interchangeably.

**Hindsight bias.** Start the timeline before the trigger and work forward, not backward from resolution. Include information the team did not have at the time that you wish they had.

### 4. Quantify impact

"Some users were affected" is not impact.

| Field | Content |
|---|---|
| Users affected | Rough count or percentage, plus segment (e.g. "EU paying customers") |
| Requests affected | Count or error rate |
| Duration | Start → mitigation (and separately → resolution if they differ) |
| Revenue / data / compliance | If applicable; unknown ⇒ say so, NEVER guess |

### 5. Root-cause analysis

**5 Whys** is the starting frame, never a single chain. Real incidents are multi-causal ⇒ capture all contributing factors.

```
Q1: Why did /checkout return 500s?          A: Orders-api threw NullPointer on line X.
Q2: Why did the code path hit null?         A: New field not populated for legacy carts.
Q3: Why wasn't that caught in testing?      A: Test fixtures only cover post-migration carts.
Q4: Why didn't the canary catch it?         A: Canary traffic routed only to new accounts.
Q5: Why is canary traffic segmented that way? A: Default router config from 2023 never revisited.
```

**Contributing Factors** are captured separately: conditions that let the trigger cause the outage.

- Alerting gap: error-rate alert threshold was 10% (incident peaked at 8%).
- Runbook gap: no documented rollback for orders-api > v2.40.
- Process gap: deploy approval did not require canary health check.

**Proximate vs root.** Proximate = what directly led to the incident (the trigger). Root = place in the chain where a change prevents the whole class of incident. Keep asking until a system, process, or design gap surfaces; "human error" is never a root cause. Also review the response process itself (collaboration, communication, review), even when it is not a root cause.

**Root-cause categories** — name one; it points to the right action:

| Category | Typical action |
|---|---|
| Bug | Tests, canary, incremental rollout, feature flags |
| Change | Improve change review / change management |
| Scale | Capacity plan; monitor and alert on resource constraints |
| Architecture | Design review; design misaligned with operating conditions |
| Dependency | See below |
| Unknown | Improve observability (logging, monitoring, debugging) so it can be diagnosed |

**Dependency failures.** Compare with the dependency's SLO (internal) or your reasonable expectation (third party; contractual SLAs usually too low to be useful). Breached → dependency owner improves, and you still review whether your service should degrade more gracefully. Within → your service lacks resilience. No SLO or expectation → creating one is an action item.

**Interviewing responders.** Ask "how" and "what", not "who" or "why": What were you focusing on? What differed from what you expected? What options did you consider and why did this one seem best? How did time pressure influence choices? Was there prior work the team chose not to do?

Blameless language throughout: [blameless-language.md](skill://incident-postmortem/references/blameless-language.md).

### 6. What went well / wrong / lucky

Post-mortems are not failure catalogs; call out what worked so it gets reinforced.

| Section | Content |
|---|---|
| Went well | Fast detection, clean rollback, good communication, useful runbook, solid monitoring |
| Went wrong | Gaps, surprises, places where system or process let the team down |
| Got lucky | Near-misses that could have made this worse; lucky outcomes are future incidents waiting to happen |

### 7. Action items

Every item MUST have the fields below. Owner or tracking link unknown → `UNASSIGNED`/blank, NEVER invent, keep the document in Draft.

| Field | Required | Notes |
|---|---|---|
| Description | Yes | Concrete and verifiable |
| Type | Yes | `prevent`, `detect`, `mitigate`, `process`, `documentation` |
| Owner | Yes | Named person, not a team (teams diffuse ownership) |
| Deadline | Yes | Absolute `YYYY-MM-DD`, not "next sprint" |
| Tracking link | Yes | Jira/Linear/GitHub issue ID so progress is visible |
| Priority | Yes | P0/P1/P2 |

**Balance types.** Only `prevent` actions ⇒ brittle: add ≥1 `detect` (catch it sooner) and consider `mitigate` (shrink blast radius on recurrence).

**Wording** MUST be **actionable** (starts with a verb, useful outcome), **specific** (scope stated, in and out), **bounded** (reader can tell when finished).

| Poorly worded | Better |
|---|---|
| Investigate monitoring for this scenario. | Add alerting for all cases where this service returns >1% errors. |
| Fix the issue that caused the outage. | Handle invalid postal code in user address form input safely. |
| Make sure engineer checks the schema parses. | Add automated presubmit check for schema changes. |
| Improve testing / Be more careful with deploys. | Add integration test covering legacy-cart checkout path (test fixture `legacy_cart_v1.json`). Owner: @alice. Deadline: 2026-05-14. ENG-1234. |

Changing human behaviour (training, "be careful") is less reliable than changing systems ⇒ reject actions that only ask people to try harder.

- **Prioritise.** Not everything P0; equal priorities hide what to do first. Large incident → group by theme, one owner per theme.
- **Do not over-ticket.** Tickets only for actions that must be done. Action judged not worth its cost → record in the document with the reason; NEVER drop silently.
- **Closure.** Tickets live in the owning team's backlog (not only the document), labelled with severity and incident ID/date so open post-mortem actions are queryable. Check whether the team or Sanofi unit has an action-item closure policy; none ⇒ flag the gap, NEVER invent a Sanofi deadline. Other organisations' closure SLOs, for reference only: PagerDuty 15 days (SEV1) / 30 days (SEV2) for preventive actions; Atlassian 4 or 8 weeks for priority actions depending on service.

**Action categories** — coverage check; map onto `Type`:

| Question | Type |
|---|---|
| How do we decrease time to accurately detect this failure? | `detect` |
| How do we cut severity or duration when it recurs? | `mitigate` |
| How do we prevent this class of failure? | `prevent` |
| How do we improve the response itself? | `process` |
| What knowledge/runbook was missing? | `documentation` |

≥1 `prevent` or `mitigate` action MUST target the root cause, not only the trigger.

### 8. Write the document

Use [post-mortem-template.md](skill://incident-postmortem/references/post-mortem-template.md) as the exact template. Fill every required section; omit optional sections only when empty — no "TBD" placeholders. File at `docs/postmortems/YYYY-MM-DD-short-slug.md` (create directory if missing); date = incident **start**, not authoring date.

### 9. Review and publish

Reread against [blameless-language.md](skill://incident-postmortem/references/blameless-language.md); run [Verification](skill://incident-postmortem/SKILL.md#verification) in SKILL.md before circulating.

## Anti-patterns

### Naming individuals as causes

```markdown
<!-- BAD -->

Root cause: Alice deployed without checking the canary.

<!-- GOOD -->

Root cause: The deploy process did not require canary health
verification before full rollout. The engineer followed the documented
procedure.
```

### Action items without owners or deadlines

```markdown
<!-- BAD -->

- [ ] Improve deploy safety
- [ ] Add more tests

<!-- GOOD -->

- [ ] Add canary health gate to `deploy.yaml` (block rollout if 5xx >
      baseline+2σ). Owner: @bob. Deadline: 2026-05-21. ENG-1235.
- [ ] Extend orders-api fixture set to cover legacy carts (`test/fixtures/
legacy_cart_v1.json`). Owner: @alice. Deadline: 2026-05-14. ENG-1234.
```

### Timeline with interpretation mixed in

```markdown
<!-- BAD -->

14:07 — Error rate spikes because the new deploy is broken.

<!-- GOOD -->

14:07 — Error rate on /checkout rises from 0.1% to 8% (`<dashboard URL>`).
(Root cause identified later at 15:42.)
```

### Single-cause narratives

Outages are almost always multi-causal; exactly one contributing factor usually means the author stopped looking. Push: "what else had to go wrong for this to happen?"

### "Human error" and bare vendor faults

```markdown
<!-- BAD -->

Root cause: human error during manual config push. / Root cause: AWS outage.

<!-- GOOD -->

Root cause: manual config pushes have no validation or staged rollout, so one
bad value reached all regions. (Category: Change.)
Root cause: orders-api has no fallback for the managed queue; the provider
stayed within our expected availability, but we built no resilience
for it. (Category: Dependency.)
```

## Sources

- Google SRE Book, ch. 15 — [Postmortem Culture: Learning from Failure](https://sre.google/sre-book/postmortem-culture/) (postmortem triggers, blamelessness).
- Google SRE Workbook, ch. 10 — [Postmortem Culture: Learning from Failure](https://sre.google/workbook/postmortem-culture/) (good vs bad postmortem: ownership, tracking, prioritisation, measurable actions, animated language, prompt publication, repeat-incident questions).
- Google — [Incident Metrics in SRE](https://sre.google/resources/practices-and-processes/incident-metrics-in-sre/) (MTTx statistics are poorly suited to decisions or trend analysis).
- PagerDuty — [Postmortem documentation: Step by Step](https://postmortems.pagerduty.com/how_to_write/writing/) (forward timeline, contributing factors vs root cause, actionable/specific/bounded, ticket labels).
- PagerDuty — [Tips for Effective Postmortems](https://postmortems.pagerduty.com/how_to_write/effective_postmortems/) (do/don't list, "human error", "outage" wording).
- PagerDuty — [Accountability](https://postmortems.pagerduty.com/culture/accountability/) (action-item closure policy, ticket labels, involving prioritising leaders).
- Atlassian — [Incident postmortems](https://www.atlassian.com/incident-management/handbook/postmortems) (proximate vs root cause, root-cause categories, dependency analysis, action categories, approvals, priority-action SLOs).
- Atlassian — [Common incident metrics](https://www.atlassian.com/incident-management/kpis/common-metrics) (MTTR has four meanings; MTTA definition).
- DORA — [DORA's software delivery metrics](https://dora.dev/guides/dora-metrics/) (definition of "failed deployment recovery time": recovery from a deployment that fails and needs immediate intervention).
