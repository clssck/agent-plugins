# Example — Mixed document library, text search (worked composition)

**Scenario:** A library of policy documents and operating manuals (mostly PDFs, some `.docx`/`.html`) lands
on a stage. You want people to **ask questions and get answers grounded in the documents, with citations to
source and page** — and the index to stay fresh as new documents land. No charts to read; this is the
text-only backbone.

This is the **reference composition** — when in doubt start here, then add the chart-vision lane
([`charts.md`](charts.md)) or optional blocks for the case at hand. It shows how blocks wire together; the
SQL bodies live in the shared palette, indexed by [`../../../blocks/README.md`](../../../blocks/README.md),
so this file stays a recipe and can't drift from it.

**Worked names:** `db=ACME`, `schema=KB`, `<prefix>=ESR`, doc stage `DOCS`, `warehouse=KB_WH`,
`<final_lag>='1 hour'`. Swap in the user's own.

## Blocks, in build order

| # | Block (in the palette) | Object(s) it creates | Grain / refresh | Composition note |
|---|------------------------|----------------------|-----------------|------------------|
| 1 | Ingestion | stage, `ESR_FILE_LOG`, `ESR_STAGE_STREAM`, `ESR_INGEST_TASK` | — | filter `.pdf/.docx/.html/.txt`; seed the backlog (base Step 4) |
| 2 | Parse | `DT_ESR_PARSED` | per-doc · `INCREMENTAL` | `LAYOUT`, format-aware `page_split` (`.pdf/.docx` paginate; `.html/.txt` parse without it — `UNION ALL`) |
| 3 | Page-flatten | `DT_ESR_PAGES` | per-page · `INCREMENTAL` | paginated branch + the non-paginating `PAGE = NULL` branch (library is mixed-format) |
| 4 | Chunk | `DT_ESR_CHUNK_ARR` → `DT_ESR_CHUNKS` | per-chunk · `INCREMENTAL` | `markdown` 1500/200; `TITLE` from the filename; `CHUNK_NO` carried; `DT_ESR_CHUNKS` is terminal → takes `<final_lag>` |
| 5 | Cortex Search | `ESR_SEARCH` | service | `ON CHUNK`, `ATTRIBUTES RELATIVE_PATH, PAGE, CHUNK_NO, TITLE` |
| 6 | Retrieve + answer | (query pattern) | n/a | `SEARCH_PREVIEW → AI_COMPLETE` with `(Title, p.N)` / `(Title, #chunk)` citations |

(Optional, not in this basic build: **Metadata facets** for filtering, **Translate** for multilingual,
**Chart/figure vision** — see [`charts.md`](charts.md).)

**DAG:**

```
@DOCS → ESR_STAGE_STREAM + ESR_INGEST_TASK → ESR_FILE_LOG
  → DT_ESR_PARSED → DT_ESR_PAGES → DT_ESR_CHUNK_ARR → DT_ESR_CHUNKS     [per-doc/-page/-chunk · INCREMENTAL]
  → ESR_SEARCH  (Cortex Search service, self-refreshing)
  → RAG query pattern (SEARCH_PREVIEW → AI_COMPLETE + citations)
```

## How the blocks wire

- **One grain, one rule.** Every `DT_ESR_*` is `INCREMENTAL` — a new file triggers AI (here, just
  `AI_PARSE_DOCUMENT`) on that file only. There are no `FULL` rollups. The search service is not a DT; it
  self-refreshes on its own lag.
- **Terminal lag sits on the chunk DT.** `DT_ESR_CHUNKS` is the last DT before the (non-DT) service, so it
  takes `<final_lag>`; every upstream DT is `TARGET_LAG = DOWNSTREAM`. Total freshness = ingest task +
  per-doc DT lag + chunk DT lag + service lag.
- **Citation key rides the chunk.** Each chunk carries `RELATIVE_PATH`, `PAGE` (1-based for paginated docs,
  `NULL` for non-paginating ones), `CHUNK_NO` (position within the doc — the citation key when `PAGE` is
  `NULL`), and a display `TITLE` (derived from the filename here — add the Metadata block for a real
  title/facets). The service exposes those as `ATTRIBUTES`, so a RAG answer cites `(Title, p.N)` for paginated
  docs and `(Title, #chunk)` for the rest.
- **`SPLIT_TEXT_RECURSIVE_CHARACTER` is not an `AI_*` function** — it keeps the `SNOWFLAKE.CORTEX.` prefix.
  Everything else (`AI_PARSE_DOCUMENT`, `AI_COMPLETE`) is unprefixed.

## Build & verify

Create blocks #1–#5, then **seed the backlog** (`DIRECTORY()` → `ESR_FILE_LOG`, base Step 4) and backfill the
chain by refreshing the terminal DT (`DT_ESR_CHUNKS`; refreshing it pulls parse → pages → chunks). Build
`ESR_SEARCH` and let it refresh. **Resume `ESR_INGEST_TASK` last** (after every object exists).

Then verify refresh modes (base Step 6): every `DT_ESR_*` reports `INCREMENTAL` — stop and fix any `FULL`.
Smoke-check:

```sql
-- chunk coverage
SELECT COUNT(*) AS chunks, COUNT(DISTINCT RELATIVE_PATH) AS docs FROM ACME.KB.DT_ESR_CHUNKS;

-- retrieval works (no LLM)
SELECT v.value:TITLE::STRING AS TITLE,
       COALESCE('p.' || v.value:PAGE::STRING, '#' || v.value:CHUNK_NO::STRING) AS LOC,
       LEFT(v.value:CHUNK::STRING, 200) AS PREVIEW
FROM TABLE(FLATTEN(input => PARSE_JSON(SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
  'ACME.KB.ESR_SEARCH', '{"query":"<a representative question>","columns":["CHUNK","TITLE","PAGE","CHUNK_NO"],"limit":5}'
))['results'])) v;
```

Then run a full RAG answer (the pattern in [`../../../blocks/search/rag-answer.md`](../../../blocks/search/rag-answer.md)) and
confirm it cites `(Title, p.N)` (or `(Title, #chunk)` for non-paginated docs) and refuses when context is thin.

For freshness, set the user's target lag (default `1 hour`) on `DT_ESR_CHUNKS` and the `ESR_SEARCH` service;
leave every upstream DT `TARGET_LAG = DOWNSTREAM` (base Step 7).

## What the search layer buys you

One governed service answers grounded questions over the whole library without anyone reading it:

```sql
-- e.g. "What is our remote-work policy for contractors?" → cited answer
CALL ACME.KB.ask_ESR('What is our remote-work policy for contractors?');   -- if the wrapper was built
```

Every answer is grounded in the org's own content and cites its source and page; the same `ESR_SEARCH`
service also backs Cortex Agents and external RAG apps, and stays fresh as new documents land — a new file
updates only its own rows.

## Teardown

Dependency-safe order for exactly the objects above. **These `DROP`s are irreversible — present them and get
explicit user approval before running any** (full rule + gate in [`../SKILL.md`](../SKILL.md) § Teardown):

```sql
ALTER TASK ACME.KB.ESR_INGEST_TASK SUSPEND;                 -- stop ingestion first

DROP PROCEDURE IF EXISTS ACME.KB.ask_ESR(STRING);          -- optional answer wrapper, if built

DROP CORTEX SEARCH SERVICE IF EXISTS ACME.KB.ESR_SEARCH;    -- the service (reads the chunk DT)

DROP DYNAMIC TABLE IF EXISTS ACME.KB.DT_ESR_CHUNKS;         -- DTs newest → oldest
DROP DYNAMIC TABLE IF EXISTS ACME.KB.DT_ESR_CHUNK_ARR;
DROP DYNAMIC TABLE IF EXISTS ACME.KB.DT_ESR_PAGES;
DROP DYNAMIC TABLE IF EXISTS ACME.KB.DT_ESR_PARSED;

DROP TASK   IF EXISTS ACME.KB.ESR_INGEST_TASK;              -- task, then stream, then file log
DROP STREAM IF EXISTS ACME.KB.ESR_STAGE_STREAM;
DROP TABLE  IF EXISTS ACME.KB.ESR_FILE_LOG;

-- Leave @DOCS in place — that's the user's documents.
```

(Conventions — `INCREMENTAL`-safety, target-lag policy, monitoring — are base-owned: see
[`../../../references/multi-step-pipeline.md`](../../../references/multi-step-pipeline.md).)
