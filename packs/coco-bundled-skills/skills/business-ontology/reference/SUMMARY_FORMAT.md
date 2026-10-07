# Summary Format — Business Ontology

Canonical render templates for all business-ontology sub-skills. Load this file when you need to display items to the builder.

> **"Concept" vs "Node" vs `TERM`.** "Concept" is the umbrella label for any ontology node shown on a card (a term, metric, entity, or policy concept). `TERM` is one specific `itemKind` value — a concept represented as a Node in the ontology. "Concept" and "node" may be used interchangeably in prose; `TERM` refers specifically to the `itemKind` discriminator.

State badges: `[DRAFT]` — saved to Snowflake, pending activation · `[ACTIVE]` — live · `[SKIPPED]` · `[FAILED]`

**Translate API state to user-facing state.** The raw API (`API_CONTRACT.md`) returns `status: "APPROVED"` for live items. Always display this as `ACTIVE` — never surface the raw `APPROVED` value to the builder. `DRAFT` is the same in both.

---

## Individual item cards

One row per field. State badge on the title row. Omit optional fields that are empty.

### Concept card

```
---------------------------------------------------------------
Concept        Purchase Order                          [DRAFT]
Domain         Purchasing
Kind           TERM
Description    A commercial document issued by a buyer specifying goods/services.
Tags           PROCUREMENT · SOX
Synonyms       PO
---------------------------------------------------------------
```

Fields: `Concept` (name) · `Domain` · `Kind` (`TERM | METRIC | ENTITY`) · `Description` · `Tags` (dot-separated) · `Synonyms` (dot-separated)

### Relationship card

```
---------------------------------------------------------------
Relationship   Purchase Order → Supplier Invoice       [DRAFT]
Type           DERIVES
---------------------------------------------------------------
```

```
---------------------------------------------------------------
Relationship   Revenue → Gross Sales                   [DRAFT]
Type           Custom — "triggers"
---------------------------------------------------------------
```

Fields: `Relationship` (source → target) · `Type` — display rules:
- Standard type: show the type name (e.g. `DERIVES`, `HAS_PART`). Omit the Label row entirely.
- `CUSTOM` type: show `Custom — "<label>"` in the Type row. Omit a separate Label row.
- If a standard type carries a user-supplied annotation (non-default label), append it inline: `DERIVES — "triggers"`.

Never display `CUSTOM` alone — the label is the meaningful information.

### Asset association card

```
---------------------------------------------------------------
Association    Purchase Order                          [ACTIVE]
Asset type     TABLE
Object         ANALYTICS.PUBLIC.TRIP_PAYMENTS
Role           DESCRIBES
---------------------------------------------------------------
```

Fields: `Association` (concept name) · `Asset type` (`TABLE | VIEW | COLUMN | SEMANTIC_VIEW | DASHBOARD`) · `Object` (FQN) · `Role` (`DESCRIBES | RELATED_SEMANTIC_VIEW | RELATED_DASHBOARD`)

---

## Edit diff card (ACTIVE item being updated)

Used when an edit targets an **existing ACTIVE item** — alias addition, type correction, description fix, tag change, etc. Show only rows where something changed; omit unchanged fields entirely.

```
Editing concept: Purchase Order                     [ACTIVE]

  Field         Current                            Proposed
  ─────────────────────────────────────────────────────────────
  Kind          TERM                               METRIC
  Description   "A commercial document..."         "A formal buyer request..."
  Synonyms      PO                                 PO · Purchase Request
  Tags          PROCUREMENT                        PROCUREMENT · SOX
```

Rules:
- Only changed fields appear in the table.
- Multi-value fields (Synonyms, Tags) show the complete new set — not just the delta.
- The item stays `[ACTIVE]` throughout — updates apply directly via `SYSTEM$UPDATE_GLOSSARY_TERM` on the existing term; there is no intermediate DRAFT state and no separate approval step.
- For relationship and association edits, use the same diff layout substituting the relevant field names.

> **Note:** updates apply directly to the ACTIVE item today (no draft, no approval step). A draft mode for updates is planned — see `NOT_IMPLEMENTED_YET.md` item 1.1.

---

## Bulk import formats

### Candidate table (import Step 4)

One row per candidate. Truncate descriptions to ~80 characters. Use state badge in the `#` column and a `Conf` column for confidence.

```
 #        Name               Domain       Kind    Conf  Graph
 1        Purchase Order     Purchasing   TERM    ▲     → Supplier Invoice (DERIVES) · TABLE: ANALYTICS.PUBLIC.PO
 2        Net Revenue        Finance      METRIC  ●     ← Gross Revenue (DERIVES) · TABLE: FINANCE.PUBLIC.REVENUE · grain: day, agg: SUM
 3[upd]   Vendor Code        Purchasing   TERM    ▲     (no new edges)
 4[merge] Active Users       Growth       METRIC  ●     also exists in Marketing domain — steward decision needed
 5        Customer           Core         ENTITY  ▼     (no edges yet) ← low confidence; will default to draft
```

State badges in `#` column:
- `[upd]` = update to an existing ACTIVE concept (Step 2B)
- `[merge]` = cross-domain homonym; steward must choose reuse or scoped variant
- No badge = genuinely `new` concept

Confidence badges in `Conf` column:
- `▲` = high
- `●` = medium
- `▼` = low (defaults to draft unless steward explicitly approves)

**Graph column:** compact inline summary of known relationships and associations for this candidate, pre-populated from `relationship_candidates` and `association_candidates` resolved in Step 3b. Format:
- `→ <Target> (<TYPE>)` — this node is the source/input
- `← <Source> (<TYPE>)` — this node is the target/output
- `TABLE: <FQN>` or `VIEW: <FQN>` — asset association
- For METRIC: append `· grain: <grain>, agg: <aggregationFn>` when set
- `(no edges yet)` when no relationships or associations are resolved for this candidate

For METRIC candidates: show `grain` and `aggregationFn` in the Graph column to help stewards distinguish metrics with the same name but different semantic grain.

When the reviewer selects `edit #N` or `one by one` reaches an `[upd]` row, show the **edit diff card** instead of the standard item card. For `[merge]` rows, show a cross-domain comparison card.

### Session report (import Step 6)

**Default output — business summary (always shown):**

```
Import complete — <source> → <domain(s)>

  Nodes
    ✓  N  made active     (new concepts live in the ontology)
    ~  N  updated         (existing concepts enriched)
    ~  N  left as drafts  (N low-confidence or steward-deferred)
    ✗  N  skipped
    !  N  failed
    ↺  N  reused          (already existed — no duplicate created)

  Relationships   <R> created
  Associations    <A> created

  Domains touched:  Finance, Purchasing, Core
```

If any items failed:
```
  Failures:
    "Discount Policy" — domain 'Finance' not found (create it first).
```

**Evidence detail — shown only on request (`show evidence` or `show detail`):**

`#N` refers to the **original candidate row number assigned in Step 4** — this number is stable and does not change as candidates are approved, drafted, or skipped. Use it consistently to reference candidates across the session.

```
Evidence detail:

  #1  Purchase Order      confidence: ▲ high    source: procurement_glossary.md §2
  #2  Net Revenue         confidence: ● medium  source: metrics.csv row 14  (no formula found)
  #5  Discount Rate       confidence: ▼ low     source: inferred from "rate applied to orders"
      → Drafted (low confidence); approve via UI or re-import with formula
```

### Multi-session resume header

Shown when the agent picks up a prior draft batch (session resumed or builder returns with "approve drafts"):

```
Resuming draft batch from <timestamp>:  N concepts pending review
```

---

## Relationship import summary (import Step 7)

Separate from concept candidates. Shown after the concept report when relationship candidates exist.

```
Relationships extracted: N
 #   Source               Type                    Target
 1   Purchase Order       DERIVES                 Supplier Invoice
 2   ARR                  EQUIVALENT_TO           Annual Recurring Revenue
 3   Revenue              Custom — "triggers"     Gross Sales

approve all / review one by one / skip
```

`Type` column display rules: standard type → type name only (e.g. `DERIVES`); user-supplied annotation on a standard type → `DERIVES — "triggers"`; `CUSTOM` type → `Custom — "<label>"`. Never show `CUSTOM` alone.
