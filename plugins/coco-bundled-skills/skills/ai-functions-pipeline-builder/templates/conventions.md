# Template Conventions — the shared recipe scaffold

Every use-case template in this directory is a **recipe** over the shared block palette
([`../blocks/`](../blocks/)): it selects blocks, supplies domain defaults, and drives the build behind one
approval gate. The orchestration scaffold — read-the-base, intake structure, the build gate, teardown, and
stopping points — is identical across templates and lives here so each `SKILL.md` carries only its domain
specifics. Each template's `SKILL.md` points here and overrides where noted.

---

## Read first (every template)

1. **Base** — [`../references/multi-step-pipeline.md`](../references/multi-step-pipeline.md): the approach
   choice (DT vs streams vs dbt), the hybrid architecture, the AI-function rules, and Steps 6–10 (refresh
   verification, target lag, test, go-live, monitoring). Inherit verbatim — don't restate or fork.
2. **Palette** — [`../blocks/README.md`](../blocks/README.md) (router) + [`../blocks/conventions.md`](../blocks/conventions.md)
   (data-shape contract, compose rules, refresh-mode policy). The template's recipe names which blocks to load.

You are the driver: gather requirements, compose the recipe's blocks, build live behind **one** approval gate.
Don't also run the parent skill's generic flow.

---

## Intake (every template)

Confirm the **hard requirements** in one batch — you can't infer these and can't build without them:

1. Database, schema, and a short object prefix (all objects are `<prefix>_*` / `DT_<prefix>_*`).
   - **Collision check:** the builds `CREATE OR REPLACE` under `<prefix>`, so reusing a prefix already in the
     schema silently clobbers it. Run `SHOW TERSE OBJECTS LIKE '%<prefix>%' IN SCHEMA <db>.<schema>;` first and
     pick a distinct prefix if anything comes back.
2. Source stage — an existing path or create one? Confirm it is **server-side encrypted** (`SNOWFLAKE_SSE`);
   client-side-encrypted stages break every AI file function.
3. Warehouse for the ingest task and the dynamic tables (one the **owner role** can use — refresh runs under
   the owner, not your session).
4. What to extract / produce — the template's domain question(s).

Then **only raise the shaping topics the prompt left open** — one at a time, lead with the default, skip
anything already answered. Each template's `SKILL.md` has its own `topic → default → block` table; each row
maps to a palette block.

**Volume / latency nudge:** if the user signals very high volume (>~10K/day) or sub-minute latency, flag that a
pure Streams+Tasks pipeline may fit better than dynamic tables, and offer to step out.

---

## Build [WAIT] (every template)

Compose the chosen blocks (order by matching each block's `Reads` shape to an upstream's `Produces`; head =
`ingest/`, tail = `serve/`), then present **one approval gate**:

1. **The DAG** — the chain of objects for the *chosen* blocks (not a maximal template), each DT's grain/refresh
   labeled.
2. **Assumptions** — every default applied, so the user can correct before anything is built.
3. **Compile-validated `CREATE`s** — run every statement through `sql_execute` `only_compile: true`; fix the
   root cause of any failure and re-validate (base Step 5). *(Downstream DTs only compile once their upstream
   exists — create the chain in dependency order, compiling each before creating it.)*
4. **Pricing** — the AI-function cost estimate (mandatory before any AI execution; see [`../SKILL.md`](../SKILL.md) § Pricing).
5. **Dry-run offer** — optionally chain the AI functions on one or two sample files as a single `SELECT` first
   (extraction/answer quality is the #1 risk), then iterate on the `responseFormat`/prompt descriptions before
   materializing DTs.

**⚠️ MANDATORY STOPPING POINT** — wait for approval (or a dry-run cycle) before creating any objects.

On approval, build live per the base: execute the `CREATE`s (the ingest task stays **suspended**) → seed the
backlog if the stage already has files → **verify refresh modes** (base Step 6) per the template's expectation →
run the base Step 8 test plus the template's smoke checks → only then **resume the ingest task last** to go live
(base Step 9).

---

## Teardown (every template)

**Only when the user explicitly asks to tear down or clean up** (never proactively): generate the `DROP`s from
the objects actually created, in reverse dependency order — suspend the ingest task(s) first; drop user-facing
**views / services / procs**, then the **DTs** newest→oldest (final shape back to parse), then any pinned tables
/ regen procs, then the **task(s)**, the **stream(s)**, and the **file-log table(s)**. **Never** drop the source
stage(s) or user-owned reference data — the user's documents and masters live there.

**⚠️ MANDATORY STOPPING POINT**: `DROP` is irreversible. Present the full list of objects to be dropped — and
call out what you are **not** dropping (source stages, reference tables) — then wait for explicit approval.

---

## Stopping points (every template)

1. ✋ **Intake** — wait for the hard requirements (and any shaping topics you raise).
2. ✋ **Build gate** — wait for approval (or a dry-run cycle) before creating objects.
3. ✋ **Base Step 6** — stop and fix any DT whose refresh mode violates the template's expectation (per-grain DTs
   must be `INCREMENTAL`; aggregate rollups are expected `FULL`).
4. ✋ **Teardown** (only if the user asks) — present the exact `DROP` list and wait for explicit approval.

The base's own gates (approach, target lag) still apply; proceed silently on approach unless the volume/latency
nudge triggers, and gather the target lag during intake.
