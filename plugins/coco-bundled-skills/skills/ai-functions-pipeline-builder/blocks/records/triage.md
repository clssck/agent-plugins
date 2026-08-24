# Triage — route records to action lanes (deterministic, no AI)

The terminal of the operational head: a deterministic `CASE` ladder that routes each record to an action lane
(auto / review / reject), then filtered views per lane. Pure SQL over the decision + confidence + presence
columns — the thresholds are your control surface.

> Read [`../conventions.md`](../conventions.md) first — shapes, refresh contract, placeholders.

- **When** — you route each record to action lanes. Skip for analytical-only pipelines (no per-record action).
- **Reads** — `DECISION` (`DT_<prefix>_DECISION`) — risk, suggested action, derived signals, `MIN_KEY_CONF`, `HAS_*`.
- **Produces** — `ROUTED`: `DT_<prefix>_TRIAGED` (+ `ROUTE`, `REVIEW_PRIORITY`); views `<prefix>_ENTITY` + one per lane.
- **Refresh** — **INCREMENTAL** (terminal DT → takes the user's `<final_lag>`; keep upstream DTs `DOWNSTREAM`).
- **Typical upstreams** — `records/reason.md`.

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_TRIAGED
  TARGET_LAG = '<final_lag>'  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL
AS
SELECT
  d.*,
  CASE                                                              -- first match wins; order = severity
    WHEN <core identifying fields are NULL>            THEN '<reject_lane>'   -- unprocessable
    WHEN d.<RISK> = 'high'                             THEN '<reject_lane>'
    WHEN d.<RISK> = 'medium'                           THEN '<review_lane>'
    WHEN d.<CONTRADICTION_FLAG>                        THEN '<review_lane>'
    WHEN COALESCE(d.MIN_KEY_CONF, 1) < <conf_cutoff>   THEN '<review_lane>'   -- shaky extraction (cutoff ≈ 0.6; calibrate)
    WHEN d.<SUGGESTED_ACTION> <> '<auto_lane>'         THEN '<review_lane>'
    WHEN d.<MAX_EXPOSURE> > <ceiling>                  THEN '<review_lane>'   -- big-ticket
    WHEN (NOT d.HAS_<TYPE3>) AND d.<MAX_EXPOSURE> > <low_ceiling> THEN '<review_lane>'  -- conservative escalation on a missing doc
    ELSE '<auto_lane>'
  END AS ROUTE,
  CASE WHEN d.<RISK> = 'high' THEN 1 WHEN d.<RISK> = 'medium' THEN 2
       WHEN d.<CONTRADICTION_FLAG> THEN 3 WHEN d.<MAX_EXPOSURE> > <ceiling> THEN 4 ELSE 5 END AS REVIEW_PRIORITY
FROM <db>.<schema>.DT_<prefix>_DECISION d;

CREATE OR REPLACE VIEW <db>.<schema>.<prefix>_ENTITY        AS SELECT <curated cols> FROM <db>.<schema>.DT_<prefix>_TRIAGED;
CREATE OR REPLACE VIEW <db>.<schema>.<prefix>_<AUTO_LANE>   AS SELECT * FROM <db>.<schema>.<prefix>_ENTITY WHERE ROUTE = '<auto_lane>';
CREATE OR REPLACE VIEW <db>.<schema>.<prefix>_<REVIEW_LANE> AS SELECT * FROM <db>.<schema>.<prefix>_ENTITY WHERE ROUTE = '<review_lane>'
  ORDER BY REVIEW_PRIORITY, <MAX_EXPOSURE> DESC NULLS LAST;
CREATE OR REPLACE VIEW <db>.<schema>.<prefix>_<REJECT_LANE> AS SELECT * FROM <db>.<schema>.<prefix>_ENTITY WHERE ROUTE = '<reject_lane>';
```

- The ladder is **first-match-wins**; lead with the hardest stops (unprocessable, high risk).
- **Conservative escalation** — a high-value record with a key document missing escalates to review, not
  auto-pass (the `NOT HAS_<TYPE3>` clause). Encode it explicitly.
- **NULL-guard every arm reading a column from an absent record.** Per-type fields arrive via `LEFT JOIN` and are `NULL` when missing — `NOT <col>` or `<col> <> '…'` on NULL yields NULL. Gate "record absent" on `NOT HAS_<X>`; gate "record present but field is no" on `HAS_<X> AND <col> = '<no-value>'`. Never write a bare `NOT <field>` against a possibly-NULL joined column.
- **Canonicalize extracted enum/boolean fields before branching.** A model often returns a phrase (`"confirmed"`) rather than the expected token (`"yes"`). Enforce the shape at extraction time with a JSON-schema `enum`/`boolean` or a `CASE`/`ILIKE` normalization layer — a routing ladder that string-compares raw model prose will mis-route wholesale when the model paraphrases.
- The thresholds (`<conf_cutoff>`, `<ceiling>`, `<low_ceiling>`) are the main control surface — start
  conservative (favor recall / never auto-pass risk) and loosen as you trust extraction quality.
- **The auto lane is the default destination.** Reserve the review lane for a concrete signal: cross-document discrepancy, failed reconciliation, genuinely low confidence, or a missing required document. Records with no such signal fall through to the `ELSE` auto branch. A raw dollar magnitude is a weak trigger — layer it on top of an actual discrepancy. Start conservative on the risk/reject arms; don't start conservative by widening the review arm.
- Lanes are filtered **views** over the one terminal DT — no second task, no data copy; they recompute as new
  records land. (For a single-doc operational pipeline with no entity assembly, this reads `DECISION` rows
  keyed on `RELATIVE_PATH` instead of `<entity_key>` — same ladder.)
