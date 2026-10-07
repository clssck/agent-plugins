# Example — Research-paper corpus (worked composition)

**Scenario:** A set of research paper PDFs land on a stage. You don't know the
collection — you want to know **what themes it covers, how the focus evolved with time, which papers are outliers,
and where to start reading**, plus a queryable per-paper facts table — without reviewing all of them manually.

This is the **reference composition** — when in doubt start here, then drop or add blocks for the case at
hand. It shows how blocks wire together; the SQL bodies live in the shared palette, indexed by
[`../../../blocks/README.md`](../../../blocks/README.md), so this file stays a recipe and can't drift from it.

**Worked names:** `db=RESEARCH`, `schema=RL`, `<prefix>=CORPUS`, `stage=PAPERS_STAGE`, `warehouse=CORPUS_WH`.
Swap in the user's own.

## Blocks, in build order

| # | Block (in the palette) | Object(s) it creates | Grain / refresh | Composition note |
|---|---------------------------|----------------------|-----------------|------------------|
| 1 | Ingestion | stage, `CORPUS_FILE_LOG`, `CORPUS_STAGE_STREAM`, `CORPUS_INGEST_TASK` | — | `.pdf` filter; seed the backlog (base Step 4) |
| 2 | Parse / OCR | `DT_CORPUS_PARSED` | per-doc · `INCREMENTAL` | `OCR` (prose papers, no tables) |
| 3 | Field extraction | `DT_CORPUS_EXTRACTED` | per-doc · `INCREMENTAL` | user schema: `title, authors[], problem, methods[], contributions[], keywords[], datasets[]`; also derives `PUB_YEAR` free from the arXiv `YYMM` filename (deterministic SQL, no AI) |
| 4 | Per-document summary | `DT_CORPUS_SUMMARIZED` | per-doc · `INCREMENTAL` | the `<facet…>` placeholders instantiated for papers: structured `problem/approach/key_result/significance` + `SUMMARY_TEXT` (from extracted fields) |
| 5 | Embedding | `DT_CORPUS_EMBEDDED` | per-doc · `INCREMENTAL` | `AI_EMBED(SUMMARY_TEXT)` → `SUMMARY_VEC` |
| 6 | Theme taxonomy | `CORPUS_THEMES` (pinned table) | regenerated on demand | the control plane — built once embeddings exist, **not** per file |
| 7 | Theme assignment | `DT_CORPUS_THEME_ASSIGN` | per-doc · `INCREMENTAL` | nearest theme by cosine → `THEME`, `THEME_SIM` |
| 8 | Outlier detection | `DT_CORPUS_OUTLIERS` | corpus · `FULL` | adaptive threshold `mean − 1·stddev` |
| 9 | Corpus synthesis | `DT_CORPUS_SYNTHESIS` | corpus · `FULL` | one generated narrative (`LISTAGG → AI_COMPLETE`) |
| 10 | Trend over time | `DT_CORPUS_TIMELINE` | corpus · `FULL` | theme × `PUB_YEAR` counts (uses the time key from #3, carried forward) |
| 11 | Cluster highlights | view `CORPUS_HIGHLIGHTS` | view | exemplar + outlier per theme (the *reading list* for papers) |
| 12 | Final shape | views `CORPUS_ITEMS`, `CORPUS_PROFILE` | views | per-paper facts + corpus profile |

**DAG:**

```
@PAPERS_STAGE → CORPUS_STAGE_STREAM + CORPUS_INGEST_TASK → CORPUS_FILE_LOG
  → DT_CORPUS_PARSED → DT_CORPUS_EXTRACTED → DT_CORPUS_SUMMARIZED → DT_CORPUS_EMBEDDED     [per-doc · INCREMENTAL]
                                                  │                       │
                          (regen on demand)  CORPUS_THEMES (pinned) ──────┤
                                                                          ↓
                                                   DT_CORPUS_THEME_ASSIGN                   [INCREMENTAL]
                                                             │
        ┌─────────────────────────────┬────────────────────┴───────────┐                  [corpus · FULL]
  DT_CORPUS_OUTLIERS           DT_CORPUS_TIMELINE                  DT_CORPUS_SYNTHESIS
  (← THEME_ASSIGN)             (← THEME_ASSIGN, carries PUB_YEAR)   (← SUMMARIZED)
        └──────────────────→ CORPUS_ITEMS · CORPUS_PROFILE · CORPUS_HIGHLIGHTS   [views]
```

## How the blocks wire

- **Two grains, one rule.** Everything from Parse to Theme-assign is **per-document `INCREMENTAL`** — a new
  paper triggers AI on that paper only. The rollups (Outliers, Synthesis, Trend) are **corpus-grain `FULL`**
  but cheap (they aggregate the short summaries/vectors, never re-parse PDFs). This is the deliberate
  override of the base's all-`INCREMENTAL` rule — see the contract in [`../../../blocks/conventions.md`](../../../blocks/conventions.md).
- **Extract owns the time axis.** `DT_CORPUS_EXTRACTED` derives `PUB_YEAR` from the arXiv `YYMM` filename in
  pure SQL (deterministic, free) — the time key lives in one place even when it's filename-encoded, then
  rides `SELECT prior.*` forward to the Trend block.
- **Summary feeds everything downstream, not the raw text.** `SUMMARY_TEXT` is built from the extracted
  fields and falls back to them if the structured summary soft-fails — so every paper always has a usable
  embedding input. Embedding, taxonomy, and assignment all key off that summary.
- **The taxonomy is a control plane, not a per-file DT.** `CORPUS_THEMES` (name + description + vector) is
  generated once from all summaries and **pinned**; assignment (#7) scores each paper against the cached
  theme vectors, so adding a paper costs one row of cosine math, not a re-derivation of the themes.
  Regenerate `CORPUS_THEMES` deliberately (corpus grew a lot, or the outlier rate climbs) — see [`../../../blocks/analyze/themes-clusters.md`](../../../blocks/analyze/themes-clusters.md).
- **Outliers are the "new direction" signal.** A paper that fits no theme well (low `THEME_SIM`) is flagged
  rather than silently mis-filed — and that's the cue to regenerate the taxonomy.


## Build & verify

Create blocks #1–#5 and #7–#12, then **backfill the per-document chain first** (refresh the terminal
per-doc DT; refreshing downstream refreshes stale upstreams), **then run the taxonomy regen (#6)** — it needs
`DT_CORPUS_SUMMARIZED` populated — and refresh assignment + the rollups. **Resume `CORPUS_INGEST_TASK` last**
(after every object exists).

Then verify refresh modes against the **two-grain policy** (base Step 6): every per-document `DT_CORPUS_*`
(parse → assign) reports `INCREMENTAL` — stop and fix any that are wrongly `FULL`; the rollups
(`_OUTLIERS`, `_TIMELINE`, `_SYNTHESIS`) are *expected* to be `FULL`. Smoke-check: `CORPUS_ITEMS` has one row
per paper with fields populated, `CORPUS_THEMES` is non-empty and every paper got a `THEME`/`THEME_SIM`, and
`DT_CORPUS_SYNTHESIS` has a narrative.

For freshness, set the user's target lag (default 1 hour) on the three terminal rollups
(`DT_CORPUS_OUTLIERS`, `DT_CORPUS_TIMELINE`, `DT_CORPUS_SYNTHESIS`) and leave every upstream DT
`TARGET_LAG = DOWNSTREAM`; they refresh transitively, and the views inherit (base Step 7).

## What the corpus profile buys you

One read of the profile answers "what is this and where do I start" — no paper-by-paper review:

```sql
-- themes, size, and how each spans the decade
SELECT THEME, N_ITEMS, AVG_COHESION FROM RESEARCH.RL.CORPUS_PROFILE ORDER BY N_ITEMS DESC;

-- where to start reading: a central + an off-beat paper per theme
SELECT THEME, ROLE, TITLE FROM RESEARCH.RL.CORPUS_HIGHLIGHTS ORDER BY THEME, ROLE;
```

On the validated 44-paper run this surfaced **8 themes** — led by *RL for Language Models* (11 papers,
2020–2025) — a clean decade arc from *DQN Improvements* (2015–2018) to the RLHF/LLM surge, and **7 topical
outliers** (world-model / planning / LLM-as-tool papers). All from objects the pipeline maintains
incrementally — a new paper updates its own row and the cheap rollups, never a re-parse of the corpus.

## Teardown

Dependency-safe order for exactly the objects above. **These `DROP`s are irreversible — present them and get explicit user approval before running any** (full rule + gate in [`../SKILL.md`](../SKILL.md) § Teardown):

```sql
ALTER TASK RESEARCH.RL.CORPUS_INGEST_TASK SUSPEND;        -- stop ingestion first

DROP VIEW IF EXISTS RESEARCH.RL.CORPUS_PROFILE;           -- user-facing views (read the DTs)
DROP VIEW IF EXISTS RESEARCH.RL.CORPUS_ITEMS;
DROP VIEW IF EXISTS RESEARCH.RL.CORPUS_HIGHLIGHTS;

DROP DYNAMIC TABLE IF EXISTS RESEARCH.RL.DT_CORPUS_SYNTHESIS;     -- corpus-grain rollups
DROP DYNAMIC TABLE IF EXISTS RESEARCH.RL.DT_CORPUS_TIMELINE;
DROP DYNAMIC TABLE IF EXISTS RESEARCH.RL.DT_CORPUS_OUTLIERS;
DROP DYNAMIC TABLE IF EXISTS RESEARCH.RL.DT_CORPUS_THEME_ASSIGN;  -- per-doc DTs, newest → oldest
DROP DYNAMIC TABLE IF EXISTS RESEARCH.RL.DT_CORPUS_EMBEDDED;
DROP DYNAMIC TABLE IF EXISTS RESEARCH.RL.DT_CORPUS_SUMMARIZED;
DROP DYNAMIC TABLE IF EXISTS RESEARCH.RL.DT_CORPUS_EXTRACTED;
DROP DYNAMIC TABLE IF EXISTS RESEARCH.RL.DT_CORPUS_PARSED;

DROP TABLE  IF EXISTS RESEARCH.RL.CORPUS_THEMES;          -- pinned taxonomy (+ its regen task/proc, if created)

DROP TASK   IF EXISTS RESEARCH.RL.CORPUS_INGEST_TASK;     -- task, then stream, then file log
DROP STREAM IF EXISTS RESEARCH.RL.CORPUS_STAGE_STREAM;
DROP TABLE  IF EXISTS RESEARCH.RL.CORPUS_FILE_LOG;

-- Leave @PAPERS_STAGE in place — that's the user's documents.
```

(Conventions — `INCREMENTAL`-safety, target-lag policy, monitoring — are base-owned: see
[`../../../references/multi-step-pipeline.md`](../../../references/multi-step-pipeline.md).)
