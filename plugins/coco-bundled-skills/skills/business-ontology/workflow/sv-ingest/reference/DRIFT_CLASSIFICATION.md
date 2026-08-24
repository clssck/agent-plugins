# Drift classification — ontology ↔ Semantic View

Used by `$business-ontology sv-ingest drift` (and the workflow reverse/bootstrap path).

All findings are produced by `../../../scripts/sv_drift_report.py` and sorted BLOCKER → WARN → INFO.
Every finding carries `resolvedDomain` + `domainSource` (how the domain was decided).

## Resolution ladder (how each SV field is matched)

Applied per field, strongest signal first (`resolve_domain()` in `sv_drift_report.py`):

| Rank | Signal | Sets domain via | Outcome |
|------|--------|-----------------|---------|
| 1 | Field already bound (`SEMANTIC_VIEW` assoc: fqn + dimensionName) | — | idempotent; expression-drift check only |
| 2 | Base **COLUMN(s)** in expression are governed | `LINEAGE_COLUMN` | same-name → bind; else derived term + `DERIVES` |
| 3 | Base **TABLE** is governed | `LINEAGE_TABLE` | inherit domain, then name match |
| 4 | `domain_map` location rule | `LOCATION_MAP` | inherit domain, then name match |
| 5 | Name match within resolved domain | — | bind, conflict, or unmapped |

**Why lineage first:** a metric's meaning comes from the physical columns it aggregates, not from the SV's name. A multi-table SV (e.g. `ENTERPRISE_CONSOLIDATED_SV`) has fields that belong to *different* domains; per-field column lineage resolves each correctly, whereas one-domain-per-SV mislabels them.

## Finding types

| Code | Meaning | Steward action |
|------|---------|----------------|
| `SV_UNMAPPED` | SV field, no governing column/table, no term in resolved domain | Draft term + bind |
| `GLOSSARY_UNBOUND` | Term exists (or governed column with same name) but SV field not yet bound | Draft `RELATED_SEMANTIC_VIEW` association |
| `DERIVES_FROM_GOVERNED_COLUMN` | Metric built from governed columns, but its own name is not yet a term | Draft derived term + `DERIVES` from each column term + bind |
| `EXPRESSION_DRIFT` | **Bound** term formula ≠ SV expression | Update term **or** patch SV (engineer) |
| `IMPORT_CONFLICT` | Existing APPROVED term (CSV/Sense) in resolved domain ≠ SV expression | Side-by-side; pick canon |
| `CROSS_SV_CONFLICT` | Two+ SVs, same resolved domain + name, different expressions | Pick canonical SV or split scoped terms |
| `CROSS_DOMAIN_HOMONYM` | Same name across resolved domains — **not an error** | Keep separate terms per domain |
| `STALE_BINDING` | Association `validity` = STALE / TARGET_MISSING | Re-bind or remove |

## Severity

| Severity | Types |
|----------|-------|
| **BLOCKER** | `EXPRESSION_DRIFT` on a bound term (Analyst executes a diverged formula) |
| **WARN** | `IMPORT_CONFLICT`, `CROSS_SV_CONFLICT`, `STALE_BINDING` |
| **INFO** | `SV_UNMAPPED`, `GLOSSARY_UNBOUND`, `DERIVES_FROM_GOVERNED_COLUMN`, `CROSS_DOMAIN_HOMONYM` |

## Derivation is modeled with real relationship types

Ontology relationships use the full vocabulary in `../../../reference/RELATIONSHIP_TYPES.md`.
There is **no** `DERIVED_FROM`. Derivation is therefore expressed as:

```sql
CALL SYSTEM$DRAFT_GLOSSARY_RELATIONSHIP('Gross Revenue', 'Adjusted Gross', 'DERIVES', NULL);
```

("Gross Revenue `DERIVES` → Adjusted Gross": source is the input concept, target is the derived metric.)

## Reconciliation playbook

```text
1. Run drift (read-only). Steward reviews sorted findings (the checkpoint is on the report).
2. Per finding choose one:
   - APPROVE the proposed sequence (new term + binding, or bind existing term, + DERIVES)
   - UPDATE_GLOSSARY_TERM (meaning wins)
   - PATCH_SV via $semantic-view / Studio (execution wins)
   - SPLIT scoped term variant in same domain
   - DEPRECATE term / ignore SV field (log reason)
3. Execute approved findings in the ORDER emitted by proposedCalls (see constraint below).
4. Re-run drift until BLOCKER = 0 (or accepted exceptions logged). Re-runs are idempotent:
   an already-approved+bound field resolves at rank 1 and produces no new finding.
```

### Ordering constraint

A term must be **APPROVED before** an asset or relationship can be drafted against it —
`DRAFT_GLOSSARY_ASSET` / `DRAFT_GLOSSARY_RELATIONSHIP` on a still-DRAFT term fail with
`Term not found`. So each new-term finding runs as an ordered unit:

```text
DRAFT_GLOSSARY_TERM → APPROVE_GLOSSARY_TERM
   → DRAFT_GLOSSARY_ASSET → APPROVE_GLOSSARY_ASSET
   → (per upstream) DRAFT_GLOSSARY_RELATIONSHIP → APPROVE_GLOSSARY_RELATIONSHIP
```

`SYSTEM$APPROVE_ALL_GLOSSARY_{TERMS,ASSETS,RELATIONSHIPS}` batch-approve is therefore only useful
for a set of independent **term** drafts, not for term+binding pairs created in one pass.
`sv_drift_report.py` already emits `proposedCalls` in the correct order.

## Never auto-apply

- No `CREATE OR REPLACE SEMANTIC VIEW` from ontology text without engineer checkpoint
- No `UPDATE_GLOSSARY_TERM` from SV without steward checkpoint
- No merge of cross-domain homonyms without explicit steward choice
- No auto-approve — batch approve only after the steward has reviewed the worklist

## Known limitations

Active backend gaps that affect drift quality are tracked in `../../../reference/NOT_IMPLEMENTED_YET.md`: Gap #2 (no provenance on draft records → sidecar `drift_report.json`), Gap #7 (`TERM_LIST` returns APPROVED only → re-run drift after approvals), and the reverse asset→terms lookup gap (invert `SYSTEM$GET_GLOSSARY_TERM_ASSETS` client-side).

## Evidence JSON (sidecar until a provenance field ships)

```json
{
  "type": "DERIVES_FROM_GOVERNED_COLUMN",
  "severity": "INFO",
  "termName": "Adjusted Gross",
  "resolvedDomain": "Finance",
  "domainSource": "LINEAGE_COLUMN",
  "svFqn": "SV_INGEST_DB.SV_INGEST_LAB.FINANCE_METRICS_SV",
  "fieldName": "ADJUSTED_GROSS",
  "expression": "SUM(gross_revenue_amount) * 0.9",
  "governingColumnTerms": ["Gross Revenue"],
  "proposedCalls": ["CALL SYSTEM$DRAFT_GLOSSARY_TERM(...)", "CALL SYSTEM$DRAFT_GLOSSARY_RELATIONSHIP('Gross Revenue','Adjusted Gross','DERIVES');"]
}
```
