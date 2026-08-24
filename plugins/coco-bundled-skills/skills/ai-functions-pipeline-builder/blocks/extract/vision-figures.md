# Vision (figures) — numbers locked in charts (`AI_COMPLETE`, page grain)

Numeric or visual content that lives **only in figures, charts, or plots** and is invisible to text parsing
(trend lines, KPIs, margin callouts, survival curves, dose–response). One vision `AI_COMPLETE` per **page
image** emits a **free-text** description (no JSON schema — free prose is what becomes searchable / summarizable),
with a sentinel for figure-less pages. Then the narrative is **fused** into the rest of the pipeline by one of
two paths. Optional — skip when prose and tables already carry the numbers.

> Read [`../conventions.md`](../conventions.md) first. For **typed** image fields (a photo assessment → columns),
> use [`vision-structured.md`](vision-structured.md) instead. Generic vision mechanics are owned by the base
> (§ Step 5 Layer 3b).

- **Prerequisite — per-page images** on a second stage (`<prefix>_PAGE_LOG`), laid out `<doc_key>/<page>.png`.
  Set it up with the second ingestion path in [`../ingest/ingestion.md`](../ingest/ingestion.md) (which also
  points to the `pypdfium2` rasterizer). If your *documents are themselves images*, you don't need this lane —
  `ingest/parse-text.md`'s image modality already turns each into text.
- **Reads** — `<prefix>_PAGE_LOG` (`RELATIVE_PATH` → `DOC_KEY`, `PAGE`).
- **Produces** — `DT_<prefix>_PAGE_FIGURES` (page grain; `FIGURE_TEXT` / `CHART_NARRATIVE`), then a fuse output (below).
- **Refresh** — **INCREMENTAL** (the expensive vision call, once per new page image).
- **Typical upstreams** — `ingest/ingestion.md` (page-image stage).

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_PAGE_FIGURES
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL  INITIALIZE = ON_SCHEDULE
AS
SELECT
  REGEXP_REPLACE(pl.RELATIVE_PATH, '/[^/]+$', '')                            AS DOC_KEY,  -- page's parent dir = doc's DOC_KEY
  TRY_CAST(SPLIT_PART(SPLIT_PART(pl.RELATIVE_PATH, '/', -1), '.', 1) AS INT) AS PAGE,     -- filename stem = page number
  AI_COMPLETE('<vision_model>',                                                           -- must be vision-capable; see model selection note below
    PROMPT('This image is ONE page of a document. Describe any charts/graphs/figures: for each, state its '
      || 'title, chart type, what the axes/segments represent, the overall trend, and the key numbers or '
      || 'percentages shown — plus any highlighted callouts (totals, growth, margin). Write concise '
      || 'self-contained prose (no markdown, no preamble). If the page has no figure with numbers, reply with '
      || 'exactly the single word NONE.\n\nPage image:\n{0}',
      TO_FILE('@<db>.<schema>.<page_stage>', pl.RELATIVE_PATH)))::STRING AS FIGURE_TEXT
FROM <db>.<schema>.<prefix>_PAGE_LOG pl
WHERE pl.RELATIVE_PATH ILIKE '%.png' OR pl.RELATIVE_PATH ILIKE '%.jpg' OR pl.RELATIVE_PATH ILIKE '%.jpeg';
```

- **Sentinel, not empty string.** The model answers `NONE` for figure-less pages, so the fuse step can skip them
  cleanly and you can tell "no figure" from a soft-failed call.
- **Pick a vision-capable model and verify regional availability before building the DT.** You can use `claude-sonnet-4-6` as the default first choice — it is vision-capable, broadly available, and
  used consistently across this skill. If it's unavailable, cross-reference the [AI_COMPLETE Prompt-object reference](https://docs.snowflake.com/en/sql-reference/functions/ai_complete-prompt-object) and the [Cortex AI SQL regional availability matrix](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql-regional-availability) — neither is queryable from SQL. Probe with a real file before creating the DT:
  ```sql
  SELECT AI_COMPLETE('<vision_model>',
    PROMPT('Describe any charts or figures. {0}', TO_FILE('@<db>.<schema>.<page_stage>', '<any_file>')));
  ```
  **Never fall back to text-only models** — they silently accept `TO_FILE` but return `null` or invented text, so `NONE`-sentinel filtering classifies every page as figure-less.
- **Never backfill with a placeholder string** on failure — fix the call. `NONE` for a figure-less page is correct; a fake success string for a failed call ships garbage.
- **Cost.** This is the priciest lane — one vision call per page image, dominating the backfill. Gate to
  likely-figure pages (`WHERE PAGE <= N`) for a first run if cost matters; all-pages is simplest and most complete.

---

## Fuse the narrative — don't leave it stranded

The lane only pays off if the numbers reach the rest of the pipeline. Pick the path that matches your downstream:

**A. Page-grain enrich (for search/RAG)** — merge the narrative into that page's `CONTENT` *before* chunking,
so chart numbers sit on the same page they came from and get chunked + indexed with it. Reads `PAGE_TEXT`
([`../ingest/parse-pages.md`](../ingest/parse-pages.md)) + this lane; produces a `PAGE_TEXT` shape that
`search/chunk-index.md` reads:

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_ENRICHED
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL  INITIALIZE = ON_SCHEDULE
AS
SELECT
  pg.RELATIVE_PATH, pg.FILE_NAME, pg.DOC_KEY, pg.PAGE,
  pg.CONTENT
    || CASE WHEN fig.FIGURE_TEXT IS NOT NULL AND fig.FIGURE_TEXT NOT ILIKE 'NONE%'
            THEN '\n\n[Charts and figures on this page]\n' || fig.FIGURE_TEXT ELSE '' END AS CONTENT
FROM <db>.<schema>.DT_<prefix>_PAGES pg
LEFT JOIN <db>.<schema>.DT_<prefix>_PAGE_FIGURES fig ON pg.DOC_KEY = fig.DOC_KEY AND pg.PAGE = fig.PAGE;
```
> `LEFT JOIN`: pages with no rendered image (or no figure) flow through with body text only.

**B. Doc-grain roll-up (for corpus summary / facts)** — stitch the non-`NONE` pages into one field per document,
then join it into `analyze/summarize-embed.md` (add a `{figures}` input to that prompt) so figure numbers flow
into summary → embedding → themes → synthesis. Stays `INCREMENTAL` (`LISTAGG … GROUP BY`, no AI):

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_FIGURE_FACTS
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL  INITIALIZE = ON_SCHEDULE
AS
SELECT DOC_KEY,
  LISTAGG(CASE WHEN UPPER(TRIM(FIGURE_TEXT)) <> 'NONE' AND TRIM(FIGURE_TEXT) <> ''
               THEN 'Page ' || PAGE || ': ' || FIGURE_TEXT END, '\n\n')
    WITHIN GROUP (ORDER BY PAGE) AS FIGURE_FINDINGS
FROM <db>.<schema>.DT_<prefix>_PAGE_FIGURES
GROUP BY DOC_KEY;
```

> **Small/simple-doc fallback (no page stage).** When page-level citation isn't needed and PDFs are small, pass
> the whole PDF directly to `AI_COMPLETE` for a document-level narrative (`TO_FILE('@<doc_stage>', RELATIVE_PATH)`
> instead of a page image; key on `DOC_KEY`, no `PAGE`). Bounded by per-call size limits — prefer the page stage
> for big reports.
