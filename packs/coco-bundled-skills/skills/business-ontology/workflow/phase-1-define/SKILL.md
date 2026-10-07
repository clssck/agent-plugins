---
name: business-ontology-workflow-phase-1-define
description: "Phase 1 (Define) of the Business Ontology workflow — stewards author or import canonical business meaning. Routes to $business-ontology import and create. Parent: business-ontology workflow."
parent_skill: business-ontology-workflow
---

# Phase 1 — Define

Stewards establish **canonical** business meaning: domains, nodes, metrics, and relationships.

## Inputs

```yaml
primary_domain: string
secondary_domain: string             # optional
import_source: string                # optional — stage URI (Path A/B) or extraction source key (C, D)
extraction_sources: list[string]     # optional — source keys from EXTRACTION_SOURCES.md (C, D, E)
```

Skip BYO import when both `import_source` and `extraction_sources` are omitted.

## Step 0 — Pre-flight (skip if workflow/SKILL.md already ran it this session)

If entering Phase 1 directly (not via the full workflow), run all checks in
`../../reference/PREFLIGHT.md`. Display the compact snapshot block and proceed unless Check 1
(feature gate) fails.

## Step 1 — Confirm steward context

Pre-flight already ran `SELECT CURRENT_ROLE()` and `SYSTEM$GET_GLOSSARY_SUMMARY()` (see `../../reference/PREFLIGHT.md` Checks 1 and 2). If entering Phase 1 directly without going through the full workflow, run Step 0 above first — do not re-inline those queries here.

Surface the resulting role and ontology counts before any mutations.

## Step 2 — Import or extract existing definitions (optional)

When `import_source` or `extraction_sources` are set, route to the appropriate source per
`../../reference/EXTRACTION_SOURCES.md`:

**Stage file (`import_source` is a stage URI):**

```yaml
source_type: stage_file
stage_path: <import_source>
target_domain_hint: <primary_domain>
ai_extraction: true
```

Route to `$business-ontology import` — the import sub-skill handles Path A (structured) or B
(AI extraction). It also registers `import_source` in the ontology source registry
(idempotent on stage URI). See `../source/SKILL.md`.

**Extraction source (key from `extraction_sources`):**

For each key in `extraction_sources`, follow the invocation in
`../../reference/EXTRACTION_SOURCES.md` for that source. Pass the resulting candidate JSON to
`$business-ontology import` Path C (structured inline data). Merge all source outputs and
deduplicate before presenting the combined review table.

After steward review, approve using production batch APIs:

```sql
-- Scoped approval (preferred when reviewing a subset):
CALL SYSTEM$APPROVE_ALL_GLOSSARY_TERMS('["<termId1>","<termId2>"]');

-- Or approve all pending nodes in the account:
CALL SYSTEM$APPROVE_ALL_GLOSSARY_TERMS();
```

Verify:

```sql
CALL SYSTEM$GET_GLOSSARY_TERM_LIST('<primary_domain>', 'TERM');
```

## Step 3 — Author or extend nodes

Route to `$business-ontology create` for at least one steward-authored item the user names (or a high-value metric in `<primary_domain>` such as `Operating Margin`).

Use `SYSTEM$CREATE_GLOSSARY_DOMAIN`, `SYSTEM$DRAFT_GLOSSARY_TERM`, and `SYSTEM$APPROVE_GLOSSARY_TERM` via the create sub-skill — do not hand-roll payloads; follow `../../reference/API_CONTRACT.md`.

Optionally define a node-to-node relationship immediately after approval.

## Step 4 — Validate

Run Phase 1 validation from `../../reference/VALIDATION.md` "Phase 1 validation". If the
validation query returns an empty `terms` array, warn and offer to re-run Steps 2–3 before
advancing.

## Step 5 — Self-check

Before returning the summary, confirm:

- [ ] At least 1 domain created or confirmed
- [ ] At least 1 ACTIVE node in `<primary_domain>`
- [ ] No pending DRAFT nodes left unintentionally (if any, ask steward whether to approve or leave)
- [ ] All import failures noted in the summary (domain-not-found, API errors)

If any checkbox fails, surface it as a warning in the summary — do not silently ignore.

## Step 6 — Return summary

```yaml
phase_1_complete:
  terms_imported: <count>
  terms_created: <count>
  domains: [<primary_domain>, ...]
  relationships_created: <count>
  extraction_sources_used: [<list of source keys>]
  next_phase: enrich
```

Return this to `workflow/SKILL.md`. The gate question ("continue to Phase 2?") is asked by the
workflow orchestrator, not here.

## Boundaries

- No asset associations (phase 2)
- No Semantic View creation (phase 3)
- Do not run extraction sources not listed in `../../reference/EXTRACTION_SOURCES.md`
