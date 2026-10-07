# Example — Chart-rich reports, chart-aware search (worked composition)

**Scenario:** A library of chart-rich reports (glossy financial/annual reports, investor decks) lands on a
stage. Much of the payload — segment mix, growth, margins — lives **only in charts**, invisible to text
parsing. You want search/RAG that can answer *"what does the net-sales-by-segment chart show?"*, not just
return a page. This is the hero: a vision step narrates each page's charts and folds that narrative into the
page's searchable content **before** chunking, so chart numbers become findable and citable.

This builds on [`basic.md`](basic.md) — read that first. It is the same backbone with **three deltas**:

1. a **second ingestion path** for a parallel page-image stage,
2. the **Chart/figure vision** lane (one vision call per page image),
3. the **Enrich** block fusing chart narrative into the page content at **page grain**.

**Worked names:** `db=ACME`, `schema=KB`, `<prefix>=ESR`, doc stage `DOCS`, page-image stage `PAGES`,
`warehouse=KB_WH`, `<final_lag>='1 hour'`. Swap in the user's own.

> **Prerequisite — page images.** Snowflake SQL can't rasterize a PDF page to an image. Land one image per
> page on `@PAGES`, laid out so each image's path mirrors the document's `RELATIVE_PATH` **with the extension
> stripped**, then `/<page>.png` — e.g. `DOCS/reports/acme.pdf` → `PAGES/reports/acme/1.png`. The page's
> parent folder is the document's `DOC_KEY` (stage-unique, so two docs sharing a basename never collide) and
> the filename stem is the page number. Produce them **inside Snowflake** (a Snowpark `pypdfium2` stored proc — see
> [`../../../references/rasterize-pdfs.md`](../../../references/rasterize-pdfs.md)) or upstream. *(Small-doc fallback without a page stage: pass the whole PDF to the
> vision call — see the chart/figure vision block in [`../../../blocks/extract/vision-figures.md`](../../../blocks/extract/vision-figures.md).)*

## Blocks, in build order

| # | Block (in the palette) | Object(s) it creates | Grain / refresh | Composition note |
|---|------------------------|----------------------|-----------------|------------------|
| 1a | Ingestion (docs) | `ESR_FILE_LOG`, `ESR_STAGE_STREAM`, `ESR_INGEST_TASK` | — | `.pdf` filter on `@DOCS` |
| 1b | Ingestion (pages) | `ESR_PAGE_LOG`, `ESR_PAGE_STREAM`, `ESR_PAGE_INGEST_TASK` | — | `.png` filter on `@PAGES`; `DOC_KEY`/`PAGE` from the `<doc_key>/<page>.png` path |
| 2 | Parse | `DT_ESR_PARSED` | per-doc · `INCREMENTAL` | `.pdf` → `LAYOUT` + `page_split`; `DOC_KEY` = path minus extension |
| 3 | Page-flatten | `DT_ESR_PAGES` | per-page · `INCREMENTAL` | one row per (doc, page) |
| 4 | Chart/figure vision | `DT_ESR_FIGURES` | per-page · `INCREMENTAL` | one vision call per PNG; `NONE` sentinel |
| 5 | Enrich | `DT_ESR_ENRICHED` | per-page · `INCREMENTAL` | `LEFT JOIN` on `DOC_KEY`+`PAGE`; append chart narrative to page content |
| 6 | Chunk | `DT_ESR_CHUNK_ARR` → `DT_ESR_CHUNKS` | per-chunk · `INCREMENTAL` | `markdown` 1500/200; `DT_ESR_CHUNKS` terminal → `<final_lag>` |
| 7 | Cortex Search | `ESR_SEARCH` | service | `ON CHUNK`, `ATTRIBUTES RELATIVE_PATH, PAGE, CHUNK_NO, TITLE` |
| 8 | Retrieve + answer | (query pattern) | n/a | optional facet filter; `(Title, p.N)` citations |

**DAG:**

```
@DOCS  → ESR_STAGE_STREAM + ESR_INGEST_TASK → ESR_FILE_LOG → DT_ESR_PARSED → DT_ESR_PAGES ─┐
@PAGES → ESR_PAGE_STREAM  + ESR_PAGE_INGEST_TASK → ESR_PAGE_LOG → DT_ESR_FIGURES ──────────┤  (LEFT JOIN on DOC_KEY+PAGE)
                                                                          DT_ESR_ENRICHED
                                                                          → DT_ESR_CHUNK_ARR → DT_ESR_CHUNKS
                                                                          → ESR_SEARCH → RAG query pattern
```

## How the blocks wire (the three deltas)

- **Two stages, two ingestion paths.** The page PNGs are *not* documents — they're pages *of* the PDFs. So
  `@PAGES` gets its own file log + stream + task (base Steps 3–4), exactly like `@DOCS`, but with a `.png`
  filter and `DOC_KEY`/`PAGE` derived from the `<doc_key>/<page>.png` path. **Both ingest tasks resume last.**
  The two lanes meet at Enrich, joined on `DOC_KEY` + `PAGE`.
- **Vision → page-grain enrich.** `DT_ESR_FIGURES` runs one vision `AI_COMPLETE` per page image, emitting a
  prose chart narrative (or the `NONE` sentinel). `DT_ESR_ENRICHED` `LEFT JOIN`s it onto the page text and
  appends a `[Charts and figures on this page]` block when a narrative is present — so the chart numbers sit
  on the **same page** they came from, then flow through chunk → index. Enriching at **page grain** (rather
  than rolling figures up to document grain) is what keeps each chart number on its own citable page.
- **Chart numbers become citable.** Because the narrative is in the page's `CONTENT`, it is chunked and
  indexed with the page's `RELATIVE_PATH`/`PAGE`, so a chart-only question retrieves the chart's numbers and
  the answer cites the page they appear on.

## Build & verify

Create #1a/#1b and #2–#7, **seed both file logs** from `DIRECTORY()` (base Step 4 — the page stage too), then
backfill: refresh `DT_ESR_FIGURES` (the vision branch) and `DT_ESR_CHUNKS` (which pulls parse → pages →
enrich → chunks). Build `ESR_SEARCH` and let it refresh. **Resume both ingest tasks last.**

Refresh-mode check (base Step 6): every `DT_ESR_*` — **including `DT_ESR_FIGURES`** — reads `INCREMENTAL`;
stop and fix any `FULL`. Then the chart-specific smoke checks, on top of `basic.md`'s:

```sql
-- vision coverage: how many pages had a chart narrative (vs NONE)
SELECT COUNT(*) AS pages,
       COUNT_IF(CHART_NARRATIVE NOT ILIKE 'NONE%') AS pages_with_charts
FROM ACME.KB.DT_ESR_FIGURES;

-- the hero: a value that exists only inside a chart should come back, with its page
SELECT v.value:TITLE::STRING AS TITLE, v.value:PAGE::INT AS PAGE, LEFT(v.value:CHUNK::STRING, 280) AS PREVIEW
FROM TABLE(FLATTEN(input => PARSE_JSON(SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
  'ACME.KB.ESR_SEARCH',
  '{"query":"net sales by business segment percentages chart","columns":["CHUNK","TITLE","PAGE"],"limit":6}'
))['results'])) v;
```

Then run the full RAG answer and confirm the chart numbers appear in the grounded answer with a page citation.

> **Cost note (display before executing AI).** Two drivers: `AI_PARSE_DOCUMENT` (once per page) and the vision
> call in `DT_ESR_FIGURES` (once per page image — the dominant cost). For a cheap first run, cap pages with
> `WHERE PAGE <= N` on `DT_ESR_FIGURES`, then widen; every DT is `INCREMENTAL`, so widening only processes new
> pages.

## Teardown

Same as `basic.md`'s, plus the figure lane, the Enrich DT, and the second ingestion path. Dependency-safe
order, **suspend both tasks first**, and **never drop the source stages** (`@DOCS`, `@PAGES`):

```sql
ALTER TASK ACME.KB.ESR_INGEST_TASK SUSPEND;
ALTER TASK ACME.KB.ESR_PAGE_INGEST_TASK SUSPEND;

DROP PROCEDURE IF EXISTS ACME.KB.ask_ESR(STRING);          -- optional wrapper, if built
DROP CORTEX SEARCH SERVICE IF EXISTS ACME.KB.ESR_SEARCH;

DROP DYNAMIC TABLE IF EXISTS ACME.KB.DT_ESR_CHUNKS;
DROP DYNAMIC TABLE IF EXISTS ACME.KB.DT_ESR_CHUNK_ARR;
DROP DYNAMIC TABLE IF EXISTS ACME.KB.DT_ESR_ENRICHED;
DROP DYNAMIC TABLE IF EXISTS ACME.KB.DT_ESR_FIGURES;        -- figure lane
DROP DYNAMIC TABLE IF EXISTS ACME.KB.DT_ESR_PAGES;
DROP DYNAMIC TABLE IF EXISTS ACME.KB.DT_ESR_PARSED;

DROP TASK   IF EXISTS ACME.KB.ESR_PAGE_INGEST_TASK;         -- page ingestion path
DROP STREAM IF EXISTS ACME.KB.ESR_PAGE_STREAM;
DROP TABLE  IF EXISTS ACME.KB.ESR_PAGE_LOG;
DROP TASK   IF EXISTS ACME.KB.ESR_INGEST_TASK;              -- doc ingestion path
DROP STREAM IF EXISTS ACME.KB.ESR_STAGE_STREAM;
DROP TABLE  IF EXISTS ACME.KB.ESR_FILE_LOG;

-- Leave @DOCS and @PAGES in place — that's the user's source data.
```

(Conventions — `INCREMENTAL`-safety, target-lag, monitoring — are base-owned: see
[`../../../references/multi-step-pipeline.md`](../../../references/multi-step-pipeline.md).)
