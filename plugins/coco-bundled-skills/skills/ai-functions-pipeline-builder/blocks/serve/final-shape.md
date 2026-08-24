# Final shape — user-facing serving views

The tail of every pipeline: thin **views** over the terminal DTs that expose a clean, curated surface and hide
the `RAW_*` VARIANTs and intermediate columns. Select only columns whose blocks were actually composed. Views
have no refresh mode; they recompute as the DTs they read refresh.

> Read [`../conventions.md`](../conventions.md) first. Some serving views are created **inside their own
> blocks** — lane views in [`../records/triage.md`](../records/triage.md), the insights view in
> [`../analyze/synthesize.md`](../analyze/synthesize.md), highlights in
> [`../analyze/themes-clusters.md`](../analyze/themes-clusters.md). This file covers the remaining
> per-document / per-entity / corpus surfaces.

- **When** — always; the deliverable consumers query.
- **Reads** — the terminal DT(s) of the composed chain.
- **Produces** — `<prefix>_*` views.
- **Refresh** — views (no refresh mode).

---

## Per-document — header (+ optional split line-items)

The common structured-extraction shape: one row per document, plus a separate line-items view if you split them.

```sql
CREATE OR REPLACE VIEW <db>.<schema>.<prefix>_HEADER AS
SELECT
  RELATIVE_PATH, FILE_NAME, <id_field>, <date_field>, <party_field>, <amount>, <currency>,
  RECON_STATUS, RECON_DISCREPANCY_PCT,   -- only if reconciliation was composed
  VENDOR_ID,                             -- only if master-match was composed
  INGESTED_AT
FROM <db>.<schema>.DT_<prefix>_RECONCILED;   -- ← the terminal DT of YOUR chain (_ANALYZED / _VENDOR_MATCHED / _EXTRACTED)
-- <prefix>_LINE_ITEMS is the view created in extract/fields.md (line-items flavor).
```

- **Single wide** (line items embedded as a VARIANT on the header): include a `line_items` array in the extract
  `responseFormat` and select `RAW_EXTRACT:response:line_items AS LINE_ITEMS`. Per-line attributes can't be
  header-grain scalars; keep them on the line-items table.
- **Header-only**: emit just `<prefix>_HEADER`; don't compose the line-items block.

---

## Per-entity — the curated record (+ lanes)

For assembled records, surface identity + key amounts + presence flags + risk/decision/route over the terminal
per-entity DT — `DT_<prefix>_TRIAGED` if the operational head exists, else `DT_<prefix>_ENTITY`. (When triage is
composed, this view and the per-lane views are created in [`../records/triage.md`](../records/triage.md).)

```sql
CREATE OR REPLACE VIEW <db>.<schema>.<prefix>_ENTITY AS
SELECT <entity_key>, <key fields>, HAS_<TYPE1>, HAS_<TYPE2>, <RISK>, ROUTE, MIN_KEY_CONF, INGESTED_AT
FROM <db>.<schema>.DT_<prefix>_ENTITY;   -- or DT_<prefix>_TRIAGED
```

Expose per-document detail (photo assessment, line items) as its own view if consumers need it; keep `RAW_*`
on the DTs for debugging.

---

## Corpus — per-document items + corpus profile

For corpus-intelligence, two surfaces: one row per document with its facts/theme/outlier flag, and a corpus
rollup (narrative + per-theme stats).

```sql
CREATE OR REPLACE VIEW <db>.<schema>.<prefix>_ITEMS AS
SELECT s.RELATIVE_PATH, s.TITLE, a.THEME, a.THEME_SIM, o.IS_OUTLIER,
       s.S_<FACET1>, s.S_<FACET2>   -- your facet columns + extracted fields / time key as composed
FROM <db>.<schema>.DT_<prefix>_SUMMARIZED s
LEFT JOIN <db>.<schema>.DT_<prefix>_THEME_ASSIGN a USING (RELATIVE_PATH)
LEFT JOIN <db>.<schema>.DT_<prefix>_OUTLIERS o USING (RELATIVE_PATH);

CREATE OR REPLACE VIEW <db>.<schema>.<prefix>_PROFILE AS
SELECT
  (SELECT CORPUS_NARRATIVE FROM <db>.<schema>.DT_<prefix>_SYNTHESIS LIMIT 1) AS CORPUS_NARRATIVE,
  THEME, COUNT(*) AS N_ITEMS, ROUND(AVG(THEME_SIM),3) AS AVG_COHESION
FROM <db>.<schema>.DT_<prefix>_THEME_ASSIGN
GROUP BY THEME;
```

---

## Search / analytical surfaces

- **Search** — the deliverable is the `<prefix>_SEARCH` service itself (no view); query it with
  [`../search/rag-answer.md`](../search/rag-answer.md).
- **Analytical** — `<prefix>_METRICS` (thin view over the metrics DT) and `<prefix>_INSIGHTS` (one row per
  insight) are created in [`../analyze/metrics-trend.md`](../analyze/metrics-trend.md) and
  [`../analyze/synthesize.md`](../analyze/synthesize.md).

For a no-SQL reading/search app over any of these, see [`presentation.md`](presentation.md).
