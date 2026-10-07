---
name: enterprise-search-demo
description: "Interactive demo: turn a shelf of consumer-goods annual reports into a searchable, chart-aware knowledge base with grounded, cited RAG answers on Snowflake Cortex. Showcases AI_PARSE_DOCUMENT, chart vision with AI_COMPLETE, Cortex Search, and incremental dynamic tables. Use when the user picks the Enterprise Search demo, or wants a walkthrough of RAG / enterprise search / chart-aware search over documents."
parent_skill: demos
---
<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Enterprise Search Demo

Build a searchable, chart-aware knowledge base over five consumer-goods annual reports, then answer questions with grounded, page-cited RAG. **Tag:** `ESR`. **Time:** ~10-15 min.

**The hero:** the meaning locked inside **charts** (net sales by segment, growth, margins) — which live only as images — is described by a vision model and folded into the searchable text. A query like *"what does P&G's net-sales-by-segment chart show?"* returns a real answer, not just the page around the figure.

## Read first

The shared scaffold — [`../conventions.md`](../conventions.md) — carries location, cost gate, consent, cleanup, and stopping points. This file adds only the enterprise-search specifics and the run order.

## Pipeline

```
DEMO_ESR_DOCS_STAGE (report PDFs + per-page PNGs)
  -> DEMO_ESR_FILE_LOG        stream + task ingestion
  -> DT_DEMO_ESR_PARSED       AI_PARSE_DOCUMENT(LAYOUT, page_split)
  -> DT_DEMO_ESR_PAGES        FLATTEN :pages -> one row per (company, page)
  -> DT_DEMO_ESR_FIGURES      AI_COMPLETE(vision) over page PNGs -> chart narrative   [the hero]
  -> DT_DEMO_ESR_ENRICHED     page text + chart narrative
  -> DT_DEMO_ESR_CHUNK_ARR    SPLIT_TEXT_RECURSIVE_CHARACTER -> array
  -> DT_DEMO_ESR_CHUNKS       FLATTEN -> one row per chunk
  -> DEMO_ESR_SEARCH          CREATE CORTEX SEARCH SERVICE
  -> RAG answers              SEARCH_PREVIEW + AI_COMPLETE + citations
```

Files: [`00_setup.sql`](00_setup.sql), [`10_pipeline.sql`](10_pipeline.sql), [`20_rag.sql`](20_rag.sql), [`notebook.ipynb`](notebook.ipynb). Sourcing: [`../scripts/data_sources/source_enterprise_search.py`](../scripts/data_sources/source_enterprise_search.py).

## Workflow

This demo instantiates the canonical [`../conventions.md`](../conventions.md) seven-step sequence with tag `ESR`. Open by explaining the hero (above) and that the demo creates `DEMO_ESR_` / `DT_DEMO_ESR_` objects in the user's account, with cleanup offered at the end.

### Step 1: Location

Do [`../conventions.md`](../conventions.md) step 1 with tag `ESR`: gather `{database}` / `{schema}` / `{warehouse}` and the connection name, and run the collision check `SHOW TERSE OBJECTS LIKE '%DEMO_ESR%' IN SCHEMA {database}.{schema};` (catches both `DEMO_ESR_` and `DT_DEMO_ESR_`).

### Step 2: Setup

Do [`../conventions.md`](../conventions.md) step 2: substitute the placeholders and run [`00_setup.sql`](00_setup.sql) — schema context, the SSE directory stage, the file log, the stage stream, the suspended ingest task, and the `DEMO_ESR_COMPANIES` dimension. No AI, no spend.

### Step 3: Source the sample corpus (consent)

Do [`../conventions.md`](../conventions.md) step 3. **Dataset + terms:** five consumer-goods annual reports / 10-Ks (Unilever, Nestlé, P&G, PepsiCo, Coca-Cola). The script fetches each PDF **directly from the issuer's own IR site or SEC EDGAR** and renders page images locally — nothing is redistributed by this skill, and the document set is pinned in the script for reproducibility. These are the issuers' copyrighted filings; proceed only if you're comfortable retrieving them from those source sites under their terms. State this to the user and **wait for consent**, then:

```bash
uv run --project <skill_dir>/demos/scripts python <skill_dir>/demos/scripts/data_sources/source_enterprise_search.py \
  --connection {connection} --database {database} --schema {schema}
# smaller first run: add  --only pg unilever --max-pages 40
```

The script downloads the PDFs, renders page PNGs, PUTs both to `@DEMO_ESR_DOCS_STAGE`, and refreshes the stage directory. Then backfill the file log by running the ingest task once:

```sql
EXECUTE TASK {database}.{schema}.DEMO_ESR_INGEST_TASK;
```

Confirm files landed: `SELECT SPLIT_PART(RELATIVE_PATH,'/',1) top, COUNT(*) FROM DIRECTORY(@DEMO_ESR_DOCS_STAGE) GROUP BY 1;` and `SELECT COUNT(*) FROM DEMO_ESR_FILE_LOG;`.

### Step 4: Cost gate

Do [`../conventions.md`](../conventions.md) step 4. **Running [`10_pipeline.sql`](10_pipeline.sql) in step 5 is what triggers AI** — show the cost warning and this estimate first:

- `AI_PARSE_DOCUMENT`: once per report PDF.
- `AI_COMPLETE` (vision): once per staged page PNG — the dominant cost; capped by `--max-pages` (default 80/doc). Trim with `--only` / `--max-pages` for a first pass.
- `AI_COMPLETE` (RAG answers): once per question in the showcase (step 6).

Present the DAG + pricing and **wait for approval**.

### Step 5: Build

Do [`../conventions.md`](../conventions.md) step 5. Compile-validate the `CREATE`s; optionally smoke first — chain parse + one-page vision on a single file interactively — then on approval run [`10_pipeline.sql`](10_pipeline.sql). Once the DTs refresh, **verify refresh modes**: run the top of [`20_rag.sql`](20_rag.sql) (`SHOW DYNAMIC TABLES LIKE 'DT_DEMO_ESR%'`), confirm **every** DT reports `refresh_mode = INCREMENTAL`, then the row-count health check. A `FULL` DT re-runs AI on every refresh — stop and fix before going further.

### Step 6: Showcase

Run the retrieval preview and the three RAG queries in [`20_rag.sql`](20_rag.sql), then open [`notebook.ipynb`](notebook.ipynb) for the narrated version. Land the hero: **Q3** filters to P&G and answers from chart content that exists only as an image — confirm `DT_DEMO_ESR_FIGURES` has non-`NO_CHART` narratives for its chart pages.

### Step 7: Cleanup

Offer teardown per [`../conventions.md`](../conventions.md) step 7. The DROP set (reverse dependency order):

```sql
ALTER TASK {database}.{schema}.DEMO_ESR_INGEST_TASK SUSPEND;
DROP CORTEX SEARCH SERVICE IF EXISTS {database}.{schema}.DEMO_ESR_SEARCH;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_ESR_CHUNKS;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_ESR_CHUNK_ARR;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_ESR_ENRICHED;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_ESR_FIGURES;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_ESR_PAGES;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_ESR_PARSED;
DROP TASK IF EXISTS {database}.{schema}.DEMO_ESR_INGEST_TASK;
DROP STREAM IF EXISTS {database}.{schema}.DEMO_ESR_STAGE_STREAM;
DROP TABLE IF EXISTS {database}.{schema}.DEMO_ESR_FILE_LOG;
DROP TABLE IF EXISTS {database}.{schema}.DEMO_ESR_COMPANIES;
DROP STAGE IF EXISTS {database}.{schema}.DEMO_ESR_DOCS_STAGE;
```

**STOP**: present this list and wait for approval — DROP is irreversible.

## Next steps

To build the same pipeline over the user's own documents, point them to [`../../templates/enterprise-search/SKILL.md`](../../templates/enterprise-search/SKILL.md).

## Stopping points

- ✋ Step 1: location. ✋ Step 2: setup approval. ✋ Step 3: dataset consent. ✋ Step 4: cost approval. ✋ Step 5: fix any non-`INCREMENTAL` DT. ✋ Step 7: teardown approval.

## Text-only variant

No chart images: source with `--skip-render`, then trim [`10_pipeline.sql`](10_pipeline.sql) before running:

1. **Delete** the entire `DT_DEMO_ESR_FIGURES` block (`CREATE OR REPLACE DYNAMIC TABLE DT_DEMO_ESR_FIGURES` through its `WHERE fl.RELATIVE_PATH ILIKE 'pages/%'` filter).
2. **Replace** `DT_DEMO_ESR_ENRICHED` with a direct pass-through from pages — drop the `LEFT JOIN DT_DEMO_ESR_FIGURES` and the `CASE` merge:

```sql
CREATE OR REPLACE DYNAMIC TABLE DT_DEMO_ESR_ENRICHED
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = {warehouse}  REFRESH_MODE = INCREMENTAL
AS
  SELECT pg.RELATIVE_PATH, pg.COMPANY, pg.PAGE, pg.CONTENT
  FROM DT_DEMO_ESR_PAGES pg;
```

Chunking and Cortex Search are unchanged. Loses chart-only facts readable from images; body-text RAG still works.
