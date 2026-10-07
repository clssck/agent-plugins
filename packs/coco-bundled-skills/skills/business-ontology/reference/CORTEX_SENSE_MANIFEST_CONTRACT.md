# Cortex Sense Manifest Contract (promotion path)

This file documents the exact fields the business-ontology import skill reads from a Cortex Sense manifest when the builder asks to "promote this to the ontology." It exists to make the dependency explicit — if the cortex-sense manifest schema changes, update this file and the import skill together.

## Fields consumed

The business-ontology import skill reads **two top-level keys** from the manifest YAML:

### `concepts` → ontology node candidates

Each entry in the `concepts` array maps to one candidate ontology node:

| Manifest field | Ontology field | Notes |
|---|---|---|
| `name` | `name` | Required. Display name of the concept. |
| `description` | `description` | Optional. Human-readable definition. |
| `formulas[0].expression` | `formula` | Optional. First formula expression mapped to the `formula` field (METRIC nodes only). Do NOT append to `description`. If multiple formula variants exist, pick the primary one for `formula` and note others in `description` or a `formulaSource` note if provenance matters. |
| `domain` | `domainName` | Optional. The owning domain identifier (usually the use-case name). |
| `aliases` | `synonyms` | Optional. Manifest alternate names map directly to ontology synonyms. |
| `type` | `itemKind` | Map: `metric` → `METRIC`; `entity` → `ENTITY`; `dimension`, `attribute`, anything else → `TERM` (default). |

The cortex-sense concept `type` vocabulary is open (documented values: `metric`, `dimension`, `entity`, `attribute`, …). The ontology `itemKind` accepts `TERM`, `METRIC`, and `ENTITY`; collapse unmapped types (dimension, attribute, policy, etc.) to `TERM`. Per the import granularity guardrails, `attribute`-typed concepts are usually folded into a parent term's description rather than promoted — surface them for review rather than auto-creating.

**Example manifest entry:**
```yaml
concepts:
  - name: ARR
    domain: finance
    type: metric
    description: "Recognized annual recurring revenue"
    formulas: ["SUM(contract_value) / 12"]
    user_prompt: "ARR is annual recurring revenue"
```

**Maps to ontology candidate:**
```json
{
  "name": "ARR",
  "domainName": "finance",
  "itemKind": "METRIC",
  "description": "Recognized annual recurring revenue",
  "formula": "SUM(contract_value) / 12"
}
```

---

### `relationships` → relationship candidates (held for Step 7)

Each entry in the `relationships` array maps to one candidate ontology relationship:

| Manifest field | Ontology field | Notes |
|---|---|---|
| `source_concept` | source term name | Required. |
| `target_concept` | target term name | Required. |
| `relationship_type` | `relationshipType` | Map the manifest vocabulary onto the ontology vocabulary (see mapping below). |
| `user_prompt` | label | Optional. Use as the relationship label if present. |

**`relationship_type` mapping.** The cortex-sense manifest uses an open vocabulary (documented values: `same_as`, `derives_from`, `parent_of`, `feeds`); map onto the ontology relationship vocabulary (see `../reference/RELATIONSHIP_TYPES.md`). Collapse as follows (relative to `source_concept`):

| Manifest `relationship_type` | Ontology `relationshipType` | Rationale |
|---|---|---|
| `same_as`, `synonym`, `alias` (term has own definition) | `EQUIVALENT_TO` | Equivalent concepts with separate definitions. |
| `same_as`, `synonym`, `alias` (alias only, no own definition) | Add to `synonyms[]` attribute on node — no edge | Simple alias, no separate node needed. |
| `feeds`, `parent_of`, `upstream` | `DERIVES` (source = the feeding term = input; target = the fed/derived term = output) | Source concept drives/feeds the target. |
| `derives_from`, `child_of`, `downstream` | `DERIVES` (swap direction: manifest target is the input, manifest source is the output) | Source is the derived concept; need to reverse edge direction. |
| anything else | `RELATED_TO` (flag for steward review) | Safe fallback. |

**Example:**
```yaml
relationships:
  - source_concept: revenue
    relationship_type: same_as
    target_concept: GAAP_REVENUE
    target_domain: finance
    user_prompt: "revenue == GAAP_REVENUE in finance"
```

**Maps to ontology relationship candidate:**
```json
{
  "source": "revenue",
  "target": "GAAP_REVENUE",
  "type": "EQUIVALENT_TO",
  "label": "revenue == GAAP_REVENUE in finance"
}
```

---

### `associations` → asset association candidates (held for Step 7)

Each entry in the `associations` array maps to one candidate asset association, drafted via `SYSTEM$DRAFT_GLOSSARY_ASSET` (or created immediately via `SYSTEM$CREATE_GLOSSARY_ASSOCIATION` when the user wants the link active right away):

| Manifest field | Ontology field | Notes |
|---|---|---|
| `concept_name` | term name (first positional arg) | Required. The node to associate. |
| `object_fqn` | `assetRefJson.fqn` | Required. Fully-qualified Snowflake object name (`DB.SCHEMA.TABLE`). |
| `object_type` | `assetRefJson.refType` | Map: `table` → `TABLE`; `view` → `VIEW`; `column` → `COLUMN`; default `TABLE`. |
| `column_name` | `assetRefJson.objectName` | Required when `object_type` is `COLUMN`. |
| `role` | role (third positional arg) | Optional. Defaults to `PRIMARY` if absent. |

Pass these to import Step 7 as association candidates alongside the relationship candidates. Apply the same go / draft / cancel gate described in `../workflow/create/SKILL.md` § Asset association.

---

## Fields NOT consumed

The following manifest keys are ignored during promotion:

| Key | Reason |
|---|---|
| `sources` | Scope rules — not meaningful as ontology nodes |
| `additional_instructions` | Free-form builder prose — not structured enough for extraction |
| `in_account_instructions` | Account-specific rules — not appropriate for a shared ontology |
| `pending_asks` | Unresolved items — skip silently |
| `status`, `version_id`, `created_at`, `updated_at` | Internal versioning — not relevant |

## Drift policy

If the cortex-sense `SCOPE_MANIFEST.md` changes the shape of `concepts` or `relationships`, update the mapping tables above and align the import sub-skill's Step 1D accordingly.
