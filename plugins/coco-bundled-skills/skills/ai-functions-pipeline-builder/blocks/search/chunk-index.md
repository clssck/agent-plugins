# Chunk & index — the searchable knowledge layer (`SPLIT_TEXT…` + Cortex Search)

Split document text into retrieval units that each carry their source location, then index them in a Cortex
Search service that embeds + self-refreshes. The service **is** the deliverable for search/RAG — and it's
agent-ready (it backs Cortex Agents unchanged). Cortex Search does **not** chunk for you (each source row is one
search unit — that's why we chunk upstream), but it **does** embed and index internally on its own `TARGET_LAG`.

> Read [`../conventions.md`](../conventions.md) first — shapes, the doc→chunk grain shift, placeholders. Default
> `<embed_model>` to `snowflake-arctic-embed-l-v2.0`.

---

## Optional: metadata facets — filterable attributes

- **When** — users want to filter/cite on attributes beyond doc + page + title (doc type, date, department, …).
- **Reads** — `DOC_TEXT`/`DOC_PARSE` (`RELATIVE_PATH`, `FILE_NAME`, parse payload).
- **Produces** — `DT_<prefix>_DOCMETA` (one row per doc: `RELATIVE_PATH, TITLE, <facet…>`).
- **Refresh** — **INCREMENTAL**.

**Prefer-path-else-extract:** parse the facet from the path/filename in plain SQL when it's encoded there (free,
no hallucination); only when it isn't, add a small `AI_EXTRACT` over the first page. Chosen facets become Cortex
Search `ATTRIBUTES` and are denormalized onto every chunk.

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_DOCMETA
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL  INITIALIZE = ON_SCHEDULE
AS
SELECT
  p.RELATIVE_PATH,
  INITCAP(REPLACE(REGEXP_REPLACE(p.FILE_NAME, '\\.[^.]+$', ''), '_', ' ')) AS TITLE,  -- filename → display title
  SPLIT_PART(p.RELATIVE_PATH, '/', 1)             AS DOC_TYPE      -- e.g. top folder = doc type / source
FROM <db>.<schema>.DT_<prefix>_PARSED p;
-- When metadata isn't in the path: AI_EXTRACT(text => LEFT(<first-page content>, 8000),
--   responseFormat => {'title':'…','doc_type':'…','doc_date':'YYYY-MM-DD or None'}) then NULLIF(x,'None').
```
> Skip this block → the chunk step derives `TITLE` inline from the filename and the service exposes only
> `RELATIVE_PATH, PAGE, CHUNK_NO, TITLE`.

---

## Chunk — source-located retrieval units

- **When** — always, unless docs are very short.
- **Reads** — a `DOC_TEXT` or `PAGE_TEXT` row (the text column: `PARSED_TEXT` / `CONTENT` / `PARSED_TEXT_EN`),
  + `DT_<prefix>_DOCMETA` if facets were composed.
- **Produces** — `CHUNK`: `DT_<prefix>_CHUNK_ARR` (chunk array) → `DT_<prefix>_CHUNKS` (`RELATIVE_PATH, PAGE/CHUNK_NO, TITLE, <facet…>, CHUNK`).
- **Refresh** — both **INCREMENTAL**; `DT_<prefix>_CHUNKS` is **terminal** → takes the user's `<final_lag>`.
- **Typical upstreams** — `ingest/parse-pages.md` (`PAGE_TEXT`), `extract/vision-figures.md` (Enrich), or `ingest/parse-text.md` (`PARSED_TEXT`).

`SPLIT_TEXT_RECURSIVE_CHARACTER` **requires** the `SNOWFLAKE.CORTEX.` prefix (it is *not* an `AI_*` function);
signature `(text, format, chunk_size, overlap)`. `'markdown'` format keeps table rows and headings together.

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_CHUNK_ARR
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL  INITIALIZE = ON_SCHEDULE
AS
SELECT
  e.RELATIVE_PATH, e.FILE_NAME, e.DOC_KEY, e.PAGE,
  SNOWFLAKE.CORTEX.SPLIT_TEXT_RECURSIVE_CHARACTER(e.CONTENT, 'markdown', 1500, 200) AS CHUNKS
FROM <db>.<schema>.DT_<prefix>_PAGES e            -- or DT_<prefix>_ENRICHED / DT_<prefix>_TRANSLATED / DT_<prefix>_PARSED (use PARSED_TEXT)
WHERE e.CONTENT IS NOT NULL AND LENGTH(e.CONTENT) > 0;

CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_CHUNKS
  TARGET_LAG = '<final_lag>'  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL  INITIALIZE = ON_SCHEDULE
AS
SELECT
  a.RELATIVE_PATH,
  a.PAGE,                                                            -- NULL for non-paginating formats
  f.index           AS CHUNK_NO,                                     -- 0-based; the citation key when PAGE is NULL
  COALESCE(m.TITLE,
           INITCAP(REPLACE(REGEXP_REPLACE(a.FILE_NAME, '\\.[^.]+$', ''), '_', ' '))) AS TITLE,
  -- m.DOC_TYPE,                                                     -- + any facets from DT_<prefix>_DOCMETA
  f.value::STRING   AS CHUNK
FROM <db>.<schema>.DT_<prefix>_CHUNK_ARR a
LEFT JOIN <db>.<schema>.DT_<prefix>_DOCMETA m USING (RELATIVE_PATH)   -- omit this join (and m.TITLE) if no Metadata block
   , LATERAL FLATTEN(input => a.CHUNKS) f;                           -- select f.index, never f.seq
```

> **Short-doc shortcut** — if the 95th-percentile `CONTENT` length is under ~1500 chars, skip chunking: drop the
> two DTs and build one `DT_<prefix>_CHUNKS` that selects `CONTENT AS CHUNK` (+ `RELATIVE_PATH, PAGE,
> 0 AS CHUNK_NO, TITLE`) directly, and point the service `ON CHUNK` at it.
> Chunks **denormalize** per-doc metadata (every chunk carries the doc's `TITLE`/facets) because a service can
> only filter/return columns present on its source rows. `RELATIVE_PATH` is the one you can't drop.

---

## Cortex Search service — the index (the deliverable)

- **Reads** — `DT_<prefix>_CHUNKS`.
- **Produces** — `<prefix>_SEARCH` (a Cortex Search service; self-refreshes on its `TARGET_LAG`, not a DT).

```sql
CREATE OR REPLACE CORTEX SEARCH SERVICE <db>.<schema>.<prefix>_SEARCH
  ON CHUNK
  ATTRIBUTES RELATIVE_PATH, PAGE, CHUNK_NO, TITLE   -- + any facets (e.g. DOC_TYPE) you added to DT_<prefix>_CHUNKS
  WAREHOUSE = <warehouse>
  TARGET_LAG = '<final_lag>'                        -- e.g. '1 hour'
  EMBEDDING_MODEL = '<embed_model>'
AS
  SELECT CHUNK, RELATIVE_PATH, PAGE, CHUNK_NO, TITLE   -- + facets
  FROM <db>.<schema>.DT_<prefix>_CHUNKS;
```

> The service must read a column for **search** (`ON CHUNK`); any **filter/return** column must be listed in
> `ATTRIBUTES` *and* selected in the body. Total freshness for a new file = ingest task + per-doc DTs + chunk DT
> lag + service lag. Query it with `search/rag-answer.md`.

**Create the service *after* `DT_<prefix>_CHUNKS` is populated.** The service indexes whatever rows exist at creation; if created while the DT is still empty it indexes 0 rows and stays empty until re-indexed on its lag. Force and confirm the chunk chain's refresh first, then:

```sql
SELECT COUNT(*) FROM <db>.<schema>.DT_<prefix>_CHUNKS;   -- must be > 0 before CREATE … SEARCH SERVICE
DESCRIBE CORTEX SEARCH SERVICE <db>.<schema>.<prefix>_SEARCH;  -- confirm source_data_num_rows > 0 after
```

`ACTIVE` status is **not** proof of a populated index — `source_data_num_rows = 0` means every query returns nothing. Refresh the source and `CREATE OR REPLACE` the service.
