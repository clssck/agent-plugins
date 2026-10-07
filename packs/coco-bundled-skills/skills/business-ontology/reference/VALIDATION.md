---
name: business-ontology-validation
description: "Per-phase and end-of-workflow validation steps for Business Ontology. SQL verification queries, acceptance criteria, and the final workflow-complete summary. Referenced from workflow phase files."
---

# Workflow Validation

Run the section for the phase that just completed. These are read-only checks — they confirm the
preceding writes landed correctly before the steward advances to the next phase.

---

## Phase 1 validation (Define)

```sql
-- Verify terms landed in the domain
SELECT value:name::STRING AS name,
       value:itemKind::STRING AS kind,
       value:status::STRING AS status
FROM TABLE(FLATTEN(PARSE_JSON(SYSTEM$GET_GLOSSARY_TERM_LIST('<primary_domain>', 'TERM')):terms));
```

**Acceptance criteria:**
- At least 1 ACTIVE (APPROVED) term in `<primary_domain>`
- Domain exists (its name appears in the list response)
- Zero unexpected errors during APPROVE calls (all previously collected termIds resolve)

**On failure:** if `terms` array is empty, warn:
> "Phase 1 produced no approved terms — check that import and create steps completed without errors."
Route back to the Define step; do not advance to Phase 2.

---

## Phase 2 validation (Enrich)

```sql
-- Spot-check that asset associations landed
CALL SYSTEM$GET_GLOSSARY_TERM_ASSETS('<spot_check_term>', '');
```

Choose `<spot_check_term>` as the first term approved during Phase 2.

**Acceptance criteria:**
- If asset proposals were presented: at least 1 APPROVED asset association present
- Cross-domain homonyms documented (in term descriptions) — no silent merges
- If sv-ingest contributed findings: EXPRESSION_DRIFT / IMPORT_CONFLICT blockers = 0

**On failure:** if associations are absent after approval calls, re-run the relevant
`SYSTEM$DRAFT_GLOSSARY_ASSET` + `SYSTEM$APPROVE_GLOSSARY_ASSET` pair before advancing.

---

## Phase 3 validation (Generate)

Skip this section if no Semantic View FQN was provided in Phase 3 — binding is optional. Note the omission in the full-workflow summary.

If a Semantic View was bound:

```sql
-- Confirm ontology ↔ SV binding for the primary term
CALL SYSTEM$GET_GLOSSARY_TERM_ASSETS('<primary_term>', 'SEMANTIC_VIEW');

-- Confirm the SV is accessible and its structure is as expected
DESC SEMANTIC VIEW <semantic_view_fqn>;
```

Then ask the steward for one natural-language question and route it through Cortex Analyst
(`$semantic-view debug` or `snowflake_multi_cortex_analyst`) to confirm end-to-end queryability.

**Acceptance criteria (only when an SV was provided):**
- `RELATED_SEMANTIC_VIEW` association exists for each bound term
- `DESC SEMANTIC VIEW` returns without error
- Cortex Analyst responds with valid SQL (no `AMBIGUOUS_TABLE` / `TABLE_NOT_FOUND` warnings)
- Ontology node definition and SV metric expression are aligned (compare via Phase 3 Step 4)

**On misalignment:** route to `$semantic_studio semantic_view` to update the SV. Never auto-overwrite either side — see `NOT_IMPLEMENTED_YET.md` Gap #4.

---

## Full-workflow summary

After Phase 3 validation passes, render:

```yaml
workflow_complete:
  domains:               <list>
  terms_active:          <count>
  asset_associations:    <count>
  semantic_views_bound:  <count>   # 0 is acceptable if no SV was provided in Phase 3
  analyst_queries_run:   <count>   # 0 is acceptable if no SV was provided in Phase 3
  drift_blockers:        0         # must be 0 to mark complete
```

If `drift_blockers > 0`, route to `$business-ontology sv-ingest reconcile` before marking
the workflow complete. Do not render `workflow_complete` with a non-zero blocker count.

---

## Failure escalation

| Issue | Action |
|-------|--------|
| Feature gate fires mid-workflow | Stop, surface gate message, do not resume until enabled |
| Phase produces 0 approved items | Warn, re-run phase step — do not silently skip |
| Partial approval (some termIds failed) | Report partial counts; offer to retry failed items |
| No SV bound in Phase 3 | Note in summary (`semantic_views_bound: 0`); user can build an SV via `$semantic-view` or `$semantic_studio` and return to bind it |
| Cortex Analyst returns ambiguity | Present the ambiguity to the steward; route to `$semantic-view debug` |
