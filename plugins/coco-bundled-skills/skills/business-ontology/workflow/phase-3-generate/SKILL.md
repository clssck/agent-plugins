---
name: business-ontology-workflow-phase-3-generate
description: "Phase 3 (Generate) of the Business Ontology workflow — Semantic View generation from approved ontology nodes, Cortex Analyst consumption, and ontology↔SV alignment. Routes to $semantic-view and $semantic_studio. Parent: business-ontology workflow."
parent_skill: business-ontology-workflow
---

# Phase 3 — Generate and Consume

Approved ontology meaning becomes **executable** Semantic Views. Engineers refine in Studio; business users consume through Cortex Analyst.

## Inputs

```yaml
primary_domain: string
semantic_view_fqn: string     # required — MY_DB.MY_SCHEMA.MY_SV
source_tables: list[string]    # tables for Autopilot / FastGen grounding
```

## Step 1 — Read canonical metrics

`SYSTEM$GET_GLOSSARY_TERM_LIST(domainFilter, sortBy)` — the second argument is a **sort key** (`DOMAIN` | `TERM` | `UPDATED`), not an item-kind filter. Filter to metrics client-side:

```sql
SELECT
  term:name::STRING AS name,
  term:description::STRING AS definition,
  term:formula::STRING AS formula
FROM TABLE(
  FLATTEN(
    PARSE_JSON(
      SYSTEM$GET_GLOSSARY_TERM_LIST('<primary_domain>', 'TERM')
    ):terms
  )
) AS f(seq, key, path, idx, term, this)
WHERE term:itemKind::STRING = 'METRIC';
```

## Step 2 — Create Semantic View

Route to `$semantic-view creation`:

```yaml
view_name: <semantic_view_fqn>
source_objects: <source_tables>
prompt: |
  Generate a Semantic View for domain <primary_domain>.
  Ground metrics on these canonical Business Ontology definitions:
  <paste metric names, definitions, and formulas from Step 1>
```

Include approved metric names, definitions, and formulas from Step 1 in the creation prompt so Autopilot aligns with steward-approved meaning.

After publish, bind ontology nodes to the Semantic View via catalog associations.

**⚠️ MANDATORY CHECKPOINT:** Present the proposed node ↔ SV metric binding list. Wait for steward confirmation before approving associations.

```sql
CALL SYSTEM$DRAFT_GLOSSARY_ASSET(
  '<termName>',
  '{"refType":"SEMANTIC_VIEW","fqn":"<semantic_view_fqn>","field":"<metric_name>"}',
  'RELATED_SEMANTIC_VIEW'
);
CALL SYSTEM$APPROVE_GLOSSARY_ASSET(
  '<termName>',
  '{"refType":"SEMANTIC_VIEW","fqn":"<semantic_view_fqn>","field":"<metric_name>"}'
);
```

Verify bindings:

```sql
CALL SYSTEM$GET_GLOSSARY_TERM_ASSETS('<termName>', 'SEMANTIC_VIEW');
```

Optional: route to `$semantic_studio semantic_view` for inline review after associations exist.

## Step 3 — Consume with Cortex Analyst

Ask the user for a natural-language question against `<semantic_view_fqn>`.

Route to **`$semantic-view debug`** (preferred) or use the host's **`snowflake_multi_cortex_analyst`** tool when available in CoCo. Pass the semantic view FQN and the user's question.

Surface to the user:

- Generated SQL
- Result summary
- Any ambiguity or warnings from Analyst

Do **not** invoke bundled Python or REST helpers from this skill — downstream skills and platform tools own Analyst execution.

## Step 4 — Align after ontology changes

When a steward updates a node (`SYSTEM$UPDATE_GLOSSARY_TERM`), check alignment with the bound Semantic View:

```sql
CALL SYSTEM$GET_GLOSSARY_TERM('<termName>');
DESC SEMANTIC VIEW <semantic_view_fqn>;
```

Compare definition and formula text. If they diverge, route the engineer to `$semantic_studio semantic_view` edit or `$semantic-view creation` to update the implementation. Never auto-overwrite ontology or Semantic View content.

## Step 5 — Validate and return summary

Run Phase 3 validation from `../../reference/VALIDATION.md` "Phase 3 validation" before
returning the summary. Only mark `workflow_status: complete` when all validation criteria pass.

**Self-check before emitting the summary:**

- [ ] At least 1 `RELATED_SEMANTIC_VIEW` association approved and confirmed via `GET_GLOSSARY_TERM_ASSETS`
- [ ] `DESC SEMANTIC VIEW` returns without error
- [ ] Cortex Analyst question ran and returned valid SQL
- [ ] Ontology node definition and SV metric expression aligned (Step 4 check)

If any criterion fails, note it explicitly in the summary and recommend the corrective route.

```yaml
phase_3_complete:
  semantic_views_created: <count>
  glossary_sv_bindings: <count>
  analyst_queries_run: <count>
  validation_passed: true        # false if any criterion above failed
  workflow_status: complete      # "needs-attention" if validation_passed: false
```

After emitting this, render the full-workflow summary from
`../../reference/VALIDATION.md` "Full-workflow summary".

## Boundaries

- Do not call fictitious functions such as `SNOWFLAKE.CORTEX.ANALYST()` or undocumented `SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML`
- Catalog-level `RELATED_SEMANTIC_VIEW` associations bind nodes to Semantic Views
- Never auto-overwrite ontology or SV when divergence is detected
