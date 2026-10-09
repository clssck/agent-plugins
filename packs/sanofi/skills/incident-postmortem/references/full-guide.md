# Post-Mortem Process Guide

Produces a blameless post-mortem for Sanofi incident management. The output
is a single Markdown document with severity classification, a reconstructed
timeline, root-cause analysis, and action items owned by named people with
deadlines.

## Philosophy

- **Blameless**: focus on systems, processes, and missing safeguards — never
  on individuals. Bad outcomes come from weak systems, not bad people.
- **Timeline before theories**: reconstruct what happened in chronological
  order before trying to explain why. Speculation anchored on a wrong fact
  is worse than no theory.
- **Lessons > documents**. A post-mortem that produces no durable change
  (runbook update, monitor added, code fix, process change) has failed.

## Workflow

### 1. Confirm (or revise) severity

Severity is set **during** the incident — it drives paging, war-room
activation, and the comms plan, so it cannot wait for the post-mortem.
The post-mortem's job here is to **confirm the live classification was
correct, or deliberately reclassify** now that the settled facts
(actual user impact, duration, data/compliance blast radius) are known.

Severity definitions, response SLAs, and the decision flow are in
[severity-levels.md](severity-levels.md).

Check the live severity against the measured impact:

- **Reclassify up** if settled facts show the blast radius was larger than
  first thought (more users, longer duration, data / compliance impact
  discovered after the fact).
- **Reclassify down** only when the measured impact is genuinely smaller
  than the live call, and record the reason. Do **not** reclassify down
  to avoid the 5-business-day post-mortem deadline — if impact was real
  and material, it is SEV2 (or higher) regardless of whether writing it
  up is inconvenient.
- If no live severity was set (the incident bypassed the declared
  process), record that as a process gap in the Contributing Factors
  section and classify now based on measured impact.

Capture both the live severity and the final severity (and the reason if
they differ) in the header of the post-mortem document.

### 2. Identify roles

Every incident has at minimum:

- **Incident Commander (IC)** — owned the response, drove decisions,
  coordinated communications. Usually the on-call engineer or their
  designated deputy. The IC is **responsible for ensuring the post-mortem
  is written**, but does not have to write every section alone.
- **Responders** — engineers who diagnosed or remediated the issue.
- **Communications lead** (SEV1 only) — owned customer/stakeholder updates.
- **Post-mortem author** — usually the IC. Name explicitly so ownership is
  unambiguous.

Capture these in the header of the post-mortem document, along with the
**Incident ID**. Reuse the ID from whichever incident tracker your team
already uses (PagerDuty incident ID, ServiceNow ticket, Opsgenie alert
ID, Jira incident issue, etc.) so the post-mortem is linkable from the
same ID the responders used in the war room. If the team has no such
system, fall back to `INC-YYYY-MMDD-NNN` using the incident start date
and a daily sequence number.

### 3. Reconstruct the timeline

Gather raw sources in this order:

```text
# Incident chat/war room transcript
# Paging/alerting history (PagerDuty, Opsgenie, etc.)
# Deploy history around the incident window
# Monitoring dashboards (screenshot or link)
# Customer support tickets filed during the incident
```

Build the timeline in UTC, with source links where possible. Every entry
has a timestamp, actor (role not person when identity doesn't matter), and
a short factual statement, plus a metric, log search, or dashboard link
showing where the data point came from (put commands/queries used in the
document so others can reproduce). **Do not interpret yet** — just record what
happened. Include changes in status/impact and key responder actions and
decisions.

Report impact duration separately from response duration: impact may
start before detection and may end before resolution.

Example row (good):

> `14:03 UTC` — Deploy of `orders-api` v2.41.0 completes.
> `14:07 UTC` — Error rate on `/checkout` climbs from 0.1% to 8% (link to dashboard).
> `14:09 UTC` — First customer ticket filed ("Payment fails with 500").

Anti-pattern (bad — contains interpretation and blame):

> `14:07 UTC` — Alice's deploy breaks checkout because she didn't test properly.

Key timestamps to always capture:

- **Detection** — when did an alert fire or a report first reach responders?
- **Acknowledgement** — when was the incident declared / on-call paged?
- **Mitigation** — when was customer impact stopped (even if root cause
  wasn't yet known)?
- **Resolution** — when was the underlying issue fully fixed?

**Start** = first customer impact (record the triggering deploy or change separately).
Impact often starts before responders know; keep Start separate from Detection.
**Time-to-Detect (TTD)** = Detection − Start.
**Time-to-Acknowledge (TTA)** = Acknowledgement − Detection.
**Time-to-Mitigate (TTM)** = Mitigation − Detection.
**Time-to-Resolve (TTR)** = Resolution − Start.

Always write the two endpoint events beside each duration. "MTTR" is used
for repair, recover/restore, respond, and resolve, so a bare "MTTR" is
ambiguous. Averages of a few incident durations are not evidence of
improvement: Google's analysis of incident metrics found MTTx statistics
poorly suited to decisions or trend analysis, so report this incident's
durations only. TTR above is not DORA's "failed deployment recovery
time", which covers only recovery from a deployment that fails and needs
immediate intervention; do not use the two interchangeably. Start the
timeline before the trigger and work forward, not backward from
resolution (hindsight bias); include information the team did not have
at the time that you wish they had.

### 4. Quantify impact

Be specific. "Some users were affected" is not impact. Use the format:

- **Users affected**: rough count or percentage, and segment (e.g., "EU
  paying customers").
- **Requests affected**: count or error rate.
- **Duration**: start → mitigation (and separately to resolution if they
  differ).
- **Revenue / data / compliance impact**: if applicable. If unknown, say
  so — do not guess.

### 5. Run root-cause analysis

Use **5 Whys** as a starting frame, but do not stop at a single chain.
Real incidents have **multiple contributing factors** — capture all of
them.

5 Whys sketch:

```
Q1: Why did /checkout return 500s?          A: Orders-api threw NullPointer on line X.
Q2: Why did the code path hit null?         A: New field not populated for legacy carts.
Q3: Why wasn't that caught in testing?      A: Test fixtures only cover post-migration carts.
Q4: Why didn't the canary catch it?         A: Canary traffic routed only to new accounts.
Q5: Why is canary traffic segmented that way? A: Default router config from 2023 never revisited.
```

Then capture **Contributing Factors** separately — the conditions that
allowed the trigger to cause the outage:

- Alerting gap: error-rate alert threshold was 10% (incident peaked at 8%).
- Runbook gap: no documented rollback for orders-api > v2.40.
- Process gap: deploy approval did not require canary health check.

**Proximate vs root cause.** The proximate cause is what directly led to
the incident (the trigger). The root cause is the place in the chain
where a change prevents the whole class of incident. Keep asking until a
system, process, or design gap surfaces. "Human error" is never a root
cause. Also review the response process itself (collaboration,
communication, review) even if it is not a root cause.

**Root-cause categories** (name one; it points to the right action):

| Category     | Typical action                                                                    |
| ------------ | --------------------------------------------------------------------------------- |
| Bug          | Tests, canary, incremental rollout, feature flags                                 |
| Change       | Improve change review / change management                                        |
| Scale        | Capacity plan; monitor and alert on resource constraints                          |
| Architecture | Design review; design misaligned with operating conditions                        |
| Dependency   | See below                                                                         |
| Unknown      | Action is to improve observability (logging, monitoring, debugging) so it can be diagnosed |

**Dependency failures.** Compare with the dependency's SLO (internal) or
your reasonable expectation of it (third party; contractual SLAs are
usually too low to be useful). If it breached the SLO or expectation,
the dependency owner needs to improve, and you still review whether your
service should degrade more gracefully. If it stayed within, your
service lacks resilience. If there is no SLO or expectation, creating one
is an action item.

Ask "how" and "what" questions rather than "who" or "why" when
interviewing responders: What were you focusing on? What differed from
what you expected? What options did you consider and why did this one
seem best? How did time pressure influence choices? Was there prior work
the team chose not to do?

Use blameless language throughout. See [blameless-language.md](blameless-language.md)
for do/don't phrasings.

### 6. Capture what went well and what went wrong

Post-mortems are not just failure catalogs — call out what worked so it
gets reinforced:

- **What went well**: fast detection, clean rollback, good communication,
  useful runbook, solid monitoring.
- **What went wrong**: gaps, surprises, places where the system or process
  let the team down.
- **Where we got lucky**: near-misses that could have made this worse.
  Lucky outcomes are future incidents waiting to happen.

### 7. Define action items

Every action item **must** have the fields below. If an owner or tracking link is not yet
known, mark it `UNASSIGNED`/blank, never invent it, and keep the post-mortem in Draft:

| Field         | Required | Notes                                                               |
| ------------- | -------- | ------------------------------------------------------------------- |
| Description   | Yes      | Concrete and verifiable                                             |
| Type          | Yes      | One of: `prevent`, `detect`, `mitigate`, `process`, `documentation` |
| Owner         | Yes      | A named person, not a team (teams diffuse ownership)                |
| Deadline      | Yes      | Absolute date (YYYY-MM-DD), not "next sprint"                       |
| Tracking link | Yes      | Jira/Linear/GitHub issue ID so progress is visible                  |
| Priority      | Yes      | P0/P1/P2                                                            |

**Balance the action types.** A post-mortem that only produces "prevent"
actions is brittle — add at least one "detect" (catch it sooner next time)
and consider "mitigate" (shrink the blast radius when it recurs).

Wording: each action MUST be **actionable** (starts with a verb, produces
a useful outcome), **specific** (scope stated, in and out), and
**bounded** (a reader can tell when it is finished).

| Poorly worded                                   | Better                                                       |
| ----------------------------------------------- | ------------------------------------------------------------ |
| Investigate monitoring for this scenario.       | Add alerting for all cases where this service returns >1% errors. |
| Fix the issue that caused the outage.           | Handle invalid postal code in user address form input safely. |
| Make sure engineer checks the schema parses.    | Add automated presubmit check for schema changes.            |
| Improve testing / Be more careful with deploys. | Add integration test covering legacy-cart checkout path (test fixture `legacy_cart_v1.json`). Owner: @alice. Deadline: 2026-05-14. ENG-1234. |

Changing human behaviour (training, "be careful") is less reliable than
changing systems; reject actions that only ask people to try harder.

**Prioritise.** Not every item is P0; equal priorities hide what to do
first. Group many items by theme (one owner per theme) when the incident
is large.

**Do not over-ticket.** Tickets are for actions that must be done.
When an action is judged not worth its cost, record it in the document
with the reason rather than silently dropping it.

**Closure.** Tickets live in the owning team's backlog (not only in the
document), labelled with the severity and incident ID/date so open
post-mortem actions can be queried. Check whether the team or Sanofi
unit has an action-item closure policy; if none exists, flag the gap
rather than inventing a Sanofi deadline. For reference, other
organisations set closure SLOs (PagerDuty: 15 days for SEV1 and 30
days for SEV2 preventive actions; Atlassian: 4 or 8 weeks for priority
actions depending on the service).

**Action categories** (use to check coverage; map onto the `Type`
field above):

| Question                                                    | Type            |
| ----------------------------------------------------------- | --------------- |
| How do we decrease time to accurately detect this failure?  | `detect`        |
| How do we cut severity or duration when it recurs?          | `mitigate`      |
| How do we prevent this class of failure?                    | `prevent`       |
| How do we improve the response itself?                      | `process`       |
| What knowledge/runbook was missing?                         | `documentation` |

Include at least one `prevent` or `mitigate` action aimed at the root
cause, not only the trigger.

### 8. Write the document

Use [post-mortem-template.md](post-mortem-template.md)
as the exact template. Fill every required section; omit optional sections
only if they have no content (do not leave "TBD" placeholders).

File the document at `docs/postmortems/YYYY-MM-DD-short-slug.md`
(create the directory if it does not exist). Use the incident **start
date**, not the authoring date.

### 9. Review and publish

Reread the document against [blameless-language.md](blameless-language.md) and run the Review Gate and Checklist in SKILL.md before circulating.

## Anti-Patterns

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

Outages are almost always multi-causal. A post-mortem with exactly one
contributing factor usually means the author stopped looking. Push on
"what else had to go wrong for this to happen?"

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
