# Parse to pages — citation grain (`DOC_PARSE` → `PAGE_TEXT`)

The page-citation flavor of parsing, for search/RAG pipelines that must cite `(document, page)`. Parse with
`page_split` so the parse keeps its page structure, then flatten to one row per page. Use this **instead of**
the text-string flavor in [`parse-text.md`](parse-text.md) when answers need page-level citations; use the
plain text flavor otherwise (it's cheaper and simpler).

> Read [`../conventions.md`](../conventions.md) first — shapes, refresh contract, placeholders.

---

## Parse (page-split) — `AI_PARSE_DOCUMENT` with `page_split`

- **When** — search/RAG over multi-page documents where citations should point at a page.
- **Reads** — `FILE` (`<prefix>_FILE_LOG`).
- **Produces** — `DOC_PARSE`: `DT_<prefix>_PARSED` (`RELATIVE_PATH, FILE_NAME, DOC_KEY, INGESTED_AT, RAW_PARSE`).
- **Refresh** — **INCREMENTAL**.
- **Typical upstreams** — `ingest/ingestion.md`.

`page_split` is **only supported for PDF, DOCX, PPTX, TIFF** — it errors on `.txt`/`.html`/images
(*"Page split is not supported for .X files"*). So split the parse by format with `UNION ALL`:
page-splittable types get `page_split=TRUE` (one entry per page → page-level citations); the rest parse
without it (a single `:content` payload). `DOC_KEY` (full path minus extension, stage-unique) links a doc to
its page images if `extract/vision-figures.md` is composed.

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_PARSED
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL  INITIALIZE = ON_SCHEDULE
AS
-- Page-splittable formats: keep page structure.
SELECT
  fl.RELATIVE_PATH, fl.FILE_NAME,
  REGEXP_REPLACE(fl.RELATIVE_PATH, '\\.[^./]+$', '') AS DOC_KEY,   -- path minus extension; stage-unique
  fl.INGESTED_AT,
  AI_PARSE_DOCUMENT(TO_FILE('@<db>.<schema>.<doc_stage>', fl.RELATIVE_PATH),
                    {'mode': 'LAYOUT', 'page_split': TRUE}) AS RAW_PARSE   -- {'mode':'OCR','page_split':TRUE} for scans
FROM <db>.<schema>.<prefix>_FILE_LOG fl
WHERE fl.RELATIVE_PATH ILIKE '%.pdf'  OR fl.RELATIVE_PATH ILIKE '%.docx'
   OR fl.RELATIVE_PATH ILIKE '%.pptx' OR fl.RELATIVE_PATH ILIKE '%.tiff'
UNION ALL
-- Non-page-splittable formats (TXT/HTML/PNG/JPG…): parse WITHOUT page_split (it errors on these).
SELECT
  fl.RELATIVE_PATH, fl.FILE_NAME,
  REGEXP_REPLACE(fl.RELATIVE_PATH, '\\.[^./]+$', '') AS DOC_KEY,
  fl.INGESTED_AT,
  AI_PARSE_DOCUMENT(TO_FILE('@<db>.<schema>.<doc_stage>', fl.RELATIVE_PATH), {'mode': 'LAYOUT'}) AS RAW_PARSE
FROM <db>.<schema>.<prefix>_FILE_LOG fl
WHERE fl.RELATIVE_PATH ILIKE '%.txt' OR fl.RELATIVE_PATH ILIKE '%.html'
   OR fl.RELATIVE_PATH ILIKE '%.png' OR fl.RELATIVE_PATH ILIKE '%.jpg' OR fl.RELATIVE_PATH ILIKE '%.jpeg';
```

> **PDF-only library?** (the common case) Keep just the first branch and drop the `UNION ALL`. Otherwise match
> each `WHERE` to the extensions the ingest task admits. Base Step 6 is the backstop that the `UNION ALL` form
> stays `INCREMENTAL`.

---

## Page-flatten — the retrieval grain & citation key

- **When** — always, paired with the page-split parse above; explodes the parse into the retrieval grain.
- **Reads** — `DOC_PARSE` (`RAW_PARSE`).
- **Produces** — `PAGE_TEXT`: `DT_<prefix>_PAGES` (`RELATIVE_PATH, FILE_NAME, DOC_KEY, PAGE, CONTENT`).
- **Refresh** — **INCREMENTAL** (`LATERAL FLATTEN` over the materialized `RAW_PARSE:pages`; select `f.index`, not `f.seq`).
- **Typical upstreams** — the page-split parse above.

Adaptive grain: paginated parses flatten `:pages` to **one row per (doc, page)** (cite `(doc, page)`); parses
with no `:pages` (the non-splittable branch) emit a single row with `PAGE = NULL` (cite `(doc, chunk #)`
downstream). Every row carries `RELATIVE_PATH`.

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_PAGES
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL  INITIALIZE = ON_SCHEDULE
AS
SELECT p.RELATIVE_PATH, p.FILE_NAME, p.DOC_KEY,
       f.value:index::INT + 1   AS PAGE,        -- 1-based, aligns with page-image filenames
       f.value:content::STRING  AS CONTENT
FROM <db>.<schema>.DT_<prefix>_PARSED p, LATERAL FLATTEN(input => p.RAW_PARSE:pages) f
WHERE ARRAY_SIZE(p.RAW_PARSE:pages) > 0
UNION ALL
SELECT p.RELATIVE_PATH, p.FILE_NAME, p.DOC_KEY,
       NULL AS PAGE,
       p.RAW_PARSE:content::STRING AS CONTENT
FROM <db>.<schema>.DT_<prefix>_PARSED p
WHERE p.RAW_PARSE:pages IS NULL OR ARRAY_SIZE(p.RAW_PARSE:pages) = 0;
```

- **`f.value:index::INT + 1` is necessary.** `AI_PARSE_DOCUMENT` returns pages with a 0-based
  `index` field — the first page is `index: 0`. Without the `+1`, all stored page numbers are off by
  one (what is page 3 in the document is stored as 2). Every downstream page-based lookup — retrieval
  citation checks, vision-figures joins, direct `WHERE PAGE = <n>` queries are off by one.

> **PDF-only library?** The second branch never matches — drop it. `PAGE_TEXT` is a `DOC_TEXT` shape for any
> block that reads document text (the text column is `CONTENT`) — so `search/chunk-index.md`, Translate, and
> `extract/vision-figures.md`'s Enrich step all wire to it directly.
