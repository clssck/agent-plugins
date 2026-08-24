---
name: business-ontology-relationship-discovery
description: "Intra-domain relationship discovery for the Business Ontology skill. Load when the user asks to find missing relationships within an existing approved domain."
---

# Intra-domain relationship discovery

**Triggers:** "find more relationships", "dig deeper", "what relationships are missing", "complete the graph", "find missing edges"

Use when the user wants to mine an existing approved domain for relationships not yet captured. No source file required — works entirely from the live ontology.

---

### Step H1 — Fetch all approved nodes

`GET_GLOSSARY_TERM_LIST` returns only APPROVED nodes (drafts are excluded).

```sql
SELECT value:termId::STRING AS term_id, value:name::STRING AS name,
       value:description::STRING AS description, value:itemKind::STRING AS item_kind,
       value:synonyms::ARRAY AS synonyms
FROM TABLE(FLATTEN(PARSE_JSON(SYSTEM$GET_GLOSSARY_TERM_LIST('<domain>')):terms));
```

Build a local index: `{termId, name, description, itemKind, synonyms}` per node.

If the returned `terms` array is empty, stop and surface: "Domain `<name>` has no approved nodes — nothing to scan."

### Step H2 — Scan for candidate edges

Scanning is O(N²) across node pairs. For domains with more than ~50 nodes, ask the user to specify a subset (e.g. "focus on METRIC nodes only") before proceeding. Scan in four priority tiers (present source-stated first):

1. **DERIVES** — See `RELATIONSHIP_TYPES.md §derives direction` for the full direction rule and examples. Key: source = INPUT, target = OUTPUT; the source's name must appear literally inside the target's formula expression.
2. **HAS_PART** — scan for enumerated component lists in descriptions (e.g. "consists of: New, Expansion, Churn, Contraction"). The parent (whole) HAS_PART each component (source = whole/parent, target = component).
3. **CLASSIFIES** — scan for taxonomy nodes whose descriptions contain "classifies", "values:", "categories:" or point to an enum of other node names.
4. **RELATED_TO** — scan for structural prose: "is the sum of", "equals X of the prior period", "one X may own multiple Y".

Separate **source-stated** (description directly names the target) from **agent-inferred** (structural reasoning). Keep the lists separate.

If both candidate lists are empty after scanning all tiers, stop and surface: "No candidate edges found in `<domain>`." Do not proceed to H3.

### Step H3 — Present and approve

Present source-stated candidates first, then inferred (as separate blocks with explicit opt-in required for inferred). Use the same table format as Step 7a in `../workflow/import/SKILL.md`.

For approved relationships, use `SYSTEM$APPROVE_ALL_GLOSSARY_RELATIONSHIPS` with the scoped `{source, target, type}` form after drafting:

```sql
-- Draft
CALL SYSTEM$DRAFT_GLOSSARY_RELATIONSHIP('<domain>.<sourceTerm>', '<domain>.<targetTerm>', '<type>', '<label>');
-- Approve (scoped — key names: "source", "target", "type")
CALL SYSTEM$APPROVE_ALL_GLOSSARY_RELATIONSHIPS('[{"source":"<id-or-fqn>","target":"<id-or-fqn>","type":"<type>"},...]');
```

Follow `APPROVAL_PATTERNS.md` for the full filtered-approve protocol.
