---
name: business-ontology
description: "Create and manage Business Ontology nodes, domains, relationships, and Snowflake object associations — individually or via bulk import with AI extraction. Also owns source registration: track stage files and prefixes as ontology sources, run imports from them, and expose those sources to Cortex Sense for enrichment."
---

# Business Ontology

The Business Ontology is where builders define canonical business nodes, describe how they relate to each other, and link them to the Snowflake objects that implement them. This skill is the **builder experience** for that workflow: it supports creating items one at a time, importing them in bulk from a file, promoting an existing Cortex Sense context, and registering stage files and prefixes as durable ontology sources that Cortex Sense can later enrich.

## Triggers

`create glossary term` · `add ontology node` · `add a domain` · `add term to <domain>` · `define relationship between X and Y` · `associate table X with term` · `import ontology from file` · `extract glossary terms from this doc` · `bulk add terms` · `promote to glossary` · `import from semantic views` · `bootstrap ontology from our SVs` · `find drift between ontology and semantic views` · `register ontology source` · `extract terms from our tables` · `import from dbt` · `delete domain` · `remove domain` · `rename domain` · `rename X to Y` · `clean up domain`

`govern how X is defined` · `govern our metrics` · `govern the semantic layer` · `standardize terminology` · `canonical definition` · `single source of truth for X` · `shared vocabulary` · `what does X mean in our business` · `governed semantics`

`business ontology` · `business taxonomy` · `data dictionary` · `knowledge graph` · `domain model` · `semantic governance` · `metadata governance`

> **Routing boundary:** Phrases about governing *what concepts mean* → this skill. Phrases about configuring *which tables/schemas Cortex sees* for a specific use case → `$cortex-sense`. Example: `"govern how Revenue is defined"` → here. `"add our Revenue table to Cortex Sense"` → cortex-sense.

## Intents

| Intent | Triggers | Sub-skill |
|---|---|---|
| **create** | "create glossary term", "add a domain", "add term to Purchasing", "define relationship between X and Y", "associate table X with term Y", "link column to term" | `workflow/create/SKILL.md` |
| **import** | "import glossary from file", "upload CSV", "extract ontology terms from this doc", "bulk add terms", "import from stage" | `workflow/import/SKILL.md` |
| **discover relationships** | "find more relationships", "dig deeper", "what relationships are missing", "complete the graph", "find missing edges" | `reference/RELATIONSHIP_DISCOVERY.md` |
| **extract (tables)** | "extract terms from our tables", "discover glossary from schema", "scan INFORMATION_SCHEMA for terms", "what business concepts are in \<schema\>?" | `workflow/import/SKILL.md` Path C (via `scripts/table_term_extractor.py`) |
| **extract (dbt)** | "import from dbt", "parse dbt manifest", "extract glossary from dbt manifest", or user provides a `manifest.json` path | `workflow/import/SKILL.md` Path D (via `scripts/dbt_manifest_parser.py`) |
| **extract (SVs)** | "extract from semantic views", "scan SVs for concepts", "import from SVs", "what business concepts are in our semantic views?" | `workflow/import/SKILL.md` Path H (via `scripts/sv_concept_extractor.py` + `scripts/batch_import.py`) |
| **promote** | "promote this to the ontology", "promote Cortex Sense context to glossary", "add my Cortex Sense concepts to the glossary" | `workflow/import/SKILL.md` Path E (cortex-sense promotion) |
| **delete** | "delete domain", "remove domain", "delete term", "delete relationship", "clean up domain", "delete all terms in X" | `workflow/delete/SKILL.md` |
| **rename** | "rename domain", "rename X to Y", "move domain to new name" | `workflow/delete/SKILL.md §Rename domain` |
| **workflow** | "business ontology workflow", "define enrich generate", "glossary to semantic view", "governed semantics rollout", "ontology cortex sense integration" | `workflow/SKILL.md` |
| **sv-ingest** | "import glossary from semantic views", "bootstrap ontology from our SVs", "scan semantic view estate", "SV to ontology", "we already have semantic views — start governance", "find drift between glossary and semantic views" | `workflow/sv-ingest/SKILL.md` |
| **source** | "register ontology source", "add stage file to glossary", "add source to <domain>", "track stage prefix for ontology", "list ontology sources", "import from registered source", "pause source" | `workflow/source/SKILL.md` |

If the user's intent is ambiguous, ask once with the options above.

## Skill structure

```
business-ontology/
├── SKILL.md                    # router (this file)
├── pyproject.toml              # uv-managed deps for scripts/
├── workflow/
│   ├── SKILL.md
│   ├── create/SKILL.md             # add individual nodes, domains, relationships, asset associations
│   ├── import/SKILL.md             # bulk import from file + AI extraction + candidate review
│   ├── delete/SKILL.md             # delete/cascade domains and nodes; rename domain workaround
│   ├── source/SKILL.md             # register/list/update stage sources; import from registered source
│   ├── sv-ingest/
│   │   ├── SKILL.md                # reverse ingest: Semantic View estate → draft nodes + bindings + drift
│   │   ├── domain_map.example.yaml # SV location → domain (fallback only; lineage wins)
│   │   ├── examples/               # messy-estate lab SQL for end-to-end validation
│   │   └── reference/              # SV↔ontology mapping contract + drift classification
│   ├── phase-0-bootstrap-from-sv/SKILL.md  # reverse entry — routes to sv-ingest
│   ├── phase-1-define/SKILL.md
│   ├── phase-2-enrich/SKILL.md
│   └── phase-3-generate/SKILL.md
├── scripts/
│   ├── ontology_source_registry.py  # CRUD for the Snowflake-stage registry (TEMPORARY — until native backend storage)
│   ├── ontology_sources.yaml        # schema template / seed for the stage registry (not used at runtime)
│   ├── table_term_extractor.py      # scan INFORMATION_SCHEMA comments → node candidates (bridge until Cortex Sense backend)
│   ├── dbt_manifest_parser.py       # parse dbt manifest.json → node candidates (bridge until Cortex Sense backend)
│   ├── sv_common.py                 # sv-ingest: snow/JSON helpers, lineage extraction
│   ├── sv_estate_scan.py            # sv-ingest: SHOW/DESC scan → candidates + lineage + VQRs
│   ├── sv_concept_extractor.py      # Path H: SV estate → scored, deduped business concepts (cross-SV dedup, noise filter, VQR scoring)
│   ├── batch_import.py              # fast batched import: draft + approve + associate in batches of 50
│   └── sv_drift_report.py           # sv-ingest: resolution ladder → steward-ready findings
└── reference/
    ├── API_CONTRACT.md                    # index → load READ or CRUD sub-file as needed
    ├── API_CONTRACT_READ.md               # GET + draft-inspection functions
    ├── API_CONTRACT_CRUD.md               # domain/term/rel/asset mutations + deletes
    ├── CORTEX_SENSE_MANIFEST_CONTRACT.md  # manifest fields consumed by the cortex-sense promotion path
    ├── EXTRACTION_SOURCES.md              # catalog of extraction sources (stage, SV, table, dbt, Cortex Sense)
    ├── PREFLIGHT.md                       # pre-flight checks (feature gate, role, ontology snapshot, pending drafts)
    ├── RELATIONSHIP_TYPES.md              # full vocabulary of relationship types with disambiguation guide
    ├── SUMMARY_FORMAT.md                  # canonical render templates for displaying items to the builder
    └── VALIDATION.md                      # per-phase and full-workflow validation steps
```

Reference files are loaded on demand. Node/domain/relationship mutations go through SYSTEM$ SQL calls. Source registry mutations go through `scripts/ontology_source_registry.py`.

## Backend model

Every mutation uses a **draft-activate workflow**:
1. `SYSTEM$DRAFT_*` creates a pending draft suggestion — user-facing state: **DRAFT**.
2. `SYSTEM$APPROVE_*` promotes it to a canonical ontology record (node / relationship / association) — user-facing state: **ACTIVE** (the underlying API field value is `APPROVED`).
3. `SYSTEM$APPROVE_ALL_*` batch-activates all pending drafts of a given type (prefer the scoped form with explicit IDs).

Users can choose to **make active immediately** (default — draft + approve in one step, transparent to the user) or **save as draft** for later review. In the **import** flow, this maps naturally onto the review step: draft all extracted candidates, then activate selectively, in bulk, or leave as drafts.

**Default domain:** When a node's domain is unclear or the concept is generic, use `"Core"` as the domain name. This catch-all domain prevents nodes from being blocked on domain assignment.

## Terminology

> **User-facing language uses "node"** (the ontology abstraction). The underlying API retains `TERM` / `GLOSSARY_TERM` for backward compatibility — `SYSTEM$DRAFT_GLOSSARY_TERM`, `itemKind: TERM`, etc. are API identifiers, not product names. Trigger phrases intentionally keep "glossary" (e.g. `"import glossary from file"`) because that is what users naturally say; the product name is "Business Ontology." 

## Feature gate

All functions require Business Ontology to be enabled on the account. If any call returns a feature-gate error, surface once:

> *(Business Ontology is not yet enabled in this account — contact your account admin to enable it (`FEATURE_BUSINESS_GLOSSARY`).)*

## Read-only exploration

For ad-hoc exploration beyond what builder workflows expose, direct SYSTEM$ calls are available:

- **Account-wide graph.** `SYSTEM$GET_GLOSSARY_GRAPH()` returns all approved domains, nodes, relationships, and associations in one call — useful for cross-domain drift detection or visualization. See `reference/API_CONTRACT_READ.md`.
- **Relationship traversal.** `SYSTEM$GET_GLOSSARY_TERM('<name>')` returns an inline `relationships` array for a single node. There is no standalone `SYSTEM$GET_GLOSSARY_TERM_RELATIONSHIPS` function.

## Out of scope (deliberately)

- **Browse / node detail view.** Read-only listing is not a builder-facing workflow here. Use `SYSTEM$GET_GLOSSARY_TERM_LIST` / `SYSTEM$GET_GLOSSARY_TERM` or the Snowflake UI directly.
- **Deprecation / deletion.** To retire a node, prefer the **soft-delete**: `SYSTEM$UPDATE_GLOSSARY_TERM('<termId>', '{"status": "DELETED"}')` — reversible and leaves a tombstone. A **hard-delete** via `SYSTEM$DELETE_GLOSSARY_TERM` is also available for permanent removal. Full cascade (domain → all nodes → relationships → associations) is handled by `workflow/delete/SKILL.md`.

For the full list of planned features, missing APIs, and gaps, see `reference/NOT_IMPLEMENTED_YET.md`.
