---
name: corpus-intelligence-demo
description: "Interactive demo: read across a collection of open-access research papers on Snowflake Cortex -- parse each paper, read numbers off figures with vision, extract trial fields, judge significance, then synthesize cross-document trends and a competitive-landscape briefing per drug. Showcases AI_PARSE_DOCUMENT, figure vision with AI_COMPLETE, AI_EXTRACT, and incremental cross-document aggregation on dynamic tables. Use when the user picks the Corpus Intelligence / Research Analytics demo, or wants a walkthrough of deep analytics across many documents, literature review, or cross-document synthesis."
parent_skill: demos
---
<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Corpus Intelligence Demo

Read across a collection of open-access GLP-1 / incretin research papers: parse each paper, read quantitative results off its **figures** with vision, extract structured trial fields, judge significance, then roll up cross-document **trends** and an AI-written **competitive-landscape briefing per drug**. **Tag:** `RES`. **Time:** ~15 min.

**The hero:** value that exists in no single document. The pipeline turns ~50 papers into a per-drug briefing that synthesizes what *all* of a drug's studies collectively show — efficacy with the strongest numbers, strength of evidence, positioning within the class — and it re-synthesizes automatically as new papers land. Numbers locked inside forest plots and Kaplan-Meier curves are read by vision and become extractable alongside the body text.

## Read first

The shared scaffold — [`../conventions.md`](../conventions.md) — carries location, cost gate, consent, cleanup, and stopping points. This file adds only the corpus-intelligence specifics and the run order.

## Pipeline

```
DEMO_RES_DOCS_STAGE (paper PDFs + per-page PNGs)
  -> DEMO_RES_FILE_LOG        stream + task ingestion
  -> DT_DEMO_RES_PARSED       AI_PARSE_DOCUMENT(LAYOUT) -> full paper text
  -> DT_DEMO_RES_FIGURES      AI_COMPLETE(vision) per page -> figure findings (or NO_FIGURE)  [the hero input]
  -> DT_DEMO_RES_FIG_AGG      GROUP BY paper -> one row / paper
  -> DT_DEMO_RES_ENRICHED     parsed text + figure findings (figure-only numbers become extractable)
  -> DT_DEMO_RES_ASSESSED     AI_COMPLETE(json) -> summary, primary finding, significance
  -> DT_DEMO_RES_ENTITIES     AI_EXTRACT -> drug / phase / n / endpoint / HR / p / sponsor / NCT
  -> DT_DEMO_RES_PAPER        assemble per paper                       -> DEMO_RES_PAPER_INTELLIGENCE
  -> DT_DEMO_RES_TRENDS       GROUP BY drug/phase/year                 -> DEMO_RES_TRENDS         [terminal]
  -> DT_DEMO_RES_LANDSCAPE    GROUP BY drug -> AI_COMPLETE briefing     -> DEMO_RES_LANDSCAPE      [terminal]
```

`DRUG` comes from the paper dimension (`DEMO_RES_PAPERS`, the reliable per-drug grouping key), falling back to the AI-extracted drug. Papers are short, so parse takes the whole document; figure vision runs per staged page image.

**Build pattern — zero-spend scaffold.** Every dynamic table is created `INITIALIZE = ON_SCHEDULE` and the two terminals are left suspended, so `10_pipeline.sql` compiles the chain and fixes refresh modes with **no AI, no spend**. The first AI-bearing action is the explicit refresh in [`20_analytics.sql`](20_analytics.sql) section A — which sits behind the cost gate.

Files: [`00_setup.sql`](00_setup.sql), [`10_pipeline.sql`](10_pipeline.sql), [`20_analytics.sql`](20_analytics.sql), [`notebook.ipynb`](notebook.ipynb), [`../scripts/data_sources/source_corpus_intelligence.py`](../scripts/data_sources/source_corpus_intelligence.py). The notebook and sourcing script ship in the stacked corpus PR (#3439); merge the stack (or check out that branch) before running steps 3 and 6.

## Workflow

This demo instantiates the canonical [`../conventions.md`](../conventions.md) seven-step sequence with tag `RES`. Open by explaining the hero (above) and that the demo creates `DEMO_RES_` / `DT_DEMO_RES_` objects in the user's account, with cleanup offered at the end.

### Step 1: Location

Do [`../conventions.md`](../conventions.md) step 1 with tag `RES`: gather `{database}` / `{schema}` / `{warehouse}` and the connection name, and run the collision check `SHOW TERSE OBJECTS LIKE '%DEMO_RES%' IN SCHEMA {database}.{schema};` (catches both `DEMO_RES_` and `DT_DEMO_RES_`).

### Step 2: Setup

Do [`../conventions.md`](../conventions.md) step 2: substitute the placeholders and run [`00_setup.sql`](00_setup.sql) — schema context, the SSE directory stage, the JSON file format, the file log, the stage stream, the suspended ingest task, and the `DEMO_RES_PAPERS` / `DEMO_RES_DRUGS` dimensions. No AI, no spend.

### Step 3: Source the sample corpus (consent)

Do [`../conventions.md`](../conventions.md) step 3. **Dataset + terms:** open-access GLP-1 / incretin papers **discovered at run time via the [Europe PMC](https://europepmc.org/) REST API** (which also indexes medRxiv / bioRxiv preprints). The script queries `OPEN_ACCESS:Y` only and downloads each paper's PDF from Europe PMC / the OA host directly — nothing is redistributed by this skill. Counts vary run to run because discovery is live. Proceed only if you're comfortable retrieving open-access papers from those sources. State this to the user and **wait for consent**, then:

```bash
uv run --project <skill_dir>/demos/scripts python <skill_dir>/demos/scripts/data_sources/source_corpus_intelligence.py \
  --connection {connection} --database {database} --schema {schema}
# smaller first pass: add  --per-drug 6 --max-pages 20
# preview discovery only (no downloads): add  --dry-run
```

The script discovers + downloads the PDFs, renders page PNGs, PUTs both + `manifest.json` to `@DEMO_RES_DOCS_STAGE`, refreshes the stage directory, **runs the ingest task once to backfill `DEMO_RES_FILE_LOG`**, and loads `DEMO_RES_PAPERS` from the manifest. Confirm: `SELECT 'file_log', COUNT(*) FROM DEMO_RES_FILE_LOG UNION ALL SELECT 'papers_dim', COUNT(*) FROM DEMO_RES_PAPERS;`.

### Step 4: Cost gate

Do [`../conventions.md`](../conventions.md) step 4. Here `10_pipeline.sql` is **zero-spend** (scaffold); **the first AI runs when you execute [`20_analytics.sql`](20_analytics.sql) section A** in step 5. Show the cost warning and this estimate first:

- `AI_COMPLETE` (vision): **once per staged page image** — the dominant cost. Capped by `--max-pages` (default 40/paper); trim with `--per-drug` / `--max-pages` for a first pass.
- `AI_PARSE_DOCUMENT`, `AI_COMPLETE` (significance), `AI_EXTRACT`: once per paper each.
- `AI_COMPLETE` (landscape briefing): once per drug.
- `AI_COMPLETE` (multi-hop Q&A): once per question in section E (step 6).

Present the DAG + pricing and **wait for approval**.

### Step 5: Build

Do [`../conventions.md`](../conventions.md) step 5 (zero-spend-scaffold pattern). Compile-validate and create the chain by running [`10_pipeline.sql`](10_pipeline.sql) — this is **no-spend**: the DTs are `INITIALIZE = ON_SCHEDULE` and the two terminals are suspended, so nothing refreshes yet. **Verify refresh modes now, before any AI**: run [`20_analytics.sql`](20_analytics.sql) section B (`SHOW DYNAMIC TABLES LIKE 'DT_DEMO_RES%'`) and confirm **every** DT reports `refresh_mode = INCREMENTAL` — a `FULL` per-paper DT would re-run AI on every refresh; stop and fix before spending. Then, on the approval from step 4, run [`20_analytics.sql`](20_analytics.sql) **section A** (optionally the section A1 smoke first) — the ordered `ALTER DYNAMIC TABLE ... REFRESH` sweep is the first AI-bearing action, and it refreshes figures before the downstream text steps so each `AI_COMPLETE` / `AI_EXTRACT` runs once against the final enriched text.

### Step 6: Showcase

Run [`20_analytics.sql`](20_analytics.sql) sections C (health), D (deliverables), and E (multi-hop Q&A), then open [`notebook.ipynb`](notebook.ipynb) for the narrated version. Land the hero: **D3** is the per-drug landscape briefing synthesized across studies; **D1** shows per-paper hazard ratios / p-values, many read off figures (cross-check against **C**'s per-drug `pages_with_figures`).

### Step 7: Cleanup

Offer teardown per [`../conventions.md`](../conventions.md) step 7. The DROP set (reverse dependency order):

```sql
ALTER TASK {database}.{schema}.DEMO_RES_INGEST_TASK SUSPEND;
DROP VIEW IF EXISTS {database}.{schema}.DEMO_RES_PAPER_INTELLIGENCE;
DROP VIEW IF EXISTS {database}.{schema}.DEMO_RES_TRENDS;
DROP VIEW IF EXISTS {database}.{schema}.DEMO_RES_LANDSCAPE;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_RES_LANDSCAPE;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_RES_TRENDS;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_RES_PAPER;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_RES_ENTITIES;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_RES_ASSESSED;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_RES_ENRICHED;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_RES_FIG_AGG;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_RES_FIGURES;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_RES_PARSED;
DROP TASK IF EXISTS {database}.{schema}.DEMO_RES_INGEST_TASK;
DROP STREAM IF EXISTS {database}.{schema}.DEMO_RES_STAGE_STREAM;
DROP TABLE IF EXISTS {database}.{schema}.DEMO_RES_FILE_LOG;
DROP TABLE IF EXISTS {database}.{schema}.DEMO_RES_PAPERS;
DROP TABLE IF EXISTS {database}.{schema}.DEMO_RES_DRUGS;
DROP FILE FORMAT IF EXISTS {database}.{schema}.DEMO_RES_JSON_FMT;
DROP STAGE IF EXISTS {database}.{schema}.DEMO_RES_DOCS_STAGE;
```

**STOP**: present this list and wait for approval — DROP is irreversible.

## Next steps

To build the same pipeline over the user's own document collection, point them to [`../../templates/corpus-intelligence/SKILL.md`](../../templates/corpus-intelligence/SKILL.md).

## Stopping points

- ✋ Step 1: location. ✋ Step 2: setup approval. ✋ Step 3: dataset consent. ✋ Step 4: cost approval. ✋ Step 5: fix any non-`INCREMENTAL` DT before running section A. ✋ Step 7: teardown approval.

## Text-only variant

No figure vision: run the sourcing script with `--skip-render` (PDFs only), and drop `DT_DEMO_RES_FIGURES` and `DT_DEMO_RES_FIG_AGG` from [`10_pipeline.sql`](10_pipeline.sql), then read `DT_DEMO_RES_ENRICHED` straight from `DT_DEMO_RES_PARSED` (body text only). Loses figure-only numbers; the significance judgment, extraction, trends, and landscape synthesis are otherwise unchanged.
