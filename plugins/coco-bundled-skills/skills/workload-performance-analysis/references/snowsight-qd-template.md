# Snowsight Query Details Output Template

This reference defines the exact output format for the UI Query Details summary (presentation_profile=snowsight-card, source=SNOWSIGHT_QD).

## Structure

The output is a markdown document with **2-3 headed sections**:

1. **What this query does** — Business logic summary
2. **How it works** — Technical SQL flow
3. **How it performed** (or **Why this query failed** when status=FAILED) — Performance analysis; always included when query is FAILED, conditional on insights/bottlenecks otherwise

---

## Paragraph 1: What this query does

Reverse-engineer the business question the query answers. Plain-language explanation for non-technical stakeholders:
- What data is being retrieved or computed
- What business question or use case this serves
- What the expected output represents in business terms

Do NOT include technical SQL details.

---

## Paragraph 2: How it works

SQL engineer-level description of logic flow:
- Tables/views accessed
- Join logic and relationships
- Filtering conditions and their purpose
- Aggregations, window functions, CTEs, subqueries
- Overall data flow from source to result

Do NOT include performance details. Focus purely on logical structure.

---

## Paragraph 3: How it performed (conditional)

**Include if** any of these conditions hold: (1) Query Insights were found, (2) performance bottlenecks identified in operator stats, or (3) query status is FAILED. For FAILED queries, always include this section even when no insights/stats are available — surface the errorMessage and errorCode from the payload instead of the assessment table.

This section is strictly **analysis only** -- describe what happened, do NOT provide recommendations.

### Formatting:

- **Check status first:**
  - **FAILED** → heading: **'Why this query failed'**; summary: "The query failed after **{duration}** with: {errorMessage}." + errorCode if present; include assessment table only if insights/bottlenecks also exist; otherwise omit the table.
  - **Succeeded** → heading: **'How it performed'**; summary: "The query completed in **{duration}** processing Y result rows."; if Query Insights found, add: "Query Insights detected **{count}** insights across **{N}** insight types." (or single type variant).
- Format node references as inline code (e.g., `node 3`, `TableScan [5]`)
- When the payload provides duration as a pre-formatted string, render it verbatim. When the payload provides raw milliseconds (`durationMs`), convert to human-readable compound format (e.g., `2m 41s`).
- Always use digits/integers for technical values, measurements, and percentages — including at the start of a sentence. Do not spell out numbers as words for any numerical data.

### Assessment Table

Present 3-5 key findings as a markdown table:

| Assessment | Key Finding | Rationale |
|----------|-------------|-----------|
| ... | ... | ... |

Assessment values (in priority order):
- `🔴 Critical` -- performance problem materially impacting execution (e.g., exploding join, remote spillage from SQL)
- `🟡 Warning` -- potential concern that may worsen (e.g., cold cache on growing table, unselective filter)
- `🟢 Good` -- positive observation or efficient behavior (e.g., high cache hit, efficient join)
- `🔵 Info` -- neutral observation, no immediate impact (e.g., standard scan size)

---

## Recommendations Policy (Strict)

When this template is active (via presentation_profile=snowsight-card):

1. **By default, do NOT provide any recommendations.** Output stops at performance analysis.
2. **If user explicitly asks for recommendations:** provide ONLY the `SUGGESTIONS` field from Query Insights. Do NOT generate, infer, or supplement with own recommendations.
3. **Never provide recommendations based on `GET_QUERY_OPERATOR_STATS` data** even if asked.
4. **If user asks but no Query Insights exist:** "No Query Insights were found for this query; no recommendations available."

---

## Follow-Up Prompt

If Query Insights were found (SQL-actionable or resource insights), append:

> Want me to run a deeper optimization analysis on this query? I can use the `workload-performance-analysis` skill to identify specific improvements.

Do NOT show this prompt if no Query Insights were found.

---

## Success Criteria

- Business logic accurately reflects query intent
- Technical summary covers all data sources, joins, filters, transformations
- When query is FAILED: Paragraph 3 always included with heading **'Why this query failed'**; errorMessage and errorCode (if present) surfaced in the summary; assessment table omitted when no insights/bottlenecks exist
- Performance analysis grounded in actual Query Insights and runtime stats
- Performance analysis is descriptive only -- no recommendations unless explicitly asked
- Recommendations (when requested) come exclusively from SUGGESTIONS field
- No fabricated query UUIDs or hallucinated data
