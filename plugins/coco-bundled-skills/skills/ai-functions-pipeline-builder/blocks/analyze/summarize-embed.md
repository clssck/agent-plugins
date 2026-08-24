# Summarize & embed — distill each document for similarity (`AI_COMPLETE`, `AI_EMBED`)

The two per-document inputs the corpus-understanding suite consumes: a **structured summary** (a small set of
short facets capturing *"what is this document about"*) and its **embedding** (for similarity / clustering /
nearest-theme). Both stay `INCREMENTAL` — they're the per-document grain feeding the corpus-grain rollups in
[`themes-clusters.md`](themes-clusters.md), [`metrics-trend.md`](metrics-trend.md), and [`synthesize.md`](synthesize.md).

> Read [`../conventions.md`](../conventions.md) first — shapes, refresh contract, placeholders.

---

## Per-document summary — structured facets

- **When** — almost always for corpus understanding; the distilled unit the embedding, taxonomy, and synthesis consume.
- **Reads** — `TYPED_FIELDS` (`DT_<prefix>_EXTRACTED`) **and** the `DOC_TEXT` (`DT_<prefix>_PARSED`) — uses both
  the extracted fields and the full text.
- **Produces** — `SUMMARY`: `DT_<prefix>_SUMMARIZED` (`SUMMARY_JSON`, typed `S_*` facet columns, and `SUMMARY_TEXT`).
- **Refresh** — **INCREMENTAL**.
- **Typical upstreams** — `extract/fields.md` (schema-elicited) + `ingest/parse-text.md`; optionally join `extract/vision-figures.md`'s doc-grain `FIGURE_FACTS`.

Pin a small, **structured** facet set (≈3–8 short facets) named for your corpus (e.g. a paper set:
`problem / approach / key_result / significance`). `<facet1>…` below are placeholders.

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_SUMMARIZED
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL  INITIALIZE = ON_SCHEDULE
AS
WITH s AS (
  SELECT e.*,
    AI_COMPLETE(
      '<reasoning_model>',
      -- Use BOTH the extracted fields and the full text: extraction gives structure, the body adds nuance it missed.
      PROMPT('Summarize into the required JSON fields, using both inputs below.\n\nExtracted fields:\n{0}\n\nFull document contents:\n{1}',
        CONCAT_WS('\n',                                              -- ⚠ COALESCE every PROMPT arg (a NULL arg → NULL prompt → error)
          '<fieldA>: ' || COALESCE(NULLIF(e.<FIELD1>,'None'),''),
          '<fieldB>: ' || COALESCE(ARRAY_TO_STRING(e.<FIELD2>::ARRAY, '; '), '')),
        COALESCE(p.PARSED_TEXT, '')),
      response_format => {'type':'json','schema':{'type':'object','properties':{
        '<facet1>':{'type':'string'},'<facet2>':{'type':'string'},'<facet3>':{'type':'string'}},
        'required':['<facet1>','<facet2>','<facet3>']}}
    ) AS SUMMARY_JSON
  FROM <db>.<schema>.DT_<prefix>_EXTRACTED e
  JOIN <db>.<schema>.DT_<prefix>_PARSED p USING (RELATIVE_PATH)
)
SELECT s.*,
  SUMMARY_JSON:<facet1>::STRING AS S_<FACET1>,   -- one S_<FACET> per facet
  SUMMARY_JSON:<facet2>::STRING AS S_<FACET2>,
  SUMMARY_JSON:<facet3>::STRING AS S_<FACET3>,
  -- SUMMARY_TEXT must never be NULL/empty (it feeds AI_EMBED); fall back to extracted fields on soft failure:
  NULLIF(TRIM(CONCAT_WS(' ',
    COALESCE(SUMMARY_JSON:<facet1>::STRING, ''), COALESCE(SUMMARY_JSON:<facet2>::STRING, ''),
    COALESCE(SUMMARY_JSON:<facet3>::STRING, ''),
    IFF(SUMMARY_JSON IS NULL, '<fallback: extracted fields stringified>', '')
  )), '') AS SUMMARY_TEXT
FROM s;
```

- **⚠ NULL-prompt trap** — `PROMPT()` returns NULL if **any** argument is NULL, then `AI_COMPLETE(model, NULL,
  response_format=>...)` throws `400 'invalid options object'`. **COALESCE every argument.**
- **Soft NULL outputs** — `AI_COMPLETE` with `response_format` occasionally returns NULL for a row; build
  `SUMMARY_TEXT` with a fallback to the extracted fields, else `AI_EMBED(NULL)` → NULL vector → the doc drops out
  of clustering. For oversized docs, cap `PARSED_TEXT` with `LEFT(...)`.
- **Facets ripple downstream** — `S_<FACET*>` are consumed by `themes-clusters.md`, `synthesize.md`, and serving;
  use the same facet names there.

---

## Embedding — `AI_EMBED`

- **When** — needed for taxonomy assignment, outliers, and any similarity work. (Cortex Search embeds internally,
  so you don't need this for search alone — only for the vector math in `themes-clusters.md`.)
- **Reads** — `SUMMARY` (`SUMMARY_TEXT`).
- **Produces** — `EMBEDDED`: `DT_<prefix>_EMBEDDED` (`SUMMARY_VEC VECTOR(FLOAT, <dim>)`).
- **Refresh** — **INCREMENTAL**.

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_EMBEDDED
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL  INITIALIZE = ON_SCHEDULE
AS
SELECT s.*, AI_EMBED('<embed_model>', s.SUMMARY_TEXT) AS SUMMARY_VEC
FROM <db>.<schema>.DT_<prefix>_SUMMARIZED s;
```

> A `VECTOR` column read into Snowpark via `to_pandas()` deserializes to `None` — select `SUMMARY_VEC::ARRAY`
> and parse the JSON string if a Python step needs the raw vector.
