# Example — Customer 360

**Scenario:** A master customer table and enrichment tables already live in Snowflake. Mixed documents land on a
stage keyed by customer ID in the path. One incremental pipeline classifies documents, extracts signals, assembles
a 360 record per customer by joining documents with warehouse tables, scores risk, routes action lanes, indexes
text for search, and rolls up product health with an executive briefing.

Drop heads the prompt did not ask for. SQL bodies: [`../../../blocks/README.md`](../../../blocks/README.md).

**Names:** `db=ACME`, `schema=CX`, `<prefix>=C360`, `stage=C360_DOCS_STAGE`, `warehouse=CX_WH`,
`<entity_key>=CUSTOMER_ID`, `<master_table>=C360_CUSTOMERS`, `<final_lag>=1 hour`. Enrichment tables are an
open list at intake — `<txn_table>`, `<telemetry_table>`, `<survey_table>`, `<campaign_table>` are placeholders.

**Path key default:** `SPLIT_PART(SPLIT_PART(RELATIVE_PATH, '/', -1), '__', 1)`.

## Blocks, in build order

| # | Block | Object(s) | Grain | Note |
|---|-------|-----------|-------|------|
| 1 | Ingestion | `<prefix>_FILE_LOG`, stream, task | — | `.pdf`, `.txt`, audio per `parse-text.md` |
| 2 | Text body | inline in doc-rows DT | per-doc | `parse-text`; or file-log `CONTENT` when pre-loaded |
| 3 | Classify | `DT_<prefix>_CLASSIFIED` | per-doc | `AI_CLASSIFY(TO_FILE(...), …)` |
| 4 | Doc rows | `DT_<prefix>_CUSTOMER_DOCS` | per-doc | `DOC_TYPE <> 'other'`; `TEXT_BODY` |
| 5 | Doc signals | `DT_<prefix>_DOC_SIGNALS` | per-doc | `AI_COMPLETE` JSON: sentiment, issue_type |
| 6 | Entity / 360 | `DT_<prefix>_ENTITY` | per-entity | [`entity.md`](../../../blocks/records/entity.md) + warehouse `LEFT JOIN`s |
| 7 | Chunk & index | `DT_<prefix>_CHUNKS`, `<prefix>_SEARCH` | per-chunk | reads `DT_<prefix>_CUSTOMER_DOCS`; [`chunk-index.md`](../../../blocks/search/chunk-index.md) |
| 8 | Operational | on `DT_<prefix>_ENTITY` or `DT_<prefix>_TRIAGED` | per-entity | `RISK_TIER`, `ROUTE` |
| 9 | RAG | query pattern or `ask_<prefix>` proc | — | [`rag-answer.md`](../../../blocks/search/rag-answer.md) |
| 10 | Landscape | `DT_<prefix>_LANDSCAPE` or metrics + synthesize | aggregate | `GROUP BY` product or segment |
| 11 | Final shape | `<prefix>_CUSTOMER_360` view | view | [`final-shape.md`](../../../blocks/serve/final-shape.md) |

**DAG** — omit rows 8–10 per prompt:

```
@<stage> → stream + task → <prefix>_FILE_LOG
  → DT_<prefix>_CLASSIFIED → DT_<prefix>_CUSTOMER_DOCS → DT_<prefix>_DOC_SIGNALS   [per-doc · INCREMENTAL]
        ├ → DT_<prefix>_CHUNKS → <prefix>_SEARCH
        └ → DT_<prefix>_ENTITY  ← aggregates DOCS + SIGNALS + warehouse
              ├ RISK_TIER / ROUTE
              └ DT_<prefix>_LANDSCAPE
              → <prefix>_CUSTOMER_360 view
```

## Wiring notes

- **Master spine:** `FROM <master_table>`; doc aggs `LEFT JOIN` in. Doc-only spine only when intake says so.
- **Entity DT:** `DT_<prefix>_ENTITY` is the shared per-entity contract; warehouse tables join here.
- **Classify on content:** `AI_CLASSIFY` on `TO_FILE` or text — not path token after `__`.
- **Txt:** default `parse-text`; join file-log `CONTENT` when ingest already loaded it.
- **Operational:** deterministic tier/route on `DT_<prefix>_ENTITY`, or `reason` + `triage` for AI judgment.
- **Search:** `DT_<prefix>_CHUNKS` from `DT_<prefix>_CUSTOMER_DOCS` per [`chunk-index.md`](../../../blocks/search/chunk-index.md).
- **Landscape:** `metrics-trend` + `synthesize` for trends; single rollup DT for snapshots.

## Assembly pattern

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_ENTITY
  TARGET_LAG = '<final_lag>' WAREHOUSE = <warehouse> REFRESH_MODE = INCREMENTAL
AS
WITH doc_agg AS (
  SELECT <entity_key>, COUNT(*) AS DOC_COUNT, ...
  FROM <db>.<schema>.DT_<prefix>_CUSTOMER_DOCS GROUP BY <entity_key>
),
sig_agg AS (
  SELECT <entity_key>, SUM(IFF(RAW:sentiment::STRING = 'negative', 1, 0)) AS NEG_DOC_COUNT, ...
  FROM <db>.<schema>.DT_<prefix>_DOC_SIGNALS GROUP BY <entity_key>
),
tel AS (
  SELECT <entity_key>, MAX(error_rate) AS MAX_ERROR_RATE, ...
  FROM <db>.<schema>.<telemetry_table> GROUP BY <entity_key>
)
SELECT
  m.*,
  COALESCE(d.DOC_COUNT, 0) AS DOC_COUNT,
  COALESCE(s.NEG_DOC_COUNT, 0) AS NEG_DOC_COUNT,
  t.MAX_ERROR_RATE,
  CASE WHEN ... THEN 'high' WHEN ... THEN 'medium' ELSE 'low' END AS RISK_TIER,
  CASE WHEN ... THEN 'escalate' WHEN ... THEN 'needs_review' ELSE 'auto_act' END AS ROUTE
FROM <db>.<schema>.<master_table> m
LEFT JOIN doc_agg d USING (<entity_key>)
LEFT JOIN sig_agg s USING (<entity_key>)
LEFT JOIN tel t USING (<entity_key>);
```

Elicit risk thresholds at the build gate.

```sql
CREATE OR REPLACE VIEW <db>.<schema>.<prefix>_CUSTOMER_360 AS
SELECT
  <entity_key>, DOC_COUNT, NEG_DOC_COUNT, MAX_ERROR_RATE, RISK_TIER, ROUTE
FROM <db>.<schema>.DT_<prefix>_ENTITY;   -- or DT_<prefix>_TRIAGED when triage is composed
```

## Build & verify

Create in dependency order; ingest task suspended until Step 6 passes. Per-doc and per-entity DTs must be
`INCREMENTAL`. Resume ingest task last.
