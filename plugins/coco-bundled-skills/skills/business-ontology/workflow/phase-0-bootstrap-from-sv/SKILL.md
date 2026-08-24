---
name: business-ontology-workflow-phase-0-bootstrap-from-sv
description: "Phase 0 (Bootstrap from Semantic Views) of the Business Ontology workflow — the reverse entry point when Semantic Views already exist. Scans the SV estate, resolves each field's domain from column lineage, and proposes draft nodes, RELATED_SEMANTIC_VIEW bindings, and derives relationships for steward approval. Delegates to $business-ontology sv-ingest, then rejoins Enrich/Generate. Parent: business-ontology workflow."
parent_skill: business-ontology-workflow
---

# Phase 0 — Bootstrap from existing Semantic Views (reverse entry)

The define → enrich → generate workflow assumes you start from an ontology. **Most real accounts
already have Semantic Views** (built by hand or Autopilot) before any ontology exists. Phase 0 is
the reverse entry point: it reads that estate and seeds the ontology *from* it, so the account
lands in the same governed state the forward workflow produces.

Use Phase 0 when the steward says "we already have semantic views" / "bootstrap the glossary from
our models" / "find drift between glossary and our SVs". Otherwise skip straight to Phase 1.

## This phase delegates — it does not re-implement

All logic lives in the **`$business-ontology sv-ingest`** sub-skill (`../sv-ingest/SKILL.md`).
Route there and run its `scan → drift → propose → reconcile` flow.

```
Semantic View estate ──sv-ingest──▶ draft nodes + RELATED_SEMANTIC_VIEW bindings + derives
                                     (steward-approved) ──▶ governed ontology
```

## Inputs

```yaml
connection:         # snow CLI connection (blank = CLI default)
database_filter:    # optional — limit scan scope
schema_filter:      # optional
sv_name_pattern: "%"
```

## Steps

1. **Route** to `../sv-ingest/SKILL.md`. Run **scan** → **drift**.
2. **Present the drift worklist** to the steward (sorted BLOCKER → WARN → INFO). This is the
   mandatory checkpoint — the same draft→approve gate used everywhere else in the workflow.
3. On approval, run **reconcile** (draft + approve nodes, associations, `derives` relationships).
4. Re-run **drift** until `BLOCKER = 0` or the steward logs accepted exceptions.

## Handoff

After Phase 0 the ontology is seeded and bound to the existing SVs. Continue the workflow for
anything still ungoverned:

- **Enrich** (`../phase-2-enrich/SKILL.md`) — add AI-proposed nodes/links and Cortex Sense evidence.
- **Generate** (`../phase-3-generate/SKILL.md`) — for domains that still need a Semantic View.

Report:

```yaml
phase_0_complete:
  semantic_views_scanned: <count>
  terms_drafted: <count>
  terms_approved: <count>
  sv_bindings_approved: <count>
  drift_blockers_remaining: 0
  next_phase: enrich | generate | done
```

## Boundaries

- Route to `$business-ontology sv-ingest` for implementation — do not duplicate its scripts or SQL here.
- Require explicit steward approval before any approve call (no auto-approve).
- `DESC SEMANTIC VIEW` is the source of truth for expressions.
- Use only documented `SYSTEM$..._GLOSSARY_*` functions from `../../reference/API_CONTRACT.md`.
