---
name: business-ontology-extraction-sources
description: "Catalog of node extraction sources for Business Ontology discovery. Describes each source, how to invoke it, and the candidate format it produces. Transitional: Sources C and D (table introspection, dbt manifest) will be superseded when the Cortex Sense backend provides automated discovery."
---

# Extraction Sources

Ontology node discovery is **transitional**: today it uses several active extraction paths; when
the **Cortex Sense backend** is ready it will push candidates automatically into the same review
pipeline. This file is the single catalog of those paths.

All sources produce candidates in the same format and feed `../workflow/import/SKILL.md` Step 2A onward.

---

## Candidate format (all sources)

Sources produce four parallel lists. Scripts and structured sources produce node candidates; AI extraction (Path B) and Cortex Sense (Path E) also produce relationship and association candidates, split into source-stated and agent-inferred buckets.

**Node candidate:**
```json
{
  "name": "...",
  "description": "...",
  "domainName": "...",
  "itemKind": "TERM | METRIC | ENTITY",
  "itemKind_ambiguous": false,
  "tags": [],
  "synonyms": [],
  "formulas": [
    {"label": "SQL", "expression": "..."},
    {"label": "DSL", "expression": "..."}
  ],
  "evidence": {
    "verified_query": "...",
    "sample_output": "...",
    "verified_as_of": "YYYY-MM-DD",
    "source_ref": "file#section"
  },
  "confidence": "high | medium | low",
  "confidence_reason": "...",
  "_metric_only": {
    "grain": "day | user | transaction | session | order | ...",
    "aggregationFn": "SUM | COUNT | COUNT_DISTINCT | AVG | MAX | MIN | RATIO | ...",
    "filterConditions": ["status = 'active'", "..."],
    "sliceDimensions": ["region", "channel", "product_line", "..."]
  }
}
```

`_metric_only` fields are only set when `itemKind == METRIC` (or `itemKind_ambiguous: true`). All four are optional but should be populated whenever extractable from the formula or source context. They are NOT separate API fields — they feed the `formula` and `exclusions` API fields and appear in the candidate card for steward verification:
- `grain` + `aggregationFn` → surfaced in the review card to help detect distinct metrics with the same name (e.g. "daily Active Users" vs "monthly Active Users")
- `filterConditions` → mapped to the `exclusions` array in `SYSTEM$DRAFT_GLOSSARY_TERM`
- `sliceDimensions` → noted in the description if not already captured

**Confidence scoring rules (set during Step 2A extraction):**

| Level | Criteria |
|---|---|
| `high` | Name + description + formula (METRIC) or lineage/FQN (ENTITY) all present from source; or candidate has `evidence.verified_query` |
| `medium` | Name + description present; formula or lineage absent |
| `low` | Name only (description absent or < 20 chars); or concept inferred from structural context without explicit source mention |

`formulas`, `evidence`, and metric-specific fields are omitted when absent. `itemKind_ambiguous: true` means structural signals were ambiguous — the steward should review `itemKind` at import time, though it can be corrected post-creation via `SYSTEM$UPDATE_GLOSSARY_TERM`.

**Relationship candidates — two buckets (never mixed):**
```json
// relationships_stated — extracted verbatim from source; auto-proposed in Step 7a-i:
{
  "sourceName": "Purchase Order",
  "targetName": "Supplier Invoice",
  "relationshipType": "HAS_VARIANT | HAS_PART | DERIVES | MEASURES | IDENTIFIED_BY | CLASSIFIES | APPLIES_TO | SCOPES | EQUIVALENT_TO | RELATED_TO | CUSTOM",
  "label": "triggers",
  "provenance": "Related field",
  "targetResolved": true
}

// relationships_inferred — agent-derived; explicit per-item opt-in required in Step 7a-ii:
{
  "sourceName": "Purchase Order",
  "targetName": "Vendor Contract",
  "relationshipType": "RELATED_TO",
  "label": "governed by",
  "provenance": "agent-inferred: PO description references vendor approval chain",
  "targetResolved": true
}
```

`targetResolved: false` means the target name could not be matched to any node in the current batch, corpus, or existing ontology — surfaced as a warning in Step 7, never dropped.

**Association candidate** (optional — extracted when source names a Snowflake object):
```json
{
  "termName": "Purchase Order",
  "objectType": "TABLE | VIEW | COLUMN | SEMANTIC_VIEW | DASHBOARD",
  "objectName": "ANALYTICS.PUBLIC.PURCHASE_ORDERS",
  "associationRole": "DESCRIBES | RELATED_SEMANTIC_VIEW | RELATED_DASHBOARD",
  "pattern": false
}
```

`pattern: true` means `objectName` contains a wildcard (`*` or `%`). Pattern entries are kept and flagged for steward confirmation — never dropped.

> **Code files are first-class extraction sources.** `.sql`, `.py`, and `.ipynb` files are not treated as background context. `-- Qn: <question>` and `# heading` comment blocks immediately preceding a query become the candidate's `description`; the adjacent query body populates `formulas`; named output aliases become `synonyms`. Named derived columns expressing business measures (e.g. `growth_pct`, `retention_rate`) are METRIC candidates, subject to the same granularity filter as prose-extracted candidates.

Scripts (Sources C and D) currently produce only node candidates. Relationship and association extraction for script output is handled by `import/SKILL.md` Step 2A when the agent runs the structured-source relationship pass over relationship-signal columns.

---

## Source A — Stage file (CSV / JSON / text)

**When:** builder provides a stage URI (`@DB.SCHEMA.STAGE/path`).

Route to `../workflow/import/SKILL.md` Path A (structured columns) or Path B (AI extraction on raw
content). See that file for mechanics.

**Registration offer:** before reading the file, offer to register the URI in the source
registry (per `../workflow/import/SKILL.md` "Offer to register"). Registered sources are stored in the
Snowflake account and remain available for scheduled offline enrichment after the session ends.

**Best for:** domain-curated node lists, consultant deliverables, exported glossaries/ontologies.

---

## Source B — Semantic View estate

**When:** account already has Semantic Views; builder says "bootstrap from SVs", "SV to ontology",
"SV to ontology", or "scan semantic view estate".

Route to `$business-ontology sv-ingest`. The scan → drift → reconcile flow produces term +
association candidates from `SHOW / DESC SEMANTIC VIEW` + column lineage. See
`../workflow/sv-ingest/SKILL.md`.

**Best for:** accounts with an existing Semantic View estate and thin / no ontology.

---

## Source C — Table / column introspection

**When:** builder says "extract terms from our tables", "what business concepts are in <schema>?",
"discover ontology data from our schema", or "scan INFORMATION_SCHEMA for terms".

**Status:** active (Python script). Cortex Sense backend will supersede this path when ready.

```bash
# Adjust --output path for your environment (Linux/macOS: /tmp/; Windows: %TEMP%)
uv run --project <SKILL_DIR>/.. python <SKILL_DIR>/../scripts/table_term_extractor.py \
  --connection <connection> \
  --database <db> \
  --schema <schema> \
  --output /tmp/table_candidates.json
```

Options:
- `--include-columns` — also extract columns with non-empty COMMENT (disabled by default; generates many candidates for large schemas; use only when the builder explicitly asks)
- `--domain-map <path>` — YAML file mapping `DB.SCHEMA` → domain name; overrides the default schema-name heuristic

The script queries `INFORMATION_SCHEMA.TABLES` and (optionally) `INFORMATION_SCHEMA.COLUMNS`
for rows where `COMMENT IS NOT NULL AND COMMENT != ''`. It normalizes table names to Title Case,
uses the COMMENT as the description, and infers `itemKind` from the table name's last segment:
- `*_FACT`, `*_METRICS`, `*_MEASURES`, `*_STATS`, `*_KPI`, `*_AGGREGATE`, `*_SUMMARY`, `*_REPORT` → `METRIC`
- `*_DIM`, `*_DIMENSION`, `*_LOOKUP`, `*_MASTER`, `*_ENTITY`, `*_REF`, `*_REFERENCE`, `*_CATALOG` → `ENTITY`
- Everything else → `TERM`

The match is case-insensitive and applies to the last `_`-delimited segment as well as the full normalized name (e.g. `ORDERS_FACT_DAILY` and `ORDERS_FACT` both → `METRIC`).

Pass the output to `../workflow/import/SKILL.md` Path C (structured inline data — no AI extraction needed;
the script already normalizes the fields).

**Best for:** accounts with well-commented schemas and no existing ontology.

---

## Source D — dbt manifest

**When:** builder says "import from dbt", "extract glossary/ontology from dbt manifest", "parse our dbt
project for terms", or provides a `manifest.json` path (local or stage URI).

**Status:** active (Python script). Cortex Sense backend will supersede this path when ready.

```bash
# Adjust --output path for your environment (Linux/macOS: /tmp/; Windows: %TEMP%)

# Local manifest file
uv run --project <SKILL_DIR>/.. python <SKILL_DIR>/../scripts/dbt_manifest_parser.py \
  --manifest <path_to_manifest.json> \
  --output /tmp/dbt_candidates.json

# Manifest stored in a Snowflake stage
uv run --project <SKILL_DIR>/.. python <SKILL_DIR>/../scripts/dbt_manifest_parser.py \
  --manifest @<DB>.<SCHEMA>.<STAGE>/target/manifest.json \
  --connection <connection> \
  --output /tmp/dbt_candidates.json
```

The parser extracts from each node type:

| dbt node type | itemKind | Source field |
|---|---|---|
| `model` | `ENTITY` | `description` (model-level) |
| `metric` | `METRIC` | `label` + `description` |
| `exposure` | `ENTITY` | `description` |
| `source` | `ENTITY` | `description` |

Domain inference order: (1) `meta.domain` tag on the node, (2) dbt package name, (3) `"Core"`.

Synonyms: if the model has a `meta.synonyms` list, they are passed through. If the model name
differs from its `label` in a metric node, the model name is added as a synonym.

Pass the output to `../workflow/import/SKILL.md` Path C (structured inline data).

**Registration offer (stage URI only):** if the manifest path is a stage URI, offer to
register it before invoking the script (per `../workflow/import/SKILL.md` "Offer to register").
Registered sources are stored in the Snowflake account and remain available for scheduled
offline enrichment after the session ends. Local file paths are not registered.

**Best for:** accounts with an active dbt project and semantic model (dbt metrics layer).

---

## Source E — Cortex Sense context promotion

**When:** builder says "promote to ontology", "add to glossary" or references an existing Cortex Sense use case by
name.

Route to `../workflow/import/SKILL.md` Path E. The import skill loads the manifest and extracts `concepts`
and `relationships`. See `../reference/CORTEX_SENSE_MANIFEST_CONTRACT.md` for the exact fields
consumed.

**Best for:** teams already running Cortex Sense who want their captured concepts governed.

---

## Source F — Cortex Sense backend (planned, not yet available)

**Status:** not yet available. The Cortex Sense backend will push node candidates directly into
the ontology review queue after offline analysis. Sources C and D (table introspection, dbt
manifest) are the active bridges until this path is live.

**Migration note:** sources tagged `monitoring-mode: sense_scheduled` in the source registry
(`../workflow/source/SKILL.md`) are already reserved for pickup by the future automated job — no registry
migration needed when Source F lands.

See `../reference/NOT_IMPLEMENTED_YET.md` for the gap tracker.

---

## Source G — Semantic View DDL import

**When:** builder provides input containing one or more `CREATE SEMANTIC VIEW` DDL statements (pasted or in a stage file).

Route to `../workflow/import/SKILL.md` Path G.

Parse each DDL statement to extract:
- **Asset associations** — for each column with a comment, create a `COLUMN` association: `termName` from the comment, `fqn` from `DB.SCHEMA.TABLE`, `columnName` from the column name, `refType: COLUMN`.
- **Dimension relationships** — FK join clauses and dimension references map to `CLASSIFIES` or `SCOPES` relationship candidates.
- **Filter/policy concepts** — WHERE filter conditions and row-level policy references map to `APPLIES_TO` candidates.

Leverage parsing patterns from `../scripts/sv_estate_scan.py` where applicable. All extracted items feed the standard `term_candidates`, `relationship_candidates`, and `association_candidates` lists.

**Best for:** accounts with SV DDL exported from Snowsight or Studio; bootstrapping ontology bindings from an existing SV estate without running the full sv-ingest workflow.

---

## Running a discovery pass

When the builder asks for discovery without specifying a source, ask once:

```
Which sources should I scan for ontology candidates?

  A  Stage file (CSV, JSON, or document)          [active]
  B  Semantic View estate (SVs already deployed)  [active]
  C  Table / column introspection                 [active — needs commented schema]
  D  dbt manifest                                 [active — needs manifest.json path]
  E  Cortex Sense context                         [active]
  F  Cortex Sense backend                         [planned — not yet available]
  G  Semantic View DDL                            [active — needs CREATE SEMANTIC VIEW DDL]

Select one or more (e.g. B C)
```

Route each selected source per this file. After all sources return candidates:

1. Merge all candidate lists.
2. Deduplicate by `(name, domainName)` — on collision keep the candidate with the longer
   description (richer source wins). Note: this means a longer-but-vaguer description from one
   source could suppress a shorter-but-precise one. If a steward questions a dropped definition,
   re-run just that source and inspect its output directly.
3. Pass the merged list to `../workflow/import/SKILL.md` Step 2B (dedup against existing ontology) and
   onward through the standard review pipeline.
