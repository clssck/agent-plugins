# Example — AP spend analytics (worked composition)

**Scenario:** A stream of vendor **invoices** (one document type) lands on a stage. You don't want to act
on each invoice — you want to turn the flow into a **reporting corpus**: spend by category over time,
concentration and trend, payment-term patterns, and a short ranked list of **recommended actions**
(consolidate a category, renegotiate a vendor, standardize payment terms). This is the **analytical head**
on a single-type extraction spine — no routing, no per-entity decision.

This is the reference composition for the analytical head — when in doubt start here, then drop or add
blocks. The SQL bodies live in the shared palette ([`../../../blocks/README.md`](../../../blocks/README.md)) — spine
in `extract/*`, metrics + insights in [`analyze/metrics-trend.md`](../../../blocks/analyze/metrics-trend.md) and
[`analyze/synthesize.md`](../../../blocks/analyze/synthesize.md) — so this file stays a recipe and can't drift
from the palette.

**Worked names:** `db=ACME`, `schema=AP`, `<prefix>=AP`, `stage=INVOICE_STAGE`, `warehouse=AP_WH`. One
document type (`invoice`); dimension is a **derived** spend category; measure is the invoice total; time
key is the invoice date.

## Blocks, in build order

| # | Block (palette) | Object(s) it creates | Grain | Composition note |
|---|---------------------------|----------------------|-------|------------------|
| 1 | Ingestion | stage, `AP_FILE_LOG`, `AP_STAGE_STREAM`, `AP_INGEST_TASK` | — | `.jpg`/`.pdf` filter; seed the backlog (base Step 4) |
| 2 | Routed extractor (single type) | `DT_AP_EXTRACTED` | per-doc · INCREMENTAL | `AI_EXTRACT` (image/file) → seller, invoice_date, due_date, total, line-items + `PAYMENT_TERM_DAYS`; `scores => TRUE` → `MIN_KEY_CONF`. No Router (one type), no assembly (one invoice = one entity) |
| 3 | Categorize / derive — *inline, not a palette block* | `DT_AP_CATEGORIZED` | per-doc · INCREMENTAL | `AI_CLASSIFY(seller + line items)` → `SPEND_CATEGORY`. Built inline as your own block per the Metrics-rollup guidance in [`../../../blocks/analyze/metrics-trend.md`](../../../blocks/analyze/metrics-trend.md) (raw vendor is near-unique → derive a groupable dimension) |
| 4 | Metrics rollup | `DT_AP_METRICS` (+ view `AP_METRICS`) | aggregate · FULL | `period × SPEND_CATEGORY` → totals, `PERIOD_SHARE_PCT`, YoY, + `AVG_TERM_DAYS` (added — see column note below); **a DT, not a view** (the Insights DT reads it) |
| 5 | Insights & actions | `DT_AP_INSIGHTS` | aggregate · FULL | one `AI_COMPLETE` over the metric rows → `{observation, evidence, recommended_action, priority}` + exec summary |
| 6 | Final shape | views `AP_METRICS`, `AP_INSIGHTS` | views | per-period metrics + one row per insight |

**DAG:**

```
@INVOICE_STAGE → AP_STAGE_STREAM + AP_INGEST_TASK → AP_FILE_LOG
  → DT_AP_EXTRACTED → DT_AP_CATEGORIZED                         [per-doc · INCREMENTAL]
      → DT_AP_METRICS (period × category)                       [aggregate · FULL]
          → DT_AP_INSIGHTS → AP_METRICS · AP_INSIGHTS  [views]
```

## How the blocks wire

- **Single type collapses the spine.** No Router and no Entity assembly: each invoice *is* the entity, so
  the extractor's output is the per-entity record the analytical head reads.
- **Derive the dimension — don't trust the vendor.** Seller names are near-unique (≈one invoice per
  vendor), so they can't be trended. `AI_CLASSIFY` turns seller + line items into a fixed `SPEND_CATEGORY`
  with enough rows per bucket to aggregate.
- **The grain shift is per-entity → aggregate.** Extract and Categorize stay **`INCREMENTAL`** (AI fires
  per new invoice); Metrics and Insights are **`FULL`** — they roll up every record but are cheap (no file
  re-reads). `DT_AP_METRICS` must be a **dynamic table**, not a view, because the Insights DT reads it and
  *a DT cannot read a view that wraps a DT*.
- **Metrics run on the validated slice.** The rollup filters `MIN_KEY_CONF >= <cutoff>` so shaky
  extractions don't pollute the numbers. Image extraction scores lower than text — calibrate the cutoff
  down (~0.5).
- **Insights reduce over the metric rows, not the documents** — one `AI_COMPLETE` over the aggregated
  `period × category` rows, returning ranked actions and an exec summary.

## Build & verify

Create blocks #1–#6 in order — the ingest task stays **suspended**. Verify refresh modes (base Step 6):
`DT_AP_EXTRACTED` and `DT_AP_CATEGORIZED` are **`INCREMENTAL`**; `DT_AP_METRICS` and `DT_AP_INSIGHTS` are
**expected `FULL`** (don't "fix" them). `DT_AP_INSIGHTS` is `INITIALIZE = ON_SCHEDULE`, so refresh it once
manually (and its upstream) before reading. Smoke-check the distinctive layers:

- **Extraction**: core fields populated; inspect the `MIN_KEY_CONF` spread to set the cutoff.
- **Density first**: `SELECT MIN(invoice_date), MAX(invoice_date), COUNT(DISTINCT period)` — if dates are
  sparse/random, **coarsen the grain** (quarter → year) or lean on **level/mix** (share, totals, payment
  terms); don't force QoQ on one invoice per cell.
- **Category distribution** is plausible; `(uncategorized)` is a small minority.
- **Insights**: `DT_AP_INSIGHTS` returns a non-empty set with a recommended action each, and `GEN_ERROR`
  is NULL (if it reports an over-context error, switch the Insights block to its map-reduce form).

For freshness, set the user's reporting cadence on `DT_AP_INSIGHTS` (e.g. `1 day`) and leave upstream DTs
`DOWNSTREAM`. Once verified, **resume `AP_INGEST_TASK` last** to go live (base Step 9).

## What the insights buy you

A standing answer to "where is spend going and what should we do" — without anyone reading invoices:

```sql
-- the ranked action list
SELECT PRIORITY, OBSERVATION, RECOMMENDED_ACTION
FROM ACME.AP.AP_INSIGHTS
ORDER BY CASE PRIORITY WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END;

-- the spend mix behind them
SELECT DIMENSION, ROUND(SUM(TOTAL_AMOUNT)) AS spend, SUM(DOC_COUNT) AS invoices, ROUND(AVG(AVG_TERM_DAYS),1) AS terms
FROM ACME.AP.AP_METRICS GROUP BY DIMENSION ORDER BY spend DESC;
```

> Column note: **`AVG_TERM_DAYS` is an
> invoice-specific measure this example adds** to `DT_AP_METRICS` (`ROUND(AVG(PAYMENT_TERM_DAYS),1)` in the
> `agg` CTE — invoices carry a due date, so payment terms are computable). Add such domain measures to the
> rollup alongside the defaults.

Because the synthesis reasons over the deterministic rollup, it stays honest about thin data — it will
call out a category whose "trend" rests on one or two invoices rather than inventing a story. Level/mix
and payment-term observations carry the value when the time axis is sparse; QoQ is the bonus when it isn't.

## Teardown

Dependency-safe order for exactly the objects above. **These `DROP`s are irreversible — present them and get explicit user approval before running any** (full rule + gate in [`../SKILL.md`](../SKILL.md) § Teardown):

```sql
ALTER TASK ACME.AP.AP_INGEST_TASK SUSPEND;               -- stop ingestion first

DROP VIEW IF EXISTS ACME.AP.AP_INSIGHTS;                 -- user-facing views
DROP VIEW IF EXISTS ACME.AP.AP_METRICS;

DROP DYNAMIC TABLE IF EXISTS ACME.AP.DT_AP_INSIGHTS;     -- aggregate-grain DTs
DROP DYNAMIC TABLE IF EXISTS ACME.AP.DT_AP_METRICS;
DROP DYNAMIC TABLE IF EXISTS ACME.AP.DT_AP_CATEGORIZED;  -- per-doc DTs, newest → oldest
DROP DYNAMIC TABLE IF EXISTS ACME.AP.DT_AP_EXTRACTED;

DROP TASK   IF EXISTS ACME.AP.AP_INGEST_TASK;            -- task, then stream, then file log
DROP STREAM IF EXISTS ACME.AP.AP_STAGE_STREAM;
DROP TABLE  IF EXISTS ACME.AP.AP_FILE_LOG;

-- Leave @INVOICE_STAGE in place — that's the user's documents.
```

(Conventions — `INCREMENTAL`-safety, target-lag policy, monitoring — are base-owned: see
[`../../../references/multi-step-pipeline.md`](../../../references/multi-step-pipeline.md).)
