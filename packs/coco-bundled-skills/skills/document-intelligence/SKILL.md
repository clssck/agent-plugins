---
name: document-intelligence
description: "Document intelligence over files, PDFs, images, and stage documents with Snowflake Cortex AI functions — extract fields, parse/OCR text, classify by type, and visually analyze charts/diagrams, for a single file or a one-time batch. Also fine-tunes arctic-extract for domain-specific extraction. Use when: extracting structured fields from PDFs/forms/invoices, parsing or OCR-ing a document, classifying/triaging documents by type, analyzing a chart/blueprint/engineering drawing, or any one-off AI task over files already on a stage. Triggers: extract from PDF, extract fields, extract data from files, structured extraction, parse document, read document, get text from PDF, extract text from image, OCR, scan, digitize, classify documents, categorize files, sort documents, triage files, document type, invoice, contract, receipt, form, blueprint, drawing, engineering drawing, technical drawing, diagram, schematic, chart, graph, plot, my files, my documents, files on stage, AI_EXTRACT, AI_PARSE_DOCUMENT, AI_CLASSIFY, AI_COMPLETE vision, fine-tune, fine-tuning, custom model, train arctic-extract, improve extraction accuracy, FINETUNE. To build a document pipeline — chaining multiple AI functions into one flow, or keeping outputs fresh as new files land (stream → task → dynamic tables) — use the ai-functions-pipeline-builder skill instead."
---

# Document Intelligence

Extract, parse, classify, and visually analyze documents and files on Snowflake stages with Cortex AI functions — for a single file or a one-time batch — and fine-tune arctic-extract for domain-specific extraction. To **build a pipeline** — chain several AI functions into one flow, or keep outputs fresh as new files land — hand off to the `ai-functions-pipeline-builder` skill.

## 🚨 INVOKE THIS SKILL FIRST - DO NOT WRITE SQL WITHOUT IT

## ⚠️ CRITICAL: Always use AI_* function names WITHOUT the `SNOWFLAKE.CORTEX` namespace prefix

## ⚠️ CRITICAL: Display pricing before executing any AI function

Before running any `AI_EXTRACT`, `AI_PARSE_DOCUMENT`, `AI_CLASSIFY`, or `AI_COMPLETE` call, warn the user to confirm current rates at the authoritative Snowflake docs. Never skip this.

## Workflow

### Step 1: Detect intent — one-time task, pipeline, fine-tuning, or tabular?

Decide the path from the request. **What matters is the shape of the work, not the number of files** — a one-time job over a large batch still belongs here.

- **Pipeline** → **hand off**: load `../ai-functions-pipeline-builder/SKILL.md`. Route here to **compose several AI functions into one flow** (e.g. parse → extract → classify → serve), build a **use-case pipeline** (enterprise search, corpus intelligence, structured extraction, customer 360), or set up **ongoing ingestion** that keeps outputs fresh as new files land (stream → task → dynamic tables) — anything shaped like "build me a pipeline".
- **One-time task** → route it in **Step 2** below: a single AI function applied once to a file **or** to a one-time batch already on a stage, with no ongoing refresh and no multi-function pipeline to assemble.
- **Fine-tuning** → load `fine-tuning/SKILL.md`: train or improve arctic-extract on your own labeled data.
- **AI functions over already-tabular text/image columns** (no file, stage, or document — e.g. classify a text column, filter/summarize/translate rows, sentiment) → defer to `../cortex-ai-function-studio/SKILL.md`.

### Step 2: Route the one-off to the right function

**Never write AI-function SQL from memory — read the matching reference first.**

| User wants | Function | Reference |
|------------|----------|-----------|
| Specific/named fields, values, JSON, tables, line items ("extract X") | `AI_EXTRACT` | `references/ai-extract.md` |
| Full text, all content, OCR, "read/get text from" scans | `AI_PARSE_DOCUMENT` | `references/ai-parse-doc.md` |
| Interpret a chart, graph, diagram, blueprint, schematic, or drawing | `AI_COMPLETE` (vision) | `references/ai-complete.md` |
| Sort, categorize, or triage documents by type | `AI_CLASSIFY` | `references/ai-classify.md` |

**Visual routing:** blueprints, drawings, engineering/technical drawings, complex diagrams, schematics, charts, and graphs route to **`AI_COMPLETE` with a vision model, not `AI_EXTRACT`** — even when the user names specific fields (e.g. "extract the dimensions from this drawing"). Interpreting visual content needs a vision model, not field extraction. The one exception is categorizing/triaging by type (not reading content), which is `AI_CLASSIFY`.

**Classification format envelope:** images (JPG/PNG/WEBP/GIF) classify directly with `AI_CLASSIFY(TO_FILE(...))`; PDF/DOCX/PPTX/HTML/TXT → run `AI_PARSE_DOCUMENT` first, then classify the extracted text; convert other formats (TIFF/BMP) to PNG or PDF first.

**File location:** ask for the Snowflake stage path (e.g. `@MY_DB.MY_SCHEMA.MY_STAGE`). For a local file, ask which database/schema/stage to use — do not create stages or run SQL until the user provides it.

**If the intent is unclear**, ask: [WAIT]
```
What would you like to do with your files?

1. Extract specific fields (AI_EXTRACT) — invoice numbers, dates, amounts, line items → JSON
2. Parse / OCR full text (AI_PARSE_DOCUMENT) — get all the text out of a PDF or scan
3. Classify by type (AI_CLASSIFY) — sort or triage documents into categories
4. Analyze a chart, diagram, or drawing (AI_COMPLETE vision)
5. Fine-tune arctic-extract — improve extraction accuracy with your own labeled data

To build a pipeline — chain several AI functions into one flow, or keep processing new files
as they land (stream → task → dynamic tables) — tell me, and I'll switch to the
ai-functions-pipeline-builder skill.

For other AI functions over already-tabular text or image columns (classify, filter, extract,
summarize, translate, etc.), use the cortex-ai-function-studio skill instead.
```

## Step 3: Validate Generated SQL

**MANDATORY: After generating any SQL, validate it before returning it to the user.**

1. Run `snowflake_sql_execute` with `only_compile: true` on every generated SQL statement.
2. If compilation **succeeds** → return the SQL to the user.
3. If compilation **fails**:
   - Read the full error message carefully.
   - Fix the root cause (do NOT just rewrite the query differently).
   - Re-validate after fixing — do not return SQL that has not passed compilation.
   - Common gotchas to check before re-validating:
     - `VECTOR` type is **not supported inside SQL scripting blocks** — use plain `SELECT` instead.
     - Variables in SQL scripting blocks require **explicit type declarations** (e.g., `LET count INTEGER := 0;`), not type inference from the initializer.
     - `AI_PARSE_DOCUMENT` requires `TO_FILE('@stage', 'file.pdf')` wrapper — never pass a raw string path.

## Stopping Points

- ✋ Step 2: After presenting the menu (if intent is unclear) - wait for user selection

## Output

Runs the one-off AI-function task, or routes to fine-tuning / the `ai-functions-pipeline-builder` skill / `cortex-ai-function-studio` based on detected intent.

## Notes

- All functions run in Snowflake (data never leaves)
- Functions work in SELECT, WHERE, JOIN clauses
- Use batch processing for best throughput
- For interactive/low-latency: consider REST API instead
- **Follow-up handling:** If you have already answered the user's question in a prior turn, do NOT repeat the same response verbatim. Instead, briefly confirm what you already said and ask what additional detail or clarification they need.
- **Explicit go-ahead:** When the user gives a clear directive ("go ahead", "implement all files", "change everything that needs changing"), act on it immediately. Do NOT re-ask for confirmation or defer the decision back to the user. Only ask clarifying questions when the request is genuinely ambiguous, not when the user has already approved the action.
- **Recovery from failure:** When an approach fails or the user signals dissatisfaction ("try again", "that didn't work", "this is wrong"):
  1. Do NOT repeat the same output or retry the identical approach.
  2. Diagnose what specifically failed — read the error, identify the root cause.
  3. If the failure is in your output (wrong SQL, incomplete extraction), resume from the failing step, not from scratch.
  4. If the failure is an environment/infrastructure blocker (missing stage, encryption error, unsupported feature), clearly tell the user it is not a code error, stop retrying the same fix, and pivot to an alternative approach if the user suggests one.
