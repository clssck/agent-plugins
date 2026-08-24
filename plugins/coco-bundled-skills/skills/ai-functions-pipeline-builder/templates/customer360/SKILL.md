---
name: customer360
description: "Build a persistent Customer 360 pipeline that unifies pre-loaded warehouse tables with staged documents — classify and extract AI signals, join into one record per customer, score risk and route action lanes, optional Cortex Search RAG, optional product-health landscape with executive briefing. Use when structured customer, transaction, telemetry, and survey data already lives in Snowflake and mixed support docs land on a stage. Triggers: customer 360, unify structured and unstructured data, CSM pipeline, join documents with warehouse tables, customer risk route, product health monitoring, campaign impact analysis, executive customer insights."
parent_skill: ai-functions-pipeline-builder
---

# Customer 360 Pipeline

A **fusion recipe** over the shared block palette: one ingest spine joins **pre-loaded warehouse tables** with
**staged documents**, then optional heads for operational routing, search, and portfolio landscape.

## When to use

- Mixed customer documents on a stage — tickets, chats, surveys, calls, errors, transcripts.
- Structured tables in Snowflake — master profile plus enrichment tables — joined into one record per customer.
- AI classification and signal extraction on documents.
- Risk scoring, grounded search, and/or product-health rollups with executive briefings.

**Do NOT use for:** doc-only routing with no warehouse tables →
[`../structured-extraction/SKILL.md`](../structured-extraction/SKILL.md); search-only →
[`../enterprise-search/SKILL.md`](../enterprise-search/SKILL.md); corpus themes without a per-customer record →
[`../corpus-intelligence/SKILL.md`](../corpus-intelligence/SKILL.md).

## Read first

[`../conventions.md`](../conventions.md) · [`../../blocks/README.md`](../../blocks/README.md) ·
[`../../blocks/conventions.md`](../../blocks/conventions.md).

Read [`examples/basic.md`](examples/basic.md) before you build.

## Shape: one spine, optional heads

**Spine:** ingest → modality-aware text → classify on file content → doc signals → `DT_<prefix>_ENTITY`
`FROM <master_table>` with `LEFT JOIN` to doc aggregates and each enrichment table on `<entity_key>`.
This is the [`records/entity`](../../blocks/records/entity.md) contract extended with warehouse tables.

**Heads** — build only what the prompt named; list every lane at the build gate:

| Head | Triggers | Blocks |
|------|----------|--------|
| Operational | risk, route, triage | Deterministic `RISK_TIER` / `ROUTE` on the 360 record, or [`records/reason`](../../blocks/records/reason.md) + [`records/triage`](../../blocks/records/triage.md) for AI judgment |
| Search | searchable text, RAG, Q&A | [`search/chunk-index`](../../blocks/search/chunk-index.md) + [`search/rag-answer`](../../blocks/search/rag-answer.md) |
| Landscape | product health, campaign impact, briefing | [`analyze/metrics-trend`](../../blocks/analyze/metrics-trend.md) + [`analyze/synthesize`](../../blocks/analyze/synthesize.md), or one rollup DT with inline `AI_COMPLETE` briefing |
| Embed | similarity, clustering beyond search | [`analyze/summarize-embed`](../../blocks/analyze/summarize-embed.md) on the doc spine; off by default |

## Recipe — spine

[`ingest/ingestion`](../../blocks/ingest/ingestion.md) → [`ingest/parse-text`](../../blocks/ingest/parse-text.md) →
derive `<entity_key>` from path → [`extract/classify`](../../blocks/extract/classify.md) on `TO_FILE` or text body →
doc signals via `AI_COMPLETE` JSON, or per-type [`extract/fields`](../../blocks/extract/fields.md) when schemas are
named → `DT_<prefix>_ENTITY` with warehouse `LEFT JOIN`s → [`serve/final-shape`](../../blocks/serve/final-shape.md).

**Modality:** route formats through [`parse-text.md`](../../blocks/ingest/parse-text.md); audio uses
`AI_TRANSCRIBE` per that block. If ingest already stores plain-text bodies in a file-log `CONTENT` column, join
that in the doc-rows DT to skip re-parsing `.txt`. Default path key: token before `__` in the basename.

**Classification:** `AI_CLASSIFY` on content — never path-only `DOC_TYPE`.

## Intake — hard requirements

With [`../conventions.md`](../conventions.md) hard requirements, confirm:

1. `<master_table>` — one row per entity; default spine.
2. Enrichment tables — open list: table name, join key, aggregates to compute. Do not load unless the user asks.
3. `<entity_key>` linkage — default path-derived.
4. `AI_CLASSIFY` labels — include `other`.
5. Heads to build — operational / search / landscape / embed; spine always.

## Intake topics

| Topic | Default | Block |
|-------|---------|-------|
| Entity universe | all `<master_table>` rows | doc-only spine only if asked |
| Structured data loaded? | yes — pipeline only | — |
| Doc signals | classify + `AI_COMPLETE` JSON | `extract/fields` if schemas named |
| Risk / route | deterministic SQL | `reason` + `triage` for AI judgment |
| Search / RAG | on when asked | `search/*` |
| Landscape | metrics + synthesize when trends named; else inline rollup | `analyze/*` |
| Per-doc embeddings | off | `summarize-embed` if asked |
| Terminal lag | 1 hour | base Step 7 |

## Refresh

Spine, operational, and search chunk DTs: **`INCREMENTAL`**. `metrics-trend` / `synthesize`: **`FULL`** when used.
Inline landscape rollups on the 360 record may stay `INCREMENTAL`. Cortex Search self-refreshes but still needs an
`INCREMENTAL` chunk DT upstream.

## Smoke checks

- One file log; `AI_CLASSIFY` on content.
- Entity DT row count matches `<master_table>` unless doc-only spine; SQL joins at least one enrichment table.
- Operational: `RISK_TIER` / `ROUTE` populated when head built.
- Search: `DT_<prefix>_CHUNKS` reads doc rows; chunks populated; `SEARCH_PREVIEW` hits on a sample query.
- Landscape: sane rollup rows and non-empty briefing when built.

## Examples

- [`examples/basic.md`](examples/basic.md) — start here.
