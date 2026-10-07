---
name: business-ontology-relationship-types
description: "Vocabulary of relationship types for the Business Ontology skill. Load when creating or classifying relationships between ontology nodes."
---

# Relationship Types

All relationships are single-direction: source = authoritative/parent/origin concept; target = derivative/dependent/child concept. The sentence template is: **"{Source} {label} {Target}"** — must read as natural English.

> **API string format:** The `relationshipType` parameter in SYSTEM$ calls uses SCREAMING_SNAKE_CASE (e.g. `HAS_VARIANT`, `DERIVES`). The label column below is the user-facing display name.

## Standard types

| Type (API value) | Label | Inverse reading | Source | Target | When to use |
|---|---|---|---|---|---|
| `HAS_VARIANT` | has variant | is variant of | General concept | Scoped/windowed variant | Same concept narrowed by time window, geography, segment, or qualifier |
| `HAS_PART` | has part | part of | Whole / composite | Component / constituent | Target is a structural component of source; removing it makes source incomplete |
| `DERIVES` | derives | derived from | Input metric/concept | Output metric computed from source | Target's value is calculated using source's value as an input |
| `MEASURES` | measures | measured by | Metric | Entity/concept quantified | Source is a numeric measure that quantifies some aspect of target |
| `IDENTIFIED_BY` | identified by | identifies | Entity being referenced | Reference key / code | Source is the business entity; target is the identifier that points to it |
| `CLASSIFIES` | classifies | classified by | Dimension / category | Entity being categorized | Source assigns categorical grouping to instances of target |
| `APPLIES_TO` | applies to | governed by | Policy / rule / constraint | Concept governed | Source is a business rule or policy that constrains target |
| `SCOPES` | scopes | scoped by | Qualifying dimension / panel / cohort | Metric valid within that boundary | Source defines the context boundary; target only meaningful within it |
| `EQUIVALENT_TO` | equivalent to | equivalent to *(symmetric)* | Canonical / preferred term | Term with same meaning | Both nodes are fully defined concepts meaning the same thing |
| `RELATED_TO` | related to | related to *(symmetric)* | Any node | Any node | Meaningful association exists but no other type captures it precisely — use sparingly |

## CUSTOM type

Use `CUSTOM` when:
- No standard type accurately describes the relationship, AND
- The user explicitly requests a custom label

**`label` is mandatory for CUSTOM** — it describes the nature of the relationship (e.g. "triggers nightly reconciliation").

Label is optional (but encouraged) for all other types.

> **TEMPORARY — UI display fix:** If no label was provided for a standard type, pass the display label from the table above instead of `NULL` (e.g. `HAS_VARIANT` → `'has variant'`, `DERIVES` → `'derives'`). This ensures the UI renders an edge label rather than a blank. Remove this rule once the UI falls back to the type name automatically.

**Never use CUSTOM as a fallback for ambiguity.** If the correct standard type is unclear, ask the user to choose between the candidates — do not default to CUSTOM.

## Disambiguation guide

### `scopes` vs `has part` vs `classifies` vs `applies to`

| Type | Test |
|---|---|
| `has part` | If you remove the target, is the source *broken/incomplete*? → `has part` |
| `scopes` | Does the source define a *data boundary/context* that limits where target is valid? The target still exists without it, just unscoped → `scopes` |
| `classifies` | Does the source *assign a category label* to instances of the target? (Region classifies Store — each store gets a region label) → `classifies` |
| `applies to` | Is the source a *policy, rule, or governance artifact*? (GDPR applies to EU Customer) → `applies to` |

### `equivalent to` vs synonyms attribute

- Synonym has its own definition, owner, or lineage → create a node and connect with `equivalent to`
- Synonym is just an alternative name or abbreviation → store as `synonyms: ["alias"]` on the node (no edge)

### `derives` direction

Source = **input/origin** → Target = **output/derived result**  
Example: "Gross Revenue `derives` Net Revenue" — Gross Revenue is the *input*; Net Revenue is *computed from it*.  
If the user says "X is derived FROM Y", the edge is Y `derives` X (Y is the input, X is the result).

## Examples by domain

| Plain English | Type | Source | Target |
|---|---|---|---|
| "Same Store Sales Growth has a 28-day trailing variant" | `HAS_VARIANT` | Same Store Sales Growth | Same Store Sales Growth - Trailing 28 Days |
| "Order has a Line Item as a component" | `HAS_PART` | Order | Line Item |
| "Gross Revenue is used to compute Net Revenue" | `DERIVES` | Gross Revenue | Net Revenue |
| "NPS Score quantifies Customer Satisfaction" | `MEASURES` | NPS Score | Customer Satisfaction |
| "Customer is referenced by Customer ID" | `IDENTIFIED_BY` | Customer | Customer ID |
| "Region categorizes Store" | `CLASSIFIES` | Region | Store |
| "Return Policy governs Online Orders" | `APPLIES_TO` | Return Policy | Online Orders |
| "EMAX Panel bounds Panel Spend metric" | `SCOPES` | EMAX Panel | Panel Spend |
| "Net Revenue means the same as Net Sales" | `EQUIVALENT_TO` | Net Revenue | Net Sales |
| "Average Order Value is broadly related to Basket Size" | `RELATED_TO` | Average Order Value | Basket Size |
