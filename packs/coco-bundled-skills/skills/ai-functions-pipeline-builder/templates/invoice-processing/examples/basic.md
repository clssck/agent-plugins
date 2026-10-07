# Example — Standard AP pipeline (worked composition)

**Scenario:** Mixed accounting documents (invoices, statements, POs) land on a stage. Gate out the
non-invoices, extract the header fields and a separate line-items table, reconcile each invoice's line items
against its header total, and expose a split `_HEADER` + `_LINE_ITEMS` deliverable.

This is the **reference composition** — when in doubt start here, then drop or add blocks for the case at
hand. It shows how blocks wire together; the SQL bodies live in the shared palette, indexed by
[`../../../blocks/README.md`](../../../blocks/README.md), so this file stays a recipe and can't drift from it.

**Worked names:** `db=ACME`, `schema=AP`, `<prefix>=INV`, `stage=INVOICE_STAGE`, `warehouse=AP_WH`. Swap in
the user's own.

## Blocks, in build order

| # | Block (in the palette) | Object(s) it creates | Composition note |
|---|---------------------------|----------------------|------------------|
| 1 | Ingestion | stage, `INV_FILE_LOG`, `INV_STAGE_STREAM`, `INV_INGEST_TASK` | default `.pdf` extension filter |
| 2 | Parse / OCR | `DT_INV_PARSED` | `mode = LAYOUT` |
| 3 | Gate → invoice | `DT_INV_CLASSIFIED` | adds `DOC_TYPE` |
| 4 | Header extract | `DT_INV_EXTRACTED` | reads `DT_INV_CLASSIFIED` `WHERE DOC_TYPE = 'invoice'` |
| 5 | Line items + flatten | `DT_INV_EXTRACTED_LINES` → `DT_INV_LINE_ITEMS` (+ view `INV_LINE_ITEMS`) | same gated source as #4 |
| 6 | Totals reconciliation | `DT_INV_RECONCILED` | joins `DT_INV_EXTRACTED` + `DT_INV_LINE_ITEMS`; terminal header DT |
| 7 | Final shape (split) | views `INV_HEADER`, `INV_LINE_ITEMS` | header view reads `DT_INV_RECONCILED` |

**DAG:**

```
@INVOICE_STAGE → INV_STAGE_STREAM + INV_INGEST_TASK → INV_FILE_LOG
  → DT_INV_PARSED → DT_INV_CLASSIFIED
      → { DT_INV_EXTRACTED,  DT_INV_EXTRACTED_LINES → DT_INV_LINE_ITEMS }
      → DT_INV_RECONCILED → INV_HEADER  (+ INV_LINE_ITEMS)
```

## How the blocks wire

- **Gate establishes `DOC_TYPE`.** Both extract blocks (#4, #5) read `FROM DT_INV_CLASSIFIED … WHERE
  DOC_TYPE = 'invoice'`, so `AI_EXTRACT` never fires on the gated-out documents.
- **No Translate** in this composition, so the extracts read `PARSED_TEXT` (not `PARSED_TEXT_EN`).
- **Reconciliation is the join point.** `DT_INV_RECONCILED` `LEFT JOIN`s the header (`DT_INV_EXTRACTED`)
  to the per-file `SUM(AMOUNT)` of `DT_INV_LINE_ITEMS`, carrying the typed header forward — so it is the
  terminal header-grain DT.
- **Final shape** reads that terminal DT for `INV_HEADER`; `INV_LINE_ITEMS` is the view created by block #5.

## Build & verify

Create blocks #1–#7 in order — the ingest task stays **suspended** — then verify every
`DT_INV_*` reports `refresh_mode = 'INCREMENTAL'` before trusting results (base Step 6 — stop and fix any
`FULL`). For freshness, set the user's target lag on `DT_INV_RECONCILED` (the terminal DT) and leave every
other DT `TARGET_LAG = DOWNSTREAM`; they refresh transitively to satisfy it, and the two views inherit from
their DTs (base Step 7). Once `INCREMENTAL` is verified and the pipeline is tested, **resume `INV_INGEST_TASK`
last** to go live (base Step 9).

## What reconciliation buys you

Triage by money at risk, not a yes/no flag:

```sql
SELECT RELATIVE_PATH, INVOICE_NUMBER, VENDOR_NAME, TOTAL_AMOUNT,
       RECON_STATUS, RECON_DISCREPANCY, RECON_DISCREPANCY_PCT
FROM ACME.AP.INV_HEADER
WHERE RECON_STATUS <> 'pass'
ORDER BY RECON_DISCREPANCY_PCT DESC NULLS LAST;
```

A plain boolean check would pass every `unknown` (e.g. flat-fee invoices with no line items) silently. The
tri-state `pass` / `fail` / `unknown` plus the magnitude columns let a reviewer sort by money at risk and
skip the legitimately line-item-free invoices.

## Teardown

Dependency-safe order for exactly the objects above. **These `DROP`s are irreversible — present them and get explicit user approval before running any** (full rule + gate in [`../SKILL.md`](../SKILL.md) § Teardown):

```sql
ALTER TASK ACME.AP.INV_INGEST_TASK SUSPEND;          -- stop ingestion first

DROP VIEW IF EXISTS ACME.AP.INV_HEADER;              -- user-facing views (read the DTs)
DROP VIEW IF EXISTS ACME.AP.INV_LINE_ITEMS;

DROP DYNAMIC TABLE IF EXISTS ACME.AP.DT_INV_RECONCILED;       -- DTs, newest → oldest
DROP DYNAMIC TABLE IF EXISTS ACME.AP.DT_INV_LINE_ITEMS;
DROP DYNAMIC TABLE IF EXISTS ACME.AP.DT_INV_EXTRACTED_LINES;
DROP DYNAMIC TABLE IF EXISTS ACME.AP.DT_INV_EXTRACTED;
DROP DYNAMIC TABLE IF EXISTS ACME.AP.DT_INV_CLASSIFIED;
DROP DYNAMIC TABLE IF EXISTS ACME.AP.DT_INV_PARSED;

DROP TASK   IF EXISTS ACME.AP.INV_INGEST_TASK;       -- task, then stream, then file log
DROP STREAM IF EXISTS ACME.AP.INV_STAGE_STREAM;
DROP TABLE  IF EXISTS ACME.AP.INV_FILE_LOG;

-- Leave @INVOICE_STAGE (and any vendor master) in place — that's the user's data.
```

(Conventions — `INCREMENTAL`-safety, target-lag policy, monitoring — are base-owned: see
[`../../../references/multi-step-pipeline.md`](../../../references/multi-step-pipeline.md).)
