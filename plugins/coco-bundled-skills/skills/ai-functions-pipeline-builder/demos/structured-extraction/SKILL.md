---
name: structured-extraction-demo
description: "Interactive demo: turn a pile of mixed auto-insurance claim documents (intake forms, repair estimates, police reports, damage photos) into triaged, decision-ready records on Snowflake Cortex. Showcases AI_CLASSIFY routing, AI_EXTRACT with confidence scores, vision damage assessment, an AI decision, and confidence-gated triage lanes on incremental dynamic tables. Use when the user picks the Structured Extraction demo, or wants a walkthrough of document classification, field extraction, claims intake, or automated triage."
parent_skill: demos
---
<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Structured Extraction Demo

Turn a pile of mixed auto-insurance claim documents into triaged, decision-ready records: classify each document, route it to a type-specific extractor with per-field confidence, assess the damage photo with vision, assemble one record per claim, then decide and triage into `auto_settle` / `needs_review` / `reject` lanes. **Tag:** `CLM`. **Time:** ~10-15 min.

**The hero:** the pipeline turns a folder of unlabeled documents into an **auto-settle rate**. `AI_CLASSIFY` is the traffic controller (junk is gated to `other`), each type gets its own extractor with confidence scores, and hard business rules plus an AI decision send only the uncertain or high-risk claims to a human. Because the corpus is synthetic, planted fraud cues let the demo *measure* whether the pipeline caught them.

## Read first

The shared scaffold — [`../conventions.md`](../conventions.md) — carries location, cost gate, consent, cleanup, and stopping points. This file adds only the structured-extraction specifics and the run order.

## Pipeline

```
DEMO_CLM_DOCS_STAGE (mixed PDFs + damage photos in incoming/)
  -> DEMO_CLM_FILE_LOG          stream + task ingestion
  -> DT_DEMO_CLM_CLASSIFIED     AI_CLASSIFY(TO_FILE) -> DOC_TYPE      [traffic controller + junk gate]
  -> DT_DEMO_CLM_PARSED         AI_PARSE_DOCUMENT(LAYOUT)  (textual types only)
  -> routed extraction (each reads its DOC_TYPE slice):
       DT_DEMO_CLM_FNOL         AI_EXTRACT(scores=>TRUE)  fields + per-field confidence
       DT_DEMO_CLM_ESTIMATE     AI_EXTRACT                shop, total
       DT_DEMO_CLM_POLICE       AI_EXTRACT                report_no, fault, narrative
       DT_DEMO_CLM_PHOTO        AI_COMPLETE(vision+JSON)  severity, parts, fraud cues
  -> DT_DEMO_CLM_CLAIM          LEFT JOIN the four on CLAIM_NO -> one record per claim
  -> DT_DEMO_CLM_DECISION       AI_COMPLETE(json) -> recommended_action, fraud_risk, settlement_estimate, rationale
  -> DT_DEMO_CLM_TRIAGED        confidence + decision -> ROUTE                        [terminal]
  -> views DEMO_CLM_AUTO_SETTLE / _NEEDS_REVIEW / _REJECTED / _CLAIM_INTELLIGENCE
```

`CLAIM_NO` (parsed from the staged path `incoming/<claim_no>__<type>.<ext>`) ties a packet together — even the photo, which carries no claim number, attaches to the right claim. Classification is honest AI: it reads the document bytes, never the `__<type>` token in the filename.

**Build pattern — zero-spend scaffold.** Every dynamic table is created `INITIALIZE = ON_SCHEDULE` and the terminal is left suspended, so `10_pipeline.sql` compiles the chain and fixes refresh modes with **no AI, no spend**. The first AI-bearing action is the explicit refresh in [`20_triage.sql`](20_triage.sql) section A — which sits behind the cost gate.

Files: [`00_setup.sql`](00_setup.sql), [`10_pipeline.sql`](10_pipeline.sql), [`20_triage.sql`](20_triage.sql), [`notebook.ipynb`](notebook.ipynb). Sourcing: [`../scripts/data_sources/source_structured_extraction.py`](../scripts/data_sources/source_structured_extraction.py).

## Workflow

This demo instantiates the canonical [`../conventions.md`](../conventions.md) seven-step sequence with tag `CLM`. Open by explaining the hero (above) and that the demo creates `DEMO_CLM_` / `DT_DEMO_CLM_` objects in the user's account, with cleanup offered at the end.

### Step 1: Location

Do [`../conventions.md`](../conventions.md) step 1 with tag `CLM`: gather `{database}` / `{schema}` / `{warehouse}` and the connection name, and run the collision check `SHOW TERSE OBJECTS LIKE '%DEMO_CLM%' IN SCHEMA {database}.{schema};` (catches both `DEMO_CLM_` and `DT_DEMO_CLM_`).

### Step 2: Setup

Do [`../conventions.md`](../conventions.md) step 2: substitute the placeholders and run [`00_setup.sql`](00_setup.sql) — schema context, the SSE directory stage, the JSON file format, the file log, the stage stream, the suspended ingest task, and the `DEMO_CLM_GROUND_TRUTH` table. No AI, no spend.

### Step 3: Source the sample corpus (consent)

Do [`../conventions.md`](../conventions.md) step 3. **Dataset + terms:** the claim *documents* are **synthesized locally** (forms via Jinja2 + WeasyPrint, Faker-populated) — nothing is downloaded for them. The **damage photos** are fetched at run time from the Hugging Face dataset [`DrBimmer/comprehensive-car-damage`](https://huggingface.co/datasets/DrBimmer/comprehensive-car-damage) (**MIT license**); proceed only if you're comfortable retrieving them under that license. `--skip-photos` builds the forms-only variant with no download at all. State this to the user and **wait for consent**.

WeasyPrint needs system libraries (pango, cairo, gdk-pixbuf) in addition to the Python extra — see [`../scripts/pyproject.toml`](../scripts/pyproject.toml). Then:

```bash
uv run --project <skill_dir>/demos/scripts --extra structured-extraction python <skill_dir>/demos/scripts/data_sources/source_structured_extraction.py \
  --connection {connection} --database {database} --schema {schema}
# smaller first run: add  --packets 12
# forms only (no photo download): add  --skip-photos   (then drop DT_DEMO_CLM_PHOTO in step 5)
```

The script synthesizes the corpus, PUTs the PDFs + photos + `manifest.json` to `@DEMO_CLM_DOCS_STAGE`, refreshes the stage directory, **runs the ingest task once to backfill `DEMO_CLM_FILE_LOG`**, and loads `DEMO_CLM_GROUND_TRUTH` from the manifest. Confirm: `SELECT 'file_log', COUNT(*) FROM DEMO_CLM_FILE_LOG UNION ALL SELECT 'ground_truth', COUNT(*) FROM DEMO_CLM_GROUND_TRUTH;`.

### Step 4: Cost gate

Do [`../conventions.md`](../conventions.md) step 4. Here `10_pipeline.sql` is **zero-spend** (scaffold); **the first AI runs when you execute [`20_triage.sql`](20_triage.sql) section A** in step 5. Show the cost warning and this estimate (full 40-claim / ~146-file corpus) first:

- `AI_CLASSIFY`: ~146 (every file, including junk).
- `AI_PARSE_DOCUMENT`: ~112 (fnol + estimate + police).
- `AI_EXTRACT`: ~112 (40 fnol with scores + 40 estimate + 32 police).
- `AI_COMPLETE` (vision): ~30 (damage photos).
- `AI_COMPLETE` (decision): ~40 (one per claim).

Fewer `--packets` scales all of these down. Present the DAG + pricing and **wait for approval**.

### Step 5: Build

Do [`../conventions.md`](../conventions.md) step 5 (zero-spend-scaffold pattern). Compile-validate and create the chain by running [`10_pipeline.sql`](10_pipeline.sql) — this is **no-spend**: the DTs are `INITIALIZE = ON_SCHEDULE` and the terminal is suspended, so nothing refreshes yet. **Verify refresh modes now, before any AI**: run [`20_triage.sql`](20_triage.sql) section B (`SHOW DYNAMIC TABLES LIKE 'DT_DEMO_CLM%'`) and confirm **every** DT reports `refresh_mode = INCREMENTAL` — a `FULL` per-document DT would re-run AI on every refresh; stop and fix before spending. Then, on the approval from step 4, run [`20_triage.sql`](20_triage.sql) **section A** (optionally the section A1 smoke first) — the ordered `ALTER DYNAMIC TABLE ... REFRESH` sweep is the first AI-bearing action.

### Step 6: Showcase

Run [`20_triage.sql`](20_triage.sql) sections C (health) and D (deliverables), then open [`notebook.ipynb`](notebook.ipynb) for the narrated version. Land the hero: **D1** is the triage lanes + auto-settle rate; **D4** shows the planted fraud cues that got escalated (the money-fraud cues get caught; subtler ones are the argument for a human in the loop); **D5** is extraction accuracy vs. the planted truth.

### Step 7: Cleanup

Offer teardown per [`../conventions.md`](../conventions.md) step 7. The DROP set (reverse dependency order):

```sql
ALTER TASK {database}.{schema}.DEMO_CLM_INGEST_TASK SUSPEND;
DROP VIEW IF EXISTS {database}.{schema}.DEMO_CLM_CLAIM_INTELLIGENCE;
DROP VIEW IF EXISTS {database}.{schema}.DEMO_CLM_AUTO_SETTLE;
DROP VIEW IF EXISTS {database}.{schema}.DEMO_CLM_NEEDS_REVIEW;
DROP VIEW IF EXISTS {database}.{schema}.DEMO_CLM_REJECTED;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_CLM_TRIAGED;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_CLM_DECISION;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_CLM_CLAIM;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_CLM_PHOTO;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_CLM_POLICE;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_CLM_ESTIMATE;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_CLM_FNOL;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_CLM_PARSED;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_CLM_CLASSIFIED;
DROP TASK IF EXISTS {database}.{schema}.DEMO_CLM_INGEST_TASK;
DROP STREAM IF EXISTS {database}.{schema}.DEMO_CLM_STAGE_STREAM;
DROP TABLE IF EXISTS {database}.{schema}.DEMO_CLM_FILE_LOG;
DROP TABLE IF EXISTS {database}.{schema}.DEMO_CLM_GROUND_TRUTH;
DROP FILE FORMAT IF EXISTS {database}.{schema}.DEMO_CLM_JSON_FMT;
DROP STAGE IF EXISTS {database}.{schema}.DEMO_CLM_DOCS_STAGE;
```

**STOP**: present this list and wait for approval — DROP is irreversible.

## Next steps

To build the same pipeline over the user's own documents, point them to [`../../templates/structured-extraction/SKILL.md`](../../templates/structured-extraction/SKILL.md).

## Stopping points

- ✋ Step 1: location. ✋ Step 2: setup approval. ✋ Step 3: dataset consent. ✋ Step 4: cost approval. ✋ Step 5: fix any non-`INCREMENTAL` DT before running section A. ✋ Step 7: teardown approval.

## Text-only variant

No damage photos: run the sourcing script with `--skip-photos`, and drop `DT_DEMO_CLM_PHOTO` from [`10_pipeline.sql`](10_pipeline.sql) (photos are still classified and counted, but not vision-assessed). Triage conservatively escalates any high-value claim with missing evidence, so the operational story holds. Everything else is unchanged.
