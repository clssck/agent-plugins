# Metrics & trend — roll records up into reporting numbers (deterministic, no AI)

Aggregate the validated records into `period × dimension` metrics — totals, QoQ trend, level/mix share, and
anomalies — plus a simple count-over-time trend. The grain shift from records to aggregate. No AI; a `FULL`
but cheap DT (it reads aggregated rows, never re-touches documents). Feeds [`synthesize.md`](synthesize.md).

> Read [`../conventions.md`](../conventions.md) first — shapes, refresh contract, the records→aggregate grain shift.

---

## Metrics rollup — period × dimension, QoQ, anomaly

- **When** — portfolio reporting: totals, QoQ trends, anomalies by category / type over time.
- **Reads** — a terminal per-record table (`ENTITY`, `ROUTED`, or a single extractor) — needs a **measure**, a
  **dimension**, and ideally a **date**.
- **Produces** — `METRIC`: `DT_<prefix>_METRICS` (`PERIOD, DIMENSION, TOTAL_*, *_COUNT, QOQ_GROWTH_PCT, PERIOD_SHARE_PCT, IS_ANOMALY`) + a thin `<prefix>_METRICS` serving view.
- **Refresh** — **FULL (cheap)**. ⚠ Must be a **DT, not a bare view**, when `synthesize.md` consumes it — a
  dynamic table **cannot read from a view that wraps a dynamic table**. If you build no Insights DT, a plain view is fine.
- **Typical upstreams** — `records/entity.md`, `records/triage.md`, or `extract/fields.md` + `extract/classify.md` (category-derive).

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_METRICS
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = FULL  INITIALIZE = ON_SCHEDULE
AS
WITH base AS (
  SELECT
    DATE_TRUNC('quarter', TRY_TO_DATE(<date_col>::STRING))     AS PERIOD,       -- TRY_, never trust the extractor
    COALESCE(NULLIF(LOWER(TRIM(<dimension>)), ''), '(uncategorized)') AS DIMENSION,  -- fold case+whitespace: LLM-emitted labels are inconsistently cased
    TRY_CAST(<amount_col>::STRING AS NUMBER(18,2))            AS AMOUNT
  FROM <db>.<schema>.DT_<prefix>_ENTITY
  WHERE COALESCE(MIN_KEY_CONF, 1) >= <conf_cutoff>      -- aggregate only the VALIDATED slice
    AND TRY_TO_DATE(<date_col>::STRING) IS NOT NULL     -- rows we can't place in time fall off the axis
    AND TRY_CAST(<amount_col>::STRING AS NUMBER(18,2)) IS NOT NULL
),
agg AS (
  SELECT PERIOD, DIMENSION, SUM(AMOUNT) AS TOTAL_AMOUNT, COUNT(*) AS DOC_COUNT, AVG(AMOUNT) AS AVG_AMOUNT
  FROM base GROUP BY PERIOD, DIMENSION
),
trended AS (
  SELECT a.*,
    ROUND(100.0 * (TOTAL_AMOUNT - LAG(TOTAL_AMOUNT) OVER (PARTITION BY DIMENSION ORDER BY PERIOD))
          / NULLIF(LAG(TOTAL_AMOUNT) OVER (PARTITION BY DIMENSION ORDER BY PERIOD), 0), 1) AS QOQ_GROWTH_PCT,
    AVG(TOTAL_AMOUNT)    OVER (PARTITION BY DIMENSION ORDER BY PERIOD ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING) AS TRAIL_MEAN,
    STDDEV(TOTAL_AMOUNT) OVER (PARTITION BY DIMENSION ORDER BY PERIOD ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING) AS TRAIL_SD
  FROM agg a
)
SELECT *,
  ROUND(100.0 * TOTAL_AMOUNT / NULLIF(SUM(TOTAL_AMOUNT) OVER (PARTITION BY PERIOD), 0), 1) AS PERIOD_SHARE_PCT,  -- level/mix
  IFF(ABS((TOTAL_AMOUNT - TRAIL_MEAN) / NULLIF(TRAIL_SD, 0)) >= 2, TRUE, FALSE)             AS IS_ANOMALY  -- ≥2σ vs the dimension's own trailing window
FROM trended;

CREATE OR REPLACE VIEW <db>.<schema>.<prefix>_METRICS AS SELECT * FROM <db>.<schema>.DT_<prefix>_METRICS;
```

- **Trend = `LAG`, anomaly = z-score over each dimension's own trailing window** — both are window columns. When a downstream serving row must report a **direction**, carry the structured `QOQ_GROWTH_PCT` (or a derived `up`/`down`/`flat` token computed deterministically from it) forward — do **not** let a later `AI_COMPLETE` narrative be the only place the trend lives. A free-text trend string is unreliable to consume programmatically.
- **Guard, don't trust** — `TRY_TO_DATE`/`TRY_CAST` every input (coerce to STRING first; `TRY_CAST` rejects a NUMBER→NUMBER cast on an already-typed column) and `COALESCE` the dimension. **Canonicalize the grouping dimension (`LOWER(TRIM(...))`) before aggregating** — inconsistent casing from the model silently splits one category into multiple under-counted rows.
- **Aggregate the validated slice** — the `MIN_KEY_CONF >= <conf_cutoff>` filter keeps shaky extractions out of
  the numbers (they sit in the review lane). Image-extracted scores skew low — calibrate down (~0.5).
- **Pick a grain with density — or drop to level/mix.** Trend math needs enough rows per `(period × dimension)`
  cell. If dates are sparse, coarsen the grain (quarter → year) or drop the time axis and report level/mix
  (`PERIOD_SHARE_PCT`, totals, rank). On real document sets level/mix is often the *primary* signal, QoQ the bonus.
- **The dimension needs cardinality-per-period.** A raw vendor column is often near-unique → nothing to trend.
  Derive a **category** with `extract/classify.md` (category-derive) and group on that.

---

## Trend over time — counts by dimension over a time key

- **When** — the corpus is meaningfully orderable and each document has a usable date/time. Skip otherwise —
  don't invent a time axis.
- **Reads** — `THEME_ASSIGNED` (or any per-record table) + a time key carried forward.
- **Produces** — `DT_<prefix>_TIMELINE` (`DIMENSION, TIME_KEY, N`).
- **Refresh** — **FULL (cheap)** — pure aggregation; no AI.
- **Typical upstreams** — `analyze/themes-clusters.md` (theme as the dimension), or any record table with a category.

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_TIMELINE
  TARGET_LAG = '<final_lag>'  WAREHOUSE = <warehouse>  REFRESH_MODE = FULL  INITIALIZE = ON_SCHEDULE
AS
SELECT THEME AS DIMENSION, a.<TIME_KEY> AS TIME_KEY, COUNT(*) AS N
FROM <db>.<schema>.DT_<prefix>_THEME_ASSIGN a   -- TIME_KEY carried forward from Field extraction (SELECT prior.*)
GROUP BY THEME, a.<TIME_KEY>;
```

> The time key rides forward on `SELECT prior.*` from `extract/fields.md` (schema-elicited time key), so it
> already sits on the assignment DT and this block reads it directly — no join. `<DIMENSION>` can be theme, an
> extracted keyword/entity, etc. The only real choice is *whether* a reliable axis exists; if not, skip it.
