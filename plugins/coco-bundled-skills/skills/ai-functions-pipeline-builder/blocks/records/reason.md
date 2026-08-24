# Reason / decide — judgment over extracted fields (`AI_COMPLETE`)

A *judgment-derived* field that isn't printed on any document: a risk flag, a priority, a derived amount, a
recommended action, a rationale. Reason **over the already-extracted typed columns** — don't ask the model to
re-read fields the extractors already pulled. Two flavors of one pattern: **single-document** (reason over one
record's fields) and **cross-document** (reason over a whole assembled entity).

> **Extract vs. reason** — extract when the value is *printed on the page* (every block in `extract/`). Reason
> with `AI_COMPLETE` only when the value needs *judgment* over what was already extracted (rank urgency, flag
> risk, categorize, decide). Extract first, then reason over the clean typed columns.

> Read [`../conventions.md`](../conventions.md) first — shapes, refresh contract, placeholders.

- **Reads** — a `TYPED_FIELDS` record (single-doc) or an `ENTITY` (cross-doc); add `PARSED_TEXT` to the prompt
  only if the judgment needs the full document.
- **Produces** — `DECISION`: `DT_<prefix>_DECISION` (+ `RISK, REASONS, DERIVED_AMOUNT, SUGGESTED_ACTION, RATIONALE`).
- **Refresh** — **INCREMENTAL**.
- **Typical upstreams** — `records/entity.md` (cross-doc), `records/validate.md` or `extract/fields.md` (single-doc).

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_DECISION
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL
AS
WITH reasoned AS (
  SELECT
    c.*,
    AI_COMPLETE(
      '<reasoning_model>',
      '<role>. <the integrity / judgment checks to consider, named explicitly>.'
      || '\n\nFACTS:'
      || '\n- <key>: '           || COALESCE(c.<entity_key>, 'unknown')
      || '\n- <fieldA>: '        || COALESCE(c.<FIELD_A>::STRING, 'unknown')
      || '\n- <ratio>: '         || COALESCE(c.<RATIO_SIGNAL>::STRING, 'unknown')
      || '\n- <contradiction>: ' || COALESCE(c.<CONTRADICTION_FLAG>::STRING, 'unknown')
      || '\n- <vision_field>: '  || COALESCE(c.<ASSESSMENT1>, 'missing'),
      response_format => { 'type': 'json', 'schema': { 'type': 'object',
        'properties': {
          '<risk>':            {'type': 'string', 'description': 'one of: none, low, medium, high'},
          '<reasons>':         {'type': 'array',  'items': {'type': 'string'}},
          '<derived_amount>':  {'type': 'number'},
          '<suggested_action>':{'type': 'string', 'description': 'one of: <lane1>, <lane2>, <lane3>'},
          'rationale':         {'type': 'string'} },
        'required': ['<risk>', '<derived_amount>', '<suggested_action>'] } }
    ) AS RAW_DECISION
  FROM <db>.<schema>.DT_<prefix>_ENTITY c              -- single-doc: DT_<prefix>_RECONCILED / _EXTRACTED
)
SELECT
  *,                                                   -- prior columns + RAW_DECISION (audit)
  LOWER(RAW_DECISION:<risk>::STRING)                                  AS <RISK>,
  ARRAY_TO_STRING(RAW_DECISION:<reasons>::ARRAY, '; ')                AS <REASONS>,
  TRY_CAST(RAW_DECISION:<derived_amount>::STRING AS NUMBER(18,2))     AS <DERIVED_AMOUNT>,
  LOWER(RAW_DECISION:<suggested_action>::STRING)                      AS <SUGGESTED_ACTION>,
  RAW_DECISION:rationale::STRING                                      AS RATIONALE
FROM reasoned;
```

> **COALESCE every interpolated fact** — a NULL anywhere in the `||` chain makes the whole prompt NULL and
> `AI_COMPLETE` errors. Wrap each fact in `COALESCE(...::STRING, 'unknown'/'missing')`.

- **Single-document flavor** — read from the terminal per-document DT (`DT_<prefix>_RECONCILED`, else
  `DT_<prefix>_EXTRACTED`); the FACTS are that one document's fields. Use it for an invoice priority/risk/action
  or a spend category that takes reasoning.
- **Cross-document flavor** — read from `DT_<prefix>_ENTITY`; the FACTS are the assembled packet plus its derived
  signals (ratios, contradiction flags, `HAS_*`). Use it for a claim/application risk that no single document states.
- Act on the judgment with `records/triage.md` (route to lanes) or a simple `ORDER BY` reviewer queue.
