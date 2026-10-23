# Severity Levels

Sanofi incident severity classification. Driven by **customer impact**, not engineering effort or internal inconvenience.

Use the **highest** applicable severity. Doubt ⇒ escalate (SEV3 → SEV2, SEV2 → SEV1), never down. Downward reclassification after facts settle: only with a recorded reason; under-classifying in the moment delays the right response.

## SEV1 — Critical

**Definition:** major customer-facing outage, data loss, security breach, or regulatory-reporting failure. Business materially impaired.

**Characteristics** (any one qualifies):

- Complete or near-complete unavailability of a core product surface (login, checkout, prescription submission, clinical data entry).
- Data loss, corruption, or unintended exposure (incl. PII, PHI, GxP-regulated records).
- Security breach or credible suspected breach.
- Regulatory-reporting failure (e.g. missed pharmacovigilance submission window).
- Revenue-critical path broken > 5 minutes with no workaround.

**Response SLA:**

- On-call paged immediately.
- Incident Commander declared ≤ 15 min.
- Dedicated war room (Slack channel + video bridge) ≤ 15 min.
- Communications lead assigned.
- Status-page update ≤ 30 min of detection.
- Stakeholders notified per incident-comms plan (execs on SEV1).

**Post-mortem:** **required within 5 business days** of incident closure; reviewed by engineering leadership.

**Examples:**

- User authentication completely down for 20 minutes.
- Prescription-submission API rejecting all valid requests.
- Accidental exposure of patient records to unauthorized users.
- Ransomware or confirmed unauthorized access to production systems.
- Payments processor integration broken; no checkouts complete globally.

## SEV2 — High

**Definition:** significant degradation or partial outage. Key feature broken for a meaningful user segment, or performance severely degraded. Business continues but measurably harmed.

**Characteristics** (any one qualifies):

- Error rate well above baseline (typically > 1% sustained) on a user-facing surface.
- Latency unusable (p95 > 10× baseline) on a core flow.
- Major feature broken for a subset of users (e.g. EU region, enterprise tier, a specific integration).
- Partial data-processing failure: no data loss, but delays a business process.
- Recurring SEV3 incidents over short windows (cumulative impact).

**Response SLA:**

- On-call response ≤ 30 min.
- Incident Commander declared for the duration.
- Slack incident channel opened.
- Status-page update ≤ 60 min if customer-visible.

**Post-mortem:** **required within 5 business days** of incident closure.

**Examples:**

- Checkout fails for ~8% of requests for 1.5 hours (the template's example).
- Clinical dashboard loads taking 30s instead of 2s for enterprise tier.
- One regional deployment intermittently failing over a 4-hour window.
- Notification emails delayed by 6+ hours (business process disrupted).

## SEV3 — Moderate

**Definition:** minor degradation, contained blast radius, workaround exists. Detected by monitoring or reported by few users.

**Characteristics** (any one qualifies):

- Error rate slightly above baseline, contained to a non-core flow.
- Small user subset affected, workaround available.
- Background job failing with automatic retry succeeding within SLA.
- Cosmetic or non-blocking bug on a core surface.

**Response SLA:**

- Responded to same business day.
- Tracked in the normal issue tracker (no dedicated war room).

**Post-mortem:** **optional**; strongly recommended when:

- Same pattern caused multiple SEV3s (recurrence signal).
- Near-miss: would have been SEV2 but for luck (timing, traffic level).
- New failure mode not seen before (learning signal).
- Humans or customers detected it instead of monitoring (monitoring failure).
- On-call intervention needed (rollback, traffic reroute).
- A stakeholder requests one.

The last three triggers follow the Google SRE book's postmortem criteria.

**Examples:**

- Internal admin dashboard throws errors on a filter rarely used.
- Nightly data-export job retries once before succeeding.
- Layout glitch on the billing page on one browser version.
- A single background worker crashes and auto-restarts within seconds.

## Classification rules

1. **Customer impact drives severity**, not engineering embarrassment or on-call fatigue.
2. **"Degraded" is SEV2, not SEV3**, when customers can measure the degradation (slow, flaky, partial).
3. **Security and compliance are force multipliers:** SEV3-sized outage + PII leak ⇒ SEV1; SEV2-sized outage + missed regulatory report ⇒ SEV1.
4. **Reclassify explicitly.** Scope widens mid-incident → IC re-declares severity (e.g. "this just became SEV1, paging leadership now"). NEVER let SEV creep silently without a decision.
5. **NEVER classify down to avoid paperwork.** SEV2 criteria apply ⇒ post-mortem required, however inconvenient.

## Decision flow

```
Any SEV1 criterion met? (check all independently)
  - customer data loss, corruption, or exposure
  - security breach or credible suspected breach
  - regulatory-reporting failure (missed submission window)
  - core product surface fully or near-fully down
  - revenue-critical path broken > 5 min with no workaround
├── Yes → SEV1
└── No → Any SEV2 criterion met? (check all independently; no minimum duration)
         - error rate well above baseline (typically > 1% sustained) on a user-facing surface
         - latency unusable (p95 > 10× baseline) on a core flow
         - major feature broken for a subset of users
         - partial data-processing failure delaying a business process
         - recurring SEV3 incidents over short windows
         ├── Yes → SEV2
         └── No → SEV3 (narrow impact with workaround)
```

Ambiguous flow result ⇒ pick the higher severity; incident review reclassifies later.
