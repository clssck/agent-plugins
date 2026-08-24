---
name: cortex-sense
"description": "Set up, test, query, and refine Cortex Sense contexts, and turn a built context into a CoWork agent. CoCo scans the account when the use case is named, proposes a scoped domain context, accepts plain-English edits, and persists a manifest the offline build consumes. Use when starting a Cortex Sense use case, validating a built context with real questions, querying across multiple contexts, listing available Cortex Sense domains, correcting a wrong / missing / stale answer, or creating an agent grounded in a context. Triggers: set up cortex sense, build cortex sense for <use case>, test the <use case> context, search contexts for <X>, what does cortex sense know about <X>, refine cortex sense, the agent picked the wrong table, DAU is wrong, exclude staging, @cortex-sense resume <use case>, @cortex-sense query <use case> about <X>, list cortex sense, create an agent for <domain>, create a cowork agent, deploy <domain> as an agent, add cortex sense to <agent>, enable cortex_sense on <agent>."
---

# Cortex Sense

Cortex Sense is how Cortex Code and Snowflake Intelligence understand your data and business. This skill is the **builder experience**: it captures the **domain** (named, persistent), assembles the **domain context** (scope + dashboards + instructions), and hands that context off to the offline **build**. See `reference/USE_CASE_AND_CONTEXT.md` for the vocabulary.

**Builder principle.** CoCo proposes; the builder steers; the build does the heavy lifting. Don't ask the builder to do work CoCo can do, and don't ask CoCo to do work the build is meant to do.

## Seven intents

| Intent | Triggers | Sub-skill |
|---|---|---|
| **list** | "list cortex sense", "show all domains", "what cortex sense do I have", "list all contexts", "what domains exist", "show my contexts", "which cortex senses are set up" | `query/SKILL.md` — list-only path (see below) |
| **setup** | "set up cortex sense", "build context for <use case>", "I want context for sales" | `setup/SKILL.md` |
| **test** | "test the <use case> context", "run questions against sales", "what does the <use case> context know about <table>", "check build", "is the build done?", "@cortex-sense resume <use case>" + a query | `test/SKILL.md` |
| **query** | "query about <X>", "search contexts for <X>", "search across contexts for <X>", "what does cortex sense know about <X>" (no use case named), "which of my contexts know about <X>", "@cortex-sense query <use-case> about <X>" | `query/SKILL.md` |
| **refine** | "refine sales", "the agent picked the wrong table", "DAU is wrong", "exclude staging", "add another schema", "@cortex-sense resume <use case>" + a correction | `refine/SKILL.md` |
| **eval** | "generate eval", "run eval", "diff eval", "score the context", "check answer correctness", "create eval set", "evaluate the context", reply to the setup confirm block with 5–10 test questions, "@cortex-sense resume <use case>" + any eval verb | `eval/SKILL.md` |
| **agent** | "create an agent for <domain>", "create a cowork agent for <domain>", "deploy <domain> as an agent", "make an agent from this context", "add cortex sense to <agent>", "wire <agent> to cortex sense", "enable cortex_sense on <agent>", "@cortex-sense resume <use case>" + an agent verb | `agent/SKILL.md` |

**list-only path:** When the intent is purely to list existing domains (no query or domain name given), route to `query/SKILL.md`. That file's "List-only path" section handles it: it calls `list-contexts` and renders the domain list, then stops. Do **not** route to setup, refine, or any stage path — `SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER list-contexts` is the single authoritative source for registered domains.

Re-entry verb is `@cortex-sense resume <domain>`. CoCo loads the domain's manifest and routes to **test**, **refine**, **eval**, or **agent** based on what the builder says next. If the domain doesn't exist yet, route to **setup**.

The **query** intent is for cross-context search — use it when the builder wants to search across all contexts or query without the full test workflow.

The **agent** intent is the hand-off to consumers: it turns a built context into a CoWork / Snowflake Intelligence agent, or adds Cortex Sense to an agent that already exists. It is the only sub-skill that creates objects outside the context's own storage, so it always confirms the spec before any DDL.

If the user's intent is ambiguous, default to **setup** when no manifest is found, **refine** when one exists and the message reads like a correction, **eval** when one exists and the message reads like validation or scoring, and **agent** when the message names an agent or asks to deploy.

## Skill structure

Top-down map. The router (this file) plus six sub-skills route conversation; reference files are loaded on demand by the sub-skills; `scripts/` is the only load-bearing code.

```
cortex-sense/
├── SKILL.md                        # router (this file) — seven intents
├── pyproject.toml                  # uv-managed deps for scripts/
│
├── setup/SKILL.md                  # name → scan → draft → confirm → save
├── test/SKILL.md                   # spot-check the active context (ad hoc lookup)
├── query/SKILL.md                  # cross-context search (query all or specific contexts)
├── refine/SKILL.md                 # corrections, expansions, updates (folds in the old "debug" flow)
├── eval/SKILL.md                   # generate / run / diff — answer-correctness eval sets (+ efficiency metrics)
├── agent/SKILL.md                  # built context → CoWork agent; or add cortex_sense to an existing agent
│
├── reference/                      # loaded on demand by the sub-skills
│   ├── USE_CASE_AND_CONTEXT.md     # vocabulary: use case / domain context / build
│   ├── DISCOVERY.md                # parallel-discovery contract + verbatim SQL
│   ├── DASHBOARDS.md               # Dashboards row + External tables row (Horizon Context mapping)
│   ├── SCOPE_MANIFEST.md           # manifest YAML shape (sources, concepts/relationships/associations, pending_asks, …)
│   ├── INSTRUCTIONS.md             # internal NL → concepts / relationships / instructions classification
│   ├── SUMMARY_FORMAT.md           # exact narrative summary (rows, order, confirm block)
│   ├── STORAGE.md                  # storage contract: SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER, doctor, persistence registration
│   ├── CONTEXT_LOOKUP.md           # context lookup contract: MCP tool + SQL fallback, rendering, error handling
│   ├── AGENT_SPEC.md               # agent spec contract: the one experimental flag, provisioned tools, doc_types, DDL, CoWork, smoke test
│   ├── ONTOLOGY_DISCOVERY.md       # contract for ontology-aware discovery: matching, script invocation, manifest output
│   ├── ACCESS_PREFLIGHT.md         # build-role read-access preflight (visibility probe + grant remediation)
│   ├── BUILD_STATUS.md             # best-effort `check build` status inference (no true state field yet)
│   ├── LOCAL_FILES.md              # local files & Workspace-backed Streamlit apps → stage
│   ├── EVAL_FORMAT.md              # eval.yaml schema, answer-grading contract, metrics, generation rules
│   └── NOT_YET_IMPLEMENTED.md      # placeholder copy + when each is surfaced
│
└── scripts/                        # invoked by the markdown sub-skills
    ├── persist_state.py            # YAML validation, dedup (merge subcommand), doctor pre-flight
    ├── discover_usage.py           # deep-pass: hot tables + Streamlits + SVs from ACCOUNT_USAGE (SQL-only, 3 parallel queries)
    └── discover_ontology_domains.py  # fast-pass: fetch registered ontology sources for a matched domain
```

A new conversation walks: `SKILL.md` → one of `setup` / `test` / `query` / `refine` / `eval` / `agent` → relevant `reference/*.md` for the contract → SQL (`SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER put-stage-file`) to persist. `persist_state.py merge` runs dedup in-process before the SQL call for scope manifests. Nothing else is in the save path.

`agent` is the one sub-skill whose output is not a stage file — it writes a Snowflake `AGENT` object via DDL. It reads the manifest but never writes one; scope changes still flow through `refine`.

## Out of scope (deliberately)

- **Activate / draft / share-for-review verbs.** The builder confirms a scope; the build runs. Internal versioning is not a builder concern.
- **Picking a routing bucket** (`concepts` vs `relationships` vs `additional_instructions`). The builder writes natural language; CoCo classifies internally.
- **Operator diagnostics** (Cortex search-service previews, task DAG resume). Wrong-answer reports flow through **refine**.
- **Delete / remove a context.** `SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER delete-context` is available (see `reference/STORAGE.md`) but is irreversible and must never be triggered from normal refine or setup flows.

  **⚠️ MANDATORY CHECKPOINT before delete-context:** surface the exact command that will be run and ask:
  > "This will permanently delete the `<domain>` context and its manifest. Type the domain name to confirm, or say cancel."

  Wait for the builder to type the domain name back verbatim. If the response does not match the domain name exactly, stop and do not run the command.

## Persistence

The manifest is persisted as YAML in a Snowflake stage (storage details are intentionally not surfaced to the builder). See `reference/STORAGE.md` for the full contract: location resolution, the doctor pre-flight, stage layout, and the post-save persistence-layer registration call.

## Ontology as a discovery source

During setup, Cortex Sense checks whether any Business Ontology domains are relevant to the current domain. If a match is found, it adds the domain plus its registered stage sources as a single `business_ontology` source; the build then reaches the domain's nodes, relationships, and stage-file contents behind the scenes. See `reference/ONTOLOGY_DISCOVERY.md` for the full contract: matching rules, script invocation, and output shape.

The Ontology is a **consumer dependency at discovery time** — Cortex Sense reads from it; Business Ontology owns all writes. The reverse direction (Cortex Sense proposing improvements back to the Ontology) is the steward-driven `business-ontology/workflow/phase-2-enrich` path; see the enrichment-handoff section of `reference/ONTOLOGY_DISCOVERY.md`.

## Not yet implemented

The skill ships several capabilities as **explicit placeholders**, surfaced to the builder the first time they would otherwise mislead. The full list is in `reference/NOT_YET_IMPLEMENTED.md`. Major ones:

- Build orchestration & the true in-flight build *state field* (running/done/failed). The `check build` verb gives **best-effort** status today by inference — see `reference/BUILD_STATUS.md`.
- Correction propagation across similar tables/metrics
- Native use-case object (replacement for stage-backed YAML)
- Content search of BI objects & external tables (discovery via search is supported; reading their internal queries/fields/row data is not — see `reference/DISCOVERY.md`)
- Horizon Context connector enablement (a platform must be connected to appear in search — Tableau / Power BI / Databricks / SQL Server / Postgres)

## Output

A persisted, versioned manifest for the domain context. See `reference/SCOPE_MANIFEST.md`.

`<WORKSPACE_DIR>` and `<SKILL_DIR>` are placeholders the agent resolves from CoCo's working directory and the current skill location respectively.
