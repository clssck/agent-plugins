# Document Intelligence

Snowflake Cortex AI Functions for document and file analytics — extract, parse, classify, and visually analyze files, PDFs, images, and stage documents, for a single file or a one-time batch. Also fine-tunes arctic-extract for domain-specific extraction.

## Taxonomy

`document-intelligence` is a problem-to-solution router for one-off document/file AI tasks (intent detection → the right Cortex AI function) plus the arctic-extract fine-tuning workflow. It carries its own curated function references.

For **pipelines** — chaining several AI functions into one flow, ongoing ingestion that keeps outputs fresh as new files land (stream → task → incremental dynamic tables), or the use-case templates (enterprise search, corpus intelligence, structured extraction, customer 360) — see the standalone top-level [`ai-functions-pipeline-builder`](../ai-functions-pipeline-builder/) skill. `document-intelligence` forwards pipeline requests there.

```
document-intelligence/
├── SKILL.md                          # Router: one-off doc tasks + fine-tuning; forwards pipelines
├── README.md                         # For humans.. ;)
├── references/                       # Cortex AI Function docs & tips (document functions)
│   ├── ai-classify.md
│   ├── ai-complete.md
│   ├── ai-extract.md
│   └── ai-parse-doc.md
└── fine-tuning/                      # Fine-tuning arctic-extract workflows
    ├── SKILL.md                      # Fine-tuning routing skill
    ├── README.md
    └── references/
        ├── overview.md
        ├── training-data.md
        ├── job-management.md
        └── inference.md
```

## One-off document tasks

| User wants | Function | Reference |
|------------|----------|-----------|
| Structured/named fields, JSON, tables, line items | **AI_EXTRACT** | `references/ai-extract.md` |
| Full text / OCR from a document | **AI_PARSE_DOCUMENT** | `references/ai-parse-doc.md` |
| Interpret a chart, diagram, blueprint, or drawing | **AI_COMPLETE** (vision) | `references/ai-complete.md` |
| Classify / categorize / triage documents by type | **AI_CLASSIFY** | `references/ai-classify.md` |
| Train a custom arctic-extract model | Fine-Tuning | `fine-tuning/SKILL.md` |

## Boundaries

- **Pipelines** — chaining multiple AI functions, keep-fresh ingestion, use-case templates, or custom block composition → [`ai-functions-pipeline-builder`](../ai-functions-pipeline-builder/).
- **AI functions over already-tabular text/image columns** (no file/stage/document — classify, filter, extract, summarize, translate a column, sentiment) → `../cortex-ai-function-studio/`.
