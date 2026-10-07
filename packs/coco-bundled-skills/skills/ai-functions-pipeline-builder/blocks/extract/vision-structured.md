# Vision (structured) — fields from images (`AI_COMPLETE` + JSON schema)

When the value lives in an **image** — a photo, a scanned form, a chart a text parser can't read — extract
structured fields with a vision `AI_COMPLETE` and a `response_format` JSON schema. Same role as
[`fields.md`](fields.md) (structured fields → typed columns), different input modality. Reads files directly,
so it slots in beside the text extractor, not after it. For **free-text page-level figure/chart narratives**
(searchable prose, not typed columns), use [`vision-figures.md`](vision-figures.md) instead.

> Read [`../conventions.md`](../conventions.md) first. Generic vision mechanics (`TO_FILE`, `PROMPT`, image
> limits) are owned by the base — [`../../references/multi-step-pipeline.md`](../../references/multi-step-pipeline.md)
> § Step 5 Layer 3b and [`../../references/visual-analysis.md`](../../references/visual-analysis.md).

- **When** — an image type carries information only a vision model can read (damage, condition, defect, a
  photographed form). A peer of the text extractors, at the same per-document grain.
- **Reads** — `FILE` (image rows) — or a routed `DOC_TEXT` slice (`WHERE DOC_TYPE = '<image_type>'`) when a
  multi-class router already typed images by modality.
- **Produces** — `TYPED_FIELDS`: `DT_<prefix>_<IMAGE_TYPE>` (typed assessment columns + `RAW_<IMAGE_TYPE>`).
- **Refresh** — **INCREMENTAL** (one vision call per new image; call inline).
- **Typical upstreams** — `ingest/ingestion.md` (raw images) or `extract/classify.md` (routed image slice).

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_<IMAGE_TYPE>
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL
AS
WITH raw AS (
  SELECT
    c.RELATIVE_PATH, c.FILE_NAME, c.<entity_key>, c.INGESTED_AT,
    AI_COMPLETE(
      '<vision_model>',                                    -- must be vision-capable; see model selection note below
      PROMPT('<role + exactly what to assess; assess only what is visible>. Image: {0}',
             TO_FILE('@<db>.<schema>.<stage>', c.RELATIVE_PATH)),
      response_format => { 'type': 'json', 'schema': { 'type': 'object',
        'properties': {
          '<field1>': { 'type': 'string', 'description': '<enumerate the allowed values>' },
          '<list>':   { 'type': 'array',  'items': { 'type': 'string' } },
          '<field2>': { 'type': 'string' } },
        'required': ['<field1>'] } }
    ) AS RAW_VISION
  FROM <db>.<schema>.DT_<prefix>_CLASSIFIED c               -- or <prefix>_FILE_LOG fl + an image extension filter
  WHERE c.DOC_TYPE = '<image_type>'                         -- vision fires only on files routed to this type
)
SELECT
  RELATIVE_PATH, FILE_NAME, <entity_key>, INGESTED_AT,
  LOWER(RAW_VISION:<field1>::STRING)               AS <FIELD1>,
  ARRAY_TO_STRING(RAW_VISION:<list>::ARRAY, '; ')  AS <LIST>,
  RAW_VISION:<field2>::STRING                      AS <FIELD2>,
  RAW_VISION
FROM raw;
```

- `PROMPT('… {0}', TO_FILE('@stage','file'))` binds the file into the prompt; `TO_FILE` takes two args. PDFs
  are accepted directly (no image conversion) — pass them the same way.
- **Constrain outputs by enumerating allowed values** in each field's description, and pin the shape with
  `response_format` JSON so downstream reads typed columns (`RAW_VISION:<field>::STRING`).
- **Carry `<entity_key>`** through the projection so `records/entity.md` can join the assessment on it.
- Image limits: jpg/png/gif/webp; ≤10 MB (3.75 MB for claude models); SSE stage required.
- **Pick a vision-capable model and verify regional availability before building the DT.** Cross-reference the [AI_COMPLETE Prompt-object reference](https://docs.snowflake.com/en/sql-reference/functions/ai_complete-prompt-object) and the [Cortex AI SQL regional availability matrix](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql-regional-availability) — neither is queryable from SQL. Probe before creating:
  ```sql
  SELECT AI_COMPLETE('<vision_model>', PROMPT('Assess the image. {0}', TO_FILE('@<db>.<schema>.<stage>', '<any_file>')));
  ```
  **Never fall back to text-only models** — they accept `TO_FILE` but return `null` or fabricated values.
