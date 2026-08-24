---
name: business-ontology-sv-ingest
description: "Reverse-ingest Business Ontology nodes and RELATED_SEMANTIC_VIEW bindings from an existing Semantic View estate. Scans SHOW/DESC SEMANTIC VIEW, resolves each metric/dimension's domain from column lineage (not the SV name), proposes draft nodes + associations + derives relationships, detects drift vs the existing ontology or prior imports, and guides stewards through reconciliation. Routed from the business-ontology skill. Use when: SVs already exist, bootstrap glossary from Analyst models, semantic view to glossary, SV estate scan, glossary drift from semantic views. Triggers: import glossary from semantic views, scan semantic view estate, SV to glossary, reverse ingest semantic layer, glossary drift semantic view."
parent_skill: business-ontology-workflow
---

# Semantic View → Ontology ingest (`sv-ingest`)

Read an existing **Semantic View estate** and propose **ontology nodes**,
**`RELATED_SEMANTIC_VIEW` associations**, and **`derives` relationships** — resolving each
field's domain and identity from **column lineage first**, SV name last. Routed from `../SKILL.md`.

This is the **reverse** of `../workflow/SKILL.md` (which takes the ontology and cues the customer
to *create* SVs). It is the **third ingress path** into the ontology, alongside CSV import
(`../import/SKILL.md`) and Cortex Sense promotion.

## The three layers (why this skill exists)

| Layer | Job | System of record | This skill's relationship |
|-------|-----|------------------|---------------------------|
| **Business Ontology** | Govern *meaning* | Ontology records (`SYSTEM$…_GLOSSARY_*`) | **writes** draft nodes/associations/relationships |
| **Semantic Views** | *Execute* metrics | Catalog object (`CREATE SEMANTIC VIEW`) | **reads** via `DESC` (source of truth for formulas) |
| **Cortex Sense** | *Discover* context | Manifest + L1/L2 tables + search | **optional** — triangulate formula variants in drift |

**Direction of each path:**

```
Sense (discover) ─▶ Ontology (govern) ─▶ Semantic View (execute) ─▶ table rows (instances)
   import path             ▲                        │
                           └────── sv-ingest (THIS) ┘   reverse: SV → Ontology
```

- The forward workflow (`$semantic-view creation`) turns approved nodes into an SV.
- **sv-ingest** turns an existing SV estate into governed nodes **and keeps them aligned** (drift).
- Neither layer stores the other: the SV object has **no** ontology field, so the binding lives
  only as an ontology association record (`refType=SEMANTIC_VIEW`).

## When to load

Route from `../SKILL.md` when the user says:

- "Import/bootstrap glossary from our semantic views / Analyst models"
- "Scan SV estate and create terms"
- "Find drift between glossary and semantic views"
- "We already have SVs — start governance"

For greenfield **define → enrich → generate**, use `../workflow/SKILL.md` instead.

## Setup

Read before executing:

- `../../reference/API_CONTRACT.md` — all `SYSTEM$` signatures, payloads, gates
- `reference/SV_GLOSSARY_MAPPING_CONTRACT.md` — candidate shape + confirmed API surface
- `reference/DRIFT_CLASSIFICATION.md` — resolution ladder + finding types + reconciliation playbook

Verify ontology enabled (surface the feature-gate note from `../../SKILL.md` once if it fails):

```sql
CALL SYSTEM$GET_GLOSSARY_SUMMARY();
```

`<SKILL_DIR>` is a placeholder the agent resolves (this directory). Scripts live at
`<SKILL_DIR>/../../scripts/` and share the parent `pyproject.toml` (invoke with `uv run --project`).

---

## The plan in one screen

```
Step 1  SCAN      SHOW + DESC SEMANTIC VIEW → per-field candidates + lineage   (read-only)
Step 2  RESOLVE   per field: column-lineage → table-lineage → domain_map        (read-only)
Step 3  DRIFT     match each candidate to ontology via resolution ladder        (read-only)
Step 4  PROPOSE   DRAFT nodes / associations / derives relationships            (no approve)
Step 5  RECONCILE steward approves per finding; re-run drift until BLOCKER = 0   (writes)
```

| Mode | Trigger | Outcome |
|------|---------|---------|
| **scan** | `sv-ingest scan` | Inventory + candidate JSON with lineage |
| **drift** | `sv-ingest drift` | Steward-ready findings (this is the core) |
| **propose** | `sv-ingest propose` | Emit DRAFT SQL from drift `proposedCalls` (no approve) |
| **reconcile** | `sv-ingest reconcile` | Guided approve loop |

### Step 0 — Scope (ask once, default when obvious)

```yaml
sv_ingest_inputs:
  connection:        # snow CLI connection; blank = CLI default
  role:              # optional; blank = connection default
  warehouse:         # optional; blank = connection default
  database_filter:   # optional — limit scan to one database
  schema_filter:     # optional
  sv_name_pattern: "%"
  domain_map_path: <SKILL_DIR>/domain_map.example.yaml   # FALLBACK only — lineage wins
  include_metrics: true
  include_dimensions: true
  include_facts: false
  auto_approve: false                   # MUST stay false unless the user explicitly asks
```

---

## Step 1 — Scan estate (read-only, lineage-aware)

**Preferred path (script)** — faster for large estates:

```bash
uv run --project <SKILL_DIR>/../.. python <SKILL_DIR>/../../scripts/sv_estate_scan.py \
   --connection <connection> --database <db> --schema <schema> \
  --output /tmp/sv_estate.json
```

The scanner (all via `--format JSON`):

1. `SHOW SEMANTIC VIEWS` → inventory (filter db/schema/name).
2. `DESC SEMANTIC VIEW <fqn>` → 5-column EAV (`object_kind, object_name, parent_entity, property, property_value`). Parses `object_kind ∈ {METRIC, DERIVED_METRIC, DIMENSION, FACT, TABLE}`.
3. For each field: maps `parent_entity` (logical table) → base table FQN (from `TABLE` rows' `BASE_TABLE_*`).
4. `SHOW COLUMNS IN TABLE <base_fqn>` → intersect expression identifiers with real columns → **`base_columns`** (the lineage).

Each candidate carries: `name, itemKind, field_kind, base_table_fqn, base_columns, formula, description`.

> Large estates (>50 SVs): the same structure is available column-wise in
> `SNOWFLAKE.ACCOUNT_USAGE.SEMANTIC_METRICS / SEMANTIC_TABLES / SEMANTIC_DIMENSIONS`
> (may lag; prefer `DESC` for authoritative expressions before reconcile).

**Fallback path (inline SQL)** — use when the script is unavailable or the estate is small (≤20 SVs):

```sql
-- 1. Discover the estate
SHOW SEMANTIC VIEWS IN ACCOUNT;         -- or: IN DATABASE <db> / IN SCHEMA <db>.<schema>

-- 2. For each SV returned, inspect its fields
DESC SEMANTIC VIEW <db>.<schema>.<sv_name>;
-- Columns: object_kind, object_name, parent_entity, property, property_value
-- object_kind values: METRIC, DERIVED_METRIC, DIMENSION, FACT, TABLE
-- For TABLE rows, property_value contains BASE_TABLE_DATABASE / BASE_TABLE_SCHEMA / BASE_TABLE_NAME

-- 3. Resolve lineage — map base table columns to candidate fields
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_catalog = '<db>' AND table_schema = '<schema>' AND table_name = '<base_table>';

-- 4. Cross-check field column references against real base columns
-- (agent does this textually by intersecting expression identifiers with the column list)

-- 5. Resolve domain via column lineage (optional — see note below)
SELECT * FROM TABLE(SNOWFLAKE.CORE.GET_LINEAGE(
  '<db>.<schema>.<base_table>.<column>', 'COLUMN', 'UPSTREAM', 3
));
```

**`GET_LINEAGE` may be unavailable.** It requires Enterprise edition and specific privileges, and may be in preview on some accounts. If step 5 errors (function not found / insufficient privileges), skip it and resolve domain from the base table location instead: use the `domain_map` location rule (Step 2, rank 4) keyed on `<db>.<schema>`, or ask the steward to confirm the domain for each base table.
 Lineage is a ranking signal, not a hard requirement.

For the fallback path, build the candidate list manually from the DESC output, then proceed to Step 3 (drift) using the inline SQL below. Skip Step 2's Python script and resolve domains from the lineage query results directly.

---

## Step 2 — Resolve domain per field (lineage-first)

**Domain is NOT the SV name.** A multi-table SV has fields from different domains. Resolve each
field with the ladder (implemented in `sv_drift_report.py`, detailed in `reference/DRIFT_CLASSIFICATION.md`):

| Rank | Signal | `domainSource` |
|------|--------|----------------|
| 1 | Field already bound (`SEMANTIC_VIEW` assoc) | — (drift-check only) |
| 2 | Base **column(s)** governed by node(s) | `LINEAGE_COLUMN` |
| 3 | Base **table** governed | `LINEAGE_TABLE` |
| 4 | `domain_map` location rule | `LOCATION_MAP` |
| 5 | name match within resolved domain | — |

Reverse lookup ("which node governs this column?") has no SYSTEM$ function, so
`sv_drift_report.py` **inverts** `SYSTEM$GET_GLOSSARY_TERM_ASSETS` once per node to build
`column_fqn → nodes` and `table_fqn → nodes`.

**Cross-domain homonyms are expected:** `Net Revenue` in Finance vs Sales are two nodes in two
domains — never auto-merged.

---

## Step 3 — Drift (the core; read-only)

**Preferred path (script):**

```bash
uv run --project <SKILL_DIR>/../.. python <SKILL_DIR>/../../scripts/sv_drift_report.py \
  --connection <connection> --estate /tmp/sv_estate.json \
  --output /tmp/drift_report.json
```

**Fallback path (inline SQL)** — when the script is unavailable, classify each candidate manually:

```sql
-- Check whether a node with this name already exists in the ontology
SELECT value:name::STRING AS name, value:domain::STRING AS domain,
       value:description::STRING AS description, value:itemKind::STRING AS kind
FROM TABLE(FLATTEN(PARSE_JSON(SYSTEM$GET_GLOSSARY_TERM_LIST('', 'TERM')):terms))
WHERE value:name::STRING ILIKE '<candidate_name>';

-- Check whether an SV association already exists for a node
SELECT PARSE_JSON(SYSTEM$GET_GLOSSARY_TERM_ASSETS('<term_name>', ''))
  AS assets;
```

Classify each candidate into a finding type by comparing the SQL results against the candidate list (see `reference/DRIFT_CLASSIFICATION.md` for the full classification rules). Build the `proposedCalls` sequence manually using the SQL templates in Step 4 below.

Produces sorted findings (each with `resolvedDomain`, `domainSource`, and ready-to-run `proposedCalls`):

| Finding | Meaning |
|---------|---------|
| `SV_UNMAPPED` | New field, no governing lineage, no node → draft node + bind |
| `GLOSSARY_UNBOUND` | Node (or same-name governed column) exists → bind SV field |
| `DERIVES_FROM_GOVERNED_COLUMN` | Metric built on governed columns, new name → derived node + `DERIVES` |
| `EXPRESSION_DRIFT` | **Bound** node formula ≠ SV expression (BLOCKER) |
| `IMPORT_CONFLICT` | APPROVED node (CSV/Sense) ≠ SV expression |
| `CROSS_SV_CONFLICT` | Same domain + name, two SVs, different formulas |
| `CROSS_DOMAIN_HOMONYM` | Same name, different domains (INFO — keep separate) |
| `STALE_BINDING` | Association `validity` = STALE / TARGET_MISSING |

Present the steward a sorted table (BLOCKER → WARN → INFO). **Never auto-fix.**

---

## Step 4 — Propose (show the ordered sequence; do not execute)

Each finding's `proposedCalls` is a **fully ordered, runnable sequence**. Present it for review —
do not run anything yet. The steward reviews the drift-report worklist (this is the checkpoint);
the writes happen in Step 5.

> **⚠️ Ordering constraint.** A node must be **APPROVED before** an asset
> or relationship can be drafted against it — `DRAFT_GLOSSARY_ASSET` / `DRAFT_GLOSSARY_RELATIONSHIP`
> on a still-DRAFT node fail with `Term not found`. So the correct per-finding order is:
> **draft node → approve node → draft asset → approve asset → (draft rel → approve rel)**. You
> cannot stage all drafts and batch-approve at the end; the node approval is a prerequisite.
> `sv_drift_report.py` emits `proposedCalls` already in this order.

```sql
-- New METRIC node — use the `formula` field directly (do NOT embed formula text in description)
CALL SYSTEM$DRAFT_GLOSSARY_TERM('{
  "name":"Net Revenue","domainName":"Finance","itemKind":"METRIC",
  "description":"Revenue after discounts and refunds.",
  "formula":"SUM(gross_revenue_amount)-SUM(discount_amount)-SUM(refund_amount)"
}');
CALL SYSTEM$APPROVE_GLOSSARY_TERM('Net Revenue');                       -- must precede the asset draft

-- Bind SV metric (fqn + dimensionName = logical field name)
CALL SYSTEM$DRAFT_GLOSSARY_ASSET('Net Revenue',
  '{"refType":"SEMANTIC_VIEW","fqn":"MY_DB.MY_SCHEMA.FINANCE_METRICS_SV","dimensionName":"net_revenue"}',
  'RELATED_SEMANTIC_VIEW');
CALL SYSTEM$APPROVE_GLOSSARY_ASSET('Net Revenue',
  '{"refType":"SEMANTIC_VIEW","fqn":"MY_DB.MY_SCHEMA.FINANCE_METRICS_SV","dimensionName":"net_revenue"}');

-- Derivation (full vocabulary in ../../reference/RELATIONSHIP_TYPES.md)
CALL SYSTEM$DRAFT_GLOSSARY_RELATIONSHIP('Gross Revenue','Adjusted Gross','DERIVES', NULL);
CALL SYSTEM$APPROVE_GLOSSARY_RELATIONSHIP('Gross Revenue','Adjusted Gross','DERIVES');
```

For a **`GLOSSARY_UNBOUND`** finding the node is already approved, so the sequence is just the
asset draft → approve (no node step).

`itemKind`: metrics → `METRIC`; dimensions → `DIMENSION_CONCEPT`; facts → `MEASURE_CONCEPT`
(all backend-valid — see `../../reference/API_CONTRACT.md`). `refType ∈ {TABLE, VIEW, COLUMN,
SEMANTIC_VIEW, DASHBOARD}`. `associationRole` is `RELATED_SEMANTIC_VIEW` for SV bindings.

---

## Step 5 — Reconcile (writes; steward-gated)

**⚠️ MANDATORY CHECKPOINT:** present the worklist and wait for Approve / Reject / Modify **before**
running any sequence. On approval, run each finding's `proposedCalls` **in order** (node first).

```sql
-- Run the finding's ordered sequence (draft+approve term, then draft+approve its binding):
CALL SYSTEM$DRAFT_GLOSSARY_TERM('{"name":"Net Revenue","domainName":"Finance","itemKind":"METRIC","description":"..."}');
CALL SYSTEM$APPROVE_GLOSSARY_TERM('Net Revenue');
CALL SYSTEM$DRAFT_GLOSSARY_ASSET('Net Revenue', '{"refType":"SEMANTIC_VIEW","fqn":"...FINANCE_METRICS_SV","dimensionName":"net_revenue"}', 'RELATED_SEMANTIC_VIEW');
CALL SYSTEM$APPROVE_GLOSSARY_ASSET('Net Revenue', '{"refType":"SEMANTIC_VIEW","fqn":"...FINANCE_METRICS_SV","dimensionName":"net_revenue"}');
```

`APPROVE_ALL_GLOSSARY_{TERMS,ASSETS,RELATIONSHIPS}` exist for batch approval, but because assets
can only be drafted after their node is approved, batch approve is mainly useful for a set of
independent node drafts — not for node+binding pairs created in one pass.

For drift **conflicts**, the steward picks one (never automatic):

1. **Update glossary** to match SV (execution wins) — `SYSTEM$UPDATE_GLOSSARY_TERM`
2. **Patch SV** to match ontology (governance wins) — route `$semantic-view` / `$semantic_studio`
3. **Scoped variant** — new disambiguated node in the same domain (encode scope in description)
4. **Delete** the losing node — `SYSTEM$UPDATE_GLOSSARY_TERM` with `"status":"DELETED"`

```yaml
reconcile_complete:
  terms_drafted: <n>
  terms_approved: <n>
  associations_approved: <n>
  relationships_approved: <n>
  drift_blockers_remaining: 0        # target
```

Re-run `drift` until BLOCKER = 0 (or the steward logs accepted exceptions).

---

## How the three skills fit (clean story)

| Situation | Entry | Then |
|-----------|-------|------|
| **SV exists, thin/no ontology** (most common) | **`sv-ingest scan → drift → reconcile`** | optional `$cortex-sense` to add evidence; `../workflow` for anything ungoverned |
| **Ontology exists, no SV** | `../workflow` (define→enrich→**generate**) | `sv-ingest drift` afterward for continuous alignment |
| **Sense-first discovery** | `$cortex-sense` → promote to glossary (`../import`) | then `sv-ingest` when SVs get built |

- **Business Ontology** is the single source of governed meaning + asset links.
- **Semantic View** is the single source of executable formulas (Analyst).
- **Cortex Sense** is optional discovery evidence (formula variants feed drift context).

`sv-ingest` is what makes the loop **bidirectional**: forward = ontology→SV (workflow),
reverse = SV→ontology (this skill). Drift keeps both honest.

---

## Validation — messy estate lab

`examples/seed_messy_sv_estate.sql` is a portable lab that deploys 4 intentionally-conflicting SVs
plus governed column/table lineage, so the resolution ladder and every finding type can be exercised
end-to-end. Replace `SV_INGEST_DB` with a database you can create objects in before running:

```bash
snow sql -c <connection> -f <SKILL_DIR>/examples/seed_messy_sv_estate.sql
uv run --project <SKILL_DIR>/../.. python <SKILL_DIR>/../../scripts/sv_estate_scan.py \
  -c <connection> -d <db> -s SV_INGEST_LAB -o /tmp/lab.json
uv run --project <SKILL_DIR>/../.. python <SKILL_DIR>/../../scripts/sv_drift_report.py \
  -c <connection> -e /tmp/lab.json -o /tmp/drift.json
```

| Lab SV | Exercises |
|----|-----------|
| `FINANCE_METRICS_SV` | Canonical metrics; `gross_revenue` → `IMPORT_CONFLICT`; `adjusted_gross` → `DERIVES_FROM_GOVERNED_COLUMN` |
| `SALES_METRICS_SV` | `net_revenue` homonym, different formula → `CROSS_DOMAIN_HOMONYM` |
| `LEGACY_FINANCE_SV` | `net_revenue` omits refunds → `CROSS_SV_CONFLICT` within Finance |
| `ENTERPRISE_CONSOLIDATED_SV` | Multi-table: `net_revenue`/`region` reassigned to Finance via `LINEAGE_COLUMN`; `total_bookings` stays via `LOCATION_MAP` |

---

## Boundaries

- Use only **confirmed** `SYSTEM$..._GLOSSARY_*` functions (see `../../reference/API_CONTRACT_CRUD.md` and `../../reference/API_CONTRACT_READ.md`). No `SYSTEM$IMPORT_GLOSSARY_FROM_SEMANTIC_VIEWS`, no reverse-lookup function — they do not exist. (`DELETE_GLOSSARY_TERM` **does** exist and is documented in `API_CONTRACT_CRUD.md`.)
- Derivation uses `DERIVES` — source is the input concept, target is the derived metric.
- No auto-approve; batch approve only after steward review.
- No auto `CREATE OR REPLACE SEMANTIC VIEW`.
- `DESC SEMANTIC VIEW` is the source of truth for expressions (not a Studio paraphrase).

## Related skills

| Skill | Relationship |
|-------|--------------|
| `../import` | Parallel ingress (CSV/Sense); dedup + `IMPORT_CONFLICT` with sv-ingest |
| `../workflow` | Forward path (ontology→SV); sv-ingest is the reverse |
| `$cortex-sense` | Optional; formula variants enrich drift context |
| `$semantic-view` | Patch SV when governance wins a conflict |
| `$semantic-view debug` | Validate Analyst after bindings |
