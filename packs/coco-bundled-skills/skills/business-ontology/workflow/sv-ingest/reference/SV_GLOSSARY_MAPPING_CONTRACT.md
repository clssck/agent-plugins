# Semantic View → Business Ontology mapping contract

> **Status:** Skill-side contract. **Adds no new backend surface** — it uses only the
> `SYSTEM$..._GLOSSARY_*` functions already documented in `../../../reference/API_CONTRACT.md`
> (same Business Ontology feature gate as the rest of the skill). There is **no**
> `SYSTEM$IMPORT_GLOSSARY_FROM_SEMANTIC_VIEWS`; ingest is via the documented `DRAFT`/`APPROVE` calls.

## Purpose

Reverse-ingest path: read instantiated Semantic Views → propose **ontology nodes**,
**`RELATED_SEMANTIC_VIEW` associations**, and (from lineage) **`derives` relationships** —
resolving domain/identity from **column lineage first**, SV name last.

| Path | Source | Skill |
|------|--------|-------|
| A | CSV / spreadsheet | `../../import` |
| B | Cortex Sense manifest | `../../import` (cortex-sense promotion) |
| **C (this)** | **Semantic View estate** | **`../` (`$business-ontology sv-ingest`)** |

## Scan inputs (all read-only)

| Source | Use |
|--------|-----|
| `SHOW SEMANTIC VIEWS IN ACCOUNT` (`--format JSON`) | Inventory (filter db/schema/name) |
| `DESC SEMANTIC VIEW <fqn>` (`--format JSON`) | Authoritative fields: 5 columns `object_kind, object_name, parent_entity, property, property_value` |
| `SHOW COLUMNS IN TABLE <base_fqn>` | Physical column set → extract referenced columns from expressions |
| `SYSTEM$GET_GLOSSARY_TERM_LIST` / `_ASSETS` | Existing terms + invert asset associations (lineage index) |
| `domain_map` (see `../domain_map.example.yaml`) | DB/schema/SV-name → domain (fallback only) |

`object_kind` field values that produce candidates: **METRIC, DERIVED_METRIC, DIMENSION, FACT**
(FACT off by default). `DERIVED_METRIC` (global metric) has no base table / columns.

## Candidate term (per SV field)

```yaml
candidate:
  name: "Net Revenue"                 # humanized from field name (or first COMMENT sentence)
  itemKind: METRIC | DIMENSION_CONCEPT | MEASURE_CONCEPT   # from object_kind
  field_kind: METRIC | DERIVED_METRIC | DIMENSION | FACT
  field_name: NET_REVENUE
  logical_table: revenue_daily          # DESC parent_entity
  base_table_fqn: MY_DB.SCHEMA.REVENUE_DAILY   # from TABLE object_kind BASE_TABLE_* rows
  base_columns:                          # expression identifiers ∩ base table columns
    - MY_DB.SCHEMA.REVENUE_DAILY.GROSS_REVENUE_AMOUNT
    - MY_DB.SCHEMA.REVENUE_DAILY.DISCOUNT_AMOUNT
    - MY_DB.SCHEMA.REVENUE_DAILY.REFUND_AMOUNT
  formula: "SUM(gross_revenue_amount) - SUM(discount_amount) - SUM(refund_amount)"   # maps directly to SYSTEM$DRAFT_GLOSSARY_TERM "formula" field — never embed in description
  data_type: NUMBER(32,2)
  synonyms: []
  description: "<SV field COMMENT if present, else leave empty>"
```

### itemKind mapping

User-facing kinds: `TERM, METRIC, ENTITY`. The backend also accepts `DIMENSION_CONCEPT` and
`MEASURE_CONCEPT`, which this sub-skill uses internally for SV-derived fields — do not use these
in import or create flows.

| SV `object_kind` | ontology `itemKind` |
|------------------|---------------------|
| METRIC / DERIVED_METRIC | `METRIC` |
| DIMENSION | `DIMENSION_CONCEPT` |
| FACT | `MEASURE_CONCEPT` |
| TABLE (logical entity) | `ENTITY` or skip (prefer field-level) |

## Domain resolution (lineage-first)

Domain is **not** the SV name. Resolved per field via the ladder in `DRIFT_CLASSIFICATION.md`:
`LINEAGE_COLUMN` → `LINEAGE_TABLE` → `LOCATION_MAP`. The `domain_map` file is the fallback only.

## Association payload (confirmed signatures — see `../../../reference/API_CONTRACT.md`)

`refType` ∈ **`TABLE, VIEW, COLUMN, SEMANTIC_VIEW, DASHBOARD`**. `associationRole` convention:
`RELATED_SEMANTIC_VIEW` for SV, `DESCRIBES` for table/column. `dimensionName` carries the
metric/dimension logical field name.

```sql
-- draft(term, asset_ref_json, association_role)  → asset_ref_json needs fqn (or objectName)
CALL SYSTEM$DRAFT_GLOSSARY_ASSET(
  'Net Revenue',
  '{"refType":"SEMANTIC_VIEW","fqn":"MY_DB.SCHEMA.FINANCE_METRICS_SV","dimensionName":"net_revenue"}',
  'RELATED_SEMANTIC_VIEW'
);
CALL SYSTEM$APPROVE_GLOSSARY_ASSET(
  'Net Revenue',
  '{"refType":"SEMANTIC_VIEW","fqn":"MY_DB.SCHEMA.FINANCE_METRICS_SV","dimensionName":"net_revenue"}'
);
```

Derivation (metric built on governed columns):

```sql
CALL SYSTEM$DRAFT_GLOSSARY_TERM('{"name":"Adjusted Gross","domainName":"Finance","itemKind":"METRIC","description":"...","formula":"SUM(gross_revenue_amount)*0.9"}');
-- Draft response is JSON. Extract termId: PARSE_JSON(<response>):termId::STRING
-- Example response: {"termId": "abc-123-...", "status": "DRAFT", "name": "Adjusted Gross", ...}
CALL SYSTEM$APPROVE_GLOSSARY_TERM('<termId from draft response>');
-- DRAFT_GLOSSARY_RELATIONSHIP requires 4 positional args: sourceFQN, targetFQN, type, label.
-- The label argument is REQUIRED — always auto-fill for standard types; NULL is not accepted.
-- Full vocabulary in ../../../reference/RELATIONSHIP_TYPES.md
CALL SYSTEM$DRAFT_GLOSSARY_RELATIONSHIP('Finance.Gross Revenue', 'Finance.Adjusted Gross', 'DERIVES', 'derives');
```

Batch approve (after steward review):

```sql
CALL SYSTEM$APPROVE_ALL_GLOSSARY_ASSETS();          -- all pending drafts
CALL SYSTEM$APPROVE_ALL_GLOSSARY_TERMS('[...]');     -- optional scoped id/name list
```

## Multi-SV / same name

| Rule | Behavior |
|------|----------|
| Uniqueness today | `(containerId, normalizedCanonicalName)` — **no `scope` field** yet |
| Same name, different domains | **Allowed** — separate ontology node record per domain (`CROSS_DOMAIN_HOMONYM`) |
| Same name, same resolved domain, different expressions | **Conflict** (`CROSS_SV_CONFLICT`) |
| One term, multiple SV bindings | **Allowed** with steward approval |

## Write ordering

A term must be **APPROVED before** an asset or relationship can be drafted against it
(`DRAFT_GLOSSARY_ASSET`/`_RELATIONSHIP` on a DRAFT term returns `Term not found`). Per new term:

```sql
CALL SYSTEM$DRAFT_GLOSSARY_TERM('{...}');
-- termId extraction: the draft response is JSON — extract via PARSE_JSON(<response>):termId::STRING
-- Example response shape: {"termId": "abc-123-...", "status": "DRAFT", "name": "...", ...}
-- Use termId for APPROVE. Use FQN '<domain>.<term>' for ASSET and RELATIONSHIP calls.
-- ⚠ FQN syntax requires an account-level feature enabled by Snowflake.
--   Without it, '<domain>.<term>' resolves as a bare name (dots included) and fails with "term not found".
--   If you cannot confirm the feature is on, use the termId from draft responses for all calls.
CALL SYSTEM$APPROVE_GLOSSARY_TERM('<termId from draft response>');
CALL SYSTEM$DRAFT_GLOSSARY_ASSET('<domain>.<term>', '<ref>', 'RELATED_SEMANTIC_VIEW');
CALL SYSTEM$APPROVE_GLOSSARY_ASSET('<domain>.<term>', '<ref>');
-- DRAFT_GLOSSARY_RELATIONSHIP label arg is REQUIRED — never pass NULL; auto-fill for standard types.
CALL SYSTEM$DRAFT_GLOSSARY_RELATIONSHIP('<domain>.<src>','<domain>.<term>','DERIVES','derives');
CALL SYSTEM$APPROVE_GLOSSARY_RELATIONSHIP('<domain>.<src>','<domain>.<term>','DERIVES');
```

## Idempotency

- Skip if `SEMANTIC_VIEW` binding already present (`SYSTEM$GET_GLOSSARY_TERM_ASSETS` fqn+dimensionName).
- Bound term with drifted expression → `EXPRESSION_DRIFT` (never silent overwrite).
- `SYSTEM$GET_GLOSSARY_TERM_LIST` returns APPROVED only — re-run drift after approvals to re-dedupe.

## Known limitations

Active backend gaps that affect this flow are tracked in `../../../reference/NOT_IMPLEMENTED_YET.md` (Gap #2 — provenance on draft records; Gap #7 — draft visibility in term list; reverse asset lookup; ontology-binding YAML on SV DDL — Gap #3).
