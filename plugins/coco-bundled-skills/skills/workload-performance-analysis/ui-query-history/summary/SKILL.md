---
name: workload-performance-analysis/ui-query-history/summary
description: "Analyze a pre-provided query history payload from the Snowflake Query History UI page and produce a structured five-section report."
---

**Loaded only when source=UI_QUERY_HISTORY (queryHistoryListContext payload present in system-reminder).**

# Query History Summary

Analyze a pre-provided query history payload from the Snowflake Query History UI page and produce a structured five-section report.

## When to Use

This skill is designed exclusively for use from the **Query History UI page** via the "Analyze with CoCo" button. It expects a pre-provided summary payload — a structured list of query records — to be present in the context before it can produce any output.

**Do NOT invoke this skill from general conversation.**

If the user invokes this skill outside of the Query History page context (i.e., no query history payload is present), stop and inform them:

> This skill is designed to be used from the Query History page in the Snowflake UI via the "Analyze with CoCo" button. It requires the query history payload that the page provides automatically. To use it, navigate to the Query History page and click "Analyze with CoCo" — the necessary data will be included automatically.

## Stopping Points

| Point | Condition | Action |
|-------|-----------|--------|
| Before Step 1 | No query history payload is present in context | Inform the user this skill requires the Query History page context (see "When to Use" above). Stop and do not proceed. |

## Step Details

### Step 1: Parse the Payload

The query history payload is pre-provided in the context. Extract the following fields from the records (use only what is present — do not fabricate missing values):

- **Applied filters**: the full list of filters active when this payload was generated (e.g., user, warehouse, status, statement type, min duration, query tag, SQL text, query ID, session ID, query hash, internal queries only, user tasks only, scheduled replication tasks only). Extract these before anything else — they define the scope of all other fields.
- **Date range**: the start and end timestamps of the query window if present; use these to frame all time-relative observations in the output.
- **Page limit indicator**: whether the payload contains "PAGINATED: true". This flag means the payload contains only the queries currently loaded on the Query History page, not the full set of queries matching the filters. To analyze the complete result set, the user must first load all queries in the UI. (Note: this is distinct from "truncated SQL text" elsewhere in the payload, which refers to SQL strings being shortened for display.)
- **Query counts**: total queries, breakdown by status (`SUCCESS`, `FAILED`, `RUNNING`, `QUEUED`, other)
- **Duration**: total, average, min, and max duration — extract these directly from the pre-aggregated duration metrics in the payload
- **Data volume**: total and average bytes scanned — extract these directly from the pre-aggregated data volume metrics in the payload
- **Warehouses**: which warehouses were used and how many queries ran on each
- **Users**: which users submitted queries (if present)
- **Failed queries**: query IDs, truncated SQL text, and error messages for any `FAILED` status queries
- **Slow queries**: for each of the top slowest queries — query ID, truncated SQL text, elapsed time, user, warehouse, and rows returned (use only fields present; do not fabricate missing values)
- **Resource-intensive queries**: for each of the top queries by bytes scanned — query ID, truncated SQL text, bytes scanned, duration, and warehouse (use only fields present; do not fabricate missing values)

Work strictly from the provided data. Do not query Snowflake or look up additional information.

### Step 2: Analyze

Before identifying any patterns, internalize the active filters and page limit status from Step 1. Any concentration or uniformity along a filtered dimension is an artifact of the filter, not a meaningful signal — do not flag it as a pattern or anomaly.

If the payload contains "PAGINATED: true" (meaning only the queries currently loaded on the UI page are included), treat all aggregate statistics and "top N" lists as reflecting only the queries visible on the page, not the full filtered result set — do not draw conclusions about the overall workload that the data cannot support.

| Active filter | Observations to suppress |
|---|---|
| User filter | Do not flag single-user load concentration |
| Warehouse filter | Do not flag single-warehouse load concentration or skew |
| Status filter | Do not treat the status breakdown as representative of the full workload |
| Min duration filter | Do not treat average/min duration as representative; note the data excludes queries below the threshold and state the threshold value (e.g., "excludes queries shorter than 5.0s") |
| SQL text filter | All queries match the filtered SQL pattern — do not flag SQL similarity as a meaningful pattern |
| Query ID filter | Result is scoped to a single specific query — aggregate statistics and pattern observations are not meaningful |
| Session ID filter | All queries came from the same session — do not flag single-session concentration |
| Query hash filter | All queries share the same normalized SQL structure — do not flag SQL similarity as a meaningful pattern |
| Query tag filter | No per-tag dimension data is present in the payload — no pattern suppression needed beyond surfacing the filter in the overview |
| Statement type filter | No per-type distribution data is present in the payload — no pattern suppression needed beyond surfacing the filter in the overview |
| Internal queries only / User tasks only / Scheduled replication tasks only | Scope all pattern observations to that query population; do not generalize |

Using the extracted data, identify only observations that are **not** explained by an active filter:

- **Patterns**: Are queries concentrated on a specific warehouse or user, or is multi-warehouse load significantly skewed — where those dimensions are not already constrained by a filter?
- **Bottlenecks**: Are there queries with disproportionately high elapsed time or bytes scanned relative to the rest of the set?
- **Anomalies**: Are there failures, unusually long-running queries, or outliers in data volume?

Derive only what the data supports. Do not infer causes or assign blame to factors not visible in the payload.

### Step 3: Generate Output

Produce the output as a markdown document with exactly five headed sections in the order below.

CRITICAL: Use `##` (h2) markdown headings for "What these queries show", "Performance metrics", and "Notable patterns". Use **bold text** labels (NOT `##` headings) for "Longest-running queries:" and "Queries that are most resource intensive:" so they match the size of "Top warehouses by query count:". Place `---` horizontal rules for visual spacing where indicated.

See the FORMAT TEMPLATE at the end of this prompt for the exact structure. Follow the formatting rules.

---

## What these queries show

If any filters were active, open with a single line reproducing the filter names and values exactly as they appear in the payload, with the label rendered in bold markdown. Example: "**Filters applied:** Status: FAILED, User: john.doe, Warehouse: COMPUTE_WH, Min duration: 5.0s." Omit this line if no filters were applied.

If the payload contains "PAGINATED: true" (only the queries currently loaded on the page are in the payload), output this line immediately after the section heading (using markdown bold with double asterisks): `**Note:**` This summary covers the `**N**` queries currently loaded on the Query History page. To analyze all queries matching your filters, load additional queries in the UI and re-run the summary. Replace N with the query count from the PAGINATED line. Wrap "Note:" in double asterisks and wrap the number in double asterisks so they render bold. Omit this line only if PAGINATED is not present.

Write 2–3 sentences that give an immediate high-level health signal. Cover:

- Total number of queries and the date range they span
- Whether there are any failures or severe outliers (e.g., "3 queries failed", "1 query accounted for the majority of total elapsed time")
- Which warehouses were involved

This section answers "should I be concerned?" before the user reads anything else.

---

## Performance metrics

Present aggregate statistics in a compact, scannable layout. Use pipe `|` as the separator between items on the same line (not commas):

- **Query counts**: total queries and a breakdown by status. Example: `Total: 499 | SUCCESS: 491 | FAILED: 8`. If a status filter is active, note that the breakdown reflects only the filtered status, not the full workload.
- **Duration**: total elapsed time, average duration, min, max. When the payload provides duration as pre-formatted strings (e.g., `"2m 41s"`, `"~19h 7m"`), use them verbatim. When the payload provides raw milliseconds, convert to human-readable compound format (e.g., `2m 41s` for per-query; prefix aggregate totals with `~`, e.g., `~19h 7m`). Example with pre-formatted payload: `Total: ~19h 7m | Average: 4h 47m | Min: 12s | Max: 11h 3m`. If a min duration filter is active, note that these statistics exclude queries shorter than the threshold and state the threshold value.
- **Data volume**: total bytes scanned and average per query. Example: `Total: 1.50 GB | Average: 115.66 MB per query`. Format in KB/MB/GB as appropriate.
- **Top warehouses by query count**: a table listing the warehouses shown in the payload and their query counts. Use plain text in table cells (no backticks). If a warehouse filter is active, append "(filtered)" to the table header. Example:
  ```
  | Warehouse  | Queries |
  |------------|---------|
  | COMPUTE_WH | 42      |
  | DEV_WH     | 8       |
  ```
- **Top users by query count**: a table listing the users shown in the payload and their query counts. Use plain text in table cells. Always show this table even when a user filter is active — it will list the 1 filtered user. Example:
  ```
  | User      | Queries |
  |-----------|---------|
  | SYSTEM    | 342     |
  | TEST_USER | 50      |
  ```

---

**Longest-running queries:**

Present all provided slowest queries as a compact table. Include Query ID, Duration, and SQL columns. Also include User, Warehouse, and Rows columns if those fields are present in the payload. Use plain text in table cells. Example:

```
| Query ID | Duration | SQL                                                      |
|----------|----------|----------------------------------------------------------|
| 01a4...  | 1h 2m    | WITH sandbox_queries AS (SELECT query_id, query_text, ... |
| 01a5...  | 7m 54s   | EXECUTE NOTEBOOK "UI_TEST_DB"."PUBLIC"."CP Replace Test"() |
```

When there are no slowest queries, keep the table header row and emit one data row with 'No slow queries to surface' in the first cell, remaining cells blank.

---

**Queries that are most resource intensive:**

Present all provided resource-intensive queries as a compact table. Include Query ID and SQL columns. Also include Bytes Scanned, Duration, and Warehouse columns if those fields are present in the payload. Use plain text in table cells. Example:

```
| Query ID | SQL                                                           |
|----------|---------------------------------------------------------------|
| 01a4...  | WITH sandbox_queries AS (SELECT query_id, query_text, ...     |
| 01a5...  | WITH customer_purchase_history AS (SELECT u.user_id, ...      |
```

When there are no qualifying resource-intensive queries, keep the table header row and emit one data row with 'No resource-intensive queries to surface' in the first cell, remaining cells blank:

```
| Query ID | SQL |
|----------|-----|
| No resource-intensive queries to surface |  |
```

---

## Notable patterns

Concrete observations about concentration of load, skew, or outliers, presented as a short bulleted list.

Before writing this section, cross-reference all query IDs in the slowest list against all query IDs in the resource-intensive list; if any ID appears in both, call it out explicitly as a dual bottleneck.

If failed queries are present, note whether the listed errors cluster around a single category (e.g., all authorization failures) or span multiple distinct categories (e.g., schema, privilege, data type); this helps prioritize remediation. When the total failed count exceeds the number of listed failed queries, note that the error pattern analysis covers only the visible sample.

**Only include an observation if the dimension it describes is not already constrained by an active filter.** For example, do not note that all queries belong to the same user if a user filter is active, and do not note that all queries ran on the same warehouse if a warehouse filter is active.

---

## Formatting Rules

- Do NOT use backticks or inline code formatting inside table cells or in the failed queries list. Use plain text for query IDs, warehouse names, usernames, and SQL text in those contexts.
- When the payload provides duration as pre-formatted strings, render them verbatim. When the payload provides raw milliseconds, convert to human-readable compound format (e.g., `2m 41s`; prefix aggregate totals with `~`, e.g., `~19h 7m`).
- Always use digits/integers for technical values, measurements, and percentages — including at the start of a sentence. Do not spell out numbers as words for any numerical data.
- Format data volumes in human-readable units: prefer GB, MB, or KB over raw bytes
- Format dates in human-readable form (e.g., `April 5–8, 2024`) rather than reproducing raw ISO timestamps from the payload
- Use pipe `|` as the separator between metrics on the same line (e.g., `Total: 499 | SUCCESS: 491 | FAILED: 8`), not commas
- Work strictly from the provided payload — do not fabricate, infer, or supplement with values not present in the data
- Do not provide recommendations or suggestions unless the user explicitly asks
- Between every two sections, output a `---` horizontal rule on its own line for visual breathing room. See the FORMAT TEMPLATE at the end of this prompt.

## Output

The final output is a markdown document with exactly five sections in order: `## What these queries show`, `## Performance metrics`, `**Longest-running queries:**`, `**Queries that are most resource intensive:**`, `## Notable patterns`.

The first two and last sections use `##` (h2) markdown headings. "Longest-running queries:" and "Queries that are most resource intensive:" use **bold text** labels (NOT `##` headings) to match the size of "Top warehouses by query count:" and "Top users by query count:" labels.

Do NOT include a Failed queries section.

## Success Criteria

- All metrics are derived directly from the provided payload — no fabricated values
- Active filters are stated at the top of the overview when present
- Date range is included in the overview when present in the payload
- If the payload contains "PAGINATED: true", the output includes `**Note:**` with the query count also wrapped in `**...**` in the "What these queries show" section, explaining that the summary covers only the queries currently loaded on the page
- Patterns and anomalies are only reported for dimensions not constrained by an active filter
- Status breakdown and duration statistics are qualified when a status or min duration filter is active; the min duration threshold value is stated explicitly when that filter is active
- Top warehouses table is marked "(filtered)" when a warehouse filter is active
- User distribution table is included in Performance metrics when user data is present
- Overview gives an immediate health signal covering failures, severe outliers, and warehouses involved
- Durations are rendered as provided when pre-formatted; raw milliseconds are converted to human-readable compound format; data volume is formatted in human-readable units (KB/MB/GB)
- Metrics lines use pipe separators, not commas
- Table cells and failed query list entries use plain text, not backticks
- All provided slowest queries are presented as a compact table; when `slowestQueries` is empty, the section preserves the table header row with a single data row: 'No slow queries to surface' in the first cell, remaining cells blank
- All provided resource-intensive queries are presented as a compact table
- When `resourceIntensiveQueries` is empty, the section preserves the table header row with a single data row: 'No resource-intensive queries to surface' in the first cell, remaining cells blank
- Filters line renders the label in bold markdown (`**Filters applied:**`) when filters are present
- Technical values, measurements, and percentages are expressed as digits (not spelled-out words), including at sentence starts
- Query IDs present in both the slowest and resource-intensive lists are identified and called out as dual bottlenecks in Notable patterns
- Error type patterns across the listed failed queries are noted in Notable patterns (single-category vs. multi-category failures); when the total failed count exceeds the listed count, the scope limitation is noted
- No recommendations are included unless explicitly requested by the user

---

## Format Template

IMPORTANT: Follow this structure exactly for section headings, spacing, and formatting. Output the markdown exactly as shown including the double-asterisk bold markers:

```markdown
## What these queries show
**Filters applied:** Status: FAILED, User: john.doe, Warehouse: COMPUTE_WH, Min duration: 5.0s.
**Note:** This summary covers the **250** queries currently loaded on the Query History page. To analyze all queries matching your filters, load additional queries in the UI and re-run the summary.
[2-3 sentence overview]

---

## Performance metrics
[section content including Top warehouses and Top users tables]

**Longest-running queries:**
[table — or empty-state row when no qualifying rows exist:
| Query ID | Duration | SQL |
|----------|----------|-----|
| No slow queries to surface |  |  |
]

**Queries that are most resource intensive:**
[table — or empty-state row when no qualifying rows exist:
| Query ID | SQL |
|----------|-----|
| No resource-intensive queries to surface |  |
]

---

## Notable patterns
[section content]
```

Rules:

- The line starting with `**Note:**` MUST appear if the payload contains "PAGINATED: true". Output it exactly as: `**Note:** This summary covers the **N** queries currently loaded on the Query History page. To analyze all queries matching your filters, load additional queries in the UI and re-run the summary.` The word "Note:" and the number N must each be wrapped in double asterisks for bold rendering. Omit this line only if PAGINATED is absent.
- Use `##` headings for: What these queries show, Performance metrics, Notable patterns.
- Use **bold text** labels for: Longest-running queries, Queries that are most resource intensive.
- Place `---` horizontal rules ONLY after "What these queries show" and after "Queries that are most resource intensive".
- Do NOT include a "Failed queries" section.
