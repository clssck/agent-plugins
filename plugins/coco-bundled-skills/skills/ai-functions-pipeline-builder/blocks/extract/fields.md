# Extract fields — structured data from text (`AI_EXTRACT`)

Pull named fields and tables out of document text into typed columns. The single biggest accuracy lever is
**field-description quality** — state the format, disambiguate near-neighbours, say what each field is *not*.
This file covers four flavors that share one engine: a **typed header**, a **routed extractor** (one per type
with confidence scoring), a **schema-elicited** extractor (corpus, with a required display key), and
**line-item / table** extraction with flatten.

> Read [`../conventions.md`](../conventions.md) first — shapes, refresh contract, placeholders. Generic
> `AI_EXTRACT` mechanics (response shape, `"None"` → `TRY_CAST`, input truncation, confidence scoring) live in
> [`../../references/extraction.md`](../../references/extraction.md).

- **Reads** — a `DOC_TEXT` row (`PARSED_TEXT` / `PARSED_TEXT_EN` / page `CONTENT`), or the file directly.
- **Produces** — `TYPED_FIELDS`: `DT_<prefix>_EXTRACTED` (or `DT_<prefix>_<TYPE>`) — typed columns + `RAW_EXTRACT` (+ `*_CONF`).
- **Refresh** — **INCREMENTAL**.
- **Typical upstreams** — `ingest/parse-text.md`, `extract/classify.md` (gate/router), `ingest/parse-text.md` Translate.

`AI_EXTRACT` returns the string `"None"` for missing values, so `TRY_CAST` every non-string field; models
sometimes ignore "number only", so strip non-numeric characters from amounts before casting. Always extract in
a CTE, then project typed columns so downstream reads clean columns.

---

## Typed header — one record per document

The core shape: a handful of named scalar fields → typed columns.

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_EXTRACTED
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL
AS
WITH raw AS (
  SELECT
    p.RELATIVE_PATH, p.FILE_NAME, p.INGESTED_AT,
    AI_EXTRACT(
      text => p.PARSED_TEXT,   -- PARSED_TEXT_EN if Translate is upstream; or file => TO_FILE('@<db>.<schema>.<stage>', p.RELATIVE_PATH)
      responseFormat => {
        '<id_field>':    'The primary ID. Usually labeled "<label>". NOT the <near-neighbour ID>.',
        '<date_field>':  'Issue date in YYYY-MM-DD format. NOT the due/received date.',
        '<party_field>': 'The issuing party name. NOT the counterparty.',
        '<amount>':      'Total amount. Number only, no currency symbol or thousands separators.',
        '<currency>':    'ISO-4217 code (USD, EUR, …). Infer from symbol if no code is printed.'
      }
    ) AS RAW_EXTRACT
  FROM <db>.<schema>.DT_<prefix>_PARSED p   -- or DT_<prefix>_CLASSIFIED c … WHERE c.DOC_TYPE = '<type>'
)
SELECT
  RELATIVE_PATH, FILE_NAME, INGESTED_AT,
  RAW_EXTRACT:response:<id_field>::STRING                                                       AS <ID_FIELD>,
  TRY_CAST(RAW_EXTRACT:response:<date_field>::STRING AS DATE)                                    AS <DATE_FIELD>,
  RAW_EXTRACT:response:<party_field>::STRING                                                     AS <PARTY_FIELD>,
  TRY_CAST(REGEXP_REPLACE(RAW_EXTRACT:response:<amount>::STRING, '[^0-9.-]', '') AS NUMBER(18,2)) AS <AMOUNT>,
  RAW_EXTRACT:response:<currency>::STRING                                                        AS <CURRENCY>,
  RAW_EXTRACT                                                                                    -- full payload; audit/debug
FROM raw;
```

- Drop fields you don't need; add custom ones with equally explicit descriptions.
- The amount-strip handles US/UK formats (`$1,671.97`, `USD 598.50`, `-165.99`); add locale handling for
  European decimals (`1.671,97`) if vendors use them.
- Poor quality on dense/small-text pages? Pass `config => { 'scale_factor': 1.5 }` (up to `4.0`) — but only
  after refining descriptions has plateaued (scale_factor lowers the page limit: `floor(125/scale_factor)`).
- **Every `AI_EXTRACT` result is nested under `:response:`** (both the flat-list and JSON-schema forms). Reading at the bare path (`RAW_EXTRACT:field` instead of `RAW_EXTRACT:response:field`) returns **NULL silently** — a whole column of NULLs after a clean build is almost always this. Run a one-row `SELECT RAW_EXTRACT` to confirm the wrapper first.

---

## Routed extractor — one per type, with confidence

When `extract/classify.md` ran as a multi-class router, instantiate this **once per kept text type**, each
with its **own schema**, scoped to that `DOC_TYPE` slice. `scores => TRUE` is **on by default** here — the
per-field certainty feeds the review lane in `records/triage.md`.

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_<TYPE>
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL
AS
WITH raw AS (
  SELECT
    c.RELATIVE_PATH, c.FILE_NAME, c.<entity_key>, c.INGESTED_AT,
    AI_EXTRACT(
      text => c.PARSED_TEXT,
      responseFormat => {
        '<field1>': '<explicit description; state the format; say what it is NOT>',
        '<amount>': 'A monetary amount. Number only, no currency symbol or thousands separators.'
      },
      scores => TRUE                 -- per-field confidence (0–1) drives the review flag
    ) AS RAW_EXTRACT
  FROM <db>.<schema>.DT_<prefix>_CLASSIFIED c
  WHERE c.DOC_TYPE = '<type>'
)
SELECT
  RELATIVE_PATH, FILE_NAME, <entity_key>, INGESTED_AT,
  RAW_EXTRACT:response:<field1>::STRING                                                          AS <FIELD1>,
  TRY_CAST(REGEXP_REPLACE(RAW_EXTRACT:response:<amount>::STRING, '[^0-9.-]', '') AS NUMBER(18,2)) AS <AMOUNT>,
  TRY_CAST(RAW_EXTRACT:scoring:scores:<field1>:score::STRING AS FLOAT)                            AS <FIELD1>_CONF,
  TRY_CAST(RAW_EXTRACT:scoring:scores:<amount>:score::STRING AS FLOAT)                            AS <AMOUNT>_CONF,
  LEAST(                                                                                          -- per-document floor for Triage
    COALESCE(TRY_CAST(RAW_EXTRACT:scoring:scores:<field1>:score::STRING AS FLOAT), 1),
    COALESCE(TRY_CAST(RAW_EXTRACT:scoring:scores:<amount>:score::STRING AS FLOAT), 1)
  )                                                                                              AS MIN_KEY_CONF,
  RAW_EXTRACT
FROM raw;
```

- **Confidence threshold** — start ≈ **0.6** and **calibrate**: sample the `MIN_KEY_CONF` spread on a batch and
  set the cutoff to catch the low tail. Make it one named constant so it's a one-line change. Image-extracted
  scores skew lower than text — calibrate down (~0.5). Per-field scores are **scalar-only**; lists/tables return
  one aggregate score, not per-cell.
- One type carries the **identifying fields** for the entity (claimant, dates, amounts) — `records/entity.md`
  surfaces them from there.

---

## Schema-elicited — corpus extraction with a display key

When the corpus has **no fixed schema** (papers → methods/contributions; filings → metrics/risks), elicit the
fields worth capturing from the goal. Two requirements specific to this flavor:

> **Required display key — `TITLE`.** Theme assignment, highlights, synthesis, and serving views all label items
> by a per-document `TITLE`. Your schema **must** expose a short, document-unique field as `TITLE`, carried
> forward. No natural title (forms, tickets, scans)? Fall back to `FILE_NAME`. Every row must end with a
> non-empty `TITLE` or downstream labels go blank.

> **Time key (optional).** If the corpus needs a trend, every doc needs an orderable time key (e.g. `PUB_YEAR`).
> Prefer **deterministic SQL** off the filename/stage metadata when a date is encoded there (free, no
> hallucination — e.g. arXiv `YYMM` → `2000 + LEFT(FILE_NAME,2)`); otherwise pull it from the body with an
> `AI_EXTRACT` field. Expose one typed column, carry it forward for `analyze/metrics-trend.md`.

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_EXTRACTED
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL  INITIALIZE = ON_SCHEDULE
AS
WITH raw AS (
  SELECT p.RELATIVE_PATH, p.FILE_NAME, p.INGESTED_AT,
    AI_EXTRACT(
      text => LEFT(p.PARSED_TEXT, 120000),   -- truncate long input (AI_EXTRACT has a ~125-page limit even on text)
      responseFormat => {'schema': {'type': 'object', 'properties': {
        '<scalar_field>': {'description': '<explicit description; disambiguate near-neighbours>', 'type': 'string'},
        '<list_field>':   {'description': '<what each item is>', 'type': 'array'}
        -- ⚠ The simple {field:'description'} form extracts SINGLE values only — a list field then comes back as a
        --   scalar string. The 'type':'array' schema form above guarantees a real ARRAY, even for one item.
      }}}
    ) AS RAW_EXTRACT
  FROM <db>.<schema>.DT_<prefix>_PARSED p      -- or DT_<prefix>_TRANSLATED (PARSED_TEXT_EN)
)
SELECT
  RELATIVE_PATH, FILE_NAME, INGESTED_AT,
  COALESCE(NULLIF(RAW_EXTRACT:response:title::STRING, ''), FILE_NAME) AS TITLE,  -- required display key; filename fallback
  RAW_EXTRACT:response:<scalar_field>::STRING AS <SCALAR_FIELD>,
  RAW_EXTRACT:response:<list_field>           AS <LIST_FIELD>,   -- a real ARRAY
  RAW_EXTRACT
FROM raw;
```

---

## Line items / tables — parallel arrays → rows

When a table (invoice line items, etc.) must land in its own normalized table, extract it as one VARIANT cell
of **parallel arrays**, then flatten into rows. Reusable for any repeating table, not just invoices.

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_EXTRACTED_LINES
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL
AS
SELECT
  p.RELATIVE_PATH, p.FILE_NAME, p.INGESTED_AT,
  AI_EXTRACT(
    text => p.PARSED_TEXT,
    responseFormat => { 'schema': { 'type': 'object', 'properties': { 'line_items': {
      'type': 'object',
      'description': 'All billable line items. Exclude subtotal / tax / total rows.',
      'column_ordering': ['description', 'quantity', 'unit_price', 'amount'],
      'properties': {
        'description': { 'description': 'Item description as printed', 'type': 'array' },
        'quantity':    { 'description': 'Quantity (number). Use 1 if not stated.', 'type': 'array' },
        'unit_price':  { 'description': 'Unit price (number, no symbol). Null if not stated.', 'type': 'array' },
        'amount':      { 'description': 'Line total (number, no symbol).', 'type': 'array' }
      } } } } }
  ) AS RAW_LINES
FROM <db>.<schema>.DT_<prefix>_PARSED p;

CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_LINE_ITEMS
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL
AS
SELECT
  el.RELATIVE_PATH, el.FILE_NAME,
  f.index + 1 AS LINE_NO,                                       -- 1-based; array access stays 0-based f.index
  el.RAW_LINES:response:line_items:description[f.index]::STRING AS DESCRIPTION,
  TRY_CAST(el.RAW_LINES:response:line_items:quantity[f.index]::STRING AS NUMBER(18,4)) AS QUANTITY,
  TRY_CAST(REGEXP_REPLACE(el.RAW_LINES:response:line_items:unit_price[f.index]::STRING, '[^0-9.-]', '') AS NUMBER(18,4)) AS UNIT_PRICE,
  TRY_CAST(REGEXP_REPLACE(el.RAW_LINES:response:line_items:amount[f.index]::STRING,     '[^0-9.-]', '') AS NUMBER(18,2)) AS AMOUNT,
  el.INGESTED_AT
FROM <db>.<schema>.DT_<prefix>_EXTRACTED_LINES el,
     LATERAL FLATTEN(input => el.RAW_LINES:response:line_items:description) f;   -- select f.index, never f.seq
```

> `LATERAL FLATTEN` over the materialized `RAW_LINES` array stays `INCREMENTAL`. Expose `<prefix>_LINE_ITEMS` as a **view** over `DT_<prefix>_LINE_ITEMS`. If line-item quality from text is poor, extract direct-from-file (`file => TO_FILE(...)`, re-paying parse). The nested-object array form here is required — the simpler `'type':'array'` form throws *"Incorrect 2nd-level type"*.
>
> ⚠ **Ragged arrays** — parallel columns can have unequal lengths when a row has missing cells. Index-based access then maps values to the wrong row. Instruct each column's description to emit one element per item with an explicit null placeholder for missing cells. If misalignment persists, fall back to direct-from-file extraction.
