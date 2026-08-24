# Example — Claims intake (worked composition)

**Scenario:** Documents for auto-insurance claims land on a stage **mixed together** — and intermixed
with non-claim junk. Each claim is a *packet* of up to four document types that share a claim number:
a **first-notice-of-loss** form (claimant, policy, date of loss, amount claimed, loss narrative, fault
from the insured's view), a **repair estimate** (shop, totals), a **police report** (official fault
determination, narrative), and a **damage photo**. The police report and photo are often absent. You
want to sort each file to the right extractor, reassemble the packet into **one record per claim**, and
route each claim to **auto-settle / needs-review / reject** — with a fraud-risk flag and a settlement
estimate. The signal that drives the routing isn't in any single document; it surfaces only when the
documents are **compared against each other** (estimate vs. amount claimed, photo severity vs. the
claimed loss, the two fault determinations, a high-value claim with no police report).

This is the **reference composition** — when in doubt start here, then drop or add blocks for the case
at hand. It shows how blocks wire together; the SQL bodies live in the shared palette ([`../../../blocks/README.md`](../../../blocks/README.md)) — spine in `ingest/*`, `extract/*`, `records/entity.md`; decision + triage in [`records/reason.md`](../../../blocks/records/reason.md) and [`records/triage.md`](../../../blocks/records/triage.md).

**Worked names:** `db=ACME`, `schema=CLAIMS`, `<prefix>=CLM`, `stage=CLAIMS_STAGE`, `warehouse=CLAIMS_WH`.
Swap in the user's own. Document types: `fnol`, `estimate`, `police` (text) and `photo` (image); the
entity key `CLAIM_NO` is encoded in each filename.

## Blocks, in build order

| # | Block (palette) | Object(s) it creates | Grain | Composition note |
|---|---------------------------|----------------------|-------|------------------|
| 1 | Ingestion | stage, `CLM_FILE_LOG`, `CLM_STAGE_STREAM`, `CLM_INGEST_TASK` | — | multi-modality extension filter (`.pdf`, `.jpg`); seed the backlog (base Step 4) |
| 2 | Parse / OCR | `DT_CLM_PARSED` | per-doc | `mode = LAYOUT`, **PDFs only**; derives `CLAIM_NO` from the path |
| 3 | Router | `DT_CLM_CLASSIFIED` | per-doc | text arm classifies PDFs → `{fnol, estimate, police, other}`; image arm assigns `photo` by modality |
| 4 | Routed extractor — `fnol` | `DT_CLM_FNOL` | per-doc | reads `WHERE DOC_TYPE = 'fnol'`; `scores => TRUE` for a confidence signal |
| 5 | Routed extractor — `estimate` | `DT_CLM_ESTIMATE` | per-doc | reads `WHERE DOC_TYPE = 'estimate'` |
| 6 | Routed extractor — `police` | `DT_CLM_POLICE` | per-doc | reads `WHERE DOC_TYPE = 'police'`; carries the police fault determination |
| 7 | Vision extractor — `photo` | `DT_CLM_PHOTO` | per-doc | reads `WHERE DOC_TYPE = 'photo'`; `AI_COMPLETE` vision → severity, area, repairable |
| 8 | Entity assembly | `DT_CLM_CLAIM` | per-claim | spine + four `LEFT JOIN`s on `CLAIM_NO`; `HAS_*` flags + cross-document signals |
| 9 | Cross-document decision | `DT_CLM_DECISION` | per-claim | `AI_COMPLETE` over the packet → fraud risk, reasons, settlement, suggested action |
| 10 | Triage & lanes | `DT_CLM_TRIAGED` (+ lane views) | per-claim | deterministic `ROUTE`; terminal DT takes the user lag |
| 11 | Final shape | views `CLM_CLAIM`, `CLM_AUTO_SETTLE`, `CLM_NEEDS_REVIEW`, `CLM_REJECT` | views | curated per-claim record + one view per lane |

**DAG:**

```
@CLAIMS_STAGE → CLM_STAGE_STREAM + CLM_INGEST_TASK → CLM_FILE_LOG
  → DT_CLM_PARSED → DT_CLM_CLASSIFIED                                   [per-doc · INCREMENTAL]
        ├ WHERE DOC_TYPE='fnol'     → DT_CLM_FNOL
        ├ WHERE DOC_TYPE='estimate' → DT_CLM_ESTIMATE
        ├ WHERE DOC_TYPE='police'   → DT_CLM_POLICE
        └ WHERE DOC_TYPE='photo'    → DT_CLM_PHOTO
              → DT_CLM_CLAIM  (LEFT JOIN all four on CLAIM_NO)          [per-claim · INCREMENTAL]
                  → DT_CLM_DECISION → DT_CLM_TRIAGED
                      → CLM_CLAIM · CLM_AUTO_SETTLE · CLM_NEEDS_REVIEW · CLM_REJECT   [views]
```

## How the blocks wire

- **The router establishes `DOC_TYPE` across two modalities.** PDFs are classified from their parsed
  text; images are typed by extension in the same DT via `UNION ALL`. Each extractor reads its own
  `DOC_TYPE` slice, so AI only ever fires on the right documents — and the junk that lands in `other` is
  selected by no extractor, which is the gate.
- **The path key is derived once and carried forward.** `CLAIM_NO` is parsed from the filename at the
  Parse layer, not from document content — it's the only handle on the photo (which prints no claim
  number) and it is the join key for assembly.
- **Assembly is the grain shift.** Everything from Parse through the extractors is **per-document**;
  `DT_CLM_CLAIM` and everything below it are **per-claim**. The spine (`DISTINCT CLAIM_NO`, excluding
  `other`) defines the claim universe, and `LEFT JOIN` lets a claim survive with the police report or
  photo missing — `HAS_*` flags record what was present.
- **Cross-document signals are computed at assembly**, so the decision and triage layers read clean
  columns instead of recomputing — e.g. amount-to-estimate ratio, a fault-contradiction flag (FNOL vs.
  police), and the maximum dollar exposure.
- **Decision reasons; triage decides.** `DT_CLM_DECISION` asks `AI_COMPLETE` for a judgment over the
  whole packet (fraud risk, settlement, reasons). `DT_CLM_TRIAGED` then assigns the lane with
  **deterministic** SQL over the decision plus the extraction-confidence and presence columns — including
  a conservative escalation (a high-value claim missing its police report goes to review, never auto).

## Build & verify

Create blocks #1–#11 in order — the ingest task stays **suspended**. Downstream DTs only compile once
their upstream exists, so build the chain in dependency order, compiling each before creating it.

Then verify every `DT_CLM_*` reports `refresh_mode = 'INCREMENTAL'` before trusting results (base Step 6
— stop and fix any `FULL`). Two spots to watch: the router's `UNION ALL` and the four-way `LEFT JOIN` in
assembly both stay incremental when AI is called inline and joins key on `CLAIM_NO`. Smoke-check the
distinctive layers: the classification distribution is plausible and junk landed in `other`; the claim
count and `HAS_*` flags match the expected document mix with core identifying fields populated; the
`ROUTE` distribution is sane and the auto-settle lane holds nothing obviously bad.

For freshness, set the user's target lag (default 5 minutes) on `DT_CLM_TRIAGED` (the terminal DT) and
leave every other DT `TARGET_LAG = DOWNSTREAM`; they refresh transitively, and the views inherit (base
Step 7). Once `INCREMENTAL` is verified and the smoke checks pass, **resume `CLM_INGEST_TASK` last** to
go live (base Step 9).

## What the lanes buy you

A first-pass decision on every claim without a person opening each packet — an auto-settle rate, the
value sitting in each lane, and a review queue ordered by risk:

```sql
-- how the book splits, and the money in each lane
SELECT ROUTE, COUNT(*) AS CLAIMS, ROUND(SUM(SETTLEMENT_ESTIMATE)) AS SETTLE_DOLLARS
FROM ACME.CLAIMS.CLM_CLAIM
GROUP BY ROUTE ORDER BY SETTLE_DOLLARS DESC;

-- the review queue: highest-risk claims first, with the reasons attached
SELECT CLAIM_NO, FRAUD_RISK, FRAUD_REASONS, MAX_DOLLAR_EXPOSURE, RATIONALE
FROM ACME.CLAIMS.CLM_NEEDS_REVIEW
ORDER BY REVIEW_PRIORITY, MAX_DOLLAR_EXPOSURE DESC NULLS LAST;
```

Routing on the deterministic triage rules rather than the model's say-so keeps the auto-settle lane
conservative: anything with a fraud signal, shaky extraction, a missing key document on a large claim,
or a big-ticket total falls to review instead of being paid automatically. The thresholds (confidence
cutoff, dollar ceilings) are the control surface — start tight and loosen as extraction proves out.

## Teardown

Dependency-safe order for exactly the objects above. **These `DROP`s are irreversible — present them and get explicit user approval before running any** (full rule + gate in [`../SKILL.md`](../SKILL.md) § Teardown):

```sql
ALTER TASK ACME.CLAIMS.CLM_INGEST_TASK SUSPEND;          -- stop ingestion first

DROP VIEW IF EXISTS ACME.CLAIMS.CLM_AUTO_SETTLE;         -- user-facing views (read the DTs)
DROP VIEW IF EXISTS ACME.CLAIMS.CLM_NEEDS_REVIEW;
DROP VIEW IF EXISTS ACME.CLAIMS.CLM_REJECT;
DROP VIEW IF EXISTS ACME.CLAIMS.CLM_CLAIM;

DROP DYNAMIC TABLE IF EXISTS ACME.CLAIMS.DT_CLM_TRIAGED;   -- per-claim DTs, newest → oldest
DROP DYNAMIC TABLE IF EXISTS ACME.CLAIMS.DT_CLM_DECISION;
DROP DYNAMIC TABLE IF EXISTS ACME.CLAIMS.DT_CLM_CLAIM;
DROP DYNAMIC TABLE IF EXISTS ACME.CLAIMS.DT_CLM_PHOTO;     -- per-document extractors
DROP DYNAMIC TABLE IF EXISTS ACME.CLAIMS.DT_CLM_POLICE;
DROP DYNAMIC TABLE IF EXISTS ACME.CLAIMS.DT_CLM_ESTIMATE;
DROP DYNAMIC TABLE IF EXISTS ACME.CLAIMS.DT_CLM_FNOL;
DROP DYNAMIC TABLE IF EXISTS ACME.CLAIMS.DT_CLM_CLASSIFIED;
DROP DYNAMIC TABLE IF EXISTS ACME.CLAIMS.DT_CLM_PARSED;

DROP TASK   IF EXISTS ACME.CLAIMS.CLM_INGEST_TASK;       -- task, then stream, then file log
DROP STREAM IF EXISTS ACME.CLAIMS.CLM_STAGE_STREAM;
DROP TABLE  IF EXISTS ACME.CLAIMS.CLM_FILE_LOG;

-- Leave @CLAIMS_STAGE in place — that's the user's documents.
```

(Conventions — `INCREMENTAL`-safety, target-lag policy, monitoring — are base-owned: see
[`../../../references/multi-step-pipeline.md`](../../../references/multi-step-pipeline.md).)
