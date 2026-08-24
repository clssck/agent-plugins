---
name: business-ontology-workflow-phase-2-enrich
description: "Phase 2 (Enrich) of the Business Ontology workflow — Cortex Sense promotion, evidence-driven asset associations, cross-domain conflict resolution, and optional schema / dbt extraction. Routes to $cortex-sense and $business-ontology import. Parent: business-ontology workflow."
parent_skill: business-ontology-workflow
---

# Phase 2 — Enrich

Snowflake AI **proposes**; stewards **approve**. Cortex Sense candidates become ontology nodes;
asset mappings link meaning to Snowflake objects.

New in this phase: **additional extraction sources** (table introspection, dbt manifest) feed
the same review pipeline and help bridge until the Cortex Sense backend provides automated
discovery. See `../../reference/EXTRACTION_SOURCES.md`.

## Inputs

```yaml
primary_domain: string
secondary_domain: string       # optional
cortex_sense_manifest: string  # optional — stage path to manifest YAML (Source E)
extraction_sources: list[str]  # optional — additional keys: C (table), D (dbt)
```

## Step 1 — Promote Cortex Sense context (optional)

When `cortex_sense_manifest` is provided:

```sql
LIST <cortex_sense_manifest> PATTERN = '.*manifest.*';
```

Route to `$business-ontology import`:

```yaml
source_type: cortex_sense_promotion
manifest_path: <cortex_sense_manifest>
target_domain_hint: <secondary_domain or primary_domain>
```

Approve node candidates:

```sql
CALL SYSTEM$APPROVE_ALL_GLOSSARY_TERMS('["<termId>", ...]');
-- or
CALL SYSTEM$APPROVE_ALL_GLOSSARY_TERMS();
```

Approve relationship candidates:

```sql
CALL SYSTEM$APPROVE_ALL_GLOSSARY_RELATIONSHIPS();
```

For deeper discovery first, route to `$cortex-sense setup` or `$cortex-sense refine` per the manifest contract in `../../reference/CORTEX_SENSE_MANIFEST_CONTRACT.md`.

## Step 1b — Additional extraction sources (optional)

When `extraction_sources` includes keys C (table introspection) or D (dbt manifest), run each
source per `../../reference/EXTRACTION_SOURCES.md` before the asset association step. This is
the bridge path until the Cortex Sense backend (Source F) is available.

For each source key:
1. Invoke the script as described in EXTRACTION_SOURCES.md.
2. Pass the output to `$business-ontology import` Path C (structured inline data).
3. The import sub-skill deduplicates against existing terms, presents the candidate review table,
   and handles draft/approve.

After all extraction sources are processed, continue to Step 2.

**Note on Cortex Sense backend (Source F):** when this path becomes available, it will push
candidates directly into the review pipeline — sources C and D become fallback paths. The review
and approve steps in this Phase remain unchanged regardless of the source.

## Step 2 — Asset association approval

When Cortex Sense or contributors propose asset mappings, present each proposal with available evidence (name match, lineage summary, confidence when present).

**⚠️ MANDATORY CHECKPOINT:** Show node, asset reference, and evidence summary. Wait for explicit steward **Approve / Reject / Modify** before any approval call.

Draft each accepted association:

```sql
CALL SYSTEM$DRAFT_GLOSSARY_ASSET(
  '<termName>',
  '<assetRefJson>',
  '<associationRole>'
);
```

After all accepted associations are drafted, batch-approve using the scoped form (preferred):

```sql
-- Scoped form — pass the association items drafted in this session
CALL SYSTEM$APPROVE_ALL_GLOSSARY_ASSETS('[
  {"term": "<termId>", "refType": "TABLE", "fqn": "<fqn>"},
  {"term": "<termId>", "refType": "SEMANTIC_VIEW", "objectName": "<svName>", "dimensionName": "<dim>"}
]');
```

Check `results` in the response. Any entries with `"status": "FAILED"` should be surfaced to the steward and retried individually via `SYSTEM$APPROVE_GLOSSARY_ASSET` if needed.

Verify:

```sql
CALL SYSTEM$GET_GLOSSARY_TERM_ASSETS('<termName>', '');
```

When the API does not return structured evidence, include Cortex Sense output or steward notes in the review table.

## Step 3 — Cross-domain conflicts (when applicable)

When the same node name appears in multiple domains with different definitions, compare side-by-side using:

```sql
CALL SYSTEM$GET_GLOSSARY_TERM('<termName>');
-- repeat per domain context
```

Resolve with scoped variants (distinct domains and clear descriptions). Never auto-merge.

## Step 4 — Validate

Run Phase 2 validation from `../../reference/VALIDATION.md` "Phase 2 validation". If the
spot-check shows no approved associations after approval calls, re-run the draft + approve
sequence for the missing items.

## Step 5 — Self-check

Before returning the summary, confirm:

- [ ] Cortex Sense candidates presented and actioned (approved / skipped) — none left in limbo
- [ ] All extraction source runs completed without unresolved errors
- [ ] Asset association approvals called per steward decisions (no silently-skipped approvals)
- [ ] Cross-domain homonyms resolved — use the `scope` field on DRAFT_GLOSSARY_TERM to distinguish scoped variants (e.g. `"Finance"` vs `"Customer Success"` for the same concept name)
- [ ] EXPRESSION_DRIFT / IMPORT_CONFLICT blockers = 0 (if sv-ingest contributed findings)

## Step 6 — Return summary

```yaml
phase_2_complete:
  cortex_sense_terms_approved: <count>
  relationships_approved: <count>
  asset_associations_approved: <count>
  conflicts_resolved: <count>
  extraction_sources_used: [<list of source keys>]
  next_phase: generate
```

Return this to `workflow/SKILL.md`. The gate question ("continue to Phase 3?") is asked by the
workflow orchestrator.
