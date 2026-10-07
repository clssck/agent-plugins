---
name: ai-functions-pipeline-builder
description: "Build Snowflake-native document and file pipelines with Cortex AI functions. Turn a plain-language request into an incremental pipeline (stream → task → INCREMENTAL dynamic tables) from a use-case template or a custom composition of building blocks — ingest files from a stage and keep the outputs fresh as new files land. Composes one-off AI steps as part of building a pipeline. Routes to AI_EXTRACT (structured fields), AI_PARSE_DOCUMENT (full text/OCR), AI_COMPLETE (visual/chart/diagram analysis), AI_CLASSIFY (categorize/triage). Use when: building a document/file processing pipeline, an incremental ingestion pipeline over a stage, or an enterprise-search / corpus-intelligence / structured-extraction / customer-360 pipeline. Triggers: document pipeline, build a pipeline, incremental pipeline, ingestion pipeline, keep outputs fresh, process new files as they land, stream and task, dynamic tables, enterprise search, corpus intelligence, structured extraction, customer 360, invoice-processing pipeline, contract analysis at scale. For a one-off task over files you already have — a single file or a one-time batch with no ongoing pipeline: extract, parse/OCR, classify, or visually analyze — use the document-intelligence skill. For standalone AI functions over already-tabular text or image rows with no file, stage, or document, defer to cortex-ai-function-studio."
---

# Pipeline Builder

Turn a plain-language request into a Snowflake-native document pipeline — pick a proven **use-case template** or **compose a custom pipeline** from building blocks — or run a quick **one-off task** (extract, parse, classify, or analyze a file or batch). Pipelines build incrementally on the hybrid **stream → file-log → dynamic-tables** architecture.

## ⚠️ Critical rules (cross-cutting — always apply)

1. **AI function names: NEVER use the `SNOWFLAKE.CORTEX` namespace prefix.** Always write `AI_EXTRACT`, `AI_PARSE_DOCUMENT`, `AI_COMPLETE`, `AI_CLASSIFY` — never `SNOWFLAKE.CORTEX.*`.
2. **Cost: warn the user to check current rates BEFORE executing any AI function.** Before running any `AI_EXTRACT`, `AI_PARSE_DOCUMENT`, `AI_COMPLETE`, or `AI_CLASSIFY` call, tell the user to confirm current pricing at the authoritative docs (links in [Pricing](#pricing)). **Never skip this.**
3. **Compile-validate generated SQL before returning or executing it.** Run every generated statement through `snowflake_sql_execute` with `only_compile: true`, fix the root cause of any failure, and re-validate. Full mechanics in [Shared mechanics and constraints](#shared-mechanics-and-constraints).
4. **NEVER write AI-function SQL from memory.** The reference files carry the authoritative syntax — read the relevant one before producing SQL.
5. **Every persistent pipeline is a stream + task + INCREMENTAL dynamic table — all three.** This is non-negotiable and applies to every template and every custom composition, not just the ones that mention it. A `CREATE STREAM … ON STAGE` detects new files; a `CREATE TASK` flushes the stream into the File Log; the per-document AI dynamic tables read the File Log with `REFRESH_MODE = INCREMENTAL`. A build that populates its deliverables perfectly but omits the stream, the task, or leaves a per-document DT on `FULL` is architecturally incomplete — it stops the moment the current backlog is processed and never ingests another file. Do **not** substitute a `CREATE TABLE AS SELECT`, a stored-procedure refresh, or a `FULL` per-document DT. See [`blocks/ingest/ingestion.md`](blocks/ingest/ingestion.md) (the three laws) and the base's Definition of done.

### Pricing

> ⚠️ **Check current rates before running any AI function** — don't quote hardcoded credit numbers; they drift, and the docs are the source of truth:
> - `AI_EXTRACT` / `AI_COMPLETE` / `AI_CLASSIFY` → [AI Functions (AISQL) Costs](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql-cost)
> - `AI_PARSE_DOCUMENT` → [Snowflake Service Consumption Table](https://docs.snowflake.com/en/user-guide/cost-understanding-overall#service-type)

The per-function references ([`references/functions/ai-extract.md`](references/functions/ai-extract.md), [`references/functions/ai-parse-doc.md`](references/functions/ai-parse-doc.md), [`references/functions/ai-complete.md`](references/functions/ai-complete.md), [`references/functions/ai-classify.md`](references/functions/ai-classify.md)) carry the same warning + links.

---

## Routing triage (start here)

Decide the path from the request — least-interruptive default, in order:

1. **One-off signal — a one-time job over files you already have, with no ongoing ingestion.** Either a single file ("what's the total on *this* invoice?", "read the text out of this PDF", "what does this chart say?") **or a one-time batch** over what's already on a stage ("classify all the files in this stage once", "extract the fields from these 200 PDFs — just this batch, no pipeline") → **[One-off tasks](#one-off-tasks)**.
2. **A job keyword / intent matches a use-case template** → load that **[template](#the-three-jobs-use-case-templates)** and run it end-to-end.
3. **Pipeline intent — ongoing ingestion / keep the outputs fresh as new files land / "build me a…" — but no job matches** → **[Compose a custom pipeline](#compose-a-custom-pipeline)**.
4. **Genuinely ambiguous** (e.g. "I want a document pipeline" with no domain or one-off signal) → ask **one** short question, then route:

   ```
   What are you trying to build?

   1. Structured Extraction (Business Automation) — classify mixed document types, extract each by its
      own schema, reassemble per record (claim/application/case), route to action lanes
   2. Research & Analytics (Corpus Intelligence) — themes, trends, outliers & a reading list across a
      whole document collection
   3. Enterprise Search — a searchable, grounded, cited knowledge layer over your documents (search / RAG)
   4. Customer 360 — unify warehouse tables (CRM, telemetry, surveys, …) with staged customer documents;
      risk/route, search, and product-health insights in one fusion pipeline
   5. A custom pipeline — something pipeline-shaped that isn't one of the above
   6. A one-off task — extract, parse, classify, or analyze files you already have (one file or a one-time batch), no ongoing pipeline
   ```

> Don't run more than one path. A template load is end-to-end; do **not** also take the one-off path.

---

## One-off tasks

*For a one-time task — extract, parse, classify, or visually analyze a single file **or** a one-time batch over files already on a stage — that is **not** a persistent pipeline.* Route to the matching single-function reference and let it carry the detailed workflow (field definitions, batch processing over the stage, `scale_factor` tuning, confidence scores, post-processing).

**Visual documents** (blueprints, drawings, technical/engineering drawings, complex diagrams, schematics, charts, graphs): to interpret or extract their content, route to Visual Analysis (`AI_COMPLETE` with a vision model) rather than `AI_EXTRACT`, even when the user names specific fields — interpreting charts, diagrams, and schematics needs a vision model, not field extraction. The one exception is categorizing or triaging documents by type (not reading their content), which routes to Classification (`AI_CLASSIFY`) regardless of whether they're visual — see [`references/document_classification.md`](references/document_classification.md) for its format envelope (JPG/PNG/WEBP/GIF classified directly; PDF/DOCX/PPTX/HTML/TXT parsed first; convert other formats such as TIFF/BMP to PNG or PDF first).

**Named-field requests** — specific or named fields, "structured output/data", "JSON output", or "extract [a specific thing]" (e.g. `invoice_number`, date, amount, total, line_items) — route to `AI_EXTRACT`, not `AI_PARSE_DOCUMENT`.

| User wants | Flow | Load |
|------------|------|------|
| Specific/named fields, values, JSON, tables, line items ("extract X") | Structured extraction (`AI_EXTRACT`) | [`references/extraction.md`](references/extraction.md) |
| Full text, all content, OCR, read/get text from scans | Parsing (`AI_PARSE_DOCUMENT`) | [`references/parsing.md`](references/parsing.md) |
| Charts, graphs, diagrams, blueprints, schematics, drawings | Visual analysis (`AI_COMPLETE`) | [`references/visual-analysis.md`](references/visual-analysis.md) |
| Sort, categorize, triage documents by type | Classification (`AI_CLASSIFY`) | [`references/document_classification.md`](references/document_classification.md) |

**File location:** ask for the Snowflake stage path (e.g. `@MY_DB.MY_SCHEMA.MY_STAGE`). For a local file, ask which database/schema/stage to use — do not create stages or run SQL until the user provides it — then create the stage with server-side encryption and upload:

```sql
CREATE STAGE IF NOT EXISTS db.schema.user_provided_stage_name
  DIRECTORY = (ENABLE = TRUE)
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');
```

```
snow stage copy "<local_path>" @db.schema.user_provided_stage_name
```

For cloud storage (S3/Azure/GCS/Google Drive), load the `openflow` skill to set up a connector.

**Continuous or persistent pipeline?** If the user wants ongoing processing rather than a one-off, go back to the triage above and build it with [`references/multi-step-pipeline.md`](references/multi-step-pipeline.md) + the templates — even if a one-off reference's "Option 3 / pipeline" step points at `references/pipeline.md`. `pipeline.md` is a legacy scheduled-task model, not the path for new pipelines.

---

## Use-case templates

Templates are specializations of [`references/multi-step-pipeline.md`](references/multi-step-pipeline.md) that add a curated palette of domain blocks, sensible defaults, and worked `examples/`. **Keyword/intent match → load the template and run it end-to-end.**

| Job | What it delivers | Trigger keywords | Load |
|-----|------------------|------------------|------|
| **Structured Extraction (Business Automation)** | Classify mixed document types, extract each by its own schema, reassemble per record (claim/application/case), route to operational action lanes or analytical rollups | mixed document types, classify then extract, document routing/triage by type, claims/loan/KYC packet intake, per-claim/per-case assembly, route to action lanes, multi-type extraction pipeline | [`templates/structured-extraction/SKILL.md`](templates/structured-extraction/SKILL.md) |
| **Research & Analytics (Corpus Intelligence)** | Themes, trends, outliers, clustering & a reading list across a whole document collection | corpus intelligence, analyze a document corpus, themes across documents, thematic analysis, cluster by theme, find outlier documents, literature review pipeline, summarize a collection of papers/reports/filings | [`templates/corpus-intelligence/SKILL.md`](templates/corpus-intelligence/SKILL.md) |
| **Enterprise Search** | A searchable knowledge layer over the library with grounded, cited, chart-aware answers (search / RAG) | enterprise search, knowledge base over documents, RAG over documents, grounded cited answers, document Q&A, Cortex Search pipeline, make our documents searchable, chart-aware search | [`templates/enterprise-search/SKILL.md`](templates/enterprise-search/SKILL.md) |
| **Customer 360** | Unify pre-loaded warehouse tables with staged documents → AI doc signals → per-customer 360 record, optional risk/route, search/RAG, and product-health landscape | customer 360, CSM, join documents with warehouse tables, unify structured and unstructured, customer risk scoring, product health monitoring, campaign impact, executive customer insights | [`templates/customer360/SKILL.md`](templates/customer360/SKILL.md) |

**Within Structured Extraction (routing precedence):**

- **Pure single-type invoices** (header + line items, no cross-document assembly) → the simpler, well-tested **[`templates/invoice-processing/SKILL.md`](templates/invoice-processing/SKILL.md)** starter.
- **Multi-type / classify-then-route / per-entity assembly** → `templates/structured-extraction/SKILL.md` (its operational/analytical heads are part of this shape).
- A **single-type, non-invoice** ask that only needs a spine + one borrowed head (e.g. "parse these contracts, extract clauses, flag the risky ones for review") is **not** template-shaped → use **[Compose a custom pipeline](#compose-a-custom-pipeline)** and borrow the head block, unless the user explicitly wants the full structured-extraction scaffold.

---

## Templates ↔ custom: one spectrum

Template as-is → load and run. Template + customize → add/drop/replace blocks (swap the extractor schema, add a rollup). Fully custom → compose from base + blocks when no template fits. Prefer a proven template — they are eval-backed defaults and starting points, not fixed pipelines.

---

## Compose a custom pipeline

When no template fits, build from the base + blocks. **Lane-archetype → where the blocks live:**

| Lane archetype | What it does | Borrow blocks from |
|----------------|--------------|--------------------|
| **Record spine** | parse → extract → enrich, one row per doc/page | [`blocks/ingest/ingestion.md`](blocks/ingest/ingestion.md) + [`blocks/ingest/parse-text.md`](blocks/ingest/parse-text.md) or [`blocks/ingest/parse-pages.md`](blocks/ingest/parse-pages.md) + [`blocks/extract/fields.md`](blocks/extract/fields.md) |
| **Vision field** | structured fields from an image/chart via `AI_COMPLETE` | [`blocks/extract/vision-structured.md`](blocks/extract/vision-structured.md) for typed image fields; [`blocks/extract/vision-figures.md`](blocks/extract/vision-figures.md) for page/chart narratives |
| **Parallel branch** | a side table off the spine (e.g. line items via `LATERAL FLATTEN` over a materialized array) | [`blocks/extract/fields.md`](blocks/extract/fields.md) (line-item / table extraction) |
| **Classify-route fan-out** | one `AI_CLASSIFY` DT → N per-type extractors | [`blocks/extract/classify.md`](blocks/extract/classify.md) (multi-class router) + [`blocks/extract/fields.md`](blocks/extract/fields.md) / [`blocks/extract/vision-structured.md`](blocks/extract/vision-structured.md) (routed extractors) |
| **Fan-in assembly** | join per-type DTs into one record per business key | [`blocks/records/entity.md`](blocks/records/entity.md) |
| **Operational decision / triage** | per-entity decision/score → action or review queue (e.g. flag risky contracts) | [`blocks/records/reason.md`](blocks/records/reason.md) + [`blocks/records/triage.md`](blocks/records/triage.md) |
| **Retrieval sink** | chunk → Cortex Search service → cited RAG | [`blocks/search/chunk-index.md`](blocks/search/chunk-index.md) + [`blocks/search/rag-answer.md`](blocks/search/rag-answer.md) |
| **Cross-document rollup / synthesis** | `GROUP BY` metrics / `LISTAGG` → `AI_COMPLETE` briefing | [`blocks/analyze/metrics-trend.md`](blocks/analyze/metrics-trend.md) + [`blocks/analyze/synthesize.md`](blocks/analyze/synthesize.md); corpus themes in [`blocks/analyze/themes-clusters.md`](blocks/analyze/themes-clusters.md) |

**Build contract:**

1. **Read the base** [`references/multi-step-pipeline.md`](references/multi-step-pipeline.md) first (mechanics + the generic spine + naming/refresh conventions).
2. **Borrow the closest block** from the index above, adapt its placeholders; write a new block only when the palette lacks one, following the base's incremental-safety rules.
3. **Per-entity action/review** flows compose `records/reason.md` + `records/triage.md`; **per-corpus/per-segment analytics** compose `analyze/metrics-trend.md` + `analyze/synthesize.md`. Mind grain shifts (doc→entity at assembly; entity→aggregate at rollups).
4. **Build every lane the request named — a fused pipeline needs all its heads.** When a request combines shapes (e.g. per-record extraction/triage **and** a searchable knowledge layer over the same documents), each named capability is its own lane and each must be built and populated. The retrieval sink (`blocks/search/chunk-index.md` → the Cortex Search service + `blocks/search/rag-answer.md`) is a required head whenever the request asks to search / ask questions over the documents — building the extraction spine perfectly and omitting the search service leaves that capability delivering nothing. Before the build gate, list every lane the request described and confirm the composition includes each (the base's Definition of done re-checks this on the terminal object of every lane).
5. **Build behind one approval gate.**
6. **Verify refresh modes:** the per-document / per-entity AI `DT_<prefix>_*` must be `INCREMENTAL` (base Step 6). Only **documented aggregate-grain rollups** may be `FULL` (`analyze/metrics-trend.md`, `analyze/synthesize.md`, and corpus rollups in `analyze/themes-clusters.md`) — do **not** blanket-require `INCREMENTAL` for every DT, and do not treat enterprise-search (all-`INCREMENTAL`) as an exception.
7. **Gate cost:** keep the task suspended until refresh modes are verified.

---

## Shared mechanics and constraints

**Reference table:**

| Reference | Location | Use for |
|-----------|----------|---------|
| Pipeline base | [`references/multi-step-pipeline.md`](references/multi-step-pipeline.md) | The incremental pipeline engine; templates + custom composition build on it |
| Extraction | [`references/extraction.md`](references/extraction.md) | Structured field/table extraction (`AI_EXTRACT`) + confidence scores, `scale_factor` |
| Parsing | [`references/parsing.md`](references/parsing.md) | Full-text parsing (`AI_PARSE_DOCUMENT`) |
| Visual analysis | [`references/visual-analysis.md`](references/visual-analysis.md) | Charts, blueprints, diagrams (`AI_COMPLETE`) |
| Classification | [`references/document_classification.md`](references/document_classification.md) | Categorize/sort/triage documents (`AI_CLASSIFY`) |

For authoritative low-level function syntax, the references above point to the syntax tier in `references/functions/ai-extract.md`, `references/functions/ai-parse-doc.md`, `references/functions/ai-complete.md`, `references/functions/ai-classify.md`. **Read the reference before writing SQL — never from memory.**

**Compile-validation gate (mandatory):** run every generated statement through `snowflake_sql_execute` with `only_compile: true`; fix the root cause of any failure and re-validate before returning or executing. Common gotchas: `VECTOR` unsupported in SQL scripting blocks (use a plain `SELECT`); scripting variables need explicit type declarations (`LET count INTEGER := 0;`); `AI_PARSE_DOCUMENT` requires `TO_FILE('@stage', RELATIVE_PATH)` — not a raw string; AI functions never take the `SNOWFLAKE.CORTEX` prefix.

**File-type support:**

| Extension | AI_EXTRACT | AI_PARSE_DOCUMENT | AI_COMPLETE |
|-----------|------------|-------------------|-------------|
| .pdf | Yes | Yes | Yes (native — no image conversion) |
| .png, .jpg, .jpeg, .gif, .tiff, .webp | Yes | Yes | Yes² |
| .bmp | Yes | No | Yes² |
| .docx, .pptx | Yes | Yes | docx: Claude models¹; pptx: No |
| .html, .txt | Yes | Yes | txt: Yes; html: No |
| .md | Yes | No | Yes |
| .eml | Yes | No | No |
| .csv | No | No | Claude models¹ |
| .doc | Yes | No | Claude models¹ |
| .ppt | Yes | No | No |
| .xls, .xlsx | No | No | Claude models¹ |

¹ AI_COMPLETE document-format support is model-dependent: `.pdf`, `.txt`, and `.md` work on all models, while Claude models additionally accept `.doc`, `.docx`, `.xls`, `.xlsx`, `.csv`, `.xhtml`. PDFs are processed natively (convert to images only for per-page image outputs or image-only models). Authoritative matrix: [`references/visual-analysis.md`](references/visual-analysis.md).
² AI_COMPLETE's supported image set: PNG, JPEG, TIFF, BMP, GIF, WEBP (authoritative matrix: [`references/visual-analysis.md`](references/visual-analysis.md)).

Unsupported formats: suggest exporting to PDF or loading directly into Snowflake. Infer file type from extension — don't ask the user.

**Limits:** each AI function's file-size and page-count limits live in its reference (linked in the Reference table above), which carries the authoritative numbers or links to the Snowflake function docs. Read the reference before running so you can flag a file that exceeds a limit.

**Stopping points:**

| Situation | Wait for |
|-----------|----------|
| One-off tasks | Task goal (extract / parse / classify / analyze) + file/stage location |
| Building a pipeline (template or custom) | **One** approval before creating objects / running AI |
| Any AI execution | Current-rate cost warning shown first (see [Pricing](#pricing)) |

**Follow-up requests:** when the user asks for something different, re-evaluate the route — don't assume the previous flow still applies (e.g. "extract" + a specific field → `AI_EXTRACT`; "get all the text" → `AI_PARSE_DOCUMENT`).
