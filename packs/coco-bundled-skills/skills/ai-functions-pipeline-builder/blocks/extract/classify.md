# Classify — sort, gate, route (`AI_CLASSIFY`)

Assign a category label to each document. Three flavors of the same function: a **binary gate** (keep one
type, drop the rest), a **multi-class router** (fan out to per-type extractors), and a **category-derive**
(add a grouping dimension for analytics). Pick the one your goal needs.

> Read [`../conventions.md`](../conventions.md) first — shapes, refresh contract, placeholders.

- **Reads** — a `DOC_TEXT` row (`PARSED_TEXT`); the router also reads `FILE` for image types.
- **Produces** — `DOC_TEXT` + a `DOC_TYPE` (or category) column.
- **Refresh** — **INCREMENTAL**.
- **Typical upstreams** — `ingest/parse-text.md`.

Task-description quality drives accuracy — define each class, and define `other` explicitly so off-target
documents land somewhere gateable.

**Keep label tokens short; put definitions in `task_description`.** Verbose multi-word labels classify worse — the model hedges to `other`, and every downstream `WHERE DOC_TYPE = '<type>'` extractor gets zero rows. Use a short distinct token per class. **The token in the label array is the exact string downstream blocks must filter on** — `'repair estimate'` emitted while the extractor filters `WHERE DOC_TYPE = 'estimate'` silently matches nothing. After building, spot-check distribution (`SELECT DOC_TYPE, COUNT(*) … GROUP BY 1`): near-100% `other` means labels are too verbose — fix before wiring extractors.

`AI_CLASSIFY` returns `{"labels": [...]}`. Read the chosen label as `:labels[0]::STRING` — the singular path `:label` does not exist and silently returns NULL for every row. Multi-label mode returns several entries in the same `labels` array.

---

## Binary gate — keep one type

When mixed types land on the stage and you only want one (e.g. invoices), classify and let downstream blocks
filter on `DOC_TYPE`. Cheaper than a full router when there's a single target type.

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_CLASSIFIED
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL
AS
SELECT
  p.*,
  AI_CLASSIFY(
    p.PARSED_TEXT,
    ['<target_type>', '<near_neighbour1>', '<near_neighbour2>', 'other'],
    {'task_description': 'Classify this document by type. Pick the single best match. '
       || 'Choose "<target_type>" only if <explicit definition of the target>.'}
  ):labels[0]::STRING AS DOC_TYPE
FROM <db>.<schema>.DT_<prefix>_PARSED p;
```

Downstream blocks add `WHERE DOC_TYPE = '<target_type>'` so `AI_EXTRACT` never fires on the rest. For images
(no parse step), pass `TO_FILE(...)` directly to `AI_CLASSIFY`.

---

## Multi-class router — traffic controller (1 → N)

When several document types arrive mixed and each must go to its own extractor. Two arms unioned: the **text
arm** classifies parsed text into your N types plus `other`; the **image arm** types images **by modality**
(a `.jpg` is unambiguously a photo) without spending an AI call.

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_CLASSIFIED
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL
AS
SELECT
  p.RELATIVE_PATH, p.FILE_NAME, p.<entity_key>, p.LAST_MODIFIED, p.INGESTED_AT,
  'pdf' AS MODALITY, p.PARSED_TEXT,
  AI_CLASSIFY(
    p.PARSED_TEXT,
    ['<type1>', '<type2>', '<type3>', 'other'],
    {'task_description': 'Classify this <domain> document by type. <type1> = <one-line definition>. '
       || '<type2> = <…>. <type3> = <…>. other = anything that is NOT one of these. Pick the single best match.'}
  ):labels[0]::STRING AS DOC_TYPE
FROM <db>.<schema>.DT_<prefix>_PARSED p
UNION ALL
SELECT
  fl.RELATIVE_PATH, fl.FILE_NAME,
  SPLIT_PART(SPLIT_PART(fl.RELATIVE_PATH, '/', -1), '__', 1) AS <entity_key>,
  fl.LAST_MODIFIED, fl.INGESTED_AT,
  'image' AS MODALITY, NULL AS PARSED_TEXT,
  '<image_type>' AS DOC_TYPE                       -- e.g. 'photo'; modality fully determines it
FROM <db>.<schema>.<prefix>_FILE_LOG fl
WHERE fl.RELATIVE_PATH ILIKE '%.jpg' OR fl.RELATIVE_PATH ILIKE '%.jpeg' OR fl.RELATIVE_PATH ILIKE '%.png';
```

- **Off-target gate** — files classified `other` are simply not selected by any downstream extractor.
- **Single modality?** Drop the image arm (no `UNION ALL`).
- Each kept type then flows to its own `extract/fields.md` slice (`WHERE DOC_TYPE = '<type>'`) or, for image
  types, `extract/vision-structured.md`.

---

## Category-derive — a grouping dimension for analytics

A raw `vendor`/`author` column is often near-unique (one doc each → nothing to trend). When the analytical
metrics rollup needs cardinality-per-period, derive a **fixed taxonomy** with a small `AI_CLASSIFY` step (same
mechanism as the gate) and group on that. Produces one category column carried forward into `analyze/metrics-trend.md`.

```sql
  AI_CLASSIFY(<text or extracted field>, ['<cat1>', '<cat2>', '<cat3>', 'other'],
    {'task_description': 'Assign a spend/topic category. <cat1> = <…>. …'}):labels[0]::STRING AS CATEGORY
```

Downstream aggregation groups on `CATEGORY`, so canonicalize it — `LOWER(TRIM(...))` it before `GROUP BY` in `metrics-trend.md`; otherwise inconsistent casing across documents splits one category into several under-counted rows.
