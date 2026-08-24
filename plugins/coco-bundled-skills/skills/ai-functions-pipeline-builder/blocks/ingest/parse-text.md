# Parse — files → document text (`DOC_TEXT`)

Turn each file into a clean text column the rest of the pipeline reasons over. Parse's only job is to
produce `PARSED_TEXT`; once it exists, every downstream block is modality-agnostic. This file covers the
**text-string** flavor (the common currency) plus the per-modality parsers and translation. For the
page-citation flavor (one row per page, for cited RAG) see [`parse-pages.md`](parse-pages.md).

> Read [`../conventions.md`](../conventions.md) first — shapes, refresh contract, placeholders.

---

## Parse / OCR — `AI_PARSE_DOCUMENT`

- **When** — always, unless you extract structured fields directly from the file with no text step.
- **Reads** — `FILE` (`<prefix>_FILE_LOG`).
- **Produces** — `DOC_TEXT`: `DT_<prefix>_PARSED` (`PARSED_TEXT`). Derive `<entity_key>` here if records span
  multiple files (it's just SQL off `RELATIVE_PATH` — see note below).
- **Refresh** — **INCREMENTAL** (parse fires on new files only).
- **Typical upstreams** — `ingest/ingestion.md`.

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_PARSED
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL  INITIALIZE = ON_SCHEDULE
AS
SELECT
  fl.RELATIVE_PATH, fl.FILE_NAME, fl.LAST_MODIFIED, fl.INGESTED_AT,
  -- SPLIT_PART(SPLIT_PART(fl.RELATIVE_PATH,'/',-1),'__',1) AS <entity_key>,  -- only if records span files
  AI_PARSE_DOCUMENT(TO_FILE('@<db>.<schema>.<stage>', fl.RELATIVE_PATH), {'mode':'<parse_mode>'}):content::STRING AS PARSED_TEXT
FROM <db>.<schema>.<prefix>_FILE_LOG fl
-- WHERE fl.RELATIVE_PATH ILIKE '%.pdf'   -- text formats only, when images are routed by modality instead
;
```

> **`INITIALIZE = ON_SCHEDULE` defers the first refresh** — the DT is created empty until its first scheduled refresh, causing every downstream DT to read NULL text. Force an initial refresh and poll `last_completed_refresh_state` to `SUCCEEDED` (base *Definition of done*, item 2 / Step 8a), or remove `INITIALIZE = ON_SCHEDULE` on this head DT so it back-fills on creation. This is the most common cause of an empty deliverable on a fresh build.

**Mode is a cost decision** — gather it from the document shape, don't blind-default:
- `OCR` — plain running text, ~6.6× cheaper. Fine for prose-heavy corpora (articles, papers, notes, scans).
- `LAYOUT` — preserves tables, columns, headings, reading order. Use when **structure carries meaning**
  (invoices, forms, multi-column reports, anything where a table must stay aligned in a chunk).

If unsure, start `OCR`, eyeball a sample, upgrade to `LAYOUT` only if structure was lost. Pricing: base § Pricing.

> **Mixed text + image stage** — parse only the text formats (`WHERE … ILIKE '%.pdf'` etc.) and let images be
> typed by modality in `extract/classify.md` rather than parsed. Keeps one row per file across both.

---

## Other modalities — same block, swap the parser

Drop one of these expressions in place of `AI_PARSE_DOCUMENT` (use a `CASE` on the extension for a mixed
stage). Each still produces `PARSED_TEXT`, so the downstream chain is unchanged. All compile-validated.

- **Images** → a vision `AI_COMPLETE` description:
  ```sql
  AI_COMPLETE('<vision_model>',
    'Describe this image in detail — subjects, scene, style, any visible text — for indexing.',
    TO_FILE('@<db>.<schema>.<stage>', fl.RELATIVE_PATH)) AS PARSED_TEXT
  ```
  Vision models: `claude-sonnet-4-x`, `gemini-3.1-pro`, `llama4-*`, `openai-gpt-*`, `pixtral-large`. Formats
  jpg/png/gif/webp; ≤10 MB (3.75 MB for claude); SSE stage required. (`AI_CLASSIFY` is the alternative when you
  only need a label, not a description.)

- **Audio** → `AI_TRANSCRIBE` (returns an **OBJECT** — read `:text`, no `PARSE_JSON`):
  ```sql
  AI_TRANSCRIBE(TO_FILE('@<db>.<schema>.<stage>', fl.RELATIVE_PATH)):text::STRING AS PARSED_TEXT
  ```
  Add `{'timestamp_granularity':'speaker'}` for diarized turns. Formats FLAC/MP3/MP4/OGG/WAV/WEBM; ≤700 MB; ≤120 min.

- **Video** → two paths: *spoken content* (GA) uses `AI_TRANSCRIBE` on the video file (MP4/MKV/WEBM/OGV — the
  audio track); *visual content* (public preview) passes the video FILE to a multimodal `AI_COMPLETE` to summarize
  scenes, on-screen text, and action. For visual scene *search* over video, `AI_MULTI_EMBED`
  (`twelvelabs-marengo-embed-3-0`) is a separate path — wire it into `search/chunk-index.md`, not here.

> When you change modality, retarget the **extract** schema and **summary** to the content (image →
> subject/style/objects; audio/video → speakers/topics/segments). The rest of the chain is unchanged.

---

## Translate — `AI_TRANSLATE` (optional)

- **When** — the corpus mixes languages and you want a single language for everything downstream.
- **Reads** — a `DOC_TEXT` row (`PARSED_TEXT`; or a gated/classified one).
- **Produces** — `DOC_TEXT`: `DT_<prefix>_TRANSLATED` (adds `PARSED_TEXT_EN`, same shape).
- **Refresh** — **INCREMENTAL**.
- **Typical upstreams** — Parse, or `extract/classify.md` (gate first, then translate only the kept type).

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_TRANSLATED
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL  INITIALIZE = ON_SCHEDULE
AS
SELECT p.*, AI_TRANSLATE(p.PARSED_TEXT, '', 'en') AS PARSED_TEXT_EN   -- '' source = auto-detect
FROM <db>.<schema>.DT_<prefix>_PARSED p;
```

> **Wiring hazard** — when Translate is present, every downstream block that reads document text must read
> `PARSED_TEXT_EN` from this DT instead of `PARSED_TEXT` from the parse layer. (For page-grain pipelines,
> translate `CONTENT` the same way — see [`parse-pages.md`](parse-pages.md).)
