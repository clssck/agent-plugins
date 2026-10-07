# Snowsight Query History Output Template

This reference defines the exact output format for the UI Query History summary (presentation_profile=snowsight-card, source=SNOWSIGHT_QH).

## Structure

The output is a markdown document with exactly **five sections** in this order:

1. `## What these queries show` (h2 heading)
2. `## Performance metrics` (h2 heading)
3. `**Longest-running queries:**` (bold text label, NOT h2)
4. `**Queries that are most resource intensive:**` (bold text label, NOT h2)
5. `## Notable patterns` (h2 heading)

Place `---` horizontal rules ONLY after "What these queries show" and after "Queries that are most resource intensive".

---

## PAGINATED Banner

If the payload contains `PAGINATED: true`, output this line immediately after the `## What these queries show` heading:

```
**Note:** This summary covers the **N** queries currently loaded on the Query History page. To analyze all queries matching your filters, load additional queries in the UI and re-run the summary.
```

- Wrap "Note:" in double asterisks (`**Note:**`)
- Wrap the number N in double asterisks (`**N**`)
- Omit this line ONLY if PAGINATED is absent

---

## Section Details

### Section 1: What these queries show

- If filters active: open with a line reproducing filter names/values exactly as in payload, with the label rendered in bold: `**Filters applied:** Status: FAILED, User: john.doe, ...`
- If PAGINATED: true: include the **Note:** banner (see above)
- 2-3 sentence high-level health signal covering: total queries, date range, failures/outliers, warehouses involved

### Section 2: Performance metrics

Use pipe `|` as separator between items on same line:

- **Query counts**: total + status breakdown (e.g., `Total: 499 | SUCCESS: 491 | FAILED: 8`)
- **Duration**: total, average, min, max — when payload provides pre-formatted strings, render verbatim; when payload provides raw milliseconds, convert to compound format (e.g., `2m 41s`; prefix aggregate totals with `~`)
- **Data volume**: total + average in KB/MB/GB
- **Top warehouses by query count**: table with Warehouse | Queries columns
- **Top users by query count**: table with User | Queries columns (always show, even with user filter active — lists the 1 filtered user)

### Section 3: Longest-running queries

Bold text label (`**Longest-running queries:**`), then a compact table:
- Columns: Query ID, Duration, SQL (+ User, Warehouse, Rows if present in payload)
- Plain text in cells (no backticks)
- When no slowest queries exist, keep the table header row and emit one data row with 'No slow queries to surface' in the first cell, remaining cells blank

### Section 4: Queries that are most resource intensive

Bold text label (`**Queries that are most resource intensive:**`), then a compact table:
- Columns: Query ID, SQL (+ Bytes Scanned, Duration, Warehouse if present in payload)
- Plain text in cells (no backticks)
- When no qualifying rows exist, keep the table header row and emit one data row with 'No resource-intensive queries to surface' in the first cell, remaining cells blank

### Section 5: Notable patterns

Bulleted list of concrete observations about load concentration, skew, or outliers:
- Cross-reference slowest and resource-intensive lists; call out dual bottlenecks
- Note error category patterns for failed queries
- Only include observations NOT explained by active filters

---

## Formatting Rules

- No backticks/inline code in table cells or failed queries list
- Durations: pre-formatted strings verbatim; raw milliseconds → compound format (e.g., `2m 41s`; aggregate totals prefixed `~`)
- Always use digits/integers for technical values, measurements, and percentages — including at the start of a sentence. Do not spell out numbers as words for any numerical data.
- Data volumes: prefer GB, MB, or KB over raw bytes
- Dates: human-readable form (e.g., `April 5-8, 2024`)
- Use pipe `|` separator between metrics, not commas
- Work strictly from provided payload -- do not fabricate values
- Do NOT provide recommendations unless user explicitly asks
- Do NOT include a "Failed queries" section

---

## Filter Suppression Rules

| Active filter | Observations to suppress |
|---|---|
| User filter | Do not flag single-user load concentration |
| Warehouse filter | Do not flag single-warehouse load concentration or skew |
| Status filter | Do not treat status breakdown as representative |
| Min duration filter | Note data excludes queries below threshold; state threshold value |
| SQL text filter | Do not flag SQL similarity as pattern |
| Query ID filter | Aggregates not meaningful |
| Session ID filter | Do not flag single-session concentration |
| Query hash filter | Do not flag SQL similarity as pattern |
