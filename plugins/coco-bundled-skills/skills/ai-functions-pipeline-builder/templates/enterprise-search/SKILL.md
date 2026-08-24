---
name: enterprise-search
description: "Build a persistent, Snowflake-native enterprise-search / RAG pipeline that turns a mixed document library into a governed, searchable knowledge layer with grounded, cited answers — using AI_PARSE_DOCUMENT, AI_COMPLETE (chart/figure vision), SPLIT_TEXT_RECURSIVE_CHARACTER, Cortex Search, plus incremental dynamic tables, streams and tasks. Use when the user wants question-answering / retrieval over a document collection, not one-by-one extraction. Triggers: enterprise search, knowledge base over documents, search service over a stage, RAG over documents, retrieval-augmented generation, grounded cited answers, ask questions about my documents, document Q&A, Cortex Search pipeline, semantic search over PDFs/reports/contracts/policies/manuals, make our documents searchable, chart-aware search, searchable knowledge layer."
parent_skill: ai-functions-pipeline-builder
---

# Enterprise Search Pipeline

A **recipe** over the shared block palette that turns a mixed document library landing on a stage into a
**governed, searchable knowledge layer** — full text plus the meaning locked in tables and charts — that answers
questions with grounded, cited answers, continuously as new files arrive.

## When to use

Use this when the user wants to **search / ask questions** across a collection — stand up a search or RAG service
over a library (reports, contracts, policies, manuals, scans) with citations to source and page, make the numbers
locked in **tables and charts** findable, or build any "documents-in → governed-search-layer + cited-answers-out"
flow kept fresh as files land (ready for search, RAG, and agents).

**Do NOT use for:** per-document structured extraction into typed columns →
[`../invoice-processing/SKILL.md`](../invoice-processing/SKILL.md) or the base; corpus-level *understanding*
(themes, trends, reading list) → [`../corpus-intelligence/SKILL.md`](../corpus-intelligence/SKILL.md); one-off
Q&A over a single document → a one-shot `AI_PARSE_DOCUMENT` + `AI_COMPLETE`.

## Read first

The orchestration scaffold is shared — [`../conventions.md`](../conventions.md). Load it, plus the palette router
[`../../blocks/README.md`](../../blocks/README.md) and contract [`../../blocks/conventions.md`](../../blocks/conventions.md).
This file supplies the recipe, defaults, the all-`INCREMENTAL` contract, and smoke checks.

## Recipe — blocks to compose

Backbone: [`ingest/ingestion`](../../blocks/ingest/ingestion.md) → [`ingest/parse-pages`](../../blocks/ingest/parse-pages.md)
(page-split parse + page-flatten → citation grain) → [`search/chunk-index`](../../blocks/search/chunk-index.md)
(chunk + Cortex Search service) → [`search/rag-answer`](../../blocks/search/rag-answer.md) (grounded cited answer)
→ [`serve/presentation`](../../blocks/serve/presentation.md) (optional app).

Optional layers: [`extract/vision-figures`](../../blocks/extract/vision-figures.md) (chart/figure narratives —
the hero; needs a page-image stage, fused page-grain into content before chunking); metadata facets and Translate
(both in [`search/chunk-index.md`](../../blocks/search/chunk-index.md) / [`ingest/parse-text.md`](../../blocks/ingest/parse-text.md)).

> **Grounded answers and summaries come from `search/rag-answer` (Cortex Search + `AI_COMPLETE`), not `AI_EXTRACT`.** `AI_EXTRACT` extracts pre-existing field values from documents; it cannot generate answers, insights, or reasoning over a document collection.

## Intake topics (raise only what the prompt left open)

| Topic | Default if unspecified | Block |
|-------|------------------------|-------|
| Parse mode | `LAYOUT` (keeps tables/headings/reading order); `OCR` only for prose-only/scanned | parse-pages |
| Chart / figure search | off; on when charts carry meaning **and** page images are available or producible | vision-figures |
| Filterable facets | none beyond doc + page + title | metadata facets (in chunk-index) |
| Languages | English-only | Translate |
| Chunk size / overlap | 1500 / 200 chars, `markdown`; skip chunking for short docs | chunk-index |
| Answer convenience wrapper | off — documented RAG query pattern only | rag-answer (`ask_<prefix>` proc) |
| Final freshness (search-service target lag) | 1 hour | base Step 7 |

> **Chart-vision needs a parallel page-image stage**, laid out so each image path mirrors the document's path
> with the extension stripped, then `/<page>.png`. The page-image stage gets its own file log + stream + task
> (the second ingestion path in `ingest/ingestion.md`). Seed **both** stages.

**Scale nudge:** chart-vision is one AI call per page image and dominates a first run. Cap pages
(`WHERE PAGE <= N`) for a smoke pass, then widen — every DT is `INCREMENTAL`, so widening only processes new pages.

## Refresh expectation

This pipeline is **all-`INCREMENTAL`** — every `DT_<prefix>_*` fires on new files only; there are **no `FULL`
rollups**. The **Cortex Search service is not a DT** (it self-refreshes on its `TARGET_LAG`). The terminal
`DT_<prefix>_CHUNKS` takes the user's `<final_lag>`; upstream DTs are `DOWNSTREAM`. In base Step 6, fix any DT
that reads `FULL` (watch the parse / page-flatten `UNION ALL` forms).

> ⚠️ **The Cortex Search service self-refreshing does NOT satisfy the INCREMENTAL requirement.** It only re-indexes whatever its source returns; if `DT_<prefix>_CHUNKS` is missing or `FULL`, every trigger re-parses and re-chunks the whole corpus. Every DT including `DT_<prefix>_CHUNKS` must be `INCREMENTAL`.

**⚠️ STOPPING POINT** — present the DAG + assumptions + pricing, then wait for approval before creating objects — *unless the user authorized an autonomous build* ("build it live" / "don't wait to confirm"), in which case proceed (capped first run). The irreversible Teardown `DROP`s always require approval.

## Smoke checks (after the base Step 8 test)

- `DT_<prefix>_CHUNKS` returns a plausible chunk count, with `CHUNK` populated and `RELATIVE_PATH` (and `PAGE`,
  when paginated) set on every row.
- `SNOWFLAKE.CORTEX.SEARCH_PREVIEW` over `<prefix>_SEARCH` returns relevant chunks for a representative query.
- If chart-vision was built: `DT_<prefix>_FIGURES` has non-`NONE` narratives for chart pages, and a chart-only
  question returns it — the hero check.
- The RAG pattern returns a grounded answer that cites `(Title, p.N)` (or `(Title, #chunk)` for non-paginating docs).

## Examples

- [`examples/basic.md`](examples/basic.md) — full worked composition (parse → page-flatten → chunk → Cortex Search → cited RAG). **Start here.**
- [`examples/charts.md`](examples/charts.md) — the chart-aware composition (parallel page-image stage + chart-vision + page-grain enrich — the hero where chart numbers become searchable).
