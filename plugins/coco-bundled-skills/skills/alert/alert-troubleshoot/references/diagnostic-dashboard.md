# Diagnostic Dashboard

Reference for the **Vital Signals Dashboard** rendered in Step 3.5 of `SKILL.md`. This is the single artifact the agent presents at the mandatory stopping point after the initial sweep — it tells the user "I checked these things, here's what looks healthy, here's what doesn't, and here's the temporal pattern" before any classification or delegation happens.

The dashboard has five panels — three required, two conditional. The first four describe **alert-object health**; Panel 5 describes the **monitored product's health** and is the one the user usually cares about most.

Path A / Path B terminology in this reference follows [`../../references/notification-dispatch-paths.md`](../../references/notification-dispatch-paths.md).

| Panel | Always rendered? | Purpose |
|-------|------------------|---------|
| **1. Vital Signals checklist** | Required | Pass/fail per check across alert-object, scheduling, notification, telemetry. Reassures the user the agent looked at the right things even when nothing's wrong. |
| **2. Execution timeline (sparkline)** | Required | Visual at-a-glance of the last N runs. |
| **3. Notification delivery strip** | Required when an integration is wired | Visual of recent notification outcomes. |
| **4. Severity histogram (event-table)** | Required when the sweep returned ≥ 1 row | Visual count of error/warn/info/span-error volumes around the incident time. |
| **5. Product Vital Signs** | Required when Step 3.5's lightweight product fingerprint matched (Method 1 tags and/or Method 2 telemetry signatures from [`product-detection.md`](product-detection.md); Method 3 only as fallback/drift check) with confidence | Per-product health checklist + optional product-specific ASCII viz. Queries and thresholds come from the matched product's existing skill (e.g. `dynamic-tables/troubleshoot/SKILL.md`, `openflow-observability/references/core-queries-resource.md`) — the alert dashboard does not re-define them. |

Render order: checklist → execution timeline → notification strip → severity histogram → product vital signs. Below all panels, list the **top 3 anomalies** in plain prose (this is what the user will read first).

The split between Panels 1–4 and Panel 5 is deliberate: alert-object health (1–4) tells the user *whether the alert itself is working*; product vital signs (5) tells them *whether the thing the alert is watching is healthy*. Both questions almost always come up; surfacing both at the stopping point lets the user redirect the investigation if Panel 5 already shows the obvious problem.

---

## Panel 1 — Vital Signals Checklist

Markdown table. Three columns: `Check`, `Status`, `Detail`. Status uses these symbols and **only** these symbols (consistency matters more than expressiveness):

| Symbol | Meaning |
|--------|---------|
| `✓` | Healthy / passed. |
| `⚠` | Degraded but not failing (warning). |
| `✗` | Failing. |
| `?` | Could not check (privilege gap or signal not available). Always include the reason in the Detail column. |
| `—` | Not applicable to this alert (e.g., notification panel for an alert with no action block). |

The required check rows. Render every row even when the result is `—`; absence of a row is harder to interpret than an explicit "not applicable".

| Check | What it asserts | Source |
|-------|-----------------|--------|
| Alert exists | `SHOW ALERTS LIKE` returned the named alert. | Step 1 |
| Alert state | `started` (✓), `suspended` (⚠ if user expected it running, else ✓). | Step 1 — `state` field |
| Schedule defined | Either `SCHEDULE` or `predecessors` is set. | Step 1 — `schedule` / `predecessors` |
| Warehouse usable | Non-serverless alerts: warehouse exists and the owner role has USAGE. Serverless: marked ✓. | Step 1 + `SHOW WAREHOUSES LIKE` |
| Owner role active | Owner role exists and is not disabled. | Step 1 + `SHOW ROLES LIKE` |
| Condition compiles | Most recent `ALERT_HISTORY.STATE ≠ CONDITION_FAILED` in the lookback window. | Step 2 |
| Recent execution success | Pass rate over the last N runs (default N = 24h or 50 rows, whichever is smaller). ✓ if ≥ 90%, ⚠ if 50–89%, ✗ if < 50%. Always include the fraction in Detail (e.g., `42/48 (87%)`). | Step 2 |
| Notification integration | Path B: integration named in action SQL exists and is ENABLED. Path A: active integration is inferred from alert config and/or recent `NOTIFICATION_HISTORY` evidence. | Step 1 + Step 2 |
| Notification delivery | NOTIFICATION_HISTORY success rate over the same window. ✓/⚠/✗ thresholds same as above. `—` if no action block. | Step 2 |
| Event table accessible | `event_table` parameter is set on the alert's database AND `SELECT` succeeded against it. | Step 3 |
| Telemetry around incident | Count of records in the ±5 min window. ✓ if ≥ 1 row, ⚠ if 0 (not necessarily wrong but worth noting), `—` if no event table. | Step 3 |
| Runbook URL | Captured from `comment`. ✓ if no URL present, `?` if URL present (status is "captured, not fetched"). | Step 1, Step 6 |

Do **not** add product-specific rows here. They live in Panel 5 and are gated on the lightweight product fingerprint described in [`product-detection.md`](product-detection.md). Leaving Panel 1 product-agnostic keeps the row order stable across all alerts so users build a fast mental model.

Example:

```
## Vital Signals — ALERT_TASKS_ERROR_RATE @ EVAL_DB.PUBLIC

| Check                      | Status | Detail                                              |
|----------------------------|--------|-----------------------------------------------------|
| Alert exists               | ✓      | EVAL_DB.PUBLIC.ALERT_TASKS_ERROR_RATE              |
| Alert state                | ✓      | started                                             |
| Schedule defined           | ✓      | USING CRON */15 * * * * UTC                        |
| Warehouse usable           | ✓      | EVAL_WH (serverless not in use; USAGE held)        |
| Owner role active          | ✓      | DATA_ENG_ROLE                                       |
| Condition compiles         | ✗      | 6 of last 24 runs CONDITION_FAILED                 |
| Recent execution success   | ✗      | 18/24 (75%) over last 24h                          |
| Notification integration   | ✓      | EMAIL_INT (enabled)                                 |
| Notification delivery      | ⚠      | 12 SUCCESS / 2 RETRIABLE_FAILURE / 0 FAILURE       |
| Event table accessible     | ✓      | EVAL_DB.PUBLIC.EVAL_EVENTS                          |
| Telemetry around incident  | ✓      | 3 ERROR logs, 0 spans, 12 metric points (±5 min)   |
| Runbook URL                | ?      | Found in COMMENT — not fetched (see Step 6)         |
```

---

## Panel 2 — Execution Timeline (Sparkline)

Single horizontal strip representing the **last 30 alert executions** (or fewer if `ALERT_HISTORY` returned fewer rows). One character per execution, oldest on the left, newest on the right.

| Char | State |
|------|-------|
| `·` | `CONDITION_FALSE` (no firing — quiet period) |
| `▲` | `TRIGGERED` (fired, condition matched) |
| `✗` | `CONDITION_FAILED` |
| `✗` | `ACTION_FAILED` (use same `✗` glyph; differentiate via the legend) |
| `~` | `ACTION_SKIPPED` |
| `?` | Other / unknown state |

Render the strip with the time axis above and a legend below. Mark the user-reported incident time with a caret (`^`) directly under the strip when it falls inside the window.

```
## Execution Timeline (last 30 runs, oldest → newest)

  06:00  →  ··················▲··✗✗✗▲▲▲··  ←  18:00 (now)
                                  ^
                          incident reported

  Legend:  · CONDITION_FALSE   ▲ TRIGGERED   ✗ FAILED   ~ SKIPPED
```

Hard rule: do not invent runs to pad the strip. If `ALERT_HISTORY` returned 7 rows, render 7 characters. The width of the strip is itself signal (a 1-week-old alert with 4 runs means it almost never fires).

For very long lookbacks (> 100 runs), down-sample by bucketing into 30 bins; render the dominant state per bin, and append a footnote: `(down-sampled from 187 runs into 30 bins)`.

---

## Panel 3 — Notification Delivery Strip

Same horizontal-strip format as Panel 2, but for the rows from `INFORMATION_SCHEMA.NOTIFICATION_HISTORY`. Skip this panel entirely only if the alert has no notification action semantics. For Path A alerts, do not skip solely because the integration name is not literal in action SQL.

| Char | Status |
|------|--------|
| `✓` | `SUCCESS` |
| `~` | `QUEUED` |
| `r` | `RETRIABLE_FAILURE` |
| `✗` | `FAILURE` |

```
## Notification Delivery (last 20 sends, oldest → newest)

  EMAIL_INT:   ✓✓✓✓✓✓✓✓r✗✓✓✓✓r✓✓✓✓✓

  Legend:  ✓ SUCCESS   ~ QUEUED   r RETRIABLE_FAILURE   ✗ FAILURE
```

When multiple integrations appear (a single alert action can fan out via multiple integrations), render one strip per integration label, aligned by the longest integration name.

---

## Panel 4 — Severity Histogram (Event Table)

Required when the Step 3 event-table sweep returned ≥ 1 row. Render an ASCII bar chart of record counts grouped by severity / span-status, scoped to the same `±5 min` window.

Use 1 cell = 1 record up to width 40, then auto-scale and annotate with the cell unit.

```
## Severity Histogram (events ±5 min around 2026-04-18T17:42:00Z)

  ERROR      ███████  7
  WARN       ████  4
  INFO       ██████████████  14
  SPAN_ERR   ██  2
  METRIC     ████████████████████████  24

  Total: 51 records across EVAL_DB.PUBLIC.EVAL_EVENTS (1 cell = 1 record)
```

When totals exceed 40 in any row, switch to scaled rendering and update the unit annotation:

```
  ERROR      ████████████████████████████████████████  152  (1 cell = ~3.8 records)
```

**Top error sample.** Below the histogram, include up to 3 distinct error messages from the sweep, deduplicated by `value:message`:

```
  Top error messages:
    1. (5×) "Numeric value '0' cannot be divided"
    2. (1×) "Task SAMPLE_FAIL_TASK was suspended after 100 consecutive failures"
    3. (1×) "Resumed by user DATA_ENG_USER"
```

---

## Panel 5 — Product Vital Signs

Required when Step 3.5's **lightweight product fingerprint** (Method 1 tag metadata and/or Method 2 telemetry signatures from [`product-detection.md`](product-detection.md); Method 3 only as fallback/drift check) returns a confident match. This is the panel users came for: it shows whether the product the alert *watches* — the dynamic table, the Openflow runtime, the task — is healthy, expressed in the product's own native signals (refresh lag, CPU%, run success rate).

**Source of truth = the downstream product skill, not this dashboard.** Each product team already maintains the canonical queries and thresholds for "is this thing healthy?" in their own skill. Panel 5 defers to those:

| Matched product | Where Panel 5 sources its queries + thresholds |
|-----------------|------------------------------------------------|
| Dynamic Tables | [`../../../../data-engineering/dynamic-tables/troubleshoot/SKILL.md`](../../../../data-engineering/dynamic-tables/troubleshoot/SKILL.md) and [`references/dt-state.md`](../../../../data-engineering/dynamic-tables/references/dt-state.md) |
| Openflow | [`../../../../data-engineering/openflow-observability/references/core-queries-resource.md`](../../../../data-engineering/openflow-observability/references/core-queries-resource.md) (CPU, memory, restarts, connectors) and [`core-queries.md`](../../../../data-engineering/openflow-observability/references/core-queries.md) (recent error logs) |
| Tasks | [`../../../../data-engineering/snowflake-tasks/SKILL.md`](../../../../data-engineering/snowflake-tasks/SKILL.md) ("Querying Task Run History") |
| Data Quality | [`../../../../data-governance/data-quality/SKILL.md`](../../../../data-governance/data-quality/SKILL.md) |

Load the matched product skill's queries reference, run a small subset (the discovery-sequence queries — usually 4–6 queries scoped to the alert's `{database}.{schema}.{object_name}`), and present the results as a checklist using *that skill's* thresholds. The alert troubleshoot skill does **not** re-define product thresholds — drift between the two would be silent and harmful.

The alert dashboard imposes only the **render contract**:

1. The panel header is `## Product Vital Signs — <product display name>` (e.g., `Dynamic Table`, `Openflow Runtime`, `Task`).
2. First body line is `Scope: <object identifier>  (<short product-specific config summary>)` so the user knows which monitored object the rows describe.
3. Then a checklist with the same `Check / Status / Detail` columns and the same glyph alphabet as Panel 1. Each row maps one product-skill query result to a `✓ / ⚠ / ✗ / ?` per the product skill's own threshold table.
4. Optional one-line ASCII visualization when there's a temporally meaningful series (refresh-state strip, CPU sparkline, run-outcome strip). Omit if the source query returned no time series.
5. **Skip the panel entirely** (do not render an empty one) when the lightweight fingerprint produced no confident match — the user should not see a "Product: unknown" panel.

When the panel renders, the raw query results feed forward as seed evidence to Step 5 (delegation), so the downstream product skill can skip its own discovery sequence.

Example, Dynamic Tables (queries + thresholds sourced from `dynamic-tables/troubleshoot/SKILL.md`):

```
## Product Vital Signs — Dynamic Table
   Scope: SALES_PROD.REPORTING.DAILY_ORDERS_DT  (refresh_mode = INCREMENTAL, target_lag = 5 min)

   | Check                       | Status | Detail                                              |
   |-----------------------------|--------|-----------------------------------------------------|
   | Scheduling state            | ✓      | RUNNING                                             |
   | Last refresh outcome        | ✗      | UPSTREAM_FAILED (parent DT STAGING.RAW_ORDERS_DT)   |
   | Lag vs target               | ✗      | time_within_target_lag_ratio = 0.62 (target ≥ 0.95) |
   | Recent refresh success rate | ✗      | 11/20 (55%) over last 24h                           |

   Refresh outcomes (last 20, oldest → newest):  ✓✓✓✓↑✓✓✗✗↑↑✗✗✓✗↑✗✗↑↑
```

---

## Top Anomalies Summary

After all panels, render a short prose paragraph (1–3 bullets) calling out the most actionable findings. This is what the user reads first; everything above is the receipts.

Format:

```
## Top anomalies

- **6 CONDITION_FAILED runs in last 24h** — condition body references an event-table column that was renamed in v8.27. Most likely root cause.
- **2 RETRIABLE_FAILURE notifications** — both at 17:38, suggests a brief webhook outage; not currently failing.
- **Runbook URL captured but not fetched** — see Step 6 for consent prompt.
```

If nothing is anomalous (everything is ✓), still render this section with `- All vital signals nominal. Most recent firing at <ts>; root cause likely in the monitored product (proceed to Step 4).` so the user knows it wasn't accidentally skipped.

---

## Rendering Rules

1. **Always render all required panels**, even when there's no anomaly. The point of the dashboard is to demonstrate coverage; an empty dashboard reads as "agent did nothing".
2. **Don't fabricate data.** If a check couldn't run (privilege gap, no notification evidence, event table not configured), use `?` and put the cause in the Detail column. Never use `✓` to mean "didn't check".
3. **Glyph stability.** Use only the glyphs in this file. Do not substitute emojis (`✅` / `❌`) — they break alignment in many terminals and are inconsistent across pasted contexts.
4. **Width.** Target 80-column friendliness. Sparkline strips should not wrap. Truncate detail strings to 60 chars with `…` if needed.
5. **Place the dashboard in the chat output**, not in a tool result file. The user must see it inline at the stopping point.
6. **Re-render on follow-up.** If the user comes back with new context (e.g., "now check the last hour only"), re-render the affected panels — don't append a delta.

---

## When to Skip Panels

| Situation | Skip rule |
|-----------|-----------|
| Alert was never executed (`ALERT_HISTORY` empty) | Skip Panels 2 and 3; render Panel 1 with `Recent execution success` = `?` and Detail `no executions in lookback window`. Also skip Panel 4 (no incident time → no sweep). |
| Alert has no action block | Skip Panel 3. Render Panel 1 row `Notification delivery` = `—`. |
| Event table not configured for the database | Skip Panel 4. Render Panel 1 row `Event table accessible` = `✗` with Detail `EVENT_TABLE parameter not set on <database>`. |
| Privilege denied on `NOTIFICATION_HISTORY` | Skip Panel 3. Render Panel 1 row `Notification delivery` = `?` with Detail `MONITOR USAGE on integration required`. |
| Integration name not parseable from action SQL | For Path A, do not skip Panel 3. Use `NOTIFICATION_HISTORY.INTEGRATION_NAME` as runtime evidence. Skip only if there is no notification evidence and no notification action semantics. |
| Privilege denied on the event table | Skip Panel 4. Render Panel 1 row `Telemetry around incident` = `?` with Detail `SELECT on event table required`. |
| Lightweight product fingerprint inconclusive (no Method 1/2 hit, and no Method 3 fallback hit, or all hits below confidence threshold) | Skip Panel 5 entirely. Do not render an empty `Scope: unknown` panel — the user should not have to read a panel that has nothing to say. |
| Product fingerprint matched but the per-product queries all returned zero rows / errored out (e.g., privileges) | Render Panel 5 with all rows as `?` and Detail spelling out the cause. Do **not** mark the product `✓` — distinguish "checked and healthy" from "couldn't check". |

---

## Why This Format

- **Markdown tables + ASCII glyphs** render cleanly in chat, in saved markdown reports, in PR descriptions, and in Slack — no plotting library or image upload required.
- **Sparklines preserve temporal information** that a status-only checklist loses (a 75% pass rate hides whether the failures are bursty or evenly distributed; the sparkline shows it).
- **Vital-signals coverage is the same shape every time**, so users build a mental model after one or two investigations and immediately notice when a row is missing.
- **The "what looks good" rows are intentionally noisy.** Showing 8 ✓ rows next to 2 ✗ rows is the explicit "I checked these things" signal the user asked for.
- **Splitting alert-object signals (Panels 1–4) from product signals (Panel 5)** matches how operators reason: first they confirm the alert plumbing isn't the problem (Panels 1–4), then they look at what the alert was actually watching (Panel 5). Both questions almost always come up — surfacing both at the stopping point lets the user redirect the investigation if Panel 5 already shows the obvious problem (e.g., Openflow runtime at 96% memory) without waiting for the agent to run classification.
