# Entity assembly — per-document → per-entity (`ENTITY`)

The grain shift: turn per-document extractor rows into **one row per entity** (a claim, application, loan file,
shipment…) when several documents compose one record. Skip this block for per-document pipelines — the
extractors are already the records, and serving reads them directly.

> Read [`../conventions.md`](../conventions.md) first — shapes, the three grain shifts, refresh contract.

- **When** — multiple documents share an `<entity_key>` and must be reassembled into one record.
- **Reads** — all per-type `TYPED_FIELDS` DTs (on `<entity_key>`) + `DT_<prefix>_CLASSIFIED` (for the spine).
- **Produces** — `ENTITY`: `DT_<prefix>_ENTITY` (one row per `<entity_key>`: all type fields + `HAS_*` flags + derived signals).
- **Refresh** — **INCREMENTAL** (`DISTINCT` spine + multiple `LEFT JOIN`s stay incremental).
- **Typical upstreams** — `extract/fields.md` (routed extractors), `extract/vision-structured.md`, `extract/classify.md`.

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_ENTITY
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL
AS
WITH spine AS (                                         -- the entity universe; excludes 'other' so off-target files never become an entity
  SELECT DISTINCT <entity_key>
  FROM <db>.<schema>.DT_<prefix>_CLASSIFIED
  WHERE DOC_TYPE IN ('<type1>', '<type2>', '<type3>', '<image_type>')
)
SELECT
  s.<entity_key>,
  (t1.<entity_key> IS NOT NULL) AS HAS_<TYPE1>,         -- presence flags = partial-assembly record
  (t2.<entity_key> IS NOT NULL) AS HAS_<TYPE2>,
  (im.<entity_key> IS NOT NULL) AS HAS_<IMAGE_TYPE>,
  t1.<…fields…>, t2.<…fields…>, im.<…fields…>,
  -- derived cross-document signals (clean columns for reason + triage to read):
  IFF(t2.<amount_b> IS NOT NULL AND t2.<amount_b> <> 0 AND t1.<amount_a> IS NOT NULL,
      ROUND(t1.<amount_a> / t2.<amount_b>, 3), NULL)                       AS <RATIO_SIGNAL>,
  (t1.<fault> IS NOT NULL AND t3.<fault> IS NOT NULL
     AND t1.<fault> <> 'unclear' AND t3.<fault> <> 'unclear'
     AND t1.<fault> <> t3.<fault>)                                        AS <CONTRADICTION_FLAG>,
  GREATEST(COALESCE(t2.<amount_b>,0), COALESCE(t1.<amount_a>,0))          AS <MAX_EXPOSURE>,
  LEAST(COALESCE(t1.MIN_KEY_CONF,1), COALESCE(t2.MIN_KEY_CONF,1))         AS MIN_KEY_CONF,   -- lowest extraction confidence across the packet
  COALESCE(t1.INGESTED_AT, t2.INGESTED_AT, im.INGESTED_AT)                AS INGESTED_AT
FROM spine s
LEFT JOIN <db>.<schema>.DT_<prefix>_<TYPE1>      t1 ON s.<entity_key> = t1.<entity_key>
LEFT JOIN <db>.<schema>.DT_<prefix>_<TYPE2>      t2 ON s.<entity_key> = t2.<entity_key>
LEFT JOIN <db>.<schema>.DT_<prefix>_<IMAGE_TYPE> im ON s.<entity_key> = im.<entity_key>;
```

- **Spine** = the entity universe (`DISTINCT <entity_key>` excluding `other`). **LEFT JOIN** every type so an
  entity survives with documents missing; `HAS_*` flags record what was present.
- Assumes **≤1 document of each type per entity** (joins are 1:1, no fan-out). If a type can repeat, pre-reduce
  to one row per `(entity, type)` with `QUALIFY ROW_NUMBER() OVER (PARTITION BY <entity_key> ORDER BY …) = 1`.
- Compute the **deterministic cross-document signals** here (ratios, contradiction booleans, max exposure) so
  the reason prompt and triage rules read clean columns instead of recomputing.
- Carry `MIN_KEY_CONF` forward (the packet-wide extraction-confidence floor) — `records/triage.md` gates on it.
