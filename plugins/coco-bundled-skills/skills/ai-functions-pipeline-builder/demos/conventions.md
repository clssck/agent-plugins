<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Demo Conventions — the shared demo scaffold

Every demo follows the same scaffold: choose a location, set up ingestion, source a sample corpus, build the pipeline behind one cost gate, showcase the hero, then tear it down. This file is the single source of truth for that sequence. Each demo `SKILL.md` instantiates it — same steps, same order, same gates — adding only its domain specifics (the corpus, the pipeline shape, the hero, the deliverables) and pointing here.

## Cross-cutting rules (always apply)

Inherited from the parent pipeline-builder skill; they hold in every demo:

1. **AI function names carry no `SNOWFLAKE.CORTEX` prefix** — write `AI_PARSE_DOCUMENT`, `AI_COMPLETE`, `AI_EXTRACT`, `AI_CLASSIFY`. (`SPLIT_TEXT_RECURSIVE_CHARACTER` and `SEARCH_PREVIEW` are not AI_* functions; they keep the `SNOWFLAKE.CORTEX.` prefix.)
2. **Cost: show a current-rates warning before any AI function runs** (see [`../SKILL.md`](../SKILL.md) § Pricing). Never quote hardcoded credit numbers — point to the authoritative docs. Mandatory.
3. **Every persistent pipeline is a stream + task + INCREMENTAL dynamic tables.** Verify refresh modes before resuming the task.
4. **Classify from document content, never from filename or path tokens.**

### Pricing

See [`../SKILL.md`](../SKILL.md) § Pricing.

## Placeholders

Demo SQL and scripts use three placeholders, substituted before running:

- `{database}` — a database the user can create objects in.
- `{schema}` — a schema in it (the demo's objects land here).
- `{warehouse}` — a warehouse the user's role can use; the ingest task and dynamic tables refresh under it, not your session.

All demo objects carry the `<tag>` (the demo's short code, given in each demo `SKILL.md`): tables, stages, streams, tasks, and search services are named `DEMO_<tag>_*`, and dynamic tables `DT_DEMO_<tag>_*` (the `DT_` prefix is the parent skill's dynamic-table convention). So a demo occupies exactly two name prefixes — `DEMO_<tag>_` and `DT_DEMO_<tag>_` — and both are checked at collision time and dropped at teardown.

## The demo sequence

Every demo runs these seven steps in this exact order. A demo `SKILL.md` instantiates them; it never reorders them or moves the gates.

### 1. Prerequisites + location

Confirm in one batch:

- `{database}` / `{schema}` where the user has CREATE TABLE / STAGE / DYNAMIC TABLE / TASK / CORTEX SEARCH SERVICE privileges.
- `{warehouse}` the role owns or can use — task and DT refresh run under the owner, not your session.
- The Snowflake CLI / connector connection name for the sourcing script.

**Collision check:** `SHOW TERSE OBJECTS LIKE '%DEMO_<tag>%' IN SCHEMA {database}.{schema};` — the leading `%` catches both the `DEMO_<tag>_` and `DT_DEMO_<tag>_` prefixes. If anything comes back, pick a fresh schema or tear the old demo down first (step 7). (Streams, tasks, and search services aren't listed by `SHOW OBJECTS`; teardown drops those by name.)

### 2. Setup — run `00_setup.sql`

Present the `00_setup.sql` object list and wait for approval. Substitute the placeholders and run `00_setup.sql`: the SSE directory stage, the change-tracked file log, the stage stream, the **suspended** ingest task, and any dimension tables. No AI, no spend. Setup runs **before** sourcing so the stream's baseline is the empty stage and the first files register as new inserts.

### 3. Source the sample corpus — consent, then run the script

Each demo ships a sourcing script under [`scripts/data_sources/`](scripts/data_sources/). Name the dataset and its **source / terms**, then **wait for consent** before downloading or synthesizing anything. One-time setup:

```bash
cd <skill_dir>/demos/scripts
uv sync        # or: pip install -e .
```

The script sources the corpus locally, PUTs it to the demo stage, and refreshes the stage directory (`--connection {connection} --database {database} --schema {schema}`). Then backfill the file log by running the ingest task once (`EXECUTE TASK ...`) and confirm files landed.

### 4. Cost gate

Show the [`../SKILL.md`](../SKILL.md) § Pricing note plus the demo's own AI call-count estimate, and present the **DAG** and applied **defaults**. **The gate applies before the first AI-bearing action (step 5, including any smoke pass).** Wait for approval. If declined, offer step 7 teardown.

### 5. Build — create the pipeline, then the first AI-bearing action

`10_pipeline.sql` creates the dynamic-table chain and any search service. Compile-validate every `CREATE` first (`only_compile`, zero spend). Each demo uses one of two build patterns (its `SKILL.md` says which):

- **Auto-initialize** — the DTs refresh on creation, so running `10_pipeline.sql` **is** the first AI-bearing action. Verify refresh modes immediately after (step 6 in `20_*.sql`). If a per-document DT is `FULL`, suspend, recreate as `INCREMENTAL`, re-refresh.
- **Zero-spend scaffold** (`INITIALIZE = ON_SCHEDULE` + a suspended terminal) — creating the DTs compiles and fixes refresh modes with **no AI**; a separate explicit refresh (in the demo's `20_*.sql`) is the first AI-bearing action. Verify refresh modes **before** that refresh.

Either way the cost gate (step 4) sits before the first AI-bearing action. Every per-document / per-record DT must be `INCREMENTAL` — a `FULL` per-document DT re-runs AI on every refresh; only documented aggregate rollups may be `FULL`. Smoke on one or two files where the demo offers it, then run the full corpus. The ingest task stays **suspended**; resume it last only for continuous ingestion (optional for a static demo corpus).

### 6. Showcase

Run the demo's `20_*.sql` deliverables and/or open its `notebook.ipynb` — a Snowflake (Streamlit) notebook of narrative plus live SQL over the deployed objects.

### 7. Teardown

Drop in reverse dependency order: suspend the task; drop views and the search service; drop dynamic tables newest -> oldest; then the task, the stream, the file log, the dimension tables, and finally the demo stage. Present the exact DROP list — it covers both the `DEMO_<tag>_` and `DT_DEMO_<tag>_` prefixes — then **wait for approval**. DROP is irreversible.

## Next steps

Point the user to the matching template — `../templates/<x>/SKILL.md` — to build the same pipeline over their own documents.

## Stopping points (every demo)

1. ✋ **Location** (step 1) — wait for db / schema / warehouse / connection.
2. ✋ **Setup** (step 2) — present the `00_setup.sql` object list; wait before running.
3. ✋ **Consent** (step 3) — name the dataset + source/terms; wait before sourcing.
4. ✋ **Cost gate** (step 4) — show pricing + estimate + DAG; wait for approval.
5. ✋ **Refresh modes** (step 5) — every per-document DT must be `INCREMENTAL`; fix any that aren't before you rely on results or resume ingestion.
6. ✋ **Teardown** (step 7) — present the DROP list; wait for approval.
