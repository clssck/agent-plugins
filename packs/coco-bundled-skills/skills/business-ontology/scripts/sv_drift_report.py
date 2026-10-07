#!/usr/bin/env python3
"""Compare sv_estate.json to ontology data with lineage-first resolution.

Resolution ladder per SV field (strongest signal first):
  1. Field already bound  (SEMANTIC_VIEW association fqn+dimensionName match)
  2. Base COLUMN(s) governed → inherit domain, propose bind or UPSTREAM_OF derivation
  3. Base TABLE governed → inherit domain
  4. domain_map location rule → domain (fallback)
  5. name match within resolved domain

Emits drift_report.json: steward-ready findings sorted BLOCKER→WARN→INFO.

Reverse asset→terms lookup has no SYSTEM$ function, so we invert
GET_GLOSSARY_TERM_ASSETS client-side (one call per relevant term).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sv_common import (
    normalize_expr,
    normalize_name,
    object_type_to_ref_type,
    run_snow,
    run_snow_batch,
    unwrap_procedure_json,
)


def _q(v: str) -> str:
    return v.replace("'", "''")


def extract_formula(description: str | None) -> str:
    if not description:
        return ""
    low = description.lower()
    idx = low.find("formula:")
    if idx >= 0:
        tail = description[idx + len("formula:"):]
        for stop in [". ", ".\n"]:
            j = tail.find(stop)
            if j >= 0:
                tail = tail[:j]
        return tail.strip()
    return description


def expressions_compatible(ontology_text: str, sv_expr: str) -> bool:
    g = normalize_expr(ontology_text)
    s = normalize_expr(sv_expr)
    if not g or not s:
        return False
    if g == s:
        return True
    g_core = g.replace("SUM(", "").replace("COUNT(", "").replace(")", "")
    s_core = s.replace("SUM(", "").replace("COUNT(", "").replace(")", "")
    return g_core == s_core or g_core in s_core or s_core in g_core


class OntologyIndex:
    def __init__(self) -> None:
        self.by_domain_name: dict[tuple[str, str], dict] = {}
        self.column_terms: dict[str, list[dict]] = defaultdict(list)   # COLUMN fqn upper -> terms
        self.table_terms: dict[str, list[dict]] = defaultdict(list)    # TABLE fqn upper -> terms
        self.sv_field_bindings: set[tuple[str, str]] = set()           # (sv fqn upper, dim lower)
        self.term_sv_assets: dict[str, list[dict]] = defaultdict(list) # term name -> SV assets

    def term(self, domain: str, name: str) -> dict | None:
        return self.by_domain_name.get((domain, normalize_name(name)))


def build_index(
    connection: str, warehouse: str, domains_of_interest: set[str], scope_to_domains: bool, role: str = "",
    chunk: int = 50,
) -> OntologyIndex:
    """Build the ontology index and invert asset associations client-side.

    Lineage is inherently cross-domain (a metric whose SV lives in one domain can be
    governed by a column term in another), so by default we invert assets for **all**
    terms — not just the SVs' location domains. `scope_to_domains=True` restricts the
    inversion to `domains_of_interest` as a speed knob for very large glossaries.

    Asset inversion is batched: N per-term CALLs run in one `snow` process (chunked),
    collapsing hundreds of process startups into a handful.
    """
    idx = OntologyIndex()
    rows = run_snow(connection, "CALL SYSTEM$GET_GLOSSARY_TERM_LIST('', 'DOMAIN');", warehouse=warehouse, role=role)
    terms = unwrap_procedure_json(rows).get("terms", [])
    for t in terms:
        idx.by_domain_name[(t.get("domain", ""), normalize_name(t["name"]))] = t

    relevant = [t for t in terms if not scope_to_domains or t.get("domain", "") in domains_of_interest]
    for start in range(0, len(relevant), chunk):
        batch = relevant[start:start + chunk]
        sqls = [f"CALL SYSTEM$GET_GLOSSARY_TERM_ASSETS('{_q(t['name'])}', '');" for t in batch]
        result_sets = run_snow_batch(connection, sqls, warehouse=warehouse, role=role)
        for t, arows in zip(batch, result_sets):
            for a in unwrap_procedure_json(arows).get("assets", []):
                ref = object_type_to_ref_type(a.get("objectType"))
                fqn = (a.get("fqn") or "").upper()
                if ref == "COLUMN" and fqn:
                    idx.column_terms[fqn].append(t)
                elif ref == "TABLE" and fqn:
                    idx.table_terms[fqn].append(t)
                elif ref == "SEMANTIC_VIEW" and fqn:
                    idx.term_sv_assets[t["name"]].append(a)
                    dim = (a.get("dimensionName") or "").lower()
                    idx.sv_field_bindings.add((fqn, dim))
    return idx


def resolve_domain(field: dict, idx: OntologyIndex, location_domain: str) -> tuple[str, str, list[dict]]:
    """Return (resolved_domain, domain_source, governing_column_terms)."""
    col_terms: list[dict] = []
    for col in field.get("base_columns", []):
        col_terms.extend(idx.column_terms.get(col.upper(), []))
    if col_terms:
        dom = Counter(t.get("domain", "") for t in col_terms).most_common(1)[0][0]
        return dom, "LINEAGE_COLUMN", col_terms
    if field.get("base_table_fqn"):
        tbl_terms = idx.table_terms.get(field["base_table_fqn"].upper(), [])
        if tbl_terms:
            dom = Counter(t.get("domain", "") for t in tbl_terms).most_common(1)[0][0]
            return dom, "LINEAGE_TABLE", []
    return location_domain, "LOCATION_MAP", []


def _asset_ref(sv_fqn: str, dim: str) -> str:
    return f'{{"refType":"SEMANTIC_VIEW","fqn":"{sv_fqn}","dimensionName":"{dim}"}}'


def bind_existing_calls(term_name: str, sv_fqn: str, dim: str) -> list[str]:
    """Bind an SV field to an ALREADY-APPROVED term (draft asset then approve)."""
    t, ref = _q(term_name), _asset_ref(sv_fqn, dim)
    return [
        f"CALL SYSTEM$DRAFT_GLOSSARY_ASSET('{t}','{ref}','RELATED_SEMANTIC_VIEW');",
        f"CALL SYSTEM$APPROVE_GLOSSARY_ASSET('{t}','{ref}');",
    ]


def draft_calls(
    term_name: str, domain: str, item_kind: str, sv_fqn: str, dim: str, description: str,
    upstream_terms: list[str] | None = None,
) -> list[str]:
    """Full ordered reconcile sequence for a NEW term.

    IMPORTANT ordering constraint: a term must be APPROVED before an
    asset or relationship can be drafted against it — DRAFT_GLOSSARY_ASSET/RELATIONSHIP on a
    still-DRAFT term fail with "Term not found". So: draft term → approve term → draft/approve
    asset → draft/approve each UPSTREAM_OF relationship.
    """
    t, d = _q(term_name), _q(description[:180].replace("\n", " "))
    ref = _asset_ref(sv_fqn, dim)
    calls = [
        f"CALL SYSTEM$DRAFT_GLOSSARY_TERM('{{\"name\":\"{t}\",\"domainName\":\"{_q(domain)}\","
        f"\"itemKind\":\"{item_kind}\",\"description\":\"{d}\"}}');",
        f"CALL SYSTEM$APPROVE_GLOSSARY_TERM('{t}');",
        f"CALL SYSTEM$DRAFT_GLOSSARY_ASSET('{t}','{ref}','RELATED_SEMANTIC_VIEW');",
        f"CALL SYSTEM$APPROVE_GLOSSARY_ASSET('{t}','{ref}');",
    ]
    for src in (upstream_terms or []):
        s = _q(src)
        calls.append(f"CALL SYSTEM$DRAFT_GLOSSARY_RELATIONSHIP('{s}','{t}','UPSTREAM_OF', NULL);")
        calls.append(f"CALL SYSTEM$APPROVE_GLOSSARY_RELATIONSHIP('{s}','{t}','UPSTREAM_OF');")
    return calls


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection", "-c", default="", help="snow CLI connection (default: CLI default)")
    parser.add_argument("--estate", "-e", required=True)
    parser.add_argument("--output", "-o", default="/tmp/drift_report.json")
    parser.add_argument("--warehouse", default="")
    parser.add_argument("--role", default="", help="role to run as (default: connection default)")
    parser.add_argument("--scope-to-domains", action="store_true",
                        help="only invert assets for terms in the SVs' location domains (faster; may miss cross-domain lineage)")
    args = parser.parse_args()

    try:
        estate = json.loads(Path(args.estate).read_text())
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Error: could not load estate file {args.estate!r}: {exc}", file=sys.stderr)
        return 1
    svs = estate.get("semantic_views", [])
    location_domains = {sv.get("location_domain", "Default") for sv in svs}
    idx = build_index(args.connection, args.warehouse, location_domains, args.scope_to_domains, args.role)

    findings: list[dict[str, Any]] = []
    # (resolved_domain, normalized_name) -> list of field entries (for conflict/homonym)
    resolved_index: dict[tuple[str, str], list[dict]] = defaultdict(list)

    for sv in svs:
        loc = sv.get("location_domain", "Default")
        for c in sv.get("candidates", []):
            dom, dom_src, col_terms = resolve_domain(c, idx, loc)
            entry = {
                "termName": c["name"],
                "itemKind": c["itemKind"],
                "fieldKind": c["field_kind"],
                "svFqn": sv["fqn"],
                "fieldName": c["field_name"],
                "expression": c.get("formula_text"),
                "baseTable": c.get("base_table_fqn"),
                "baseColumns": c.get("base_columns", []),
                "resolvedDomain": dom,
                "domainSource": dom_src,
                "locationDomain": loc,
            }
            resolved_index[(dom, normalize_name(c["name"]))].append(entry)

            existing = idx.term(dom, c["name"])
            sv_key = (sv["fqn"].upper(), c["field_name"].lower())
            already_bound = sv_key in idx.sv_field_bindings

            is_metric = c["itemKind"] == "METRIC"

            # Rank 1: already bound → expression drift check only
            if already_bound and existing:
                gform = extract_formula(existing.get("description"))
                if is_metric and c.get("formula_text") and gform and not expressions_compatible(gform, c["formula_text"]):
                    findings.append({
                        "type": "EXPRESSION_DRIFT", "severity": "BLOCKER", **entry,
                        "ontologyFormula": gform, "termStatus": existing.get("status"),
                        "recommendedAction": "Steward: UPDATE_GLOSSARY_TERM or PATCH_SV (bound metric diverged)",
                    })
                continue

            # Rank 2: governed base columns → derivation or same-term bind
            if col_terms and not existing:
                col_names = sorted({t["name"] for t in col_terms})
                # If a governing column term has the SAME display name, it's the same concept → bind.
                same = [t for t in col_terms if normalize_name(t["name"]) == normalize_name(c["name"])]
                if same:
                    findings.append({
                        "type": "ONTOLOGY_UNBOUND", "severity": "INFO", **entry,
                        "note": "Governed column term matches metric name — bind SV field to it.",
                        "recommendedAction": "DRAFT_GLOSSARY_ASSET (RELATED_SEMANTIC_VIEW) to existing term",
                        "proposedCalls": bind_existing_calls(same[0]["name"], sv["fqn"], c["field_name"]),
                    })
                else:
                    findings.append({
                        "type": "DERIVES_FROM_GOVERNED_COLUMN", "severity": "INFO", **entry,
                        "governingColumnTerms": col_names,
                        "note": "Metric derives from governed columns — new derived term + UPSTREAM_OF links.",
                        "recommendedAction": "DRAFT+APPROVE derived term, then bind SV, then UPSTREAM_OF from each column term",
                        "proposedCalls": draft_calls(
                            c["name"], dom, c["itemKind"], sv["fqn"], c["field_name"], entry["expression"] or "",
                            upstream_terms=col_names,
                        ),
                    })
                continue

            # Rank 5: name match within resolved domain
            if existing:
                gform = extract_formula(existing.get("description"))
                if is_metric and c.get("formula_text") and gform and not expressions_compatible(gform, c["formula_text"]):
                    findings.append({
                        "type": "IMPORT_CONFLICT" if existing.get("status") == "APPROVED" else "EXPRESSION_DRIFT",
                        "severity": "WARN" if existing.get("status") == "APPROVED" else "BLOCKER",
                        **entry, "ontologyFormula": gform, "termStatus": existing.get("status"),
                        "recommendedAction": "Side-by-side: UPDATE_GLOSSARY_TERM, PATCH_SV, or scoped variant",
                    })
                else:
                    findings.append({
                        "type": "ONTOLOGY_UNBOUND", "severity": "INFO", **entry,
                        "recommendedAction": "DRAFT_GLOSSARY_ASSET (RELATED_SEMANTIC_VIEW) to existing term",
                        "proposedCalls": bind_existing_calls(existing["name"], sv["fqn"], c["field_name"]),
                    })
            else:
                findings.append({
                    "type": "SV_UNMAPPED", "severity": "INFO", **entry,
                    "recommendedAction": "DRAFT+APPROVE term, then DRAFT+APPROVE SV binding",
                    "proposedCalls": draft_calls(
                        c["name"], dom, c["itemKind"], sv["fqn"], c["field_name"], entry["expression"] or ""
                    ),
                })

    # Cross-SV conflict (same resolved domain + name, different expressions)
    for (dom, nm), entries in resolved_index.items():
        exprs = {normalize_expr(e["expression"]) for e in entries if e["expression"]}
        if len(entries) > 1 and len(exprs) > 1:
            findings.append({
                "type": "CROSS_SV_CONFLICT", "severity": "WARN",
                "resolvedDomain": dom, "termName": entries[0]["termName"],
                "svFields": [{"svFqn": e["svFqn"], "fieldName": e["fieldName"], "expression": e["expression"]} for e in entries],
                "recommendedAction": "Pick canonical SV or split scoped terms (e.g. 'Net Revenue (Legacy)')",
            })

    # Cross-domain homonym (same name, multiple resolved domains) — informational
    name_domains: dict[str, set[str]] = defaultdict(set)
    for (dom, nm), entries in resolved_index.items():
        name_domains[nm].add(dom)
    for nm, doms in name_domains.items():
        if len(doms) > 1:
            findings.append({
                "type": "CROSS_DOMAIN_HOMONYM", "severity": "INFO",
                "termName": nm.title(), "domains": sorted(doms),
                "recommendedAction": "Keep separate terms per domain; do not merge",
            })

    order = {"BLOCKER": 0, "WARN": 1, "INFO": 2}
    findings.sort(key=lambda f: (order.get(f.get("severity", "INFO"), 9), f.get("type", "")))
    counts = dict(sorted(Counter(f["type"] for f in findings).items()))

    report = {
        "findings": findings,
        "findingCount": len(findings),
        "countsByType": counts,
        "domainsScanned": sorted(location_domains),
        "domainResolution": dict(sorted(Counter(
            f.get("domainSource", "n/a") for f in findings if "domainSource" in f
        ).items())),
        "ontologySummary": unwrap_procedure_json(
            run_snow(args.connection, "CALL SYSTEM$GET_GLOSSARY_SUMMARY();", warehouse=args.warehouse, role=args.role)
        ),
    }
    Path(args.output).write_text(json.dumps(report, indent=2))
    print(f"Wrote {args.output} ({len(findings)} findings)")
    for t, n in counts.items():
        print(f"  {t}: {n}")
    print(f"  domain resolution: {report['domainResolution']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
