# Synthesize — aggregate-grain narrative & insights (`LISTAGG` → `AI_COMPLETE`)

Reason over **aggregated rows**, not documents: one `AI_COMPLETE` that turns a corpus of summaries into a
narrative, or a table of metrics into ranked insights + recommended actions. The map step is the deterministic
rollup upstream (`metrics-trend.md` / `summarize-embed.md`); this is the reduce step. Aggregate-grain `FULL` but
cheap (it reads short aggregated rows, never re-touches documents). This file also owns the **shared
context-window / map-reduce mechanics** that `themes-clusters.md`'s taxonomy refers to.

> Read [`../conventions.md`](../conventions.md) first — shapes, refresh contract, the records→aggregate grain shift.

- **Reads** — an aggregate table: `METRIC` (`DT_<prefix>_METRICS`) for insights, or `SUMMARY` (`DT_<prefix>_SUMMARIZED`) for a corpus narrative.
- **Produces** — `DT_<prefix>_INSIGHTS` / `DT_<prefix>_SYNTHESIS` (a narrative + optional structured insights array).
- **Refresh** — **FULL (cheap), or scheduled on a slow lag.** It aggregates every row, so it cannot be
  `INCREMENTAL` — and that's correct; regenerate on the reporting cadence, not per file. `AI_AGG` is banned inside
  DTs — use `LISTAGG → AI_COMPLETE`.

---

## Insights & actions — from metrics

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_INSIGHTS
  TARGET_LAG = '<insights_lag>'   -- a slow reporting cadence (e.g. '1 day'); NOT per-file
  WAREHOUSE = <warehouse>  REFRESH_MODE = FULL  INITIALIZE = ON_SCHEDULE
AS
WITH salient AS (                 -- feed the model only what matters; keeps the call within the context window
  SELECT LISTAGG(
    DIMENSION || ' ' || PERIOD || ': total=' || TOTAL_AMOUNT
      || ', QoQ=' || COALESCE(QOQ_GROWTH_PCT::STRING, 'n/a') || '%'
      || IFF(IS_ANOMALY, ' [ANOMALY]', ''), '\n'
  ) WITHIN GROUP (ORDER BY PERIOD, TOTAL_AMOUNT DESC) AS METRICS_TEXT
  FROM <db>.<schema>.DT_<prefix>_METRICS
  WHERE IS_ANOMALY OR ABS(COALESCE(QOQ_GROWTH_PCT, 0)) >= 15      -- trim to the notable rows
),
gen AS (
  SELECT AI_COMPLETE(
    model => '<reasoning_model>',
    prompt => PROMPT(
      'You are a business analyst. From these period-over-period metrics, surface the most important insights '
      || 'and a concrete recommended action for each (invest in a growing category, investigate a decline, '
      || 'renegotiate a vendor, optimize payment terms). Rank by business impact. '
      || 'For each insight keep the concrete figure and the specific group it applies to — '
      || 'do not generalize to the dominant group only. Metrics:\n{0}',
      COALESCE(METRICS_TEXT, 'No notable movements.')),     -- COALESCE so an empty set never NULLs the prompt
    response_format => { 'type': 'json', 'schema': { 'type': 'object', 'properties': {
        'exec_summary': {'type': 'string'},
        'insights': {'type': 'array', 'items': {'type': 'object', 'properties': {
            'observation':        {'type': 'string'},
            'evidence':           {'type': 'string', 'description': 'the dimension/period/number it rests on'},
            'recommended_action': {'type': 'string'},
            'priority':           {'type': 'string', 'description': 'one of: high, medium, low'} },
          'required': ['observation', 'recommended_action', 'priority'] } } },
      'required': ['exec_summary', 'insights'] } },
    return_error_details => TRUE) AS R                       -- returns {value, error} instead of failing silently to NULL
  FROM salient
)
SELECT R:value:exec_summary::STRING AS EXEC_SUMMARY,
       R:value:insights            AS INSIGHTS,              -- VARIANT array; flatten in the serving view
       R:error::STRING             AS GEN_ERROR              -- NULL on success; carries an over-context message if the input overflowed
FROM gen;
```

Serve one row per insight:
```sql
CREATE OR REPLACE VIEW <db>.<schema>.<prefix>_INSIGHTS AS
SELECT i.value:observation::STRING AS OBSERVATION, i.value:evidence::STRING AS EVIDENCE,
       i.value:recommended_action::STRING AS RECOMMENDED_ACTION,
       LOWER(i.value:priority::STRING) AS PRIORITY   -- normalize: models return High/Critical/etc. despite the enum hint
FROM <db>.<schema>.DT_<prefix>_INSIGHTS, LATERAL FLATTEN(input => INSIGHTS) i;   -- FLATTEN over a materialized array is fine in a view
```

---

## Corpus narrative — from summaries

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_SYNTHESIS
  TARGET_LAG = '<final_lag>'  WAREHOUSE = <warehouse>  REFRESH_MODE = FULL  INITIALIZE = ON_SCHEDULE
AS
WITH agg AS (
  SELECT LISTAGG(TITLE || ' (' || <date_col> || '): ' || SUMMARY_TEXT, '\n\n') AS corpus_text
  FROM <db>.<schema>.DT_<prefix>_SUMMARIZED
),
gen AS (
  SELECT AI_COMPLETE(
           model => '<reasoning_model>',
           prompt => PROMPT('Write a ~200-word overview of this corpus: the main themes, how the focus shifted, and any notable surprises. '
                            || 'Keep each item specific — retain the concrete detail and the distinguishing attribute of each group '
                            || 'rather than generalizing to the dominant theme. Items:\n{0}', corpus_text),
           return_error_details => TRUE) AS R
  FROM agg
)
SELECT R:value::STRING AS CORPUS_NARRATIVE,   -- cast VARIANT→STRING so readers don't get JSON-quoted text
       R:error::STRING AS GEN_ERROR
FROM gen;
```

> **Always use `SUMMARY_TEXT`** — the full per-document summary from `summarize-embed.md`. Include `TITLE` and a time key if present; skip re-passing individual extracted fields the summary already covers.

---

## Context-window ceiling → map-reduce (shared)

Any aggregate `AI_COMPLETE` that `LISTAGG`s all rows (insights, corpus narrative, **and the taxonomy in
[`themes-clusters.md`](themes-clusters.md)**) overflows once the concatenated input exceeds the model's context
window. **Detect, don't guess:** pass `return_error_details => TRUE` (a **named** arg — `show_details` does *not*
surface this) so the call returns `{value, error}`; surface `error` as a `GEN_ERROR` column and check it:

```sql
SELECT GEN_ERROR FROM <db>.<schema>.DT_<prefix>_<rollup>
WHERE GEN_ERROR ILIKE '%token%' OR GEN_ERROR ILIKE '%too long%' OR GEN_ERROR ILIKE '%exceed%';
```

A match means the input overflowed — rebuild the DT as a **2-level map-reduce** (still one `FULL` DT): split rows
into `NTILE(<n>)` batches sized to fit the window, summarize/propose within each batch, then a final reduce over
the batch outputs. For very large corpora, nest another reduce level.

```sql
-- Corpus narrative, map-reduce form:
WITH batched AS (
  SELECT NTILE(<n_batches>) OVER (ORDER BY RELATIVE_PATH) AS BATCH_ID, TITLE, <date_col>, SUMMARY_TEXT
  FROM <db>.<schema>.DT_<prefix>_SUMMARIZED
),
partials AS (
  SELECT BATCH_ID,
    AI_COMPLETE('<reasoning_model>',
      PROMPT('Summarize the themes in this subset of the corpus. Items:\n{0}',
        LISTAGG(TITLE || ' (' || <date_col> || '): ' || SUMMARY_TEXT, '\n\n'))) AS PARTIAL
  FROM batched GROUP BY BATCH_ID
)
SELECT AI_COMPLETE('<reasoning_model>',
  PROMPT('Combine these subset summaries into one ~200-word corpus overview. Subsets:\n{0}',
    LISTAGG(PARTIAL, '\n')))::STRING AS CORPUS_NARRATIVE
FROM partials;
```

(For the **taxonomy** map-reduce, the map step proposes candidate themes per batch as free text and only the
reduce step needs the structured `response_format` — see [`themes-clusters.md`](themes-clusters.md).)
