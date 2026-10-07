# Example — Corpus with companion page images (figure extraction)

**Scenario:** A collection of research papers (PDFs) lands on one stage, and a **parallel stage** carries
**page-image renders** of the same papers — one PNG per page, laid out as `<paper_id>/<page>.png`. Much of the
quantitative payload lives **only in the figures** and never appears as machine-readable text. You want the full
corpus picture *plus* those figure-only numbers folded into every downstream layer.

This builds on [`basic.md`](basic.md) — read that first. It is the same backbone with **three deltas**:

1. a **second ingestion path** for the page-image stage,
2. the **figure-extraction** lane ([`../../../blocks/extract/vision-figures.md`](../../../blocks/extract/vision-figures.md)),
3. the **time key is extracted** (the filenames are opaque IDs like `PMC13191423`, not dated).

**Worked names:** `db=RESEARCH`, `schema=PUBMED`, `<prefix>=LIT`, doc stage `PAPERS`, page stage `PAGES`,
`warehouse=CORPUS_WH`.

## Blocks, in build order

| # | Block (in the palette) | Object(s) it creates | Grain / refresh | Composition note |
|---|---------------------------|----------------------|-----------------|------------------|
| 1a | Ingestion (docs) | `LIT_FILE_LOG`, `LIT_STAGE_STREAM`, `LIT_INGEST_TASK` | — | `.pdf` filter on `@PAPERS` |
| 1b | Ingestion (pages) | `LIT_PAGE_LOG`, `LIT_PAGE_STREAM`, `LIT_PAGE_INGEST_TASK` | — | `.png` filter on `@PAGES`; derive `PAPER_ID = SPLIT_PART(RELATIVE_PATH,'/',1)`, `PAGE_NO` from the file stem |
| 2 | Parse / OCR | `DT_LIT_PARSED` | per-doc · `INCREMENTAL` | `OCR`; carries `PAPER_ID = REPLACE(FILE_NAME,'.pdf','')` |
| 3 | Visual / figure extraction | `DT_LIT_PAGE_FIGURES` → `DT_LIT_FIGURE_FACTS` | page · `INCREMENTAL` → doc · `INCREMENTAL` | vision per PNG with a `NONE` sentinel; roll up to `FIGURE_FINDINGS` per `PAPER_ID` |
| 4 | Field extraction | `DT_LIT_EXTRACTED` | per-doc · `INCREMENTAL` | clinical schema (`title, study_design, condition, interventions[], sample_size, primary_outcome, key_findings[], …`); **also derives `PUB_YEAR`** as an `AI_EXTRACT` field (opaque filenames → see the time-key note in [`../../../blocks/extract/fields.md`](../../../blocks/extract/fields.md)) |
| 5 | Per-document summary | `DT_LIT_SUMMARIZED` | per-doc · `INCREMENTAL` | **fuses three inputs** — extracted fields + parsed text + `FIGURE_FINDINGS`; facets `objective/design/key_result/significance` + `SUMMARY_TEXT` |
| 6 | Embedding | `DT_LIT_EMBEDDED` | per-doc · `INCREMENTAL` | `AI_EMBED(SUMMARY_TEXT)` (figure numbers are now in it) |
| 7 | Theme taxonomy | `LIT_THEMES` (pinned) | regenerated on demand | built once summaries exist |
| 8 | Theme assignment | `DT_LIT_THEME_ASSIGN` | per-doc · `INCREMENTAL` | nearest theme by cosine; carries `PUB_YEAR` forward |
| 9 | Outlier detection | `DT_LIT_OUTLIERS` | corpus · `FULL` | adaptive `mean − 1·stddev` |
| 10 | Corpus synthesis | `DT_LIT_SYNTHESIS` | corpus · `FULL` | one narrative (`LISTAGG → AI_COMPLETE`) |
| 11 | Trend over time | `DT_LIT_TIMELINE` | corpus · `FULL` | theme × `PUB_YEAR` (key carried forward from #4) |
| 12 | Semantic search | `DT_LIT_CHUNKS` → `LIT_SEARCH` | per-doc · `INCREMENTAL` + service | text chunks **plus a figure-findings chunk per paper** so Q&A can cite chart numbers |
| 13 | Cluster highlights | view `LIT_HIGHLIGHTS` | view | exemplar + outlier per theme |
| 14 | Final shape | views `LIT_ITEMS`, `LIT_PROFILE` | views | `LIT_ITEMS` exposes `FIGURE_FINDINGS` as a column |

**DAG:**

```
@PAPERS → LIT_STAGE_STREAM + LIT_INGEST_TASK → LIT_FILE_LOG → DT_LIT_PARSED ─────────────┐
@PAGES  → LIT_PAGE_STREAM  + LIT_PAGE_INGEST_TASK → LIT_PAGE_LOG                          │
                                  → DT_LIT_PAGE_FIGURES → DT_LIT_FIGURE_FACTS ────────────┤   [per-page/-doc · INCREMENTAL]
                                                                                          ↓
                          DT_LIT_EXTRACTED ──────────────────────────────→ DT_LIT_SUMMARIZED → DT_LIT_EMBEDDED
                                                  (fields + parsed text + FIGURE_FINDINGS)              │
                                              (regen)  LIT_THEMES (pinned) ────────────────────────────┤
                                                                                                        ↓
                                                                              DT_LIT_THEME_ASSIGN  (carries PUB_YEAR)
                                                                                        │
                  ┌──────────────────┬──────────────────────┬─────────────────────────┴───────┐
            DT_LIT_OUTLIERS    DT_LIT_TIMELINE        DT_LIT_SYNTHESIS                   DT_LIT_CHUNKS → LIT_SEARCH
                  └────────────────→ LIT_ITEMS · LIT_PROFILE · LIT_HIGHLIGHTS  [views]
```

## How the blocks wire (the three deltas)

- **Two stages, two ingestion paths.** The page PNGs are *not* documents — they're pages *of* the PDFs. So
  `@PAGES` gets its own file log + stream + task (base Steps 3–4), exactly like `@PAPERS`, but with a `.png`
  filter and `PAPER_ID`/`PAGE_NO` derived from the `<paper_id>/<page>.png` path. Both ingest tasks resume
  **last**. The two lanes only meet at the summary, joined on `PAPER_ID`.
- **Figure lane → summary fusion.** `DT_LIT_PAGE_FIGURES` runs one vision `AI_COMPLETE` per page (the `NONE`
  sentinel drops text-only pages); `DT_LIT_FIGURE_FACTS` `LISTAGG`s the survivors per paper. The summary then
  takes **three** inputs — add the figure findings as a third `PROMPT()` arg (`COALESCE` it, like every arg):

  ```sql
  AI_COMPLETE('<reasoning_model>',
    PROMPT('Summarize into the required JSON fields, using the extracted fields, the numbers read from '
        || 'figures/charts, and the full text.\n\nExtracted:\n{0}\n\nFigure numbers:\n{1}\n\nFull text:\n{2}',
      <extracted_fields_concat>,
      COALESCE(ff.FIGURE_FINDINGS, 'None reported in figures.'),
      COALESCE(LEFT(p.PARSED_TEXT, 60000), '')),
    response_format => { … objective/design/key_result/significance … })
  FROM DT_LIT_EXTRACTED e
  JOIN DT_LIT_PARSED  p  USING (RELATIVE_PATH)
  LEFT JOIN DT_LIT_FIGURE_FACTS ff ON ff.PAPER_ID = e.PAPER_ID   -- LEFT: papers may have no figures
  ```

  Because the numbers now live in `SUMMARY_TEXT`, they propagate for free into the embedding, themes, and
  synthesis — no separate plumbing.
- **Figure findings as a citable chunk.** In the Semantic search block, `UNION ALL` one extra row per paper
  whose `CHUNK_TEXT` is the `FIGURE_FINDINGS` (give it a sentinel `CHUNK_ID`, e.g. `9000`), so a Q&A answer can
  retrieve and cite a chart value, not just body text.
- **Extracted time key.** Unlike `basic.md`'s arXiv case, the filenames here are opaque PMC IDs, so `PUB_YEAR`
  is an `AI_EXTRACT` field in #4 (not filename SQL) — then carried forward to `DT_LIT_THEME_ASSIGN` for the
  Trend block. Same single-stage rule as the rest of the extract lane; just the other source branch.

## Build & verify

Create #1a/#1b and #2–#14, seed **both** file logs from `DIRECTORY()` (base Step 4 — page stage too), then
backfill: refresh `DT_LIT_PAGE_FIGURES` (the vision branch) and `DT_LIT_EMBEDDED` (the text branch pulls
parse → figure-facts → extract → summarize → embed), generate `LIT_THEMES`, refresh assignment + rollups +
chunks, build `LIT_SEARCH`, **resume both ingest tasks last**.

Two-grain check (base Step 6): every per-doc/per-page `DT_LIT_*` — **including `DT_LIT_PAGE_FIGURES` and
`DT_LIT_FIGURE_FACTS`** — must read `INCREMENTAL` (the `LISTAGG … GROUP BY PAPER_ID` roll-up stays incremental;
verified). The rollups (`_OUTLIERS`, `_TIMELINE`, `_SYNTHESIS`) are expected `FULL`.

Figure-specific smoke checks, on top of `basic.md`'s:

```sql
-- coverage: how many pages / papers actually yielded figure numbers
SELECT COUNT(*) AS pages,
       COUNT_IF(UPPER(TRIM(FIGURE_TEXT)) <> 'NONE') AS pages_with_figures,
       COUNT(DISTINCT IFF(UPPER(TRIM(FIGURE_TEXT)) <> 'NONE', PAPER_ID, NULL)) AS papers_with_figures
FROM RESEARCH.PUBMED.DT_LIT_PAGE_FIGURES;

-- spot-check one paper's stitched findings against its actual pages
SELECT FIGURE_FINDINGS FROM RESEARCH.PUBMED.DT_LIT_FIGURE_FACTS WHERE PAPER_ID = '<some_id>';
```
## What it buys

Figure-only numbers become first-class: they steer theme assignment and the synthesis narrative, show up per
paper in `LIT_ITEMS.FIGURE_FINDINGS`, and are retrievable in Q&A. On the validated run, a question like *"how
much weight loss did tirzepatide vs semaglutide achieve?"* returned exact chart values (−22.8 kg vs −15.0 kg)
that existed only inside the figures — unreachable by a text-only pipeline.

## Teardown

Same as `basic.md`'s, plus the figure lane and the second ingestion path. Dependency-safe order, **suspend
both tasks first**, and **never drop the source stages** (`@PAPERS`, `@PAGES`):

```sql
ALTER TASK RESEARCH.PUBMED.LIT_INGEST_TASK SUSPEND;
ALTER TASK RESEARCH.PUBMED.LIT_PAGE_INGEST_TASK SUSPEND;

DROP VIEW IF EXISTS RESEARCH.PUBMED.LIT_PROFILE;
DROP VIEW IF EXISTS RESEARCH.PUBMED.LIT_ITEMS;
DROP VIEW IF EXISTS RESEARCH.PUBMED.LIT_HIGHLIGHTS;

DROP CORTEX SEARCH SERVICE IF EXISTS RESEARCH.PUBMED.LIT_SEARCH;
DROP DYNAMIC TABLE IF EXISTS RESEARCH.PUBMED.DT_LIT_CHUNKS;
DROP DYNAMIC TABLE IF EXISTS RESEARCH.PUBMED.DT_LIT_SYNTHESIS;
DROP DYNAMIC TABLE IF EXISTS RESEARCH.PUBMED.DT_LIT_TIMELINE;
DROP DYNAMIC TABLE IF EXISTS RESEARCH.PUBMED.DT_LIT_OUTLIERS;
DROP DYNAMIC TABLE IF EXISTS RESEARCH.PUBMED.DT_LIT_THEME_ASSIGN;
DROP DYNAMIC TABLE IF EXISTS RESEARCH.PUBMED.DT_LIT_EMBEDDED;
DROP DYNAMIC TABLE IF EXISTS RESEARCH.PUBMED.DT_LIT_SUMMARIZED;
DROP DYNAMIC TABLE IF EXISTS RESEARCH.PUBMED.DT_LIT_EXTRACTED;
DROP DYNAMIC TABLE IF EXISTS RESEARCH.PUBMED.DT_LIT_FIGURE_FACTS;   -- figure lane
DROP DYNAMIC TABLE IF EXISTS RESEARCH.PUBMED.DT_LIT_PAGE_FIGURES;
DROP DYNAMIC TABLE IF EXISTS RESEARCH.PUBMED.DT_LIT_PARSED;

DROP TABLE  IF EXISTS RESEARCH.PUBMED.LIT_THEMES;

DROP TASK   IF EXISTS RESEARCH.PUBMED.LIT_PAGE_INGEST_TASK;          -- page ingestion path
DROP STREAM IF EXISTS RESEARCH.PUBMED.LIT_PAGE_STREAM;
DROP TABLE  IF EXISTS RESEARCH.PUBMED.LIT_PAGE_LOG;
DROP TASK   IF EXISTS RESEARCH.PUBMED.LIT_INGEST_TASK;               -- doc ingestion path
DROP STREAM IF EXISTS RESEARCH.PUBMED.LIT_STAGE_STREAM;
DROP TABLE  IF EXISTS RESEARCH.PUBMED.LIT_FILE_LOG;

-- Leave @PAPERS and @PAGES in place — that's the user's source data.
```

(Conventions — `INCREMENTAL`-safety, target-lag, monitoring — are base-owned: see
[`../../../references/multi-step-pipeline.md`](../../../references/multi-step-pipeline.md).)
