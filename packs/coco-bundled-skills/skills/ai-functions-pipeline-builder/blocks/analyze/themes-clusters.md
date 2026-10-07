# Themes & clusters — organize a corpus by topic (vector math + one AI call)

The corpus-understanding suite: discover the **themes** a collection organizes into, assign each document to its
nearest theme, flag **outliers** that fit none, and surface an **exemplar + outlier per theme**. A coupled
dependency chain — taxonomy needs the summaries, assignment needs embeddings + taxonomy, outliers/highlights need
assignment — so they live together. Only the taxonomy makes an AI call; the rest is vector math.

> Read [`../conventions.md`](../conventions.md) first. These read the per-document `SUMMARY`/`EMBEDDED` shapes
> from [`summarize-embed.md`](summarize-embed.md). The aggregate context-window / map-reduce mechanics referenced
> below are detailed once in [`synthesize.md`](synthesize.md).

---

## Theme taxonomy — the named topics (pinned table, not a DT)

- **When** — you want named topics/groups the corpus organizes into.
- **Reads** — `SUMMARY` (`DT_<prefix>_SUMMARIZED`, all rows: `TITLE`, `S_*` facets).
- **Produces** — `<prefix>_THEMES` table (`THEME_ID, THEME_NAME, THEME_DESC, THEME_VEC`).
- **Refresh** — **n/a — a pinned table regenerated on demand, not a DT.** If it were a `FULL` DT it would
  re-derive (and re-embed, and churn theme names) on every new file. Pin it so assignment stays incremental
  against stable vectors; regenerate when the corpus grows materially, on a slow schedule, or when the **outlier
  fraction** climbs (the cue that new directions have arrived).

```sql
-- Run on demand (or schedule slowly). NOT per upload.
CREATE OR REPLACE TABLE <db>.<schema>.<prefix>_THEMES AS
WITH agg AS (
  SELECT LISTAGG(TITLE || ': ' || S_<FACET1> || ' ' || S_<FACET2>, '\n') AS corpus_text
  FROM <db>.<schema>.DT_<prefix>_SUMMARIZED
),
prop AS (
  SELECT AI_COMPLETE('<reasoning_model>',
    PROMPT('Identify 5-8 distinct themes that organize this corpus; each with a short name and one-sentence description. Items:\n{0}', corpus_text),
    response_format => {'type':'json','schema':{'type':'object','properties':{
      'themes':{'type':'array','items':{'type':'object','properties':{
        'name':{'type':'string'},'description':{'type':'string'}},'required':['name','description']}}},
      'required':['themes']}}
  ) AS RAW_TAXONOMY FROM agg
)
SELECT
  f.index AS THEME_ID,
  f.value:name::STRING AS THEME_NAME,
  f.value:description::STRING AS THEME_DESC,
  AI_EMBED('<embed_model>', f.value:name::STRING || ': ' || f.value:description::STRING) AS THEME_VEC
FROM prop, LATERAL FLATTEN(input => RAW_TAXONOMY:themes) f;
```

- `AI_AGG` is allowed here (one-shot CTAS, not a DT), but `LISTAGG → AI_COMPLETE` gives more control over the
  structured output. Wrap the CTAS in a proc + task if you want it scheduled.
- **Large corpora** — the `LISTAGG` of all summaries overflows the context window past a few hundred docs. Detect
  it with `return_error_details => TRUE` (see [`synthesize.md`](synthesize.md)) and switch to a **2-level
  map-reduce**: propose candidate themes per `NTILE` batch (free text), then a `reduce` step consolidates them
  into 5-8 final themes (only the reduce needs the structured `response_format`; the final `FLATTEN` + `AI_EMBED`
  is unchanged).

---

## Theme assignment — nearest theme per document

- **When** — with a taxonomy; labels each document with its best-fit theme + similarity.
- **Reads** — `EMBEDDED` (`SUMMARY_VEC`) + `<prefix>_THEMES` (`THEME_VEC`).
- **Produces** — `THEME_ASSIGNED`: `DT_<prefix>_THEME_ASSIGN` (`THEME, THEME_SIM`; carry a time key if present).
- **Refresh** — **INCREMENTAL** (per-doc `ROW_NUMBER` + `CROSS JOIN` to the small static themes table is incremental-eligible).

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_THEME_ASSIGN
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = <warehouse>  REFRESH_MODE = INCREMENTAL  INITIALIZE = ON_SCHEDULE
AS
WITH scored AS (
  SELECT e.RELATIVE_PATH, e.FILE_NAME, e.TITLE, e.<TIME_KEY>,   -- carry the time key forward for Trend
    t.THEME_ID, t.THEME_NAME,
    VECTOR_COSINE_SIMILARITY(e.SUMMARY_VEC, t.THEME_VEC) AS SIM,
    ROW_NUMBER() OVER (PARTITION BY e.RELATIVE_PATH
                       ORDER BY VECTOR_COSINE_SIMILARITY(e.SUMMARY_VEC, t.THEME_VEC) DESC) AS RN
  FROM <db>.<schema>.DT_<prefix>_EMBEDDED e
  CROSS JOIN <db>.<schema>.<prefix>_THEMES t
)
SELECT RELATIVE_PATH, FILE_NAME, TITLE, <TIME_KEY>, THEME_ID, THEME_NAME AS THEME, SIM AS THEME_SIM
FROM scored WHERE RN = 1;
```

> Regenerating `<prefix>_THEMES` correctly re-drives this DT for all rows; a new document alone assigns just that
> row. Documents that fit no theme well surface in Outliers (below) rather than being silently mis-filed.

---

## Outlier detection — documents that fit no theme

- **When** — flag topically-unusual documents (the cue to regenerate themes).
- **Reads** — `THEME_ASSIGNED` (`THEME_SIM`).
- **Produces** — `DT_<prefix>_OUTLIERS` (`THEME_SIM, OUTLIER_THRESHOLD, IS_OUTLIER`).
- **Refresh** — **FULL (cheap)** — needs the corpus-wide mean/stddev; no AI.

```sql
CREATE OR REPLACE DYNAMIC TABLE <db>.<schema>.DT_<prefix>_OUTLIERS
  TARGET_LAG = '<final_lag>'  WAREHOUSE = <warehouse>  REFRESH_MODE = FULL  INITIALIZE = ON_SCHEDULE
AS
WITH stats AS (SELECT AVG(THEME_SIM) mu, STDDEV(THEME_SIM) sd FROM <db>.<schema>.DT_<prefix>_THEME_ASSIGN)
SELECT a.RELATIVE_PATH, a.FILE_NAME, a.TITLE, a.THEME, a.THEME_SIM,
  ROUND(s.mu - s.sd, 3) AS OUTLIER_THRESHOLD,
  (a.THEME_SIM < s.mu - s.sd) AS IS_OUTLIER
FROM <db>.<schema>.DT_<prefix>_THEME_ASSIGN a CROSS JOIN stats s;
```

- Use an **adaptive** threshold (`mean − k·stddev`), not an absolute cutoff — cohesion varies by corpus (an
  absolute 0.55 over-flagged ~half a tight corpus; `mean − 1·sd` flagged a sensible ~15%).
- **Want it incremental?** Store the threshold as a scalar in `<prefix>_THEMES` at regen time, then the per-doc
  flag (`THEME_SIM < :threshold`) can live in the assignment DT and stay `INCREMENTAL`.

---

## Cluster highlights — exemplar + outlier per theme

- **When** — almost always; a fast way in: the most-representative item per theme and the most-divergent one.
- **Reads** — `THEME_ASSIGNED` (`THEME, TITLE, THEME_SIM`).
- **Produces** — `<prefix>_HIGHLIGHTS` view (`THEME, ROLE, TITLE, RELATIVE_PATH, THEME_SIM`).
- **Refresh** — view (no refresh mode).

```sql
CREATE OR REPLACE VIEW <db>.<schema>.<prefix>_HIGHLIGHTS AS
WITH ranked AS (
  SELECT THEME, TITLE, RELATIVE_PATH, THEME_SIM,
    ROW_NUMBER() OVER (PARTITION BY THEME ORDER BY THEME_SIM DESC) AS rn_top,
    ROW_NUMBER() OVER (PARTITION BY THEME ORDER BY THEME_SIM ASC)  AS rn_bot
  FROM <db>.<schema>.DT_<prefix>_THEME_ASSIGN
)
SELECT THEME, 'exemplar' AS ROLE, TITLE, RELATIVE_PATH, THEME_SIM FROM ranked WHERE rn_top = 1
UNION ALL
SELECT THEME, 'outlier'  AS ROLE, TITLE, RELATIVE_PATH, THEME_SIM FROM ranked WHERE rn_bot = 1;
```

> **Domain framing** — describe generically (exemplar + outlier per theme); the corpus may be videos, filings,
> tickets, etc. For research papers this naturally reads as a *recommended reading list* (a representative paper +
> the off-beat one per direction).
