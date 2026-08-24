# Validate — reconcile & match (deterministic, no AI)

Deterministic record-level checks: **reconcile** an extracted total against its parts, and **match** an
extracted name to a master/reference table. Both are pure SQL over already-extracted columns — no AI, cheap,
incremental.

> Read [`../conventions.md`](../conventions.md) first — shapes, refresh contract, placeholders.

---

## Totals reconciliation — do the parts sum to the whole?

- **When** — line items (or sub-amounts) must be checked against a header total (the signature AP check).
- **Reads** — a `TYPED_FIELDS` header (`<total>`) + a line-items table (`<amount>`).
- **Produces** — `DT_<prefix>_RECONCILED` (header columns + `RECON_STATUS, RECON_DISCREPANCY, RECON_DISCREPANCY_PCT`).
- **Refresh** — **INCREMENTAL**.
- **Typical upstreams** — `extract/fields.md` (typed header + line items).

Tri-state, because "couldn't check" (no line items, or a null total) is not the same as "checked and passed":

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_RECONCILED
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL
AS
WITH sums AS (
  SELECT RELATIVE_PATH, SUM(AMOUNT) AS COMPUTED_LINE_SUM
  FROM <db>.<schema>.DT_<prefix>_LINE_ITEMS GROUP BY RELATIVE_PATH
)
SELECT
  h.*,                                                          -- carries the typed header forward
  s.COMPUTED_LINE_SUM,
  CASE
    WHEN h.TOTAL_AMOUNT IS NULL OR s.COMPUTED_LINE_SUM IS NULL THEN 'unknown'
    WHEN ABS(h.TOTAL_AMOUNT - s.COMPUTED_LINE_SUM) <= 0.01      THEN 'pass'
    ELSE 'fail'
  END AS RECON_STATUS,
  IFF(h.TOTAL_AMOUNT IS NOT NULL AND s.COMPUTED_LINE_SUM IS NOT NULL,
      ABS(h.TOTAL_AMOUNT - s.COMPUTED_LINE_SUM), NULL) AS RECON_DISCREPANCY,
  IFF(h.TOTAL_AMOUNT IS NOT NULL AND s.COMPUTED_LINE_SUM IS NOT NULL AND h.TOTAL_AMOUNT <> 0,
      ROUND(ABS(h.TOTAL_AMOUNT - s.COMPUTED_LINE_SUM) / h.TOTAL_AMOUNT * 100, 2), NULL) AS RECON_DISCREPANCY_PCT
FROM <db>.<schema>.DT_<prefix>_EXTRACTED h
LEFT JOIN sums s USING (RELATIVE_PATH);
```

> **Quarantine** — to hold failures back instead of flagging, expose a view filtered on `RECON_STATUS = 'fail'`
> and have the final header view read `WHERE RECON_STATUS <> 'fail'`. Need more checks (future-dated,
> required-fields, duplicates)? Add them as extra `CASE` flag columns here.

---

## Fuzzy master match — canonicalize a name to a reference table

- **When** — the user has a master (vendor / customer / product) and wants extracted names canonicalized to its IDs.
- **Reads** — the terminal header-grain DT (`VENDOR_NAME` or similar) + the user's master table.
- **Produces** — `DT_<prefix>_VENDOR_MATCHED` (+ `VENDOR_ID, MATCH_NAME, SIM`).
- **Refresh** — **INCREMENTAL** (`ROW_NUMBER` + `CROSS JOIN` to a small static table is incremental-eligible).
- **Typical upstreams** — `extract/fields.md`, or this file's reconciliation above.

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_VENDOR_MATCHED
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL
AS
WITH scored AS (
  SELECT
    v.*, m.VENDOR_ID, m.VENDOR_NAME AS MATCH_NAME,
    JAROWINKLER_SIMILARITY(UPPER(v.VENDOR_NAME), UPPER(m.VENDOR_NAME)) AS SIM,
    ROW_NUMBER() OVER (PARTITION BY v.RELATIVE_PATH ORDER BY SIM DESC) AS RN
  FROM <db>.<schema>.DT_<prefix>_RECONCILED v   -- or DT_<prefix>_EXTRACTED if reconciliation wasn't composed
  CROSS JOIN <user master table> m
)
SELECT * FROM scored WHERE RN = 1 AND SIM >= 80;
```

> 80 is a starting threshold — tune on sample data. For rows below threshold, optionally feed the top-3
> candidates to `AI_FILTER` for a semantic tie-break. Skip the whole block if there is no master.
