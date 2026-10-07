# Block Conventions — the shared contract

Every block in `blocks/` is a composable layer of a document pipeline. This file is the **contract
that lets blocks from different use cases intermix**: the data shapes blocks pass to each other, the
rules for composing them, the refresh-mode policy, and how to write your own. Read it once; every
block file assumes it.

Generic AI-function mechanics and the end-to-end workflow (approach choice, requirements, refresh
verification, target lag, test, go-live, monitoring) live in the base —
[`../references/multi-step-pipeline.md`](../references/multi-step-pipeline.md). Blocks supply the
*layers*; the base supplies the *workflow* and the *AI-function rules* (no `SNOWFLAKE.CORTEX` prefix,
`TO_FILE` two-arg, `TRY_CAST` for `"None"`, no `LATERAL`-join to AI/UDTF in incremental DTs). Don't
restate those here.

Use the router — [`README.md`](README.md) — to pick the files you need; load only those.

---

## Data shapes — the currency between blocks

Each block declares what it **Reads** and **Produces** in terms of these **named shapes** — a row grain
plus the columns that matter — rather than a specific upstream object, so a block stays composable across
use cases instead of being tied to one chain. Composition is: **match a block's `Reads` shape to an
upstream block's `Produces` shape.** The object names are yours; the shapes are the contract.

| Shape | Grain | Key columns | Produced by |
|-------|-------|-------------|-------------|
| `FILE` | per file | `RELATIVE_PATH` (PK, stage-unique), `FILE_NAME`, `INGESTED_AT` (+ `FILE_SIZE`, `LAST_MODIFIED`, `FILE_URL`) | `ingest/ingestion.md` |
| `DOC_TEXT` | per file | a `FILE` + **one text column** holding the document's content as a string — named `PARSED_TEXT`, `PARSED_TEXT_EN`, or `CONTENT` depending on upstream | `ingest/parse-text.md` (+ Translate) |
| `DOC_PARSE` | per file | a `FILE` + `RAW_PARSE` (VARIANT, has `:pages` / `:content`) + `DOC_KEY` (path minus extension) | `ingest/parse-pages.md` |
| `PAGE_TEXT` | per (doc, page) | `RELATIVE_PATH`, `DOC_KEY`, `PAGE`, `CONTENT` | `ingest/parse-pages.md` |
| `TYPED_FIELDS` | per document | a `FILE` + typed extracted columns (+ `RAW_EXTRACT`, + per-field `<F>_CONF` / `MIN_KEY_CONF` when scored) | `extract/fields.md`, `extract/vision-structured.md` |
| `ENTITY` | per entity | `<entity_key>` (PK) + assembled type fields + `HAS_*` flags + derived cross-doc signals (+ `MIN_KEY_CONF`) | `records/entity.md` |
| `SUMMARY` | per document | a per-doc row + `S_*` facet columns + `SUMMARY_TEXT` (never NULL) | `analyze/summarize-embed.md` |
| `EMBEDDED` | per document | a `SUMMARY` + `SUMMARY_VEC VECTOR(FLOAT, <dim>)` | `analyze/summarize-embed.md` |
| `THEME_ASSIGNED` | per document | a per-doc row + `THEME`, `THEME_SIM` (+ a time key when present) | `analyze/themes-clusters.md` |
| `CHUNK` | per chunk | `RELATIVE_PATH` + (`PAGE` or `CHUNK_NO`) + `TITLE` + `CHUNK` text (+ filterable facets) | `search/chunk-index.md` |
| `METRIC` | aggregate (period × dimension) | `PERIOD`, `DIMENSION`, `TOTAL_*`, `*_COUNT`, `QOQ_*`, `IS_ANOMALY` | `analyze/metrics-trend.md` |
| `DECISION` | per record | a record + `RISK`, `REASONS`, `DERIVED_AMOUNT`, `SUGGESTED_ACTION`, `RATIONALE` | `records/reason.md` |
| `ROUTED` | per record | a `DECISION` + `ROUTE`, `REVIEW_PRIORITY` | `records/triage.md` |

Blocks declare shapes, not specific objects — e.g. *"Reads a `DOC_TEXT` row"* (the column may be `PARSED_TEXT`, `PARSED_TEXT_EN`, or `CONTENT`). **Typical upstreams** names the concrete producers.

### The three grain shifts (the only places grain changes)

Blocks at the same grain carry prior columns forward (`SELECT prior.*, <new_col>`). Grain only
changes through one of these blocks — never join across grains any other way:

- **doc → entity** — `records/entity.md` (many documents compose one record).
- **doc → chunk** — `search/chunk-index.md` (one document fans out to many retrieval units).
- **records → aggregate** — `analyze/metrics-trend.md`, `analyze/synthesize.md`, and the corpus
  rollups in `analyze/themes-clusters.md` (every record collapses to period × dimension or one
  corpus-level row).

---

## How blocks compose

1. **Select** the blocks the goal needs (the router groups them; the templates give curated recipes).
2. **Order** them by matching each block's `Reads` shape to an upstream block's `Produces` shape.
   Ingestion is always the head; a serving view/app is always the tail.
3. **Carry columns forward** on same-grain blocks; cross grain only through the three shift blocks above.
4. **Resolve wiring hazards** flagged on individual blocks (e.g. Translate rewiring which text column the
   extractors read).
5. **Key per-file joins on `RELATIVE_PATH`** (stage-unique), per-entity joins on `<entity_key>` — never
   on `FILE_NAME` (a basename that collides across subfolders).

---

## Refresh-mode contract

The whole cost argument of this architecture is: **the expensive AI runs once per new file, never
re-runs the corpus.** Two grains, two rules — every block is tagged with its mode and why.

- **Per-document / per-page / per-entity grain** — where the expensive AI lives (parse, extract,
  vision, summarize, embed, reason). **MUST stay `INCREMENTAL`** so a new file triggers AI on *that
  file only*. Call AI **inline** — a `LATERAL`-join to an AI/UDTF demotes the DT to `FULL`. (`LATERAL
  FLATTEN` over an already-materialized array is the one allowed lateral form; select `f.index`, never
  `f.seq`.)
- **Aggregate / corpus grain** — rollups that read every row (taxonomy, synthesis, metrics, outliers,
  trend, insights). These are **`FULL` by necessity but cheap**: they aggregate short summaries / vectors
  / metric rows and make at most one or two AI calls — they never re-touch the source files. Mark them
  `REFRESH_MODE = FULL  INITIALIZE = ON_SCHEDULE`.

`AI_AGG` is **non-deterministic and banned inside dynamic tables** — use `LISTAGG(...) → AI_COMPLETE(...)`
for aggregate-grain synthesis. (`AI_AGG` *is* allowed in a one-shot CTAS / stored proc.)

After building, run the base **Step 6** check (`SHOW DYNAMIC TABLES` → `refresh_mode`): every per-grain
DT must read `INCREMENTAL`; a per-grain DT that reads `FULL` is a re-process-everything cost bug — stop
and fix it. Aggregate rollups reading `FULL` are expected, not defects.

> **Naming gate (from base):** name *every* dynamic table `DT_<prefix>_*` so the Step 6 filter sees it.
> Expose unprefixed user-facing names (`<prefix>_HEADER`, `<prefix>_ITEMS`, search services, apps) as
> **views / services**, never as bare dynamic tables.

---

## Writing your own block

The palette won't cover every request. When you need a layer that isn't here, build it inline — keep
it composable and respect the contract:

- Declare its `Reads`/`Produces` in the shape vocabulary above; if it introduces a genuinely new shape,
  describe its grain + key columns so the next block can wire to it.
- Name every dynamic table `DT_<prefix>_*`; expose friendly names as views. Pick the refresh mode by
  grain (per-grain → `INCREMENTAL`; aggregate → `FULL` cheap) and verify it (base Step 6).
- Intermediate DTs use `TARGET_LAG = DOWNSTREAM`; only the final DT/view in the chain takes the user's lag.
- Call AI inline; `TRY_CAST` every non-string `AI_EXTRACT` field; `COALESCE` every `PROMPT()` argument (NULL arg → NULL prompt → error); pass files as `TO_FILE('@<stage>', RELATIVE_PATH)` from within the DT body — never `BUILD_SCOPED_FILE_URL`/`SCOPED_FILE_URL` (non-deterministic; URLs expire on refresh).

---

## Choosing models — confirm availability before building DTs

AI-function DTs hardcode a model name. A wrong or unavailable name fails **on every refresh** and cascades silently (not at `CREATE` time).

- **Confirm the model exists before wiring it into a DT.** Availability varies by account/region. Check the [Cortex AI SQL regional availability matrix](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql-regional-availability); for vision models also the [AI_COMPLETE Prompt-object reference](https://docs.snowflake.com/en/sql-reference/functions/ai_complete-prompt-object) — neither is queryable from SQL. Probe: `SELECT AI_COMPLETE('<model>', 'test')` (or a real file for vision) before building.
- **On "model unavailable"** — swap the model name and re-create the same DT; not a pipeline rebuild. Never fall back to a text-only model in a vision DT (compiles but produces unusable output).
- Keep the model name as a named placeholder (`<vision_model>`, `<reasoning_model>`, `<embed_model>`) — one-line swap across the whole chain.

---

## Placeholders

Replace consistently across every block you compose:

`<db>.<schema>` · `<prefix>` (object prefix; all objects are `<prefix>_*` / `DT_<prefix>_*`) ·
`<stage>` (and `<page_stage>` for page-image lanes) · `<warehouse>` ·
`<entity_key>` (the per-record grouping key, e.g. `CLAIM_NO`) ·
`<reasoning_model>` · `<vision_model>` (must be image-capable; never fall back to a text-only model in a vision DT — it passes compile but produces unusable output) ·
`<embed_model>` (default `snowflake-arctic-embed-l-v2.0`) · `<final_lag>` (the terminal object's target lag).

> **Collision check before building:** objects are `CREATE OR REPLACE`d under `<prefix>`, so reusing a
> prefix already in the schema silently clobbers it. Run
> `SHOW TERSE OBJECTS LIKE '%<prefix>%' IN SCHEMA <db>.<schema>;` first and pick a distinct prefix if
> anything comes back.
