# Example — Invoice triage & fan-out (routing after extraction)

**Scenario:** You've built `basic.md` and want to **route** each extracted invoice to a lane — auto-approve,
human review, or reject — and fan it out to a per-lane view. This is the "what happens after extraction"
layer, and a worked instance of **writing your own block** (see [`../../../blocks/conventions.md`](../../../blocks/conventions.md)): pure SQL
over the terminal DT, no new AI calls, fully incremental.

**Prereq:** build [`basic.md`](./basic.md) first, so `DT_INV_RECONCILED` exists with `RECON_STATUS`,
`RECON_DISCREPANCY_PCT`, and the typed header columns. No new `CHANGE_TRACKING` — triage reads a dynamic table.

**Worked names:** as in `basic.md` (`ACME.AP`, `<prefix>=INV`, `warehouse=AP_WH`), plus
`<auto_approve_ceiling>` (e.g. `1000`).

**DAG (the triage tail):**

```
DT_INV_RECONCILED → DT_INV_TRIAGED → { INV_AUTO_APPROVE, INV_NEEDS_REVIEW, INV_REJECTED }
```

```sql
/* Triage — assign a routing lane with deterministic rules over the reconciled header */
CREATE OR REPLACE DYNAMIC TABLE ACME.AP.DT_INV_TRIAGED
  TARGET_LAG = '5 minutes'   -- new terminal DT takes the user lag; revert DT_INV_RECONCILED to DOWNSTREAM (base Step 7)
  WAREHOUSE  = AP_WH
  REFRESH_MODE = INCREMENTAL
AS
SELECT
  v.*,
  CASE
    WHEN v.INVOICE_NUMBER IS NULL
      OR v.TOTAL_AMOUNT IS NULL
      OR v.INVOICE_DATE IS NULL                  THEN 'reject'         -- unprocessable → send back for re-scan
    WHEN v.RECON_STATUS IN ('fail', 'unknown')   THEN 'needs_review'   -- totals don't add up / couldn't check
    WHEN v.TOTAL_AMOUNT > <auto_approve_ceiling> THEN 'needs_review'   -- big-ticket → eyes required
    ELSE 'auto_approve'                                                -- clean, reconciled, under the ceiling
  END AS ROUTE,
  CASE                                                                 -- reviewer queue: biggest risk first
    WHEN v.RECON_STATUS = 'fail'                 THEN 1
    WHEN v.RECON_DISCREPANCY_PCT >= 5            THEN 2
    WHEN v.TOTAL_AMOUNT > <auto_approve_ceiling> THEN 3
    ELSE 4
  END AS REVIEW_PRIORITY
FROM ACME.AP.DT_INV_RECONCILED v;

/* Fan-out — one view per lane */
CREATE OR REPLACE VIEW ACME.AP.INV_AUTO_APPROVE AS
SELECT * FROM ACME.AP.DT_INV_TRIAGED WHERE ROUTE = 'auto_approve';

CREATE OR REPLACE VIEW ACME.AP.INV_NEEDS_REVIEW AS
SELECT * FROM ACME.AP.DT_INV_TRIAGED WHERE ROUTE = 'needs_review'
ORDER BY REVIEW_PRIORITY, RECON_DISCREPANCY_PCT DESC NULLS LAST;

CREATE OR REPLACE VIEW ACME.AP.INV_REJECTED AS
SELECT * FROM ACME.AP.DT_INV_TRIAGED WHERE ROUTE = 'reject';
```

## Why DT-native instead of a task fan-out

Each lane is a filtered view over one incremental DT, so routing recomputes automatically as new invoices
land — no orchestration, no second task, no copy of the data. Counts per lane are one query:

```sql
SELECT ROUTE, COUNT(*) AS N, SUM(TOTAL_AMOUNT) AS DOLLARS
FROM ACME.AP.DT_INV_TRIAGED
GROUP BY ROUTE ORDER BY DOLLARS DESC;
```

## Adapting the routing

- **Route on confidence or derived priority** — if you composed the scored Header extract or the Reason /
  derive block ([`../../../blocks/records/reason.md`](../../../blocks/records/reason.md)), read their columns here: e.g. `WHEN v.LOW_CONFIDENCE THEN 'needs_review'`, or
  order the review queue by `v.PRIORITY_SCORE DESC`. Read `FROM DT_INV_ANALYZED` when that block is terminal.
- **Add an approver dimension** — band `auto_approve` by `TOTAL_AMOUNT` and join a vendor / cost-center table
  to set the approver, all inside the triage DT.
- **Push out of Snowflake** — emitting to Slack / email / an ERP from `INV_NEEDS_REVIEW` needs
  `EXTERNAL ACCESS` and is out of scope here; surface the lane as a view and let the external system poll it.
- **Tune the ceiling** — `<auto_approve_ceiling>` is the single biggest control; start conservative and raise
  it as you come to trust extraction quality.

(Conventions — `INCREMENTAL`-safety, target-lag policy — are base-owned: see
[`../../../references/multi-step-pipeline.md`](../../../references/multi-step-pipeline.md).)
