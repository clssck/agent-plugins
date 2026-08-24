---
name: cortex-sense-refine
description: "Refine an existing Cortex Sense use case: capture corrections, declared facts, scope changes, and term mappings in plain English; classify and persist; tell the builder what was recorded. Wrong-answer reports flow through here. Use when: the agent picked the wrong table, DAU is wrong, exclude staging, add another schema, change the lookback, treat X as Y. Triggers: refine cortex sense, refine <use case>, the agent picked the wrong table, DAU is wrong, missing entity, context is stale, why did it pick X, exclude staging, @cortex-sense resume <use case> + a correction."
parent_skill: cortex-sense
---

# Refine

## When to load

The user wants to correct, expand, or update an existing domain context. Routed from `SKILL.md`. If no manifest exists for the domain, route to `setup/SKILL.md`.

This sub-skill folds in the previous `debug` flow: a wrong-answer report **is** a correction. There is no separate diagnostic taxonomy.

## Setup

Read once before mutating state:

- `../reference/INSTRUCTIONS.md` — how to classify builder prose into the right manifest slot
- `../reference/SCOPE_MANIFEST.md` — manifest shape
- `../reference/SUMMARY_FORMAT.md` — narrative summary
- `../reference/NOT_YET_IMPLEMENTED.md` — exact placeholder lines (notably: feedback-storage flags, propagation)
- `../reference/CONTEXT_LOOKUP.md` — lookup contract for the pre-correction diagnostic step (§1b)

`<WORKSPACE_DIR>` and `<SKILL_DIR>` are placeholders the agent resolves.

## 0. Pre-flight (run once before any subprocess)

Before the first `persist_state.py` call, run `doctor` once. Handle the three branches exactly as `../setup/SKILL.md` §1 does (full contract in `../reference/STORAGE.md`):

```bash
uv run --project <SKILL_DIR>/.. python <SKILL_DIR>/../scripts/persist_state.py doctor
```

- **`snow_cli == "missing"`** → install line and stop.
- **`needs_database_schema: true`** → ask once for a database and schema, set `CORTEX_SENSE_DB` / `CORTEX_SENSE_SCHEMA`, then re-run `doctor`. **Never** mention env-var names to the builder.
- **Otherwise** → continue silently.

The user should never see `snow` tracebacks, "stage format" errors, raw tool traces, bash/python stack traces, validator error details, or internal step commentary. If a save or load fails with no recovery path, render a single plain-English sentence and stop.

## Load the latest manifest

Use `get-stage-file` per `../reference/STORAGE.md` "Loading — one call". The SQL handles both legacy base64-encoded files and new plain-YAML files automatically.

If the load returns no manifest, route to `../setup/SKILL.md`.

## 1. Show what's there

Render the scope box per `../reference/SUMMARY_FORMAT.md`, built from the **loaded manifest** (not a fresh scan). Map the stored fields onto the INCLUDE/EXCLUDE blocks so the summary is as rich as what's in the manifest — render every source that has data, omit only empty ones. The Optional section renders when `pending_asks` is non-empty. The footer bar uses the refine trailing prompt (`type a change, or: **done**`) — not the setup footer.

Render the INCLUDE block from manifest fields in this order; EXCLUDE block from any `excluded: true` rules:

| INCLUDE source label | Manifest field(s) |
|---|---|
| `Tables` | `sources[catalog_objects].rules` — one indented line per included `pattern` (with `est_tables` count if present) |
| `Semantic Views` | `sources[semantic_views]` rules |
| `Streamlit Apps` | `streamlit_apps` (source code) and/or `streamlit_apps_metadata` (metadata) |
| `External Tables` | enabled `horizon_context` DB sources (`databricks`, `sqlserver`, `postgres`, `redshift`) |
| `External Dashboards` | enabled `horizon_context` BI sources (`tableau`, `powerbi`, `sigma`, `looker`) |
| `Tags` | `tag` rules |
| `Ontology` | `sources[business_ontology]` rules — show `node_count`, `relationship_count`, `association_count`, `source_file_count` if stored; otherwise run Step 1b from `ONTOLOGY_DISCOVERY.md` (`SYSTEM$GET_GLOSSARY_GRAPH()` filtered by `domainId`) — `GET_GLOSSARY_SUMMARY` only returns `termCount` and must not be used for Relationships or Associations |
| `dbt` | `dbt_projects` file rules |
| `Files` | `stage_files` file rules |
| `Definitions` | `concepts` + `relationships` + `associations` |
| `Instructions` | `additional_instructions` |
| *Optional section* | `pending_asks` — one line per ask, including `dbt` manifest path if no dbt file rule is present in the scope |

| EXCLUDE source label | Manifest field(s) |
|---|---|
| `Tables` | `sources[catalog_objects].rules` where `excluded: true` |

If the builder asks for detail, render the **Expanded view** from `../reference/SUMMARY_FORMAT.md` (full per-rule `user_prompt` lines + any `pending_asks`). Then:

```
type a change, or: **done**
```

Examples of changes the builder might make (do **not** show this list to the user; it's a CoCo-facing reminder):

- Scope: "exclude staging", "add `SALES.ORDERS.*`", "include only sales tables", "ignore dev"
- Definitions: "DAU is COUNT(DISTINCT user_id)", "ARR means …"
- Links: "ARR lives in `ANALYTICS.MARTS.FACT_ARR`"
- Connections: "revenue is the same as GAAP_REVENUE"
- Settings: "7 day access history", "dbt at @DB.SCHEMA.STAGE/target/manifest.json"
- Wrong-answer reports: "the agent picked `SALES.STAGING.OPPS` for pipeline yesterday — it should use `SALES.DATA.OPPORTUNITIES`"
- Procedural: "treat house campaigns as non-client-serving", "default to ARR when someone says revenue"

## 1b. Diagnose before correcting (optional, automatic)

When the builder's input is a **wrong-answer report** (e.g. "the agent picked `SALES.STAGING.OPPS` for pipeline — it should use `SALES.DATA.OPPORTUNITIES`", "why did it pick X?", "it got the grain wrong"), proactively run a context lookup **before** recording the correction.

Extract the table name or concept from the report (e.g. `SALES.STAGING.OPPS`, `SALES.DATA.OPPORTUNITIES`, or the concept being asked about), then follow the lookup contract in `../reference/CONTEXT_LOOKUP.md`.

Prefix the result with one line:

```
Here is what the context currently knows about <name>:
```

Then render the documents per the contract. This grounds the correction: the builder sees the actual context document and can give a more precise instruction (e.g. "yes, the grain is wrong — it should be order-level, not order-line").

**This step is optional and non-blocking.** If the lookup returns nothing or errors (including the dead-end from `../reference/CONTEXT_LOOKUP.md` when neither the MCP tool nor SQL fallback is available), skip it silently and go straight to "2. Classify and echo". Do not ask the builder whether to run the lookup — just do it and suppress failures. If Signal A fires during this lookup (wrong-account detection — see `../reference/CONTEXT_LOOKUP.md` "Wrong-account detection"), set `mcp_wrong_account = true` for the rest of the session before suppressing the result.

## 2. Classify and echo

**Route to named branches first** before the general classifier:

| Trigger | Route to |
|---|---|
| `clean up`, `deduplicate`, `remove staging`, `remove low-quality sources` | [Scope clean-up](#scope-clean-up) below |
| `deeper` | `setup/SKILL.md §5 Branch: deeper` (same heuristic; re-render after) |
| `help` | `setup/SKILL.md §9 Branch: help` (contextual improvement card) |
| `build`, `ok`, `go`, `yes` | § 6. Save |

For all other free-text input, classify per `../reference/INSTRUCTIONS.md`. Update local state. Render the **echo line** for the change (single sentence, present tense). Then re-render the summary if the change is structural; otherwise just echo.

On every re-render, apply the same post-fence checks as `setup/SKILL.md §4`: staging advisory (flag `Tables` patterns matching `*.STG.*`, `*.STAGING.*`, `*_STG`, `*_DEV`, `*.RAW.*`, `*_TEMP`; skip EXCLUDE-covered rules) and empty-sources note (per `../reference/SUMMARY_FORMAT.md` "Empty row handling — two cases").

Examples:

> Builder: *"DAU is COUNT(DISTINCT user_id)"*
> CoCo: *"Recorded: DAU defined as `COUNT(DISTINCT user_id)` (metric)."*

> Builder: *"exclude staging and dev in ANALYTICS"*
> CoCo: *"Updated scope: excluding `ANALYTICS.STAGING.*` and `ANALYTICS.DEV_*.*`."*

> Builder: *"the agent picked `SALES.STAGING.OPPS` for pipeline yesterday"*
> CoCo: *"Recorded: exclude `SALES.STAGING.*` from sales scope. The active context will reflect this on the next build."*

> Builder: *"exclude tables in any schema matching DEV or STAGING"*
> CoCo: *"Updated scope: excluding `*.*DEV*.*` and `*.*STAGING*.*`."*

## 3. Conflict check

Before appending, scan for contradictions. The full table is in `../reference/INSTRUCTIONS.md` ("Conflict handling"). Quick-reference:

| New input | Conflicts with | Action |
|---|---|---|
| `concept` named X with new definition | Existing `concept` X with different formula | Show both; ask which is canonical. Mark old `superseded_by` new. |
| Exclusion pattern overlapping an inclusion | An overlapping include rule | One `COUNT(*)` against `INFORMATION_SCHEMA` to estimate impact; confirm with "this hides ~N tables — OK?" |
| Same `user_prompt` already present | Exact duplicate | Skip silently; tell the user "already recorded". |

## 4. Set provenance on every recorded item

Every entry written by this sub-skill must carry a `provenance` block. See `../reference/SCOPE_MANIFEST.md` "Provenance" for the full shape. Assign `state` and `origin` as follows:

| Situation | `state` | `origin` |
|---|---|---|
| Builder stated this explicitly ("DAU is …", "exclude staging") | `approved` | `declared-by-user` |
| CoCo classified the input without prompting the builder | `needs-feedback` | `inferred` |
| CoCo showed the inference to the builder (e.g. conflict resolution prompt) and builder confirmed | `approved` | `inferred-shown-to-user` |
| CoCo showed the inference but builder has not yet confirmed | `needs-feedback` | `inferred-shown-to-user` |

Always set `recorded_at` to the current ISO-8601 timestamp. Populate `initiated_by` when the builder's identity is known. Populate `sources` when the inference has traceable sources (e.g. `type: user_message` with the triggering quote, `type: trajectory` with the step reference).

`pending_asks` entries always use `state: needs-feedback`. When the builder responds, remove the ask from `pending_asks` and add the classified entry to the correct field with `state: approved`.

## 5. Surface placeholder copy when relevant

Append the matching line from `../reference/NOT_YET_IMPLEMENTED.md` exactly **once per session** per capability — not after every recorded change. The most relevant lines for refine:

- After a correction that *could* propagate (item 3):
  > *(Propagation across similar metrics is not yet implemented — recorded as a single declared fact.)*
- Only if the builder asks to share or hand off (item 8):
  > *(Hand-off and delegation are not yet implemented. For now, share the domain name with your reviewer; they can run `@cortex-sense resume <domain>`.)*

## 5b. Promote to Business Ontology

When the builder explicitly says "promote to glossary", "add to glossary", "push to ontology", "add this/these to the glossary", "suggest for the glossary", "add these concepts to glossary", "promote this domain to ontology", or any unambiguous phrasing that moves Cortex Sense content into Business Ontology — **do not record this as a correction**; route to `$business-ontology` instead.

**Pre-flight: check `ontology_available`.** If the session-level flag (see `../reference/CONTEXT_LOOKUP.md` "Ontology availability — session-level flag") is `false`, surface **once** and stop:
```
(Business Ontology is not enabled on this account — contact your account admin to enable it.)
```

**Two scope cases:**

1. **Full manifest** — builder says "promote all", "promote this domain", "promote everything", or an unqualified "promote this to the ontology" with no specific item named:
   - Say: "Routing to Business Ontology to promote the `<domain>` context."
   - Route to `$business-ontology` with the intent "promote Cortex Sense context for `<domain>`" and `target_domain_hint: <domain>`.
   - BG `import/SKILL.md` Path D loads the manifest, extracts concepts + relationships, deduplicates against existing nodes, and presents the review/approve table.

2. **Specific named items** — builder names a concept or relationship ("add ARR to ontology", "add ARR to glossary", "promote the revenue–GAAP_REVENUE relationship", "add DAU, MAU, ARR to ontology"):
   - Extract those entries from the already-loaded in-memory manifest (no new reads).
   - Say: "Routing to Business Ontology to add `<name(s)>`."
   - Route to `$business-ontology` passing the extracted entries as structured inline data. BG `import/SKILL.md` Path C handles them directly (no AI extraction). For a single item, BG may route to `create/SKILL.md`; let BG's router decide.

Cortex Sense does nothing further after the handoff. All draft, dedup, review, and approval logic lives in the BG skill.

> ⚠️ **STOP** — only proceed to §6 after the builder explicitly signals they are finished (types **done**, **save**, or an equivalent). Do not save speculatively.

## 6. Save

When the builder says **done** (or otherwise signals they're finished):

Assemble the manifest as YAML in-memory (status: active). The top-level `warehouse` field is **required**: if the loaded manifest already has one, keep it; if it is missing (e.g. an older manifest), resolve it with `SELECT CURRENT_WAREHOUSE()` and set it — when the session has no active warehouse, ask the builder to name one before saving (same handling as `setup/SKILL.md` §6). Pipe the manifest through `scripts/persist_state.py merge` (deduplicates `additional_instructions`, validates). Then run two SQL calls per `../reference/STORAGE.md` "Saving — two calls in sequence":
- **create-context** (or "already exists" → treat as success).
- **put-stage-file** (path: `scope.yaml`, content: JSON-escaped YAML, overwrite: true).

On any error, render the one-line warning from `../reference/STORAGE.md` and stop.

Then call `force-reprocess` per `../reference/STORAGE.md` "Force-reprocessing a context". This is non-blocking — if it fails, continue without surfacing the error to the builder.

There is no "save as draft" step. There is no "activate now" prompt. The builder confirmed by typing the changes; the save is silent and immediate.

Render the final summary per `../reference/SUMMARY_FORMAT.md`, followed by:

```
Saved. Build triggered — changes will apply when the build completes.
```

## Scope clean-up (trigger: "clean up", "deduplicate", "remove staging")

Run the two heuristics from `setup/SKILL.md §9 Branch: clean up`: (1) flag staging-name patterns; (2) flag include/exclude overlap. Surface findings as an advisory block outside the scope box fence; never auto-remove. If nothing found: `Scope looks clean — no obvious staging or redundant patterns found.`

## What this skill never does

- Render the layered debug taxonomy ("Layer 1 / Layer 2 / QBE / instruction gap")
- Run `SHOW TASKS` / `ALTER TASK ... RESUME` / `SEARCH_PREVIEW` SQL
- Ask the builder to pick `concepts` vs `relationships` vs `additional_instructions`
- Surface `draft` / `active` / `version_id`
- Offer "share for review" with stage paths
- Show raw tool traces, `snow sql` output, bash/python stack traces, or `persist_state.py` validator detail lines in the conversation
- Narrate internal retry attempts, pass-by-pass fallback logic, or connection debugging steps
- Surface messages about `INVALID_ARGUMENT`, `stage format` errors, or internal storage mechanics
- Show CoCo's own reasoning steps or intermediate tool results inline
