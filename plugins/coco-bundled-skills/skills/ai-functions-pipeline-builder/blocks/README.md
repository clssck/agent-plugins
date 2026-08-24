# Pipeline Block Palette

The shared, composable building blocks for document pipelines on Snowflake Cortex AI. Each block is one layer
(a dynamic table, a service, or a view) with a fixed input/output **contract** so blocks from different use
cases mix freely. The use-case templates ([`../templates/`](../templates/)) are *recipes* over this palette;
you can also pick individual blocks for a task no template covers.

**Start with [`conventions.md`](conventions.md)** — it defines the data-shape vocabulary every block's
`Reads`/`Produces` is written in, the compose rules, the refresh-mode contract, and "writing your own block".
Generic AI-function mechanics and the end-to-end workflow live in the base —
[`../references/multi-step-pipeline.md`](../references/multi-step-pipeline.md).

## How to use this router

Load **only** the block files your goal needs (each is ~50–200 lines). Find them two ways: scan the
**block index** by pipeline stage, or jump to a **recipe** for a known use case. A pipeline composes as a chain:
ingest → (parse) → (extract) → … → serve, ordered by matching each block's `Reads` shape to an upstream
block's `Produces` shape.

```
ingest ──► extract ──► records ──┬─► (operational head)
                                 ├─► analyze (analytical / corpus head)
                                 ├─► search  (retrieval head)
                                 └─► serve
```

---

## Block index (by stage)

### `ingest/` — files in, clean text/pages out
| File | What it gives you |
|------|-------------------|
| [`ingest/ingestion.md`](ingest/ingestion.md) | The event-driven head: directory stage + file-log table + stream + ingest task, with the extension-filter parameter and backlog seed. Includes the optional **second page-image stage** that the figure/chart-vision lane needs. Always the head of the chain. |
| [`ingest/parse-text.md`](ingest/parse-text.md) | `AI_PARSE_DOCUMENT` → a `PARSED_TEXT` string (OCR vs LAYOUT cost call), the **multi-modality** swap-the-parser variants (image→vision-describe, audio/video→transcribe), and **Translate**. The common text currency every downstream block reads. |
| [`ingest/parse-pages.md`](ingest/parse-pages.md) | The **citation-grain** parse: `page_split` (UNION-ALL by format) → `RAW_PARSE`, then page-flatten to one row per `(doc, page)`. Use instead of `parse-text` when search answers must cite a page. |

### `extract/` — text/images → structured per-document data
| File | What it gives you |
|------|-------------------|
| [`extract/classify.md`](extract/classify.md) | `AI_CLASSIFY` in three flavors: a **binary gate** (keep one type), a **multi-class router** (fan out to per-type extractors, image-by-modality arm), and a **category-derive** (add a grouping dimension for analytics). |
| [`extract/fields.md`](extract/fields.md) | `AI_EXTRACT` field extraction: a typed header, a **routed extractor per type** with confidence scores, a **schema-elicited** extractor (corpus, with required `TITLE`/time-key), and **line-item / table** parallel-array flatten. The accuracy lever is field-description quality. |
| [`extract/vision-structured.md`](extract/vision-structured.md) | `AI_COMPLETE` over an image with a `response_format` JSON schema → **typed assessment columns** (damage, condition, a photographed form). For when fields live in an image, not text. |
| [`extract/vision-figures.md`](extract/vision-figures.md) | `AI_COMPLETE` over **page images** → **free-text** figure/chart numbers, then fused either page-grain (into searchable content) or doc-grain (into the summary). The priciest lane; optional. |

### `records/` — assemble, validate, decide, route
| File | What it gives you |
|------|-------------------|
| [`records/entity.md`](records/entity.md) | The **doc → entity grain shift**: a spine + multi-`LEFT JOIN` reassembles many per-document rows into one record per `<entity_key>`, with `HAS_*` presence flags and derived cross-document signals. |
| [`records/validate.md`](records/validate.md) | Deterministic, no-AI checks: tri-state **totals reconciliation** (do the parts sum to the whole) and **fuzzy master match** (canonicalize an extracted name to a reference table). |
| [`records/reason.md`](records/reason.md) | `AI_COMPLETE` **judgment** over already-extracted fields — single-document or cross-document — producing risk / derived-amount / suggested-action / rationale. Reason, don't re-extract. |
| [`records/triage.md`](records/triage.md) | The operational tail: a deterministic first-match-wins `CASE` ladder → an action lane (auto / review / reject), plus filtered per-lane views. Thresholds are the control surface. |

### `analyze/` — aggregate understanding (analytical & corpus head)
| File | What it gives you |
|------|-------------------|
| [`analyze/summarize-embed.md`](analyze/summarize-embed.md) | The per-document inputs to corpus understanding: a **structured summary** (short facets) and its **embedding**. Both incremental; feed the corpus-grain rollups below. |
| [`analyze/themes-clusters.md`](analyze/themes-clusters.md) | The coupled clustering suite: a pinned **theme taxonomy** → vector **theme assignment** → **outlier** flag → **exemplar/outlier highlights** per theme. |
| [`analyze/metrics-trend.md`](analyze/metrics-trend.md) | The **records → aggregate grain shift**: deterministic `period × dimension` rollup with QoQ trend, level/mix share, and z-score anomalies; plus a simple count-over-time trend. No AI; `FULL` but cheap. |
| [`analyze/synthesize.md`](analyze/synthesize.md) | Aggregate-grain `LISTAGG → AI_COMPLETE`: a ranked **insights & actions** set (from metrics) or a **corpus narrative** (from summaries). |

### `search/` — the retrieval / RAG layer
| File | What it gives you |
|------|-------------------|
| [`search/chunk-index.md`](search/chunk-index.md) | The **doc → chunk grain shift**: split text into source-located chunks (optional metadata facets), then a self-refreshing **Cortex Search service** — the searchable, agent-ready deliverable. |
| [`search/rag-answer.md`](search/rag-answer.md) | The query surface: `SEARCH_PREVIEW` → `AI_COMPLETE` for a grounded, **cited** answer with an insufficient-context guard, plus an optional `ask_<prefix>` Python stored-proc wrapper. |

### `serve/` — user-facing outputs
| File | What it gives you |
|------|-------------------|
| [`serve/final-shape.md`](serve/final-shape.md) | Thin serving **views** over the terminal DTs by grain (per-document header/lines, per-entity record, corpus items + profile), hiding `RAW_*` and intermediate columns. |
| [`serve/presentation.md`](serve/presentation.md) | A no-SQL **Streamlit-in-Snowflake** app over the published contract: one render per output wired into tabs (Ask / Search / Overview / Themes / Outliers / Insights / Explore). Covers both search and corpus apps. |

---

## Recipes (known use cases)

Each template's `SKILL.md` is the authoritative recipe (intake, defaults, build gate); these are the block sets.

| Use case | Block set |
|----------|-----------|
| **Invoice / single-type extraction** | `ingest/ingestion` + `ingest/parse-text` → `extract/classify` (gate, optional) → `extract/fields` (header + line-items) → `records/validate` (reconcile, optional) → `serve/final-shape`. Add `records/reason`+`triage` for a review queue. |
| **Structured extraction (multi-type)** | spine: `ingest/*` → `extract/classify` (router) → `extract/fields` (per type) + `extract/vision-structured` → `records/entity`. Operational head: `records/reason` → `records/triage`. Analytical head: `analyze/metrics-trend` → `analyze/synthesize`. Tail: `serve/final-shape`. |
| **Corpus intelligence** | `ingest/ingestion` + `ingest/parse-text` → `extract/fields` (schema-elicited) → `analyze/summarize-embed` → `analyze/themes-clusters` → `analyze/synthesize` (narrative) (+ `analyze/metrics-trend` trend) → `serve/final-shape` + `serve/presentation`. Optional `extract/vision-figures`, `search/*`. |
| **Enterprise search / RAG** | `ingest/ingestion` + `ingest/parse-pages` → (`extract/vision-figures` + enrich, optional) → `search/chunk-index` → `search/rag-answer` → `serve/presentation`. Optional metadata facets in `chunk-index`. |
| **Something else** | Pick blocks by the index above — match each block's `Reads` shape (in `conventions.md`) to an upstream's `Produces`. e.g. add `search/*` to a corpus pipeline for Q&A, or `analyze/synthesize` to an extraction pipeline for an exec summary. |
