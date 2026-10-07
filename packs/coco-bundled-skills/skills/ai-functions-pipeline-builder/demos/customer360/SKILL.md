---
name: customer360-demo
description: "Interactive demo: fuse six structured tables (customers, products, transactions, daily telemetry, survey scores, campaigns) with AI signals extracted from unstructured customer docs (support tickets, chat and call transcripts, survey comments, error reports) into one per-customer 360 record with a risk tier and route, plus a product-health landscape. Showcases AI_CLASSIFY routing, AI_COMPLETE signal extraction, a warehouse JOIN that reconciles structured facts with AI evidence, Cortex Search over the docs, and an AI executive briefing on incremental dynamic tables. Use when the user picks the Customer 360 demo, or wants a walkthrough of structured+unstructured fusion, churn/health scoring, customer risk routing, or joining documents to a data warehouse."
parent_skill: demos
---
<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Customer 360 Demo

Fuse a customer data warehouse with the documents customers generate: classify each doc, extract a sentiment + issue signal, then **JOIN those AI signals onto six structured tables** (customers, products, transactions, daily telemetry, survey scores, campaigns) to produce one per-customer 360 record with a `RISK_TIER` and a `ROUTE` (`escalate` / `needs_review` / `auto_act`), plus a per-product health landscape with an AI-written executive briefing. **Tag:** `C360`. **Time:** ~10-15 min.

**The hero:** risk is not legible from any single source. A customer with clean telemetry and a decent NPS can still be high-risk because their support tickets read **negative** (an AI signal), and a cratering daily-active-user trend flags a "silent" account that never filed a ticket. **Fusion** = structured facts + AI-extracted doc signals, reconciled by SQL rules with per-cohort guardrails, so every customer is scored — not just the ones who complained.

## Read first

The shared scaffold — [`../conventions.md`](../conventions.md) — carries location, cost gate, consent, cleanup, and stopping points. This file adds only the customer-360 specifics and the run order.

## Pipeline

```
DEMO_C360_* structured tables (pre-loaded)      DEMO_C360_DOCS_STAGE (customer docs in incoming/)
                                                  -> DEMO_C360_FILE_LOG        stream + task ingestion
                                                  -> DT_DEMO_C360_CLASSIFIED   AI_CLASSIFY -> DOC_TYPE   [doc gate]
                                                  -> DT_DEMO_C360_CUSTOMER_DOCS attach CONTENT, drop 'other'
                                                  -> DT_DEMO_C360_DOC_SIGNALS   AI_COMPLETE(json) sentiment + issue
                                                       |
  the six tables + the doc signals  ---- JOIN ---->  DT_DEMO_C360_CUSTOMER_RECORD   RISK_TIER + ROUTE   [deliverable]
                                                  -> DT_DEMO_C360_SEARCH_CHUNKS  (DEMO_C360_SEARCH built in 20 A)
                                                  -> DT_DEMO_C360_HEALTH_LANDSCAPE  AI_COMPLETE briefing per product [deliverable]
                                                  -> views DEMO_C360_HIGH_RISK / _NEEDS_REVIEW / _AUTO_ACT / _CUSTOMER_360
```

`CUSTOMER_ID` (parsed from the staged path `incoming/<customer_id>__<type>.txt`) links a doc to its account. Classification is honest AI: it reads the document text, never the `__<type>` token. Junk docs carry no customer prefix and classify to `other`, so they drop out before the signal step. Each customer also carries a `COHORT_STORY` (planted at synthesis) that fusion uses only as a **guardrail** — e.g. a billing dispute's one negative doc must not, alone, force `high`.

**Build pattern — zero-spend scaffold.** Every dynamic table is created `INITIALIZE = ON_SCHEDULE` and the two deliverable DTs are left suspended, so `10_pipeline.sql` compiles the chain and fixes refresh modes with **no AI, no spend**. The first AI-bearing action is the explicit refresh in [`20_insights.sql`](20_insights.sql) section A — which sits behind the cost gate.

Files: [`00_setup.sql`](00_setup.sql), [`10_pipeline.sql`](10_pipeline.sql), [`20_insights.sql`](20_insights.sql), [`notebook.ipynb`](notebook.ipynb), [`../scripts/data_sources/source_customer360.py`](../scripts/data_sources/source_customer360.py). The notebook and sourcing script ship in the stacked corpus PR (#3441); merge the stack (or check out that branch) before running steps 3 and 6.

## Workflow

This demo instantiates the canonical [`../conventions.md`](../conventions.md) seven-step sequence with tag `C360`. Open by explaining the hero (above) and that the demo creates `DEMO_C360_` / `DT_DEMO_C360_` objects in the user's account, with cleanup offered at the end.

### Step 1: Location

Do [`../conventions.md`](../conventions.md) step 1 with tag `C360`: gather `{database}` / `{schema}` / `{warehouse}` and the connection name, and run the collision check `SHOW TERSE OBJECTS LIKE '%DEMO_C360%' IN SCHEMA {database}.{schema};` (catches both `DEMO_C360_` and `DT_DEMO_C360_`).

### Step 2: Setup

Do [`../conventions.md`](../conventions.md) step 2: substitute the placeholders and run [`00_setup.sql`](00_setup.sql) — schema context, the six `DEMO_C360_` structured tables (empty; loaded in step 3), the CSV file format, the SSE structured stage, the SSE directory docs stage, the file log (with a `CONTENT` column), the stage stream, and the suspended ingest task. No AI, no spend.

### Step 3: Source the sample corpus (consent)

Do [`../conventions.md`](../conventions.md) step 3. **Dataset + terms:** the entire corpus — the six structured tables **and** the customer docs — is **synthesized locally** from a seed (Faker-populated names/companies; nothing is downloaded or redistributed). It's synthetic precisely because real customer records are PII / contract-restricted. State this to the user and **wait for consent**. Then:

```bash
uv run --project <skill_dir>/demos/scripts --extra customer360 python <skill_dir>/demos/scripts/data_sources/source_customer360.py \
  --connection {connection} --database {database} --schema {schema}
# smaller first run: add  --customers 20
```

The script synthesizes the six CSVs + the customer docs, PUTs the CSVs to `@DEMO_C360_STRUCTURED_STAGE` and `COPY`s them into the tables, PUTs the docs to `@DEMO_C360_DOCS_STAGE/incoming/`, refreshes the stage directory, **runs the ingest task once to backfill `DEMO_C360_FILE_LOG`** (a hard gate — it aborts rather than proceed on a partial file log), then backfills `DEMO_C360_FILE_LOG.CONTENT` from the local doc text. Confirm every staged doc has its text loaded (the two counts must match):

```sql
SELECT (SELECT COUNT(*) FROM DIRECTORY(@DEMO_C360_DOCS_STAGE) WHERE RELATIVE_PATH ILIKE 'incoming/%') AS staged_docs,
       (SELECT COUNT(*) FROM DEMO_C360_FILE_LOG WHERE CONTENT IS NOT NULL)                            AS file_log_with_content;
```

### Step 4: Cost gate

Do [`../conventions.md`](../conventions.md) step 4. Here `10_pipeline.sql` is **zero-spend** (scaffold); **the first AI runs when you execute [`20_insights.sql`](20_insights.sql) section A** in step 5. Show the cost warning and this estimate (default ~40-customer corpus, ~48 docs) first:

- `AI_CLASSIFY`: ~48 (per-document: every doc, including junk).
- `AI_COMPLETE` (sentiment): ~44 (per-document: every non-`other` doc).
- `AI_COMPLETE` (briefing): ~5 (per-product, once per health-landscape refresh — not per document).
- `DEMO_C360_SEARCH`: a separate indexing + serving cost surface.

Fewer `--customers` scales the **per-document** costs (classify + sentiment) down; the per-product briefings and the junk docs (fixed unless `--junk` changes) don't follow customer count, and search indexing/serving is its own surface. Present the DAG + pricing and **wait for approval**.

### Step 5: Build

Do [`../conventions.md`](../conventions.md) step 5 (zero-spend-scaffold pattern). Compile-validate and create the chain by running [`10_pipeline.sql`](10_pipeline.sql) — this is **no-spend**: the DTs are `INITIALIZE = ON_SCHEDULE` and the two deliverable DTs are suspended, so nothing refreshes yet. **Verify refresh modes now, before any AI**: run [`20_insights.sql`](20_insights.sql) **section 0 (preflight)** — it's the zero-spend `SHOW DYNAMIC TABLES LIKE 'DT_DEMO_C360%'` gate; confirm **every** DT reports `refresh_mode = INCREMENTAL` (a `FULL` per-document DT would re-run AI on every refresh; stop and fix before spending). Then, on the approval from step 4, run [`20_insights.sql`](20_insights.sql) **section A** (optionally the section A1 smoke first) — the ordered `ALTER DYNAMIC TABLE ... REFRESH` sweep, ending with the `CREATE CORTEX SEARCH SERVICE DEMO_C360_SEARCH` that builds + serves the doc-text index, is the first AI-bearing action. (The search service is created here, not in `10_pipeline.sql`, because a service is active on creation.)

### Step 6: Showcase

Run [`20_insights.sql`](20_insights.sql) sections C (health) and D (deliverables), then open [`notebook.ipynb`](notebook.ipynb) for the narrated version. Land the hero: **D1** is the risk-tier × route distribution across *all* customers; **D3** is the fusion proof — customers who look fine on structured signals but are high/medium risk purely because their docs read negative; **D5** pulls the exact ticket behind a risk tier via Cortex Search; **D6** checks the computed tiers against each planted `COHORT_STORY`.

### Step 7: Cleanup

Offer teardown per [`../conventions.md`](../conventions.md) step 7. The DROP set (reverse dependency order):

```sql
ALTER TASK {database}.{schema}.DEMO_C360_INGEST_TASK SUSPEND;
DROP VIEW IF EXISTS {database}.{schema}.DEMO_C360_CUSTOMER_360;
DROP VIEW IF EXISTS {database}.{schema}.DEMO_C360_HIGH_RISK;
DROP VIEW IF EXISTS {database}.{schema}.DEMO_C360_NEEDS_REVIEW;
DROP VIEW IF EXISTS {database}.{schema}.DEMO_C360_AUTO_ACT;
DROP CORTEX SEARCH SERVICE IF EXISTS {database}.{schema}.DEMO_C360_SEARCH;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_C360_HEALTH_LANDSCAPE;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_C360_SEARCH_CHUNKS;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_C360_CUSTOMER_RECORD;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_C360_DOC_SIGNALS;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_C360_CUSTOMER_DOCS;
DROP DYNAMIC TABLE IF EXISTS {database}.{schema}.DT_DEMO_C360_CLASSIFIED;
DROP TASK IF EXISTS {database}.{schema}.DEMO_C360_INGEST_TASK;
DROP STREAM IF EXISTS {database}.{schema}.DEMO_C360_STAGE_STREAM;
DROP TABLE IF EXISTS {database}.{schema}.DEMO_C360_FILE_LOG;
DROP TABLE IF EXISTS {database}.{schema}.DEMO_C360_CUSTOMERS;
DROP TABLE IF EXISTS {database}.{schema}.DEMO_C360_PRODUCTS;
DROP TABLE IF EXISTS {database}.{schema}.DEMO_C360_TRANSACTIONS;
DROP TABLE IF EXISTS {database}.{schema}.DEMO_C360_TELEMETRY_DAILY;
DROP TABLE IF EXISTS {database}.{schema}.DEMO_C360_SURVEY_SCORES;
DROP TABLE IF EXISTS {database}.{schema}.DEMO_C360_CAMPAIGNS;
DROP FILE FORMAT IF EXISTS {database}.{schema}.DEMO_C360_TXT_FMT;
DROP FILE FORMAT IF EXISTS {database}.{schema}.DEMO_C360_CSV_FMT;
DROP STAGE IF EXISTS {database}.{schema}.DEMO_C360_DOCS_STAGE;
DROP STAGE IF EXISTS {database}.{schema}.DEMO_C360_STRUCTURED_STAGE;
```

**STOP**: present this list and wait for approval — DROP is irreversible.

## Next steps

To build the same fusion pipeline over the user's own warehouse tables + documents, point them to [`../../templates/customer360/SKILL.md`](../../templates/customer360/SKILL.md).

## Stopping points

- ✋ Step 1: location. ✋ Step 2: setup approval. ✋ Step 3: dataset consent. ✋ Step 4: cost approval. ✋ Step 5: fix any non-`INCREMENTAL` DT before running section A. ✋ Step 7: teardown approval.
