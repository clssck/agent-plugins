# Ingestion — stage + file log + stream + task

The event-driven head of every pipeline: a directory stage, a file-log table, and a stream + task that
appends each new file to the log exactly once. This is the only place a stream + task is used; everything
downstream is dynamic tables reading the log.

> Read [`../conventions.md`](../conventions.md) first — shapes, refresh contract, and placeholders live there.

## ⚠️ Three laws — every persistent pipeline has all three, no exceptions

Missing any one is not a lighter variant — it is broken and stops when the backlog clears.

1. **STREAM (`CREATE STREAM … ON STAGE`)** — the stage-change detector. Without it nothing signals a new file arrival. A DT directly over `DIRECTORY()` cannot substitute (no change tracking).
2. **TASK (`CREATE TASK`)** — flushes the stream into the File Log. Without it the stream accumulates but never drains. Required even when every downstream layer is a DT.
3. **INCREMENTAL on per-document DTs** — `FULL` re-pays AI cost on every document on every trigger. Aggregate-grain rollups may be `FULL`; per-document DTs never.

If you find yourself missing any of the three — stop. Each is one `CREATE` statement away.

- **When** — always.
- **Reads** — `@<db>.<schema>.<stage>` (new files).
- **Produces** — `FILE` shape: `<prefix>_FILE_LOG` (`RELATIVE_PATH, FILE_NAME, FILE_SIZE, LAST_MODIFIED, FILE_URL, INGESTED_AT`; `CHANGE_TRACKING = TRUE`).
- **Refresh** — n/a (regular table + stream + task; the DTs that read it are what stay incremental).

Use the base ingestion mechanics verbatim — [`../../references/multi-step-pipeline.md`](../../references/multi-step-pipeline.md)
§ Step 4 owns the File-Log DDL, the stream, the ingest task, the backlog seed, and the `DIRECTORY()` path
rule. The only per-pipeline parameter is the **extension filter** in the ingest task's `WHERE` — set it to
the modalities you ingest:

```sql
  AND (RELATIVE_PATH ILIKE '%.pdf'  OR RELATIVE_PATH ILIKE '%.png'   -- ILIKE = case-insensitive (.PDF matches too)
    OR RELATIVE_PATH ILIKE '%.jpg'  OR RELATIVE_PATH ILIKE '%.jpeg'
    OR RELATIVE_PATH ILIKE '%.tiff' OR RELATIVE_PATH ILIKE '%.docx'  -- add/remove per your corpus
    OR RELATIVE_PATH ILIKE '%.pptx' OR RELATIVE_PATH ILIKE '%.html' OR RELATIVE_PATH ILIKE '%.txt');
```

- **Leave the ingest task suspended** here. It's resumed **last** (base Step 9), only after refresh mode is
  verified (Step 6) and quality is tested (Step 8) — so scheduled AI spend never starts before the pipeline
  is verified safe.
- **Do not build a DT directly over `DIRECTORY(@stage)`.** It fails at compile time (`Object ref of type DIRECTORY_TABLE not supported`) — directory tables have no change tracking. Fix: use this block's stream + task + File Log pattern. Pivoting to a stored-proc snapshot or task-without-stream is still wrong.
- **Multi-head temptation** — do not skip the task and wire DTs straight to the stream; a DT cannot consume a stage stream incrementally. The `SHOW TASKS >= 1` check in the base Definition of done (item 5) catches this.
- **Seed the backlog** if the stage already holds files: a stream only captures files added *after* it is
  created, so `INSERT … SELECT FROM DIRECTORY(@stage)` once (base Step 4d). Use the bare `RELATIVE_PATH` that
  `DIRECTORY()` returns — it can differ from what `LIST` prints, and `TO_FILE` fails on the wrong form.
- **Stage encryption** — the stage must be server-side encrypted (`ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')`).
  Client-side-encrypted stages break **every** AI file function with *"Input files from stages with Client
  Side Encryption is not supported"*. Some upload tooling defaults to client-side — confirm/recreate as SSE
  and re-upload if so.

---

## Second ingestion path — page-image stage (optional)

When a downstream lane needs **one image per page** — `extract/vision-figures.md` (figure/chart numbers
that live only in images) — the page images sit on their **own stage** with their **own** file log + stream
+ task, identical to the above but with an image extension filter. This is a second instance of this block,
not a new mechanism.

```sql
CREATE TABLE IF NOT EXISTS <db>.<schema>.<prefix>_PAGE_LOG (
  RELATIVE_PATH STRING, FILE_NAME STRING, FILE_SIZE NUMBER,
  LAST_MODIFIED TIMESTAMP_LTZ, FILE_URL STRING, INGESTED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
ALTER TABLE <db>.<schema>.<prefix>_PAGE_LOG SET CHANGE_TRACKING = TRUE;
-- + a CREATE STREAM on @<page_stage> and a CREATE TASK filtering '%.png'/'%.jpg' (base Step 4).
```

- **Page-image layout** — lay each image path out so it mirrors the document's `RELATIVE_PATH` with the
  extension stripped, then `/<page>.<ext>` — e.g. doc `reports/acme.pdf` → pages `reports/acme/1.png`,
  `reports/acme/2.png`. The page's parent folder is then the document's `DOC_KEY` (stage-unique even when two
  docs share a basename) and the filename stem is the page number. `extract/vision-figures.md` relies on this.
- **Producing the images** — either the corpus already ships page renders, or rasterize the PDFs **inside
  Snowflake** with a Snowpark `pypdfium2` stored proc (PDFs never leave the account) — see
  [`../../references/rasterize-pdfs.md`](../../references/rasterize-pdfs.md) for a verified procedure that
  emits exactly this `<doc_id>/<page>.png` layout.
- Seed and resume this task on the same schedule as the doc-stage task.
