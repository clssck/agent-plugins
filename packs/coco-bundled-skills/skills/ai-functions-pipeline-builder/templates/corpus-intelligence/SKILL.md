---
name: corpus-intelligence
description: "Build a persistent, Snowflake-native corpus-intelligence pipeline that turns a collection of documents into corpus-level understanding — themes, trends, outliers, exemplars, and a per-document facts table — using AI_PARSE_DOCUMENT, AI_EXTRACT, AI_COMPLETE, AI_EMBED, plus incremental dynamic tables, streams and tasks. Use when the user wants to understand or analyze a whole set of documents rather than process them one-by-one. Triggers: corpus intelligence, analyze a document corpus, understand a collection of documents, what are these documents about, themes across documents, thematic analysis, document corpus overview, corpus profiling, literature review pipeline, summarize a collection of papers/reports/filings, cluster documents by theme, find outlier documents, recommended reading list from a corpus, corpusiq."
parent_skill: ai-functions-pipeline-builder
---

# Corpus Intelligence Pipeline

A **recipe** over the shared block palette that turns a collection of documents landing on a stage into
corpus-level understanding — themes, evolution, outliers, exemplars, and a queryable per-document facts table —
continuously, as new files arrive.

## When to use

Use this when the user wants to **understand a whole corpus** they didn't necessarily author — papers, filings,
reports, tickets, transcripts — for example to reduce a backlog to a queryable profile (what themes exist, how
they evolved, what's unusual) without reading every file, discover the topics a collection organizes into and
which documents are central or off-beat, or track how focus shifted over time.

**Do NOT use for:** per-document structured extraction with no cross-document synthesis → the base; one-off
analysis of a single document → a one-shot call; free-form Q&A / RAG as the *only* goal → just the
[`search/*`](../../blocks/search/chunk-index.md) blocks or the standalone `cortex-search` skill.

## Read first

The orchestration scaffold is shared — [`../conventions.md`](../conventions.md). Load it, plus the palette router
[`../../blocks/README.md`](../../blocks/README.md) and contract [`../../blocks/conventions.md`](../../blocks/conventions.md).
This file supplies the recipe, defaults, the two-grain refresh policy, and smoke checks.

## Recipe — blocks to compose

Backbone: [`ingest/ingestion`](../../blocks/ingest/ingestion.md) → [`ingest/parse-text`](../../blocks/ingest/parse-text.md)
→ [`extract/fields`](../../blocks/extract/fields.md) (**schema-elicited**, with the required `TITLE` and an
optional time key) → [`analyze/summarize-embed`](../../blocks/analyze/summarize-embed.md) →
[`analyze/themes-clusters`](../../blocks/analyze/themes-clusters.md) (taxonomy → assign → outliers → highlights)
→ [`analyze/synthesize`](../../blocks/analyze/synthesize.md) (corpus narrative) → [`serve/final-shape`](../../blocks/serve/final-shape.md)
(`<prefix>_ITEMS` + `<prefix>_PROFILE`) + [`serve/presentation`](../../blocks/serve/presentation.md).

Optional: [`analyze/metrics-trend`](../../blocks/analyze/metrics-trend.md) (trend over time, if a usable date
exists); [`extract/vision-figures`](../../blocks/extract/vision-figures.md) (numbers locked in charts — needs a
page-image stage); [`search/chunk-index`](../../blocks/search/chunk-index.md) + [`search/rag-answer`](../../blocks/search/rag-answer.md) (free-form Q&A).

> **Corpus narratives and insights come from `analyze/synthesize` (`AI_COMPLETE`), not `AI_EXTRACT`.** `AI_EXTRACT` pulls pre-existing field values from individual documents; it cannot generate cross-document reasoning, thematic insights, or recommended actions.

> **No default extract schema** (unlike invoice): elicit the fields worth capturing from the goal (papers →
> methods/contributions; filings → metrics/risks). The schema **must** expose a unique `TITLE` (filename
> fallback) carried forward, or downstream labels go blank.

## Intake topics (raise only what the prompt left open)

| Topic | Default if unspecified | Block |
|-------|------------------------|-------|
| Parse mode | `OCR` (cheaper); `LAYOUT` only if structure/tables matter | parse-text |
| Languages | English-only | Translate (in parse-text) |
| Per-document summary | on — structured facets feeding the analysis | summarize-embed |
| Figure / chart numbers | off; on when numbers live only in figures **and** page images are available | vision-figures |
| Themes | on — taxonomy + nearest-theme assignment | themes-clusters |
| Topical outliers / highlights | on | themes-clusters |
| Corpus narrative | on — one generated overview | synthesize |
| Trend over time | off unless docs are orderable **and** carry a usable date | metrics-trend |
| Free-form Q&A / RAG | off | search/* |
| Taxonomy regeneration | on demand (not per file) | themes-clusters (taxonomy) |
| Final freshness (target lag) | 1 hour | base Step 7 |

**Scale nudge:** the corpus-grain rollups (taxonomy, synthesis) feed all summaries to one `AI_COMPLETE`. Past a
few hundred documents the concatenated input exceeds the context window — switch those blocks to the map-reduce
form (`analyze/synthesize.md` owns the detection + map-reduce).

## Refresh expectation (two grains)

**Per-document DTs** (parse, translate, extract, summarize, embed, theme-assign, figure lane) **MUST stay
`INCREMENTAL`** — that's where the expensive AI is. **Corpus-grain rollups** (outliers, synthesis, trend) are
**`FULL` by necessity but cheap**; the **taxonomy is a pinned table**, not a DT. In base Step 6, fix any
per-document DT that reads `FULL`; corpus-grain rollups reading `FULL` are expected.

On approval, also: regenerate the taxonomy table once embeddings exist, then resume the ingest task last.

## Smoke checks (after the base Step 8 test)

- `<prefix>_ITEMS` returns one row per file with key extracted fields populated (all-NULL → fix the
  `responseFormat`/prompt descriptions or the `TRY_CAST`s).
- `<prefix>_THEMES` is non-empty and every document got a `THEME` + `THEME_SIM`.
- `DT_<prefix>_SYNTHESIS` has a non-empty narrative; if trend was built, the timeline spans plausibly.

## Examples

- [`examples/basic.md`](examples/basic.md) — full worked composition (parse → extract → summarize → embed → taxonomy + assign → synthesis/outliers/trend → final-shape views). **Start here.**
- [`examples/figures.md`](examples/figures.md) — adds the page-image stage + figure-extraction lane (numbers that live only in charts), fused into the summary and Q&A.
