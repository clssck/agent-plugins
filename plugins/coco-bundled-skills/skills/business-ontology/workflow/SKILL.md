---
name: business-ontology-workflow
description: "End-to-end Business Ontology workflow: define governed nodes, enrich with Cortex Sense and multiple extraction sources, generate Semantic Views, and consume via Cortex Analyst. Orchestrates $business-ontology, $cortex-sense, $semantic-view, and $semantic_studio in a 3-phase sequence. Use when: rolling out governed business semantics, connecting the ontology to Semantic View Autopilot, or onboarding stewards to the full define → enrich → generate path. Triggers: business ontology workflow, glossary to semantic view, define enrich generate, governed semantics workflow, glossary cortex sense integration."
parent_skill: business-ontology
---

# Business Ontology Workflow

Roll out governed business meaning in three phases: **define** canonical nodes, **enrich** with
AI proposals and extraction sources, **generate** Semantic Views and consume them through Cortex
Analyst.

This sub-skill **orchestrates** existing Cortex Skills. It does not re-implement ontology CRUD,
Cortex Sense, Semantic Views, or Semantic Studio.

## Execution order

Run steps in this sequence. Each step must complete before the next begins.

1. **Pre-flight** — run `../reference/PREFLIGHT.md` (feature gate, role, ontology snapshot, pending drafts). Stop if feature gate fails; do not proceed to any further step.
2. **Scope collection** — collect `workflow_inputs`, confirm with steward (see Step 0b below).
3. **Phase 0 Bootstrap** (conditional) — run `phase-0-bootstrap-from-sv/SKILL.md` only if SVs already exist or the builder says "bootstrap from SVs" / "we already have semantic views". Gate required after it completes before Phase 1.
4. **Phase 1 — Define** — run `phase-1-define/SKILL.md`. Validate via `../reference/VALIDATION.md §Phase 1`. Gate required before Phase 2.
5. **Phase 2 — Enrich** — run `phase-2-enrich/SKILL.md`. Validate via `../reference/VALIDATION.md §Phase 2`. Gate required before Phase 3.
6. **Phase 3 — Generate** — run `phase-3-generate/SKILL.md`. Validate via `../reference/VALIDATION.md §Phase 3`. Emit full-workflow summary.

**Gate rule:** between every phase, ask exactly once:
```
Phase <N> complete — continue to Phase <N+1>? (yes / pause / skip to phase N+2)
```
On **pause**: stop and retain `workflow_inputs` in context. On **skip**: jump to the named phase. Never auto-advance.

## Phases

| Phase | Outcome | Routes to |
|---|---|---|
| **Bootstrap** (optional, reverse entry) | Seed ontology + bindings from existing Semantic Views | `$business-ontology sv-ingest` |
| **Define** | Domains, nodes, relationships | `$business-ontology create`, `$business-ontology import` |
| **Enrich** | AI-proposed nodes and asset links | `$cortex-sense`, `$business-ontology import` |
| **Generate** | Semantic Views + Analyst consumption | `$semantic-view creation`, `$semantic-view debug`, `$semantic_studio semantic_view` |

**Two directions, one workflow.** Define → Enrich → Generate is the **forward** path
(ontology → Semantic View). **Phase 0 Bootstrap** is the **reverse** path (Semantic View →
ontology) for accounts that already have SVs; it seeds the ontology, then rejoins Enrich/Generate.
Both use the same steward draft→approve gate.

**Skill disambiguation:** Use `$semantic-view` for Autopilot creation and Cortex Analyst debug. Use `$semantic_studio semantic_view` for inline SV editing in Studio after bindings exist. (`semantic_studio` uses underscore — this is the registered skill name, not a typo.)

Known production gaps (simulated workarounds, missing batch APIs): `../reference/NOT_IMPLEMENTED_YET.md`.

## Invocation

| Mode | Trigger |
|---|---|
| Full workflow | `$business-ontology workflow` |
| Single phase | `$business-ontology workflow bootstrap` · `define` · `enrich` · `generate` |
| Reverse entry (SVs exist) | `$business-ontology workflow bootstrap` → `phase-0-bootstrap-from-sv/SKILL.md` |

## Prerequisites

Install the orchestrated skills:

```bash
cortex code skills install --skill business-ontology
cortex code skills install --skill cortex-sense
cortex code skills install --skill semantic-view
cortex code skills install --skill semantic_studio
```

Ontology SQL signatures live in `../reference/API_CONTRACT.md`.

## Step 0 — Pre-flight

Run all checks in `../reference/PREFLIGHT.md` before collecting workflow inputs. Display the
compact snapshot block (role, domains, nodes, pending drafts prompt if any). Only continue if
Check 1 (feature gate) passes.

## Step 0b — Route and scope

- **Do Semantic Views already exist for this domain?** If yes (or the user says "bootstrap from
  our SVs" / "we already have semantic views"), start at **Phase 0 Bootstrap** →
  `phase-0-bootstrap-from-sv/SKILL.md`, which routes to `$business-ontology sv-ingest`. It seeds
  the ontology from the estate, then continues with Enrich/Generate for anything still ungoverned.
- Full run → all three forward phases with gates between each.
- `bootstrap` → `phase-0-bootstrap-from-sv/SKILL.md`
- `define` / `enrich` / `generate` → `phase-1-define/SKILL.md`, `phase-2-enrich/SKILL.md`, or `phase-3-generate/SKILL.md`

Collect once (skip provided fields):

```yaml
workflow_inputs:
  primary_domain:          # e.g. "Finance"
  secondary_domain:        # optional
  import_source:           # optional — stage path for bulk import (Path A/B)
  extraction_sources:      # optional — list from EXTRACTION_SOURCES.md (C, D, E, F)
  cortex_sense_manifest:   # optional — stage path for Cortex Sense promotion (Path E)
  semantic_view_fqn:       # required for generate, e.g. MY_DB.MY_SCHEMA.MY_SV
  source_tables:           # optional — tables for Semantic View creation
```

Confirm with the user before phase 1:

```
Business Ontology Workflow
  Domains:   {primary_domain}, {secondary_domain or "—"}
  Sources:   {extraction_sources or "none specified — will ask per phase"}
  Phases:    Define → Enrich → Generate

Proceed? (yes / adjust)
```

Wait for confirmation. On **adjust**, re-collect `workflow_inputs`.

## Step 0c — Bootstrap from Semantic Views (optional, reverse entry)

Only when SVs already exist. Route to `phase-0-bootstrap-from-sv/SKILL.md` → `$business-ontology
sv-ingest`. Run scan → drift, present the steward worklist, reconcile approved findings. Summarize
what was seeded/bound.

Then ask the gate question (per Global gate rule):

```
Phase 0 complete — continue to Phase 1 (Define)? (yes / pause / skip to phase 2)
```

## Step 1 — Define

Route to `phase-1-define/SKILL.md`.

When the phase returns its summary, present the gate question:

```
Phase 1 complete — continue to Phase 2 (Enrich)? (yes / pause / skip to phase 3)
```

## Step 2 — Enrich

Route to `phase-2-enrich/SKILL.md`.

When the phase returns its summary, present the gate question:

```
Phase 2 complete — continue to Phase 3 (Generate)? (yes / pause)
```

## Step 3 — Generate

Route to `phase-3-generate/SKILL.md`. Emit the full-workflow summary from
`../reference/VALIDATION.md` "Full-workflow summary" when Phase 3 validation passes.

## Skill delegation rule

When routing to a sub-skill, pass all relevant `workflow_inputs` fields to avoid asking the
steward for information already provided. The sub-skill uses what it needs and ignores the rest.

## Boundaries

- Route to downstream skills for implementation details — do not duplicate them here
- Global gate rule enforced at this level; phase files enforce their own internal checkpoints
- Use only documented `SYSTEM$..._GLOSSARY_*` functions from `../reference/API_CONTRACT.md`
- Extraction source routing follows `../reference/EXTRACTION_SOURCES.md` — do not inline source logic here
