---
name: workload-performance-analysis/ui-performance-explorer/summary
description: "Analyze a pre-provided Performance Explorer page snapshot from the Snowflake Performance Explorer UI page and produce a condensed report covering overall health, what's working, what may be concerning, notable patterns, cross-dimensional insights, and a prioritized action plan."
---

**Loaded only when source=UI_PERFORMANCE_EXPLORER (`performanceExplorerContext` payload present).**

# Performance Explorer Summary

Analyze a pre-provided Performance Explorer page snapshot from the Snowflake Performance Explorer UI page and produce a condensed structured report.

## When to Use

This skill is designed exclusively for use from the **Performance Explorer UI page** via the "Analyze with CoCo" button. It expects a pre-provided page-context payload — `pageName == "Performance Explorer"` plus a `metadata` object carrying health metrics, top tables, top warehouses, and table/warehouse events — to be present in the context before it can produce any output.

**Do NOT invoke this skill from general conversation.** Do NOT auto-invoke based on a user describing performance problems, asking for workload analysis, or pasting query telemetry. The skill is button-only.

If the user invokes this skill outside of the Performance Explorer page context (i.e., no Performance Explorer page snapshot is present), stop and inform them:

> This skill is designed to be used from the Performance Explorer page in the Snowflake UI via the "Analyze with CoCo" button. It requires the Performance Explorer page-context payload that the page provides automatically. To use it, navigate to the Performance Explorer page and click "Analyze with CoCo" — the necessary data will be included automatically.

## Stopping Points

| Point | Condition | Action |
|-------|-----------|--------|
| Within Step 1, immediately after `get_page_context` is invoked | `get_page_context` returns `null`, throws an error, returns a non-object, or the tool itself is unavailable in the runtime | The page-context provider failed. Inform the user that the page-context provider could not be reached and ask them to retry the "Analyze with CoCo" button from the Performance Explorer page. Phrase the message distinctly so the user knows it is a tool-side issue, not a wrong-page issue — do **not** use the §When to Use refusal blockquote (which is for wrong-page cases). Stop and do not proceed. |
| Within Step 1, immediately after `get_page_context` returns | `pageName` is missing or is not exactly `"Performance Explorer"` | Deliver the exact refusal blockquote in §When to Use ("This skill is designed to be used from the Performance Explorer page in the Snowflake UI via the 'Analyze with CoCo' button..."). Stop and do not proceed. |
| Within Step 1, immediately after `get_page_context` returns | `pageName == "Performance Explorer"` but the payload carries **no analyzable data for the selected filters** — every one of `metadata.healthMetrics` / `metadata.topTables` / `metadata.topWarehouses` parses to an empty array or object. (The FE emits these keys as JSON-stringified strings — decode and inspect the contents, not bare key presence.) | **No data matched the selected filters.** Emit a single brief message leading with **No Performance Explorer results found for the selected filters**, naming the active filters / time window (humanized per Step 1) and inviting the user to broaden the filters or widen the time range and re-run the "Analyze with CoCo" button. Stop — do **not** proceed to Step 2/3, and do **not** emit a `✅ Healthy` (or any) verdict. The Analyze button is disabled while the page is loading, so an empty payload at invoke time means no data matched this scope, never "still loading." |

The routing layer above this skill (the parent `workload-performance-analysis` SKILL Step 0) matches on the literal `${performanceExplorerContext}` system-reminder marker; this skill independently re-checks `pageName` and metadata-shape after `get_page_context` returns, before producing output. The two checks together (parent marker + sub-skill payload-shape) are defense-in-depth.

## Canonical Enum Strings and Humanization

Every enum value in the payload (`healthMetrics.metric`, `tableEvents.operation` / `.status` / `.type`, `warehouseEvents.eventName` / `.state`) arrives in canonical proto-enum form, prefixed with one of six type-name prefixes. The prefix identifies which proto enum the value belongs to; the suffix carries the value.

### The six type-name prefixes

`METRIC_NAME_`, `TABLE_EVENT_OPERATION_TYPE_`, `TABLE_EVENT_STATUS_`, `TABLE_EVENT_TABLE_TYPE_`, `WAREHOUSE_EVENT_NAME_`, `WAREHOUSE_EVENT_STATE_`.

See [`../../references/data_contract.md` § Enum prefix shapes](../../references/data_contract.md) for the proto enum names and field locations per prefix. Note: the failure value for `TABLE_EVENT_STATUS_` is `_FAIL`, not `_FAILED`.

These canonical-prefix strings are wire-format identifiers — they MUST be humanized (via the algorithmic rule below) before appearing in any user-facing output. They never leak verbatim into a heading, table cell, prose sentence, arrow chain, or bullet.

### Algorithmic humanization rule (5 steps)

Apply these steps in order to convert any canonical-prefix enum string into a display label:

1. **Strip the type-name prefix** — remove one of the six prefixes from the front (`METRIC_NAME_`, `TABLE_EVENT_OPERATION_TYPE_`, `TABLE_EVENT_STATUS_`, `TABLE_EVENT_TABLE_TYPE_`, `WAREHOUSE_EVENT_NAME_`, `WAREHOUSE_EVENT_STATE_`).
2. **Replace underscores with spaces.**
3. **Title-Case each word**, with the carve-out that `P50` / `P90` / `P99` percentile tokens stay literal all-caps — never lowercase to `p50`.
4. **Polish abbreviations** — replace `Avg` with `Average`, `Sec` with `Seconds`, and `Pct` / `Percent` with `%`.
5. **Parenthesize qualifier suffixes** — if the canonical name ends in `_OVERLOAD`, `_PROVISIONING`, or `_REPAIR`, move that final word into parentheses at the end of the display label.

Worked examples:

- `METRIC_NAME_DURATION_P50` → strip prefix → `DURATION_P50` → spaces → `DURATION P50` → title-case (P50 stays all-caps) → `Duration P50` → no polish needed → no qualifier suffix → **`Duration P50`**.
- `METRIC_NAME_FAILURES_PER_THOUSAND_QUERIES` → strip prefix → spaces → title-case → `Failures Per Thousand Queries` → no polish → no qualifier → **`Failures Per Thousand Queries`**.
- `METRIC_NAME_AVG_PERCENT_OF_TIME_QUEUED_OVERLOAD` → strip prefix → spaces → title-case → `Avg Percent Of Time Queued Overload` → polish (`Avg` → `Average`, `Percent` → `%`) → `Average % Of Time Queued Overload` → parenthesize `_OVERLOAD` → **`Average % Of Time Queued (Overload)`**.

### UNSPECIFIED variants — drop the row

Every proto3 enum has a zero-value sentinel ending in `_UNSPECIFIED` (e.g. `METRIC_NAME_UNSPECIFIED`, `TABLE_EVENT_STATUS_UNSPECIFIED`, `WAREHOUSE_EVENT_STATE_UNSPECIFIED`). When the suffix after the type-name prefix equals `UNSPECIFIED`, drop the row entirely — do **not** humanize, do **not** surface as a real metric/event/state. UNSPECIFIED is the proto3 default-zero sentinel and indicates upstream data was not populated; treat the row as absent. Apply this check **before** the 5-step humanization rule fires.

### Unrecognized prefix — drop the row

Proto enums forward-compatibly add new prefixes as the FE schema grows. If a value's prefix does **not** match one of the six prefixes listed above, drop the row entirely. Do **not** attempt to humanize an unrecognized-prefix value — partial humanization risks misleading the user. Surface only what the skill is sure about.

### Pattern-matching by prefix-shape, not by value

When gating logic depends on which enum a value belongs to, phrase the rule in prefix-shape terms ("any `WAREHOUSE_EVENT_NAME_`-prefixed event whose timestamp aligns with a metric shift") rather than enumerating specific values — proto enums grow over time, and value-enumeration drifts.

## Step Details

### Step 1: Parse the Payload

The Performance Explorer page snapshot is registered as a `get_page_context` provider rather than embedded in the user message. **Invoke the `get_page_context` tool once at the start of this step** to retrieve the snapshot, then extract the following fields (use only what is present — do not fabricate missing values):

- **Filters**: `metadata.filters` — JSON-stringified `{warehouses, databases, roles}` arrays. Frame all observations within this scope.
- **Time range**: `metadata.timeRange` — JSON-stringified `{current: {from, to}, previous: {from, to}}`. Use both periods to frame change-over-time language. When surfacing dates in user-facing output, render in human-readable form (e.g. `May 5–8, 2026` or `May 5 – May 12, 2026`) — do **not** reproduce raw ISO timestamps from the payload. When the current and previous spans are equal in length and adjacent, phrase as `the last 7 days` (or equivalent) rather than two separate ranges.
- **Health metrics**: `metadata.healthMetrics` — JSON-stringified array of `{metric, value, previousValue, changePercent}`. The `metric` field carries `METRIC_NAME_`-prefixed values (see [`../../references/data_contract.md` § Expected Fields — Performance Explorer](../../references/data_contract.md) for the canonical list). Humanize via the algorithmic rule below before user-facing display. The numeric `value` is the current period; `previousValue` is the prior period. Pre-aggregated; do not recompute.
- **Top tables**: `metadata.topTables` — JSON-stringified array of `{name, id?, databaseName?, schemaName?, value, previousValue, changePercent}`. Flat-value rows — the FE-selected ranking metric is **not** flowed through to the skill. Do not infer which metric the FE used to rank these rows.
- **Top warehouses**: `metadata.topWarehouses` — JSON-stringified array of `{name, value, previousValue, changePercent}`. The schema carries no metric label per row — the FE-selected ranking metric for the panel is **not** flowed through to the skill. Do not infer a metric from `healthMetrics` or surrounding context; treat the row as a directional change reading only.
- **Table events**: `metadata.tableEvents` — JSON-stringified array of `{tableName, operation, status, type?, timestamp}`. `operation` carries `TableEventOperationType` proto-enum values prefixed `TABLE_EVENT_OPERATION_TYPE_`; `status` carries `TableEventStatus` values prefixed `TABLE_EVENT_STATUS_` (note: the failure value is `TABLE_EVENT_STATUS_FAIL`, not `_FAILED`); `type` carries `TableEventTableType` values prefixed `TABLE_EVENT_TABLE_TYPE_`. Use as a cross-correlation anchor in `### Notable patterns` and `### Cross-dimensional insights` — e.g. a `TABLE_EVENT_OPERATION_TYPE_CLUSTER` event whose `timestamp` aligns with a `topTables` row's `changePercent` shift can anchor a cross-dimensional insight. Do not enumerate events on their own; they only surface when paired with a metric/entity signal in the same window. Humanize each enum value via the algorithmic rule below before user-facing display.
- **Warehouse events**: `metadata.warehouseEvents` — JSON-stringified array of `{warehouseName, eventName, state, timestamp}`. `eventName` carries `WarehouseEventName` proto-enum values prefixed `WAREHOUSE_EVENT_NAME_`; `state` carries `WarehouseEventState` values prefixed `WAREHOUSE_EVENT_STATE_`. Use as a cross-correlation anchor in `### Notable patterns` and `### Cross-dimensional insights` — e.g. a warehouse resize event whose `timestamp` aligns with a `topWarehouses` row's `value` shift, or an event-cadence aligned with a `healthMetrics` anomaly window, can anchor a notable pattern or cross-dimensional insight. Do not enumerate events on their own; they only surface when paired with a metric/entity signal in the same window. Humanize each enum value via the algorithmic rule below before user-facing display.
- **Truncation marker** (wire-format spec — `…truncated` ellipsis sentinel and empty-fallback `[]` / `{}` swap — at [`../../references/data_contract.md` § Expected Fields — Performance Explorer](../../references/data_contract.md)): treat empty / near-empty sections defensively, applying the empty-section recipe rather than a truncation note. If the marker IS present, emit a single bolded `**Note:**` line immediately after the affected user-facing section heading (mirroring the sibling `ui-query-history` PAGINATED note format). Two variants by field-shape:

  - **Ranked** fields (`healthMetrics`, `topTables`, `topWarehouses`) carry magnitude-ordered entries; truncation drops the smaller ones. Verbatim: `**Note:** The underlying ` + backtick-wrapped `metadata.<sectionName>` + ` data is bounded — only the largest entries are surfaced.`
  - **Event** fields (`tableEvents`, `warehouseEvents`) carry time-ordered events; truncation drops events at the wire-format cap, not by magnitude. Verbatim: `**Note:** The underlying ` + backtick-wrapped `metadata.<sectionName>` + ` data is bounded — some events from the window may not be available for cross-correlation.`

  The `<sectionName>` placeholder resolves to the **field-name suffix only** (e.g. `topTables`, `healthMetrics`, `tableEvents`) — no leading `metadata.` — so that literal substitution into `metadata.<sectionName>` yields the rendered backtick token `metadata.topTables`, not the user-facing section title. Section-mapping (which user-facing heading the Note attaches under, given which `metadata.*` field is truncated):

  | Truncated `metadata.*` field | Attach `**Note:**` after this heading | Variant |
  |---|---|---|
  | `metadata.healthMetrics` | `## What's going well` | Ranked |
  | `metadata.topTables` / `metadata.topWarehouses` | `## What may be concerning` | Ranked |
  | `metadata.tableEvents` / `metadata.warehouseEvents` | `## What may be concerning` | Event |

  If multiple `metadata.*` fields are truncated, emit one `**Note:**` per affected user-facing section heading **per variant** (not per truncated field) — when both `topTables` and `topWarehouses` are truncated, a single Ranked Note under `## What may be concerning` covers both; if `tableEvents` is also truncated in the same payload, emit a separate Event Note under the same heading. If an FE-truncated section then collapses to `[]` / `{}`, the empty-section recipe wins — do **not** stack the truncation `**Note:**` line on top of an empty-section sentence.

Each `metadata.*` field is capped before attachment per the FE-side Snowsight page-context bridge contract — see [`../../references/data_contract.md` § Expected Fields — Performance Explorer](../../references/data_contract.md) for the cap value.

Work strictly from the provided data once `get_page_context` returns. Do **not** query Snowflake or call any other tools to fetch additional information. (This is Phase 1.1 — backend access lands in Phase 1.2.)

### Step 2: Analyze

Apply the **Discipline Rules** in the `## Discipline Rules` section of this SKILL.md before identifying any signal. In particular:

- Suppress observations that would require fabricating a metric the payload does not carry (most acutely: per-query credits or bytes-scanned rankings — Phase 1.1 PE payload does NOT carry these per-query, so any "most expensive query" framing is off-limits).
- Anchor every quantitative claim in a `metadata.*` field. If a desired claim has no anchor, fall back to the empty-section recipe rather than inventing a number.
- Treat `topTables` rows as flat-value entries; do NOT split them into metric-distinct sub-categories (Poorly Clustered, Most Scanned, Stale/Unused, Growth Anomalies). Tables surface as severity-table rows by their own `value` reading and `changePercent`.

Using the extracted data, identify:

- **Verdict**: a high-level health reading derived from `healthMetrics` magnitudes / signs and the spread of `changePercent` values. Pattern: aggregate metrics may look healthy while localized signals (specific warehouses, specific tables) are degraded — call that contradiction out explicitly.
- **Most impactful finding**: the single most consequential entity / signal worth surfacing — the largest-magnitude `changePercent`, the highest-error warehouse, or the most-scanned table. Pick one; don't itemize.
- **What's working**: positive readings in `healthMetrics` (low overloaded %, low blocked %, stable median duration, predictable throughput).
- **What's concerning**: entries from `topWarehouses` / `topTables` whose `value` and `changePercent` indicate a problem the payload directly anchors — undersized warehouses (where `healthMetrics` shows high spill / high error rate at the account level) and hotspot tables (high `changePercent` on the row's flat `value` reading; do not infer or assert which metric the FE selected for the panel — `topTables` carries no metric label per row, same as `topWarehouses`).
- **Notable patterns**: cross-cutting observations — error concentration in a small subset of warehouses, spill cost vs. compute upsize trade-offs, burst cadences, stable-median-vs-volatile-tail patterns, single-entity dominance, event-cadence-vs-anomaly alignment (where `tableEvents` / `warehouseEvents` timestamps align with shifts in `topTables` / `topWarehouses` / `healthMetrics`).
- **Cross-dimensional insights**: correlations where BOTH sides are anchored in the payload — e.g. a `tableEvents` / `warehouseEvents` entry whose `timestamp` aligns with a `topTables` / `topWarehouses` row's reading change. Do not assume a metric for a `topWarehouses` row that the schema does not state. Drop any correlation row whose second side is unsourced; an event without a paired metric/entity shift is single-sided and does not qualify.
- **Recommended action plan**: a prioritized set of next-steps that traces back to entities or patterns surfaced above. Don't introduce new entities here; every action references something already discussed. Order by combination of impact (magnitude of the underlying anomaly) and effort (low-effort fixes go first within a tier).

Severity-tier (High / Medium / Low) and priority-tier (Immediate / Short-term / Long-term) assignments are derived from the **magnitude** of the underlying readings (`changePercent`, absolute counts, spread relative to other entries in the same panel) — there are no fixed numerical thresholds. Use proportional judgment, and prefer giving the user a clear hierarchy of magnitude over rigid bucketing.

Derive only what the data supports. Do not infer causes or assign blame to factors not visible in the payload.

### Step 3: Generate Output

Produce the output as a markdown document with exactly **four `##` (h2) sections** in this order: `## Overall health`, `## What's going well`, `## What may be concerning`, `## Recommended action plan`. Emit a `---` horizontal-rule divider on its own line between each consecutive pair of top-level `##` sections (three dividers total) so the sections render visually separated. **Five** additional `###` (h3) sub-headings render nested under their parent h2 per the prototype's compact-sub-heading hierarchy:

- `### {emoji} {verdict}` and `### Most impactful finding` nest under `## Overall health`
- `### Anomalies`, `### Notable patterns`, and `### Cross-dimensional insights` nest under `## What may be concerning`

Each section's structure (sub-headings, lead-in paragraph length, table headers, row counts) is specified verbatim — match the prototype's register and tone. Tables hard-cap at 5 rows.

When a section has no qualifying data, apply the **empty-section recipe** (see `## Discipline Rules` for the literal table shape) — never drop the heading, never fabricate rows. The three table sub-sections under `## What may be concerning` keep their column-header row and carry a **fixed canonical string** in the first cell of a single data row (remaining cells blank): `### Anomalies` → `No concerns found`; `### Notable patterns` → `No notable patterns found`; `### Cross-dimensional insights` → `No cross-dimensional insights found`. The other two sections (`## What's going well`, `## Recommended action plan`) keep a single brief prose sentence acknowledging the absence.

---

## Overall health

### {emoji} {verdict-as-noun-phrase}

Render the verdict as a compact `###` sub-heading where the emoji follows directly after the heading marker. **Emit the heading VERBATIM character-for-character** — `###` then a single space, then the emoji, then a single space, then the verdict noun-phrase.

```
### ✅ Healthy
### ⚠️ Has concerns
### 🚨 Critical
```

Pick exactly one of the three:

- `### ✅ Healthy` — aggregate and localized signals are both clean
- `### ⚠️ Has concerns` — aggregate metrics look healthy but localized signals are degraded, OR vice versa
- `### 🚨 Critical` — multiple aggregate metrics are degraded with no compensating positive signal

**Never emit `✅ Healthy` (or any verdict) for a no-data payload.** The §Stopping Points no-results condition should have already halted the skill in Step 1. As defense-in-depth: if you reach this point with `healthMetrics` / `topTables` / `topWarehouses` all empty, emit the §Stopping Points no-results message instead of a verdict — an empty workload is *no data*, not health.

Body: 1 sentence stating the high-level verdict and the root reason. Pattern:

> While {aggregate metric reading from `healthMetrics`} looks healthy, {contradicting localized signal from `topWarehouses` / `topTables`} indicates {verdict reason}.

Make clear the readings come from the Performance Explorer page snapshot for the time window in `metadata.timeRange`.

### Most impactful finding

Body: 1 sentence calling out the single most consequential finding. Reference the entity by its backtick-wrapped name from the payload, include 1–2 quantitative anchors (counts, percentages — bold the absolute counts and percentages), and frame the interpretation with "suggesting {hypothesis}" rather than asserting cause.

---

## What's going well

1 paragraph lead-in (1–3 sentences): positive framing about what IS working. Use the "concentrated rather than systemic" framing or an equivalent when the issues are localized. Emphasize stable baselines and healthy concurrency / throughput readings. Sample register:

> The workload is fundamentally healthy — concurrency metrics are near-zero and improving, and median latency is stable across the window. The remaining issues are isolated, not systemic.

Then a 2-column table with headers `Area` and `Signal` (5 rows recommended, 5 rows hard cap):

| Area | Signal |
|------|--------|
| {humanized area-name derived from `healthMetrics.metric` via the algorithmic rule in §Canonical Enum Strings and Humanization, or a derived cross-cutting dimension} | {quantitative reading + 1-clause interpretation} |
| ... | ... |

Area cells show display labels — never the wire-format canonical-prefix string. Apply the 5-step algorithmic rule to every `healthMetrics.metric` value before placing it in this column. Each `Signal` cell pairs a quantitative reading (with bold absolute counts / percentages) and a one-clause interpretation. Drop the table entirely (and use the empty-section recipe) only if no positive readings exist in `healthMetrics`.

---

## What may be concerning

1 paragraph lead-in (2–3 sentences): describe the concerning state with cause→effect chains and "concentrated rather than systemic" framing. Sample register:

> The workload is in a degraded but manageable state — {a few X}, {recurring Y}, and {one Z} are creating cascading effects ({X → Y, A → B}) that compound each other. The problems are concentrated rather than systemic, and the fixes are well-defined and cost-justified.

When no concerning entities surface (all of `### Anomalies` / `### Notable patterns` / `### Cross-dimensional insights` are empty), do **not** emit the degraded-state framing above — replace the lead-in with a single neutral sentence (e.g. "No concerning entities surfaced for this time window.") before the empty sub-sections.

### Anomalies

A 5-column severity table with headers `Severity`, `Focus Area`, `Entity`, `Issue`, `Recommendations` (1–5 rows; order rows High → Medium → Low):

| Severity | Focus Area | Entity | Issue | Recommendations |
|----------|------------|--------|-------|-----------------|
| 🔴 High | Warehouse | `{warehouse-name}` | {1–2 sentences naming the metric anomaly + a hypothesis} | {1 sentence concrete next-step} |
| 🟠 Medium | Table | `{table-name}` | ... | ... |

Severity emoji prefixes: `🔴 High`, `🟠 Medium`, `🟡 Low`. Focus Area: `Warehouse` / `Table` (the dimension the entity belongs to). Entity: backtick-wrapped name from the payload (warehouse name or table name).

Severity is assigned by **magnitude judgment** — proportional to the size of the `changePercent` and absolute `value`, with the High / Medium / Low buckets giving the user a hierarchy of attention. There are no fixed numerical thresholds; pick the bucket that proportionally reflects the entity's standing relative to its peers in the same panel.

All metric / event / state names rendered in the `Issue` column use display labels per the §Canonical Enum Strings and Humanization rule — never the wire-format canonical-prefix names.

If no concerning entities exist, apply the empty-section recipe — keep the header row and emit a single data row with `No concerns found` in the first (`Severity`) cell and the remaining four cells blank.

### Notable patterns

A 2-column table with headers `Pattern` and `Description` (1–5 rows; 3–5 rows typical):

| Pattern | Description |
|---------|-------------|
| {short noun phrase} | {1–2 sentences — quantitative observation + interpretation} |
| ... | ... |

When fewer than 3 anchored rows are derivable, emit only the rows the data supports; when zero are derivable, apply the empty-section recipe.

Patterns are short noun phrases like "Error concentration", "Spill-cost mismatch", "Burst-failure cadence", "Stable baseline, volatile tail", "Single-entity dominance". Descriptions follow patterns such as:

- "**{N}**+ of all {thing} come from {subset of entities} — {implication}"
- "{entity} {metric reading} yet {contradiction}, {interpretation}"
- "{entity} {metric} repeats every {cadence} aligned with {co-cadence} — strongly suggests {hypothesis}"

Drop rows whose interpretation would require an unsourced inference. If no patterns are derivable from the rows alone, apply the empty-section recipe — keep the header row and emit a single data row with `No notable patterns found` in the first (`Pattern`) cell and the `Description` cell blank. All metric / event / state names rendered in this table use display labels per the §Canonical Enum Strings and Humanization rule — never the wire-format canonical-prefix names.

### Cross-dimensional insights

A 2-column table with headers `Cross-dimensional insight` and `Dimensions linked` (1–5 rows; 3–5 rows typical):

| Cross-dimensional insight | Dimensions linked |
|---------------------------|-------------------|
| {short noun phrase OR arrow-chained narrative — e.g. "{entity} errors → failure burst spikes → retry growth"} | {1–2 sentences naming which dimensions correlate, with cause/effect interpretation} |
| ... | ... |

When fewer than 3 anchored rows are derivable, emit only the rows the data supports; when zero are derivable, apply the empty-section recipe.

Only emit a row when **both** sides of the correlation are anchored in the payload. Drop rows that would require unsourced inference. If only one side of every candidate correlation is anchored (or none are), apply the empty-section recipe — keep the header row and emit a single data row with `No cross-dimensional insights found` in the first (`Cross-dimensional insight`) cell and the `Dimensions linked` cell blank. All metric / event / state names rendered in either column (including arrow-chained narratives) use display labels per the §Canonical Enum Strings and Humanization rule — never the wire-format canonical-prefix names.

---

## Recommended action plan

A 4-column table with headers `Priority`, `Action`, `Impact`, `Effort` (1–5 rows; 3–5 rows typical; order rows Immediate → Short-term → Long-term):

| Priority | Action | Impact | Effort |
|----------|--------|--------|--------|
| Immediate | {1–2 sentences naming the specific change; reference entities by backtick-wrapped name} | {1–2 sentences quantifying the expected improvement} | {qualitative scale `Low` / `Medium` / `High` + 1-sentence concrete reason} |
| Short-term | ... | ... | ... |
| Long-term | ... | ... | ... |

When fewer than 3 anchored actions are derivable, emit only the rows the data supports; when zero are derivable (no concerning entities or patterns surfaced in earlier sections), apply the empty-section recipe.

Each action must trace back to a concerning entity or pattern surfaced in earlier sections. Do not introduce a new entity here that wasn't already discussed. Effort follows the format `Low — single ALTER WAREHOUSE statement.` (qualitative label + em-dash + concrete reason). All metric / event / state names rendered in the `Action` column use display labels per the §Canonical Enum Strings and Humanization rule — never the wire-format canonical-prefix names.

---

## Discipline Rules

- **No fabrication.** Every quantitative claim must trace to a `metadata.*` field. If the payload does not carry it, apply the empty-section recipe rather than inventing a number, an entity name, or a metric. This includes credit / bytes-scanned rankings (which Phase 1.1 PE payload does NOT carry per-query) and per-row metric labels for `topWarehouses` and `topTables` (both flat-value schemas — neither carries a per-row metric label, and the FE-selected ranking metric for the panel is not flowed through to the skill).
- **No raw canonical strings in output.** Canonical-prefix enum strings (`METRIC_NAME_*`, `TABLE_EVENT_OPERATION_TYPE_*`, `TABLE_EVENT_STATUS_*`, `TABLE_EVENT_TABLE_TYPE_*`, `WAREHOUSE_EVENT_NAME_*`, `WAREHOUSE_EVENT_STATE_*`) are wire-format identifiers. They MUST be humanized via the 5-step rule in §Canonical Enum Strings and Humanization before appearing in any user-facing output — section heading, table cell, prose sentence, arrow chain, or bullet. If a value cannot be humanized (unrecognized prefix, or an `UNSPECIFIED` suffix), drop the row rather than emit the raw string.
- **Drop UNSPECIFIED variants.** When the suffix after the type-name prefix equals `UNSPECIFIED` (e.g. `METRIC_NAME_UNSPECIFIED`, `WAREHOUSE_EVENT_STATE_UNSPECIFIED`), drop the row entirely — do NOT humanize, do NOT surface as a real metric / event / state. UNSPECIFIED is the proto3 default-zero sentinel and indicates upstream data was not populated.
- **Drop unrecognized-prefix values.** If a value's prefix does not match one of the six prefixes listed in §Canonical Enum Strings and Humanization, drop the row entirely. Do NOT attempt partial humanization — proto enums forward-compatibly add new prefixes, and surfacing a guessed label risks misleading the user.
- **Empty-section recipe.** When a section has no qualifying data, never drop the heading and never fabricate rows. The three table sub-sections under `## What may be concerning` preserve the table's column-header shape: emit the header row + one data row whose first cell carries the canonical empty-state string and whose remaining cells are blank — e.g. for `### Anomalies`:
  ```
  | Severity | Focus Area | Entity | Issue | Recommendations |
  |----------|------------|--------|-------|-----------------|
  | No concerns found |  |  |  |  |
  ```
  Canonical strings: `No concerns found` (Anomalies), `No notable patterns found` (Notable patterns, in the `Pattern` cell), `No cross-dimensional insights found` (Cross-dimensional insights, in the `Cross-dimensional insight` cell). The other two sections (`## What's going well`, `## Recommended action plan`) emit a single brief prose sentence instead.
- **Performance Explorer data-source tagging.** Make clear in the `## Overall health` verdict, and at any point where the user could mistake the data for Query History, that the readings come from the Performance Explorer page snapshot for the time window in `metadata.timeRange` — a single time window, not cross-account telemetry and not individual query records. Render `metadata.timeRange.current` / `.previous` dates in human-readable form (e.g. `May 5–8, 2026`) — do not reproduce raw ISO timestamps.
- **Phase 1.1 scope limits.** Beyond the initial `get_page_context` invocation in Step 1, do not call any tools to fetch additional data. Do not query Snowflake. Work strictly from the provided payload. Backend access lands in Phase 1.2.
- **Tables hard-cap at 5 rows.** When more than 5 candidate rows exist, keep the top 5 by severity / impact and drop the rest.
- **Output length.** Target 2–3 screenfuls of dense content for the emitted analysis (the condensed variant is roughly half the length of the verbose variant). Tighten lead-ins and trim table rows to honor this budget when more content is available than fits.
- **Register / tone.** Em-dash heavy for cause/effect. Named entities in backticks. Bold absolute counts and percentages (e.g. **8.8K errors**, **3,371%**, **60%**). Cause→effect arrows (`spill → P99 latency`, `errors → retries`) when chaining related findings. "Concentrated rather than systemic" when issues are localized. "Suggesting {hypothesis}" framing for interpretations. Declarative voice — no hedging like "might be" or "could potentially".

## Output

The final user-facing output is a markdown document with exactly **four** `##` (h2) sections in order: `## Overall health`, `## What's going well`, `## What may be concerning`, `## Recommended action plan`, separated by `---` horizontal-rule dividers. **Five** additional `###` h3 sub-headings render nested under their parent h2 per the prototype's compact-sub-heading hierarchy: `### {emoji} {verdict}` and `### Most impactful finding` under `## Overall health`; `### Anomalies`, `### Notable patterns`, and `### Cross-dimensional insights` under `## What may be concerning`. The `## Discipline Rules` (above) and `## Success Criteria` (below) sections are SKILL-INTERNAL — they govern how the LLM produces output but are NOT emitted in the user-facing output.

## Success Criteria

- All four required h2 sections (`## Overall health`, `## What's going well`, `## What may be concerning`, `## Recommended action plan`) are emitted in the specified order.
- Five h3 sub-headings render nested under their parent h2: `### {emoji} {verdict-as-noun-phrase}` and `### Most impactful finding` under `## Overall health`; `### Anomalies`, `### Notable patterns`, and `### Cross-dimensional insights` under `## What may be concerning`.
- The `### {emoji} {verdict-as-noun-phrase}` heading is verbatim — single space after `###`, emoji, single space, noun phrase.
- Every quantitative claim traces directly to a `metadata.*` field — no fabricated counts, percentages, entity names, or rankings.
- `topWarehouses` and `topTables` entries are not assigned a metric label — both flat-value schemas, and neither carries a per-row metric label nor flows the FE-selected ranking metric through to the skill.
- Empty table sub-sections (Anomalies / Notable patterns / Cross-dimensional insights) preserve the column-header row and carry the canonical empty-state string in the first cell of a single data row, remaining cells blank (`No concerns found` / `No notable patterns found` / `No cross-dimensional insights found`) — not dropped, not fabricated, not a headerless line. `## What's going well` and `## Recommended action plan` keep a brief prose acknowledgment.
- The data-source attribution in `## Overall health` makes clear the readings come from the Performance Explorer page snapshot for a single time window.
- All tables hard-cap at 5 rows.
- Severity rows in `## What may be concerning` are ordered High → Medium → Low; priority rows in `## Recommended action plan` are ordered Immediate → Short-term → Long-term.
- Named entities (warehouse, table) are wrapped in backticks; absolute counts and percentages are bolded.
- No `METRIC_NAME_*` / `TABLE_EVENT_OPERATION_TYPE_*` / `TABLE_EVENT_STATUS_*` / `TABLE_EVENT_TABLE_TYPE_*` / `WAREHOUSE_EVENT_NAME_*` / `WAREHOUSE_EVENT_STATE_*` canonical-prefix strings appear in user-visible output — every enum value is humanized via the 5-step rule before display, and unrecognized-prefix or `*_UNSPECIFIED` rows are dropped rather than surfaced.
- Date ranges from `metadata.timeRange` are rendered in human-readable form (e.g. `May 5–8, 2026`) — never as raw ISO timestamps.
- No backend / Snowflake queries are issued by this skill (beyond the initial `get_page_context` invocation in Step 1).
- Top-level `##` sections are separated by `---` horizontal-rule dividers.
- A payload with no analyzable data for the selected filters (all sections — `healthMetrics` / `topTables` / `topWarehouses` — empty) yields a brief "No Performance Explorer results found" message and NO verdict — never `✅ Healthy`.
